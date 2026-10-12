"""Offline paired pending-action identity on uncertain exits against exact v0.1.10."""

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
BASELINE = "c4486ed8cc3c82a00f421f3bac32653b814f2d40"
ACTION_ID = "synthetic_step"
INPUT_MARKER = "SYNTHETIC_INPUT_CONTEXT"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    **{
        f"{stage}_{usage}": {"stage": stage, "usage": usage}
        for stage in ("execute", "result_context", "observe", "verify")
        for usage in ("known", "unknown")
    },
    "pre_effect_bind_stop": {"stage": "bind_stop", "usage": "known"},
    "pre_effect_freshness_stop": {"stage": "freshness_stop", "usage": "unknown"},
    "pre_effect_freshness_exception": {"stage": "freshness_exception", "usage": "known"},
    "post_effect_ordinary_exception": {"stage": "ordinary_exception", "usage": "known"},
    "normal_done_known": {"stage": "done", "usage": "known"},
    "normal_done_unknown": {"stage": "done", "usage": "unknown"},
    "cleared_next_cycle_verify_stop": {"stage": "next_cycle_verify_stop", "usage": "known"},
    "second_effect_execute_unknown": {"stage": "second_effect_execute", "usage": "unknown"},
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def expected_result(config):
    stage = config["stage"]
    pre_effect = stage in {"bind_stop", "freshness_stop", "freshness_exception"}
    uncertain = stage in {"execute", "result_context", "observe", "verify", "ordinary_exception"}
    expected = {
        "status": "execution_uncertain"
        if uncertain
        else "done"
        if stage == "done"
        else "failed"
        if stage == "freshness_exception"
        else "needs_context",
        "complete": stage == "done",
        "reason": "synthetic_stop_after_effect:" + stage
        if stage in {"execute", "result_context", "observe", "verify"}
        else "synthetic_stop_before_effect"
        if stage in {"bind_stop", "freshness_stop"}
        else None,
        "error_type": "TimeoutError"
        if stage == "ordinary_exception"
        else "RuntimeError"
        if stage == "freshness_exception"
        else None,
        "steps": 0 if pre_effect or stage in {"execute", "ordinary_exception"} else 1,
        "effects": 0 if pre_effect else 1,
        "intent_events": 0 if pre_effect else 1,
        "executed_events": 0 if pre_effect or stage in {"execute", "ordinary_exception"} else 1,
        "action_id": ACTION_ID if uncertain or stage == "freshness_exception" else None,
        "scripted_decisions": 1,
        "scripted_requests_reported": 1,
        "scripted_usage_complete": config["usage"] == "known",
        "reported_scripted_usage": {"input_tokens": 7, "output_tokens": 2}
        if config["usage"] == "known"
        else None,
    }
    if stage == "next_cycle_verify_stop":
        expected.update(status="needs_context", reason="synthetic_stop_next_cycle", steps=1)
    elif stage == "second_effect_execute":
        expected.update(
            status="execution_uncertain",
            reason="synthetic_stop_after_second_effect",
            steps=1,
            effects=2,
            intent_events=2,
            executed_events=1,
            action_id="second_step",
            scripted_decisions=2,
            scripted_requests_reported=2,
        )
    return expected


