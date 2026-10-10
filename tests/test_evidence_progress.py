import json

import pytest

from apixly_jev_harness import AgentLoop, Option, Parameter, Task


def select_first(parts, task, workers, spec):
    return {
        part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
        for i, part in enumerate(parts)
    }, {
        "ok": True,
        "usage_complete": True,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "requests": 1,
        "models": {},
    }


@pytest.fixture
def loop(monkeypatch):
    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", select_first)
    return AgentLoop()


def test_read_only_evidence_reaches_next_decision(loop, monkeypatch, tmp_path):
    state = {"resolved": False}
    received = []
    workflow = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["resolved"])

    @workflow.tool(
        "Read failure details",
        available=lambda ctx, seen: not ctx.results,
        result_context=lambda result: result,
    )
    def read():
        return {"finding": "Inspect correlated logs next"}

    @workflow.tool("Inspect correlated logs", available=lambda ctx, seen: bool(ctx.results))
    def inspect():
        state["resolved"] = True
        return {"resolved": True}

    def decide(parts, task, workers, spec):
        received.append(spec["context"])
        if len(received) == 2:
            assert spec["context"]["observation"] == {"resolved": False}
            assert spec["context"]["history"][0]["result"] == {
                "finding": "Inspect correlated logs next"
            }
        return select_first(parts, task, workers, spec)

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", decide)
    result = loop.run(workflow, goal="Resolve the failure", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done"
    assert result["steps"] == 2
    assert len(received) == 2


def test_repeated_same_bound_call_and_admitted_result_still_stops(loop):
    calls = []
    workflow = Task(observe=lambda ctx: {"status": "same"}, verify=lambda ctx, state: False)

    @workflow.tool("Read stable status", result_context=lambda result: result)
    def read():
        calls.append(1)
        return {"status": "unchanged"}

    result = loop.run(workflow, goal="Diagnose status", max_steps=10)
    assert result["status"] == "blocked"
    assert result["reason"] == "repeated_action_state"
    assert len(calls) == 1


def test_same_result_for_different_bound_objects_is_new_evidence(loop):
    workflow = Task(
        observe=lambda ctx: {"status": "same"}, verify=lambda ctx, state: len(ctx.results) == 2
    )

    @workflow.tool(
        "Read each required object",
        parameters={
            "target": Parameter(
                "Next unread object",
                lambda ctx, state: [Option(str(len(ctx.results)), "Next object", len(ctx.results))],
            )
        },
        result_context=lambda result: result,
    )
    def read(target):
        return {"exists": True}

    result = loop.run(workflow, goal="Check two objects")
    assert result["status"] == "done"
    assert result["steps"] == 2


def test_unadmitted_raw_result_cannot_advance_unchanged_state(loop):
    workflow = Task(observe=lambda ctx: {"status": "same"}, verify=lambda ctx, state: False)

    @workflow.tool("Read private raw result")
    def read():
        return {"private": "not admitted"}

    result = loop.run(workflow, goal="Read")
    assert result["status"] == "blocked"
    assert result["steps"] == 1
    assert "private" not in json.dumps(result)


def test_known_effect_is_not_repeated_when_only_evidence_advanced(loop):
    calls = []
    workflow = Task(
        observe=lambda ctx: {"remote_state": "same"},
        verify=lambda ctx, state: False,
        authorize=lambda ctx, action: True,
    )

    @workflow.tool(
        "Submit one bounded synthetic action",
        irreversible=True,
        result_context=lambda result: result,
    )
    def submit():
        calls.append(1)
        return {"accepted": True}

    result = loop.run(workflow, goal="Submit then verify")
    assert result["status"] == "blocked"
    assert result["reason"] == "repeated_action_state"
    assert len(calls) == 1
