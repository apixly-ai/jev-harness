"""Offline A/B against the published runtime: evidence progress and completion guards."""

import argparse
import hashlib
import io
import json
import os
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "e00bb1c1c6e063030446e7e795d33cc371f21032"
SCENARIOS = {
    "read_then_act": {"status": "done", "effects": 2},
    "different_objects_same_result": {"status": "done", "effects": 2},
    "duplicate_query": {"status": "blocked", "effects": 1},
    "duplicate_known_effect": {"status": "blocked", "effects": 1},
    "unadmitted_result": {"status": "blocked", "effects": 1},
    "empty_verifier": {"status": "invalid_configuration", "effects": 0},
    "missing_is_not_null": {"status": "blocked", "effects": 1},
}


def trial(scenario, archive):
    from apixly_jev_harness import AgentLoop, Option, Parameter, Task, __version__, verify_state

    requests = []
    effects = []
    private_marker = "SYNTHETIC_UNADMITTED_PAYLOAD"
    state = {"resolved": False}

    def decide(parts, goal, workers, spec):
        requests.append(len(json.dumps([parts, spec], sort_keys=True).encode()))
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, p in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "requests": 1,
            "models": {},
        }

    started = time.perf_counter()
    with patch("apixly_jev_harness.engine.analysis.evaluate", decide):
        try:
            if scenario == "empty_verifier":
                verifier = verify_state()
            elif scenario == "missing_is_not_null":
                state = {"controls": [{"label": "Name"}]}
                verifier = verify_state(controls=[{"label": "Name", "value": None}])
            elif scenario == "different_objects_same_result":

                def verifier(ctx, seen):
                    return len(ctx.results) == 2

            else:

                def verifier(ctx, seen):
                    return seen["resolved"]

            task = Task(
                observe=lambda ctx: state.copy(),
                verify=verifier,
                authorize=lambda ctx, action: True,
            )

            if scenario == "read_then_act":

                @task.tool(
                    "Inspect evidence",
                    available=lambda ctx, seen: not ctx.results,
                    result_context=lambda result: result,
                )
                def read():
                    effects.append("read")
                    return {"finding": "Inspect correlated logs next"}

                @task.tool("Inspect correlated logs", available=lambda ctx, seen: bool(ctx.results))
                def act():
                    effects.append("act")
                    state["resolved"] = True

            elif scenario == "different_objects_same_result":

                @task.tool(
                    "Inspect next object",
                    parameters={
                        "target": Parameter(
                            "Next unread object",
                            lambda ctx, seen: [
                                Option(str(len(ctx.results)), "Next object", len(ctx.results))
                            ],
                        )
                    },
                    result_context=lambda result: result,
                )
                def inspect(target):
                    effects.append(target)
                    return {"exists": True}

            else:

                @task.tool(
                    "Inspect or submit one synthetic object",
                    irreversible=scenario == "duplicate_known_effect",
                    result_context=(
                        (lambda result: result)
                        if scenario in ("duplicate_query", "duplicate_known_effect")
                        else None
                    ),
                )
                def inspect():
                    effects.append("inspect")
                    return {"accepted": True, "private": private_marker}

            result = AgentLoop().run(
                task, goal="Resolve the bounded synthetic task", archive=archive, max_steps=10
            )
        except ValueError as exc:
            result = {"status": "invalid_configuration", "reason": str(exc)}
    elapsed = time.perf_counter() - started
    expected = SCENARIOS[scenario]
    return {
        "runtime_version": __version__,
        "scenario": scenario,
        "expected": expected,
        "status": result["status"],
        "reason": result.get("reason"),
        "effects": len(effects),
        "correct": result["status"] == expected["status"] and len(effects) == expected["effects"],
        "private_payload_in_terminal": private_marker in json.dumps(result),
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(result).encode()),
        "scripted_decision_bytes": sum(requests),
        "scripted_decisions": len(requests),
        "actual_model_usage": {"requests": 0, "models": {}, "input_tokens": 0, "output_tokens": 0},
    }


def snapshot(ref, destination):
    commit = subprocess.check_output(
        ["git", "rev-parse", ref + "^{commit}"], cwd=ROOT, text=True
    ).strip()
    archive = subprocess.check_output(["git", "archive", commit], cwd=ROOT)
    # Extract trusted Git files without following tar links or depending on newer Python filters.
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream:
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise ValueError("unsupported_snapshot_member")
            if member.isfile():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.extractfile(member).read())
    return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", choices=list(SCENARIOS), help=argparse.SUPPRESS)
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    parser.add_argument("--archive", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, args.source_dir)
        print(json.dumps(trial(args.worker, Path(args.archive))))
        return 0
    if not args.output:
        parser.error("--output is required")

    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = snapshot(args.baseline_ref, root / "baseline")
        sources = {"baseline": root / "baseline/src", "candidate": ROOT / "src"}
        for scenario in SCENARIOS:
            for repeat in range(3):
                for arm in (
                    ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                ):
                    archive = root / f"{scenario}-{repeat}-{arm}.jsonl"
                    # No credential is needed; decisions are scripted in the worker.
                    env = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
                    output = subprocess.check_output(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--worker",
                            scenario,
                            "--source-dir",
                            str(sources[arm]),
                            "--archive",
                            str(archive),
                        ],
                        env=env,
                        text=True,
                    )
                    row = json.loads(output)
                    row.update(arm=arm, repeat=repeat + 1)
                    rows.append(row)

    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [r for r in rows if r["arm"] == arm]
        summaries[arm] = {
            "correct": sum(r["correct"] for r in group),
            "runs": len(group),
            "statuses": {
                s: sum(r["status"] == s for r in group)
                for s in sorted({r["status"] for r in group})
            },
            "median_whole_operation_seconds": statistics.median(
                r["whole_operation_seconds"] for r in group
            ),
            "returned_context_bytes": sum(r["returned_context_bytes"] for r in group),
            "scripted_decision_bytes": sum(r["scripted_decision_bytes"] for r in group),
            "scripted_decisions": sum(r["scripted_decisions"] for r in group),
            "private_terminal_exposures": sum(r["private_payload_in_terminal"] for r in group),
            "actual_model_usage": {
                "requests": 0,
                "models": {},
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }
    report = {
        "mode": "offline-scripted",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "candidate_source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
        },
        "python_version": sys.version.split()[0],
        "reproduction": "python benchmarks/progress.py --output local-results/evidence-progress-ab.json",
        "scope": "Seven fixed synthetic scenarios, three paired repeats. No semantic accuracy or native UI measurement. Decisions and inference telemetry are scripted; actual model calls are zero.",
        "negative_results": "Fresh admitted evidence needs another decision even when observation is unchanged, increasing decision/context overhead. Identical invocation under identical observed state cannot be used for repeated polling. No cross-run deduplication promise.",
        "cost_conversion": "Zero paid calls; no tariff or savings assumed. Timing excludes interpreter/import/snapshot setup and includes task creation, decisions, tool callbacks and private journal writes.",
        "summary": summaries,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summaries))
    return (
        0
        if all(
            r["correct"] and not r["private_payload_in_terminal"]
            for r in rows
            if r["arm"] == "candidate"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
