"""Minimal stdio MCP exposure of a caller-owned toolkit session.

No prompts or skills prefer either route. Tool results remain source material. Model
output identifies offered capabilities and references, never Python code or commands.
"""

import json
import sys

from . import __version__
from .output import TaskOutput

TOOLS = [
    {
        "name": "arguments",
        "description": "Inspect current argument references for a tool, resolving dependent candidates after supplied parent references.",
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
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "operate",
        "description": "Execute one currently available tool using its supplied argument references.",
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
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def serve(session, *, source=None, destination=None, allow_delegate=True, checkpoint=None):
    source = source or sys.stdin
    destination = destination or sys.stdout
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
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [x for x in TOOLS if allow_delegate or x["name"] != "run_task"]}
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
                        elif name in ("run_task", "delegate") and allow_delegate and args == {}:
                            packet = session.delegate()
                        else:
                            raise ValueError("mcp_tool_or_arguments_not_registered")
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps(packet, ensure_ascii=False)}
                        ]
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
    phase = "configuration"
    session = None
    try:
        args = parser.parse_args(argv)
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
            )
        phase = "serving"
        serve(session, allow_delegate=not args.direct_only)
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
