"""Export public receipts for the 2026-10-12 delegation search (repeated tasks, triage).

Only whitelisted fields are copied: no local paths, raw transcripts, credentials or page
text. Failed acceptance attempts, development runs and negative route choices are kept.
Jev cost is computed from actual usage at the published price; primary costs are the
Claude Code CLI's own estimates, not invoices.
"""

import argparse
import json
from pathlib import Path

from export_browser_cold import _primary

JEV_INPUT_USD_PER_MTOK = 0.042  # docs.typesafe.ai/models, checked 2026-10-12; output free


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jev_usd(input_tokens):
    return None if input_tokens is None else round(input_tokens * JEV_INPUT_USD_PER_MTOK / 1e6, 4)


def records_arm(directory, arm):
    result = _read(Path(directory) / f"{arm}-result.json")
    primary = _primary(result.get("primary") or {})
    usage = result.get("jev_usage_total") or {}
    return {
        "arm": arm,
        "corpus": (result.get("case") or {}).get("name", "template"),
        "objective": result.get("objective"),
        "objective_note": result.get("objective_note"),
        "priced_tool_docs": result.get("priced_tool_docs", False),
        "run_script_description": result.get("run_script_description"),
        "route": result.get("route"),
        "tool_counts": result.get("tool_counts"),
        "authored_python_files": len(result.get("authored_python") or []),
        "script_executions": result.get("script_executions"),
        "independent_check": result.get("independent_check"),
        "jev_usage_total": usage,
        "jev_cost_usd_at_published_price": _jev_usd(usage.get("input_tokens")),
        "whole_operation_seconds": result.get("whole_operation_seconds"),
        "serve_finalized": result.get("serve_finalized"),
        "container_cleanup": result.get("container_cleanup"),
        "budgets": result.get("budgets"),
        "route_preference_in_prompt": result.get("route_preference_in_prompt"),
        "product_skill_disabled": result.get("product_skill_disabled"),
        "primary": primary,
    }


