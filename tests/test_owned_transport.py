import json

import httpx
import pytest
from jev_context.provider import Client

from apixly_jev_harness import AgentLoop, Parameter, Task
from apixly_jev_harness.task_cli import SPEC, main


def response(request):
    body = json.loads(request.content)
    options = list(body["questions"]["target"]["criteria"])
    return httpx.Response(
        200,
        json={
            "model": "jev-synthetic-resolved",
            "usage": {"input_tokens": 5, "output_tokens": 1},
            "answers": {
                "target": {
                    "type": "choice",
                    "choice": options[0],
                    "confidence": 1,
                    "probabilities": {key: float(key == options[0]) for key in options},
                }
            },
        },
    )


@pytest.mark.parametrize(
    "case,logical,attempts,status,known",
    [
        ("success", 1, 1, "done", True),
        ("parameter_retry", 2, 3, "done", False),
        ("exhausted", 1, 3, "needs_review", False),
        ("credential", 1, 0, "needs_review", False),
        ("http413", 1, 1, "needs_review", False),
        ("invalid_response", 1, 1, "needs_review", False),
        ("planning", 0, 0, "needs_review", True),
        ("already_done", 0, 0, "done", True),
        ("preused_counters", 1, 1, "done", True),
    ],
)
def test_owned_sdk_counter_distinguishes_logical_requests_and_matches_journal(
    monkeypatch, tmp_path, case, logical, attempts, status, known
):
    observed = []

    def transport(request):
        observed.append(1)
        if case == "exhausted" or (case == "parameter_retry" and len(observed) == 1):
            return httpx.Response(503, headers={"retry-after": "0"})
        if case == "http413":
            return httpx.Response(413, text="PRIVATE_RESPONSE")
        if case == "invalid_response":
            return httpx.Response(200, text="PRIVATE_RESPONSE")
        return response(request)

    client = Client(
        api_key="synthetic invalid" if case == "credential" else "synthetic-key",
        transport=httpx.MockTransport(transport),
        sleep=lambda _: None,
    )
    if case == "preused_counters":
        client.stats.update(requests=7, clients_created=5, client_reuses=11)
    monkeypatch.setattr("apixly_jev_harness.backend.Client", lambda **kwargs: client)
    state = {"done": case == "already_done"}
    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])

    @task.tool(
        "x" * 60000 if case == "planning" else "Synthetic effect",
        parameters={"amount": Parameter("Observed amount", [1, 2])}
        if case == "parameter_retry"
        else {},
    )
    def effect(amount=1):
        state["done"] = True

    archive = tmp_path / "run.jsonl"
    result = AgentLoop().run(task, goal="Synthetic goal", archive=archive)
    assert result["status"] == status
    assert result["telemetry"]["requests"] == logical
    assert len(observed) == attempts
    assert result["telemetry"]["usage_complete"] is known
    assert (result["telemetry"]["usage"] is None) is (not known)
    assert result["telemetry"]["owned_transport"] == {
        "scope": "run_owned_provider_client",
        "snapshot": "terminal_finish",
        "request_attempts": attempts,
        "clients_created": int(attempts > 0),
        "client_reuses": max(0, attempts - 1),
        "counters_complete": True,
    }
    terminal = json.loads(archive.read_text().splitlines()[-1])["result"]
    assert terminal["telemetry"]["owned_transport"] == result["telemetry"]["owned_transport"]
    assert client.closed and "PRIVATE_RESPONSE" not in json.dumps(result)


