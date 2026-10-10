import json

import pytest

from jev_harness import Engine, Option, Task


def test_register_tool_with_dynamic_parameters_and_named_private_value(monkeypatch):
    state = {"done": False, "job_ids": [1820]}
    calls = []
    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])

    @task.tool(
        "Inspect the selected job",
        parameters={
            "job_id": lambda ctx, seen: seen["job_ids"],
            "credential": [Option("service", "Configured service credential", "secret-token")],
        },
    )
    def inspect(job_id, credential):
        calls.append((job_id, credential))
        state["done"] = True

    def choose(parts, goal, workers, spec):
        assert "secret-token" not in json.dumps([parts, spec])
        assert "1820" in parts[0]["text"]
        assert "inspect" in parts[0]["text"]
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE", "answers": {}}
            for i, p in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 10, "output_tokens": 1},
            "requests": 1,
        }

    monkeypatch.setattr("jev_harness.engine.analysis.evaluate", choose)
    assert Engine().run(task, goal="Inspect the failing job")["status"] == "done"
    assert calls == [(1820, "secret-token")]


def test_multiple_tools_and_parameters_are_program_bound():
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool("Read one record", parameters={"job_id": [1, 2], "mode": ["logs", "status"]})
    def read(job_id, mode):
        return job_id, mode

    @task.tool("Refresh source")
    def refresh():
        return "refreshed"

    offered = task.candidates(None, {})
    assert len(offered) == 5
    assert task.execute(None, offered[2]) == (2, "logs")
    assert task.execute(None, offered[-1]) == "refreshed"


def test_unknown_or_modified_action_cannot_dispatch():
    from jev_harness import Action

    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool("Read", parameters={"job_id": [1]})
    def read(job_id):
        raise AssertionError("must not execute")

    offered = task.candidates(None, {})
    with pytest.raises(ValueError):
        task.execute(
            None, Action(offered[0].id, "Read", {"tool": "read", "arguments": {"job_id": 99}})
        )


def test_registration_signature_and_candidate_limits():
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)
    with pytest.raises(ValueError):
        task.tool("Broken", parameters={"unknown": [1]})(lambda required: None)

    @task.tool("Too many", parameters={"a": list(range(254))})
    def many(a):
        return a

    with pytest.raises(ValueError, match="narrow"):
        task.candidates(None, {})


def test_tool_effect_policy_and_empty_parameter_domain():
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool("Send", irreversible=True, parameters={"recipient": []})
    def send(recipient):
        return recipient

    assert task.candidates(None, {}) == []
    assert task.authorize(None, None) is False


def test_agent_loop_carries_admitted_results_and_execution_history(monkeypatch):
    from jev_harness import AgentLoop

    task = Task(
        observe=lambda ctx: {"collected": len(ctx.results)},
        verify=lambda ctx, state: state["collected"] == 2,
    )

    @task.tool(
        "Collect one record",
        parameters={"id": [1]},
        result_context=lambda result: {"finding": result["finding"]},
    )
    def collect(id):
        return {"finding": "current failure", "private": "secret-token"}

    requests = []

    def choose(parts, goal, workers, spec):
        requests.append(spec["context"])
        assert "secret-token" not in json.dumps(spec)
        if len(requests) == 2:
            assert spec["context"]["history"][0]["result"] == {"finding": "current failure"}
            assert spec["context"]["budgets"]["remaining_steps"] == 19
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, p in enumerate(parts)
        }, {"ok": True, "usage_complete": True, "usage": {"input_tokens": 0, "output_tokens": 0}}

    monkeypatch.setattr("jev_harness.engine.analysis.evaluate", choose)
    assert AgentLoop().run(task, goal="Collect two records")["status"] == "done"
    assert len(requests) == 2
