"""Explicit trusted-script entrypoint; no model-generated imports or scripts."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from .engine import AgentLoop, Workflow

TEMPLATE = '''"""Synthetic counter task. Replace callbacks with your business operations.

Run: jev-filter run task.py --goal "Reach the requested target" --inputs '{"target":2}'
Running calls Jev and is billable. Script Python is trusted, not sandboxed.
"""
from jev_harness import Task


state = {"value": 0}

def observe(ctx):
    # Read-only JSON evidence. Only this admitted observation goes to Jev.
    return {"value": state["value"], "target": ctx.inputs["target"]}

workflow = Task(
    observe=observe,
    verify=lambda ctx, seen: seen["value"] >= seen["target"],
)

@workflow.tool(
    "Increase the value toward target without exceeding it",
    parameters={"amount": lambda ctx, seen: [
        n for n in (1, 2) if seen["value"] + n <= seen["target"]
    ]},
)
def increment(amount):
    # Only registered calls execute; bound external I/O timeouts inside each tool.
    state["value"] += amount
    return {"value": state["value"]}

'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init-task", help="Write a synthetic task template; offline")
    init.add_argument("script")
    run = commands.add_parser("run", help="Run caller-trusted Python; Jev inference is billable")
    run.add_argument("script")
    run.add_argument("--goal", required=True)
    run.add_argument("--inputs", default="{}", help="JSON object; not automatically sent to Jev")
    run.add_argument("--context", default="{}", help="Shared JSON facts sent to Jev")
    run.add_argument("--required-context", action="append", default=[])
    run.add_argument("--max-steps", type=int, default=20)
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--archive", help="New private journal path; never overwritten")
    args = parser.parse_args(argv)
    try:
        path = Path(args.script).expanduser().resolve(strict=args.command == "run")
        if args.command == "init-task":
            with path.open("x", encoding="utf-8") as stream:
                stream.write(TEMPLATE)
            packet = {"status": "created", "script": str(path), "model_calls": 0}
            exit_code = 0
        else:
            inputs, context = json.loads(args.inputs), json.loads(args.context)
            if not isinstance(inputs, dict) or not isinstance(context, dict):
                raise ValueError("inputs_and_context_must_be_objects")
            spec = importlib.util.spec_from_file_location("_jev_task", path)
            if spec is None or spec.loader is None:
                raise ValueError("python_script_required")
            module = importlib.util.module_from_spec(spec)
            previous = sys.modules.get("_jev_task")
            sys.modules["_jev_task"] = module
            try:
                spec.loader.exec_module(module)
                workflow = getattr(module, "workflow", None)
                if not isinstance(workflow, Workflow):
                    raise ValueError("script_must_export_workflow")
                packet = AgentLoop().run(
                    workflow,
                    goal=args.goal,
                    inputs=inputs,
                    context=context,
                    required_context=args.required_context,
                    max_steps=args.max_steps,
                    timeout_seconds=args.timeout,
                    archive=args.archive,
                )
            finally:
                if previous is None:
                    sys.modules.pop("_jev_task", None)
                else:
                    sys.modules["_jev_task"] = previous
            exit_code = 0 if packet["complete"] else 2
    except Exception as error:
        packet = {"status": "failed", "complete": False, "error_type": type(error).__name__}
        exit_code = 2
    print(json.dumps(packet, ensure_ascii=False, allow_nan=False))
    return exit_code
