"""Offline paired CLI task-output policy against the exact v0.1.6 release."""

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
import warnings
from pathlib import Path
from unittest.mock import patch

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "32867087bf173515806958b61acffdd08c743659"
MARKER = "SYNTHETIC_TASK_OUTPUT"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
COMPLETE = """from apixly_jev_harness import Task
workflow=Task(observe=lambda ctx: {'done': True}, verify=lambda ctx, seen: seen['done'])
"""
EFFECT = """import sys
from pathlib import Path
from apixly_jev_harness import Task
state={'done':False}
workflow=Task(observe=lambda ctx:dict(state),verify=lambda ctx,seen:seen['done'])
@workflow.tool('Inspect one synthetic state')
def inspect():
    print('SYNTHETIC_TASK_OUTPUT')
    print('SYNTHETIC_TASK_OUTPUT',file=sys.stderr)
    Path('effect-marker.txt').write_text('synthetic effect')
    state['done']=True
"""
SOURCES = {
    "quiet": COMPLETE,
    "import_stdout": f"print({MARKER!r})\n" + COMPLETE,
    "import_stderr": f"import sys\nprint({MARKER!r},file=sys.stderr)\n" + COMPLETE,
    "import_both": f"import sys\nprint({MARKER!r})\nprint({MARKER!r},file=sys.stderr)\n" + COMPLETE,
    "observer_verifier": f"""import sys
from apixly_jev_harness import Task
def observe(ctx):
    print({MARKER!r})
    return {{'done':True}}
def verify(ctx,seen):
    print({MARKER!r},file=sys.stderr)
    return seen['done']
workflow=Task(observe=observe,verify=verify)
""",
    "success_effect": EFFECT + "    return {'done':True}\n",
    "uncertain_effect": EFFECT + f"    raise TimeoutError({MARKER!r})\n",
    "import_exception": f"print({MARKER!r})\nraise ValueError({MARKER!r})\n",
    "unicode": f"import sys\nsys.stdout.write('中文🙂'+{MARKER!r})\n" + COMPLETE,
    "binary_invalid_utf8": f"import sys\nsys.stdout.buffer.write(b'\\xff'+{MARKER.encode()!r})\nsys.stderr.buffer.write(memoryview(b'\\xfe'+{MARKER.encode()!r}))\n"
    + COMPLETE,
    "large_output": f"print({MARKER!r}+'X'*1000000)\n" + COMPLETE,
    "empty_writes": "import sys\nsys.stdout.write('')\nsys.stderr.write('')\nsys.stdout.buffer.write(b'')\nsys.stderr.buffer.write(b'')\n"
    + COMPLETE,
    "warning": f"import warnings\nwarnings.warn({MARKER!r},UserWarning)\n" + COMPLETE,
    "write_return_counts": f"""import sys
from apixly_jev_harness import Task
text='中文'+{MARKER!r}
binary=b'\\xff'+{MARKER.encode()!r}
printed=print({MARKER!r})
returns=[sys.stdout.write(text),sys.stdout.buffer.write(binary),sys.stderr.write({MARKER!r}),sys.stderr.buffer.write(memoryview(binary))]
correct=printed is None and returns==[len(text),len(binary),len({MARKER!r}),len(binary)]
workflow=Task(observe=lambda ctx:{{'done':correct}},verify=lambda ctx,seen:seen['done'])
""",
    "system_exit": f"print({MARKER!r})\nraise SystemExit(7)\n",
    "keyboard_interrupt": f"print({MARKER!r})\nraise KeyboardInterrupt()\n",
    "system_exit_text": f"print({MARKER!r})\nraise SystemExit({MARKER!r})\n",
    "system_exit_zero": f"print({MARKER!r})\nraise SystemExit(0)\n",
    "keyboard_interrupt_text": f"print({MARKER!r})\nraise KeyboardInterrupt({MARKER!r})\n",
}
BASE_EXCEPTION_CASES = {
    "system_exit": ("SystemExit", 7),
    "system_exit_text": ("SystemExit", 1),
    "system_exit_zero": ("SystemExit", 1),
    "keyboard_interrupt": ("KeyboardInterrupt", 130),
    "keyboard_interrupt_text": ("KeyboardInterrupt", 130),
}
CASES = {
    name: {
        "status": "execution_uncertain"
        if name == "uncertain_effect"
        else "failed"
        if name == "import_exception"
        else "base_exception"
        if name in BASE_EXCEPTION_CASES
        else "done",
        "effects": 1 if name in {"success_effect", "uncertain_effect"} else 0,
        "exit_code": 2
        if name in {"uncertain_effect", "import_exception"}
        else None
        if name in BASE_EXCEPTION_CASES
        else 0,
        "base_exception": "SystemExit" if name in BASE_EXCEPTION_CASES else None,
        "source_exception_kind": BASE_EXCEPTION_CASES[name][0]
        if name in BASE_EXCEPTION_CASES
        else None,
        "exception_exit_code": BASE_EXCEPTION_CASES[name][1]
        if name in BASE_EXCEPTION_CASES
        else None,
    }
    for name in SOURCES
}


