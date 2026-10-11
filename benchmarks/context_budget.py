"""Offline paired diagnostics preserving the loop's 15,000 JSON-character limit."""

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

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "c757179c22e6104df06a44e8ce66e5217f1d96c7"
LIMIT = 15000
MARKER = "SYNTHETIC_CONTEXT_MARKER"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "ascii_projection_over": {
        "character": "A",
        "target": "context_projection",
        "characters": 15001,
    },
    "ascii_projection_exact": {
        "character": "A",
        "target": "context_projection",
        "characters": 15000,
    },
    "ascii_tool_over": {"character": "A", "target": "tool_selection", "characters": 15001},
    "ascii_tool_exact": {"character": "A", "target": "tool_selection", "characters": 15000},
    "ascii_tool_under": {"character": "A", "target": "tool_selection", "characters": 14999},
    "chinese_tool_exact": {"character": "中", "target": "tool_selection", "characters": 15000},
    "emoji_tool_exact": {"character": "🙂", "target": "tool_selection", "characters": 15000},
    "chinese_tool_over": {"character": "中", "target": "tool_selection", "characters": 15001},
    "emoji_projection_over": {
        "character": "🙂",
        "target": "context_projection",
        "characters": 15001,
    },
    "ascii_parameter_exact": {
        "character": "A",
        "target": "parameter_selection",
        "characters": 15000,
    },
    "ascii_parameter_over": {
        "character": "A",
        "target": "parameter_selection",
        "characters": 15001,
    },
    "chinese_parameter_exact": {
        "character": "中",
        "target": "parameter_selection",
        "characters": 15000,
    },
    "direct_ascii_over": {"character": "A", "target": "direct_decide", "characters": 15001},
    "direct_chinese_over": {"character": "中", "target": "direct_decide", "characters": 15001},
}