@pytest.mark.parametrize("bad", [None, True, -1, "PRIVATE_COUNTER", 0])
def test_post_effect_counter_corruption_is_unknown_not_zero_or_task_failure(
    monkeypatch, tmp_path, bad
):
    client = Client(api_key="synthetic-key", transport=httpx.MockTransport(response))
    monkeypatch.setattr("apixly_jev_harness.backend.Client", lambda **kwargs: client)
    done = []
    task = Task(observe=lambda ctx: {"done": bool(done)}, verify=lambda ctx, state: state["done"])

    @task.tool("Synthetic effect")
    def effect():
        done.append(1)
        client.stats["requests"] = bad
        client.stats["PRIVATE_EXTRA"] = "PRIVATE_COUNTER"

    result = AgentLoop().run(task, goal="Synthetic goal", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done" and done == [1]
    assert result["telemetry"]["usage"] == {"input_tokens": 5, "output_tokens": 1}
    owned = result["telemetry"]["owned_transport"]
    assert owned["request_attempts"] is None and owned["counters_complete"] is False
    assert owned["clients_created"] == 1 and owned["client_reuses"] == 0
    assert "PRIVATE_" not in json.dumps(result)


def test_no_active_owned_session_omits_metadata_instead_of_claiming_zero(tmp_path):
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: True)
    result = AgentLoop.run.__wrapped__(
        AgentLoop(), task, goal="Done", archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "done" and "owned_transport" not in result["telemetry"]


@pytest.mark.parametrize("replacement", [None, {}, "unreadable"])
def test_unavailable_stats_do_not_change_success_or_reveal_instrumentation_errors(
    monkeypatch, tmp_path, replacement
):
    class Unreadable(dict):
        def get(self, key, default=None):
            raise RuntimeError("PRIVATE_COUNTER_EXCEPTION")

    client = Client(api_key="synthetic-key", transport=httpx.MockTransport(response))
    monkeypatch.setattr("apixly_jev_harness.backend.Client", lambda **kwargs: client)
    done = []
    task = Task(observe=lambda ctx: {"done": bool(done)}, verify=lambda ctx, state: state["done"])

    @task.tool("Synthetic effect")
    def effect():
        done.append(1)
        client.stats = Unreadable() if replacement == "unreadable" else replacement

    result = AgentLoop().run(task, goal="Synthetic goal", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done" and done == [1]
    owned = result["telemetry"]["owned_transport"]
    assert owned["counters_complete"] is False
    assert all(
        owned[key] is None for key in ("request_attempts", "clients_created", "client_reuses")
    )
    assert result["telemetry"]["usage"] == {"input_tokens": 5, "output_tokens": 1}
    assert "PRIVATE_" not in json.dumps(result)


def test_spec_defines_counter_scope_and_preserves_existing_request_meaning():
    contract = SPEC["transport_counters"]
    assert contract["metadata_field"] == "telemetry.owned_transport"
    assert contract["scope"] == "run_owned_provider_client"
    assert contract["snapshot"] == "terminal_finish"
    assert contract["server_received_or_billable_proof"] is False
    assert contract["includes_other_tool_network"] is False
    assert contract["missing_or_invalid_counter"] == "null; never inferred zero"


def test_cli_local_credential_rejection_reports_zero_owned_attempts_but_unknown_usage(
    monkeypatch, tmp_path, capsys
):
    def forbidden(request):
        raise AssertionError("Rejected synthetic credential must not reach the transport")

    client = Client(api_key="synthetic invalid", transport=httpx.MockTransport(forbidden))
    monkeypatch.setattr("apixly_jev_harness.backend.Client", lambda **kwargs: client)
    script = tmp_path / "task.py"
    script.write_text(
        "from apixly_jev_harness import Task\n"
        "workflow=Task(observe=lambda ctx: {}, verify=lambda ctx,state: False)\n"
        "@workflow.tool('Synthetic bounded effect')\n"
        "def effect():\n"
        "    raise AssertionError('Must not execute')\n"
    )
    assert main(["run", str(script), "--goal", "Synthetic goal"]) == 2
    captured = capsys.readouterr()
    packet = json.loads(captured.out)
    assert packet["status"] == "needs_review" and packet["steps"] == 0
    assert packet["telemetry"]["requests"] == 1
    assert packet["telemetry"]["owned_transport"]["request_attempts"] == 0
    assert packet["telemetry"]["owned_transport"]["counters_complete"] is True
    assert packet["telemetry"]["usage"] is None and captured.err == ""