class _BinaryCollector(io.RawIOBase):
    """Outer synthetic collector only; raw bytes never leave the trial function."""

    def __init__(self, storage):
        self.storage = storage

    def writable(self):
        return True

    def write(self, value):
        data = memoryview(value)
        self.storage.extend(data.tobytes())
        return data.nbytes


class _Collector(io.TextIOBase):
    def __init__(self):
        self.storage = bytearray()
        self.buffer = _BinaryCollector(self.storage)

    @property
    def encoding(self):
        return "utf-8"

    @property
    def errors(self):
        return "strict"

    def writable(self):
        return True

    def write(self, value):
        self.storage.extend(value.encode("utf-8"))
        return len(value)


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def expected_output(name, script):
    out_text = error_text = out_binary = error_binary = 0
    if name in {
        "import_stdout",
        "import_both",
        "observer_verifier",
        "success_effect",
        "uncertain_effect",
        "import_exception",
        "system_exit",
        "keyboard_interrupt",
        "system_exit_text",
        "system_exit_zero",
        "keyboard_interrupt_text",
    }:
        out_text = len(MARKER) + 1
    if name in {
        "import_stderr",
        "import_both",
        "observer_verifier",
        "success_effect",
        "uncertain_effect",
    }:
        error_text = len(MARKER) + 1
    if name == "unicode":
        out_text = len(MARKER) + 3
    elif name == "binary_invalid_utf8":
        out_binary = error_binary = len(MARKER.encode()) + 1
    elif name == "large_output":
        out_text = len(MARKER) + 1000001
    elif name == "warning":
        error_text = len(
            warnings.formatwarning(
                MARKER, UserWarning, str(script.resolve()), 2, line=SOURCES[name].splitlines()[1]
            )
        )
    elif name == "write_return_counts":
        out_text = len(MARKER) * 2 + 3
        error_text = len(MARKER)
        out_binary = error_binary = len(MARKER.encode()) + 1
    if not any((out_text, error_text, out_binary, error_binary)):
        return None
    return {
        "policy": "discard",
        "scope": "python_streams",
        "stdout": {"characters": out_text, "binary_bytes": out_binary},
        "stderr": {"characters": error_text, "binary_bytes": error_binary},
    }


