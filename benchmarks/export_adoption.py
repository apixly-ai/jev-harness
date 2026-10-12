"""Publish bounded adoption/functional receipts without private paths or source bodies."""

import argparse
import json
from pathlib import Path


def _usage(telemetry):
    if not telemetry:
        return None
    calls = telemetry.get("calls", [])
    return {
        "requests": telemetry.get("requests"),
        "usage_complete": telemetry.get("usage_complete"),
        "usage": telemetry.get("usage"),
        "resolved_models": sorted({c["model_resolved"] for c in calls if c.get("model_resolved")}),
        "max_context_bytes": max((c.get("context_bytes", 0) for c in calls), default=None),
    }


def export(root):
    rows = []
    for directory in sorted(root.glob("adoption-*20261012")):
        for path in sorted(directory.glob("**/result.json")):
            packet = json.loads(path.read_text())
            primary, server = packet.get("primary"), packet.get("server")
            if not primary or not server:
                continue
            delegated = any(x.get("route") == "jev" for x in server["routes"])
            telemetry = None
            trace = path.parent / "server.rpc.jsonl"
            if trace.exists():
                for reply in map(json.loads, trace.read_text().splitlines()):
                    data = reply.get("result", {}).get("structuredContent", {})
                    if "telemetry" in data:
                        telemetry = data["telemetry"]
            verified = packet["independent_verification"]["passed"]
            rows.append(
                {
                    "trial": path.parent.relative_to(root).as_posix(),
                    "track": packet.get("track", "prepared_script_execution"),
                    "objective": packet.get("objective", "neutral"),
                    "record_contract": packet.get("actor_record_contract", "schema_markers"),
                    "actual_route": "jev" if delegated else "direct",
                    "independently_verified": verified,
                    "primary_protocol_qualified": primary["ok"],
                    "qualified_substantive_delegation": delegated
                    and verified
                    and primary["ok"]
                    and server["steps"] > 0,
                    "steps": server["steps"],
                    "whole_operation_seconds": packet["whole_operation_seconds"],
                    "primary": {
                        k: primary.get(k)
                        for k in (
                            "model_requested",
                            "model_resolved",
                            "usage_complete",
                            "usage",
                            "reason",
                            "unexpected_item_count",
                        )
                    },
                    "jev": _usage(telemetry),
                    "source_sha256": packet.get("source_sha256"),
                }
            )
    functional = []
    for directory in sorted(root.glob("*jev-functionality-20261012")):
        packet = json.loads((directory / "result.json").read_text())
        result = packet.get("result", packet.get("journal_recovered_terminal"))
        functional.append(
            {
                "trial": directory.name,
                "track": "explicit_delegation_functionality_not_adoption",
                "status": result["status"],
                "steps": result["steps"],
                "reason": result.get("reason"),
                "diagnostic": result.get("diagnostic"),
                "whole_operation_seconds": packet.get("whole_operation_seconds"),
                "loop_elapsed_seconds": result["elapsed_seconds"],
                "independently_verified": packet.get("quality", {}).get("passed", False),
                "jev": _usage(result["telemetry"]),
                "recording_error": packet.get("negative_recording_error"),
                "source_sha256": packet.get("source_sha256"),
            }
        )
    context = json.loads((root / "handoff-context-history-ab-20261012.json").read_text())
    return {
        "scope": "prepared-script source investigations; authoring and unrestricted native operation excluded",
        "historical_baseline": {
            "source": "toolkit-live-2026-10-11.json",
            "free_choices": 5,
            "delegations": 0,
            "first_four_prompt_inspection_caveat": True,
        },
        "interface_control_scope": "same runtime with legacy v0.2.1 metadata projection, not the historical runtime",
        "choice_trials": rows,
        "functionality_trials": functional,
        "offline_context_ab": context,
        "conclusion": "One protocol-qualified, independently verified substantive delegation under a generic client-interaction efficiency objective. Neutral prepared choices remain direct. No unconditional preference or AI authoring claim.",
        "negative_results": "Capacity-stop and label-review failures are retained. Marker-only actor validation did not qualify current-version evidence; caller source checks were strengthened outside the core. Extra CLI resource-discovery activity remains unqualified under the strict prepared helper. One exporter failed after execution; its known terminal/usage were recovered from the journal and whole-operation timing remains unknown.",
        "pricing": "unknown; no tariff, invoice or savings conversion",
        "model_identity": "Jev resolved identities are recorded; requested primary CLI identity is not a resolved provider identity",
        "reproduction": "opt-in benchmarks/adoption.py; synthetic benchmarks/adoption_cases.py, caller benchmarks/repository_task.py; offline benchmarks/handoff_context.py; source hashes per trial",
        "skills_force_route": False,
        "source_text_and_private_paths_exported": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(export(args.private_root), ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
