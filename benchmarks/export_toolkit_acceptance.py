"""Project private synthetic trial receipts into a publishable evidence ledger.

No provider keys, host paths, raw CLI transcripts or private journals are exported.
This is a report exporter, not a live test runner.
"""

import argparse
import hashlib
import json
from pathlib import Path


def json_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def project(row, directory):
    actor = json.loads((directory / "actor.json").read_text())
    markers = actor["inputs"]["requirements"]
    terminal = row.get("terminal") or {}
    primary = row.get("primary") or {}
    telemetry = terminal.get("telemetry") or {}
    calls = telemetry.get("calls") or []
    models = {}
    for call in calls:
        for name, usage in call.get("models", {}).items():
            total = models.setdefault(name, {})
            for field, value in usage.items():
                if type(value) is int:
                    total[field] = total.get(field, 0) + value
    server = row.get("server") or {}
    routes = server.get("routes", [])
    mcp_returned = 0
    activity = []
    events = directory / "primary-events.jsonl"
    if events.exists():
        for line in events.read_text().splitlines():
            event = json.loads(line)
            item = event.get("item") or {}
            if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
                mcp_returned += json_bytes(item.get("result"))
                activity.append(item.get("tool"))
    intents = []
    journal = directory / "jev.jsonl"
    if journal.exists():
        for line in journal.read_text().splitlines():
            event = json.loads(line)
            if event.get("event") == "intent":
                intents.append(event["params"].get("tool", event.get("action_id")))
    strengthened = directory / "verification-strengthened.json"
    verification = row.get("independent_verification")
    verification_scope = "original trial checker"
    if strengthened.exists():
        supplemental = json.loads(strengthened.read_text())
        verification = supplemental["result"]
        verification_scope = supplemental["browser_capture_scope"]
    fixture_root = directory / "sources"
    fixture_hashes = {
        str(p.relative_to(fixture_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(fixture_root.rglob("*"))
        if p.is_file()
    }
    report = directory / "report.json"
    artifact = None
    if report.exists():
        data = json.loads(report.read_text())
        artifact = {
            "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "records": [
                {
                    k: value
                    for k, value in r.items()
                    if k in ("label", "ref", "offset", "end", "total", "sha256")
                }
                for r in data.get("records", [])
            ],
        }
    return {
        "case": row["case"],
        "variant": row["variant"],
        "arm": row["route"],
        "missing_source": row["missing_source"],
        "whole_operation_seconds": row["whole_operation_seconds"],
        "terminal_status": terminal.get("status") or primary.get("status"),
        "reason": terminal.get("reason") or primary.get("reason"),
        "independent_verification": verification,
        "verification_scope": verification_scope,
        "steps": terminal.get("steps", server.get("steps")),
        "chosen_route": "jev"
        if row["route"] == "jev"
        or any(x.get("route") == "jev" for x in routes)
        or "run_task" in activity
        or "delegate" in activity
        else "direct"
        if activity
        else "unknown",
        "tool_sequence": intents or [x.get("tool") for x in routes if x.get("tool")],
        "primary_mcp_sequence": activity,
        "jev": {
            "model_requested": sorted(
                {c["model_requested"] for c in calls if c.get("model_requested")}
            ),
            "model_resolved": sorted(
                {c["model_resolved"] for c in calls if c.get("model_resolved")}
            ),
            "requests": telemetry.get("requests"),
            "actual_usage": telemetry.get("usage"),
            "usage_complete": telemetry.get("usage_complete"),
            "models": models,
            "unknown_usage_attempts": sum(c["unknown_usage_attempts"] for c in calls)
            if calls and all(type(c.get("unknown_usage_attempts")) is int for c in calls)
            else None,
            "shared_context_bytes_sum": sum(c.get("context_bytes", 0) for c in calls),
        }
        if terminal
        else None,
        "primary": {
            k: primary.get(k)
            for k in (
                "model_requested",
                "model_resolved",
                "usage_scope",
                "usage_complete",
                "usage",
                "ok",
                "unexpected_item_count",
            )
        }
        if primary
        else None,
        "returned_mcp_result_bytes": mcp_returned if primary else None,
        "artifact": artifact,
        "fixture_sha256": fixture_hashes,
        "provenance": row.get("provenance"),
        "actor_received_route_oracle": row["actor_received_expected_oracle"],
        "prompt_scope": row.get(
            "prompt_scope", "earlier instruction included inspecting state and argument references"
        ),
        "actor_verification_fields": "schema prefixes"
        if all(v.endswith(":") for v in markers.values())
        else "development answer phrases (not a blind task)",
    }


def export(directories):
    groups = []
    for directory in directories:
        rows = json.loads((directory / "results.json").read_text())
        projected = [
            project(r, directory / f"{r['case']}-{r['variant']}-{r['route']}") for r in rows
        ]
        choices = [r for r in projected if r["arm"] == "choice"]
        groups.append(
            {
                "run": directory.name,
                "stage": "bounded acceptance"
                if directory.name
                in (
                    "toolkit-acceptance-frozen-20261011",
                    "toolkit-state-ref-variant0-20261011",
                    "toolkit-variant0-sources-20261011",
                    "toolkit-missing-source-20261011",
                    "toolkit-neutral-goal-20261011",
                )
                else "development, retained negatives and wiring diagnosis",
                "runtime_snapshot_scope": "before-trial source hashes where present, not an imported-bytecode attestation; first 9-arm group predates MCP state_ref requirement and JSON preflight hardening",
                "rows": projected,
                "natural_choice": {
                    "delegated": sum(r["chosen_route"] == "jev" for r in choices),
                    "trials": len(choices),
                },
            }
        )
    return {
        "schema": 1,
        "release": "0.2.0",
        "date": "2026-10-11",
        "scope": "local synthetic source research, repository evidence and actual headless Camofox; no desktop/customer/production data",
        "comparison": "one continuous primary Codex CLI MCP session vs one Jev-native loop over the same registered task tools; setup/authoring not measured",
        "primary_requested": "gpt-6.1-sol/high",
        "primary_resolved": None,
        "costs": {
            "currency_conversion": None,
            "invoice": None,
            "reason": "No current tariff or account invoice established. Actual provider usage is retained separately; cached input is a subset of primary input, not extra tokens.",
        },
        "neutral_choice": "Product skills disabled and both routes available before first effect. Earlier prompts also requested state/reference inspection, a possible direct-route bias; the separate neutral-goal group omits that instruction. No preference rule mandates a route.",
        "timing": "wall perf_counter includes task creation/capture, model/tool decisions, effects, artifact verification, journals and CLI startup/final answer where applicable; excludes fixture/server preparation and script authoring",
        "context": "Jev shared-context-byte sum and primary MCP returned-result bytes are different observed quantities, not directly comparable token savings.",
        "negative_results": "Includes development groups as explicitly labeled; failures and unknown identity/usage are retained. Small samples do not prove general speed/cost or autonomous adoption.",
        "groups": groups,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directories", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = export(args.directories)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(report, out, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