def measure(context):
    encoded = json.dumps(context, ensure_ascii=False)
    return {"characters": len(encoded), "utf8_bytes": len(encoded.encode())}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def trial(name, source_dir):
    from apixly_jev_harness import AgentLoop, Engine, Option, Parameter, Task, __version__
    from apixly_jev_harness import __file__ as runtime_file

    config = CASES[name]
    native_attempts = effects = 0
    requests = []
    state = {"done": False}

    def forbidden(*args, **kwargs):
        nonlocal native_attempts
        native_attempts += 1
        raise AssertionError("Offline context fixtures prohibit native inference")

    def decide(parts, goal, workers, spec):
        context = spec.get("context", {})
        requests.append(
            {"stage": context.get("decision_stage", "direct_decide"), **measure(context)}
        )
        return {
            item["id"]: {"status": "OK", "decision": "MATCH" if index == 0 else "EXCLUDE"}
            for index, item in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "requests": 1,
            "models": {},
        }

    started = time.perf_counter()
    workflow = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])
    parameter_mode = config["target"] == "parameter_selection"
    if parameter_mode:

        @workflow.tool(
            "Execute one synthetic step",
            parameters={
                "target": Parameter(
                    "Choose synthetic target",
                    [Option("a", "Synthetic A", "A"), Option("b", "Synthetic B", "B")],
                )
            },
        )
        def inspect(target):
            nonlocal effects
            effects += 1
            state["done"] = True
            return {"value": target}
    else:

        @workflow.tool("Execute one synthetic step")
        def inspect():
            nonlocal effects
            effects += 1
            state["done"] = True
            return {"done": True}

    def contexts(payload):
        projection = {
            "payload": payload,
            "budgets": {"remaining_steps": 2, "remaining_seconds": 120.0},
        }
        tool = {**projection, "decision_stage": "tool_selection"}
        parameter = {
            **projection,
            "selected_tool": "inspect",
            "tool_contract": workflow.describe()["inspect"],
            "parameter": "target",
            "parameter_description": "Choose synthetic target",
            "bound_references": {},
            "decision_stage": "parameter_selection",
        }
        return {
            "context_projection": projection,
            "tool_selection": tool,
            "parameter_selection": parameter,
            "direct_decide": {"payload": payload},
        }

    overhead = measure(contexts(MARKER)[config["target"]])["characters"]
    repetitions = config["characters"] - overhead
    if repetitions < 0:
        raise ValueError("invalid_synthetic_fixture_size")
    payload = MARKER + config["character"] * repetitions
    direct = config["target"] == "direct_decide"
    stages = (
        ["direct_decide"]
        if direct
        else ["context_projection", "tool_selection"]
        + (["parameter_selection"] if parameter_mode else [])
    )
    projections = contexts(payload)
    sizes = {stage: measure(projections[stage]) for stage in stages}
    rejection = (
        next(
            (stage for stage in stages if sizes[stage]["characters"] > LIMIT),
            None,
        )
        if not direct
        else None
    )
    decisions = (
        1
        if direct or not rejection and not parameter_mode or rejection == "parameter_selection"
        else 2
        if not rejection
        else 0
    )
    expected_status = "admitted" if direct else "needs_review" if rejection else "done"
    expected = {
        "status": expected_status,
        "scripted_decisions": decisions,
        "effects": 0 if direct or rejection else 1,
        "intent_events": 0 if direct or rejection else 1,
        "reason": "context_budget_exceeded" if rejection else None,
        "context_budget": {
            "scope": "loop_shared_context",
            "stage": rejection,
            "unit": "json_characters",
            "limit": LIMIT,
            "observed": sizes[rejection]["characters"],
        }
        if rejection
        else None,
    }

    class FixedPolicy:
        def build(self, ctx, observation):
            return {"payload": payload}

    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "run.jsonl"
        with (
            patch("apixly_jev_harness.backend.native_run", forbidden),
            patch("apixly_jev_harness.backend.provider_evaluate", forbidden),
            patch("apixly_jev_harness.engine.analysis.evaluate", decide),
            patch("apixly_jev_harness.engine.time", SimpleNamespace(monotonic=lambda: 100.0)),
        ):
            if direct:
                packet = Engine().decide(
                    [{"id": "a", "text": "Synthetic A"}, {"id": "b", "text": "Synthetic B"}],
                    goal="Choose one synthetic record",
                    context={"payload": payload},
                    analysis_spec={"mode": "choose", "selection_policy": "any"},
                )
            else:
                packet = AgentLoop().run(
                    workflow,
                    goal="Resolve one synthetic state",
                    context_policy=FixedPolicy(),
                    max_steps=2,
                    timeout_seconds=120,
                    archive=archive,
                )
        elapsed = time.perf_counter() - started
        events = (
            [json.loads(line)["event"] for line in archive.read_text().splitlines()]
            if archive.exists()
            else []
        )
    compact = {key: value for key, value in packet.items() if key != "archive"}
    status = (
        "admitted"
        if direct
        and packet.get("ok")
        and packet.get("complete")
        and packet.get("selected_ids") == ["a"]
        else packet.get("status", "unknown")
    )
    calls = packet.get("telemetry", {}).get("calls", [])
    call_telemetry = [
        {
            key: call.get(key)
            for key in ("stage", "context_characters", "context_character_limit", "context_bytes")
        }
        for call in calls
    ]
    failure_metadata_correct = packet.get("context_budget") == expected["context_budget"]
    success_metadata_correct = len(call_telemetry) == (0 if direct else len(requests)) and all(
        call["stage"] == request["stage"]
        and call["context_characters"] == request["characters"]
        and call["context_character_limit"] == LIMIT
        and call["context_bytes"] == request["utf8_bytes"]
        for call, request in zip(call_telemetry, requests)
    )
    terminal_marker_exposures = json.dumps(compact, ensure_ascii=False).count(MARKER)
    behavior_correct = (
        status == expected["status"]
        and len(requests) == expected["scripted_decisions"]
        and effects == expected["effects"]
        and events.count("intent") == expected["intent_events"]
        and packet.get("reason") == expected["reason"]
    )
    actual_usage = (
        ZERO_USAGE
        if native_attempts == 0
        else {
            "requests": None,
            "models": {},
            "input_tokens": None,
            "output_tokens": None,
            "usage_complete": False,
        }
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": {
            **config,
            "marker_prefix_characters": len(MARKER),
            "payload_character_repetitions": repetitions,
            "frozen_monotonic": 100.0,
            "max_steps": 2,
            "timeout_seconds": 120,
        },
        "projected_context_sizes": sizes,
        "expected": expected,
        "result": {
            "status": status,
            "reason": packet.get("reason"),
            "context_budget": packet.get("context_budget"),
            "failure_metadata_correct": failure_metadata_correct,
            "success_metadata_correct": success_metadata_correct,
            "behavior_correct": behavior_correct,
            "scripted_decisions": len(requests),
            "effects": effects,
            "intent_events": events.count("intent"),
            "native_inference_attempts": native_attempts,
            "request_context_sizes": requests,
            "returned_call_telemetry": call_telemetry,
            "terminal_marker_exposures": terminal_marker_exposures,
            "reported_scripted_usage_complete": packet.get("telemetry", {}).get("usage_complete"),
        },
        "correct": behavior_correct
        and failure_metadata_correct
        and success_metadata_correct
        and terminal_marker_exposures == 0
        and native_attempts == 0,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(compact, ensure_ascii=False).encode()),
        "actual_model_usage": actual_usage,
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
        guard_hit = any(row["result"]["native_inference_attempts"] for row in group)
        summaries[arm] = {
            "runs": len(group),
            "correct": sum(row["correct"] for row in group),
            "behavior_correct": sum(row["result"]["behavior_correct"] for row in group),
            "failure_metadata_correct": sum(
                row["result"]["failure_metadata_correct"] for row in group
            ),
            "success_metadata_correct": sum(
                row["result"]["success_metadata_correct"] for row in group
            ),
            "statuses": {
                status: sum(row["result"]["status"] == status for row in group)
                for status in sorted({row["result"]["status"] for row in group})
            },
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "effects": sum(row["result"]["effects"] for row in group),
            "intent_events": sum(row["result"]["intent_events"] for row in group),
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
            ),
            "terminal_marker_exposures": sum(
                row["result"]["terminal_marker_exposures"] for row in group
            ),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "request_context_characters": sum(
                request["characters"]
                for row in group
                for request in row["result"]["request_context_sizes"]
            ),
            "request_context_utf8_bytes": sum(
                request["utf8_bytes"]
                for row in group
                for request in row["result"]["request_context_sizes"]
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
        for key in (
            "status",
            "reason",
            "scripted_decisions",
            "effects",
            "intent_events",
            "request_context_sizes",
        )
    )
    report = {
        "mode": "offline-synthetic-context-budget-diagnostics",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "behavior_parity": behavior_parity,
        "reproduction": "python benchmarks/context_budget.py --output local-results/context-budget-ab.json",
        "scope": "Fourteen fixed ASCII/Chinese/emoji shared-context fixtures, three paired repeats with alternating arm order. Custom policy, exact scalar payload sizes and a loop-only frozen clock make projection/tool/parameter thresholds deterministic. The 15,000 limit remains JSON characters from json.dumps(ensure_ascii=False) with default separators and rejects only greater values. Unicode contexts whose UTF-8 size exceeds 15,000 still admit when character count fits. Parameter excess occurs after a scripted tool choice but before intent/effect. Direct Engine.decide remains outside this loop limit. All decisions are scripted; native inference entrypoints are forbidden, actual model/UI/network calls zero unless the guard is hit.",
        "negative_results": "Fixed failure diagnostics and successful call counters add returned context and local measurement work. This is not a UTF-8 byte, token, candidate text, question, full provider prompt or direct Engine.decide budget. Direct decide still has upstream analysis-spec validation: the first synthetic smoke with 16,000 shared characters failed its 16,000-character full-spec cap after default questions were added; direct fixtures therefore use 15,001 shared characters to isolate the loop boundary. A custom policy omits ordinary production history and the frozen clock excludes wall-budget races. No truncation, context-quality improvement, model accuracy, speed or fee benefit is claimed. Static scalar context measurements are diagnostic evidence and do not authorize execution.",
        "cost_conversion": "Zero actual model usage only with no native guard attempts; a guard hit records unknown usage and fails the fixture. No tariff or savings assumed. Real whole-operation timing uses perf_counter and includes synthetic registration, payload/projection setup, loop admission, scripted decisions, tool effects and private journal serialization; excludes process/import setup and terminal-analysis/source-hashing. Frozen monotonic values stabilize only the synthetic remaining-time context and do not stand in for end-to-end timing. Returned context bytes exclude the local archive path and never include raw payloads; request metrics are shared-context scalar sizes, not provider prompt/token counts.",
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
