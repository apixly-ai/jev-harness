"""Offline paired run-owned SDK counter snapshots against exact v0.1.11."""

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "95276bd77eef162645b45bfcd8c40c7a06dac212"
MARKER = "SYNTHETIC_PRIVATE_DETAIL"
STAT_KEYS = {
    "request_attempts": "requests",
    "clients_created": "clients_created",
    "client_reuses": "client_reuses",
}
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "success": {"response": "success"},
    "tool_parameter_retry": {"response": "parameter_retry", "parameter": True},
    "three_503_exhausted": {"response": "three_503"},
    "credential_local_reject": {"response": "credential_reject"},
    "mock_http_413": {"response": "http_413"},
    "invalid_response": {"response": "invalid"},
    "planning_narrow": {"response": "success", "oversize_description_repetitions": 60000},
    "already_done": {"response": "success", "initially_done": True},
    "preused_seed_counters": {"response": "success", "seed_calls": 1},
    "post_effect_string_counter": {
        "response": "success",
        "corrupt_key": "requests",
        "corrupt_kind": "string",
    },
    "post_effect_negative_counter": {
        "response": "success",
        "corrupt_key": "requests",
        "corrupt_kind": "negative",
    },
    "post_effect_bool_counter": {
        "response": "success",
        "corrupt_key": "clients_created",
        "corrupt_kind": "bool",
    },
    "post_effect_private_extra": {"response": "success", "corrupt_kind": "private_extra"},
    "post_effect_reset_to_zero": {
        "response": "success",
        "corrupt_key": "requests",
        "corrupt_kind": "reset_zero",
    },
    "no_active_session": {"response": "scripted", "without_owned_session": True},
    "sdk_encoding_counter_boundary": {"response": "surrogate", "standalone_sdk": True},
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def counter_delta(before, after):
    output = {}
    for published, key in STAT_KEYS.items():
        start, finish = before.get(key), after.get(key)
        output[published] = (
            finish - start
            if type(start) is int and type(finish) is int and start >= 0 and finish >= start
            else None
        )
    return output


def owned_metadata(delta):
    return {
        "scope": "run_owned_provider_client",
        "snapshot": "terminal_finish",
        **delta,
        "counters_complete": all(value is not None for value in delta.values()),
    }


