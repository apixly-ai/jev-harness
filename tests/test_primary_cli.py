import importlib
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = [
    {
        "name": "read",
        "description": "Read one newly discovered source",
        "parameters": {
            "ref": {"description": "A current source", "allowed_refs": ["source-a", "source-b"]}
        },
    },
    {"name": "finish", "description": "Request independent verification", "parameters": {}},
]
CONTEXT = {"goal": "Find evidence", "observation": {"discovered": ["source-a", "source-b"]}}
USAGE = {
    "input_tokens": 90,
    "cached_input_tokens": 20,
    "output_tokens": 12,
    "reasoning_output_tokens": 4,
}
CHOICE = {"tool": "read", "arguments": {"ref": "source-b"}}
PRIVATE_MARKER = "SYNTHETIC_PRIMARY_PRIVATE_DETAIL"


@pytest.fixture
def primary(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))

    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must never launch a real model process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    return importlib.import_module("primary_cli")


def events(choice=CHOICE, usage=USAGE, extra=()):
    return "\n".join(
        json.dumps(event)
        for event in [
            {"type": "thread.started", "thread_id": "synthetic", "model": "unverified-claim"},
            {"type": "turn.started"},
            *extra,
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(choice)},
            },
            {"type": "turn.completed", "usage": usage},
        ]
    )


def run_result(stdout=None, returncode=0):
    return SimpleNamespace(
        stdout=events() if stdout is None else stdout,
        stderr=PRIVATE_MARKER,
        returncode=returncode,
    )


def test_choice_binds_only_allowed_refs_and_keeps_resolved_model_unknown(primary, monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_BASE_URL", "https://synthetic-production.invalid")
    monkeypatch.setenv("OPENAI_API_KEY", PRIVATE_MARKER)
    monkeypatch.setenv("CODEX_API_KEY", PRIVATE_MARKER)
    monkeypatch.setenv("TYPESAFE_API_KEY", PRIVATE_MARKER)
    monkeypatch.setenv("JEV_TEXT_API_KEY", PRIVATE_MARKER)
    clock = iter([10.0, 10.75])
    monkeypatch.setattr(primary.time, "perf_counter", lambda: next(clock))

    def runner(command, **kwargs):
        calls.append(command)
        assert "--ignore-user-config" in command and "--ephemeral" in command
        assert command[command.index("--model") + 1] == "gpt-6.1-sol"
        assert 'model_provider="openai"' in command
        assert 'web_search="disabled"' in command
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert "--json" in command and command[-1] == "-"
        for feature in ("shell_tool", "unified_exec", "multi_agent", "apps", "plugins"):
            assert ["--disable", feature] == command[command.index(feature) - 1 :][:2]
        assert all(
            name not in kwargs["env"]
            for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "CODEX_API_KEY", "TYPESAFE_API_KEY")
        )
        assert not any(name.startswith("JEV_TEXT_") for name in kwargs["env"])
        assert kwargs["shell"] is False
        assert PRIVATE_MARKER not in kwargs["input"]
        assert json.loads(kwargs["input"].split("\n", 1)[1])["tools"] == TOOLS
        schema_path = Path(command[command.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text())
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["tool", "arguments"]
        assert schema["properties"]["tool"]["enum"] == ["read", "finish"]
        assert schema_path.stat().st_mode & 0o077 == 0
        assert Path(kwargs["cwd"]).samefile(schema_path.parent)
        return run_result()

    result = primary.choose_tool(TOOLS, CONTEXT, model="gpt-6.1-sol", runner=runner)
    assert len(calls) == 1
    assert result["ok"] and result["status"] == "completed"
    assert result["choice"] == CHOICE
    assert result["model_requested"] == "gpt-6.1-sol"
    assert result["model_resolved"] is None
    assert result["usage_complete"] is True and result["usage"] == USAGE
    assert result["whole_process_seconds"] == 0.75
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize(
    "choice",
    [
        {"tool": "invented", "arguments": {}},
        {"tool": "read", "arguments": {"ref": "unknown-source"}},
        {"tool": "read", "arguments": {"ref": "source-a", "command": PRIVATE_MARKER}},
        {"tool": "read", "arguments": {}},
        {"tool": "read", "arguments": {"ref": 1}},
        {"tool": "finish", "arguments": {"ref": "source-a"}},
        {"tool": "finish", "arguments": {}, "extra": PRIVATE_MARKER},
    ],
)
def test_bad_choice_is_rejected_without_losing_known_completed_usage(primary, choice):
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(events(choice=choice)),
    )
    assert not result["ok"] and result["reason"] == "invalid_choice"
    assert result["choice"] is None
    assert result["usage_complete"] and result["usage"] == USAGE
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {**USAGE, "input_tokens": True},
        {**USAGE, "output_tokens": -1},
        {**USAGE, "cached_input_tokens": 91},
        {**USAGE, "reasoning_output_tokens": 13},
    ],
)
def test_unknown_or_invalid_terminal_usage_never_becomes_zero(primary, usage):
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(events(usage=usage)),
    )
    assert result["choice"] == CHOICE
    assert result["usage_complete"] is False and result["usage"] is None


