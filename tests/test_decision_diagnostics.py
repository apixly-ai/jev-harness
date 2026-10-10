import json

import httpx
import pytest
from jev_context.provider import Client, ProviderError

from apixly_jev_harness import Action, AgentLoop, Option, Parameter, Task, Workflow


def task_fixture():
    task = Task(observe=lambda ctx: {"ready": False}, verify=lambda ctx, seen: False)

    @task.tool(
        "Inspect an observed object",
        parameters={
            "target": Parameter(
                "Which object needs inspection?",
                [
                    Option("a", "First object", "PRIVATE_ARGUMENT_A"),
                    Option("b", "Second object", "PRIVATE_ARGUMENT_B"),
                ],
            )
        },
    )
    def inspect(target):
        raise AssertionError("Unresolved selection must not execute")

    return task


def mock_client(monkeypatch, transport):
    client = Client(
        api_key="synthetic-test-key", transport=httpx.MockTransport(transport), sleep=lambda _: None
    )
    monkeypatch.setattr("apixly_jev_harness.backend.Client", lambda **kwargs: client)
    return client


@pytest.mark.parametrize("code", ["credentials_missing", "credential_file_permissions"])
def test_safe_provider_failure_survives_typed_batch(monkeypatch, tmp_path, code):
    def unavailable(*args, **kwargs):
        raise ProviderError(code)

    monkeypatch.setattr("apixly_jev_harness.backend.provider_evaluate", unavailable)
    result = AgentLoop().run(task_fixture(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["status"] == "needs_review"
    assert result["diagnostic"] == {
        "stage": "tool_selection",
        "reason_codes": [code],
        "automatic_retry": False,
    }
    assert result["telemetry"]["usage"] is None
    assert result["telemetry"]["calls"][0]["model_resolved"] is None
    assert result["telemetry"]["calls"][0]["stage"] == "tool_selection"


def test_http_code_is_preserved_without_response_body(monkeypatch, tmp_path):
    mock_client(monkeypatch, lambda request: httpx.Response(401, text="PRIVATE_RESPONSE_BODY"))
    result = AgentLoop().run(task_fixture(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["diagnostic"]["reason_codes"] == ["http_401_body_suppressed"]
    assert result["telemetry"]["usage_complete"] is False
    assert "PRIVATE_RESPONSE_BODY" not in json.dumps(result)
    assert "PRIVATE_RESPONSE_BODY" not in (tmp_path / "run.jsonl").read_text()


@pytest.mark.parametrize(
    "failure", [ProviderError("PRIVATE_UNKNOWN_CODE"), RuntimeError("PRIVATE_EXCEPTION_TEXT")]
)
def test_unrecognized_exception_details_are_suppressed(monkeypatch, tmp_path, failure):
    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr("apixly_jev_harness.backend.provider_evaluate", unavailable)
    result = AgentLoop().run(task_fixture(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["diagnostic"]["reason_codes"] == ["provider_unavailable"]
    assert "PRIVATE_" not in json.dumps(result)


@pytest.mark.parametrize("stage", ["tool_selection", "parameter_selection"])
def test_low_probability_diagnostic_locates_selection(monkeypatch, tmp_path, stage):
    calls = []

    def transport(request):
        body = json.loads(request.content)
        calls.append(body)
        options = list(body["questions"]["target"]["criteria"])
        failed = stage == "tool_selection" or len(calls) == 2
        probabilities = {option: 0.0 for option in options}
        probabilities[options[0]] = 0.51 if failed else 1.0
        probabilities[options[1]] = 0.49 if failed else 0.0
        return httpx.Response(
            200,
            json={
                "model": "jev-synthetic-resolved",
                "usage": {"input_tokens": 5, "output_tokens": 1},
                "answers": {
                    "target": {
                        "type": "choice",
                        "choice": options[0],
                        "confidence": 1.0,
                        "probabilities": probabilities,
                    }
                },
            },
        )

    mock_client(monkeypatch, transport)
    result = AgentLoop().run(task_fixture(), goal="Inspect", archive=tmp_path / "run.jsonl")
    expected = {
        "stage": stage,
        "reason_codes": ["below_min_top_probability", "below_min_margin"],
        "automatic_retry": False,
    }
    if stage == "parameter_selection":
        expected.update(tool_id="inspect", parameter="target")
    assert result["diagnostic"] == expected
    assert result["telemetry"]["calls"][-1]["stage"] == stage
    assert "PRIVATE_ARGUMENT" not in json.dumps(result)
    assert result["steps"] == 0


@pytest.mark.parametrize("choice", ["REVIEW", "NONE"])
def test_explicit_review_and_no_match_are_distinct(monkeypatch, tmp_path, choice):
    def transport(request):
        body = json.loads(request.content)
        options = list(body["questions"]["target"]["criteria"])
        return httpx.Response(
            200,
            json={
                "model": "jev-synthetic-resolved",
                "usage": {"input_tokens": 2, "output_tokens": 1},
                "answers": {
                    "target": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": 1.0,
                        "probabilities": {x: float(x == choice) for x in options},
                    }
                },
            },
        )

    mock_client(monkeypatch, transport)
    result = AgentLoop().run(task_fixture(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["status"] == ("needs_review" if choice == "REVIEW" else "blocked")
    assert result["diagnostic"]["reason_codes"] == (
        ["model_review"] if choice == "REVIEW" else ["no_matching_candidate"]
    )
    assert result["diagnostic"]["stage"] == "tool_selection"


@pytest.mark.parametrize("execution_fails", [False, True])
def test_trusted_binding_fallback_does_not_leave_old_failure_diagnostic(
    monkeypatch, tmp_path, execution_fails
):
    decisions = []

    def evaluate(parts, goal, workers, spec):
        decisions.append(spec)
        return {
            part["id"]: {
                "status": "OK",
                "decision": "REVIEW" if len(decisions) == 2 else ("MATCH" if i == 0 else "EXCLUDE"),
            }
            for i, part in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "requests": 1,
        }

    class TrustedFallback(Workflow):
        done = False

        def observe(self, ctx):
            return {"done": self.done}

        def verify(self, ctx, state):
            return state["done"]

        def candidates(self, ctx, state):
            return [Action("inspect", "Inspect the bounded object", {"target": "caller-default"})]

        def bind(self, ctx, state, action, choose):
            packet = choose(
                [{"id": "a", "text": "First optional target"}, {"id": "b", "text": "Second"}],
                "Optional selection; the trusted caller can use its own fixed value",
                {"selected_tool": "inspect", "parameter": "target"},
            )
            assert not packet["complete"]
            return action

        def execute(self, ctx, action):
            self.done = True
            if execution_fails:
                raise TimeoutError("PRIVATE_EFFECT_EXCEPTION")

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", evaluate)
    result = AgentLoop().run(TrustedFallback(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["status"] == ("execution_uncertain" if execution_fails else "done")
    assert "diagnostic" not in result
    assert result["telemetry"]["calls"][1]["stage"] == "parameter_selection"


def test_unknown_optional_reason_shapes_cannot_change_abstention(monkeypatch, tmp_path):
    def evaluate(parts, goal, workers, spec):
        return {part["id"]: {"status": "UNAVAILABLE", "decision": "REVIEW"} for part in parts}, {
            "ok": False,
            "usage_complete": False,
            "usage": None,
            "requests": 1,
            "provider_failure_codes": None,
            "selection_review_reasons": "PRIVATE_UNTRUSTED_REASON",
        }

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", evaluate)
    result = AgentLoop().run(task_fixture(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["status"] == "needs_review"
    assert result["diagnostic"]["reason_codes"] == ["provider_unavailable"]
