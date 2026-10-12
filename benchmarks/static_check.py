"""Offline paired check-task correctness; no inspected script or model is executed."""

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
BASELINE = "37358ff83a83203b270c4cf92f8db7272239cca6"
FIXTURES = {
    "assignment": ("workflow = None\n", 0, "syntax_and_export_ok", 0),
    "assigned_annotation": ("workflow: object = None\n", 0, "syntax_and_export_ok", 0),
    "annotation_only": ("workflow: object\n", 2, "workflow_export_missing", 0),
    "module_return": ("workflow = None\nreturn\n", 2, "invalid_python", 0),
    "module_break": ("workflow = None\nbreak\n", 2, "invalid_python", 0),
    "module_continue": ("workflow = None\ncontinue\n", 2, "invalid_python", 0),
    "duplicate_arguments": (
        "workflow = None\ndef duplicate(x, x):\n    pass\n",
        2,
        "invalid_python",
        0,
    ),
    "unbound_nonlocal": (
        "workflow = None\ndef missing():\n    nonlocal unknown\n",
        2,
        "invalid_python",
        0,
    ),
    "parse_failure": ("workflow = (", 2, "invalid_python", 0),
    "non_utf8": (b"workflow = None\n# SYNTHETIC_PRIVATE_SOURCE \xff\n", 2, "source_not_utf8", 0),
    "unavailable_import_not_run": (
        "import synthetic_module_that_does_not_exist\nworkflow = None\n",
        0,
        "syntax_and_export_ok",
        0,
    ),
    "effects_and_raise_not_run": (
        "from pathlib import Path\nPath('effect.txt').write_text('must never execute')\nraise RuntimeError('SYNTHETIC_PRIVATE_SOURCE')\nworkflow = None\n",
        0,
        "syntax_and_export_ok",
        0,
    ),
    "compiler_warning": (
        "workflow = None\nif 'SYNTHETIC_PRIVATE_SOURCE' is 'SYNTHETIC_PRIVATE_SOURCE':\n    pass\n",
        0,
        "syntax_and_export_ok",
        1,
    ),
}


def trial(name):
    from apixly_jev_harness import __version__
    from apixly_jev_harness.task_cli import main

    source, expected_exit, expected_code, expected_warnings = FIXTURES[name]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "task.py"
        path.write_bytes(source if isinstance(source, bytes) else source.encode())
        previous = Path.cwd()
        stdout, stderr = io.StringIO(), io.StringIO()
        packet, exception_type = None, None
        try:
            os.chdir(directory)
            started = time.perf_counter()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    exit_code = main(["check-task", str(path)])
                except Exception as error:
                    exception_type = type(error).__name__
                    exit_code = None
            elapsed = time.perf_counter() - started
            try:
                packet = json.loads(stdout.getvalue())
            except ValueError:
                pass
            effect = (Path(directory) / "effect.txt").exists()
        finally:
            os.chdir(previous)
    classification_correct = (
        exit_code == expected_exit and packet is not None and packet.get("code") == expected_code
    )
    warning_count = len(packet.get("source_warnings", [])) if packet is not None else None
    private_source = "SYNTHETIC_PRIVATE_SOURCE" in stdout.getvalue() + stderr.getvalue()
    return {
        "fixture": name,
        "runtime_version": __version__,
        "expected": {
            "exit_code": expected_exit,
            "code": expected_code,
            "warning_count": expected_warnings,
        },
        "exit_code": exit_code,
        "packet": packet,
        "exception_type": exception_type,
        "classification_correct": classification_correct,
        "warning_reporting_correct": warning_count == expected_warnings,
        "protocol_correct": classification_correct and warning_count == expected_warnings,
        "script_effect_detected": effect,
        "private_source_in_output": private_source,
        "stderr_bytes": len(stderr.getvalue().encode()),
        "whole_operation_seconds": elapsed,
        "source_bytes": len(source if isinstance(source, bytes) else source.encode()),
        "returned_context_bytes": len(stdout.getvalue().encode()),
        "actual_model_usage": {"requests": 0, "models": {}, "input_tokens": 0, "output_tokens": 0},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", choices=list(FIXTURES), help=argparse.SUPPRESS)
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
        for name in FIXTURES:
            for repeat in range(3):
                for arm in (
                    ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                ):
                    env = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
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
            "protocol_correct": sum(row["protocol_correct"] for row in group),
            "unhandled_exceptions": sum(row["exception_type"] is not None for row in group),
            "script_effects": sum(row["script_effect_detected"] for row in group),
            "private_source_exposures": sum(row["private_source_in_output"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "source_bytes": sum(row["source_bytes"] for row in group),
            "actual_model_usage": {
                "requests": 0,
                "models": {},
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }
    report = {
        "mode": "offline-static-check",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "candidate_source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": sys.version.split()[0],
        "fixtures": {
            name: {
                "source": source if isinstance(source, str) else None,
                "source_hex": source.hex() if isinstance(source, bytes) else None,
                "expected_exit": exit_code,
                "expected_code": code,
                "expected_warning_count": count,
            }
            for name, (source, exit_code, code, count) in FIXTURES.items()
        },
        "reproduction": "python benchmarks/static_check.py --output local-results/static-check-ab.json",
        "scope": "Thirteen fixed synthetic scripts, three paired repeats against published source. Checks run on the current Python interpreter. The checker does not execute inspected scripts, imports or callbacks. No model/UI calls. Static acceptance is not workflow-type, import, callback, provider or runtime-success verification.",
        "negative_results": "Compilation adds deterministic work and diagnostic bytes. Nonfatal source warnings remain nonfatal; unknown imports and workflow=None remain statically accepted. No model cost or latency improvement is measured. Other interpreter versions are tested separately by CI, not inferred from this run.",
        "cost_conversion": "Zero actual model calls, no tariff or savings assumed. Whole-operation timing covers CLI argument parsing, source reading, parse/compile and compact output, excluding interpreter/import/snapshot setup.",
        "summary": summaries,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summaries))
    return (
        0
        if all(
            row["protocol_correct"]
            and not row["script_effect_detected"]
            and not row["private_source_in_output"]
            for row in rows
            if row["arm"] == "candidate"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
