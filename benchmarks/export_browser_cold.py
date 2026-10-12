"""Export public browser cold-start receipts from private result directories.

Only whitelisted fields are copied: no local paths, raw transcripts, page text,
credentials or tab/ticket identifiers. Failed and infrastructure attempts are kept.
"""

import argparse
import json
from pathlib import Path


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _runtime(evidence):
    if not evidence:
        return None
    headless, humanize = evidence.get("headless") or {}, evidence.get("humanize") or {}
    return {
        "passed": evidence.get("passed"),
        "problems": evidence.get("problems"),
        "context_active": (evidence.get("context") or {}).get("user_active"),
        "service": evidence.get("service"),
        "browser_processes": headless.get("browser_processes"),
        "all_browser_processes_headless": headless.get("all_browser_processes_headless"),
        "session_mapping": headless.get("session_mapping"),
        "session_profile_process": headless.get("session_profile_process"),
        "visible_windows": headless.get("visible_windows"),
        "pointer_moves": humanize.get("moves"),
        "pointer_distinct_positions": humanize.get("distinct_positions"),
        "pointer_span_ms": humanize.get("span_ms"),
        "probe_tab_owned_and_closed": evidence.get("probe_tab_owned_and_closed"),
    }


def _primary(packet):
    inventory = packet.get("effective_inventory") or {}
    return {
        key: packet.get(key)
        for key in (
            "ok",
            "status",
            "reason",
            "model_requested",
            "models_resolved",
            "model_fallbacks",
            "tool_calls",
            "unexpected_tool_calls",
            "permission_denials",
            "num_turns",
            "usage_scope",
            "usage_complete",
            "usage_by_model",
            "cli_reported_cost_usd_estimate",
            "whole_process_seconds",
            "final_output",
        )
    } | {
        "effective_inventory": {
            "tools": inventory.get("tools"),
            "non_evaluation_tools": inventory.get("non_evaluation_tools"),
            "mcp_servers": inventory.get("mcp_servers"),
            "skills": inventory.get("skills"),
            "slash_commands": inventory.get("slash_commands"),
            "permission_mode": inventory.get("permission_mode"),
            "builtin_plugins": [row.get("name") for row in inventory.get("plugins") or []],
        }
    }


