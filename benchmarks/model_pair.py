"""Opt-in, billable pair of two versioned Jev models on unchanged harness code.

The arms differ only in the requested model. Each repeat runs the six next-tool cases in
both candidate orders and a two-stage counter task (a tool, then a parameter with a better
and a worse offered value), alternating which model goes first. No calibration claim.
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

from _private_files import secure_fs as _secure_fs
from tool_choice import CASES, should_stop, trial

MODELS = ("jev-1.13.0", "jev-1.14.0")
GOAL = "Reach the target value 3 with the fewest increment calls"


def _gate_view(selection):
    probabilities = sorted((selection or {}).get("probabilities", {}).values(), reverse=True)
    return {
        "choice": (selection or {}).get("choice"),
        "top_probability": probabilities[0] if probabilities else None,
        "margin": probabilities[0] - (probabilities[1] if len(probabilities) > 1 else 0)
        if probabilities
        else None,
        "confidence": (selection or {}).get("confidence"),
    }


def counter_trial(model, archive):
    from apixly_jev_harness import AgentLoop, Parameter, Task

    state, amounts = {"value": 0}, []
    task = Task(
        observe=lambda ctx: {"value": state["value"], "target": 3},
        verify=lambda ctx, seen: seen["value"] == seen["target"],
    )

    @task.tool(
        "Increase the value toward target without exceeding it",
        parameters={
            "amount": Parameter(
                "Choose the largest allowed increment to reach target with the fewest tool calls",
                lambda ctx, seen: [v for v in (1, 2) if v <= seen["target"] - seen["value"]],
            )
        },
        result_context=lambda result: result,
    )
    def increment(amount):
        amounts.append(amount)
        state["value"] += amount
        return {"value": state["value"]}

    started = time.perf_counter()
    result = AgentLoop(model=model).run(
        task, goal=GOAL, max_steps=4, timeout_seconds=120, archive=archive
    )
    calls = result["telemetry"]["calls"]
    return {
        "probe": "counter",
        "model_requested": model,
        "status": result["status"],
        "complete": result["complete"],
        "steps": result["steps"],
        "amounts": amounts,
        "fewest_calls": result["complete"] and amounts == [2, 1],
        "calls": [
            {
                "stage": call.get("stage"),
                "model_resolved": call.get("model_resolved"),
                **_gate_view(call.get("selection")),
                "probabilities": (call.get("selection") or {}).get("probabilities"),
                "review_reasons": call.get("selection_review_reasons", []),
                "provider_failure_codes": call.get("provider_failure_codes", []),
                "usage": call.get("usage"),
            }
            for call in calls
        ],
        "usage_complete": bool(result["telemetry"].get("usage_complete")),
        "whole_operation_seconds": time.perf_counter() - started,
    }


def counter_should_stop(row):
    return row["status"] in ("failed", "execution_uncertain") or any(
        call["provider_failure_codes"] for call in row["calls"]
    )


def summarize(rows, models):
    summaries = {}
    for model in models:
        tools = [r for r in rows if r["probe"] == "tool_choice" and r["model_requested"] == model]
        counters = [r for r in rows if r["probe"] == "counter" and r["model_requested"] == model]
        gates = [_gate_view(r["selection"]) for r in tools] + [
            call for r in counters for call in r["calls"]
        ]
        usage, reasons = {}, {}
        for r in tools:
            for name, counts in r["actual_model_usage"]["models"].items():
                usage.setdefault(name, {"input_tokens": 0, "output_tokens": 0})
                for key in ("input_tokens", "output_tokens"):
                    usage[name][key] += counts[key]
            for reason in r["review_reasons"]:
                reasons[reason["reason"]] = reasons.get(reason["reason"], 0) + 1
        for r in counters:
            for call in r["calls"]:
                if call["model_resolved"] and call["usage"]:
                    usage.setdefault(
                        call["model_resolved"], {"input_tokens": 0, "output_tokens": 0}
                    )
                    for key in ("input_tokens", "output_tokens"):
                        usage[call["model_resolved"]][key] += call["usage"][key]
                for reason in call["review_reasons"]:
                    reasons[reason["reason"]] = reasons.get(reason["reason"], 0) + 1
        tops = [g["top_probability"] for g in gates if g["top_probability"] is not None]
        margins = [g["margin"] for g in gates if g["margin"] is not None]
        summaries[model] = {
            "tool_choice": {
                "runs": len(tools),
                "raw_choice_expected": sum(r["raw_choice_expected"] for r in tools),
                "admitted_expected": sum(r["admitted_expected"] for r in tools),
                "statuses": {
                    s: sum(r["status"] == s for r in tools) for s in {r["status"] for r in tools}
                },
                "median_whole_operation_seconds": statistics.median(
                    r["whole_operation_seconds"] for r in tools
                )
                if tools
                else None,
            },
            "counter": {
                "runs": len(counters),
                "complete": sum(r["complete"] for r in counters),
                "fewest_calls": sum(r["fewest_calls"] for r in counters),
                "decisions": sum(len(r["calls"]) for r in counters),
            },
            "gates": {
                "decisions": len(gates),
                "min_top_probability": min(tops) if tops else None,
                "min_margin": min(margins) if margins else None,
                "review_reasons": reasons,
            },
            "resolved_models": sorted(
                {r["reported_model_resolved"] for r in tools}
                | {c["model_resolved"] for r in counters for c in r["calls"]},
                key=str,
            ),
            "known_reported_usage_by_model": usage,
            "usage_complete": all(r["actual_model_usage"]["usage_complete"] for r in tools)
            and all(r["usage_complete"] for r in counters),
        }
    return summaries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True, help="Billable inference")
    parser.add_argument("--output", required=True)
    parser.add_argument("--models", nargs=2, default=list(MODELS))
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args(argv)
    from apixly_jev_harness.backend import validate_model

    models = [validate_model(model) for model in args.models]
    if len(set(models)) != 2 or args.repeats < 1:
        parser.error("two_distinct_versioned_models_and_positive_repeats_required")
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.close(_secure_fs.open_private_file(path, "x"))  # Send-once reservation.
    report = {
        "mode": "live-paired-models",
        "status": "reserved",
        "models": models,
        "repeats": args.repeats,
        "planned_probes": args.repeats * (len(cases) * 2 + 1) * 2,
        "reproduction": "python benchmarks/model_pair.py --live --output local-results/model-pair.json",
        "scope": "Same harness code and floors; arms differ only in the requested model. Six development next-tool cases in both orders plus one two-stage counter task per repeat, model order alternated. Synthetic, saturated on the earlier model; no held-out, calibration or browser/desktop claim.",
        "cost_conversion": "Actual resolved model and provider token usage, not invoice amounts. Unknown attempts remain unknown, not zero.",
        "rows": [],
        "pending": None,
    }

    def checkpoint():
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".model-pair-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    started = time.perf_counter()
    checkpoint()
    with tempfile.TemporaryDirectory() as directory:
        root, index, stop = Path(directory), 0, False
        plan = []
        for repeat in range(args.repeats):
            for case_index, case in enumerate(cases):
                for reverse in (False, True):
                    order = models if (repeat + case_index + reverse) % 2 == 0 else models[::-1]
                    plan += [("tool_choice", repeat, case, reverse, m) for m in order]
            plan += [
                ("counter", repeat, None, False, m)
                for m in (models if repeat % 2 == 0 else models[::-1])
            ]
        for probe, repeat, case, reverse, model in plan:
            index += 1
            archive = root / f"{index}.jsonl"
            report.update(
                status="running",
                pending={"probe": probe, "repeat": repeat, "model": model, "reverse": reverse},
            )
            checkpoint()  # Reserve before any potentially billable inference.
            if probe == "tool_choice":
                row = trial(case, reverse, archive, True, model=model)
                row.pop("requests")  # Fixture-derived request bodies; keep the receipts compact.
                row.update(probe="tool_choice", model_requested=model, repeat=repeat)
                stop = should_stop(row)
            else:
                row = {**counter_trial(model, archive), "repeat": repeat}
                stop = counter_should_stop(row)
            report["rows"].append(row)
            report["pending"] = None
            checkpoint()
            print(json.dumps({"probe": probe, "model": model, "status": row["status"]}), flush=True)
            if stop:
                report["status"] = "stopped_after_runtime_or_provider_failure"
                break
        else:
            report["status"] = "completed"
    report["whole_benchmark_seconds"] = time.perf_counter() - started
    report["summary"] = summarize(report["rows"], models)
    checkpoint()
    print(json.dumps(report["summary"]))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
