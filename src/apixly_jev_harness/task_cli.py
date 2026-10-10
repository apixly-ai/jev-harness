"""Explicit trusted-script entrypoint; no model-generated imports or scripts."""

import argparse
import ast
import importlib.util
import json
import sys
import warnings
from importlib.resources import files
from pathlib import Path

from .diagnostics import HTTP_CODE_PATTERN, PROVIDER_CODES, SELECTION_CODES
from .engine import AgentLoop, Workflow

TEMPLATE = '''"""Synthetic counter task. Replace callbacks with your business operations.

Run: jev-harness run task.py --goal "Reach the requested target" --inputs '{"target":2}'
Running calls Jev and is billable. Script Python is trusted, not sandboxed.
"""
from apixly_jev_harness import Parameter, Task


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
    parameters={"amount": Parameter("Program-computed increment bounded by the remaining target",
        lambda ctx, seen: [min(2, seen["target"] - seen["value"])])},
    result_context=lambda result: result,
)
def increment(amount):
    # Only registered calls execute; bound external I/O timeouts inside each tool.
    state["value"] += amount
    return {"value": state["value"]}

'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("skill", help="Print bundled AI task instructions; offline")
    commands.add_parser("spec", help="Machine-readable interface and adoption contract; offline")
    check = commands.add_parser(
        "check-task", help="Parse/compile Python and check assignment without executing; offline"
    )
    check.add_argument("script")
    init = commands.add_parser("init-task", help="Write a synthetic task template; offline")
    init.add_argument("script")
    run = commands.add_parser("run", help="Run caller-trusted Python; Jev inference is billable")
    run.add_argument("script")
    run.add_argument("--goal", required=True)
    run.add_argument("--inputs", default="{}", help="JSON object; not automatically sent to Jev")
    run.add_argument(
        "--messages", default="[]", help="Explicit admitted user/assistant messages as JSON"
    )
    run.add_argument("--context", default="{}", help="Shared JSON facts sent to Jev")
    run.add_argument("--required-context", action="append", default=[])
    run.add_argument("--max-steps", type=int, default=20)
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--archive", help="New private journal path; never overwritten")
    args = parser.parse_args(argv)
    if args.command == "skill":
        bundled = files("apixly_jev_harness").joinpath("skill/SKILL.md")
        body = (
            bundled.read_text()
            if bundled.is_file()
            else (Path(__file__).resolve().parents[2] / "skills/jev-harness/SKILL.md").read_text()
        )
        print(body)
        return 0
    if args.command == "spec":
        print(json.dumps(SPEC))
        return 0
    if args.command == "check-task":
        try:
            path = Path(args.script).expanduser().resolve(strict=True)
            with warnings.catch_warnings(record=True) as source_warnings:
                warnings.simplefilter("always")
                tree = ast.parse(path.read_text(encoding="utf-8"), filename="task.py")
                compile(tree, "task.py", "exec", dont_inherit=True)
            exported = any(
                isinstance(node, (ast.Assign, ast.AnnAssign))
                and node.value is not None
                and any(
                    isinstance(target, ast.Name) and target.id == "workflow"
                    for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
                )
                for node in tree.body
            )
            packet = {
                "ok": exported,
                "model_calls": 0,
                "code": "syntax_and_export_ok" if exported else "workflow_export_missing",
                "scope": "Python parsing/compilation and top-level workflow assignment only; code, callbacks and imports are not executed",
                **(
                    {
                        "source_warnings": [
                            {"code": "python_source_warning", "line": warning.lineno}
                            for warning in source_warnings
                        ]
                    }
                    if source_warnings
                    else {}
                ),
            }
        except SyntaxError as error:
            packet = {"ok": False, "code": "invalid_python", "line": error.lineno, "model_calls": 0}
        except UnicodeDecodeError:
            packet = {"ok": False, "code": "source_not_utf8", "model_calls": 0}
        except OSError:
            packet = {"ok": False, "code": "script_unreadable", "model_calls": 0}
        print(json.dumps(packet))
        return 0 if packet["ok"] else 2
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
                    messages=json.loads(args.messages),
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


SPEC = {
    "name": "jev-harness",
    "distribution": "apixly-jev-harness",
    "python_import": "apixly_jev_harness",
    "version": "0.1.4",
    "parameter_binding": "staged_candidate_choice",
    "tool_selection": {
        "scope": "next_step",
        "decision_stage_field": "decision_stage",
        "requirements_source": "caller_task_contract",
        "candidate_order_is_priority": False,
        "direct_choice_without_loop_marker": "unchanged",
    },
    "commands": {
        "skill": {"offline": True},
        "spec": {"offline": True},
        "init-task": {"required": ["script"], "offline": True},
        "check-task": {
            "required": ["script"],
            "offline": True,
            "scope": "parse/compile/top-level assignment only",
            "checks": ["utf8_decode", "ast_parse", "python_compile", "top_level_assignment"],
            "python_scope": "current_interpreter",
            "source_execution": False,
            "runtime_validation": False,
            "source_warning_code": "python_source_warning",
        },
        "run": {
            "required": ["script", "goal"],
            "billable": True,
            "optional": [
                "inputs",
                "context",
                "messages",
                "required-context",
                "max-steps",
                "timeout",
                "archive",
            ],
        },
    },
    "script_contract": {
        "export": "workflow",
        "type": "Task or Workflow",
        "trusted_python": True,
        "callbacks": ["observe", "verify"],
        "tool_registration": "Task.tool",
        "parameters": {
            "Parameter": ["description", "choices", "depends_on"],
            "Option": ["id", "description", "value"],
        },
    },
    "context": [
        "goal",
        "facts",
        "messages",
        "observation",
        "history",
        "compacted_steps",
        "budgets",
        "decision_stage",
    ],
    "progress": {
        "unchanged_observation_requires": "non_none_admitted_result",
        "duplicate_invocation": {
            "scope": "single_run",
            "key": ["observation", "action_id", "bound_parameters"],
            "status": "blocked",
            "reason": "repeated_action_state",
            "effect": "not_executed",
        },
        "identical_fixed_observation_polling": False,
    },
    "verification": {
        "independent": True,
        "strict_bool": True,
        "helper": "verify_state",
        "helper_requires": "nonempty_text_or_control_condition",
        "missing_control_fields": "do_not_match",
    },
    "diagnostic": {
        "optional": True,
        "scope": "selection_calls",
        "stages": ["tool_selection", "parameter_selection"],
        "fields": ["stage", "tool_id", "parameter", "reason_codes", "automatic_retry"],
        "reason_codes": sorted(PROVIDER_CODES | SELECTION_CODES),
        "http_code_pattern": HTTP_CODE_PATTERN,
        "automatic_retry": False,
        "call_telemetry_stage": True,
        "raw_exception_text": False,
        "bound_values": False,
        "provider_transport_retry": "pinned SDK bounded policy unchanged",
    },
    "statuses": [
        "done",
        "needs_context",
        "needs_review",
        "needs_confirmation",
        "blocked",
        "stale",
        "max_steps",
        "budget_exceeded",
        "execution_uncertain",
        "failed",
    ],
    "exit_codes": {"0": "done or offline operation successful", "2": "parse_terminal_packet"},
    "adoption": "Use for bounded tasks with semantic choices and an independent verifier. Keep exact/fixed work in code. Inspect spec, generate template, check script, run once, consume terminal result. Reconcile uncertain effects before any rerun.",
    "limits": {
        "tools": 250,
        "parameter_options": 253,
        "independent_inference_workers": 30,
        "max_steps_default": 20,
        "timeout_seconds_default": 120,
        "result_cache": False,
    },
}
