"""Opt-in Claude Code CLI primary adapter; importing it never launches inference.

run_mcp_session runs one headless ``claude -p`` turn whose only tools are the caller's
synthetic ``jev_eval`` MCP server tools. Built-in tools, skills, settings sources,
user/project instructions and other MCP servers are excluded, and the stream's init
event is retained so the effective tool inventory is evidence rather than assumption.
CLI completion or valid JSON never proves task completion; callers verify artifacts.
Reported usage is the CLI's own accounting; resolved model ids come from the stream.
"""

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from _private_files import secure_fs as _secure_fs

SERVER = "jev_eval"
PREFIX = "mcp__" + SERVER + "__"
# The --json-schema answer channel; it returns the final object and has no side effects.
ANSWER_TOOLS = {"StructuredOutput"}
_STRIPPED_PREFIXES = ("CLAUDE", "ANTHROPIC_", "MCP_", "TYPESAFE_", "JEV_", "OPENAI_", "CODEX_")


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _environment():
    """Host process environment without parent-session, provider or credential variables.

    The CLI authenticates with its own saved login; nothing from the calling agent's
    session, an API base override or the TypeSafe/Jev credentials is inherited.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(_STRIPPED_PREFIXES)
    }


def claude_launcher(binary="claude"):
    """Argument-safe launcher; an npm ``.cmd`` shim is bypassed for its Node entrypoint."""
    resolved = shutil.which(binary) or binary
    if os.name == "nt" and Path(resolved).suffix.lower() in (".cmd", ".bat"):
        package = Path(resolved).parent / "node_modules/@anthropic-ai/claude-code"
        native = package / "bin/claude.exe"
        if native.is_file():
            return [str(native)]
        raise ValueError("claude_batch_shim_requires_native_entrypoint")
    return [resolved]


def command(binary, model, effort, schema, mcp_command, mcp_args, approved_tools):
    config = {"mcpServers": {SERVER: {"command": mcp_command, "args": list(mcp_args)}}}
    allowed = [PREFIX + name for name in approved_tools]
    return [
        *(binary if isinstance(binary, list) else [binary]),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--effort",
        effort,
        "--tools",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        _json(config),
        "--allowedTools",
        ",".join(allowed),
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--setting-sources",
        "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--no-chrome",
        "--json-schema",
        _json(schema),
    ]


def _usage(model_usage):
    if type(model_usage) is not dict or not model_usage:
        return None
    fields = {
        "inputTokens": "input_tokens",
        "outputTokens": "output_tokens",
        "cacheReadInputTokens": "cache_read_input_tokens",
        "cacheCreationInputTokens": "cache_creation_input_tokens",
    }
    models = {}
    for name, row in model_usage.items():
        if type(name) is not str or type(row) is not dict:
            return None
        values = {target: row.get(source) for source, target in fields.items()}
        if any(type(value) is not int or value < 0 for value in values.values()):
            return None
        models[name] = values
    return models


def parse(stdout, approved_tools):
    """Qualify one stream: only approved jev_eval tools, a single successful result."""
    if isinstance(stdout, bytes):
        try:
            stdout = stdout.decode("utf-8")
        except UnicodeError:
            return {"reason": "invalid_event_stream"}
    try:
        events = [json.loads(line) for line in (stdout or "").splitlines() if line.strip()]
    except ValueError:
        return {"reason": "invalid_event_stream"}
    if any(type(event) is not dict or type(event.get("type")) is not str for event in events):
        return {"reason": "invalid_event_stream"}
    init = [e for e in events if e["type"] == "system" and e.get("subtype") == "init"]
    results = [e for e in events if e["type"] == "result"]
    packet = {"reason": None, "tool_calls": {}, "unexpected": 0}
    if len(init) != 1 or len(results) != 1:
        packet["reason"] = "missing_or_multiple_init_or_result_events"
        return packet
    init, result = init[0], results[0]
    allowed = {PREFIX + name for name in approved_tools}
    inventory = init.get("tools") if type(init.get("tools")) is list else None
    servers = init.get("mcp_servers") if type(init.get("mcp_servers")) is list else []
    packet["inventory"] = {
        "model": init.get("model"),
        "tools": inventory,
        "non_evaluation_tools": sorted(
            t for t in inventory or [] if not str(t).startswith(PREFIX) and t not in ANSWER_TOOLS
        ),
        "mcp_servers": [
            {"name": row.get("name"), "status": row.get("status")}
            for row in servers
            if type(row) is dict
        ],
        "skills": init.get("skills"),
        "slash_commands": init.get("slash_commands"),
        "plugins": init.get("plugins"),
        "agents": init.get("agents"),
        "permission_mode": init.get("permissionMode"),
    }
    resolved = set()
    for event in events:
        message = event.get("message") if event["type"] == "assistant" else None
        if type(message) is not dict:
            continue
        if type(message.get("model")) is str:
            resolved.add(message["model"])
        for block in message.get("content") or []:
            if type(block) is dict and block.get("type") == "tool_use":
                name = block.get("name")
                packet["tool_calls"][name] = packet["tool_calls"].get(name, 0) + 1
                if name not in allowed and name not in ANSWER_TOOLS:
                    packet["unexpected"] += 1
    packet["model_fallbacks"] = [
        {key: event.get(key) for key in ("original_model", "fallback_model", "trigger")}
        | {"category": event.get("api_refusal_category")}
        for event in events
        if event["type"] == "system" and event.get("subtype") == "model_refusal_fallback"
    ]
    denials = result.get("permission_denials") or []
    packet["permission_denials"] = len(denials) if type(denials) is list else None
    packet["models_resolved"] = sorted(resolved)
    packet["usage"] = _usage(result.get("modelUsage"))
    packet["num_turns"] = result.get("num_turns")
    packet["cli_reported_cost_usd_estimate"] = result.get("total_cost_usd")
    if inventory is None or packet["inventory"]["non_evaluation_tools"]:
        packet["reason"] = "non_evaluation_tool_inventory"
    elif any(row["name"] != SERVER for row in packet["inventory"]["mcp_servers"]):
        packet["reason"] = "foreign_mcp_server"
    elif result.get("subtype") != "success" or result.get("is_error"):
        packet["reason"] = "failed_result:" + str(result.get("subtype"))
    elif packet["unexpected"] or packet["permission_denials"]:
        packet["reason"] = "unexpected_tool_activity"
    output = result.get("structured_output")
    if output is None and packet["reason"] is None:
        try:
            output = json.loads(result.get("result"))
        except (TypeError, ValueError):
            packet["reason"] = "invalid_final_output"
    packet["final_output"] = output if packet["reason"] is None else None
    return packet


def run_mcp_session(
    prompt,
    output_schema,
    *,
    model,
    mcp_command,
    mcp_args,
    approved_tools,
    effort="high",
    timeout_seconds=900,
    claude_binary="claude",
    working_directory=None,
    runner=None,
    private_events_path=None,
    private_diagnostics_path=None,
):
    if (
        type(prompt) is not str
        or type(output_schema) is not dict
        or type(model) is not str
        or not model.strip()
        or type(mcp_command) is not str
        or type(mcp_args) is not list
        or any(type(arg) is not str for arg in mcp_args)
        or isinstance(approved_tools, str)
        or not approved_tools
        or any(
            type(name) is not str or not name.replace("_", "").isalnum() for name in approved_tools
        )
        or type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("invalid_claude_session_configuration")
    run = subprocess.run if runner is None else runner
    with ExitStack() as stack:
        streams = {}
        for name, value in (("stdout", private_events_path), ("stderr", private_diagnostics_path)):
            if value is not None:
                fd = _secure_fs.open_private_file(Path(value), "x")
                streams[name] = stack.enter_context(os.fdopen(fd, "wb"))
        directory = working_directory or stack.enter_context(
            tempfile.TemporaryDirectory(prefix="jev-claude-primary-")
        )
        argv = command(
            claude_launcher(claude_binary) if runner is None else [claude_binary],
            model,
            effort,
            output_schema,
            mcp_command,
            mcp_args,
            approved_tools,
        )
        started = time.perf_counter()
        stdout = stderr = None
        returncode, reason, status = None, None, "failed"
        try:
            completed = run(
                argv,
                input=prompt.encode("utf-8"),
                capture_output=True,
                timeout=timeout_seconds,
                cwd=directory,
                env=_environment(),
                shell=False,
                check=False,
            )
            stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
            if returncode:
                reason = "cli_failed"
        except subprocess.TimeoutExpired as error:
            stdout, stderr, reason, status = (
                error.stdout,
                error.stderr,
                "cli_timeout",
                "interrupted",
            )
        except OSError:
            reason = "cli_launch_failed"
        elapsed = time.perf_counter() - started
        for name, value in (("stdout", stdout), ("stderr", stderr)):
            if name in streams and value:
                streams[name].write(value if isinstance(value, bytes) else value.encode())
                streams[name].flush()
                os.fsync(streams[name].fileno())
    parsed = parse(stdout, approved_tools)
    reason = reason or parsed["reason"]
    if reason is None:
        status = "completed"
    usage = parsed.get("usage")
    return {
        "ok": reason is None,
        "status": status,
        "reason": reason,
        "final_output": parsed.get("final_output") if reason is None else None,
        "model_requested": model,
        "models_resolved": parsed.get("models_resolved"),
        "model_fallbacks": parsed.get("model_fallbacks"),
        "effective_inventory": parsed.get("inventory"),
        "tool_calls": parsed.get("tool_calls"),
        "unexpected_tool_calls": parsed.get("unexpected"),
        "permission_denials": parsed.get("permission_denials"),
        "num_turns": parsed.get("num_turns"),
        "usage_scope": "claude_code_result_model_usage",
        "usage_complete": usage is not None and status == "completed",
        "usage_by_model": usage,
        "cli_reported_cost_usd_estimate": parsed.get("cli_reported_cost_usd_estimate"),
        "whole_process_seconds": elapsed,
        "cli_returncode": returncode,
        "automatic_retry": False,
        "mode": "primary_mcp_session",
        "completion_scope": "cli_process_not_task_artifact",
    }
