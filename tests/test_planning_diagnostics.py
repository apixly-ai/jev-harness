import json

import httpx
import pytest
from jev_context.provider import Client

from apixly_jev_harness import Action, AgentLoop, Engine, Workflow, backend
from apixly_jev_harness.diagnostics import selection_diagnostic


def successful(items, *, unknown=False):
    return {
        "ok": True,
        "usage_complete": not unknown,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "requests": 1,
        "results": [
            {
                "id": items[0]["id"],
                "ok": True,
                "answers": {
                    "target": {"type": "choice", "choice": "c0", "probabilities": {"c0": 1.0}}
                },
            }
        ],
    }


@pytest.fixture
def no_native(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Deferred plan must not enter native inference")

    monkeypatch.setattr(backend, "native_run", forbidden)


def assert_planning(telemetry, reason):
    assert telemetry["planning"] == {
        "scope": "current_selection",
        "phase": "request_planning",
        "inference_dispatched": False,
        "reason_codes": [reason],
    }


@pytest.mark.parametrize("character", ["x", "中"])
def test_actual_request_size_deferral_has_input_reason_without_dispatch(no_native, character):
    packet = Engine().decide(
        [{"id": "a", "text": character * 60000}],
        goal="Inspect",
        analysis_spec={"mode": "choose"},
    )
    assert packet["review_ids"] == ["a"] and not packet["complete"]
    assert_planning(packet["telemetry"], "request_needs_narrowing")
    assert packet["telemetry"]["requests"] == 0
    assert packet["telemetry"]["usage_complete"] is True


def test_missing_record_fields_preserve_actual_planner_status(no_native):
    parts = [{"id": "a", "source_id": "a", "text": "Inspect", "source": {}}]
    judgments, telemetry = backend.evaluate(
        parts, "Inspect", "auto", {"mode": "choose", "required_record_fields": ["source.id"]}
    )
    assert judgments["a"]["status"] == "NEEDS_CONTEXT"
    assert judgments["a"]["decision"] == "REVIEW"
    assert_planning(telemetry, "request_needs_context")


@pytest.mark.parametrize("status", ["PRIVATE_UNKNOWN_STATUS", ["PRIVATE_BAD_TYPE"]])
def test_unknown_planner_status_is_generic_and_never_echoed(no_native, monkeypatch, status):
    monkeypatch.setattr(
        backend.core,
        "plan",
        lambda *args: {"items": [], "deferred": {"a": status}},
    )
    parts = [{"id": "a", "text": "Inspect", "source": {}}]
    judgments, telemetry = backend.evaluate(parts, "Inspect", "auto", {"mode": "choose"})
    assert judgments["a"]["status"] == "UNAVAILABLE"
    assert_planning(telemetry, "request_planning_review")
    assert "PRIVATE" not in json.dumps([judgments, telemetry])


class Inspect(Workflow):
    def __init__(self):
        self.effects = 0

    def observe(self, ctx):
        return {"done": bool(self.effects)}

    def verify(self, ctx, state):
        return state["done"]

    def candidates(self, ctx, state):
        return [Action("inspect", "Inspect")]

    def execute(self, ctx, action):
        self.effects += 1


def test_loop_tool_deferral_has_fixed_stage_and_no_effect(no_native, tmp_path):
    class TooLarge(Inspect):
        def candidates(self, ctx, state):
            return [Action("inspect", "x" * 60000)]

    task = TooLarge()
    packet = AgentLoop().run(task, goal="Inspect", archive=tmp_path / "run.jsonl")
    assert packet["status"] == "needs_review" and task.effects == 0
    assert packet["diagnostic"] == {
        "stage": "tool_selection",
        "reason_codes": ["request_needs_narrowing"],
        "automatic_retry": False,
    }
    assert_planning(packet["telemetry"]["calls"][0], "request_needs_narrowing")


@pytest.mark.parametrize("unknown", [False, True])
def test_parameter_deferral_preserves_prior_call_and_unknown_usage(monkeypatch, tmp_path, unknown):
    calls = []

    def native(items, **kwargs):
        calls.append(1)
        assert len(calls) == 1
        return successful(items, unknown=unknown)

    monkeypatch.setattr(backend, "native_run", native)

    # A normal Task binding requests review on incomplete choice; emulate its gate.
    from apixly_jev_harness.engine import DecisionStop

    class Guarded(Inspect):
        def bind(self, ctx, state, action, choose):
            packet = choose(
                [{"id": "a", "text": "x" * 60000}],
                "Select target",
                {"selected_tool": action.id, "parameter": "target"},
            )
            if not packet["complete"]:
                raise DecisionStop("needs_review", "unresolved_parameter:target")
            return action

    workflow = Guarded()
    packet = AgentLoop().run(workflow, goal="Inspect", archive=tmp_path / "run.jsonl")
    assert packet["status"] == "needs_review" and workflow.effects == 0 and len(calls) == 1
    assert packet["diagnostic"]["stage"] == "parameter_selection"
    assert packet["diagnostic"]["reason_codes"] == ["request_needs_narrowing"]
    assert_planning(packet["telemetry"]["calls"][1], "request_needs_narrowing")
    assert packet["telemetry"]["requests"] == 1
    assert packet["telemetry"]["usage_complete"] is (not unknown)
    assert packet["telemetry"]["usage"] == (
        None if unknown else {"input_tokens": 10, "output_tokens": 2}
    )


def test_generic_analysis_validation_error_is_not_reinterpreted_as_size_or_zero(no_native):
    with pytest.raises(ValueError):
        Engine().decide(
            [{"id": "a", "text": "Inspect"}],
            goal="Inspect",
            context={"padding": "x" * 17000},
            analysis_spec={"mode": "choose"},
        )


def test_dispatched_http_413_stays_provider_failure_with_unknown_usage(monkeypatch, tmp_path):
    attempts = []

    def transport(request):
        attempts.append(1)
        return httpx.Response(413, text="PRIVATE_RESPONSE_BODY")

    client = Client(api_key="synthetic-key", transport=httpx.MockTransport(transport))
    monkeypatch.setattr(backend, "Client", lambda **kwargs: client)
    packet = AgentLoop().run(Inspect(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert attempts == [1]
    assert packet["diagnostic"]["reason_codes"] == ["http_413_body_suppressed"]
    assert packet["telemetry"]["usage_complete"] is False
    assert packet["telemetry"]["usage"] is None
    assert "planning" not in packet["telemetry"]["calls"][0]
    assert "PRIVATE" not in json.dumps(packet)


def test_empty_records_keep_legacy_completion_without_invented_failure(no_native):
    packet = Engine().decide([], goal="Inspect", analysis_spec={"mode": "choose"})
    assert packet["complete"] is True and packet["review_ids"] == packet["selected_ids"] == []
    assert packet["telemetry"]["planning"]["reason_codes"] == []
    assert packet["telemetry"]["planning"]["inference_dispatched"] is False


@pytest.mark.parametrize("fails", [False, True])
def test_trusted_fallback_does_not_leave_planner_diagnostic_on_execution(
    monkeypatch, tmp_path, fails
):
    monkeypatch.setattr(backend, "native_run", lambda items, **kwargs: successful(items))

    class Fallback(Inspect):
        def bind(self, ctx, state, action, choose):
            packet = choose(
                [{"id": "a", "text": "x" * 60000}],
                "Optional target",
                {"selected_tool": action.id, "parameter": "target"},
            )
            assert not packet["complete"]
            return action  # Caller-owned fixed fallback, no model-generated argument.

        def execute(self, ctx, action):
            super().execute(ctx, action)
            if fails:
                raise TimeoutError("PRIVATE_EFFECT")

    workflow = Fallback()
    packet = AgentLoop().run(workflow, goal="Inspect", archive=tmp_path / "run.jsonl")
    assert packet["status"] == ("execution_uncertain" if fails else "done")
    assert workflow.effects == 1 and "diagnostic" not in packet
    assert_planning(packet["telemetry"]["calls"][1], "request_needs_narrowing")


@pytest.mark.parametrize("dispatched", [False, 0, True])
def test_planner_diagnostic_admits_only_fixed_codes_and_strict_false(dispatched):
    packet = {
        "ok": True,
        "complete": False,
        "selected_ids": [],
        "review_ids": ["a"],
        "telemetry": {
            "planning": {
                "scope": "current_selection",
                "phase": "request_planning",
                "inference_dispatched": dispatched,
                "reason_codes": ["PRIVATE_CODE", {"PRIVATE": 1}, "request_needs_narrowing"],
            }
        },
    }
    diagnostic = selection_diagnostic(packet, [{"id": "a"}], {"stage": "tool_selection"})
    assert diagnostic["reason_codes"] == (
        ["request_needs_narrowing"] if dispatched is False else ["unresolved_selection"]
    )
    assert "PRIVATE" not in json.dumps(diagnostic)
