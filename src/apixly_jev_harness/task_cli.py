"""Trusted task scripts and offline scaffolds. Use 'jev-harness mcp SCRIPT --goal GOAL'
to expose the same script for primary-AI operation or Jev delegation over stdio.
"""

import argparse
import ast
import importlib.util
import json
import sys
import warnings
from importlib.resources import files
from pathlib import Path

from . import __version__
from .callbacks import (
    CALLBACK_CODES,
    CALLBACK_KINDS,
    CALLBACK_ROLES,
    CallbackContractError,
    project_contract_error,
)
from .context import CONTEXT_CHARACTER_LIMIT
from .diagnostics import HTTP_CODE_PATTERN, PLANNING_CODES, PROVIDER_CODES, SELECTION_CODES
from .engine import AgentLoop, Workflow, validate_run_options
from .output import TaskOutput

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

TOOLKIT_TEMPLATES = ("workspace", "http", "browser", "surface", "records")

QUICKSTART = {
    "name": "Jev Harness",
    "model_calls": 0,
    "purpose": "Execute a caller-defined goal through registered tools, observations and an independent completion check.",
    "script": {
        "export": "workflow = TaskScript(build)",
        "factory": "build(inputs) -> Task",
        "imports": "from apixly_jev_harness import Task, TaskScript, Parameter, Option",
        "callbacks": "observe(ctx) -> JSON; verify(ctx, observation) -> bool",
        "trusted_python": True,
        "source_execution_by_jev": False,
    },
    "tools": {
        "registration": "@task.tool(description, name=..., parameters={name: Parameter(description, choices)}, result_context=...)",
        "parameter_values": "caller_supplied_candidates",
        "dynamic_choices": "choices(ctx, observation) or choices(ctx, observation, previously_bound_params)",
        "candidate": "Option(id, description, value)",
        "dependent_params": "Parameter(..., depends_on=(parent_name,))",
        "selection": "Jev chooses a tool then parameter references from fresh observations; code binds actual values.",
        "authorization": "irreversible=True tools run only when Task(authorize=...) returns True for authorize(ctx, action); action.params == {'tool': name, 'arguments': {param: bound value}}",
    },
    "toolkits": {
        "workspace": "WorkspaceTools(root, store, queries=...): permitted file discovery, search and evidence capture",
        "http": "WebTools(HttpProvider(url, allowed_origins=...), store): GET discovery and source capture",
        "browser": "WebTools(CamofoxProvider(url=url, session=..., allowed_origins=...), store): observed links and sections",
        "evidence_task": "EvidenceTask([pack], store=store, labels=..., output=..., verify=..., record_checks=...)",
        "evidence_store": "EvidenceStore(): retained originals, source digests and bounded source windows",
        "surface": "apixly_jev_harness.surfaces.SurfaceTask(surface, values=..., allowed_origins=..., verify=..., authorize=..., allow=...): click/select/fill over fresh observed targets; allow(target)->bool narrows offered controls by label/role/section/row/state; click is irreversible; scaffold with init-task --toolkit surface",
        "records": "Engine().decide(records=[{'id','text'}], goal=question, analysis_spec={'questions': {...}, 'filter': {...}}) -> selected_ids/review_ids: one typed question over many records, packed into batched requests; scaffold with init-task --toolkit records",
        "validation": "Caller record_checks and verify establish the requested facts; schema marker presence alone does not establish semantic truth.",
    },
    "cli": {
        "init": "jev-harness init-task task.py --toolkit workspace",
        "check": "jev-harness check-task task.py",
        "run": "jev-harness run task.py --goal GOAL --inputs JSON --max-steps 20 --timeout 120 --archive NEW_PATH",
        "mcp": "jev-harness mcp task.py --goal GOAL --inputs JSON --execution-name run_task",
        "detailed_protocol": "jev-harness spec",
    },
    "outcome": {
        "completion": "caller_independent_verifier",
        "terminal": "status, complete, steps, telemetry and optional artifact",
        "mcp_routes": "run_task performs the Jev loop; operate performs one registered effect. Choose before the first effect; read_report reads saved quotes after either route.",
        "failure": "Partial, review and uncertain outcomes are retained; no automatic effect retries.",
        "usage": "Jev inference is billable; actual or unknown model usage is retained. Primary model usage is separate.",
        "price": "Published TypeSafe price (2026-10-12, docs.typesafe.ai/models): jev-1.13.0 $0.042 per million input tokens; output tokens free. Check the source before relying on it.",
        "bounds": "Step and cooperative wall limits; caller callbacks bound their own I/O.",
    },
}


