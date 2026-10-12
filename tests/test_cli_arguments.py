import contextlib
import io
import json
import os
import subprocess
import sys

import pytest

from apixly_jev_harness.task_cli import main


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["PRIVATE_COMMAND"],
        ["run"],
        ["run", "task.py"],
        ["run", "task.py", "--goal"],
        ["run", "task.py", "--goal", "Inspect", "--max-steps", "PRIVATE_VALUE"],
        ["run", "task.py", "--goal", "Inspect", "--timeout", "PRIVATE_VALUE"],
        ["run", "task.py", "--goal", "Inspect", "--m", "PRIVATE_VALUE"],
        ["run", "task.py", "--goal", "Inspect", "--unknown", "PRIVATE_VALUE"],
        ["run", "task.py", "extra", "--goal", "Inspect"],
        ["check-task"],
        ["check-task", "task.py", "PRIVATE_EXTRA"],
        ["init-task"],
        ["spec", "PRIVATE_EXTRA"],
        ["skill", "--unknown", "PRIVATE_VALUE"],
        ["PRIVATE_\ud800"],
    ],
)
def test_argument_parser_failure_is_safe_json_before_dispatch(argv, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Argument failure must not read/load/execute a task or infer")

    monkeypatch.setattr(
        "apixly_jev_harness.task_cli.importlib.util.spec_from_file_location", forbidden
    )
    monkeypatch.setattr("apixly_jev_harness.task_cli.Path.read_text", forbidden)
    monkeypatch.setattr("apixly_jev_harness.task_cli.Path.open", forbidden)
    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    assert exit_code == 2
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue()) == {
        "status": "failed",
        "complete": False,
        "phase": "arguments",
        "code": "invalid_command_arguments",
        "script_loaded": False,
        "model_calls": 0,
    }
    assert "PRIVATE" not in stdout.getvalue()


@pytest.mark.parametrize("argv", [["--help"], ["run", "--help"], ["run", "--help", "--unknown"]])
def test_help_keeps_text_exit_and_original_precedence(argv, capsys):
    with pytest.raises(SystemExit) as stopped:
        main(argv)
    assert stopped.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out and captured.err == ""


def test_argument_failure_does_not_create_init_script(tmp_path, capsys):
    script = tmp_path / "task.py"
    assert main(["init-task", str(script), "--unknown"]) == 2
    assert not script.exists()
    assert json.loads(capsys.readouterr().out)["phase"] == "arguments"


def test_configuration_failure_remains_distinct_and_abbreviations_still_parse(tmp_path, capsys):
    script = tmp_path / "task.py"
    script.write_text("raise AssertionError('Must not load')\n", encoding="utf-8", newline="\n")
    assert main(["run", str(script), "--go", "Inspect", "--max-s", "0"]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["phase"] == "configuration"
    assert packet["code"] == "invalid_run_configuration"


def test_real_cli_parser_failure_has_exact_json_and_no_raw_stderr(tmp_path):
    script = tmp_path / "task.py"
    script.write_text("raise AssertionError('Must not load')\n", encoding="utf-8", newline="\n")
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
            "--max-steps",
            "PRIVATE_ARGUMENT_VALUE",
        ],
        capture_output=True,
        env=env,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2 and result.stderr == b""
    packet = json.loads(result.stdout)
    assert packet["code"] == "invalid_command_arguments" and packet["model_calls"] == 0
    assert b"PRIVATE" not in result.stdout


def test_default_sys_argv_parse_failure_does_not_echo_program_name(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["PRIVATE_PROGRAM", "PRIVATE_COMMAND"])
    assert main() == 2
    captured = capsys.readouterr()
    assert captured.err == "" and "PRIVATE" not in captured.out
    assert json.loads(captured.out)["phase"] == "arguments"


def test_parser_exception_payload_contains_only_fixed_code():
    from apixly_jev_harness.task_cli import _ArgumentParser, _CLIArgumentError

    with pytest.raises(_CLIArgumentError) as raised:
        _ArgumentParser().error("PRIVATE_DIAGNOSTIC")
    assert raised.value.args == ("invalid_command_arguments",)
    assert raised.value.__dict__ == {}
