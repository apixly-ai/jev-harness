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
    script.write_text(
        """from __future__ import annotations
from dataclasses import dataclass
from apixly_jev_harness import Task
@dataclass
class Row:
    value: int = 0
class Pack:
    def close(self): print('private cleanup')
workflow = Task(observe=lambda c: {'value': Row().value}, verify=lambda c, s: False)
workflow.toolkits = [Pack()]
""",
        newline="\n",
    )
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
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nworkflow = None\n", newline="\n"
    )
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


def test_list_advertises_bound_goal_without_materializing_or_mutating_session():
    from apixly_jev_harness import Task, TaskScript, ToolkitSession

    calls = []

    def build(inputs):
        calls.append(1)
        return Task(observe=lambda c: {}, verify=lambda c, s: False)

    client = ToolkitSession(
        TaskScript(build), goal="Investigate release requirements", max_steps=17, timeout_seconds=90
    )
    out = io.StringIO()
    serve(client, source=io.StringIO('{"id":1,"method":"tools/list"}\n'), destination=out)
    tools = json.loads(out.getvalue())["result"]["tools"]
    run = next(t for t in tools if t["name"] == "run_task")
    assert "Jev Harness" in run["description"]
    assert "Investigate release requirements" in run["description"]
    assert run["outputSchema"]["properties"]["complete"]["type"] == "boolean"
    assert calls == [] and client.steps == 0 and client.events == []


def test_mcp_structured_terminal_matches_text_without_losing_unknown_usage(monkeypatch):
    client, _ = session()
    packet = {
        "status": "needs_review",
        "complete": False,
        "steps": 0,
        "telemetry": {"usage": None, "usage_complete": False},
    }
    monkeypatch.setattr(client, "delegate", lambda: packet)
    out = io.StringIO()
    serve(
        client,
        source=io.StringIO(
            '{"id":1,"method":"tools/call","params":{"name":"run_task","arguments":{}}}\n'
        ),
        destination=out,
    )
    r = json.loads(out.getvalue())["result"]
    assert r["structuredContent"] == packet
    assert json.loads(r["content"][0]["text"]) == packet
    assert r["structuredContent"]["telemetry"]["usage"] is None


def test_initialize_explains_both_routes_without_acquiring_task_state():
    client, state = session()
    out = io.StringIO()
    serve(client, source=io.StringIO('{"id":1,"method":"initialize"}\n'), destination=out)
    guidance = json.loads(out.getvalue())["result"]["instructions"]
    assert "run_task" in guidance[:512] and "operate" in guidance[:512]
    assert "Jev Harness" in guidance[:512]
    assert state["value"] == 0 and client.events == []


def test_caller_can_expose_a_purpose_named_goal_operation_without_changing_execution(monkeypatch):
    client, _ = session()
    replies = io.StringIO()
    packet = {
        "status": "done",
        "complete": True,
        "steps": 0,
        "telemetry": {"usage": None, "usage_complete": False},
    }
    calls = []
    monkeypatch.setattr(client, "delegate", lambda: calls.append(1) or packet)
    requests = [
        {"id": 1, "method": "tools/list"},
        {
            "id": 2,
            "method": "tools/call",
            "params": {"name": "collect_source_evidence", "arguments": {}},
        },
    ]
    serve(
        client,
        source=io.StringIO("".join(json.dumps(r) + "\n" for r in requests)),
        destination=replies,
        execution_name="collect_source_evidence",
    )
    rows = [json.loads(line) for line in replies.getvalue().splitlines()]
    names = {x["name"] for x in rows[0]["result"]["tools"]}
    assert "collect_source_evidence" in names and "run_task" not in names
    assert rows[1]["result"]["structuredContent"] == packet
    assert calls == [1]


def test_invalid_execution_name_fails_before_loading_trusted_script(tmp_path, capsys):
    marker = tmp_path / "imported"
    script = tmp_path / "task.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nworkflow = None\n", newline="\n"
    )
    assert main([str(script), "--goal", "Inspect", "--execution-name", "operate"]) == 2
    assert not marker.exists()
    assert json.loads(capsys.readouterr().out)["phase"] == "configuration"


def test_lazy_factory_does_not_change_advertised_tool_names_after_first_inspection():
    from apixly_jev_harness import Task, TaskScript, ToolkitSession
    from apixly_jev_harness.mcp import describe_tools

    script = TaskScript(lambda inputs: Task(observe=lambda c: {}, verify=lambda c, s: False))
    client = ToolkitSession(script, goal="Inspect regular registered task")
    before = {x["name"] for x in describe_tools(client)}
    client.observe()
    assert {x["name"] for x in describe_tools(client)} == before
    with pytest.raises(ValueError, match="evidence_report"):
        client.read_report()


def test_stdio_mcp_is_utf8_even_when_the_locale_codec_is_not(tmp_path):
    import os
    import subprocess

    script = tmp_path / "task.py"
    script.write_text(
        "from apixly_jev_harness import Task\n"
        "workflow = Task(observe=lambda c: {'ok': True}, verify=lambda c, s: False)\n",
        encoding="utf-8",
        newline="\n",
    )
    goal = "保存草稿 → 预览收件箱 ✓"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHONIOENCODING", "PYTHONUTF8")
    }
    # Only the stdio codec is non-UTF-8 (argv decoding stays intact on every platform).
    environment.update(PYTHONIOENCODING="latin-1", PYTHONUTF8="0")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "apixly_jev_harness.mcp",
            str(script),
            "--goal",
            goal,
        ],
        input=b'{"id":1,"method":"initialize"}\n{"id":2,"method":"tools/list"}\n',
        capture_output=True,
        env=environment,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr[-400:]
    rows = [json.loads(line) for line in completed.stdout.decode("utf-8").splitlines()]
    assert [row["id"] for row in rows] == [1, 2]
    assert goal in json.dumps(rows, ensure_ascii=False)
