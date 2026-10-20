import json

import pytest

from apixly_jev_harness import AgentLoop, Engine, Task, task_cli
from apixly_jev_harness.mcp import main as mcp_main
from apixly_jev_harness.toolkit import ToolkitSession

MOVING_OR_MALFORMED = [
    "jev-latest",
    "jev-preview",
    "jev-1.14",
    "1.14.0",
    "jev-1.14.0 ",
    "",
    None,
    14,
]


def counter_task():
    state = {"value": 0}
    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, s: s["value"] == 1)

    @task.tool("Advance the value", parameters={"amount": [1, 2]})
    def advance(amount):
        state["value"] += amount
        return dict(state)

    return task


def recording_provider(models):
    def provider(items, **kwargs):
        body = items[0]["request"]
        models.append(body["model"])
        return {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 1, "output_tokens": 0},
            "results": [
                {
                    "id": items[0]["id"],
                    "ok": True,
                    "model": body["model"],
                    "answers": {
                        "target": {"type": "choice", "choice": "c0", "probabilities": {"c0": 1.0}}
                    },
                }
            ],
        }

    return provider


def test_default_run_pins_the_stable_versioned_model(monkeypatch):
    models = []
    monkeypatch.setattr("apixly_jev_harness.backend.native_run", recording_provider(models))
    result = AgentLoop().run(counter_task(), goal="Reach one")
    assert result["status"] == "done"
    assert models and set(models) == {"jev-1.13.0"}
    assert {call["model_requested"] for call in result["telemetry"]["calls"]} == {"jev-1.13.0"}


def test_caller_selected_model_reaches_every_stage_and_telemetry(monkeypatch):
    models = []
    monkeypatch.setattr("apixly_jev_harness.backend.native_run", recording_provider(models))
    result = AgentLoop(model="jev-1.14.0").run(counter_task(), goal="Reach one")
    assert result["status"] == "done"
    assert len(models) == 2 and set(models) == {"jev-1.14.0"}  # tool, then parameter
    calls = result["telemetry"]["calls"]
    assert {call["model_requested"] for call in calls} == {"jev-1.14.0"}
    assert {call["model_resolved"] for call in calls} == {"jev-1.14.0"}


def test_record_decisions_use_the_engine_model_unless_the_spec_names_one(monkeypatch):
    models = []
    monkeypatch.setattr("apixly_jev_harness.backend.native_run", recording_provider(models))
    records = [{"id": "a", "text": "Act"}]
    Engine(model="jev-1.14.0").decide(records, goal="Choose", analysis_spec={"mode": "choose"})
    Engine(model="jev-1.14.0").decide(
        records, goal="Choose", analysis_spec={"mode": "choose", "model": "jev-1.13.0"}
    )
    assert models == ["jev-1.14.0", "jev-1.13.0"]


@pytest.mark.parametrize("model", MOVING_OR_MALFORMED)
def test_moving_aliases_and_malformed_ids_fail_before_any_call(monkeypatch, model):
    def never(*args, **kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", never)
    with pytest.raises(ValueError, match="versioned_jev_model_required"):
        AgentLoop(model=model)
    with pytest.raises(ValueError, match="versioned_jev_model_required"):
        ToolkitSession(counter_task(), goal="Reach one", model=model)


def test_toolkit_delegation_runs_on_the_session_model(monkeypatch):
    seen = []

    def run(self, workflow, **kwargs):
        seen.append(self.model)
        return {"status": "needs_review", "complete": False, "steps": 0}

    monkeypatch.setattr(AgentLoop, "run", run)
    ToolkitSession(counter_task(), goal="Reach one", model="jev-1.14.0").delegate()
    ToolkitSession(counter_task(), goal="Reach one").delegate()
    assert seen == ["jev-1.14.0", "jev-1.13.0"]


SCRIPT = """from apixly_jev_harness import Task
workflow = Task(observe=lambda c: {}, verify=lambda c, s: False)
"""


def test_cli_run_passes_the_selected_model_to_the_loop(tmp_path, capsys, monkeypatch):
    script = tmp_path / "task.py"
    script.write_text(SCRIPT, newline="\n")
    seen = []

    def run(self, workflow, **kwargs):
        seen.append(self.model)
        return {"status": "needs_review", "complete": False, "telemetry": {}}

    monkeypatch.setattr(task_cli.AgentLoop, "run", run)
    assert task_cli.main(["run", str(script), "--goal", "Inspect", "--model", "jev-1.14.0"]) == 2
    assert task_cli.main(["run", str(script), "--goal", "Inspect"]) == 2
    assert seen == ["jev-1.14.0", "jev-1.13.0"]
    capsys.readouterr()


def test_cli_rejects_alias_model_as_configuration_before_loading_script(tmp_path, capsys):
    marker = tmp_path / "imported"
    script = tmp_path / "task.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nworkflow = None\n", newline="\n"
    )
    assert task_cli.main(["run", str(script), "--goal", "Inspect", "--model", "jev-latest"]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["phase"] == "configuration"
    assert packet["code"] == "invalid_run_configuration"
    assert packet["model_calls"] == 0 and packet["script_loaded"] is False
    assert not marker.exists()


def test_mcp_serves_on_the_selected_model_and_rejects_aliases_early(tmp_path, capsys, monkeypatch):
    marker = tmp_path / "imported"
    script = tmp_path / "task.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n" + SCRIPT, newline="\n"
    )
    assert mcp_main([str(script), "--goal", "Inspect", "--model", "jev-preview"]) == 2
    assert json.loads(capsys.readouterr().out)["phase"] == "configuration"
    assert not marker.exists()

    served = []
    monkeypatch.setattr(
        "apixly_jev_harness.mcp.serve", lambda session, **kwargs: served.append(session.model)
    )
    assert mcp_main([str(script), "--goal", "Inspect", "--model", "jev-1.14.0"]) == 0
    assert served == ["jev-1.14.0"]


def test_machine_spec_documents_the_model_option_and_default(capsys):
    assert task_cli.main(["spec"]) == 0
    run = json.loads(capsys.readouterr().out)["commands"]["run"]
    assert "model" in run["optional"]
    assert run["model"]["default"] == "jev-1.13.0"
    assert run["model"]["moving_aliases_accepted"] is False


def test_backend_names_the_pinned_default_rather_than_the_dependency_default(monkeypatch):
    from apixly_jev_harness import backend

    planned = []
    original = backend.core.plan

    def plan(parts, task, spec):
        planned.append(spec.get("model"))
        return original(parts, task, spec)

    monkeypatch.setattr(backend.core, "plan", plan)
    monkeypatch.setattr("apixly_jev_harness.backend.native_run", recording_provider([]))
    Engine().decide([{"id": "a", "text": "Act"}], goal="Choose", analysis_spec={"mode": "choose"})
    assert planned == [backend.DEFAULT_MODEL]
