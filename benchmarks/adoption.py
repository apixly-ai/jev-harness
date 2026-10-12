"""Opt-in unforced route evaluation: task-specific handoff vs released presentation.

Both arms use the same current runtime and source tools. 'legacy' is an interface
projection control copied from v0.2.1, not execution of the old runtime. Scripts are
prepared by the evaluator; this does not measure AI script authoring.
"""

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from _private_files import secure_fs as _secure_fs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
BASELINE = "eec0d58f52ce157bfcb1fca669a21c3068eefa19"


def legacy_tools():
    source = subprocess.check_output(
        ["git", "show", BASELINE + ":src/apixly_jev_harness/mcp.py"], cwd=ROOT, text=True
    )
    tree = ast.parse(source)
    return next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets)
    )


class AuditOutput:
    def __init__(self, destination, ledger, legacy=False):
        self.destination, self.ledger, self.legacy = destination, ledger, legacy

    def write(self, line):
        packet = json.loads(line)
        result = packet.get("result", {})
        if self.legacy and isinstance(result, dict):
            result.pop("structuredContent", None)
            result.pop("instructions", None)
            for block in result.get("content", []):
                if block.get("type") == "text":
                    data = json.loads(block["text"])
                    if isinstance(data, dict):
                        data.pop("report", None)
                    block["text"] = json.dumps(data, ensure_ascii=False)
        encoded = json.dumps(packet, ensure_ascii=False) + "\n"
        self.ledger.write(encoded)
        self.ledger.flush()
        return self.destination.write(encoded)

    def flush(self):
        self.destination.flush()


def server(args):
    if args.record_contract == "current":
        from repository_task import build
    else:
        from open_tasks import build

    from apixly_jev_harness import TaskScript, ToolkitSession, mcp

    actor = json.loads(Path(args.actor).read_text(encoding="utf-8"))
    if args.credential_file:
        os.environ["TYPESAFE_API_KEY_FILE"] = args.credential_file
    script = TaskScript(build)
    session = ToolkitSession(
        script,
        goal=actor["goal"],
        inputs=actor["inputs"],
        max_steps=20,
        timeout_seconds=220,
        archive=Path(args.result).with_suffix(".jev.jsonl"),
    )
    if args.presentation == "legacy":
        baseline = legacy_tools()
        mcp.describe_tools = lambda session, allow_delegate=True, **kwargs: [
            t for t in baseline if allow_delegate or t["name"] != "run_task"
        ]
    started = time.perf_counter()

    def checkpoint():
        task = script._task
        packet = {
            "steps": session.steps,
            "routes": session.events,
            "seconds": time.perf_counter() - started,
            "uncertain": session._uncertain,
        }
        if task is not None:
            packet["complete"] = task.verify(session.ctx, task.observe(session.ctx))
            packet["artifact"] = task.artifact_receipt()
        Path(args.result).write_text(json.dumps(packet), encoding="utf-8", newline="\n")

    trace = Path(args.result).with_suffix(".rpc.jsonl")
    fd = _secure_fs.open_private_file(trace, "x")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as ledger:
            mcp.serve(
                session,
                execution_name="collect_source_evidence"
                if args.presentation == "named"
                else "run_task",
                destination=AuditOutput(sys.stdout, ledger, args.presentation == "legacy"),
                checkpoint=checkpoint,
            )
    finally:
        checkpoint()
        if script._task:
            for pack in script._task.toolkits:
                pack.close()