def trial(name, source_dir):
    from apixly_jev_harness import Action, AgentLoop, Workflow, __version__
    from apixly_jev_harness import __file__ as runtime_file
    from apixly_jev_harness.engine import DecisionStop

    config = CASES[name]
    expected = expected_result(config)
    counts = {"effects": 0, "observations": 0, "verifications": 0, "native_inference_attempts": 0}
    requests = []

    def forbidden(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Offline identity fixtures must not invoke native inference")

    def decide(parts, goal, workers, spec):
        requests.append(
            {
                "selection_input_bytes": len(
                    json.dumps([parts, spec], ensure_ascii=False).encode()
                ),
                "shared_context_bytes": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False).encode()
                ),
                "shared_context_characters": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False)
                ),
            }
        )
        return {
            item["id"]: {"status": "OK", "decision": "MATCH" if index == 0 else "EXCLUDE"}
            for index, item in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": config["usage"] == "known",
            "usage": {"input_tokens": 7, "output_tokens": 2}
            if config["usage"] == "known"
            else None,
            "requests": 1,
            "models": {},
        }

    class SyntheticWorkflow(Workflow):
        def observe(self, ctx):
            counts["observations"] += 1
            if counts["observations"] == 2:
                if config["stage"] == "freshness_stop":
                    raise DecisionStop("needs_context", "synthetic_stop_before_effect")
                if config["stage"] == "freshness_exception":
                    raise RuntimeError("Synthetic observation failure")
            if counts["effects"] and config["stage"] == "observe":
                raise DecisionStop("needs_context", "synthetic_stop_after_effect:observe")
            if config["stage"] in {"next_cycle_verify_stop", "second_effect_execute"}:
                return {"count": counts["effects"]}
            return (
                {"done": bool(counts["effects"])} if config["stage"] == "done" else {"stable": True}
            )

        def verify(self, ctx, seen):
            counts["verifications"] += 1
            if counts["effects"] and config["stage"] == "verify":
                raise DecisionStop("needs_context", "synthetic_stop_after_effect:verify")
            if counts["effects"] and config["stage"] == "next_cycle_verify_stop":
                raise DecisionStop("needs_context", "synthetic_stop_next_cycle")
            return seen.get("done", False)

        def candidates(self, ctx, seen):
            action_id = (
                ("first_step" if not counts["effects"] else "second_step")
                if config["stage"] == "second_effect_execute"
                else ACTION_ID
            )
            return [Action(action_id, "Apply one synthetic effect", {"target": "synthetic-value"})]

        def bind(self, ctx, seen, action, choose):
            if config["stage"] == "bind_stop":
                raise DecisionStop("needs_context", "synthetic_stop_before_effect")
            return action

        def execute(self, ctx, action):
            counts["effects"] += 1
            if config["stage"] == "execute":
                raise DecisionStop("needs_context", "synthetic_stop_after_effect:execute")
            if config["stage"] == "ordinary_exception":
                raise TimeoutError("Synthetic execution failure")
            if config["stage"] == "second_effect_execute" and counts["effects"] == 2:
                raise DecisionStop("needs_context", "synthetic_stop_after_second_effect")
            return {"synthetic_effect": True}

        def result_context(self, ctx, action, result):
            if config["stage"] == "result_context":
                raise DecisionStop("needs_context", "synthetic_stop_after_effect:result_context")
            return {"effect_observed": True}

    started = time.perf_counter()
    workflow = SyntheticWorkflow()
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "run.jsonl"
        with (
            patch("apixly_jev_harness.backend.native_run", forbidden),
            patch("apixly_jev_harness.backend.provider_evaluate", forbidden),
            patch("apixly_jev_harness.engine.analysis.evaluate", decide),
            patch("apixly_jev_harness.engine.time", SimpleNamespace(monotonic=lambda: 100.0)),
        ):
            packet = AgentLoop().run(
                workflow,
                goal="Finish one synthetic effect",
                context={"scope": INPUT_MARKER},
                max_steps=2,
                timeout_seconds=120,
                archive=archive,
            )
        elapsed = time.perf_counter() - started
        journal = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
    compact = {key: value for key, value in packet.items() if key != "archive"}
    intents = [entry for entry in journal if entry["event"] == "intent"]
    telemetry = packet["telemetry"]
    result = {
        "status": packet["status"],
        "complete": packet["complete"],
        "reason": packet.get("reason"),
        "error_type": packet.get("error_type"),
        "steps": packet["steps"],
        "effects": counts["effects"],
        "intent_events": len(intents),
        "executed_events": sum(entry["event"] == "executed" for entry in journal),
        "action_id": packet.get("action_id"),
        "scripted_decisions": len(requests),
        "scripted_requests_reported": telemetry["requests"],
        "scripted_usage_complete": telemetry["usage_complete"],
        "reported_scripted_usage": telemetry["usage"],
    }
    behavior_keys = [key for key in expected if key != "action_id"]
    behavior_correct = all(result[key] == expected[key] for key in behavior_keys)
    identity_correct = result["action_id"] == expected["action_id"]
    terminal_matches_intent = (
        expected["status"] != "execution_uncertain"
        or result["action_id"] == intents[-1]["action_id"]
    )
    marker_exposures = json.dumps(compact, ensure_ascii=False).count(INPUT_MARKER)
    result.update(behavior_correct=behavior_correct, identity_correct=identity_correct)
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": {
            **config,
            "offered_action_ids": ["first_step", "second_step"]
            if config["stage"] == "second_effect_execute"
            else [ACTION_ID],
            "frozen_loop_monotonic": 100.0,
            "max_steps": 2,
            "timeout_seconds": 120,
        },
        "expected": expected,
        "result": {
            **result,
            "terminal_matches_durable_intent": terminal_matches_intent,
            "observations": counts["observations"],
            "verifications": counts["verifications"],
            "request_sizes": requests,
            "native_inference_attempts": counts["native_inference_attempts"],
            "raw_input_marker_exposures": marker_exposures,
        },
        "correct": behavior_correct
        and identity_correct
        and terminal_matches_intent
        and marker_exposures == 0
        and counts["native_inference_attempts"] == 0,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(compact, ensure_ascii=False).encode()),
        "actual_model_usage": ZERO_USAGE
        if counts["native_inference_attempts"] == 0
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
        guard_hit = any(row["result"]["native_inference_attempts"] for row in group)
        summaries[arm] = {
            "runs": len(group),
            "correct": sum(row["correct"] for row in group),
            "behavior_correct": sum(row["result"]["behavior_correct"] for row in group),
            "identity_correct": sum(row["result"]["identity_correct"] for row in group),
            "terminal_matches_durable_intent": sum(
                row["result"]["terminal_matches_durable_intent"] for row in group
            ),
            "uncertain_exits": sum(
                row["result"]["status"] == "execution_uncertain" for row in group
            ),
            "pre_effect_stops": sum(
                row["fixture"]["stage"] in {"bind_stop", "freshness_stop"} for row in group
            ),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "effects": sum(row["result"]["effects"] for row in group),
            "intent_events": sum(row["result"]["intent_events"] for row in group),
            "unknown_scripted_usage_rows": sum(
                not row["result"]["scripted_usage_complete"] for row in group
            ),
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
            ),
            "raw_input_marker_exposures": sum(
                row["result"]["raw_input_marker_exposures"] for row in group
            ),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
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
    parity_keys = [key for key in expected_result(CASES["execute_known"]) if key != "action_id"]
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
        "mode": "offline-synthetic-execution-identity",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "behavior_parity": behavior_parity,
        "reproduction": "python benchmarks/execution_identity.py --output local-results/execution-identity-ab.json",
        "scope": "Sixteen fixed synthetic workflows, three paired repeats with alternating arm order. Four post-effect DecisionStop stages are paired with known/unknown prior scripted usage. Controls cover pre-effect binding/freshness stops, existing ordinary exception identities before/after effects, verified done with known/unknown usage, a later-cycle stop after pending identity was cleared and a second distinct action whose current id must not be replaced by the first historical id. Selection is scripted; native inference entrypoints are forbidden and actual model/network/UI calls are zero if the guard is never hit. Durable local intent and independent synthetic effect counters establish which current action stopped. The verifier-stop fixture uses the unchanged-observation immediate verification path while execution is still pending.",
        "negative_results": "Adding a current action_id increases uncertain terminal output bytes and introduces local projection work. The id identifies the program's pending action, not proof of external completion, permission, rollback, safe retry or exactly-once behavior. Ordinary exceptions already carried pending ids, including a pre-effect failure; pre-effect DecisionStop controls still omit action_id. No semantic quality, real-world action reconciliation, speed or fee improvement is claimed. Unknown prior scripted usage remains unknown even when the terminal action is identified.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only with zero forbidden native attempts; a guard hit records unknown actual usage and fails the fixture. Scripted requests and reported scripted usage are separate from actual model usage. Real whole-operation timing uses perf_counter and includes synthetic registration, loop admission, scripted selection, trusted callbacks, effect markers and private journal serialization; excludes process/import setup and terminal analysis/source hashes. A loop-only frozen monotonic clock stabilizes synthetic request budgets and never substitutes for whole-operation timing. Returned context bytes exclude the local archive path; scalar request sizes include the shared context and selection envelope, not provider tokens.",
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
