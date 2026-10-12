import contextlib
import gc
import io
import json
import os
import subprocess
import sys
import weakref

import pytest

from apixly_jev_harness import AgentLoop, Task
from apixly_jev_harness.output import TaskOutput
from apixly_jev_harness.task_cli import main


@pytest.fixture(autouse=True)
def offline_inference(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Console fixtures must not call native inference")

    def select_first(parts, *args):
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {"ok": True, "usage_complete": True, "usage": {"input_tokens": 0, "output_tokens": 0}}

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", select_first)


def run_script(tmp_path, source):
    script = tmp_path / "task.py"
    script.write_text(source, encoding="utf-8", newline="\n")
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(["run", str(script), "--goal", "Inspect synthetic state"])
        assert sys.stdout is stdout and sys.stderr is stderr
    return exit_code, stdout.getvalue(), stderr.getvalue()


COMPLETE = """from apixly_jev_harness import Task
workflow = Task(observe=lambda ctx: {'done': True}, verify=lambda ctx, state: state['done'])
"""


def test_import_console_is_discarded_and_terminal_json_stays_parseable(tmp_path):
    exit_code, stdout, stderr = run_script(
        tmp_path,
        "import sys\nprint('PRIVATE_IMPORT')\nprint('PRIVATE_WARNING', file=sys.stderr)\n"
        + COMPLETE,
    )
    packet = json.loads(stdout)
    assert exit_code == 0 and packet["status"] == "done"
    assert stderr == "" and "PRIVATE" not in stdout
    assert packet["task_output"] == {
        "policy": "discard",
        "scope": "python_streams",
        "stdout": {"characters": len("PRIVATE_IMPORT\n"), "binary_bytes": 0},
        "stderr": {"characters": len("PRIVATE_WARNING\n"), "binary_bytes": 0},
    }


def test_observer_and_verifier_console_is_discarded(tmp_path):
    exit_code, stdout, stderr = run_script(
        tmp_path,
        """import sys
from apixly_jev_harness import Task
def observe(ctx):
    print('PRIVATE_OBSERVATION')
    return {'done': True}
def verify(ctx, state):
    print('PRIVATE_VERIFY', file=sys.stderr)
    return state['done']
workflow=Task(observe=observe, verify=verify)
""",
    )
    packet = json.loads(stdout)
    assert exit_code == 0 and packet["status"] == "done"
    assert stderr == "" and "PRIVATE" not in stdout
    assert packet["task_output"]["stdout"]["characters"] > 0
    assert packet["task_output"]["stderr"]["characters"] > 0


@pytest.mark.parametrize("fails", [False, True])
def test_effect_console_does_not_change_completion_or_uncertainty(tmp_path, fails):
    exit_code, stdout, stderr = run_script(
        tmp_path,
        """import sys
from apixly_jev_harness import Task
state={'done': False}
workflow=Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen['done'])
@workflow.tool('Inspect')
def inspect():
    print('PRIVATE_EFFECT')
    print('PRIVATE_EFFECT_ERROR', file=sys.stderr)
    state['done']=True
"""
        + (
            "    raise TimeoutError('PRIVATE_EXCEPTION')\n"
            if fails
            else "    return {'done': True}\n"
        ),
    )
    packet = json.loads(stdout)
    assert packet["status"] == ("execution_uncertain" if fails else "done")
    assert exit_code == (2 if fails else 0)
    assert stderr == "" and "PRIVATE" not in stdout
    assert packet["task_output"]["stdout"]["characters"] == len("PRIVATE_EFFECT\n")


def test_import_exception_restores_streams_and_keeps_fixed_failure(tmp_path):
    exit_code, stdout, stderr = run_script(
        tmp_path, "print('PRIVATE_IMPORT')\nraise ValueError('PRIVATE_EXCEPTION')\n"
    )
    packet = json.loads(stdout)
    assert exit_code == 2 and packet["error_type"] == "ValueError"
    assert packet["status"] == "failed"
    assert stderr == "" and "PRIVATE" not in stdout
    assert "model_calls" not in packet  # Trusted import cannot promise zero effects.


def test_binary_and_unicode_writes_count_units_without_encoding_or_retention(tmp_path):
    exit_code, stdout, stderr = run_script(
        tmp_path,
        "import sys\nsys.stdout.write('中文')\nsys.stdout.buffer.write(b'\\xffPRIVATE')\n"
        "sys.stderr.buffer.write(memoryview(b'PRIVATE_BYTES'))\n" + COMPLETE,
    )
    packet = json.loads(stdout)
    assert exit_code == 0 and packet["status"] == "done"
    assert stderr == "" and "PRIVATE" not in stdout
    assert packet["task_output"]["stdout"] == {"characters": 2, "binary_bytes": 8}
    assert packet["task_output"]["stderr"] == {"characters": 0, "binary_bytes": 13}


def test_empty_writes_do_not_add_task_output_metadata(tmp_path):
    exit_code, stdout, stderr = run_script(
        tmp_path, "import sys\nsys.stdout.write('')\nsys.stderr.write('')\n" + COMPLETE
    )
    assert exit_code == 0 and stderr == ""
    assert "task_output" not in json.loads(stdout)


def test_large_prints_are_counted_without_replaying_contents(tmp_path):
    exit_code, stdout, stderr = run_script(tmp_path, "print('X' * 1000000)\n" + COMPLETE)
    packet = json.loads(stdout)
    assert exit_code == 0 and stderr == "" and len(stdout) < 2000
    assert packet["task_output"]["stdout"]["characters"] == 1000001


def test_discard_sink_does_not_retain_written_objects():
    class Payload(str):
        pass

    output = TaskOutput()
    payload = Payload("PRIVATE" * 10000)
    reference = weakref.ref(payload)
    assert output.stdout.write(payload) == len(payload)
    del payload
    gc.collect()
    assert reference() is None
    assert output.summary()["stdout"]["characters"] == 70000


def test_stream_write_return_values_and_binary_units_are_preserved(tmp_path):
    exit_code, stdout, stderr = run_script(
        tmp_path,
        "import sys, array\nassert sys.stdout.write('abc') == 3\n"
        "assert sys.stderr.buffer.write(memoryview(array.array('I', [1, 2]))) == 8\n"
        "sys.stdout.flush()\nsys.stderr.buffer.flush()\n" + COMPLETE,
    )
    packet = json.loads(stdout)
    assert exit_code == 0 and packet["status"] == "done" and stderr == ""
    assert packet["task_output"]["stdout"]["characters"] == 3
    assert packet["task_output"]["stderr"]["binary_bytes"] == 8


@pytest.mark.parametrize("exception", ["SystemExit", "KeyboardInterrupt"])
def test_cli_interrupts_restore_streams_and_raise_quiet_nonzero_exit(tmp_path, exception):
    script = tmp_path / "task.py"
    script.write_text(
        "print('PRIVATE_IMPORT')\nraise " + exception + "()\n", encoding="utf-8", newline="\n"
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit) as interrupted:
            main(["run", str(script), "--goal", "Inspect"])
        assert interrupted.value.code == (130 if exception == "KeyboardInterrupt" else 1)
        assert sys.stdout is stdout and sys.stderr is stderr
    assert stdout.getvalue() == stderr.getvalue() == ""


@pytest.mark.parametrize(
    "exception, argument, code",
    [
        ("SystemExit", "'PRIVATE_EXIT_TEXT'", 1),
        ("SystemExit", "0", 1),
        ("SystemExit", "None", 1),
        ("SystemExit", "256", 1),
        ("SystemExit", "7", 7),
        ("KeyboardInterrupt", "'PRIVATE_INTERRUPT_TEXT'", 130),
    ],
)
def test_real_cli_interrupts_exit_quietly_without_success_or_terminal_packet(
    tmp_path, exception, argument, code
):
    script = tmp_path / "task.py"
    script.write_text(
        "import sys\nprint('PRIVATE_IMPORT')\nprint('PRIVATE_STDERR',file=sys.stderr)\n"
        + f"raise {exception}({argument})\n",
        newline="\n",
    )
    # Fixtures exit during import, before any workflow or inference; no credentials needed.
    env = {key: value for key, value in os.environ.items() if not key.startswith("TYPESAFE_")}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apixly_jev_harness.cli import entrypoint; entrypoint()",
            "run",
            str(script),
            "--goal",
            "Inspect",
        ],
        env=env,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == code
    assert result.stdout == result.stderr == b""