def trial(
    out,
    level,
    variant,
    presentation,
    credential_file,
    primary_model,
    objective="neutral",
    record_contract="markers",
):
    import hashlib

    from adoption_cases import fixture, independent_check
    from primary_cli import run_mcp_session

    directory = out / f"{level}-{variant}-{presentation}"
    directory.mkdir(parents=True, exist_ok=False)
    case = fixture(directory / "sources", level, variant)
    case["inputs"]["output"] = str(directory / "report.json")
    actor = directory / "actor.json"
    actor.write_text(
        json.dumps({"goal": case["goal"], "inputs": case["inputs"]}), encoding="utf-8", newline="\n"
    )
    provenance = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "src/apixly_jev_harness").glob("*.py")
    }
    started = time.perf_counter()
    prompt = case["goal"]
    if objective == "efficient":
        prompt += (
            "\nUse as few sequential client tool interactions as practical while preserving "
            "factual accuracy and independent source checks."
        )
    result = run_mcp_session(
        prompt
        + "\nReturn whether the saved report passes the task completion check and a concise summary.",
        {
            "type": "object",
            "properties": {
                "complete": {"type": "boolean"},
                "summary": {"type": "string"},
                "approach_reason": {
                    "type": "string",
                    "description": "Briefly state the practical reason for the execution approach chosen.",
                },
            },
            "required": ["complete", "summary", "approach_reason"],
            "additionalProperties": False,
        },
        model=primary_model,
        mcp_command=str(ROOT / ".venv/bin/python"),
        mcp_args=[
            str(Path(__file__).resolve()),
            "--server",
            "--actor",
            str(actor),
            "--result",
            str(directory / "server.json"),
            "--presentation",
            presentation,
            "--credential-file",
            credential_file,
            "--record-contract",
            record_contract,
        ],
        timeout_seconds=260,
        private_events_path=directory / "primary.jsonl",
        private_diagnostics_path=directory / "stderr.log",
    )
    seconds = time.perf_counter() - started
    checkpoint = (
        json.loads((directory / "server.json").read_text(encoding="utf-8"))
        if (directory / "server.json").exists()
        else None
    )
    verified = independent_check(case, directory / "report.json")
    packet = {
        "track": "execution_after_preparation",
        "level": level,
        "variant": variant,
        "presentation": presentation,
        "objective": objective,
        "actor_record_contract": record_contract,
        "comparison_scope": "same-runtime interface projection control vs task-bound typed handoff",
        "baseline_presentation_source": BASELINE,
        "primary": result,
        "server": checkpoint,
        "independent_verification": verified,
        "whole_operation_seconds": seconds,
        "source_sha256": provenance,
        "script_authoring_measured": False,
        "product_skill_disabled": True,
        "route_preference_in_prompt": False,
    }
    (directory / "result.json").write_text(
        json.dumps(packet, indent=2), encoding="utf-8", newline="\n"
    )
    return packet


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--server", action="store_true")
    p.add_argument("--actor")
    p.add_argument("--result")
    p.add_argument("--presentation", choices=["legacy", "task", "named"], default="task")
    p.add_argument("--live", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--credential-file")
    p.add_argument("--primary-model", default="gpt-6.1-sol")
    p.add_argument("--objective", choices=["neutral", "efficient"], default="neutral")
    p.add_argument("--record-contract", choices=["markers", "current"], default="markers")
    p.add_argument(
        "--levels", nargs="+", choices=["short", "medium", "missing"], default=["short", "medium"]
    )
    p.add_argument(
        "--presentations",
        nargs="+",
        choices=["legacy", "task", "named"],
        default=["legacy", "task"],
    )
    p.add_argument("--variant", type=int, choices=[0, 1], default=0)
    args = p.parse_args()
    if args.server:
        return server(args)
    if not args.live or not args.output or not args.credential_file:
        p.error("live, output and credential-file are required for paid execution")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for level in args.levels:
        for presentation in args.presentations:
            row = trial(
                out,
                level,
                args.variant,
                presentation,
                args.credential_file,
                args.primary_model,
                args.objective,
                args.record_contract,
            )
            rows.append(row)
            (out / "results.json").write_text(
                json.dumps(rows, indent=2), encoding="utf-8", newline="\n"
            )
            routes = (row["server"] or {}).get("routes", [])
            print(
                json.dumps(
                    {
                        "level": level,
                        "presentation": presentation,
                        "delegated": any(r.get("route") == "jev" for r in routes),
                        "passed": row["independent_verification"]["passed"],
                        "seconds": row["whole_operation_seconds"],
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