def records_acceptance(canary, validation, rehearsal):
    c, v, r = (
        _read(Path(canary) / "canary.json"),
        _read(Path(validation) / "jev-validation.json"),
        _read(Path(rehearsal) / "rehearsal.json"),
    )
    usage = v.get("actual_model_usage") or {}
    return {
        "zero_model_canary": {
            "passed": c["passed"],
            "empty_check": c["empty_check"],
            "oracle_check": c["oracle_check"],
            "partial_check": c["partial_check"],
            "fake_provider_execution": c["fake_provider_execution"],
            "whole_seconds": c["whole_seconds"],
            "scope": c["scope"],
        },
        "live_jev_unedited_scaffold": {
            "passed": v["passed"],
            "terminal": {
                k: (v.get("terminal") or {}).get(k) for k in ("status", "complete", "steps")
            },
            "score": v["private_score"],
            "execution_seconds": v["execution_seconds"],
            "requests": v.get("logical_submissions"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "usage_complete": usage.get("usage_complete"),
            "jev_cost_usd_at_published_price": _jev_usd(usage.get("input_tokens")),
            "scope": v["scope"],
        },
        "foreign_cwd_rehearsal": {
            "passed": r["passed"],
            "tools": r["tools"],
            "initial_check": r["initial_check"],
            "whole_seconds": r["whole_seconds"],
        },
    }


def browser_batch(transport, worker, validations):
    t = _read(Path(transport) / "report.json")
    w = _read(Path(worker) / "worker-canary.json")
    rows = []
    for directory in validations:
        report = _read(Path(directory) / "jev-validation.json")
        rows.append(
            {
                "passed_teams": report["independent_check"]["passed_teams"],
                "effects": report["effects"],
                "uncertain": report["uncertain"],
                "totals": report["totals"],
                "jev_cost_usd_at_published_price": _jev_usd(report["totals"]["input_tokens"]),
                "teams": [
                    {
                        "team": row["team"],
                        "status": (row.get("terminal") or {}).get("status"),
                        "reason": (row.get("terminal") or {}).get("reason"),
                        "steps": (row.get("terminal") or {}).get("steps"),
                        "requests": row.get("requests"),
                        "saved": (row.get("team_check") or {}).get("saved"),
                    }
                    for row in report["rows"]
                ],
            }
        )
    return {
        "zero_model_host_program_path": {
            "passed": t["passed"],
            "effects": t["effects"],
            "passed_teams": t["check"]["passed_teams"],
            "whole_seconds": t["whole_seconds"],
        },
        "zero_model_container_canary": {
            "passed": w["passed"],
            "direct_effects": w["phases"]["direct"].get("effects"),
            "direct_check_passed": (w["phases"]["direct"].get("independent_check") or {}).get(
                "passed"
            ),
            "fake_provider_executions": [
                {
                    "execution": p.get("execution"),
                    "terminal": (p.get("terminal") or {}).get("status"),
                    "mock_submissions": (p.get("bridge") or {}).get("mock_submissions"),
                    "remaining": p.get("remaining"),
                }
                for p in w["phases"]["worker"].get("packets") or []
            ],
            "whole_seconds": w["whole_seconds"],
        },
        "live_jev_reference_script_development_runs": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-pair", type=Path, required=True)
    parser.add_argument("--natural-pair", type=Path, required=True)
    parser.add_argument("--cost-run", type=Path, required=True)
    parser.add_argument("--priced-run", type=Path, required=True)
    parser.add_argument("--template-acceptance", type=Path, nargs=3, required=True)
    parser.add_argument("--natural-acceptance", type=Path, nargs=3, required=True)
    parser.add_argument("--batch-transport", type=Path, required=True)
    parser.add_argument("--batch-worker", type=Path, required=True)
    parser.add_argument("--batch-validation", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    natural_fixture = _read(
        Path(__file__).resolve().parent / "fixtures/triage-natural-v1/generation.json"
    )
    report = {
        "track": "delegation_task_shape_search",
        "date": "2026-10-12",
        "primary_cli": "Claude Code CLI (headless -p, stream-json), requested claude-opus-5-5, effort high",
        "isolation": "Linux container (python:3.12-slim) on dockerd inside WSL Ubuntu; network none, read-only corpus/runtime, writable /work, uid 1000; credential and labels host-only",
        "pricing": {
            "jev": "jev-1.13.0 $0.042 per million input tokens, output free (docs.typesafe.ai/models, checked 2026-10-12)",
            "primary": "cli_reported_cost_usd_estimate is the Claude Code CLI's own estimate, not an invoice",
        },
        "browser_repeated_form": {
            "task": "six team workspaces with differing navigation, labels, page split, pagination and a confirmation step; one draft per team; independent per-team backend check",
            "bounds": "200 browser effects, 12 run_script executions, 600 Jev seconds, 300 provider requests per session",
            **browser_batch(args.batch_transport, args.batch_worker, args.batch_validation),
            "fixture_fixes_retained": [
                "a Borealis field labelled 'Send schedule' was hidden by the send/delete safety filter; renamed 'Repeat schedule'",
                "Fjord's Save button sat below the fold and no route can scroll; review controls moved above the draft preview",
                "repeated executions first failed on create-only artifact files; per-run files are now numbered and summaries replaced atomically",
            ],
            "primary_pair_run": False,
            "reason_no_pair": "the mechanism did not complete any team with a reference script, so a primary choosing it would only measure a known failure",
        },
        "records_triage": {
            "task": "save the ids of notification events that need a page now; independent check needs precision and recall of at least 0.95 against hidden labels",
            "template_corpus": {
                "records": 2000,
                "generator": "benchmarks/records_triage.py (owned templates, seed 20261012)",
                "acceptance": records_acceptance(*args.template_acceptance),
                "pair": [records_arm(args.template_pair, arm) for arm in ("native", "optional")],
            },
            "natural_corpus": {
                "records": natural_fixture["records"],
                "positive": natural_fixture["positive"],
                "generation": {
                    k: natural_fixture[k]
                    for k in (
                        "model",
                        "seed",
                        "records_sha256",
                        "cost_usd_estimate_total",
                        "generator",
                    )
                },
                "acceptance": records_acceptance(*args.natural_acceptance),
                "pair": [records_arm(args.natural_pair, arm) for arm in ("native", "optional")],
                "operator_price_note_run": records_arm(args.cost_run, "optional"),
                "priced_tool_docs_run": records_arm(args.priced_run, "optional"),
            },
            "development_probes_host": {
                "source": "console output of local probe scripts during development (not file receipts)",
                "rows": [
                    {
                        "corpus": "template",
                        "records": 300,
                        "spec": "one question",
                        "precision": 1.0,
                        "recall": 1.0,
                        "requests": 5,
                        "seconds": 1.32,
                    },
                    {
                        "corpus": "template",
                        "records": 2000,
                        "spec": "one question",
                        "precision": 1.0,
                        "recall": 1.0,
                        "requests": 29,
                        "seconds": 3.33,
                    },
                    {
                        "corpus": "thread templates",
                        "records": 600,
                        "spec": "one question",
                        "precision": 0.873,
                        "recall": 0.990,
                        "requests": 9,
                        "seconds": 1.64,
                    },
                    {
                        "corpus": "thread templates",
                        "records": 600,
                        "spec": "four typed questions combined in code",
                        "precision": 0.965,
                        "recall": 0.990,
                        "requests": 26,
                        "seconds": 2.74,
                    },
                    {
                        "corpus": "natural",
                        "records": 1000,
                        "spec": "one question",
                        "precision": 0.990,
                        "recall": 1.0,
                        "requests": 16,
                        "seconds": 2.58,
                    },
                    {
                        "corpus": "natural",
                        "records": 1000,
                        "spec": "four typed questions combined in code",
                        "precision": 0.997,
                        "recall": 1.0,
                        "requests": 46,
                        "seconds": 3.41,
                    },
                ],
            },
        },
        "scope": "one primary model, one sample per condition; route choices and costs are single observations, not rates or distributions",
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