@pytest.mark.parametrize("exception, code", [("KeyboardInterrupt", 130), ("SystemExit", 1)])
def test_interrupted_effect_is_not_retried_or_reported_as_safe_failure(tmp_path, exception, code):
    script = tmp_path / "task.py"
    script.write_text(
        r"""from pathlib import Path
from apixly_jev_harness import Task
workflow=Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False)
@workflow.tool('Inspect')
def inspect():
    marker=Path(__file__).with_suffix('.effect')
    marker.write_text((marker.read_text() if marker.exists() else '')+'effect\n')
    print('PRIVATE_EFFECT')
"""
        + f"    raise {exception}()\n"
    )
    archive = tmp_path / "run.jsonl"
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit) as interrupted:
            main(["run", str(script), "--goal", "Inspect", "--archive", str(archive)])
    assert interrupted.value.code == code
    assert stdout.getvalue() == stderr.getvalue() == ""
    assert script.with_suffix(".effect").read_text() == "effect\n"
    events = [json.loads(line) for line in archive.read_text().splitlines()]
    assert events[-1]["event"] == "intent"
    assert not any(event["event"] == "terminal" for event in events)


def test_direct_sdk_console_behavior_is_unchanged(capsys, tmp_path):
    def observe(ctx):
        print("SDK_CONSOLE")
        return {"done": True}

    result = AgentLoop().run(
        Task(observe=observe, verify=lambda ctx, state: state["done"]),
        goal="Observe completion",
        archive=tmp_path / "run.jsonl",
    )
    assert result["status"] == "done"
    assert capsys.readouterr().out == "SDK_CONSOLE\n"


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit("PRIVATE_EXIT")])
def test_non_run_interrupts_keep_original_behavior(monkeypatch, tmp_path, interruption):
    from pathlib import Path

    def interrupted_open(*args, **kwargs):
        raise interruption

    monkeypatch.setattr(Path, "open", interrupted_open)
    with pytest.raises(type(interruption)) as raised:
        main(["init-task", str(tmp_path / "task.py")])
    assert raised.value is interruption
