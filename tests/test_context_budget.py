import json

import pytest

from apixly_jev_harness import Action, AgentLoop, Workflow
from apixly_jev_harness.engine import DecisionStop, _json

LIMIT = 15000
BUDGETS = {"remaining_steps": 20, "remaining_seconds": 120.0}


def shared(padding, stage=None, **extra):
    value = {"PRIVATE_PADDING": padding, "budgets": BUDGETS, **extra}
    if stage is not None:
        value["decision_stage"] = stage
    return value


def padding_to_size(target, character="x", stage=None):
    empty = len(json.dumps(shared("", stage), ensure_ascii=False))
    return character * (target - empty)


class Policy:
    def __init__(self, padding):
        self.padding = padding

    def build(self, ctx, state):
        return {"PRIVATE_PADDING": self.padding}


class Inspect(Workflow):
    def __init__(self):
        self.effects = 0

    def observe(self, ctx):
        return {"done": bool(self.effects)}

    def verify(self, ctx, state):
        return state["done"]

    def candidates(self, ctx, state):
        return [Action("inspect", "Inspect one synthetic state")]

    def execute(self, ctx, action):
        self.effects += 1


@pytest.fixture
def decisions(monkeypatch):
    captured = []

    def forbidden(*args, **kwargs):
        pytest.fail("Budget fixtures must not invoke native inference")

    def evaluate(parts, goal, workers, spec):
        captured.append(spec["context"])
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "requests": 1,
        }

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", evaluate)
    monkeypatch.setattr("apixly_jev_harness.engine.time.monotonic", lambda: 1000.0)
    return captured


@pytest.mark.parametrize(
    "projection_size, expected_stage",
    [(LIMIT + 1, "context_projection"), (LIMIT, "tool_selection")],
)
def test_overflow_reports_actual_limit_stage_and_size_before_inference(
    decisions, tmp_path, projection_size, expected_stage
):
    padding = padding_to_size(projection_size)
    workflow = Inspect()
    result = AgentLoop().run(
        workflow, goal="Inspect", context_policy=Policy(padding), archive=tmp_path / "run.jsonl"
    )
    observed = len(
        json.dumps(
            shared(padding, None if expected_stage == "context_projection" else "tool_selection"),
            ensure_ascii=False,
        )
    )
    assert result["status"] == "needs_review" and result["reason"] == "context_budget_exceeded"
    assert result["context_budget"] == {
        "scope": "loop_shared_context",
        "stage": expected_stage,
        "unit": "json_characters",
        "limit": LIMIT,
        "observed": observed,
    }
    assert decisions == [] and workflow.effects == 0
    assert "PRIVATE_PADDING" not in json.dumps(result)


