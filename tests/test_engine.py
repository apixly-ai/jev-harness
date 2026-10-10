import json

import pytest

from apixly_jev_harness import Action, Engine, Workflow


class Counter(Workflow):
    def __init__(self, *, irreversible=False, authorized=False):
        self.value = 0
        self.calls = []
        self.irreversible = irreversible
        self.authorized = authorized

    def observe(self, ctx):
        return {"value": self.value}

    def candidates(self, ctx, state):
        return [
            Action(
                "increment",
                "Increase counter by one",
                {"amount": 1},
                irreversible=self.irreversible,
            )
        ]

    def execute(self, ctx, action):
        self.calls.append(action)
        self.value += action.params["amount"]
        return {"value": self.value}

    def verify(self, ctx, state):
        return state["value"] >= ctx.inputs.get("target", 2)

    def authorize(self, ctx, action):
        return self.authorized


def select_first(parts, task, workers, spec):
    return {
        p["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE", "answers": {}}
        for i, p in enumerate(parts)
    }, {
        "ok": True,
        "usage_complete": True,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "requests": 1,
    }


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", select_first)
    return Engine()


def test_observe_select_execute_verify_with_private_journal(engine, tmp_path):
    workflow = Counter()
    archive = tmp_path / "run.jsonl"
    result = engine.run(workflow, goal="Reach two", inputs={"target": 2}, archive=archive)
    assert result["status"] == "done"
    assert result["steps"] == 2
    assert len(workflow.calls) == 2
    assert result["telemetry"]["usage"]["input_tokens"] == 20
    assert result["telemetry"]["usage_complete"]
    events = [json.loads(line) for line in archive.read_text().splitlines()]
    assert events[-1]["event"] == "terminal"
    assert any(event["event"] == "executed" for event in events)
    assert "amount" not in json.dumps(result)


def test_already_complete_needs_no_model_call(engine):
    workflow = Counter()
    result = engine.run(workflow, goal="Reach zero", inputs={"target": 0})
    assert result["status"] == "done"
    assert result["telemetry"]["requests"] == 0


def test_irreversible_action_requires_program_authorization(engine):
    workflow = Counter(irreversible=True)
    result = engine.run(workflow, goal="Increment")
    assert result["status"] == "needs_confirmation"
    assert workflow.calls == []
    assert (
        engine.run(
            Counter(irreversible=True, authorized=True), goal="Increment", inputs={"target": 1}
        )["status"]
        == "done"
    )


def test_freshness_rechecked_before_execution(engine):
    class Drifting(Counter):
        def observe(self, ctx):
            self.value += 1
            return super().observe(ctx)

    workflow = Drifting()
    result = engine.run(workflow, goal="Reach ten", inputs={"target": 10})
    assert result["status"] == "stale"
    assert workflow.calls == []


def test_partial_decision_never_executes(engine, monkeypatch):
    def partial(parts, *args):
        return {p["id"]: {"status": "UNAVAILABLE", "decision": "REVIEW"} for p in parts}, {
            "ok": False,
            "usage_complete": False,
            "requests": 1,
        }

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", partial)
    workflow = Counter()
    result = engine.run(workflow, goal="Increment")
    assert result["status"] == "needs_review"
    assert result["telemetry"]["usage_complete"] is False
    assert result["telemetry"]["usage"] is None
    assert workflow.calls == []


def test_execution_failure_is_uncertain_and_never_retried(engine):
    class Ambiguous(Counter):
        def execute(self, ctx, action):
            super().execute(ctx, action)
            raise TimeoutError("secret provider message")

    workflow = Ambiguous()
    result = engine.run(workflow, goal="Increment")
    assert result["status"] == "execution_uncertain"
    assert len(workflow.calls) == 1
    assert "secret" not in json.dumps(result)


def test_stall_is_not_retried(engine):
    class Stalled(Counter):
        def execute(self, ctx, action):
            self.calls.append(action)

    workflow = Stalled()
    assert engine.run(workflow, goal="Increment")["status"] == "blocked"
    assert len(workflow.calls) == 1


def test_step_budget(engine):
    workflow = Counter()
    result = engine.run(workflow, goal="Reach ten", inputs={"target": 10}, max_steps=2)
    assert result["status"] == "max_steps"
    assert len(workflow.calls) == 2


def test_missing_context_prevents_collection(engine):
    workflow = Counter()
    result = engine.run(workflow, goal="Increment", required_context=["project"])
    assert result["status"] == "needs_context"
    assert result["missing_context"] == ["project"]
    assert workflow.calls == []


def test_duplicate_action_ids_and_non_boolean_verifier_fail_closed(engine):
    class Duplicates(Counter):
        def candidates(self, ctx, state):
            return super().candidates(ctx, state) * 2

    workflow = Duplicates()
    assert engine.run(workflow, goal="Increment")["status"] == "failed"
    assert workflow.calls == []

    class BadVerifier(Counter):
        def verify(self, ctx, state):
            return "yes"

    assert engine.run(BadVerifier(), goal="Increment")["status"] == "failed"


