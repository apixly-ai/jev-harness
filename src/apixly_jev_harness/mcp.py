"""Minimal stdio MCP exposure of a caller-owned toolkit session.

No prompts or skills prefer either route. Tool results remain source material. Model
output identifies offered capabilities and references, never Python code or commands.
"""

import copy
import json
import re
import sys

from . import __version__
from .output import TaskOutput

# Inspection callbacks are caller-owned Python: factories, observers, verifiers and
# dynamic candidate providers may perform I/O or change their environment. Preserve
# conservative hints for those routes as well as execution; hints never grant permission.
TOOLS = [
    {
        "name": "arguments",
        "description": "Inspect current argument references for a tool, resolving dependent candidates after supplied parent references.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_ref": {"type": "string"},
                "tool": {"type": "string"},
                "parameters": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["tool", "parameters", "state_ref"],
            "additionalProperties": False,
        },
    },
    {
        "name": "observe",
        "description": "Read the task state and currently available tools and argument references.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "operate",
        "description": "Execute one currently available tool using its supplied argument references.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_ref": {"type": "string"},
                "tool": {"type": "string"},
                "parameters": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["tool", "parameters", "state_ref"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_task",
        "description": "Run the CURRENT goal with its already registered task script, tools, inputs and independent completion check. This performs the multi-step task in one call and returns status, artifact location, source references and usage. Available before any operate call; either route can be selected at the start.",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

TOOLS.append(
    {
        "name": "read_report",
        "description": "Read up to four original quoted records from the current saved evidence report, with source references, character windows and SHA-256. Requires an already saved report that matches this task's records. Available after either route; this does not execute task tools or inference.",
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {"page": {"type": "integer", "minimum": 0}},
            "required": ["page"],
            "additionalProperties": False,
        },
    }
)


RUN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "description": "Terminal state; completion requires the independent check.",
        },
        "complete": {"type": "boolean"},
        "steps": {"type": "integer", "minimum": 0},
        "artifact": {
            "type": "object",
            "description": "Caller artifact location, record count and match/digest receipt when defined.",
        },
        "report": {
            "type": "object",
            "description": "Up to four original quoted records; has_more points to subsequent read_report pages.",
        },
        "telemetry": {
            "type": "object",
            "description": "Actual/unknown Jev model usage, requests and operation timing; caller model cost is separate.",
        },
    },
    "required": ["status", "complete", "steps", "telemetry"],
    "additionalProperties": True,
}


def validate_execution_name(execution_name):
    """Validate the caller's descriptive execution tool name before any task loading."""
    if (
        type(execution_name) is not str
        or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", execution_name) is None
        or execution_name in {"observe", "arguments", "operate", "read_report", "delegate"}
    ):
        raise ValueError("unique_execution_tool_name_required")
    return execution_name


def describe_tools(session, *, allow_delegate=True, execution_name="run_task"):
    """Describe a bound task without running its factory, callbacks or inference."""
    validate_execution_name(execution_name)
    report_supported = session.report_tool_advertised
    result = copy.deepcopy(
        [
            x
            for x in TOOLS
            if (allow_delegate or x["name"] != "run_task")
            and (report_supported or x["name"] != "read_report")
        ]
    )
    for tool in result:
        if tool["name"] == "run_task":
            tool["title"] = "Jev Harness: execute the registered task"
            tool["description"] = (
                "Jev Harness executes the caller's registered task definition end to end for this goal: "
                + json.dumps(session.ctx.goal[:600], ensure_ascii=False)
                + ". The Jev agent loop selects registered tools and fresh argument references from observations, "
                "then runs the same independent completion check as direct operation. All inputs and source permissions "
                "are already bound by the caller; this call does not need per-step references. "
                "One client call returns terminal status, artifact receipt, bounded source quotes when the task "
                "defines an evidence report, and actual or unknown model usage. "
                f"Limits: at most {session.max_steps} tool effects and {session.timeout_seconds:g} seconds, "
                "checked cooperatively; callback I/O is bounded by the task. "
                "Only available before any operate call. Partial/review/uncertain outcomes are retained, "
                "and effects are not automatically retried."
            )
            tool["outputSchema"] = copy.deepcopy(RUN_OUTPUT_SCHEMA)
            tool["name"] = execution_name
    return result


