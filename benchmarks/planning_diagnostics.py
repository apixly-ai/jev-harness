"""Offline paired typed-plan deferral diagnostics against exact v0.1.9."""

import argparse
import copy
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "bb808e1472d3894e276689115574f126c193c52a"
MARKER = "SYNTHETIC_UNTRUSTED_DETAIL"
PLANNING_CODES = {"request_needs_narrowing", "request_needs_context", "request_planning_review"}
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "direct_ascii_60k": {
        "mode": "direct",
        "character": "A",
        "text_repetitions": 60000,
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "direct_chinese_60k": {
        "mode": "direct",
        "character": "中",
        "text_repetitions": 60000,
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "direct_254_choices": {
        "mode": "direct",
        "records": 254,
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "direct_missing_record_field": {
        "mode": "direct",
        "required_record_fields": ["source.required"],
        "plan_code": "request_needs_context",
        "typed_status": "NEEDS_CONTEXT",
    },
    "direct_small_mock_choice": {"mode": "direct", "mock_response": "choice"},
    "loop_tool_oversize": {
        "mode": "loop",
        "location": "tool",
        "text_repetitions": 60000,
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "loop_parameter_oversize": {
        "mode": "loop",
        "location": "parameter",
        "text_repetitions": 60000,
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "prior_unknown_then_parameter": {
        "mode": "loop",
        "location": "parameter",
        "text_repetitions": 60000,
        "mock_response": "retry_then_choice",
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "fallback_then_effect_error": {
        "mode": "loop",
        "location": "fallback",
        "text_repetitions": 60000,
        "plan_code": "request_needs_narrowing",
        "typed_status": "NEEDS_NARROWING",
    },
    "unknown_plan_deferred": {
        "mode": "direct",
        "plan_stub": "unknown",
        "plan_code": "request_planning_review",
        "typed_status": "UNAVAILABLE",
    },
    "unsafe_plan_enum_injection": {
        "mode": "direct",
        "plan_stub": "injected",
        "plan_code": "request_needs_context",
        "typed_status": "NEEDS_CONTEXT",
    },
    "generic_spec_value_error": {
        "mode": "direct",
        "context_repetitions": 17000,
        "expected_exception": "ValueError",
    },
    "mock_http_413_loop": {"mode": "loop", "mock_response": "http_413"},
    "mock_http_413_direct": {"mode": "direct", "mock_response": "http_413"},
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def planning_metadata(code):
    return {
        "scope": "current_selection",
        "phase": "request_planning",
        "inference_dispatched": False,
        "reason_codes": [code],
    }


def safe_planning(value):
    if not isinstance(value, dict):
        return None
    if (
        value.get("scope") != "current_selection"
        or value.get("phase") != "request_planning"
        or value.get("inference_dispatched") is not False
    ):
        return {"invalid_metadata": True}
    codes = value.get("reason_codes")
    if (
        not isinstance(codes, list)
        or any(code not in PLANNING_CODES for code in codes if isinstance(code, str))
        or any(not isinstance(code, str) for code in codes)
    ):
        return {"invalid_metadata": True}
    return {
        "scope": "current_selection",
        "phase": "request_planning",
        "inference_dispatched": False,
        "reason_codes": codes,
    }


def trial(name, source_dir):
    from jev_context.provider import Client

    from apixly_jev_harness import (
        Action,
        AgentLoop,
        Engine,
        Option,
        Parameter,
        Task,
        Workflow,
        __version__,
        backend,
    )
    from apixly_jev_harness import __file__ as runtime_file

    config = CASES[name]
    calls, plans, mock_requests = [], [], []
    effects = real_network_attempts = mock_batch_dispatches = 0
    state = {"done": False}
    original_plan, original_evaluate, original_native = (
        backend.core.plan,
        backend.evaluate,
        backend.native_run,
    )

    def forbid_real_network(*args, **kwargs):
        nonlocal real_network_attempts
        real_network_attempts += 1
        raise AssertionError("Synthetic benchmark must never use a real HTTP transport")

    def transport(request):
        body = json.loads(request.content)
        mock_requests.append(
            {
                "request_json_characters": len(json.dumps(body, ensure_ascii=False)),
                "request_json_utf8_bytes": len(json.dumps(body, ensure_ascii=False).encode()),
                "question_count": len(body["questions"]),
                "criterion_count": len(body["questions"]["target"]["criteria"]),
            }
        )
        if config.get("mock_response") == "http_413":
            return httpx.Response(413, text=MARKER)
        if config.get("mock_response") == "retry_then_choice" and len(mock_requests) == 1:
            return httpx.Response(503, text=MARKER, headers={"retry-after": "0"})
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
                        "confidence": 1.0,
                        "probabilities": {
                            option: float(option == options[0]) for option in options
                        },
                    }
                },
            },
        )

    client = Client(
        api_key="synthetic-test-key", transport=httpx.MockTransport(transport), sleep=lambda _: None
    )

    def mock_native(items, **kwargs):
        nonlocal mock_batch_dispatches
        mock_batch_dispatches += 1
        # The real typed-batch code executes only through our explicit mock-transport Session.
        kwargs["runner"] = backend.Session(client).run
        return original_native(items, **kwargs)

    def plan(parts, goal, spec):
        if config.get("plan_stub"):
            deferred = "NEEDS_CONTEXT" if config["plan_stub"] == "injected" else MARKER
            planned = {
                "items": [],
                "routes": {},
                "deferred": {part["id"]: deferred for part in parts},
            }
            if config["plan_stub"] == "injected":
                planned.update(
                    reason_codes=[MARKER], planning={"scope": MARKER, "reason_codes": [MARKER]}
                )
        else:
            planned = original_plan(parts, goal, spec)
        status_counts = {}
        for status in planned.get("deferred", {}).values():
            admitted = status if status in {"NEEDS_CONTEXT", "NEEDS_NARROWING"} else "UNRECOGNIZED"
            status_counts[admitted] = status_counts.get(admitted, 0) + 1
        plans.append(
            {
                "items": len(planned["items"]),
                "deferred_status_counts": status_counts,
                "source_count": len(parts),
            }
        )
        return planned

    def evaluate(parts, goal, workers, spec):
        judgments, telemetry = original_evaluate(parts, goal, workers, spec)
        statuses = {}
        for judgment in judgments.values():
            status = judgment.get("status")
            key = (
                status
                if status in {"OK", "UNAVAILABLE", "NEEDS_CONTEXT", "NEEDS_NARROWING"}
                else "UNRECOGNIZED"
            )
            statuses[key] = statuses.get(key, 0) + 1
        planning = telemetry.get("planning")
        calls.append(
            {
                "stage": spec.get("context", {}).get("decision_stage", "direct_selection"),
                "typed_status_counts": statuses,
                "planning": safe_planning(planning),
                "planning_raw_marker_exposures": json.dumps(planning).count(MARKER),
                "requests_reported": telemetry.get("requests"),
                "usage_complete": telemetry.get("usage_complete"),
                "usage_known": isinstance(telemetry.get("usage"), dict),
                "provider_failure_codes": [
                    code
                    for code in telemetry.get("provider_failure_codes", [])
                    if code == "http_413_body_suppressed"
                ],
                "raw_planning_matches_expected": planning
                == (
                    planning_metadata(config["plan_code"])
                    if not plans[-1]["items"] and config.get("plan_code")
                    else None
                ),
            }
        )
        return judgments, telemetry

    started = time.perf_counter()
    records = [{"id": "a", "text": "Synthetic A"}, {"id": "b", "text": "Synthetic B"}]
    if config.get("records"):
        records = [
            {"id": str(index), "text": "Synthetic option"} for index in range(config["records"])
        ]
    elif config.get("text_repetitions") and config["mode"] == "direct":
        records[0]["text"] = MARKER + config.get("character", "A") * config["text_repetitions"]

    workflow = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])
    if config.get("location") == "parameter":

        @workflow.tool(
            "Inspect one synthetic target",
            parameters={
                "parent": ["fixed"],
                "target": Parameter(
                    "Choose synthetic target",
                    lambda ctx, seen, bound: [
                        Option("a", MARKER + "A" * config["text_repetitions"], "A"),
                        Option("b", "Synthetic B", "B"),
                    ],
                    depends_on=("parent",),
                ),
            },
        )
        def inspect(parent, target):
            nonlocal effects
            effects += 1
            state["done"] = True
    else:

        @workflow.tool(
            MARKER + "A" * config["text_repetitions"]
            if config.get("location") == "tool"
            else "Inspect one synthetic target"
        )
        def inspect():
            nonlocal effects
            effects += 1
            state["done"] = True

    class Fallback(Workflow):
        def observe(self, ctx):
            return dict(state)

        def verify(self, ctx, seen):
            return seen["done"]

        def candidates(self, ctx, seen):
            return [Action("inspect", "Inspect one synthetic target", {"target": "caller-default"})]

        def bind(self, ctx, seen, action, choose):
            optional = choose(
                [
                    {"id": "a", "text": MARKER + "A" * config["text_repetitions"]},
                    {"id": "b", "text": "Synthetic B"},
                ],
                "Choose an optional synthetic target",
                {"selected_tool": "inspect", "parameter": "target"},
            )
            assert not optional["complete"]
            return action

        def execute(self, ctx, action):
            nonlocal effects
            effects += 1
            state["done"] = True
            raise TimeoutError(MARKER)

    exception_type, packet = None, None
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "run.jsonl"
        with (
            client,
            patch("apixly_jev_harness.backend.Client", lambda **kwargs: client),
            patch("apixly_jev_harness.backend.native_run", mock_native),
            patch("apixly_jev_harness.backend.core.plan", plan),
            patch("apixly_jev_harness.engine.analysis.evaluate", evaluate),
            patch("httpx.HTTPTransport.handle_request", forbid_real_network),
        ):
            try:
                if config["mode"] == "direct":
                    spec = {
                        "mode": "choose",
                        "selection_policy": "any",
                        "required_record_fields": config.get("required_record_fields", []),
                    }
                    packet = Engine().decide(
                        records,
                        goal="Choose one synthetic record",
                        context={"payload": "A" * config["context_repetitions"]}
                        if config.get("context_repetitions")
                        else {},
                        analysis_spec=spec,
                    )
                else:
                    packet = AgentLoop().run(
                        Fallback() if config.get("location") == "fallback" else workflow,
                        goal="Inspect one synthetic target",
                        max_steps=2,
                        archive=archive,
                    )
            except ValueError as error:
                exception_type = type(error).__name__
        elapsed = time.perf_counter() - started
        events = (
            [json.loads(line)["event"] for line in archive.read_text(encoding="utf-8").splitlines()]
            if archive.exists()
            else []
        )
    compact = (
        {key: value for key, value in packet.items() if key != "archive"}
        if packet
        else {"exception_type": exception_type}
    )
    direct = config["mode"] == "direct"
    if exception_type:
        status = "raised_value_error"
    elif direct:
        status = "admitted" if packet.get("complete") else "review"
    else:
        status = packet.get("status")
    usage = packet.get("telemetry", {}).get("usage") if packet else None
    diagnostic = packet.get("diagnostic") if packet else None
    expected_diag = None
    if not direct and config.get("location") != "fallback":
        code = config.get("plan_code") or "http_413_body_suppressed"
        stage = "parameter_selection" if config.get("location") == "parameter" else "tool_selection"
        expected_diag = {
            "stage": stage,
            "reason_codes": [code],
            "automatic_retry": False,
            **(
                {"tool_id": "inspect", "parameter": "target"}
                if stage == "parameter_selection"
                else {}
            ),
        }
    expected_status = (
        "raised_value_error"
        if config.get("expected_exception")
        else "admitted"
        if name == "direct_small_mock_choice"
        else "execution_uncertain"
        if config.get("location") == "fallback"
        else "review"
        if direct
        else "needs_review"
    )
    expected_dispatches = (
        0
        if direct
        and config.get("plan_code")
        or config.get("expected_exception")
        or config.get("location") == "tool"
        else 1
    )
    expected_mock_attempts = (
        2 if config.get("mock_response") == "retry_then_choice" else expected_dispatches
    )
    expected_effects = int(config.get("location") == "fallback")
    expected_calls = (
        0
        if config.get("expected_exception")
        else 2
        if config.get("location") in {"parameter", "fallback"}
        else 1
    )
    expected_usage_complete = (
        None
        if config.get("expected_exception")
        else config.get("mock_response") not in {"retry_then_choice", "http_413"}
    )
    behavior_correct = (
        status == expected_status
        and effects == expected_effects
        and events.count("intent") == expected_effects
        and mock_batch_dispatches == expected_dispatches
        and len(mock_requests) == expected_mock_attempts
        and exception_type == config.get("expected_exception")
        and (packet.get("telemetry", {}).get("usage_complete") if packet else None)
        == expected_usage_complete
        and (isinstance(usage, dict) if packet else False) == (expected_usage_complete is True)
    )
    planning_correct = len(calls) == expected_calls and all(
        call["raw_planning_matches_expected"] for call in calls
    )
    deferred_calls = [call for call, planned in zip(calls, plans) if not planned["items"]]
    typed_status_correct = (
        not config.get("typed_status")
        or bool(deferred_calls)
        and all(
            call["typed_status_counts"]
            == {config["typed_status"]: sum(call["typed_status_counts"].values())}
            for call in deferred_calls
        )
    )
    diagnostic_correct = diagnostic == expected_diag
    exposures = json.dumps(compact, ensure_ascii=False).count(MARKER) + sum(
        call["planning_raw_marker_exposures"] for call in calls
    )
    # Publish fixed projected diagnostics only, even if an injected negative fixture leaks.
    safe_diag = (
        copy.deepcopy(expected_diag)
        if diagnostic == expected_diag
        else {"matches_expected": False}
        if diagnostic
        else None
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": config,
        "expected": {
            "status": expected_status,
            "effects": expected_effects,
            "mock_batch_dispatches": expected_dispatches,
            "mock_http_attempts": expected_mock_attempts,
            "usage_complete": expected_usage_complete,
            "diagnostic": expected_diag,
        },
        "result": {
            "status": status,
            "exception_type": exception_type,
            "complete": packet.get("complete") if packet else None,
            "selected_count": len(packet.get("selected_ids", [])) if packet else 0,
            "review_count": len(packet.get("review_ids", [])) if packet else 0,
            "effects": effects,
            "intent_events": events.count("intent"),
            "mock_batch_dispatches": mock_batch_dispatches,
            "mock_http_attempts": len(mock_requests),
            "mock_request_sizes": mock_requests,
            "planning_calls": calls,
            "plans": plans,
            "diagnostic": safe_diag,
            "diagnostic_correct": diagnostic_correct,
            "planning_correct": planning_correct,
            "typed_status_correct": typed_status_correct,
            "behavior_correct": behavior_correct,
            "usage_complete": packet.get("telemetry", {}).get("usage_complete") if packet else None,
            "usage_known": isinstance(usage, dict),
            "reported_mock_usage": usage if isinstance(usage, dict) else None,
            "real_network_attempts": real_network_attempts,
            "raw_marker_exposures": exposures,
        },
        "correct": behavior_correct
        and planning_correct
        and typed_status_correct
        and diagnostic_correct
        and exposures == 0
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
            "planning_correct": sum(row["result"]["planning_correct"] for row in group),
            "diagnostic_correct": sum(row["result"]["diagnostic_correct"] for row in group),
            "typed_status_correct": sum(row["result"]["typed_status_correct"] for row in group),
            "mock_batch_dispatches": sum(row["result"]["mock_batch_dispatches"] for row in group),
            "mock_http_attempts": sum(row["result"]["mock_http_attempts"] for row in group),
            "effects": sum(row["result"]["effects"] for row in group),
            "intent_events": sum(row["result"]["intent_events"] for row in group),
            "real_network_attempts": sum(row["result"]["real_network_attempts"] for row in group),
            "raw_marker_exposures": sum(row["result"]["raw_marker_exposures"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
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
        "complete",
        "selected_count",
        "review_count",
        "effects",
        "intent_events",
        "mock_batch_dispatches",
        "mock_http_attempts",
        "usage_complete",
        "usage_known",
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
        "mode": "offline-synthetic-planning-diagnostics",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "behavior_parity": behavior_parity,
        "reproduction": "python benchmarks/planning_diagnostics.py --output local-results/planning-diagnostics-ab.json",
        "scope": "Fourteen fixed synthetic fixtures, three paired repeats with alternating arm order. Actual pinned core.plan handles oversized ASCII/Chinese records, 254 options, required-record fields and dependent parameter descriptions. Small/HTTP/retry fixtures execute the pinned typed batch and provider Client only through explicit httpx.MockTransport with a synthetic key; real HTTPTransport is forbidden. Mock dispatches and HTTP attempts are separate from actual model usage, which is zero if the guard is never hit. Two injected plan fixtures test safe enum projection; a generic 17,000-character spec ValueError remains an exception. Unknown usage after a mocked retry or HTTP 413 remains unknown in reported mock telemetry.",
        "negative_results": "New fixed planning metadata and reason codes add returned bytes and local projection work. Request fit limits, option counts, prompts and loop context limits are unchanged; typed NEEDS_CONTEXT is preserved instead of being folded into NEEDS_NARROWING, and unrecognized statuses become UNAVAILABLE. End-state/selection/effect parity excludes that deliberate typed-status correction and diagnostic fields. No semantic quality, speed, real-provider fit, live HTTP behavior, fee benefit or automatic retry improvement is claimed. The only retry is the pinned SDK's existing bounded policy exercised by synthetic MockTransport. A trusted fallback clears the current failure diagnostic but keeps its historical call metadata; later effects remain execution_uncertain.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only with no forbidden real transport attempts; a guard hit records unknown actual usage and fails the fixture. Reported mock usage and unknown mock attempts never represent paid usage. Real whole-operation timing includes synthetic registration, actual planning, mocked typed batch/provider validation, bounded mock transport attempts, permitted effect and private journal serialization; excludes process/import/client-fixture setup and terminal-analysis/source hashing. Returned context bytes exclude local archive paths; raw candidate bodies, injected detail and response text are omitted.",
        "summary": summaries,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"behavior_parity": behavior_parity, "summary": summaries}))
    return (
        0
        if behavior_parity and all(row["correct"] for row in rows if row["arm"] == "candidate")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
