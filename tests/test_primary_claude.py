"""Claude primary adapter: neutral inventory, scoped tools, retained identity and usage."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("primary_claude")


def stream(*, tools=None, calls=(), result=None, servers=None, extra=()):
    init = {
        "type": "system",
        "subtype": "init",
        "model": "claude-opus-5-5",
        "tools": tools if tools is not None else ["StructuredOutput", "mcp__jev_eval__act"],
        "mcp_servers": servers or [{"name": "jev_eval", "status": "connected"}],
        "skills": [],
        "slash_commands": [],
        "permissionMode": "dontAsk",
    }
    assistant = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-5-5",
            "content": [{"type": "tool_use", "name": name, "input": {}} for name in calls],
        },
    }
    final = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": {"complete": True},
        "permission_denials": [],
        "num_turns": 3,
        "modelUsage": {
            "claude-opus-5-5": {
                "inputTokens": 10,
                "outputTokens": 5,
                "cacheReadInputTokens": 7,
                "cacheCreationInputTokens": 3,
            }
        },
        **(result or {}),
    }
    return "\n".join(json.dumps(row) for row in (init, *extra, assistant, final))


def run(claude, stdout, returncode=0, **kwargs):
    captured = {}

    def runner(argv, **options):
        captured.update(argv=argv, **options)
        return SimpleNamespace(stdout=stdout.encode(), stderr=b"", returncode=returncode)

    packet = claude.run_mcp_session(
        "Goal",
        {"type": "object"},
        model="claude-opus-5-5",
        mcp_command="python",
        mcp_args=["server.py"],
        approved_tools=["act", "observe"],
        runner=runner,
        **kwargs,
    )
    return packet, captured


def test_command_has_no_builtin_tools_settings_skills_or_foreign_servers(claude):
    argv = claude.command(["claude"], "claude-opus-5-5", "high", {}, "python", ["s.py"], ["act"])
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--allowedTools") + 1] == "mcp__jev_eval__act"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in argv
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(config["mcpServers"]) == ["jev_eval"]


def test_environment_strips_parent_session_provider_and_credentials(claude, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "ANTHROPIC_BASE_URL", "TYPESAFE_API_KEY"):
        monkeypatch.setenv(name, "secret-or-session")
    monkeypatch.setenv("PATH_KEEP_MARKER", "kept")
    environment = claude._environment()
    assert "PATH_KEEP_MARKER" in environment
    assert not any(key.startswith(("CLAUDE", "ANTHROPIC_", "TYPESAFE_")) for key in environment)


def test_qualified_turn_retains_identity_usage_and_inventory(claude):
    packet, captured = run(claude, stream(calls=["mcp__jev_eval__act", "StructuredOutput"]))
    assert packet["ok"] is True and packet["final_output"] == {"complete": True}
    assert packet["models_resolved"] == ["claude-opus-5-5"] and packet["model_fallbacks"] == []
    assert packet["usage_by_model"]["claude-opus-5-5"]["cache_read_input_tokens"] == 7
    assert packet["effective_inventory"]["non_evaluation_tools"] == []
    assert captured["shell"] is False and captured["input"] == b"Goal"


@pytest.mark.parametrize(
    "variant, reason",
    [
        ({"tools": ["Bash", "mcp__jev_eval__act"]}, "non_evaluation_tool_inventory"),
        ({"calls": ["mcp__jev_eval__shell_escape"]}, "unexpected_tool_activity"),
        ({"result": {"permission_denials": [{"tool_name": "Read"}]}}, "unexpected_tool_activity"),
        ({"servers": [{"name": "other", "status": "connected"}]}, "foreign_mcp_server"),
        (
            {"result": {"subtype": "error_max_turns", "is_error": True}},
            "failed_result:error_max_turns",
        ),
    ],
)
def test_foreign_tools_denials_servers_and_failures_disqualify(claude, variant, reason):
    packet, _ = run(claude, stream(**variant))
    assert packet["ok"] is False and packet["reason"] == reason
    assert packet["final_output"] is None


def test_refusal_fallback_is_recorded_not_hidden(claude):
    fallback = {
        "type": "system",
        "subtype": "model_refusal_fallback",
        "original_model": "claude-opus-5-5",
        "fallback_model": "claude-opus-4-8",
        "trigger": "refusal",
        "api_refusal_category": "cyber",
    }
    packet, _ = run(claude, stream(extra=[fallback]))
    assert packet["model_fallbacks"] == [
        {
            "original_model": "claude-opus-5-5",
            "fallback_model": "claude-opus-4-8",
            "trigger": "refusal",
            "category": "cyber",
        }
    ]


def test_cli_failure_keeps_usage_incomplete(claude):
    packet, _ = run(claude, "not json", returncode=1)
    assert packet["ok"] is False and packet["reason"] == "cli_failed"
    assert packet["usage_complete"] is False and packet["automatic_retry"] is False