def trial(name, source_dir):
    from jev_context.provider import Client, ProviderError

    from apixly_jev_harness import AgentLoop, Parameter, Task, __version__, backend
    from apixly_jev_harness import __file__ as runtime_file

    config = CASES[name]
    mock_requests, evaluation_calls = [], []
    real_network_attempts = batch_calls = scripted_calls = effects = 0
    original_native, original_evaluate = backend.native_run, backend.evaluate

    def forbid_real_network(*args, **kwargs):
        nonlocal real_network_attempts
        real_network_attempts += 1
        raise AssertionError("Owned counter fixtures prohibit real HTTP transports")

    def transport(request):
        body = json.loads(request.content)
        context = body.get("state", {}).get("context", {})
        mock_requests.append(
            {
                "json_characters": len(json.dumps(body, ensure_ascii=False)),
                "json_utf8_bytes": len(json.dumps(body, ensure_ascii=False).encode()),
                "stage": context.get("decision_stage", "seed"),
            }
        )
        response = config["response"]
        if response == "three_503" or response == "parameter_retry" and len(mock_requests) == 2:
            return httpx.Response(503, text=MARKER, headers={"retry-after": "0"})
        if response == "http_413":
            return httpx.Response(413, text=MARKER)
        if response == "invalid":
            return httpx.Response(200, text=MARKER)
        answers = {}
        for key, question in body["questions"].items():
            options = list(question["criteria"])
            answers[key] = {
                "type": "choice",
                "choice": options[0],
                "confidence": 1.0,
                "probabilities": {option: float(option == options[0]) for option in options},
            }
        return httpx.Response(
            200,
            json={
                "model": "jev-synthetic-resolved",
                "usage": {"input_tokens": 5, "output_tokens": 1},
                "answers": answers,
            },
        )

    client = Client(
        api_key=None if config["response"] == "credential_reject" else "synthetic-test-key",
        transport=httpx.MockTransport(transport),
        sleep=lambda _: None,
    )

    def credentials_unavailable():
        raise ProviderError("credentials_missing")

    def native(items, **kwargs):
        nonlocal batch_calls
        batch_calls += 1
        if kwargs.get("runner") is None:
            raise AssertionError("Every typed batch must have the explicit run-owned mock Client")
        return original_native(items, **kwargs)

    def evaluate(parts, goal, workers, spec):
        nonlocal scripted_calls
        if config.get("without_owned_session"):
            scripted_calls += 1
            judgments = {
                part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
                for i, part in enumerate(parts)
            }
            telemetry = {
                "ok": True,
                "usage_complete": True,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "requests": 1,
                "models": {},
            }
        else:
            judgments, telemetry = original_evaluate(parts, goal, workers, spec)
        evaluation_calls.append(
            {
                "stage": spec.get("context", {}).get("decision_stage"),
                "shared_context_bytes": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False).encode()
                ),
                "shared_context_characters": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False)
                ),
                "logical_requests_reported": telemetry.get("requests"),
                "model_resolved": telemetry.get("model_resolved"),
                "usage_complete": telemetry.get("usage_complete"),
                "usage_known": isinstance(telemetry.get("usage"), dict),
                "per_call_transport": {
                    key: telemetry.get("transport", {}).get(key) for key in STAT_KEYS.values()
                }
                if isinstance(telemetry.get("transport"), dict)
                else None,
            }
        )
        return judgments, telemetry

    state = {"done": bool(config.get("initially_done"))}
    workflow = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])

    def apply_corruption():
        kind = config.get("corrupt_kind")
        if kind == "private_extra":
            client.stats["private_counter"] = MARKER
        elif kind:
            client.stats[config["corrupt_key"]] = {
                "string": MARKER,
                "negative": -1,
                "bool": True,
                "reset_zero": 0,
            }[kind]

    if config.get("parameter"):

        @workflow.tool(
            "Inspect one synthetic target",
            parameters={"target": Parameter("Choose synthetic target", ["A", "B"])},
        )
        def inspect(target):
            nonlocal effects
            effects += 1
            state["done"] = True
            apply_corruption()
    else:

        @workflow.tool(
            MARKER + "A" * config["oversize_description_repetitions"]
            if config.get("oversize_description_repetitions")
            else "Inspect one synthetic target"
        )
        def inspect():
            nonlocal effects
            effects += 1
            state["done"] = True
            apply_corruption()

    seed_body = {
        "model": "jev-1.13.0",
        "state": {},
        "questions": {
            "target": {
                "type": "choice",
                "instructions": "Choose one synthetic item",
                "criteria": {"a": "Synthetic A", "REVIEW": "Needs review"},
            }
        },
    }
    packet, exception_type = None, None
    with (
        client,
        patch("httpx.HTTPTransport.handle_request", forbid_real_network),
        patch("apixly_jev_harness.backend.Client", lambda **kwargs: client),
        patch("apixly_jev_harness.backend.native_run", native),
        patch("apixly_jev_harness.engine.analysis.evaluate", evaluate),
        patch("apixly_jev_harness.engine.time", SimpleNamespace(monotonic=lambda: 100.0)),
    ):
        credential_patch = (
            patch("jev_context.provider.credential", credentials_unavailable)
            if config["response"] == "credential_reject"
            else patch.dict(os.environ, {}, clear=False)
        )
        with credential_patch:
            for _ in range(config.get("seed_calls", 0)):
                client.call(seed_body)
            mock_seed_attempts = len(mock_requests)
            before = {key: client.stats.get(key) for key in STAT_KEYS.values()}
            started = time.perf_counter()
            with tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "run.jsonl"
                if config.get("standalone_sdk"):
                    backend.Session(
                        client
                    )  # Take the same initial snapshot as a run-owned Session.
                    body = {**seed_body, "state": "\ud800"}
                    try:
                        client.call(body)
                    except UnicodeEncodeError as error:
                        exception_type = type(error).__name__
                elif config.get("without_owned_session"):
                    token = backend._ACTIVE.set(None)
                    try:
                        engine = AgentLoop()
                        packet = engine.run.__wrapped__(
                            engine,
                            workflow,
                            goal="Inspect one synthetic target",
                            archive=archive,
                            max_steps=2,
                        )
                    finally:
                        backend._ACTIVE.reset(token)
                else:
                    packet = AgentLoop().run(
                        workflow, goal="Inspect one synthetic target", archive=archive, max_steps=2
                    )
                elapsed = time.perf_counter() - started
                events = (
                    [json.loads(line)["event"] for line in archive.read_text().splitlines()]
                    if archive.exists()
                    else []
                )
            after = {key: client.stats.get(key) for key in STAT_KEYS.values()}
    delta = counter_delta(before, after)
    owns_session = not config.get("without_owned_session") and not config.get("standalone_sdk")
    protected_delta = dict(delta)
    if config.get("corrupt_kind") == "reset_zero":
        # The successful per-call snapshot already witnessed one request before the reset.
        protected_delta["request_attempts"] = None
    expected_owned = owned_metadata(protected_delta) if owns_session else None
    telemetry = packet.get("telemetry", {}) if packet else {}
    owned = telemetry.get("owned_transport")
    owned_correct = owned == expected_owned and ("owned_transport" in telemetry) == owns_session
    compact = (
        {key: value for key, value in packet.items() if key != "archive"}
        if packet
        else {"exception_type": exception_type}
    )
    safe_owned = (
        expected_owned
        if owned == expected_owned
        else {"matches_expected": False}
        if owned is not None
        else None
    )
    failures = config["response"] in {
        "three_503",
        "credential_reject",
        "http_413",
        "invalid",
    } or config.get("oversize_description_repetitions")
    expected_status = (
        "sdk_encoding_error"
        if config.get("standalone_sdk")
        else "needs_review"
        if failures
        else "done"
    )
    expected_effects = (
        0 if failures or config.get("initially_done") or config.get("standalone_sdk") else 1
    )
    expected_logical = (
        0
        if config.get("initially_done")
        or config.get("oversize_description_repetitions")
        or config.get("standalone_sdk")
        else 2
        if config.get("parameter")
        else 1
    )
    expected_attempts = (
        0
        if config.get("initially_done")
        or config.get("oversize_description_repetitions")
        or config.get("without_owned_session")
        or config["response"] == "credential_reject"
        else 3
        if config["response"] in {"three_503", "parameter_retry"}
        else 1
    )
    expected_mock_entries = 0 if config.get("standalone_sdk") else expected_attempts
    expected_usage_complete = (
        None
        if config.get("standalone_sdk")
        else config["response"]
        not in {"parameter_retry", "three_503", "credential_reject", "http_413", "invalid"}
    )
    expected_usage = (
        None
        if expected_usage_complete is not True
        else {"input_tokens": 0, "output_tokens": 0}
        if expected_logical == 0 or config.get("without_owned_session")
        else {"input_tokens": 5, "output_tokens": 1}
    )
    status = (
        packet["status"]
        if packet
        else "sdk_encoding_error"
        if exception_type == "UnicodeEncodeError"
        else "unknown"
    )
    observed_attempts = delta["request_attempts"]
    # Corruption makes this counter unknown; expected physical mock entries remain independently known.
    attempts_correct = (
        observed_attempts == 0
        if config.get("corrupt_kind") == "reset_zero"
        else observed_attempts == expected_attempts
        if config.get("corrupt_key") != "requests"
        else observed_attempts is None
    )
    behavior_correct = (
        status == expected_status
        and effects == expected_effects
        and (packet.get("steps") if packet else None)
        == (expected_effects if not config.get("standalone_sdk") else None)
        and events.count("intent") == expected_effects
        and (telemetry.get("requests", 0)) == expected_logical
        and (telemetry.get("usage_complete") if packet else None) == expected_usage_complete
        and telemetry.get("usage") == expected_usage
        and len(mock_requests) - mock_seed_attempts == expected_mock_entries
        and attempts_correct
    )
    raw_exposures = json.dumps(compact, ensure_ascii=False).count(MARKER)
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": {**config, "frozen_loop_monotonic": 100.0},
        "expected": {
            "status": expected_status,
            "effects": expected_effects,
            "logical_requests": expected_logical,
            "mock_transport_entries_in_operation": expected_mock_entries,
            "sdk_attempt_counter_in_operation": expected_attempts,
            "usage_complete": expected_usage_complete,
            "owned_transport": expected_owned,
        },
        "result": {
            "status": status,
            "exception_type": exception_type,
            "complete": packet.get("complete") if packet else None,
            "steps": packet.get("steps") if packet else None,
            "effects": effects,
            "intent_events": events.count("intent"),
            "logical_requests": telemetry.get("requests", 0),
            "scripted_selection_calls": scripted_calls,
            "mock_typed_batch_calls": batch_calls,
            "mock_transport_entries_total": len(mock_requests),
            "mock_seed_transport_entries": mock_seed_attempts,
            "mock_transport_entries_in_operation": len(mock_requests) - mock_seed_attempts,
            "sdk_counter_delta_independent": delta,
            "counter_types_at_finish": {
                published: type(after.get(key)).__name__ for published, key in STAT_KEYS.items()
            },
            "owned_transport": safe_owned,
            "owned_transport_correct": owned_correct,
            "behavior_correct": behavior_correct,
            "usage_complete": telemetry.get("usage_complete") if packet else None,
            "reported_mock_usage": telemetry.get("usage"),
            "evaluation_calls": evaluation_calls,
            "mock_request_sizes": mock_requests,
            "real_network_attempts": real_network_attempts,
            "raw_marker_exposures": raw_exposures,
        },
        "correct": behavior_correct
        and owned_correct
        and raw_exposures == 0
        and real_network_attempts == 0,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(compact, ensure_ascii=False).encode()),
        "actual_model_usage": ZERO_USAGE
        if real_network_attempts == 0
        else {
            "requests": None,
            "models": {},
            "input_tokens": None,
            "output_tokens": None,
            "usage_complete": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", choices=list(CASES), help=argparse.SUPPRESS)
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, args.source_dir)
        print(json.dumps(trial(args.worker, args.source_dir)))
        return 0
    if not args.output:
        parser.error("--output is required")
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = snapshot(args.baseline_ref, root / "baseline")
        sources = {"baseline": root / "baseline/src", "candidate": ROOT / "src"}
        hashes = {arm: source_hashes(source) for arm, source in sources.items()}
        runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        for name in CASES:
            for repeat in range(3):
                for arm in (
                    ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                ):
                    env = {
                        key: value
                        for key, value in os.environ.items()
                        if not key.startswith("TYPESAFE_")
                    }
                    output = subprocess.check_output(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--worker",
                            name,
                            "--source-dir",
                            str(sources[arm]),
                        ],
                        env=env,
                        text=True,
                    )
                    row = json.loads(output)
                    row.update(arm=arm, repeat=repeat + 1)
                    if (
                        row.pop("source_sha256") != hashes[arm]
                        or not row["runtime_loaded_from_requested_source"]
                    ):
                        raise RuntimeError("runtime_source_changed_or_misloaded")
                    rows.append(row)
        if (
            any(source_hashes(source) != hashes[arm] for arm, source in sources.items())
            or runner_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        ):
            raise RuntimeError("benchmark_sources_changed_during_run")
    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        guard_hit = any(row["result"]["real_network_attempts"] for row in group)
        summaries[arm] = {
            "runs": len(group),
            "correct": sum(row["correct"] for row in group),
            "behavior_correct": sum(row["result"]["behavior_correct"] for row in group),
            "owned_transport_correct": sum(
                row["result"]["owned_transport_correct"] for row in group
            ),
            "owned_transport_present": sum(
                row["result"]["owned_transport"] is not None for row in group
            ),
            "incomplete_owned_counter_rows": sum(
                row["result"]["owned_transport"] is not None
                and row["result"]["owned_transport"].get("counters_complete") is False
                for row in group
            ),
            "logical_requests_reported": sum(row["result"]["logical_requests"] for row in group),
            "scripted_selection_calls": sum(
                row["result"]["scripted_selection_calls"] for row in group
            ),
            "mock_typed_batch_calls": sum(row["result"]["mock_typed_batch_calls"] for row in group),
            "mock_transport_entries_total": sum(
                row["result"]["mock_transport_entries_total"] for row in group
            ),
            "mock_seed_transport_entries": sum(
                row["result"]["mock_seed_transport_entries"] for row in group
            ),
            "mock_transport_entries_in_operation": sum(
                row["result"]["mock_transport_entries_in_operation"] for row in group
            ),
            "effects": sum(row["result"]["effects"] for row in group),
            "usage_unknown_rows": sum(row["result"]["usage_complete"] is False for row in group),
            "real_network_attempts": sum(row["result"]["real_network_attempts"] for row in group),
            "raw_marker_exposures": sum(row["result"]["raw_marker_exposures"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "shared_context_bytes": sum(
                call["shared_context_bytes"]
                for row in group
                for call in row["result"]["evaluation_calls"]
            ),
            "actual_model_usage": ZERO_USAGE
            if not guard_hit
            else {
                "requests": None,
                "models": {},
                "input_tokens": None,
                "output_tokens": None,
                "usage_complete": False,
            },
        }
    parity_keys = (
        "status",
        "exception_type",
        "complete",
        "steps",
        "effects",
        "intent_events",
        "logical_requests",
        "scripted_selection_calls",
        "mock_typed_batch_calls",
        "mock_transport_entries_total",
        "mock_seed_transport_entries",
        "mock_transport_entries_in_operation",
        "sdk_counter_delta_independent",
        "usage_complete",
        "reported_mock_usage",
        "evaluation_calls",
    )
    behavior_parity = all(
        next(
            row
            for row in rows
            if row["case"] == case and row["repeat"] == repeat and row["arm"] == "baseline"
        )["result"][key]
        == next(
            row
            for row in rows
            if row["case"] == case and row["repeat"] == repeat and row["arm"] == "candidate"
        )["result"][key]
        for case in CASES
        for repeat in (1, 2, 3)
        for key in parity_keys
    )
    report = {
        "mode": "offline-synthetic-owned-transport",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "behavior_parity": behavior_parity,
        "reproduction": "python benchmarks/owned_transport.py --output local-results/transport-counters-ab.json",
        "scope": "Sixteen fixed synthetic fixtures, three paired repeats with alternating arm order. Normal scenarios use the pinned typed batch and Client only through explicit httpx.MockTransport with a synthetic key; real HTTPTransport is forbidden. Fourteen run-owned snapshots compare fixed SDK counter deltas taken before the run and at terminal finish; valid per-key counters survive while invalid string/negative/bool counters and a reset below a witnessed per-call high-water become unknown, and private extra keys are omitted. A preused Client seed operation is excluded from run-owned deltas. An unwrapped no-active loop uses scripted selection and must omit ownership metadata. A standalone SDK/Session supplement deliberately fails UTF-8 serialization: SDK request counter increments before MockTransport entry, so this is not an HTTP-dispatch count. Actual model/network/UI calls are zero if the guard is never hit.",
        "negative_results": "New fixed snapshot metadata adds returned bytes and local stats-validation work. SDK counters do not prove remote receipt, inference, billing, HTTP dispatch, TCP connection reuse or other tool traffic. Existing telemetry.requests remains logical packed-request aggregation and per-call transport fields remain unchanged. Mocked retry/HTTP failure usage remains unknown; complete local counters do not make it known. Inactive Session and standalone non-loop paths omit metadata rather than report fake zero ownership. No semantic quality, real-provider transport measurement, speed or fee gain is claimed.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only with no forbidden real transport attempts; a guard hit records unknown actual usage and fails the fixture. Logical requests, scripted selection, mock transport entries, standalone SDK counters and mock token usage are explicitly separate. Real perf_counter timing includes loop admission, pinned request planning, bounded mock retry/validation, effects, terminal snapshot and private journal flush/fsync; excludes process/import/client/task setup, optional seed operation and post-call analysis/source hashing. Loop-only frozen monotonic values stabilize context budgets without substituting for whole-operation timing. Returned bytes exclude local archive paths and scalar context/request sizes do not count provider tokens.",
        "summary": summaries,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"behavior_parity": behavior_parity, "summary": summaries}))
    return (
        0
        if behavior_parity and all(row["correct"] for row in rows if row["arm"] == "candidate")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
