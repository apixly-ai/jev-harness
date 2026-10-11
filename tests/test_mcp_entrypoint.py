import io
import json
import sys

import pytest
from test_toolkit_session import session

from apixly_jev_harness.mcp import main, serve


def test_public_mcp_loader_supports_dataclass_scripts_and_suppresses_cleanup(
    tmp_path, monkeypatch, capsys
):
    script = tmp_path / "task.py"
    script.write_text("""from __future__ import annotations
from dataclasses import dataclass
from apixly_jev_harness import Task
@dataclass
class Row:
    value: int = 0
class Pack:
    def close(self): print('private cleanup')
workflow = Task(observe=lambda c: {'value': Row().value}, verify=lambda c, s: False)
workflow.toolkits = [Pack()]
""")
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"id":1,"method":"initialize"}\n'))
    assert main([str(script), "--goal", "Inspect", "--direct-only"]) == 0
    rows = capsys.readouterr().out.splitlines()
    assert len(rows) == 1
    from apixly_jev_harness import __version__

    assert json.loads(rows[0])["result"]["serverInfo"]["version"] == __version__
    assert "_jev_mcp_task" not in sys.modules


def test_mcp_stale_client_snapshot_is_rejected_after_successful_operation():
    client, state = session()
    old = client.observe()["state_ref"]
    client.operate("advance", {"amount": "0"})
    request = {
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "operate",
            "arguments": {"tool": "advance", "parameters": {"amount": "0"}, "state_ref": old},
        },
    }
    out = io.StringIO()
    serve(client, source=io.StringIO(json.dumps(request) + "\n"), destination=out)
    assert json.loads(out.getvalue())["result"]["isError"] is True
    assert state["value"] == 1


def test_mcp_requires_current_state_reference_for_argument_operations():
    client, _ = session()
    out = io.StringIO()
    serve(client, source=io.StringIO('{"id":1,"method":"tools/list"}\n'), destination=out)
    listed = json.loads(out.getvalue())["result"]["tools"]
    for tool in listed:
        if tool["name"] in ("operate", "arguments"):
            assert "state_ref" in tool["inputSchema"]["required"]


def test_mcp_reads_with_a_finite_line_bound():
    class Source:
        def readline(self, size=-1):
            assert 0 < size <= 1_000_001
            return "x" * size

    client, _ = session()
    with pytest.raises(ValueError, match="too_large"):
        serve(client, source=Source(), destination=io.StringIO())


def test_mcp_null_snapshot_cannot_bypass_advertised_string_contract():
    client, state = session()
    client.observe()
    request = {
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "operate",
            "arguments": {"tool": "advance", "parameters": {"amount": "0"}, "state_ref": None},
        },
    }
    out = io.StringIO()
    serve(client, source=io.StringIO(json.dumps(request) + "\n"), destination=out)
    assert json.loads(out.getvalue())["result"]["isError"] is True
    assert state["value"] == 0


@pytest.mark.parametrize("field", ["--inputs", "--context"])
def test_mcp_null_json_configuration_does_not_import_script(tmp_path, field, capsys):
    marker = tmp_path / "imported"
    script = tmp_path / "task.py"
    script.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nworkflow = None\n")
    assert main([str(script), "--goal", "Inspect", field, "null"]) == 2
    assert not marker.exists()
    assert json.loads(capsys.readouterr().out)["phase"] == "configuration"


def test_public_mcp_parser_keeps_the_fixed_cli_argument_packet(capsys):
    assert main(["task.py", "--goal", "Inspect", "--not-an-option", "private-value"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "failed",
        "complete": False,
        "phase": "arguments",
        "code": "invalid_command_arguments",
        "script_loaded": False,
        "model_calls": 0,
    }
    assert captured.err == ""