def utf8_stream(stream):
    """MCP stdio is UTF-8; a Windows pipe otherwise inherits the locale code page."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None and (getattr(stream, "encoding", "") or "").lower() not in (
        "utf-8",
        "utf8",
    ):
        reconfigure(encoding="utf-8")
    return stream


def serve(
    session,
    *,
    source=None,
    destination=None,
    allow_delegate=True,
    checkpoint=None,
    execution_name="run_task",
):
    describe_tools(session, allow_delegate=allow_delegate, execution_name=execution_name)
    source = source or utf8_stream(sys.stdin)
    destination = destination or utf8_stream(sys.stdout)
    while True:
        line = source.readline(1_000_001)
        if not line:
            break
        if len(line) > 1_000_000:
            raise ValueError("mcp_message_too_large")
        request = {}
        try:
            request = json.loads(line)
            identifier = request.get("id")
            method = request.get("method")
            if identifier is None:
                continue
            result = None
            if method == "initialize":
                result = {
                    "protocolVersion": request.get("params", {}).get(
                        "protocolVersion", "2024-11-05"
                    ),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "jev-toolkit", "version": __version__},
                    "instructions": (
                        (
                            "Jev Harness task server. run_task executes the registered goal end to end: Jev selects supplied tools and fresh argument references, code executes them, and the caller's independent check determines completion. operate performs one supplied task tool; observe inspects state and arguments resolves dependent references. Inputs and permissions are already bound. Choose either route before the first effect. read_report reads saved quotes after either route; it does not resume execution."
                        ).replace("run_task", execution_name)
                        if allow_delegate
                        else "Jev Harness direct task server. observe inspects task state, arguments resolves dependent references, and operate executes one registered tool. Inputs, permissions and independent completion checks are caller-defined. read_report reads saved source quotes when available."
                    ),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {
                    "tools": describe_tools(
                        session, allow_delegate=allow_delegate, execution_name=execution_name
                    )
                }
            elif method == "tools/call":
                params = request.get("params", {})
                name, args = params.get("name"), params.get("arguments", {})
                try:
                    with TaskOutput().discard():
                        if name == "observe" and args == {}:
                            packet = session.observe()
                        elif (
                            name == "arguments"
                            and type(args) is dict
                            and set(args) == {"tool", "parameters", "state_ref"}
                            and type(args["state_ref"]) is str
                        ):
                            packet = session.resolve(**args)
                        elif (
                            name == "operate"
                            and type(args) is dict
                            and set(args) == {"tool", "parameters", "state_ref"}
                            and type(args["state_ref"]) is str
                        ):
                            packet = session.operate(**args)
                        elif name == "read_report" and type(args) is dict and set(args) == {"page"}:
                            packet = session.read_report(**args)
                        elif (
                            name in (execution_name, "run_task", "delegate")
                            and allow_delegate
                            and args == {}
                        ):
                            packet = session.delegate()
                        else:
                            raise ValueError("mcp_tool_or_arguments_not_registered")
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps(packet, ensure_ascii=False)}
                        ],
                        "structuredContent": copy.deepcopy(packet),
                    }
                except Exception as error:
                    result = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "execution_uncertain"
                                        if session._uncertain
                                        else "failed",
                                        "error_type": type(error).__name__,
                                        "automatic_retry": False,
                                    }
                                ),
                            }
                        ],
                    }
            else:
                raise ValueError("unsupported_mcp_method")
            response = {"jsonrpc": "2.0", "id": identifier, "result": result}
        except Exception:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32600, "message": "Invalid or unsupported request"},
            }
        if checkpoint is not None:
            checkpoint()
        destination.write(json.dumps(response, ensure_ascii=False) + "\n")
        destination.flush()


def main(argv=None):
    """Serve a caller-reviewed thin task script over stdio; never generate/import model text."""
    import importlib.util
    from pathlib import Path

    from .backend import DEFAULT_MODEL, validate_model
    from .engine import validate_run_options
    from .task_cli import _ArgumentParser, _CLIArgumentError
    from .toolkit import ToolkitSession

    parser = _ArgumentParser(description=main.__doc__)
    parser.add_argument("script")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--inputs", default="{}")
    parser.add_argument("--context", default="{}")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--archive")
    parser.add_argument("--direct-only", action="store_true")
    parser.add_argument("--execution-name", default="run_task")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    phase = "configuration"
    session = None
    try:
        args = parser.parse_args(argv)
        validate_execution_name(args.execution_name)
        validate_model(args.model)
        inputs, context = json.loads(args.inputs), json.loads(args.context)
        if type(inputs) is not dict or type(context) is not dict:
            raise ValueError("json_objects_required")
        validate_run_options(
            goal=args.goal,
            inputs=inputs,
            context=context,
            max_steps=args.max_steps,
            timeout_seconds=args.timeout,
        )
        phase = "script_loading"
        path = Path(args.script).expanduser().resolve(strict=True)
        with TaskOutput().discard():
            spec = importlib.util.spec_from_file_location("_jev_mcp_task", path)
            if spec is None or spec.loader is None:
                raise ValueError("python_script_required")
            module = importlib.util.module_from_spec(spec)
            previous = sys.modules.get("_jev_mcp_task")
            sys.modules["_jev_mcp_task"] = module
            try:
                spec.loader.exec_module(module)
            finally:
                if previous is None:
                    sys.modules.pop("_jev_mcp_task", None)
                else:
                    sys.modules["_jev_mcp_task"] = previous
            session = ToolkitSession(
                module.workflow,
                goal=args.goal,
                inputs=inputs,
                context=context,
                max_steps=args.max_steps,
                timeout_seconds=args.timeout,
                archive=args.archive,
                model=args.model,
            )
        phase = "serving"
        serve(session, allow_delegate=not args.direct_only, execution_name=args.execution_name)
        return 0
    except _CLIArgumentError:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "complete": False,
                    "phase": "arguments",
                    "code": "invalid_command_arguments",
                    "script_loaded": False,
                    "model_calls": 0,
                }
            )
        )
        return 2
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "phase": phase,
                    "error_type": type(error).__name__,
                    "automatic_retry": False,
                }
            )
        )
        return 2
    finally:
        if session is not None:
            task = getattr(session.task, "_task", session.task)
            for pack in getattr(task, "toolkits", []):
                if callable(getattr(pack, "close", None)):
                    with TaskOutput().discard():
                        pack.close()


if __name__ == "__main__":
    raise SystemExit(main())