def _template(toolkit):
    if toolkit is None:
        return TEMPLATE
    bundled = files("apixly_jev_harness").joinpath("templates/" + toolkit + ".py")
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8")
    return (Path(__file__).resolve().parents[2] / "templates" / (toolkit + ".py")).read_text(
        encoding="utf-8"
    )


def _close_toolkits(workflow):
    from .toolkit import EvidenceTask, TaskScript

    if isinstance(workflow, TaskScript):
        task = workflow._task
    elif isinstance(workflow, EvidenceTask):
        task = workflow
    else:
        return []
    errors = []
    for pack in getattr(task, "toolkits", []):
        try:
            if callable(getattr(pack, "close", None)):
                pack.close()
        except Exception as error:
            errors.append({"toolkit_type": type(pack).__name__, "error_type": type(error).__name__})
    return errors


class _CLIArgumentError(ValueError):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's message may contain raw argv. Do not copy it to payload/output.
        raise _CLIArgumentError("invalid_command_arguments") from None


def main(argv=None):
    parser = _ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("skill", help="Print bundled AI task instructions; offline")
    commands.add_parser("spec", help="Machine-readable interface and adoption contract; offline")
    commands.add_parser("quickstart", help="Compact task-script and toolkit API card; offline")
    check = commands.add_parser(
        "check-task", help="Parse/compile Python and check assignment without executing; offline"
    )
    check.add_argument("script")
    init = commands.add_parser("init-task", help="Write a counter or thin toolkit task; offline")
    init.add_argument("script")
    init.add_argument("--toolkit", choices=TOOLKIT_TEMPLATES)
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
    try:
        args = parser.parse_args(argv)
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
    if args.command == "skill":
        bundled = files("apixly_jev_harness").joinpath("skill/SKILL.md")
        body = (
            bundled.read_text(encoding="utf-8")
            if bundled.is_file()
            else (Path(__file__).resolve().parents[2] / "skills/jev-harness/SKILL.md").read_text(
                encoding="utf-8"
            )
        )
        print(body)
        return 0
    if args.command == "spec":
        print(json.dumps(SPEC))
        return 0
    if args.command == "quickstart":
        print(json.dumps(QUICKSTART))
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
    phase = "configuration" if args.command == "run" else None
    task_output = None
    cleanup_errors = []
    try:
        if args.command == "run":
            inputs, context, messages = (
                json.loads(args.inputs),
                json.loads(args.context),
                json.loads(args.messages),
            )
            if not isinstance(inputs, dict) or not isinstance(context, dict):
                raise ValueError("inputs_and_context_must_be_objects")
            if not isinstance(messages, list):
                raise ValueError("invalid_messages")
            admitted, run_spec = validate_run_options(
                goal=args.goal,
                inputs=inputs,
                context=context,
                messages=messages,
                required_context=args.required_context,
                max_steps=args.max_steps,
                timeout_seconds=args.timeout,
            )
            phase = "script_loading"
        path = Path(args.script).expanduser().resolve(strict=args.command == "run")
        if args.command == "init-task":
            body = _template(args.toolkit)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(body)
            packet = {"status": "created", "script": str(path), "model_calls": 0}
            if args.toolkit is not None:
                packet["toolkit"] = args.toolkit
            exit_code = 0
        else:
            task_output = TaskOutput()
            with task_output.discard():
                spec = importlib.util.spec_from_file_location("_jev_task", path)
                if spec is None or spec.loader is None:
                    raise ValueError("python_script_required")
                module = importlib.util.module_from_spec(spec)
                previous = sys.modules.get("_jev_task")
                sys.modules["_jev_task"] = module
                workflow = None
                try:
                    spec.loader.exec_module(module)
                    workflow = getattr(module, "workflow", None)
                    if not isinstance(workflow, Workflow):
                        raise ValueError("script_must_export_workflow")
                    packet = AgentLoop().run(
                        workflow,
                        goal=args.goal,
                        inputs=admitted.inputs,
                        context=admitted.facts,
                        messages=admitted.messages,
                        required_context=run_spec.get("required_context", []),
                        max_steps=args.max_steps,
                        timeout_seconds=args.timeout,
                        archive=args.archive,
                    )
                finally:
                    cleanup_errors = _close_toolkits(workflow)
                    if previous is None:
                        sys.modules.pop("_jev_task", None)
                    else:
                        sys.modules["_jev_task"] = previous
            exit_code = 0 if packet["complete"] else 2
    except SystemExit as error:
        if task_output is None:
            raise
        # No verified terminal exists. Non-integer codes would expose raw task text;
        # zero/out-of-range codes can look successful after OS exit-code truncation.
        code = error.code if type(error.code) is int and 1 <= error.code <= 255 else 1
        raise SystemExit(code) from None
    except KeyboardInterrupt:
        if task_output is None:
            raise
        # Preserve interruption, without an interpreter traceback of trusted source.
        raise SystemExit(130) from None
    except Exception as error:
        packet = {"status": "failed", "complete": False, "error_type": type(error).__name__}
        if isinstance(error, CallbackContractError):
            packet["contract_error"] = project_contract_error(error)
        if phase == "configuration":
            packet.update(
                phase="configuration",
                code="invalid_run_configuration",
                script_loaded=False,
                model_calls=0,
            )
        exit_code = 2
    if task_output is not None and (summary := task_output.summary()) is not None:
        packet["task_output"] = summary
    if cleanup_errors:
        packet["cleanup_errors"] = cleanup_errors
    print(json.dumps(packet, ensure_ascii=False, allow_nan=False))
    return exit_code


