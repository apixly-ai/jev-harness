"""Fixed synthetic, real stdio MCP metadata A/B; no inference or external network."""

import argparse
import copy
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "f667e102c568b3b555e87217b9a40371587cb361"
CALLBACK_HINTS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}
REPORT_HINTS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
CASES = (
    "plain_direct",
    "plain_default",
    "lazy_default",
    "lazy_direct",
    "lazy_named",
    "callback_reads",
    "direct_effect",
    "irreversible_gate",
    "saved_report",
)
FIXTURE = """import atexit
import json
import socket
from pathlib import Path
import httpx
from apixly_jev_harness import Option, Parameter, Task, TaskScript
from apixly_jev_harness import backend
from apixly_jev_harness.engine import AgentLoop
from apixly_jev_harness.evidence import EvidenceStore
from apixly_jev_harness.toolkit import EvidenceTask
CASE = CASE_VALUE
counts = dict(factory=0, observe=0, domain=0, effects=0, report_writes=0,
              native_inference_attempts=0, real_network_attempts=0)
def write_counts():
    Path('counts.json').write_text(json.dumps(counts), encoding='utf-8')
atexit.register(write_counts)
def forbid_model(*args, **kwargs):
    counts['native_inference_attempts'] += 1
    raise AssertionError('offline_model_forbidden')
def forbid_network(*args, **kwargs):
    counts['real_network_attempts'] += 1
    raise AssertionError('offline_network_forbidden')
AgentLoop.decide = forbid_model
backend.native_run = forbid_model
backend.provider_evaluate = forbid_model
httpx.HTTPTransport.handle_request = forbid_network
socket.socket.connect = forbid_network
socket.create_connection = forbid_network
state = {'value': 0}
def observe(ctx):
    counts['observe'] += 1
    return dict(state)
def choices(ctx, seen):
    counts['domain'] += 1
    return [Option('one', 'One synthetic increment', 1)]
def build(inputs):
    counts['factory'] += 1
    task = Task(observe=observe, verify=lambda ctx, seen: seen['value'] == 1)
    @task.tool('Advance the synthetic value', name='advance',
               parameters={'amount': Parameter('Increment', choices)},
               irreversible=CASE == 'irreversible_gate', result_context=lambda value: value)
    def advance(amount):
        counts['effects'] += 1
        state['value'] += amount
        return dict(state)
    return task
if CASE == 'saved_report':
    store = EvidenceStore()
    ref = store.put('Synthetic captured evidence.', 'synthetic-source')
    workflow = EvidenceTask([], store=store, labels=['proof'], output='report.json',
                            verify=lambda ctx, seen: False)
    workflow.record_evidence({'ref': ref, 'offset': 0, 'limit': 1200}, 'proof')
    workflow.save_report()
    counts['report_writes'] += 1
else:
    workflow = TaskScript(build) if CASE.startswith('lazy_') else build({})
"""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def requests(case):
    rows = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]

    def call(name, arguments):
        rows.append(
            {
                "id": len(rows),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )

    state_ref = digest({"value": 0})
    if case in ("callback_reads", "direct_effect", "irreversible_gate"):
        call("observe", {})
    if case == "callback_reads":
        call("observe", {})
        for _ in range(2):
            call("arguments", {"tool": "advance", "parameters": {}, "state_ref": state_ref})
    if case in ("direct_effect", "irreversible_gate"):
        for _ in range(2):
            call(
                "operate",
                {"tool": "advance", "parameters": {"amount": "one"}, "state_ref": state_ref},
            )
    if case == "saved_report":
        call("read_report", {"page": 0})
        call("read_report", {"page": 0})
    return rows


def expected_behavior(case):
    names = ["arguments", "observe", "operate"]
    if not case.endswith("_direct"):
        names.append("collect_evidence" if case == "lazy_named" else "run_task")
    if case.startswith("lazy_") or case == "saved_report":
        names.append("read_report")
    observe, domain = {
        "callback_reads": (4, 4),
        "direct_effect": (4, 2),
        "irreversible_gate": (3, 3),
    }.get(case, (0, 0))
    return {
        "tool_names": names,
        "counts": {
            "factory": int(not case.startswith("lazy_") and case != "saved_report"),
            "observe": observe,
            "domain": domain,
            "effects": int(case == "direct_effect"),
            "report_writes": int(case == "saved_report"),
            "native_inference_attempts": 0,
            "real_network_attempts": 0,
        },
        "tool_errors": {"direct_effect": 1, "irreversible_gate": 2}.get(case, 0),
    }


def trial(case, source):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TYPESAFE_", "OPENAI_", "ANTHROPIC_", "CAMOFOX_"))
    }
    environment["PYTHONPATH"] = str(source)
    with tempfile.TemporaryDirectory(prefix="jev-mcp-annotations-") as directory:
        work = Path(directory)
        fixture = FIXTURE.replace("CASE_VALUE", repr(case))
        (work / "task.py").write_text(fixture, encoding="utf-8")
        command = [
            sys.executable,
            "-B",
            "-m",
            "apixly_jev_harness.mcp",
            "task.py",
            "--goal",
            "Inspect the registered synthetic task",
        ]
        if case.endswith("_direct"):
            command.append("--direct-only")
        if case == "lazy_named":
            command.extend(["--execution-name", "collect_evidence"])
        payload = "".join(json.dumps(row) + "\n" for row in requests(case)).encode()
        started = time.perf_counter()
        completed = subprocess.run(
            command, input=payload, capture_output=True, cwd=work, env=environment, timeout=30
        )
        elapsed = time.perf_counter() - started
        counts = json.loads((work / "counts.json").read_text())
        if completed.returncode or completed.stderr:
            raise AssertionError("stdio_fixture_failed")
        replies = [json.loads(line) for line in completed.stdout.splitlines()]
    tools = replies[1]["result"]["tools"]
    stripped = copy.deepcopy(replies)
    for tool in stripped[1]["result"]["tools"]:
        tool.pop("annotations", None)
    # Source capture IDs are deliberately random; compare report content and hashes.
    for response in stripped[2:]:
        content = response.get("result", {}).get("structuredContent")
        if content and "records" in content:
            content.pop("artifact_sha256", None)
            for record in content["records"]:
                record.pop("ref", None)
            response["result"].pop("content", None)
    hints = {tool["name"]: tool.get("annotations") for tool in tools}
    actual = {
        "tool_names": [tool["name"] for tool in tools],
        "counts": counts,
        "tool_errors": sum(reply.get("result", {}).get("isError") is True for reply in replies),
    }
    offline = counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
    return {
        **actual,
        "behavior_correct": actual == expected_behavior(case),
        "annotations": hints,
        "annotations_correct": all(
            value == (REPORT_HINTS if name == "read_report" else CALLBACK_HINTS)
            for name, value in hints.items()
        ),
        "protocol_sha256_excluding_annotations_and_capture_ids": digest(stripped),
        "counts": counts,
        "fixture_sha256": hashlib.sha256(fixture.encode()).hexdigest(),
        "input_bytes": len(payload),
        "returned_context_bytes": len(completed.stdout),
        "whole_operation_seconds": elapsed,
        "actual_model_usage": {
            "requests": 0 if offline else None,
            "models": {},
            "input_tokens": 0 if offline else None,
            "output_tokens": 0 if offline else None,
            "usage_complete": offline,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("repeats must be positive")
    rows = []
    with tempfile.TemporaryDirectory(prefix="jev-mcp-source-") as directory:
        base = Path(directory)
        baseline = snapshot(BASELINE, base / "baseline")
        shutil.copytree(
            ROOT / "src",
            base / "candidate" / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        source_hashes = {
            arm: hashlib.sha256(
                (base / arm / "src/apixly_jev_harness/mcp.py").read_bytes()
            ).hexdigest()
            for arm in ("baseline", "candidate")
        }
        for repeat in range(args.repeats):
            for case in CASES:
                arms = ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                for arm in arms:
                    rows.append(
                        {
                            "arm": arm,
                            "case": case,
                            "repeat": repeat + 1,
                            **trial(case, base / arm / "src"),
                        }
                    )
    parity = all(
        all(
            pair[0][key] == pair[1][key]
            for key in (
                "tool_names",
                "protocol_sha256_excluding_annotations_and_capture_ids",
                "counts",
                "fixture_sha256",
                "input_bytes",
            )
        )
        for case in CASES
        for repeat in range(1, args.repeats + 1)
        if (pair := [row for row in rows if row["case"] == case and row["repeat"] == repeat])
    )
    summary = {}
    for arm in ("baseline", "candidate"):
        selected = [row for row in rows if row["arm"] == arm]
        summary[arm] = {
            "runs": len(selected),
            "behavior_passes": sum(row["behavior_correct"] for row in selected),
            "annotation_contract_passes": sum(row["annotations_correct"] for row in selected),
            "effects": sum(row["counts"]["effects"] for row in selected),
            "inference_attempts": sum(
                row["counts"]["native_inference_attempts"] for row in selected
            ),
            "network_attempts": sum(row["counts"]["real_network_attempts"] for row in selected),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in selected),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in selected
            ),
        }
    report = {
        "mode": "offline-synthetic-real-stdio-mcp-annotations",
        "baseline_commit": baseline,
        "mcp_source_sha256": source_hashes,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": sys.version.split()[0],
        "expected_behavior": {case: expected_behavior(case) for case in CASES},
        "reproduction": "python benchmarks/mcp_annotations.py --output local-results/mcp-annotations-ab.json",
        "scope": "Nine fixed synthetic stdio sessions, three paired repeats by default with alternating arm order. Covers plain/lazy, direct-only/delegation, renamed execution discovery, callback reads, direct effects with stale retry, irreversible authorization denial and repeated saved-report reads. run_task is listed but never invoked; no inference quality or live caller callbacks are measured.",
        "negative_results": "Explicit hints add returned bytes and local metadata-copy work. No speed, security-score or fee improvement is claimed. Callback-capable tools retain conservative MCP default values; only saved-report reads are declared read-only. Annotation hints do not authorize execution. Report reads include a fixture setup write in both arms, separately counted.",
        "cost_conversion": "No tariff conversion or savings assumed. Actual model usage is zero only for these guarded offline sessions when no inference/network guard fires; this says nothing about live or previous unknown usage. Whole-operation timing includes process startup, imports, fixture setup, all stdio requests, output and exit/count flush; it excludes Git snapshot extraction and final report aggregation. Returned bytes are complete UTF-8 protocol stdout, not provider token estimates.",
        "action_and_protocol_parity": parity,
        "summary": summary,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"action_and_protocol_parity": parity, "summary": summary}))
    return (
        0
        if parity
        and summary["candidate"]["annotation_contract_passes"] == len(CASES) * args.repeats
        and all(row["behavior_correct"] for row in rows)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