def test_parameters_are_not_sent_to_model(engine, monkeypatch):
    def inspect(parts, task, workers, spec):
        assert "secret-token" not in json.dumps([parts, spec])
        return select_first(parts, task, workers, spec)

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", inspect)

    class Private(Counter):
        def candidates(self, ctx, state):
            return [Action("increment", "Increase counter", {"amount": 1, "key": "secret-token"})]

    assert engine.run(Private(), goal="Increment", inputs={"target": 1})["status"] == "done"


def test_archive_never_overwritten(engine, tmp_path):
    archive = tmp_path / "existing.jsonl"
    archive.write_text("original")
    with pytest.raises(FileExistsError):
        engine.run(Counter(), goal="Increment", archive=archive)
    assert archive.read_text() == "original"


def test_no_candidates_and_no_match(engine, monkeypatch):
    class Empty(Counter):
        def candidates(self, ctx, state):
            return []

    assert engine.run(Empty(), goal="Increment")["reason"] == "no_candidates"

    def none(parts, *args):
        judgments, telemetry = select_first(parts, *args)
        for entry in judgments.values():
            entry["decision"] = "EXCLUDE"
        return judgments, telemetry

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", none)
    assert engine.run(Counter(), goal="Increment")["reason"] == "no_qualifying_action"


def test_deadline_prevents_effect_after_slow_decision(engine, monkeypatch):
    import time

    def slow(*args):
        time.sleep(0.01)
        return select_first(*args)

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", slow)
    workflow = Counter()
    assert (
        engine.run(workflow, goal="Increment", timeout_seconds=0.005)["status"] == "budget_exceeded"
    )
    assert workflow.calls == []


def test_transport_exception_keeps_unknown_usage(engine, monkeypatch):
    def unavailable(*args):
        raise TimeoutError("private debug data")

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", unavailable)
    result = engine.run(Counter(), goal="Increment")
    assert result["status"] == "failed"
    assert result["telemetry"]["usage"] is None
    assert not result["telemetry"]["usage_complete"]


@pytest.mark.parametrize(
    "kwargs",
    [{"max_steps": 0}, {"timeout_seconds": float("nan")}, {"inputs": [1]}, {"context": [1]}],
)
def test_invalid_configuration(engine, kwargs):
    with pytest.raises(ValueError):
        engine.run(Counter(), goal="Increment", **kwargs)


def test_decide_missing_context_needs_no_inference(engine):
    result = engine.decide([], goal="Select", analysis_spec={"required_context": ["project"]})
    assert result["status"] == "NEEDS_CONTEXT"


def test_task_cli_template_and_execution(engine, tmp_path, capsys):
    from apixly_jev_harness.task_cli import main

    script = tmp_path / "task.py"
    assert main(["init-task", str(script)]) == 0
    assert json.loads(capsys.readouterr().out)["model_calls"] == 0
    assert main(["run", str(script), "--goal", "Reach two", "--inputs", '{"target":2}']) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "done"
    assert main(["init-task", str(script)]) == 2
    assert json.loads(capsys.readouterr().out)["error_type"] == "FileExistsError"
    assert main(["run", str(script), "--goal", "Reach two", "--inputs", "[]"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_default_authorization_and_action_validation():
    assert Workflow().authorize(None, None) is False
    for args in [("", "description"), ("id", ""), ("id", "description", [])]:
        with pytest.raises(ValueError):
            Action(*args)


def test_native_uncertainty_policy_blocks_low_margin(tmp_path, monkeypatch):
    def runner(items, **kwargs):
        return {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 5, "output_tokens": 1},
            "results": [
                {
                    "id": items[0]["id"],
                    "ok": True,
                    "answers": {
                        "target": {
                            "type": "choice",
                            "choice": "c0",
                            "probabilities": {"c0": 0.51, "REVIEW": 0.49},
                        }
                    },
                }
            ],
        }

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", runner)
    workflow = Counter()
    result = Engine().run(workflow, goal="Increment", archive=tmp_path / "uncertain.jsonl")
    assert result["status"] == "needs_review"
    assert workflow.calls == []


@pytest.mark.parametrize(
    "control,status",
    [
        ("__loop_done", "needs_review"),
        ("__loop_blocked", "blocked"),
        ("__loop_needs_context", "needs_context"),
    ],
)
def test_model_exit_controls_cannot_claim_unverified_completion(monkeypatch, control, status):
    def choose(parts, *args):
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if p["id"] == control else "EXCLUDE"}
            for p in parts
        }, {"ok": True, "usage_complete": True, "usage": {"input_tokens": 0, "output_tokens": 0}}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    workflow = Counter()
    result = Engine().run(workflow, goal="Increment")
    assert result["status"] == status
    assert workflow.calls == []


def test_control_stop_after_effect_is_uncertain(engine):
    from apixly_jev_harness.engine import DecisionStop

    class EffectThenStop(Counter):
        def execute(self, ctx, action):
            super().execute(ctx, action)
            raise DecisionStop("needs_context", "stop_after_effect")

    workflow = EffectThenStop()
    result = engine.run(workflow, goal="Increment")
    assert result["status"] == "execution_uncertain"
    assert len(workflow.calls) == 1