@pytest.mark.parametrize(
    "kind", ["command_execution", "file_change", "mcp_tool_call", "web_search", "unknown_tool"]
)
def test_native_tool_activity_cannot_be_accepted_as_pure_decision(primary, kind):
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(
            events(
                extra=[{"type": "item.started", "item": {"type": kind, "command": PRIVATE_MARKER}}]
            )
        ),
    )
    assert not result["ok"] and result["reason"] == "unexpected_item_activity"
    assert result["choice"] is None and result["unexpected_item_count"] == 1
    assert result["usage"] == USAGE
    assert PRIVATE_MARKER not in json.dumps(result)


def test_failed_cli_retains_reported_tokens_but_marks_whole_attempt_unknown(primary):
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(returncode=1),
    )
    assert result["reason"] == "cli_failed" and result["choice"] is None
    assert result["usage_complete"] is False and result["usage"] is None
    assert result["reported_terminal_usage"] == USAGE
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize("interrupt", ["timeout", "keyboard", "launch"])
def test_interrupted_or_unlaunched_call_is_not_retried_or_billed_as_zero(primary, interrupt):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if interrupt == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=events())
        if interrupt == "keyboard":
            raise KeyboardInterrupt(PRIVATE_MARKER)
        raise OSError(PRIVATE_MARKER)

    result = primary.choose_tool(TOOLS, CONTEXT, model="gpt-6.1-sol", runner=runner)
    assert len(calls) == 1 and result["choice"] is None
    assert result["status"] == ("failed" if interrupt == "launch" else "interrupted")
    assert result["usage_complete"] is False and result["usage"] is None
    if interrupt == "timeout":
        assert result["reported_terminal_usage"] == USAGE
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize("stdout", [PRIVATE_MARKER, "", events() + "\n" + events()])
def test_missing_malformed_or_multiple_terminal_events_leave_usage_unknown(primary, stdout):
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(stdout),
    )
    assert not result["ok"] and result["choice"] is None
    assert result["usage_complete"] is False and result["usage"] is None
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize(
    "tools",
    [
        [],
        [{**TOOLS[0], "name": ""}],
        [TOOLS[0], TOOLS[0]],
        [{**TOOLS[0], "parameters": {"ref": {"allowed_refs": []}}}],
    ],
)
def test_invalid_manifest_is_rejected_before_process_launch(primary, tools):
    with pytest.raises(ValueError, match="invalid_tool_manifest"):
        primary.choose_tool(tools, CONTEXT, model="gpt-6.1-sol")


def test_no_parameter_tool_and_missing_optional_reasoning_usage_work(primary):
    usage = {key: value for key, value in USAGE.items() if key != "reasoning_output_tokens"}
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(
            events({"tool": "finish", "arguments": {}}, usage)
        ),
    )
    assert result["ok"] and result["choice"] == {"tool": "finish", "arguments": {}}
    assert result["usage"] == usage and result["usage_complete"]


