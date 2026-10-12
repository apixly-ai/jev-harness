"""Offline paired post-verification wall-budget admission against exact v0.1.15."""

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
BASELINE = "30524752a83438decb431b36267ac81378f0bcb8"
TIMEOUT = 10.0
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "slow_false_empty": {"kind": "empty", "group": "budget_fix", "verify_time": 11.0},
    "slow_false_raises": {"kind": "raises", "group": "budget_fix", "verify_time": 11.0},
    "slow_false_task_dynamic": {"kind": "task", "group": "budget_fix", "verify_time": 11.0},
    "slow_false_generator": {"kind": "generator", "group": "budget_fix", "verify_time": 11.0},
    "prior_effect_unknown_slow_false": {
        "kind": "after_effect_empty",
        "group": "budget_fix",
        "verify_time": 11.0,
        "unknown_usage": True,
    },
    "false_exact_timeout_boundary": {
        "kind": "nonempty",
        "group": "budget_fix",
        "verify_time": TIMEOUT,
    },
    "initially_expired": {"kind": "initial_expired", "group": "compatibility"},
    "fast_false_normal_tool": {"kind": "normal", "group": "compatibility"},
    "late_true_keeps_completion": {
        "kind": "late_true",
        "group": "compatibility",
        "verify_time": 11.0,
    },
    "max_steps_precedes_new_guard": {
        "kind": "max_steps",
        "group": "compatibility",
        "verify_time": 11.0,
    },
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def trial(name, source_dir):
    from apixly_jev_harness import Action, AgentLoop, Parameter, Task, Workflow, __version__
    from apixly_jev_harness import __file__ as runtime_file

    config, kind = CASES[name], CASES[name]["kind"]
    counts = {
        "candidate_entries": 0,
        "collector_body_calls": 0,
        "provider_calls": 0,
        "generator_yields": 0,
        "effects": 0,
        "verify_calls": 0,
        "observe_calls": 0,
        "native_inference_attempts": 0,
        "real_network_attempts": 0,
    }
    trace, requests = [], []
    clock = {"now": 0.0}

    def record(callback, **extra):
        trace.append(
            {
                "callback": callback,
                "synthetic_time": clock["now"],
                "effects": counts["effects"],
                **extra,
            }
        )

    def observe_callback(ctx):
        counts["observe_calls"] += 1
        if kind == "initial_expired":
            clock["now"] = TIMEOUT + 1
        record("observe")
        return {"value": counts["effects"], "ready": kind == "late_true"}

    def verify_callback(ctx, seen):
        counts["verify_calls"] += 1
        if kind == "late_true":
            clock["now"] = config["verify_time"]
            matched = seen["ready"]
        elif kind == "normal":
            matched = seen["value"] >= 1
        elif kind in {"after_effect_empty", "max_steps"}:
            if counts["effects"]:
                clock["now"] = config["verify_time"]
            matched = seen["value"] >= 2
        else:
            clock["now"] = config.get("verify_time", clock["now"])
            matched = False
        record("verify", matched=matched)
        return matched

    class SyntheticWorkflow(Workflow):
        observe = staticmethod(observe_callback)
        verify = staticmethod(verify_callback)

        def candidates(self, ctx, seen):
            counts["candidate_entries"] += 1
            counts["collector_body_calls"] += 1
            record("candidates")
            if kind == "raises":
                raise RuntimeError("Fixed synthetic acquisition failure")
            if kind == "empty" or kind == "after_effect_empty" and counts["effects"]:
                return []
            return [Action("apply", "Advance the synthetic observation", {"amount": 1})]

        def execute(self, ctx, action):
            counts["effects"] += 1
            record("execute")
            return {"applied": True}

    class GeneratorWorkflow(SyntheticWorkflow):
        def candidates(self, ctx, seen):
            counts["candidate_entries"] += 1
            counts["collector_body_calls"] += 1
            record("generator_start")
            counts["generator_yields"] += 1
            yield Action("apply", "Advance the synthetic observation", {"amount": 1})

    class TracedTask(Task):
        def candidates(self, ctx, seen):
            counts["candidate_entries"] += 1
            record("task_candidates")
            return super().candidates(ctx, seen)

    def provider(ctx, seen):
        counts["provider_calls"] += 1
        counts["collector_body_calls"] += 1
        record("provider")
        return ["synthetic-record", "other-record"]

    workflow = GeneratorWorkflow() if kind == "generator" else SyntheticWorkflow()
    if kind == "task":
        workflow = TracedTask(observe=observe_callback, verify=verify_callback)

        @workflow.tool(
            "Process one synthetic record",
            parameters={"record": Parameter("Observed record", provider)},
        )
        def apply(record):
            counts["effects"] += 1

    def forbid_native(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Budget fixtures prohibit native inference")

    def forbid_network(*args, **kwargs):
        counts["real_network_attempts"] += 1
        raise AssertionError("Budget fixtures prohibit real HTTP transport")

    def decide(parts, goal, workers, spec):
        requests.append(
            {
                "selection_input_bytes": len(
                    json.dumps([parts, spec], ensure_ascii=False).encode()
                ),
                "shared_context_bytes": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False).encode()
                ),
            }
        )
        record("scripted_selection")
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": not config.get("unknown_usage", False),
            "usage": None
            if config.get("unknown_usage")
            else {"input_tokens": 7, "output_tokens": 2},
            "requests": 1,
            "models": {},
        }

    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "run.jsonl"
        with (
            patch("apixly_jev_harness.backend.native_run", forbid_native),
            patch("apixly_jev_harness.backend.provider_evaluate", forbid_native),
            patch("apixly_jev_harness.engine.analysis.evaluate", decide),
            patch(
                "apixly_jev_harness.engine.time", SimpleNamespace(monotonic=lambda: clock["now"])
            ),
            patch("httpx.HTTPTransport.handle_request", forbid_network),
        ):
            packet = AgentLoop().run(
                workflow,
                goal="Reach the verified synthetic observation",
                timeout_seconds=TIMEOUT,
                max_steps=1 if kind == "max_steps" else 2,
                archive=archive,
            )
        elapsed = time.perf_counter() - started
        journal = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
    compact = {key: value for key, value in packet.items() if key != "archive"}
    effects = 1 if kind in {"normal", "max_steps", "after_effect_empty"} else 0
    expected_status = (
        "done"
        if kind in {"normal", "late_true"}
        else "max_steps"
        if kind == "max_steps"
        else "budget_exceeded"
    )
    expected_candidates = 1 if effects else 0
    expected_usage_complete = not config.get("unknown_usage", False)
    expected_usage = (
        None
        if not expected_usage_complete
        else {"input_tokens": effects * 7, "output_tokens": effects * 2}
    )
    expected = {
        "status": expected_status,
        "candidate_entries": expected_candidates,
        "collector_body_calls": expected_candidates,
        "provider_calls": 0,
        "generator_yields": 0,
        "effects": effects,
        "steps": effects,
        "scripted_decisions": effects,
        "usage_complete": expected_usage_complete,
        "reported_scripted_usage": expected_usage,
    }
    result = {
        "status": packet["status"],
        "complete": packet["complete"],
        "reason": packet.get("reason"),
        "error_type": packet.get("error_type"),
        "candidate_entries": counts["candidate_entries"],
        "collector_body_calls": counts["collector_body_calls"],
        "provider_calls": counts["provider_calls"],
        "generator_yields": counts["generator_yields"],
        "effects": counts["effects"],
        "steps": packet["steps"],
        "intent_events": sum(entry["event"] == "intent" for entry in journal),
        "scripted_decisions": len(requests),
        "usage_complete": packet["telemetry"]["usage_complete"],
        "reported_scripted_usage": packet["telemetry"]["usage"],
        "verify_calls": counts["verify_calls"],
        "observe_calls": counts["observe_calls"],
        "synthetic_elapsed_seconds": packet["elapsed_seconds"],
        "synthetic_clock_final": clock["now"],
        "callback_trace": trace,
        "journal_events": [entry["event"] for entry in journal],
        "journal_candidate_events": sum(entry["event"] == "candidates" for entry in journal),
        "request_sizes": requests,
        "native_inference_attempts": counts["native_inference_attempts"],
        "real_network_attempts": counts["real_network_attempts"],
    }
    correct = (
        all(result[key] == value for key, value in expected.items())
        and result["intent_events"] == effects
        and counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
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
            "timeout_seconds": TIMEOUT,
            "max_steps": 1 if kind == "max_steps" else 2,
            "clock_advance": "explicit synthetic callback transition; no sleep",
        },
        "expected": expected,
        "result": result,
        "correct": correct,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(compact, ensure_ascii=False).encode()),
        "actual_model_usage": ZERO_USAGE
        if counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
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
        guard_hit = any(
            row["result"]["native_inference_attempts"] or row["result"]["real_network_attempts"]
            for row in group
        )
        summaries[arm] = {
            "runs": len(group),
            "correct": sum(row["correct"] for row in group),
            "groups": {
                kind: {
                    "runs": sum(row["fixture"]["group"] == kind for row in group),
                    "correct": sum(
                        row["correct"] and row["fixture"]["group"] == kind for row in group
                    ),
                }
                for kind in ("budget_fix", "compatibility")
            },
            "statuses": {
                status: sum(row["result"]["status"] == status for row in group)
                for status in sorted({row["result"]["status"] for row in group})
            },
            "candidate_entries": sum(row["result"]["candidate_entries"] for row in group),
            "collector_body_calls": sum(row["result"]["collector_body_calls"] for row in group),
            "provider_calls": sum(row["result"]["provider_calls"] for row in group),
            "generator_yields": sum(row["result"]["generator_yields"] for row in group),
            "effects": sum(row["result"]["effects"] for row in group),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "unknown_scripted_usage_rows": sum(
                row["result"]["usage_complete"] is False for row in group
            ),
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
            ),
            "real_network_attempts": sum(row["result"]["real_network_attempts"] for row in group),
            "selection_input_bytes": sum(
                request["selection_input_bytes"]
                for row in group
                for request in row["result"]["request_sizes"]
            ),
            "shared_context_bytes": sum(
                request["shared_context_bytes"]
                for row in group
                for request in row["result"]["request_sizes"]
            ),
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
        "reason",
        "error_type",
        "candidate_entries",
        "collector_body_calls",
        "provider_calls",
        "generator_yields",
        "effects",
        "steps",
        "intent_events",
        "scripted_decisions",
        "usage_complete",
        "reported_scripted_usage",
        "verify_calls",
        "observe_calls",
        "synthetic_elapsed_seconds",
        "callback_trace",
        "journal_events",
        "request_sizes",
    )
    compatibility_parity = all(
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
        for case, config in CASES.items()
        if config["group"] == "compatibility"
        for repeat in (1, 2, 3)
        for key in parity_keys
    )
    report = {
        "mode": "offline-synthetic-candidate-budget",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "compatibility_parity": compatibility_parity,
        "reproduction": "python benchmarks/candidate_budget.py --output local-results/candidate-budget-ab.json",
        "scope": "Ten fixed synthetic Task/Workflow/Engine fixtures, three paired repeats with alternating arm order. An explicit callback-driven monotonic clock, never sleep, models false verification reaching/passing the ten-second budget before candidate collection. Empty, raising, Task dynamic-provider and generator collectors prove collection does not begin after known exhaustion; one completed prior effect preserves steps and unknown scripted usage. Controls preserve initial expiry, ordinary fast progression, late successful verification, max-step precedence and the exact >= timeout boundary. Callback traces and journal event subsequences preserve baseline failures without raw input/body details. Selection is scripted and native inference/real HTTPTransport forbidden; actual model/network/UI calls zero if guards stay zero.",
        "negative_results": "The new guard changes terminal phase: blocked/no-candidates or a collector failure becomes budget_exceeded because that downstream callback never ran. Return bytes and event sequences therefore can increase/decrease without quality or performance meaning. Prior effects and unknown usage are retained; a late true verifier can still complete and max_steps still wins after false verification at that existing boundary. This remains a cooperative between-callback budget, not a hard deadline, callback cancellation, rollback, safe retry or a guarantee against a callback's own I/O. No AI quality, speed or fee gain is claimed.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only when both guards remain zero; guard hits record unknown actual usage and fail fixtures. Scripted usage is separate from actual usage. Real perf_counter timing includes run admission, trusted callbacks, optional scripted decision/effect and private journal flush/fsync; excludes imports, synthetic clock/workflow setup and terminal analysis/source hashing. The synthetic clock only triggers budget transitions and never represents measured latency. Returned bytes omit local archive paths; scalar input/context sizes are not provider-token counts.",
        "summary": summaries,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"compatibility_parity": compatibility_parity, "summary": summaries}))
    return (
        0
        if compatibility_parity and all(row["correct"] for row in rows if row["arm"] == "candidate")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
