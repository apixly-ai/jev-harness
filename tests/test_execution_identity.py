import json

import pytest

from apixly_jev_harness import Action, AgentLoop, Workflow
from apixly_jev_harness.engine import DecisionStop
from apixly_jev_harness.task_cli import SPEC, main


def test_machine_contract_explains_current_action_reconciliation_limits():
    contract = SPEC["execution_reconciliation"]
    assert contract["action_id_scope"] == "current_pending_bound_action"
    assert contract["decision_stop_during_execution"] == "execution_uncertain_with_action_id"
    assert contract["infer_action_id_from_history"] is False
    assert contract["action_id_proves_effect_success"] is False
    assert contract["action_id_is_idempotency_key"] is False
    assert contract["automatic_retry"] is False


class StopWorkflow(Workflow):
    def __init__(self, phase):
        self.phase = phase
        self.effects = []

    def observe(self, ctx):
        if len(ctx.results) == 2 and self.phase == "observe":
            raise DecisionStop("needs_context", "synthetic_post_effect_stop")
        progress = min(len(ctx.results), 1) if self.phase == "verify" else len(ctx.results)
        return {"progress": progress}

    def verify(self, ctx, state):
        if len(ctx.results) == 2 and self.phase in ("verify", "next_cycle"):
            raise DecisionStop("blocked", "synthetic_post_effect_stop")
        return len(ctx.results) == 2

    def candidates(self, ctx, state):
        if self.phase == "candidates":
            raise DecisionStop("needs_context", "synthetic_pre_effect_stop")
        return [Action("first" if not ctx.results else "second", "Synthetic registered action")]

    def execute(self, ctx, action):
        self.effects.append(action.id)
        if action.id == "second" and self.phase == "execute":
            raise DecisionStop("needs_review", "synthetic_post_effect_stop")
        if action.id == "second" and self.phase == "ordinary_error":
            raise TimeoutError("PRIVATE_SYNTHETIC_ERROR")
        return {"accepted": True}

    def result_context(self, ctx, action, result):
        if action.id == "second" and self.phase == "result_context":
            raise DecisionStop("failed", "synthetic_post_effect_stop")
        return {"accepted": True}


def scripted_loop(monkeypatch, unknown_prior=False):
    calls = []

    def choose(parts, *args):
        calls.append(1)
        unknown = unknown_prior and len(calls) == 1
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {
            "ok": True,
            "requests": 1,
            "usage_complete": not unknown,
            "usage": None if unknown else {"input_tokens": 11, "output_tokens": 2},
        }

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)

    def forbidden(*args, **kwargs):
        raise AssertionError("No real inference in this fixture")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    return AgentLoop(), calls


@pytest.mark.parametrize("phase", ["execute", "result_context", "observe", "verify"])
@pytest.mark.parametrize("unknown_prior", [False, True])
def test_post_effect_stop_identifies_current_action_and_keeps_prior_usage(
    monkeypatch, tmp_path, phase, unknown_prior
):
    loop, calls = scripted_loop(monkeypatch, unknown_prior)
    workflow = StopWorkflow(phase)
    archive = tmp_path / "run.jsonl"
    result = loop.run(workflow, goal="Run two synthetic actions", archive=archive)
    assert result["status"] == "execution_uncertain" and result["complete"] is False
    assert result["reason"] == "synthetic_post_effect_stop"
    assert result["action_id"] == "second"
    assert result["steps"] == (1 if phase == "execute" else 2)
    assert workflow.effects == ["first", "second"] and len(calls) == 2
    assert result["telemetry"]["requests"] == 2
    assert result["telemetry"]["usage_complete"] is (not unknown_prior)
    assert result["telemetry"]["usage"] == (
        None if unknown_prior else {"input_tokens": 22, "output_tokens": 4}
    )
    events = [json.loads(line) for line in archive.read_text().splitlines()]
    assert [event["action_id"] for event in events if event["event"] == "intent"] == [
        "first",
        "second",
    ]
    assert events[-1]["result"]["action_id"] == "second"


@pytest.mark.parametrize("phase", ["candidates", "next_cycle", "ordinary_error", "done"])
def test_action_identity_does_not_attach_to_stops_outside_current_execution(
    monkeypatch, tmp_path, phase
):
    loop, calls = scripted_loop(monkeypatch)
    workflow = StopWorkflow(phase)
    result = loop.run(workflow, goal="Run two synthetic actions", archive=tmp_path / "run.jsonl")
    if phase == "ordinary_error":
        assert result["status"] == "execution_uncertain" and result["action_id"] == "second"
        assert "PRIVATE_SYNTHETIC_ERROR" not in json.dumps(result)
    else:
        assert "action_id" not in result
        assert (
            result["status"]
            == {
                "candidates": "needs_context",
                "next_cycle": "blocked",
                "done": "done",
            }[phase]
        )
    assert len(calls) == len(workflow.effects) == (0 if phase == "candidates" else 2)


def test_cli_exit_two_preserves_current_action_for_reconciliation(monkeypatch, tmp_path, capsys):
    scripted_loop(monkeypatch, unknown_prior=True)
    script = tmp_path / "task.py"
    marker = tmp_path / "synthetic-effect.txt"
    script.write_text(
        "from pathlib import Path\n"
        "from apixly_jev_harness import Task\n"
        "from apixly_jev_harness.engine import DecisionStop\n"
        "workflow=Task(observe=lambda ctx: {}, verify=lambda ctx,state: False)\n"
        "@workflow.tool('Bounded synthetic effect')\n"
        "def reconcile_target():\n"
        f"    Path({str(marker)!r}).write_text('one effect')\n"
        "    print('PRIVATE_SYNTHETIC_OUTPUT')\n"
        "    raise DecisionStop('needs_context','synthetic_stop')\n",
        newline="\n",
    )
    assert main(["run", str(script), "--goal", "Synthetic effect"]) == 2
    captured = capsys.readouterr()
    packet = json.loads(captured.out)
    assert packet["status"] == "execution_uncertain"
    assert packet["action_id"] == "reconcile_target"
    assert packet["telemetry"]["usage"] is None
    assert packet["telemetry"]["requests"] == 1
    assert marker.read_text() == "one effect"
    assert captured.err == "" and "PRIVATE_SYNTHETIC_OUTPUT" not in captured.out
