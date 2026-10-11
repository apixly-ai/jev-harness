import json

import pytest

from apixly_jev_harness import Action, AgentLoop, Task, Workflow


def clock_and_no_inference(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr("apixly_jev_harness.engine.time.monotonic", lambda: clock["now"])

    def forbidden(*args, **kwargs):
        pytest.fail("synthetic fixture must not dispatch native inference")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    return clock


@pytest.mark.parametrize("now", [1.0, 2.0])
@pytest.mark.parametrize("mode", ["empty", "raises", "nonempty"])
def test_expired_false_verification_does_not_start_parameter_collection(
    now, mode, monkeypatch, tmp_path
):
    clock = clock_and_no_inference(monkeypatch)
    providers, effects = [], []

    def verify(ctx, seen):
        clock["now"] = now
        return False

    def choices(ctx, seen):
        providers.append(1)
        if mode == "raises":
            raise RuntimeError("synthetic-private-candidate-error")
        return [] if mode == "empty" else [1]

    task = Task(observe=lambda ctx: {}, verify=verify)

    @task.tool("Read a value", parameters={"value": choices})
    def read(value):
        effects.append(value)

    result = AgentLoop().run(
        task, goal="Read value", timeout_seconds=1, archive=tmp_path / "run.jsonl"
    )
    assert providers == []
    assert effects == []
    assert result["status"] == "budget_exceeded" and result["steps"] == 0
    assert result["telemetry"]["requests"] == 0
    assert result["telemetry"]["usage_complete"] is True
    assert "synthetic-private-candidate-error" not in json.dumps(result)


def test_expired_false_verification_does_not_iterate_workflow_candidates(monkeypatch, tmp_path):
    clock = clock_and_no_inference(monkeypatch)
    collected = []

    class Collect(Workflow):
        def observe(self, ctx):
            return {}

        def verify(self, ctx, seen):
            clock["now"] = 2.0
            return False

        def candidates(self, ctx, seen):
            collected.append(1)
            yield Action("read", "Read synthetic evidence")

        def execute(self, ctx, action):
            pytest.fail("must not execute")

    result = AgentLoop().run(
        Collect(), goal="Read evidence", timeout_seconds=1, archive=tmp_path / "run.jsonl"
    )
    assert collected == [] and result["status"] == "budget_exceeded"


@pytest.mark.parametrize("unknown", [False, True])
@pytest.mark.parametrize("max_steps", [1, 2])
def test_expiry_after_prior_effect_keeps_usage_and_step_precedence(
    unknown, max_steps, monkeypatch, tmp_path
):
    clock = clock_and_no_inference(monkeypatch)
    state, providers, effects = {"progress": 0}, [], []

    def verify(ctx, seen):
        if seen["progress"] == 1:
            clock["now"] = 2.0
        return False

    def choices(ctx, seen):
        providers.append(seen["progress"])
        return [1]

    task = Task(observe=lambda ctx: dict(state), verify=verify)

    @task.tool("Collect synthetic progress", parameters={"value": choices})
    def collect(value):
        effects.append(value)
        state["progress"] += 1

    def choose(parts, *args):
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {
            "ok": True,
            "requests": 1,
            "usage_complete": not unknown,
            "usage": None if unknown else {"input_tokens": 7, "output_tokens": 2},
        }

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(
        task,
        goal="Collect progress",
        timeout_seconds=1,
        max_steps=max_steps,
        archive=tmp_path / "run.jsonl",
    )
    assert providers == [0, 0] and effects == [1]
    assert result["status"] == ("max_steps" if max_steps == 1 else "budget_exceeded")
    assert result["steps"] == result["telemetry"]["requests"] == 1
    assert result["telemetry"]["usage_complete"] is not unknown
    assert (result["telemetry"]["usage"] is None) is unknown


def test_late_verified_success_still_finishes_done(monkeypatch, tmp_path):
    clock = clock_and_no_inference(monkeypatch)

    def verify(ctx, seen):
        clock["now"] = 2.0
        return True

    task = Task(observe=lambda ctx: {}, verify=verify)
    result = AgentLoop().run(
        task, goal="Observe completion", timeout_seconds=1, archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "done" and result["telemetry"]["requests"] == 0


def test_machine_contract_states_soft_candidate_budget_boundary():
    from apixly_jev_harness.task_cli import SPEC

    contract = SPEC["wall_budget"]
    assert contract["before_candidate_collection"] == "rechecked_after_false_verification"
    assert contract["late_verified_success"] == "done"
    assert contract["post_verification_step_limit_precedence"] is True
    assert contract["callbacks_forcibly_interrupted"] is False