SPEC = {
    "name": "jev-harness",
    "distribution": "apixly-jev-harness",
    "python_import": "apixly_jev_harness",
    "version": __version__,
    "parameter_binding": "staged_candidate_choice",
    "argument_parsing": {
        "scope": "all command parsers when argparse reports an error",
        "failure_phase": "arguments",
        "failure_code": "invalid_command_arguments",
        "failure_exit_code": 2,
        "script_loaded_on_failure": False,
        "model_calls_on_failure": 0,
        "raw_argument_values": False,
        "raw_error_message": False,
        "help": "text and SystemExit(0); original precedence",
        "long_option_abbreviation": "unchanged",
        "configuration_validation": "separate after parsing",
        "arbitrary_argv_types_supported": False,
    },
    "tool_selection": {
        "scope": "next_step",
        "decision_stage_field": "decision_stage",
        "requirements_source": "caller_task_contract",
        "candidate_order_is_priority": False,
        "direct_choice_without_loop_marker": "unchanged",
        "selection_description": {
            "signature": "selection_description(action) -> str",
            "default": "original offered description",
            "action_argument": "deepcopy; execution identity retained separately",
            "synchronous_admission": True,
            "thin_factory_admission_before_caching": True,
            "evidence_task": "parameter contract plus candidate count and up to 3 hints of 80 characters",
            "full_binding_domains": "fresh, unchanged",
            "direct_mcp_domains": "full, unchanged",
        },
    },
    "commands": {
        "skill": {"offline": True},
        "spec": {"offline": True},
        "quickstart": {"offline": True, "format": "compact_json_api_card", "inference": False},
        "init-task": {
            "required": ["script"],
            "offline": True,
            "default": "counter",
            "optional": ["toolkit"],
            "toolkit_choices": list(TOOLKIT_TEMPLATES),
            "writes_existing_script": False,
            "source_acquisition": False,
            "inference": False,
        },
        "mcp": {
            "entrypoint": "jev-harness mcp",
            "required": ["script", "goal"],
            "optional": [
                "inputs",
                "context",
                "max-steps",
                "timeout",
                "archive",
                "direct-only",
                "execution-name",
            ],
            "transport": "stdio_json_rpc",
            "task_source": "caller_trusted_script",
            "jev_delegation_billable": True,
            "direct_operations_use_jev": False,
        },
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
            "toolkit_cleanup": {
                "workflows": ["EvidenceTask", "materialized_TaskScript"],
                "scope": "registered_toolkit_close_methods",
                "metadata_field": "cleanup_errors",
                "error_fields": ["toolkit_type", "error_type"],
                "raw_error_text": False,
                "terminal_and_usage_preserved_on_cleanup_exception": True,
                "resource_release_proven": False,
            },
            "task_output": {
                "policy": "discard",
                "scope": "python_streams",
                "channels": ["stdout", "stderr"],
                "counters": ["characters", "binary_bytes"],
                "characters_unit": "Unicode code points, not encoded bytes",
                "metadata_field": "task_output",
                "metadata_when": "nonzero intercepted output",
                "retains_content": False,
                "sdk_behavior": "unchanged",
                "fd_isolation": False,
                "overlapping_cli_runs": "unsupported process-global redirection",
                "base_exception_terminal_guarantee": False,
                "interrupt_exit": {
                    "KeyboardInterrupt": 130,
                    "SystemExit": "exact integer 1..255 preserved; otherwise 1",
                    "terminal_packet": False,
                    "raw_exception_text": False,
                    "effects_and_usage_proven": False,
                },
            },
            "configuration_preflight": {
                "before_task_module_loading": True,
                "shared_with_engine": True,
                "defaults_for": "None only",
                "finite_json": ["inputs", "context", "messages"],
                "failure_code": "invalid_run_configuration",
                "failure_phase": "configuration",
                "script_loaded_on_failure": False,
                "model_calls_on_failure": 0,
                "sandbox": False,
            },
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
        "type": "Task, Workflow or TaskScript",
        "trusted_python": True,
        "callbacks": ["observe", "verify"],
        "tool_registration": "Task.tool",
        "factory": {
            "wrapper": "TaskScript",
            "signature": "build(inputs) -> Task",
            "inputs": "validated_runtime_inputs",
            "materialization": "once_per_TaskScript_instance",
            "during_script_import": False,
            "source_acquisition": "when_factory_materializes_or_a_registered_tool_acquires",
            "result_cache": False,
        },
        "parameters": {
            "Parameter": ["description", "choices", "depends_on", "selection"],
            "Option": ["id", "description", "value"],
            "selection": {"match": "supported_fact_candidate", "explore": "worth_inspecting_next"},
        },
    },
    "toolkits": {
        "built_in": list(TOOLKIT_TEMPLATES),
        "interface": {
            "name": "unique_string",
            "observe": "compact_json",
            "install": "register_on_Task",
        },
        "observation": "stable_compact_source_references",
        "business_logic": "caller_tools_and_independent_verifier",
        "workspace": {
            "class": "WorkspaceTools",
            "scope": "caller_selected_root",
            "source_execution": False,
        },
        "http": {
            "classes": ["HttpProvider", "WebTools"],
            "methods": ["GET"],
            "origin_checks": "before_each_redirect_hop",
        },
        "browser": {
            "classes": ["CamofoxProvider", "WebTools"],
            "identity": "named_session_and_fixed_tab",
            "cleanup": "owned_tab_only",
            "origin_checks": "target_and_final_observation; not_network_firewall",
        },
        "records": {
            "api": "Engine().decide",
            "modes": ["filter", "analyze", "choose", "passthrough"],
            "batching": "records packed into typed batch requests",
            "output": "selected_ids, review_ids and per-request usage telemetry",
        },
        "surface": {
            "class": "SurfaceTask",
            "tools": ["click", "select", "fill"],
            "targets": "fresh_observed_controls_with_label_role_section_row_and_state",
            "target_filter": "optional allow(target) -> bool for caller business rules",
            "fill_values": "caller_supplied_named_values_only",
            "click": "irreversible_requires_authorize",
        },
        "raw_candidate_arguments": "program_bound_values_only",
        "model_generated_selectors_or_code": False,
        "free_text_generation": "explicit_caller_registered_trusted_tool",
    },
    "evidence": {
        "store": "EvidenceStore",
        "capture": "private_original_text_and_source_metadata",
        "reference": "capture_specific; not_result_cache",
        "raw_text_read_limit": 1200,
        "recording": "previously_read_source_window_and_registered_label",
        "record_checks": "caller_optional_source_field_checks",
        "completion": "saved_artifact_matches_records_and_independent_verifier_passes",
        "verifier_records": "full_set",
        "task_observation_records": "bounded_summaries",
        "template_marker_scope": "known_schema_prefix_presence; customize_semantic_verification",
        "template_markers_are_expected_answers_or_routes": False,
    },
    "mcp": {
        "tools": ["observe", "arguments", "operate", "run_task", "read_report"],
        "execution_tool_name": "caller-defined --execution-name; default run_task",
        "legacy_unadvertised_alias": "delegate",
        "typed_output": ["outputSchema", "structuredContent", "JSON_text_content"],
        "report_read": {
            "records_per_page": 4,
            "artifact_match_required": True,
            "inference": False,
            "after_delegation": True,
            "after_execution_deadline": True,
        },
        "route_selection": "before_first_operation",
        "direct": "primary_AI_selects_registered_tool_and_parameter_refs",
        "delegate": "Jev_runs_same_task_and_returns_terminal_evidence",
        "switch_after_operations": False,
        "state_transfer_between_routes": False,
        "automatic_delegation_claim": False,
        "dependent_parameters": "arguments_after_parent_refs",
        "completion": "independent_verifier; not_primary_final_message",
        "uncertain_execution": "reconcile_before_any_new_operation",
        "scope": "in_process_session; not_durable_resume",
    },
    "task_action_identity": {
        "scope": "Task.bind_and_execute_against_latest_offered_snapshot",
        "action_type": "exact_Action",
        "id_before_lookup": "builtin_str",
        "fields": ["id", "description", "params", "irreversible"],
        "comparison": "shared_builtin_value_semantics",
        "boolean_number_equality": False,
        "finite_int_float_equality": True,
        "containers": "same_kind_recursive",
        "dictionary_keys": "typed_null_boolean_number_string",
        "unsupported_values_and_subclasses": "do_not_match; normalize_before_offering",
        "global_action_equality_changed": False,
        "object_or_byte_identity": False,
        "direct_errors": ["action_not_offered", "action_not_bound"],
        "engine_guard_rejection_always_failed": False,
        "execute_window": "existing_execution_uncertain_handling",
        "tool_body_not_entered_proves_global_zero_effects": False,
        "authorization_or_target_verification": False,
        "arbitrary_python_hook_execution_prohibited": False,
    },
    "wall_budget": {
        "policy": "cooperative_checks; callbacks_bound_their_own_io",
        "before_candidate_collection": "rechecked_after_false_verification",
        "late_verified_success": "done",
        "post_verification_step_limit_precedence": True,
        "callbacks_forcibly_interrupted": False,
        "strict_whole_operation_deadline": False,
        "prior_usage_and_effects": "preserved",
        "candidate_timeout_terminal": "budget_exceeded",
        "skipped_candidate_diagnostics": "unavailable; not guessed",
    },
    "parameter_snapshots": {
        "scope": "each_valid_parameter_domain",
        "stage": "after_domain_validation_before_selection",
        "policy": "deepcopy_all_options_and_values",
        "strategies": ["staged", "joint"],
        "dynamic_provider_identity": "preserved",
        "provider_results_cached": False,
        "staged_preview_reused_for_binding": False,
        "atomic_acquisition": False,
        "external_target_freshness_proven": False,
        "custom_deepcopy_behavior_proven": False,
        "copy_failure": "existing error/stop handling; no aliased-domain fallback",
        "cost_scope": "every valid option value, including private and unselected values",
    },
    "callbacks": {
        "execution": "synchronous",
        "roles": sorted(CALLBACK_ROLES),
        "rejected_declared_kinds": sorted(CALLBACK_KINDS),
        "generator_exception": "Workflow.candidates",
        "provider_positional_arguments": [2, 3],
        "provider_preferred_arity": 3,
        "provider_outer_signature": "inspect.signature(follow_wrapped=False)",
        "provider_generic_wrapped_contract": "advertised signature and actual bind",
        "provider_generic_rule": "VAR_POSITIONAL and fewer than three explicit positional parameters",
        "provider_explicit_signature_override": "respected; does not prove behavior",
        "tool_signature_registration": "unchanged",
        "provider_dynamic_identity": "preserved",
        "provider_static_choices": "deepcopied_at_registration",
        "provider_result_cache": False,
        "admission_invokes_body": False,
        "return_type_proven": False,
        "error_codes": sorted(CALLBACK_CODES),
        "fallback_error_code": "callback_contract_error",
        "terminal_error_field": "contract_error",
        "raw_exception_text": False,
        "trusted_module_loading": "may_have_effects_before_registration",
        "async_runtime": False,
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
    "context_admission": {
        "scope": "loop_shared_context",
        "unit": "json_characters",
        "limit": CONTEXT_CHARACTER_LIMIT,
        "serialization": "json.dumps(context, ensure_ascii=False) with default separators",
        "maximum_is_inclusive": True,
        "stages": ["context_projection", "tool_selection", "parameter_selection"],
        "metadata_field": "context_budget",
        "metadata_fields": ["scope", "stage", "unit", "limit", "observed"],
        "failure_reason": "context_budget_exceeded",
        "automatic_truncation": False,
        "raw_context_in_failure": False,
        "candidate_record_text_in_budget": False,
        "selection_question_in_budget": False,
        "full_prompt_or_token_budget": False,
        "direct_decide_admission": "unchanged",
        "call_telemetry_fields": ["context_characters", "context_character_limit", "context_bytes"],
        "prior_calls_and_effects_possible": True,
    },
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
        "observed_text_requires": "str; otherwise does not match",
        "helper_expected_text_requires": "built-in str or None; subclasses rejected before strip",
        "boolean_number_equality": False,
        "numeric_int_float_equality": True,
        "helper_value_types": [
            "None",
            "bool",
            "int",
            "finite float",
            "str",
            "list",
            "tuple",
            "dict",
        ],
        "helper_type_scope": "exact built-in types; subclasses are unsupported",
        "helper_container_comparison": "recursive; list and tuple do not cross-match",
        "helper_dictionary_keys": "typed None/bool/finite number/str; bool distinct from number",
        "helper_control_records": "built-in dict with built-in str field keys",
        "helper_expected_control_label": "built-in str",
        "helper_unknown_control_record": "does not match; not filtered to establish uniqueness",
        "helper_observation_root": "built-in dict with built-in str field keys; otherwise does not match",
        "unsupported_helper_values": "do not match; custom verifier required",
        "custom_verifier": "unchanged caller-owned strict bool",
    },
    "execution_reconciliation": {
        "action_id_scope": "current_pending_bound_action",
        "decision_stop_during_execution": "execution_uncertain_with_action_id",
        "infer_action_id_from_history": False,
        "action_id_proves_effect_success": False,
        "action_id_is_idempotency_key": False,
        "automatic_retry": False,
        "prior_usage": "retained including unknown",
        "recovery": "inspect private journal and target state before a new run",
    },
    "transport_counters": {
        "metadata_field": "telemetry.owned_transport",
        "scope": "run_owned_provider_client",
        "snapshot": "terminal_finish",
        "snapshot_timing": "before journal terminal write and client close",
        "counters": ["request_attempts", "clients_created", "client_reuses"],
        "measurement": "Client.stats difference from Session start; includes SDK retries",
        "requests_semantics": "unchanged sum of decision telemetry.requests; native Choice reports packed requests",
        "missing_or_invalid_counter": "null; never inferred zero",
        "decreasing_counter": "null when below start or a witnessed Session.run snapshot",
        "no_active_session": "metadata omitted; no zero inference",
        "server_received_or_billable_proof": False,
        "includes_other_tool_network": False,
        "tcp_connection_proof": False,
        "usage_handling": "unchanged; unknown usage remains unknown",
    },
    "request_planning": {
        "scope": "current_selection",
        "metadata_field": "telemetry.planning or telemetry.calls[].planning",
        "phase": "request_planning",
        "empty_plan_inference_dispatched": False,
        "reason_codes": sorted(PLANNING_CODES),
        "typed_statuses": ["NEEDS_CONTEXT", "NEEDS_NARROWING"],
        "unknown_status": "UNAVAILABLE with request_planning_review",
        "whole_run_zero_calls_or_effects": False,
        "arbitrary_validation_error_classification": False,
        "raw_context_or_error_text": False,
        "automatic_retry": False,
        "planner_admission_limits": "pinned upstream rules unchanged",
    },
    "diagnostic": {
        "optional": True,
        "scope": "selection_calls",
        "stages": ["tool_selection", "parameter_selection"],
        "fields": ["stage", "tool_id", "parameter", "reason_codes", "automatic_retry"],
        "reason_codes": sorted(PROVIDER_CODES | SELECTION_CODES | PLANNING_CODES),
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
    "adoption": "Give the primary AI an open goal, define trusted tools and fresh parameter providers, then choose direct operation or Jev delegation before the first operation. Inspect spec, generate a thin task, check it offline and consume independently verified artifact evidence. Keep exact work in code; reconcile uncertain effects before any rerun.",
    "limits": {
        "tools": 250,
        "parameter_options": 253,
        "independent_inference_workers": 30,
        "max_steps_default": 20,
        "timeout_seconds_default": 120,
        "result_cache": False,
        "decision_context_characters": CONTEXT_CHARACTER_LIMIT,
    },
}
