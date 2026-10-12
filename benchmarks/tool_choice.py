"""Paired next-tool probes across task families; offline by default, live is billable."""

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

from _private_files import secure_fs as _secure_fs
from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "b51614e8acfbac5a64bbad3c7da34a5a3698fa27"
CASES = ROOT / "benchmarks/tool-choice-cases.json"


def trial(case, reverse, archive, live):
    from apixly_jev_harness import Action, AgentLoop, Workflow, __version__, backend
    from apixly_jev_harness.context import ContextPolicy
    from apixly_jev_harness.engine import DecisionStop

    candidates = list(reversed(case["candidates"])) if reverse else case["candidates"]
    selected = []
    requests = []

    class ProbeContext(ContextPolicy):
        def build(self, ctx, observation):
            projected = super().build(ctx, observation)
            # Caller-owned projection for frozen synthetic history, not implicit host memory.
            projected["history"] = copy.deepcopy(case["history"])
            return projected

    class Probe(Workflow):
        def observe(self, ctx):
            return copy.deepcopy(case["observation"])

        def verify(self, ctx, state):
            return False  # A next-step selection never proves this complete goal.

        def candidates(self, ctx, state):
            return [Action(row["id"], row["description"]) for row in candidates]

        def bind(self, ctx, state, action, choose):
            selected.append(action.id)
            raise DecisionStop("max_steps", "decision_probe_no_execution")

        def execute(self, ctx, action):
            raise AssertionError("Decision probe must stop before any tool effect")

    original = backend.provider_evaluate

    def evaluate(body, client, cache=None):
        requests.append(copy.deepcopy(body))
        if live:
            return original(body, client, cache=None)
        answers = {}
        for name, question in body["questions"].items():
            options = question["criteria"]
            choice = next(
                key
                for key, value in options.items()
                if isinstance(value, dict)
                and value.get("properties", {}).get("id") == case["expected_id"]
            )
            answers[name] = {
                "type": "choice",
                "choice": choice,
                "confidence": 1.0,
                "probabilities": {key: float(key == choice) for key in options},
            }
        return {
            "ok": True,
            "model": "jev-synthetic-protocol",
            "answers": answers,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "usage_complete": True,
        }

    started = time.perf_counter()
    with patch("apixly_jev_harness.backend.provider_evaluate", evaluate):
        result = AgentLoop().run(
            Probe(),
            goal=case["goal"],
            context=case["facts"],
            context_policy=ProbeContext(),
            max_steps=1,
            archive=archive,
        )
    elapsed = time.perf_counter() - started
    events = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
    effects = sum(event["event"] in ("intent", "executed") for event in events)
    calls = result["telemetry"]["calls"]
    meta = calls[0] if calls else {}
    raw_choice = meta.get("selection", {}).get("choice")
    offered = [row["id"] for row in candidates] + [
        "__loop_done",
        "__loop_blocked",
        "__loop_needs_context",
    ]
    raw_id = None
    if isinstance(raw_choice, str) and raw_choice.startswith("c") and raw_choice[1:].isdigit():
        index = int(raw_choice[1:])
        raw_id = offered[index] if index < len(offered) else None
    body = requests[0] if requests else {}
    context = body.get("state", {}).get("context", {})
    instructions = " ".join(q.get("instructions", "") for q in body.get("questions", {}).values())
    assumed_form = "requested fields and controls" in body.get("state", {}).get("task", "")
    complete_usage = bool(result["telemetry"].get("usage_complete"))
    known_usage = meta.get("usage") or meta.get("reported_usage")
    actual_usage = {
        "network_attempts": meta.get("transport", {}).get("requests") if live else 0,
        "models": {meta["model_resolved"]: known_usage}
        if live and meta.get("model_resolved") and isinstance(known_usage, dict)
        else {},
        "usage_complete": complete_usage if live else True,
        "usage": result["telemetry"].get("usage")
        if live
        else {"input_tokens": 0, "output_tokens": 0},
    }
    return {
        "case": case["id"],
        "family": case["family"],
        "order": "reverse" if reverse else "original",
        "runtime_version": __version__,
        "expected_id": case["expected_id"],
        "raw_choice": raw_choice,
        "raw_selected_id": raw_id,
        "raw_choice_expected": raw_id == case["expected_id"],
        "admitted_id": selected[0] if selected else None,
        "admitted_expected": selected == [case["expected_id"]],
        "status": result["status"],
        "reason": result.get("reason"),
        "diagnostic": result.get("diagnostic"),
        "review_reasons": meta.get("selection_review_reasons", []),
        "provider_failure_codes": meta.get("provider_failure_codes", []),
        "reported_model_resolved": meta.get("model_resolved"),
        "protocol": {
            "decision_stage": context.get("decision_stage"),
            "next_step_question": "NEXT step" in instructions,
            "assumed_form_rule": assumed_form,
            "scope_correct": context.get("decision_stage") == "tool_selection"
            and "NEXT step" in instructions
            and not assumed_form,
        },
        "intent_or_effect_events": effects,
        "whole_operation_seconds": elapsed,
        "request_bytes": sum(len(json.dumps(request).encode()) for request in requests),
        "returned_context_bytes": len(json.dumps(result).encode()),
        "actual_model_usage": actual_usage,
        "requests": requests,
    }