def test_single_mcp_session_has_only_explicit_server_and_no_artifact_success_claim(primary):
    calls = []
    schema = {
        "type": "object",
        "properties": {"artifact": {"type": "string"}},
        "required": ["artifact"],
        "additionalProperties": False,
    }

    def runner(command, **kwargs):
        calls.append(command)
        assert 'mcp_servers.jev_eval.command="synthetic-python"' in command
        assert 'mcp_servers.jev_eval.args=["synthetic-server.py", "--mode", "auto"]' in command
        assert "mcp_servers.jev_eval.required=true" in command
        assert "--ignore-user-config" in command and 'model_provider="openai"' in command
        assert kwargs["input"] == "Use either available method to complete the task."
        assert json.loads(Path(command[command.index("--output-schema") + 1]).read_text()) == schema
        return run_result(
            events(
                {"artifact": "unverified-artifact.json"},
                extra=[
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "mcp-1",
                            "type": "mcp_tool_call",
                            "server": "jev_eval",
                            "tool": "operate",
                            "arguments": PRIVATE_MARKER,
                        },
                    }
                ],
            )
        )

    result = primary.run_mcp_session(
        "Use either available method to complete the task.",
        schema,
        model="gpt-6.1-sol",
        mcp_command="synthetic-python",
        mcp_args=["synthetic-server.py", "--mode", "auto"],
        runner=runner,
    )
    assert len(calls) == 1 and result["ok"]
    assert result["completion_scope"] == "cli_process_not_task_artifact"
    assert "complete" not in result and result["model_resolved"] is None
    assert result["final_output"] == {"artifact": "unverified-artifact.json"}
    assert result["usage"] == USAGE and PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize("kind", [[], {}, None])
def test_malformed_cli_item_type_is_fixed_failure_not_parser_crash(primary, kind):
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(
            events(extra=[{"type": "item.started", "item": {"type": kind}}])
        ),
    )
    assert result["reason"] == "unexpected_item_activity" and result["choice"] is None
    assert result["usage"] == USAGE


def test_other_mcp_server_does_not_gain_execution_qualification(primary):
    result = primary.run_mcp_session(
        "Complete the permitted task.",
        {"type": "object"},
        model="gpt-6.1-sol",
        mcp_command="synthetic-python",
        mcp_args=[],
        runner=lambda *args, **kwargs: run_result(
            events(
                extra=[
                    {"type": "item.started", "item": {"type": "mcp_tool_call", "server": "other"}}
                ]
            )
        ),
    )
    assert not result["ok"] and result["reason"] == "unexpected_item_activity"
    assert result["final_output"] is None and result["usage"] == USAGE


def test_failed_cli_private_logs_are_exact_opt_in_and_owner_only(primary, tmp_path):
    stdout = PRIVATE_MARKER + " stdout\n"
    stderr = PRIVATE_MARKER + " stderr\n"
    event_path, diagnostic_path = tmp_path / "private-events.jsonl", tmp_path / "private-stderr.log"
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        private_events_path=event_path,
        private_diagnostics_path=diagnostic_path,
        runner=lambda *args, **kwargs: SimpleNamespace(stdout=stdout, stderr=stderr, returncode=1),
    )
    assert event_path.read_text() == stdout and diagnostic_path.read_text() == stderr
    for path in (event_path, diagnostic_path):
        assert path.stat().st_mode & 0o777 == 0o600
    assert result["reason"] == "cli_failed" and result["usage"] is None
    assert result["usage_complete"] is False and result["reported_terminal_usage"] is None
    assert PRIVATE_MARKER not in json.dumps(result)
    assert str(event_path) not in json.dumps(result)
    assert str(diagnostic_path) not in json.dumps(result)


def test_default_failed_call_does_not_persist_raw_streams(primary, monkeypatch, tmp_path):
    monkeypatch.setattr(
        primary.tempfile, "TemporaryDirectory", lambda **kwargs: nullcontext(str(tmp_path))
    )
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        runner=lambda *args, **kwargs: run_result(PRIVATE_MARKER, returncode=1),
    )
    assert {path.name for path in tmp_path.iterdir()} == {"output-schema.json"}
    assert PRIVATE_MARKER not in (tmp_path / "output-schema.json").read_text()
    assert PRIVATE_MARKER not in json.dumps(result)
    assert result["usage"] is None


def test_mcp_session_private_logs_do_not_change_known_terminal_usage(primary, tmp_path):
    stdout = events({"artifact": "private-result.json"})
    result = primary.run_mcp_session(
        "Complete the permitted task.",
        {"type": "object"},
        model="gpt-6.1-sol",
        mcp_command="synthetic-python",
        mcp_args=[],
        private_events_path=tmp_path / "mcp-events.jsonl",
        private_diagnostics_path=tmp_path / "mcp-stderr.log",
        runner=lambda *args, **kwargs: run_result(stdout),
    )
    assert (tmp_path / "mcp-events.jsonl").read_text() == stdout
    assert (tmp_path / "mcp-stderr.log").read_text() == PRIVATE_MARKER
    assert result["ok"] and result["usage_complete"] and result["usage"] == USAGE
    assert PRIVATE_MARKER not in json.dumps(result)


