"""Offline paired CLI configuration admission, using only synthetic import markers."""

import argparse
import contextlib
import hashlib
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "26cb69ae54e879043e6f18511da1f39446337de1"
CASES = {
    "blank_goal": ["--goal", " "],
    "messages_bad_json": ["--messages", "{"],
    "messages_wrong_empty_type": ["--messages", "{}"],
    "messages_system_role": ["--messages", '[{"role":"system","content":"policy"}]'],
    "messages_content_number": ["--messages", '[{"role":"user","content":1}]'],
    "zero_steps": ["--max-steps", "0"],
    "negative_steps": ["--max-steps", "-1"],
    "zero_timeout": ["--timeout", "0"],
    "nan_timeout": ["--timeout", "nan"],
    "infinite_timeout": ["--timeout", "inf"],
    "empty_required_path": ["--required-context", ""],
    "malformed_required_path": ["--required-context", "tenant..id"],
    "nan_inputs": ["--inputs", '{"amount":NaN}'],
    "infinite_context": ["--context", '{"amount":Infinity}'],
    "nan_message_metadata": ["--messages", '[{"role":"user","content":"text","extra":NaN}]'],
    "inputs_wrong_type": ["--inputs", "[]"],
    "context_wrong_type": ["--context", "[]"],
    "null_inputs": ["--inputs", "null"],
    "null_context": ["--context", "null"],
    "null_messages": ["--messages", "null"],
    "surrogate_inputs": ["--inputs", '{"text":"\\ud800"}'],
    "surrogate_context": ["--context", '{"text":"\\ud800"}'],
    "surrogate_messages": ["--messages", '[{"role":"user","content":"\\ud800"}]'],
    "valid_defaults": [],
    "valid_message": ["--messages", '[{"role":"user","content":"synthetic evidence"}]'],
    "missing_required_fact": ["--required-context", "tenant.id"],
}
VALID = {"valid_defaults", "valid_message", "missing_required_fact"}
SCRIPT = """from pathlib import Path
Path('import-marker.txt').write_text('synthetic trusted import')
from apixly_jev_harness import Task
workflow = Task(observe=lambda ctx: {'complete': True},
                verify=lambda ctx, seen: seen['complete'])
"""


def trial(name):
    from apixly_jev_harness import __version__
    from apixly_jev_harness.task_cli import main

    stdout = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "task.py"
        path.write_text(SCRIPT)
        previous = Path.cwd()
        try:
            os.chdir(directory)
            started = time.perf_counter()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    ["run", str(path), "--goal", "Observe synthetic completion", *CASES[name]]
                )
            elapsed = time.perf_counter() - started
            imported = (Path(directory) / "import-marker.txt").exists()
        finally:
            os.chdir(previous)
    packet = json.loads(stdout.getvalue())
    valid = name in VALID
    expected_status = (
        "needs_context" if name == "missing_required_fact" else "done" if valid else "failed"
    )
    expected_exit = 0 if expected_status == "done" else 2
    metadata_correct = valid or (
        packet.get("phase") == "configuration"
        and packet.get("code") == "invalid_run_configuration"
        and packet.get("script_loaded") is False
        and packet.get("model_calls") == 0
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "options": CASES[name],
        "expected_status": expected_status,
        "status": packet.get("status"),
        "exit_code": exit_code,
        "classification_correct": packet.get("status") == expected_status
        and exit_code == expected_exit,
        "expected_script_import": valid,
        "script_import_marker": imported,
        "load_policy_correct": imported == valid,
        "configuration_metadata_correct": metadata_correct,
        "phase": packet.get("phase"),
        "code": packet.get("code"),
        "error_type": packet.get("error_type"),
        "missing_context": packet.get("missing_context"),
        "reported_model_requests": packet.get("telemetry", {}).get(
            "requests", packet.get("model_calls")
        ),
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(stdout.getvalue().encode()),
        "actual_model_usage": {"requests": 0, "models": {}, "input_tokens": 0, "output_tokens": 0},
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
        print(json.dumps(trial(args.worker)))
        return 0
    if not args.output:
        parser.error("--output is required")
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = snapshot(args.baseline_ref, root / "baseline")
        sources = {"baseline": root / "baseline/src", "candidate": ROOT / "src"}
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
                    rows.append(row)
    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        summaries[arm] = {
            "runs": len(group),
            "classification_correct": sum(row["classification_correct"] for row in group),
            "load_policy_correct": sum(row["load_policy_correct"] for row in group),
            "configuration_metadata_correct": sum(
                row["configuration_metadata_correct"] for row in group
            ),
            "invalid_config_imports": sum(
                row["script_import_marker"] and not row["expected_script_import"] for row in group
            ),
            "valid_config_imports": sum(
                row["script_import_marker"] and row["expected_script_import"] for row in group
            ),
            "statuses": {
                status: sum(row["status"] == status for row in group)
                for status in sorted({row["status"] for row in group})
            },
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "actual_model_usage": {
                "requests": 0,
                "models": {},
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }
    report = {
        "mode": "offline-synthetic-config-admission",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "candidate_source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "synthetic_script": SCRIPT,
        "reproduction": "python benchmarks/run_preflight.py --output local-results/run-preflight-ab.json",
        "scope": "Twenty-six fixed configurations, three paired repeats. The only script import effect is a local synthetic marker. Valid scripts deliberately import and return an observed complete state or runtime needs_context; no tool execution or model/UI/network calls. This is configuration admission, not semantic accuracy or a sandbox.",
        "negative_results": "Preflight adds local work and configuration metadata bytes; Engine revalidates options for direct API parity. Valid imports may have effects. This does not check archive/credential/runtime conditions or workflow correctness. No runtime/model latency or fee improvement is claimed.",
        "cost_conversion": "Zero actual model calls, no tariff or savings assumed. Timing covers CLI parsing, admission, permitted synthetic import, engine validation/journaling and compact output; excludes process/import/snapshot setup.",
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
            row["classification_correct"]
            and row["load_policy_correct"]
            and row["configuration_metadata_correct"]
            for row in rows
            if row["arm"] == "candidate"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