@pytest.mark.parametrize("character", ["x", "中", "🙂"])
def test_exact_character_limit_admits_even_when_utf8_bytes_are_larger(
    decisions, tmp_path, character
):
    padding = padding_to_size(LIMIT, character, "tool_selection")
    result = AgentLoop().run(
        Inspect(), goal="Inspect", context_policy=Policy(padding), archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "done" and len(decisions) == 1
    assert "context_budget" not in result
    call = result["telemetry"]["calls"][0]
    assert call["context_characters"] == LIMIT
    assert call["context_character_limit"] == LIMIT
    assert call["context_bytes"] == len(_json(decisions[0]).encode())
    if character != "x":
        assert call["context_bytes"] > LIMIT


class ParameterChoice(Inspect):
    def bind(self, ctx, state, action, choose):
        self.choose = choose
        choose(
            [{"id": "a", "text": "First"}, {"id": "b", "text": "Second"}],
            "Select the observed destination",
            {"selected_tool": action.id, "parameter": "target", "extra": "x" * LIMIT},
        )
        return action


def test_parameter_context_overflow_keeps_prior_call_usage_and_blocks_effect(decisions, tmp_path):
    workflow = ParameterChoice()
    result = AgentLoop().run(
        workflow, goal="Inspect", context_policy=Policy("small"), archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "needs_review" and workflow.effects == 0
    assert result["context_budget"]["stage"] == "parameter_selection"
    assert result["context_budget"]["observed"] > LIMIT
    assert len(decisions) == result["telemetry"]["requests"] == 1
    assert result["telemetry"]["usage"] == {"input_tokens": 10, "output_tokens": 2}


def test_parameter_budget_does_not_turn_unknown_prior_usage_into_zero(
    decisions, tmp_path, monkeypatch
):
    from apixly_jev_harness.engine import analysis

    original = analysis.evaluate

    def unknown_usage(*args):
        judgments, telemetry = original(*args)
        telemetry.update(usage_complete=False, usage=None)
        return judgments, telemetry

    monkeypatch.setattr(analysis, "evaluate", unknown_usage)
    result = AgentLoop().run(
        ParameterChoice(),
        goal="Inspect",
        context_policy=Policy("small"),
        archive=tmp_path / "run.jsonl",
    )
    assert result["status"] == "needs_review"
    assert result["context_budget"]["stage"] == "parameter_selection"
    assert result["telemetry"]["requests"] == 1
    assert result["telemetry"]["usage_complete"] is False
    assert result["telemetry"]["usage"] is None


def test_large_candidate_text_and_question_are_outside_this_shared_context_cap(decisions, tmp_path):
    class LongLabels(Inspect):
        def candidates(self, ctx, state):
            return [Action("inspect", "x" * (LIMIT + 1))]

    result = AgentLoop().run(
        LongLabels(),
        goal="x" * (LIMIT + 1),
        context_policy=Policy("small"),
        archive=tmp_path / "run.jsonl",
    )
    assert result["status"] == "done" and len(decisions) == 1
    assert result["telemetry"]["calls"][0]["context_characters"] < LIMIT


@pytest.mark.parametrize("fails", [False, True])
def test_trusted_fallback_does_not_leave_rejected_budget_metadata(decisions, tmp_path, fails):
    class Fallback(ParameterChoice):
        def bind(self, ctx, state, action, choose):
            try:
                return super().bind(ctx, state, action, choose)
            except DecisionStop:
                return action

        def execute(self, ctx, action):
            super().execute(ctx, action)
            if fails:
                raise TimeoutError("PRIVATE_EFFECT")

    result = AgentLoop().run(
        Fallback(), goal="Inspect", context_policy=Policy("small"), archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == ("execution_uncertain" if fails else "done")
    assert "context_budget" not in result


def test_budget_rejection_after_effect_stays_uncertain_and_is_not_retried(decisions, tmp_path):
    class Interrupted(Inspect):
        def bind(self, ctx, state, action, choose):
            self.choose = choose
            return action

        def execute(self, ctx, action):
            super().execute(ctx, action)
            self.choose(
                [{"id": "a", "text": "First"}],
                "Deferred check from a trusted tool",
                {"parameter": "target", "extra": "x" * LIMIT},
            )

    workflow = Interrupted()
    result = AgentLoop().run(
        workflow, goal="Inspect", context_policy=Policy("small"), archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "execution_uncertain" and workflow.effects == 1
    assert result["context_budget"]["stage"] == "parameter_selection"
    assert len(decisions) == 1


def test_next_projection_budget_failure_keeps_completed_steps_and_spent_calls(decisions, tmp_path):
    class Continue(Inspect):
        def verify(self, ctx, state):
            return False

    class GrowingPolicy:
        def build(self, ctx, state):
            return {"PRIVATE_PADDING": padding_to_size(LIMIT + 1) if ctx.step else "small"}

    workflow = Continue()
    result = AgentLoop().run(
        workflow, goal="Inspect", context_policy=GrowingPolicy(), archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "needs_review" and result["steps"] == workflow.effects == 1
    assert result["context_budget"]["stage"] == "context_projection"
    assert len(decisions) == result["telemetry"]["requests"] == 1
    assert result["telemetry"]["usage"] == {"input_tokens": 10, "output_tokens": 2}
