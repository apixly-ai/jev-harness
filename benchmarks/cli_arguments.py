"""Offline paired structured CLI argument failures against exact v0.1.7."""

import argparse
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "609d76822dc721a1f19bb7c3b2837f553507d24f"
MARKER = "SYNTHETIC_ARGUMENT_VALUE"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
SCRIPT = """from pathlib import Path
Path('import-marker.txt').write_text('synthetic trusted import')
from apixly_jev_harness import Task
workflow=Task(observe=lambda ctx:{'done':True},verify=lambda ctx,seen:seen['done'])
"""
RUN = ["run", "$SCRIPT", "--goal", "Observe synthetic completion"]
INVALID = {
    "missing_command": [],
    "unknown_command": [MARKER],
    "unknown_flag": [*RUN, "--" + MARKER],
    "unknown_flag_value": [*RUN, "--unknown", MARKER],
    "invalid_integer": [*RUN, "--max-steps", MARKER],
    "invalid_float": [*RUN, "--timeout", MARKER],
    "missing_goal": ["run", "$SCRIPT"],
    "missing_goal_value": ["run", "$SCRIPT", "--goal"],
    "extra_positional": [*RUN, MARKER],
    "missing_run_script": ["run", "--goal", "Observe synthetic completion"],
    "missing_check_script": ["check-task"],
    "missing_init_script": ["init-task"],
    "ambiguous_short_option": [*RUN, "--m", MARKER],
    "missing_inputs_value": [*RUN, "--inputs"],
    "init_unknown_flag": ["init-task", "$NEW", "--" + MARKER],
    "spec_extra_value": ["spec", MARKER],
}
CASES = {
    **{
        name: {"argv": arguments, "kind": "arguments", "exit_code": 2}
        for name, arguments in INVALID.items()
    },
    "root_help": {"argv": ["--help"], "kind": "help", "exit_code": 0},
    "run_help": {"argv": ["run", "--help"], "kind": "help", "exit_code": 0},
    "help_before_unknown_flag": {
        "argv": ["run", "--help", "--unknown"],
        "kind": "help",
        "exit_code": 0,
    },
    "valid_spec": {"argv": ["spec"], "kind": "spec", "exit_code": 0},
    "valid_check": {"argv": ["check-task", "$SCRIPT"], "kind": "check", "exit_code": 0},
    "valid_init": {"argv": ["init-task", "$NEW"], "kind": "init", "exit_code": 0},
    "valid_complete_run": {"argv": [*RUN, "--archive", "$ARCHIVE"], "kind": "run", "exit_code": 0},
    "valid_long_abbreviations": {
        "argv": [
            "run",
            "$SCRIPT",
            "--go",
            "Observe synthetic completion",
            "--max-s",
            "2",
            "--time",
            "5",
            "--archive",
            "$ARCHIVE",
        ],
        "kind": "run",
        "exit_code": 0,
    },
    "malformed_json_configuration": {
        "argv": [*RUN, "--inputs", "{" + MARKER],
        "kind": "configuration",
        "exit_code": 2,
    },
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def argument_packet(packet):
    return packet == {
        "status": "failed",
        "complete": False,
        "phase": "arguments",
        "code": "invalid_command_arguments",
        "script_loaded": False,
        "model_calls": 0,
    }


def trial(name, source_dir):
    from apixly_jev_harness import __file__ as runtime_file
    from apixly_jev_harness import __version__
    from apixly_jev_harness.task_cli import main

    counts = {
        "source_read_calls": 0,
        "module_spec_attempts": 0,
        "module_exec_attempts": 0,
        "native_inference_attempts": 0,
    }

    def forbidden(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Offline argument fixtures prohibit native inference")

    stdout, stderr = io.StringIO(), io.StringIO()
    previous_directory = Path.cwd()
    previous_stdout, previous_stderr = sys.stdout, sys.stderr
    raised, exit_code, restored = None, None, False
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        script, new_script, archive = (
            fixture / file for file in ("task.py", "new-task.py", "run.jsonl")
        )
        script.write_text(SCRIPT, encoding="utf-8", newline="\n")
        script_resolved = script.resolve()
        initial_files = {path.relative_to(fixture) for path in fixture.rglob("*") if path.is_file()}
        values = {"$SCRIPT": str(script), "$NEW": str(new_script), "$ARCHIVE": str(archive)}
        argv = [values.get(value, value) for value in CASES[name]["argv"]]
        original_open = Path.open
        original_spec = importlib.util.spec_from_file_location
        original_data = importlib.machinery.SourceFileLoader.get_data
        original_exec = importlib.machinery.SourceFileLoader.exec_module

        def is_script(path):
            return Path(path).resolve() == script_resolved

        def track_open(path, mode="r", *args, **kwargs):
            if is_script(path) and "r" in mode:
                counts["source_read_calls"] += 1
            return original_open(path, mode, *args, **kwargs)

        def track_spec(module_name, path, *args, **kwargs):
            if path is not None and is_script(path):
                counts["module_spec_attempts"] += 1
            return original_spec(module_name, path, *args, **kwargs)

        def track_data(loader, path):
            if is_script(path):
                counts["source_read_calls"] += 1
            return original_data(loader, path)

        def track_exec(loader, module):
            if is_script(loader.path):
                counts["module_exec_attempts"] += 1
            return original_exec(loader, module)

        try:
            os.chdir(directory)
            with (
                patch("apixly_jev_harness.backend.native_run", forbidden),
                patch("apixly_jev_harness.backend.provider_evaluate", forbidden),
                patch("apixly_jev_harness.engine.analysis.evaluate", forbidden),
                patch("pathlib.Path.open", track_open),
                patch("importlib.util.spec_from_file_location", track_spec),
                patch("importlib.machinery.SourceFileLoader.get_data", track_data),
                patch("importlib.machinery.SourceFileLoader.exec_module", track_exec),
            ):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    started = time.perf_counter()
                    try:
                        exit_code = main(argv)
                    except SystemExit as error:
                        raised = "SystemExit"
                        exit_code = error.code if type(error.code) is int else None
                    restored = sys.stdout is stdout and sys.stderr is stderr
                    elapsed = time.perf_counter() - started
            imported = (fixture / "import-marker.txt").is_file()
            created = new_script.is_file()
            journal = archive.is_file()
            final_files = {
                path.relative_to(fixture) for path in fixture.rglob("*") if path.is_file()
            }
            source_unchanged = script.read_text(encoding="utf-8") == SCRIPT
        finally:
            os.chdir(previous_directory)
    restored = restored and sys.stdout is previous_stdout and sys.stderr is previous_stderr
    raw_stdout, raw_stderr = stdout.getvalue().encode(), stderr.getvalue().encode()
    try:
        packet = json.loads(raw_stdout)
        if not isinstance(packet, dict):
            packet = None
    except (json.JSONDecodeError, UnicodeDecodeError):
        packet = None
    expected = CASES[name]
    kind = expected["kind"]
    files_correct = (
        source_unchanged
        and imported == (kind == "run")
        and created == (kind == "init")
        and journal == (kind == "run")
    )
    if kind in {"arguments", "configuration", "help", "spec", "check"}:
        files_correct = files_correct and not (final_files - initial_files)
    no_source_access = (
        counts["source_read_calls"]
        == counts["module_spec_attempts"]
        == counts["module_exec_attempts"]
        == 0
    )
    if kind in {"arguments", "configuration", "help", "spec", "init"}:
        access_correct = no_source_access
    elif kind == "check":
        access_correct = (
            counts["source_read_calls"] == 1
            and counts["module_spec_attempts"] == counts["module_exec_attempts"] == 0
        )
    else:
        access_correct = (
            counts["source_read_calls"]
            == counts["module_spec_attempts"]
            == counts["module_exec_attempts"]
            == 1
        )
    if kind == "arguments":
        metadata_correct = argument_packet(packet)
        status = packet.get("status") if packet else "system_exit" if raised else "unknown"
    elif kind == "configuration":
        metadata_correct = packet is not None and all(
            packet.get(key) == value
            for key, value in {
                "status": "failed",
                "complete": False,
                "phase": "configuration",
                "code": "invalid_run_configuration",
                "script_loaded": False,
                "model_calls": 0,
            }.items()
        )
        status = packet.get("status") if packet else "unknown"
    elif kind == "help":
        metadata_correct = packet is None and raised == "SystemExit" and b"usage:" in raw_stdout
        status = "help" if metadata_correct else "unknown"
    elif kind == "spec":
        metadata_correct = (
            packet is not None
            and packet.get("name") == "jev-harness"
            and packet.get("version") == __version__
        )
        status = "spec" if metadata_correct else "unknown"
    elif kind == "check":
        metadata_correct = (
            packet is not None
            and packet.get("ok") is True
            and packet.get("code") == "syntax_and_export_ok"
            and packet.get("model_calls") == 0
        )
        status = "checked" if metadata_correct else "unknown"
    elif kind == "init":
        metadata_correct = (
            packet is not None
            and packet.get("status") == "created"
            and packet.get("model_calls") == 0
        )
        status = packet.get("status") if packet else "unknown"
    else:
        metadata_correct = (
            packet is not None
            and packet.get("status") == "done"
            and packet.get("complete") is True
            and packet.get("steps") == 0
            and packet.get("telemetry", {}).get("requests") == 0
        )
        status = packet.get("status") if packet else "unknown"
    exposures = {
        "stdout": raw_stdout.count(MARKER.encode()),
        "stderr": raw_stderr.count(MARKER.encode()),
    }
    output_correct = (
        not raw_stderr and (packet is not None or kind == "help") and not any(exposures.values())
    )
    exit_correct = exit_code == expected["exit_code"]
    correct = (
        metadata_correct
        and files_correct
        and access_correct
        and output_correct
        and exit_correct
        and restored
        and counts["native_inference_attempts"] == 0
    )
    result = {
        "status": status,
        "exit_code": exit_code,
        "raised": raised,
        "terminal_json_exact": packet is not None,
        "phase": packet.get("phase") if packet else None,
        "code": packet.get("code") if packet else None,
        "status_metadata_correct": metadata_correct,
        "output_policy_correct": output_correct,
        "exit_code_correct": exit_correct,
        "task_import_marker": imported,
        "init_output_created": created,
        "journal_created": journal,
        "source_unchanged": source_unchanged,
        "new_file_count": len(final_files - initial_files),
        "filesystem_policy_correct": files_correct,
        "source_access_policy_correct": access_correct,
        "streams_restored": restored,
        "raw_marker_exposures": exposures,
        "captured_stdout_bytes": len(raw_stdout),
        "captured_stderr_bytes": len(raw_stderr),
        "captured_stdout_sha256": hashlib.sha256(raw_stdout).hexdigest(),
        "captured_stderr_sha256": hashlib.sha256(raw_stderr).hexdigest(),
        **counts,
    }
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "argv_template": expected["argv"],
        "expected": {"kind": kind, "exit_code": expected["exit_code"]},
        "result": result,
        "correct": correct,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(raw_stdout) + len(raw_stderr),
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
            "argument_error_runs": sum(row["expected"]["kind"] == "arguments" for row in group),
            "help_runs": sum(row["expected"]["kind"] == "help" for row in group),
            "exact_json_packets": sum(row["result"]["terminal_json_exact"] for row in group),
            "correct": sum(row["correct"] for row in group),
            "status_metadata_correct": sum(
                row["result"]["status_metadata_correct"] for row in group
            ),
            "filesystem_policy_correct": sum(
                row["result"]["filesystem_policy_correct"] for row in group
            ),
            "source_access_policy_correct": sum(
                row["result"]["source_access_policy_correct"] for row in group
            ),
            "streams_restored": sum(row["result"]["streams_restored"] for row in group),
            "raw_marker_exposures": {
                channel: sum(row["result"]["raw_marker_exposures"][channel] for row in group)
                for channel in ("stdout", "stderr")
            },
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
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
    report = {
        "mode": "offline-synthetic-cli-arguments",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "synthetic_task_sha256": hashlib.sha256(SCRIPT.encode()).hexdigest(),
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "reproduction": "python benchmarks/cli_arguments.py --output local-results/cli-arguments-ab.json",
        "scope": "Twenty-five fixed synthetic argv fixtures, three paired repeats with alternating arm order. Sixteen malformed parser inputs expect a fixed arguments-phase JSON failure and zero task source read/spec/exec, import/init/journal effects and actual model calls. Help remains plain text with SystemExit(0), including help before a trailing unknown flag; valid long-option abbreviations remain accepted, and malformed JSON remains a distinct configuration-phase failure. Valid task runs import only a synthetic local marker and an already-complete workflow, with zero tool effects/decisions. Native inference entrypoints are forbidden. Raw captured stdout/stderr stay local to each trial; the report contains counts/digests/fixed synthetic marker exposures and argv templates with path placeholders.",
        "negative_results": "Fixed failure metadata adds bytes for terse failures and omits argparse's specific corrective error/help detail. AI callers can inspect spec/help but this does not guarantee every malformed input or every process failure returns JSON. Argparse help can exit successfully before validating later unknown arguments; that plain-text precedence is preserved. BaseExceptions, failed output streams, encoding issues, trusted task runtime and sandboxing are outside the argument-parser boundary. Source-access probes cover the synthetic task content/import paths, not every operating-system filesystem read. Valid help is intentionally not a JSON packet. No semantic quality, speed or fee gain is claimed.",
        "cost_conversion": "Zero actual model calls only with no native guard attempts; a guard hit records unknown usage and fails the fixture. No tariff or savings assumed. Whole-operation timing includes parser construction/admission, permitted offline commands or trusted synthetic task import/journaling, output serialization and stream restoration; excludes process/import/temp fixture setup and result analysis. Returned context bytes measure all actual stdout plus stderr, including baseline help/error detail. Fixed synthetic marker exposure counts do not establish arbitrary data confidentiality.",
        "summary": summaries,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summaries))
    return 0 if all(row["correct"] for row in rows if row["arm"] == "candidate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