def test_timeout_preserves_partial_binary_streams_but_usage_stays_unknown(primary, tmp_path):
    stdout, stderr = b"\xff" + PRIVATE_MARKER.encode(), b"\x00" + PRIVATE_MARKER.encode()

    def interrupted(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=stdout, stderr=stderr)

    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        private_events_path=tmp_path / "partial-events.bin",
        private_diagnostics_path=tmp_path / "partial-stderr.bin",
        runner=interrupted,
    )
    assert (tmp_path / "partial-events.bin").read_bytes() == stdout
    assert (tmp_path / "partial-stderr.bin").read_bytes() == stderr
    assert result["status"] == "interrupted" and result["usage"] is None
    assert result["usage_complete"] is False and PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.parametrize("symlink", [False, True])
def test_private_log_destination_never_overwrites_and_fails_before_launch(
    primary, tmp_path, symlink
):
    owner = tmp_path / "owner.txt"
    owner.write_text("owner evidence")
    destination = tmp_path / "occupied.log"
    if symlink:
        destination.symlink_to(owner)
    else:
        destination.write_text("prior private log")
    with pytest.raises(FileExistsError):
        primary.choose_tool(
            TOOLS,
            CONTEXT,
            model="gpt-6.1-sol",
            private_diagnostics_path=destination,
        )
    assert owner.read_text() == "owner evidence"
    if not symlink:
        assert destination.read_text() == "prior private log"


def test_private_log_fsync_failure_cannot_turn_success_into_unknown(primary, monkeypatch, tmp_path):
    def broken_fsync(fd):
        raise OSError(PRIVATE_MARKER)

    monkeypatch.setattr(primary.os, "fsync", broken_fsync)
    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        private_events_path=tmp_path / "events.jsonl",
        private_diagnostics_path=tmp_path / "stderr.log",
        runner=lambda *args, **kwargs: run_result(),
    )
    assert result["ok"] and result["choice"] == CHOICE and result["usage"] == USAGE
    assert result["private_log_failures"] == ["stdout", "stderr"]
    assert PRIVATE_MARKER not in json.dumps(result)


def test_opt_in_logs_capture_binary_transport_without_newline_or_decode_loss(primary, tmp_path):
    stdout, stderr = b"invalid\xff\r\n", b"diagnostic\r\n" + PRIVATE_MARKER.encode()

    def runner(command, **kwargs):
        assert kwargs["text"] is False
        assert isinstance(kwargs["input"], bytes)
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=1)

    result = primary.choose_tool(
        TOOLS,
        CONTEXT,
        model="gpt-6.1-sol",
        private_events_path=tmp_path / "binary-events.log",
        private_diagnostics_path=tmp_path / "binary-stderr.log",
        runner=runner,
    )
    assert (tmp_path / "binary-events.log").read_bytes() == stdout
    assert (tmp_path / "binary-stderr.log").read_bytes() == stderr
    assert result["usage"] is None and result["usage_complete"] is False
    assert PRIVATE_MARKER not in json.dumps(result)


def test_mcp_continuous_loop_keeps_code_execution_host_available(primary):
    commands = []
    primary.run_mcp_session(
        "Inspect",
        {},
        model="gpt-6.1-sol",
        mcp_command="python",
        mcp_args=[],
        runner=lambda command, **kwargs: commands.append(command) or run_result(),
    )
    c = commands[0]
    assert not any(c[i : i + 2] == ["--disable", "code_mode_host"] for i in range(len(c) - 1))
    assert "--config" in c and "project_doc_max_bytes=0" in c


def test_owned_synthetic_mcp_scope_is_usable_under_noninteractive_approval_policy(primary):
    commands = []
    primary.run_mcp_session(
        "Inspect",
        {},
        model="gpt-6.1-sol",
        mcp_command="python",
        mcp_args=[],
        runner=lambda command, **kwargs: commands.append(command) or run_result(),
    )
    assert 'mcp_servers.jev_eval.default_tools_approval_mode="auto"' in commands[0]
