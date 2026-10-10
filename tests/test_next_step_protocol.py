import json

import pytest

from apixly_jev_harness import Action, AgentLoop, Engine, Option, Parameter, Task, Workflow


def provider_result(items, choice):
    return {
        "ok": True,
        "usage_complete": True,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "results": [
            {
                "id": items[0]["id"],
                "ok": True,
                "answers": {
                    "target": {"type": "choice", "choice": choice, "probabilities": {choice: 1.0}}
                },
            }
        ],
    }


@pytest.mark.parametrize("reverse", [False, True])
def test_non_browser_loop_has_next_step_scope_and_stable_id_binding(monkeypatch, tmp_path, reverse):
    executed = []
    seen = []

    class Artifact(Workflow):
        def observe(self, ctx):
            return {"digest_checked": bool(executed), "artifact_exists": True}

        def verify(self, ctx, state):
            return state["digest_checked"]

        def candidates(self, ctx, state):
            actions = [
                Action("submit", "Submit only after digest verification"),
                Action("verify", "Check digest of the artifact"),
            ]
            return list(reversed(actions)) if reverse else actions

        def execute(self, ctx, action):
            executed.append(action.id)

    def provider(items, **kwargs):
        body = items[0]["request"]
        seen.append(body)
        assert body["state"]["context"]["decision_stage"] == "tool_selection"
        assert "NEXT step" in body["questions"]["target"]["instructions"]
        assert "without completing" in body["questions"]["target"]["instructions"]
        # The caller supplied an artifact contract, not a UI form. Do not invent one.
        assert "requested fields" not in body["state"]["task"]
        assert "controls are satisfied" not in body["state"]["task"]
        choices = body["questions"]["target"]["criteria"]
        chosen = next(
            key
            for key, value in choices.items()
            if isinstance(value, dict) and value["properties"]["id"] == "verify"
        )
        return provider_result(items, chosen)

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", provider)
    result = AgentLoop().run(
        Artifact(),
        goal="Verify the artifact digest before submission",
        archive=tmp_path / "run.jsonl",
    )
    assert result["status"] == "done"
    assert executed == ["verify"]
    assert len(seen) == 1


def test_parameter_scope_and_private_binding_remain_distinct(monkeypatch, tmp_path):
    done = []
    task = Task(observe=lambda ctx: {"done": bool(done)}, verify=lambda ctx, state: state["done"])

    @task.tool(
        "Inspect an observed object",
        parameters={
            "target": Parameter(
                "Object needing inspection",
                [
                    Option("a", "First existing object", "PRIVATE_A"),
                    Option("b", "Second existing object", "PRIVATE_B"),
                ],
            )
        },
    )
    def inspect(target):
        done.append(target)

    calls = []

    def provider(items, **kwargs):
        body = items[0]["request"]
        calls.append(body)
        stage = body["state"]["context"]["decision_stage"]
        assert stage == ("tool_selection" if len(calls) == 1 else "parameter_selection")
        if stage == "parameter_selection":
            assert "selected_tool" in body["questions"]["target"]["instructions"]
            assert body["state"]["context"]["selected_tool"] == "inspect"
        assert "PRIVATE_" not in json.dumps(body)
        return provider_result(items, "c0" if len(calls) == 1 else "c1")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", provider)
    result = AgentLoop().run(
        task, goal="Inspect the second observed object", archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "done"
    assert done == ["PRIVATE_B"]


def test_direct_record_selection_does_not_acquire_loop_semantics(monkeypatch):
    def provider(items, **kwargs):
        body = items[0]["request"]
        assert "decision_stage" not in body["state"]["context"]
        assert "NEXT step" not in body["questions"]["target"]["instructions"]
        return provider_result(items, "c0")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", provider)
    packet = Engine().decide(
        [{"id": "record", "text": "Relevant record"}],
        goal="Select the relevant record",
        analysis_spec={"mode": "choose"},
    )
    assert packet["selected_ids"] == ["record"]