def arm(directory, name):
    result = _read(Path(directory) / f"{name}-result.json")
    script = result.get("script_execution")
    return {
        "arm": name,
        "route": result.get("route"),
        "effects": result.get("effects"),
        "tool_counts": result.get("tool_counts"),
        "independent_check": result.get("independent_check"),
        "backend_saved": (result.get("backend") or {}).get("saved"),
        "save_attempts": (result.get("backend") or {}).get("save_attempts"),
        "authored_python_files": len(result.get("authored_python") or []),
        "run_script_used": script is not None,
        "jev_usage": None
        if script is None
        else (script.get("bridge") or {}).get("actual_model_usage"),
        "whole_operation_seconds": result.get("whole_operation_seconds"),
        "serve_finalized": result.get("serve_finalized"),
        "tab_cleanup": result.get("tab_cleanup"),
        "container_cleanup": result.get("container_cleanup"),
        "runtime_evidence": _runtime(result.get("runtime_evidence")),
        "budgets": result.get("budgets"),
        "route_preference_in_prompt": result.get("route_preference_in_prompt"),
        "objective": result.get("objective", "neutral"),
        "objective_note": result.get("objective_note"),
        "product_skill_disabled": result.get("product_skill_disabled"),
        "approved_tools": result.get("approved_tools"),
        "primary": _primary(result.get("primary") or {}),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--failed-pair", type=Path, required=True)
    parser.add_argument("--transport-canary", type=Path, required=True)
    parser.add_argument("--worker-canary", type=Path, action="append", required=True)
    parser.add_argument("--isolation-canary", type=Path, required=True)
    parser.add_argument("--rehearsal", type=Path, required=True)
    parser.add_argument("--cost-premise", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    transport = _read(args.transport_canary / "report.json")
    workers = []
    for directory in args.worker_canary:
        report = _read(directory / "worker-canary.json")
        direct, worker = report["phases"]["direct"], report["phases"]["worker"]
        packet = worker.get("packet") or {}
        workers.append(
            {
                "passed": report["passed"],
                "direct_effects": direct.get("effects"),
                "direct_check": (direct.get("independent_check") or {}).get("passed"),
                "direct_process_seconds": (direct.get("process") or {}).get("seconds"),
                "worker_terminal": (packet.get("terminal") or {}).get("status"),
                "worker_effects": worker.get("effects"),
                "worker_engine_seconds": (packet.get("terminal") or {}).get("elapsed_seconds"),
                "fake_provider_submissions": (packet.get("bridge") or {}).get("mock_submissions"),
                "unknown_fake_submissions": (packet.get("bridge") or {}).get(
                    "unknown_mock_usage_attempts"
                ),
                "whole_seconds": report["whole_seconds"],
                "actual_model_usage": report["actual_model_usage"],
            }
        )
    isolation = _read(args.isolation_canary / "canary.json")
    rehearsal = _read(args.rehearsal / "rehearsal.json")
    failed = [arm(args.failed_pair, name) for name in ("native", "optional")]
    for row in failed:
        servers = row["primary"]["effective_inventory"]["mcp_servers"] or []
        connected = any(
            s.get("name") == "jev_eval" and s.get("status") == "connected" for s in servers
        )
        # Recorded before the adapter disqualified unconnected servers; re-judged here.
        row["qualified_under_current_adapter"] = connected
        row["requalified_reason"] = None if connected else "evaluation_server_not_connected"
    report = {
        "track": "browser_cold_start_route_choice",
        "date": "2026-10-12",
        "goal_variant": 0,
        "primary_cli": "Claude Code CLI (headless -p, stream-json), requested claude-opus-5-5, effort high",
        "isolation": "Linux container (python:3.12-slim) on dockerd inside WSL Ubuntu; network none, read-only corpus/runtime, writable /work, uid 1000, no oracle/credential/docker socket",
        "browser": "camofox-browser 2.4.8 (Camoufox 152.0.4 beta.30), headless, humanize, named session general, Windows 11",
        "transport_acceptance": {
            "host_program_path": {
                "passed": transport["passed"],
                "effects": transport["effects"],
                "check": transport["check"],
                "whole_seconds": transport["whole_seconds"],
                "runtime_evidence": _runtime(transport["health"].get("runtime_evidence")),
                "actual_model_usage": transport["actual_model_usage"],
            },
            "humanize_negative_control": {
                "configuration": "separate temporary Camofox instance with CAMOFOX_HUMANIZE=false",
                "pointer_moves": 1,
                "pointer_span_ms": 0,
                "scope": "private probe console output; discriminates the trajectory probe",
            },
            "docker_ipc": workers,
            "container_isolation": {
                "passed": isolation["passed"],
                "isolation": isolation["isolation"],
                "empty_work_before": isolation["empty_work_before"],
            },
            "serve_rehearsal": {
                "passed": rehearsal["passed"],
                "observed_actions": rehearsal["observed_actions"],
                "initial_check": rehearsal["initial_check"],
                "effects": rehearsal["collected"]["effects"],
                "runtime_evidence": _runtime(rehearsal["collected"]["runtime_evidence"]),
                "launch": "foreign working directory and stripped environment, as the primary CLI launches MCP servers",
            },
        },
        "infrastructure_failed_attempt": {
            "cause": "serve received relative paths and the CLI starts MCP servers in its own working directory; jev_eval never connected, so neither arm had task tools",
            "counted_as_task_result": False,
            "arms": failed,
            "fix": "absolute serve paths, foreign-cwd rehearsal, unconnected server disqualifies the turn",
        },
        "pair": [arm(args.pair, name) for name in ("native", "optional")],
        "post_completion_defect": {
            "arm": "optional",
            "observation": "after the independent check had passed, a final shell call to write an optional report found the actor container gone",
            "cause": "the WSL distribution stopped while idle between short-lived wsl.exe docker calls",
            "effect_on_route_or_result": "none observed; route chosen at session start, saved state already verified",
            "fix": "one attached wsl.exe keep-alive session for the run",
        },
        "cost_premise_run": None
        if args.cost_premise is None
        else {
            "design": "optional arm only, same goal, tools, budgets and model as the counted pair; the prompt adds the recorded operator cost note (published list prices and the operator's expectation), naming no tool or route",
            "price_sources": {
                "jev": "docs.typesafe.ai/models: jev-1.13.0 $0.042 per million input tokens, output free",
                "claude": "platform.claude.com/docs/en/about-claude/pricing: Haiku 5.5 $0.10/$0.50 (prompts up to 100K), Opus 5.5 $4/$20",
                "openai": "developers.openai.com/api/docs/pricing: gpt-5.6-luna $0.20/$1.20 (up to 272K input)",
                "checked": "2026-10-12",
            },
            "arm": arm(args.cost_premise, "optional"),
        },
        "scope": "one pair, one variant; not a success-rate, latency or cost distribution",
        "pricing": "CLI-reported cost fields are estimates from the CLI, not invoices",
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
