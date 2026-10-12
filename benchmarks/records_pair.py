"""Opt-in records triage pair: direct-only control vs optional caller-authored Jev.

Both arms receive the same goal, isolated container shell, corpus and independent check
against hidden labels. The optional arm additionally exposes run_script backed by
host-only live Jev. No route preference, product skill or prebuilt task script is
supplied. Each arm is one Claude Code CLI turn (benchmarks/primary_claude.py); failures,
unknown usage, model fallbacks and whole-operation time are retained. ``rehearse`` drives
the same serve process with a scripted MCP client from a foreign working directory.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _private_files import secure_fs as _secure_fs
from browser_cold_pair import OUTPUT_SCHEMA, _read, build_wheel, stop_leftover_container
from cold_authoring import _write_json
from primary_claude import _environment as primary_environment
from records_cold import BUDGETS, CASES, actor_prompt, load_corpus, tools
from records_triage import score

SERVER = Path(__file__).resolve().parent / "records_cold.py"
# Same published list prices as the browser cost note (checked 2026-10-12); the closing
# sentence names this task's kind of work instead of multi-step operation. No route named.
COST_NOTE = (
    "Operator cost note (published list prices, USD per million tokens): Jev "
    "(TypeSafe jev-1.13.0) $0.042 input, output tokens free; Claude Haiku 5.5 $0.10 input, "
    "$0.50 output; OpenAI GPT-5.6 Luna $0.20 input, $1.20 output; your own model, Claude "
    "Opus 5.5, $4 input, $20 output. Jev is cheaper per token than even these small models, "
    "so the operator expects delegating work that Jev can do to lower total model cost "
    "compared with doing all of it yourself."
)
OBJECTIVES = {"neutral": "", "cost": COST_NOTE}


def serve_arguments(
    directory,
    arm,
    *,
    wheel,
    credential=None,
    docker_wsl_distro=None,
    corpus="natural",
    priced_docs=False,
):
    arguments = [
        str(SERVER),
        "serve",
        "--directory",
        str(Path(directory).absolute()),
        "--arm",
        arm,
        "--wheel",
        str(Path(wheel).absolute()),
        "--corpus",
        corpus,
    ]
    if docker_wsl_distro is not None:
        arguments += ["--docker-wsl-distro", docker_wsl_distro]
    if arm == "optional" and credential is not None:
        arguments += ["--live", "--credential-file", str(Path(credential).absolute())]
    if priced_docs:
        arguments.append("--priced-docs")
    return arguments


def final_score(directory, case):
    """Independent score of the saved report, recomputed from the corpus labels."""
    _, labels = load_corpus(case)
    path = Path(directory) / "work" / "report.json"
    if not path.is_file() or _secure_fs.is_link(path):
        return {"passed": False, "problem": "not_saved"}
    try:
        ids = json.loads(path.read_text(encoding="utf-8"))["ids"]
        if type(ids) is not list or any(type(x) is not str for x in ids):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeError):
        return {"passed": False, "problem": "invalid_report"}
    result = score(ids, labels)
    result["passed"] = (
        result["precision"] >= case["min_precision"]
        and result["recall"] >= case["min_recall"]
        and not result["unknown_ids"]
    )
    return result


def collect(directory, case):
    directory = Path(directory)
    events = _read(directory / "session-events.json") or {}
    progress = events or _read(directory / "session-progress.json") or {}
    executions = _read(directory / "script-executions.json") or []
    work = directory / "work"
    authored = [
        {
            "path": path.relative_to(work).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(work.rglob("*.py") if work.is_dir() else [])
        if path.is_file() and not _secure_fs.is_link(path)
    ]
    tool_counts = {}
    for row in progress.get("events", []):
        tool_counts[row.get("tool")] = tool_counts.get(row.get("tool"), 0) + 1
    usage = [((p.get("bridge") or {}).get("actual_model_usage") or {}) for p in executions]
    return {
        "serve_finalized": bool(events),
        "route": "caller_authored_jev" if executions else "direct",
        "tool_counts": tool_counts,
        "authored_python": authored,
        "script_executions": [
            {
                "execution": p.get("execution"),
                "terminal": {
                    k: (p.get("terminal") or {}).get(k)
                    for k in ("status", "complete", "steps", "reason")
                },
                "independent_check": p.get("independent_check"),
                "execution_seconds": p.get("execution_seconds"),
                "logical_submissions": (p.get("bridge") or {}).get("logical_submissions"),
                "actual_model_usage": (p.get("bridge") or {}).get("actual_model_usage"),
            }
            for p in executions
        ],
        "jev_usage_total": {
            "requests": sum(u.get("requests") or 0 for u in usage),
            "input_tokens": sum(u.get("input_tokens") or 0 for u in usage),
            "output_tokens": sum(u.get("output_tokens") or 0 for u in usage),
            "usage_complete": all(u.get("usage_complete") for u in usage) if usage else True,
        },
        "checks": progress.get("checks"),
        "independent_check": final_score(directory, case),
    }


def rehearse(output, *, wheel=None, docker_wsl_distro=None, corpus="natural"):
    """Scripted MCP client, foreign cwd, stripped environment, as the primary CLI launches."""
    output = Path(output).absolute()
    _secure_fs.make_private_directory(output, parents=True)
    started = time.perf_counter()
    if wheel is None:
        wheel, _ = build_wheel(output / "wheel")
    requests = [
        {"jsonrpc": "2.0", "id": "probe", "method": "server/discover"},
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "check_goal", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "shell", "arguments": {"command": "wc -l /corpus/records.jsonl"}},
        },
    ]
    with tempfile.TemporaryDirectory() as foreign:
        completed = subprocess.run(
            [
                sys.executable,
                *serve_arguments(
                    output / "optional",
                    "optional",
                    wheel=wheel,
                    docker_wsl_distro=docker_wsl_distro,
                    corpus=corpus,
                ),
            ],
            cwd=foreign,
            env=primary_environment(),
            input="".join(json.dumps(r) + "\n" for r in requests),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
    responses = {}
    for line in completed.stdout.splitlines():
        try:
            row = json.loads(line)
            responses[row["id"]] = row
        except (ValueError, KeyError):
            continue
    names = [t["name"] for t in responses.get(1, {}).get("result", {}).get("tools", [])]
    check = responses.get(2, {}).get("result", {}).get("structuredContent", {})
    shell = responses.get(3, {}).get("result", {}).get("structuredContent", {})
    report = {
        "passed": responses.get("probe", {}).get("error", {}).get("code") == -32601
        and names == ["shell", "check_goal", "run_script"]
        and check.get("problems") == ["not_saved"]
        and shell.get("exit_code") == 0
        and str(CASES[corpus]["count"]) in shell.get("stdout", ""),
        "tools": names,
        "initial_check": check,
        "shell_exit_code": shell.get("exit_code"),
        "exit_code": completed.returncode,
        "stderr_tail": completed.stderr[-1500:],
        "whole_seconds": time.perf_counter() - started,
        "actual_model_usage": "zero: scripted client, no run_script",
    }
    report["container_cleanup"] = stop_leftover_container(output / "optional", docker_wsl_distro)
    _write_json(output / "rehearsal.json", report)
    return report


def run_arm(
    output,
    arm,
    *,
    wheel,
    wheel_sha256,
    model,
    effort,
    credential,
    primary_timeout,
    docker_wsl_distro=None,
    objective="neutral",
    corpus="natural",
    priced_docs=False,
):
    from primary_claude import run_mcp_session

    directory = output / arm
    case = CASES[corpus]
    note = OBJECTIVES[objective]
    prompt = (
        actor_prompt(case)
        + ("\n" + note if note else "")
        + "\nReturn whether the saved report passes the independent check, a concise summary "
        "and the practical reason for the execution approach you chose."
    )
    offered = tools(arm == "optional", priced=priced_docs)
    approved = [tool["name"] for tool in offered]
    started = time.perf_counter()
    primary = run_mcp_session(
        prompt,
        OUTPUT_SCHEMA,
        model=model,
        effort=effort,
        mcp_command=sys.executable,
        mcp_args=serve_arguments(
            directory,
            arm,
            wheel=wheel,
            credential=credential,
            docker_wsl_distro=docker_wsl_distro,
            corpus=corpus,
            priced_docs=priced_docs,
        ),
        approved_tools=approved,
        timeout_seconds=primary_timeout,
        private_events_path=output / f"{arm}-primary-events.jsonl",
        private_diagnostics_path=output / f"{arm}-primary-stderr.log",
    )
    whole = time.perf_counter() - started
    try:
        container_cleanup = stop_leftover_container(directory, docker_wsl_distro)
    except Exception as error:
        container_cleanup = {"error_type": type(error).__name__}
    packet = {
        "arm": arm,
        "case": case,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "objective": objective,
        "objective_note": note or None,
        "priced_tool_docs": priced_docs,
        "run_script_description": next(
            (t["description"] for t in offered if t["name"] == "run_script"), None
        ),
        "route_preference_in_prompt": False,
        "product_skill_disabled": True,
        "approved_tools": approved,
        "wheel_sha256": wheel_sha256,
        "primary": primary,
        "whole_operation_seconds": whole,
        "container_cleanup": container_cleanup,
        **collect(directory, case),
        "budgets": {**BUDGETS, "primary_cli_seconds": primary_timeout},
        "automatic_retry": False,
    }
    _write_json(output / f"{arm}-result.json", packet)
    return packet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    rehearsal = modes.add_parser("rehearse")
    rehearsal.add_argument("--output", type=Path, required=True)
    rehearsal.add_argument("--wheel", type=Path)
    rehearsal.add_argument("--docker-wsl-distro")
    rehearsal.add_argument("--corpus", choices=sorted(CASES), default="natural")
    pair = modes.add_parser("pair")
    pair.add_argument("--output", type=Path, required=True)
    pair.add_argument("--arms", default="native,optional")
    pair.add_argument("--primary-model", default="claude-opus-5-5")
    pair.add_argument("--effort", default="high")
    pair.add_argument("--credential-file", type=Path, required=True)
    pair.add_argument("--primary-timeout", type=int, default=1200)
    pair.add_argument("--docker-wsl-distro")
    pair.add_argument("--objective", choices=sorted(OBJECTIVES), default="neutral")
    pair.add_argument("--corpus", choices=sorted(CASES), default="natural")
    pair.add_argument("--priced-docs", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "rehearse":
        report = rehearse(
            args.output,
            wheel=args.wheel,
            docker_wsl_distro=args.docker_wsl_distro,
            corpus=args.corpus,
        )
        print(json.dumps({k: report[k] for k in ("passed", "tools", "whole_seconds")}))
        return 0 if report["passed"] else 1
    arms = args.arms.split(",")
    if not arms or any(arm not in ("native", "optional") for arm in arms):
        parser.error("--arms must name native and/or optional")
    _secure_fs.make_private_directory(args.output, parents=True)
    wheel, wheel_sha256 = build_wheel(args.output / "wheel")
    summary = {
        "arms": arms,
        "objective": args.objective,
        "corpus": args.corpus,
        "priced_tool_docs": args.priced_docs,
        "wheel_sha256": wheel_sha256,
    }
    summary["results"] = {}
    for arm in arms:
        packet = run_arm(
            args.output,
            arm,
            wheel=wheel,
            wheel_sha256=wheel_sha256,
            model=args.primary_model,
            effort=args.effort,
            credential=args.credential_file,
            primary_timeout=args.primary_timeout,
            docker_wsl_distro=args.docker_wsl_distro,
            objective=args.objective,
            corpus=args.corpus,
            priced_docs=args.priced_docs,
        )
        summary["results"][arm] = {
            "primary_ok": packet["primary"]["ok"],
            "primary_reason": packet["primary"]["reason"],
            "route": packet["route"],
            "independent_check": packet["independent_check"],
            "jev_usage_total": packet["jev_usage_total"],
            "whole_operation_seconds": packet["whole_operation_seconds"],
        }
        print(json.dumps({arm: summary["results"][arm]}, ensure_ascii=False), flush=True)
    _write_json(args.output / "pair-summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