def recover_terminal(stdout):
    """Diagnostic recovery from synthetic baseline pollution, never a CLI guarantee."""
    exact = True
    try:
        packet = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        exact = False
        start = stdout.rfind(b'{"status":')
        if start == -1:
            return None, False
        try:
            packet = json.loads(stdout[start:].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, False
    return packet if isinstance(packet, dict) else None, exact and isinstance(packet, dict)


def trial(name, source_dir):
    from apixly_jev_harness import __file__ as runtime_file
    from apixly_jev_harness import __version__
    from apixly_jev_harness.task_cli import main

    native_attempts = 0
    decision_sizes = []

    def forbidden(*args, **kwargs):
        nonlocal native_attempts
        native_attempts += 1
        raise AssertionError("Offline task-output fixture prohibits native inference")

    def decide(parts, goal, workers, spec):
        decision_sizes.append(len(json.dumps([parts, spec], sort_keys=True).encode()))
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

    stdout, stderr = _Collector(), _Collector()
    base_exception, exit_code, restored = None, None, False
    exception_exit_code, exception_code_type, exception_marker_count = None, None, 0
    previous_directory = Path.cwd()
    previous_stdout, previous_stderr = sys.stdout, sys.stderr
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "task.py"
        script.write_text(SOURCES[name], encoding="utf-8", newline="\n")
        expected_metadata = expected_output(name, script)
        try:
            os.chdir(directory)
            with (
                patch("apixly_jev_harness.backend.native_run", forbidden),
                patch("apixly_jev_harness.backend.provider_evaluate", forbidden),
                patch("apixly_jev_harness.engine.analysis.evaluate", decide),
            ):
                with (
                    warnings.catch_warnings(),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    warnings.simplefilter("always")
                    started = time.perf_counter()
                    try:
                        exit_code = main(
                            [
                                "run",
                                str(script),
                                "--goal",
                                "Inspect one synthetic state",
                                "--archive",
                                str(Path(directory) / "run.jsonl"),
                                "--max-steps",
                                "2",
                            ]
                        )
                    except (SystemExit, KeyboardInterrupt) as error:
                        base_exception = type(error).__name__
                        exception_marker_count = str(error).count(MARKER)
                        if isinstance(error, SystemExit):
                            exception_code_type = type(error.code).__name__
                            exception_exit_code = error.code if type(error.code) is int else None
                    restored = sys.stdout is stdout and sys.stderr is stderr
                    elapsed = time.perf_counter() - started
            effects = int((Path(directory) / "effect-marker.txt").exists())
        finally:
            os.chdir(previous_directory)
    restored = restored and sys.stdout is previous_stdout and sys.stderr is previous_stderr
    raw_stdout, raw_stderr = bytes(stdout.storage), bytes(stderr.storage)
    packet, exact_json = recover_terminal(raw_stdout)
    expected = CASES[name]
    is_base_exception = expected["base_exception"] is not None
    if is_base_exception:
        metadata_correct = packet is None
        terminal_policy_correct = packet is None and not raw_stdout and not raw_stderr
    else:
        metadata_correct = packet is not None and packet.get("task_output") == expected_metadata
        terminal_policy_correct = exact_json and not raw_stderr
    status = "base_exception" if base_exception else packet.get("status") if packet else "unknown"
    status_correct = (
        status == expected["status"]
        and exit_code == expected["exit_code"]
        and effects == expected["effects"]
        and base_exception == expected["base_exception"]
        and exception_exit_code == expected["exception_exit_code"]
    )
    exposures = {
        "stdout": raw_stdout.count(MARKER.encode()),
        "stderr": raw_stderr.count(MARKER.encode()),
    }
    result = {
        "status": status,
        "exit_code": exit_code,
        "effects": effects,
        "base_exception": base_exception,
        "source_exception_kind": expected["source_exception_kind"],
        "exception_exit_code": exception_exit_code,
        "exception_code_type": exception_code_type,
        "propagated_exception_marker_count": exception_marker_count,
        "error_type": packet.get("error_type") if packet else None,
        "terminal_json_exact": exact_json,
        "terminal_packet_recovered": packet is not None,
        "terminal_policy_correct": terminal_policy_correct,
        "task_output_metadata": packet.get("task_output") if packet else None,
        "expected_task_output_metadata": None if is_base_exception else expected_metadata,
        "task_output_metadata_correct": metadata_correct,
        "status_and_effect_correct": status_correct,
        "streams_restored": restored,
        "raw_marker_exposures": exposures,
        "captured_stdout_bytes": len(raw_stdout),
        "captured_stderr_bytes": len(raw_stderr),
        "captured_stdout_sha256": hashlib.sha256(raw_stdout).hexdigest(),
        "captured_stderr_sha256": hashlib.sha256(raw_stderr).hexdigest(),
        "scripted_decisions": len(decision_sizes),
        "native_inference_attempts": native_attempts,
    }
    correct = (
        status_correct
        and metadata_correct
        and terminal_policy_correct
        and restored
        and not any(exposures.values())
        and exception_marker_count == 0
        and native_attempts == 0
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture_sha256": hashlib.sha256(SOURCES[name].encode()).hexdigest(),
        "expected": expected,
        "result": result,
        "correct": correct,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(raw_stdout) + len(raw_stderr),
        "scripted_decision_bytes": sum(decision_sizes),
        "actual_model_usage": ZERO_USAGE
        if native_attempts == 0
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
        if any(source_hashes(source) != hashes[arm] for arm, source in sources.items()) or (
            runner_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        ):
            raise RuntimeError("benchmark_sources_changed_during_run")

    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        guard_hit = any(row["result"]["native_inference_attempts"] for row in group)
        summaries[arm] = {
            "runs": len(group),
            "ordinary_terminal_runs": sum(
                row["expected"]["base_exception"] is None for row in group
            ),
            "exact_json_terminals": sum(row["result"]["terminal_json_exact"] for row in group),
            "propagated_base_exceptions": sum(
                row["result"]["base_exception"] is not None for row in group
            ),
            "propagated_exception_markers": sum(
                row["result"]["propagated_exception_marker_count"] for row in group
            ),
            "correct": sum(row["correct"] for row in group),
            "status_and_effect_correct": sum(
                row["result"]["status_and_effect_correct"] for row in group
            ),
            "terminal_policy_correct": sum(
                row["result"]["terminal_policy_correct"] for row in group
            ),
            "task_output_metadata_correct": sum(
                row["result"]["task_output_metadata_correct"] for row in group
            ),
            "streams_restored": sum(row["result"]["streams_restored"] for row in group),
            "raw_marker_exposures": {
                channel: sum(row["result"]["raw_marker_exposures"][channel] for row in group)
                for channel in ("stdout", "stderr")
            },
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
            ),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "scripted_decision_bytes": sum(row["scripted_decision_bytes"] for row in group),
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
        "mode": "offline-synthetic-cli-task-output",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "reproduction": "python benchmarks/task_output.py --output local-results/task-output-ab.json",
        "scope": "Nineteen fixed synthetic CLI fixtures, three paired repeats with alternating arm order. Binary-capable outer collectors hold baseline printed bytes only inside each trial; only counts and digests are reported. Ordinary loops use scripted decisions and native inference entrypoints are forbidden. The expected new policy is one exact terminal JSON packet and count-only output metadata; interrupt/exit fixtures deliberately produce no packet and are caught outside main to measure restored streams and sanitized integer exit codes. Source exception kind is separate from the propagated exception. Actual model/UI/network calls are zero if the native guard is never hit. This evaluates console transport and exit-code normalization, not semantic quality, interpreter exception printing, an async runtime or a sandbox.",
        "negative_results": "Discard removes console debugging text from the CLI and fixed counters add metadata/context for small-output tasks. Python stream redirection is process-global; saved streams, existing logging handlers, native file descriptors, subprocesses and concurrent/late threads can bypass it and are excluded. Direct SDK console behavior is outside this CLI benchmark. KeyboardInterrupt changes to quiet SystemExit(130); task SystemExit retains exact integers 1..255 but text/zero/other codes become 1. A terminal packet, counter metadata and runtime effects remain unknown for those exits; fixed synthetic effects here are independently checked via local markers and no effects are inferred from exit codes. Outer benchmark catches prevent interpreter printing, so these rows alone do not prove actual interpreter output. Baseline terminal recovery after pollution is diagnostic only and does not count as parseable output. No model accuracy, speed or fee gain is claimed.",
        "cost_conversion": "No tariff or savings assumed. Actual usage is zero only with zero native guard attempts; guard hits produce unknown usage and a failed policy result. Whole-operation timing includes CLI parsing, trusted import, stream capture/discard, callback effects, scripted decisions, private synthetic journal and terminal serialization/stream restoration; excludes worker/import/temp-script setup and post-call analysis. Returned context bytes are actual stdout plus stderr bytes, including synthetic baseline pollution. Text counters are Unicode code points and binary counters are bytes; raw bytes/text are never saved in this report.",
        "summary": summaries,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summaries))
    return 0 if all(row["correct"] for row in rows if row["arm"] == "candidate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