def should_stop(row):
    return (
        bool(row["provider_failure_codes"])
        or row["intent_or_effect_events"] != 0
        or row["status"] not in {"max_steps", "needs_review", "blocked", "needs_context"}
    )


def summarize(rows):
    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        models = {}
        for row in group:
            for model, usage in row["actual_model_usage"]["models"].items():
                counts = models.setdefault(model, {"input_tokens": 0, "output_tokens": 0})
                for key in counts:
                    counts[key] += usage[key]
        summaries[arm] = {
            "runs": len(group),
            "raw_choice_expected": sum(row["raw_choice_expected"] for row in group),
            "admitted_expected": sum(row["admitted_expected"] for row in group),
            "scope_correct": sum(row["protocol"]["scope_correct"] for row in group),
            "intent_or_effect_events": sum(row["intent_or_effect_events"] for row in group),
            "statuses": {
                status: sum(row["status"] == status for row in group)
                for status in sorted({row["status"] for row in group})
            },
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            )
            if group
            else None,
            "total_request_bytes": sum(row["request_bytes"] for row in group),
            "total_returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "actual_network_attempts": sum(
                row["actual_model_usage"]["network_attempts"] for row in group
            )
            if all(row["actual_model_usage"]["network_attempts"] is not None for row in group)
            else None,
            "known_network_attempts": sum(
                row["actual_model_usage"]["network_attempts"] or 0 for row in group
            ),
            "unknown_network_attempt_rows": sum(
                row["actual_model_usage"]["network_attempts"] is None for row in group
            ),
            "known_reported_usage_by_model": models,
            "usage_complete": all(row["actual_model_usage"]["usage_complete"] for row in group),
        }
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument(
        "--live", action="store_true", help="Opt-in: 24 synthetic decisions, billable"
    )
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    parser.add_argument("--archive", help=argparse.SUPPRESS)
    parser.add_argument("--result-file", help=argparse.SUPPRESS)
    parser.add_argument("--reverse", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    fixture = json.loads(CASES.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    if len(cases) != 6 or any(len(case["candidates"]) != 3 for case in cases):
        parser.error("bounded_fixture_requires_six_cases_with_three_candidates")
    if args.worker:
        sys.path.insert(0, args.source_dir)
        case = next(case for case in cases if case["id"] == args.worker)
        result = trial(case, args.reverse, Path(args.archive), args.live)
        fd = _secure_fs.open_private_file(args.result_file, "x")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"worker_completed": case["id"]}))
        return 0
    if not args.output:
        parser.error("--output is required")
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = _secure_fs.open_private_file(path, "x")
    os.close(fd)
    started = time.perf_counter()
    report = {
        "mode": "live-synthetic-next-decision" if args.live else "offline-scripted-protocol",
        "status": "reserved",
        "fixture": fixture,
        "candidate_source_sha256": {
            str(source.relative_to(ROOT)): hashlib.sha256(source.read_bytes()).hexdigest()
            for source in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "reproduction": "python benchmarks/tool_choice.py --output local-results/tool-choice.json [--live]",
        "planned_decisions": 24,
        "rows": [],
        "pending": None,
        "scope": "Six development cases, two candidate permutations, paired runtime arms. Each probe deliberately stops before intent/execution after one tool choice. Native Choice selection is not permission or full goal completion. Offline answers are scripted and do not measure semantic quality. Live failures and review gates are retained; no repeat calibration or held-out generalization claim.",
        "negative_results": "The loop-specific question adds input context. This trial does not prove complete task/browser/desktop execution or host-AI recovery; candidate descriptions have unusually explicit preconditions.",
        "cost_conversion": "Report actual resolved model and provider token usage, not invoice amounts. At a caller-supplied input rate R USD/million, known input cost is known_input_tokens * R / 1000000; no current tariff is assumed. Incomplete/unknown attempts remain unknown, not zero. The pinned provider may retry only explicit 429/503/529 up to three attempts per logical decision; the harness adds no retries.",
    }
    try:

        def checkpoint():
            temporary_fd, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".tool-choice-")
            try:
                with os.fdopen(temporary_fd, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(report, stream, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, path)
                if os.name == "posix":
                    parent_fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)

        checkpoint()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report["baseline_commit"] = snapshot(args.baseline_ref, root / "baseline")
            sources = {"baseline": root / "baseline/src", "candidate": ROOT / "src"}
            stop = False
            for case_index, case in enumerate(cases):
                for reverse in (False, True):
                    arms = (
                        ("baseline", "candidate")
                        if (case_index + reverse) % 2 == 0
                        else ("candidate", "baseline")
                    )
                    for arm in arms:
                        report["status"] = "running"
                        report["pending"] = {"case": case["id"], "reverse": reverse, "arm": arm}
                        checkpoint()  # Reserve before any potentially billable inference.
                        command = [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--worker",
                            case["id"],
                            "--source-dir",
                            str(sources[arm]),
                            "--archive",
                            str(root / f"{case_index}-{reverse}-{arm}.jsonl"),
                            "--result-file",
                            str(root / f"{case_index}-{reverse}-{arm}.result.json"),
                        ]
                        if reverse:
                            command.append("--reverse")
                        if args.live:
                            command.append("--live")
                        env = (
                            os.environ.copy()
                            if args.live
                            else {
                                key: value
                                for key, value in os.environ.items()
                                if not key.startswith("TYPESAFE_")
                            }
                        )
                        try:
                            subprocess.run(
                                command, env=env, text=True, check=True, capture_output=True
                            )
                            row = json.loads(
                                (root / f"{case_index}-{reverse}-{arm}.result.json").read_text(
                                    encoding="utf-8"
                                )
                            )
                        except Exception as error:
                            report.update(
                                status="interrupted_outcome_unknown",
                                error_type=type(error).__name__,
                            )
                            checkpoint()
                            raise
                        row["arm"] = arm
                        report["rows"].append(row)
                        report["pending"] = None
                        checkpoint()
                        if args.live and should_stop(row):
                            report["status"] = "stopped_after_runtime_or_provider_failure"
                            stop = True
                            break
                    if stop:
                        break
                if stop:
                    break
                print(
                    json.dumps(
                        {"case_completed": case["id"], "decisions_recorded": len(report["rows"])}
                    ),
                    flush=True,
                )
            if not stop:
                report["status"] = "completed"
        report["whole_benchmark_seconds"] = time.perf_counter() - started
        report["summary"] = summarize(report["rows"])
        checkpoint()
    except Exception:
        # Existing output is a send-once reservation; never restart it automatically.
        raise
    print(json.dumps(report["summary"]))
    return (
        0
        if report["status"] == "completed"
        and all(row["intent_or_effect_events"] == 0 for row in report["rows"])
        and all(
            row["protocol"]["scope_correct"] and (args.live or row["admitted_expected"])
            for row in report["rows"]
            if row["arm"] == "candidate"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
