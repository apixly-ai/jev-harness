import json
import subprocess
import sys

import pytest

from apixly_jev_harness.task_cli import main


@pytest.mark.parametrize(
    ("source", "line"),
    [
        ("workflow = None\nreturn\n", 2),
        ("workflow = None\nbreak\n", 2),
        ("workflow = None\ncontinue\n", 2),
        ("workflow = None\ndef duplicate(value, value):\n    pass\n", 2),
        ("workflow = None\ndef missing_scope():\n    nonlocal unknown\n", 3),
    ],
)
def test_parseable_but_uncompilable_script_is_rejected(tmp_path, capsys, source, line):
    script = tmp_path / "task.py"
    script.write_text(source, encoding="utf-8", newline="\n")
    assert main(["check-task", str(script)]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["code"] == "invalid_python"
    assert packet["line"] == line
    assert packet["model_calls"] == 0
    assert "source" not in packet


def test_annotation_without_assignment_does_not_export_workflow(tmp_path, capsys):
    script = tmp_path / "task.py"
    script.write_text("workflow: object\n", encoding="utf-8", newline="\n")
    assert main(["check-task", str(script)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "workflow_export_missing"
    script.write_text("workflow: object = None\n", encoding="utf-8", newline="\n")
    assert main(["check-task", str(script)]) == 0


def test_compilation_never_executes_imports_effects_or_model_calls(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Static checking must not load or execute the script")

    monkeypatch.setattr(
        "apixly_jev_harness.task_cli.importlib.util.spec_from_file_location", forbidden
    )
    monkeypatch.setattr("apixly_jev_harness.task_cli.AgentLoop.run", forbidden)
    marker = tmp_path / "effect.txt"
    script = tmp_path / "task.py"
    script.write_text(
        "import module_that_does_not_exist\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('must never run')\n"
        "raise RuntimeError('PRIVATE_EXCEPTION_TEXT')\n"
        "workflow = None\n",
        newline="\n",
    )
    assert main(["check-task", str(script)]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["model_calls"] == 0
    assert not marker.exists()
    assert "PRIVATE_EXCEPTION_TEXT" not in json.dumps(packet)


def test_non_utf8_source_returns_compact_failure(tmp_path, capsys):
    script = tmp_path / "task.py"
    script.write_bytes(b"workflow = None\n# PRIVATE_SOURCE_MARKER \xff\n")
    assert main(["check-task", str(script)]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet == {"ok": False, "code": "source_not_utf8", "model_calls": 0}
    assert "PRIVATE_SOURCE_MARKER" not in json.dumps(packet)


def test_compiler_warning_does_not_print_source(tmp_path):
    script = tmp_path / "task.py"
    script.write_text(
        "workflow = None\nif 'PRIVATE_SOURCE_FRAGMENT' is 'PRIVATE_SOURCE_FRAGMENT':\n    pass\n",
        newline="\n",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apixly_jev_harness.cli import entrypoint; entrypoint()",
            "check-task",
            "task.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "PRIVATE_SOURCE_FRAGMENT" not in result.stdout + result.stderr
    packet = json.loads(result.stdout)
    assert packet["ok"] is True
    assert packet["source_warnings"] == [{"code": "python_source_warning", "line": 2}]
