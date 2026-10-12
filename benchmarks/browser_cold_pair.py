"""Opt-in browser cold-start pair: direct-only control vs optional caller-authored Jev.

Both arms receive the same synthetic goal, real headless Camofox surface, isolated
container shell, total effect budget, session deadline and independent saved-state
check. The optional arm additionally exposes run_script backed by host-only live Jev.
No route preference, product skill or prebuilt task script is supplied. Each arm is
one Claude Code CLI turn (benchmarks/primary_claude.py); failures, unknown usage,
model fallbacks and whole-operation time are retained.
``rehearse`` drives the same serve process with a scripted MCP client and no model.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from _private_files import secure_fs as _secure_fs
from browser_cold import actor_prompt, case_contract, tools
from cold_authoring import ROOT, _write_json

SERVER = Path(__file__).resolve().parent / "browser_cold.py"
OUTPUT_SCHEMA = {
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
}


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_wheel(directory):
    directory = Path(directory).absolute()
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(directory)],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=300,
    )
    wheel = next(directory.glob("*.whl"))
    return wheel, hashlib.sha256(wheel.read_bytes()).hexdigest()


def serve_arguments(
    directory, arm, *, wheel, variant, headless_config, session_seconds, credential
):
    arguments = [
        str(SERVER),
        "serve",
        "--directory",
        str(directory),
        "--arm",
        arm,
        "--wheel",
        str(wheel),
        "--variant",
        str(variant),
        "--session-seconds",
        str(session_seconds),
    ]
    if headless_config is not None:
        arguments += ["--headless-config", str(headless_config)]
    if arm == "optional" and credential is not None:
        arguments += ["--live", "--credential-file", str(credential)]
    return arguments


def collect(directory):
    """Artifacts the arm left behind; the backend snapshot is the independent truth."""
    directory = Path(directory)
    events = _read(directory / "session-events.json") or {}
    script = _read(directory / "script-execution.json")
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
    # A terminated serve process skips its final files; durable mirrors remain the truth.
    finalized = bool(events)
    progress = events or _read(directory / "session-progress.json") or {}
    live = _read(directory / "backend-live.json") or {}
    tool_counts = {}
    for row in progress.get("events", []):
        tool_counts[row.get("tool")] = tool_counts.get(row.get("tool"), 0) + 1
    if script is None:
        route = "direct" if progress.get("effects") else "no_effect"
    else:
        route = script.get("route")
    return {
        "serve_finalized": finalized,
        "independent_check": events.get("independent_check") or live.get("check"),
        "backend": _read(directory / "backend-saved.json") or live.get("backend"),
        "effects": progress.get("effects"),
        "uncertain": progress.get("uncertain"),
        "route": route,
        "tool_counts": tool_counts,
        "authored_python": authored,
        "script_execution": script,
        "session_ready": _read(directory / "session-ready.json"),
        "runtime_evidence": (_read(directory / "browser-running-health.json") or {}).get(
            "runtime_evidence"
        ),
    }


def close_leftover_owned_tab(directory, base=None):
    """Close the arm's own recorded tab only if a terminated serve left it open."""
    import urllib.parse
    import urllib.request

    from browser_cold import CAMOFOX_BASE

    owned = _read(Path(directory) / "owned-tab.json")
    if not owned or owned.get("owned") is not True or not owned.get("tab"):
        return {"owned_tab_recorded": False}
    base = (base or CAMOFOX_BASE).rstrip("/")
    user = "camofox-" + owned["session"]
    query = urllib.parse.urlencode({"userId": user})
    with urllib.request.urlopen(base + "/tabs?" + query, timeout=10) as response:
        open_tabs = {row.get("tabId") for row in json.load(response).get("tabs") or []}
    if owned["tab"] not in open_tabs:
        return {"owned_tab_recorded": True, "left_open": False}
    request = urllib.request.Request(
        base + "/tabs/" + urllib.parse.quote(owned["tab"], safe=""),
        data=json.dumps({"userId": user}).encode(),
        method="DELETE",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10):
        pass
    return {"owned_tab_recorded": True, "left_open": True, "closed_by_runner": True}


def rehearse(output, *, wheel=None, headless_config=None, session_seconds=600):
    """Zero-model serve rehearsal: scripted MCP client, observe/check only, no effects."""
    output = Path(output)
    _secure_fs.make_private_directory(output, parents=True)
    wheel = Path(wheel) if wheel else build_wheel(output / "wheel")[0]
    directory = output / "native"
    started = time.perf_counter()
    process = subprocess.Popen(
        [
            sys.executable,
            *serve_arguments(
                directory,
                "native",
                wheel=wheel,
                variant=0,
                headless_config=headless_config,
                session_seconds=session_seconds,
                credential=None,
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "observe"}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "check_goal"}},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "shell", "arguments": {"command": "cat /corpus/inputs.json"}},
        },
    ]
    body = "".join(json.dumps(row) + "\n" for row in requests).encode("utf-8")
    stdout, stderr = process.communicate(body, timeout=600)
    rows = [json.loads(line) for line in stdout.decode("utf-8").splitlines() if line.strip()]
    by_id = {row["id"]: row["result"] for row in rows}
    observed = by_id.get(3, {}).get("structuredContent", {})
    checked = by_id.get(4, {}).get("structuredContent", {})
    collected = collect(directory)
    report = {
        "passed": process.returncode == 0
        and [row["id"] for row in rows] == [1, 2, 3, 4, 5]
        and [tool["name"] for tool in by_id[2]["tools"]] == [tool["name"] for tool in tools(False)]
        and bool(observed.get("actions"))
        and checked.get("passed") is False
        and collected["effects"] == 0
        and (collected["runtime_evidence"] or {}).get("passed") is True,
        "observed_actions": len(observed.get("actions", [])),
        "initial_check": checked,
        "collected": collected,
        "returncode": process.returncode,
        "stderr_tail": stderr.decode("utf-8", "replace")[-600:],
        "whole_seconds": time.perf_counter() - started,
        "actual_model_usage": {"requests": 0, "models": {}, "usage_complete": True},
        "scope": "zero-model serve rehearsal; scripted MCP client, no effects or inference",
    }
    _write_json(output / "rehearsal.json", report)
    return report


def run_arm(
    output,
    arm,
    *,
    wheel,
    wheel_sha256,
    variant,
    model,
    effort,
    credential,
    headless_config,
    session_seconds,
    primary_timeout,
):
    from primary_claude import run_mcp_session

    directory = output / arm
    case = case_contract(variant)
    prompt = (
        actor_prompt(case)
        + "\nReturn whether the actual saved draft passes the independent check, a concise "
        "summary and the practical reason for the execution approach you chose."
    )
    approved = [tool["name"] for tool in tools(arm == "optional", live=credential is not None)]
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
            variant=variant,
            headless_config=headless_config,
            session_seconds=session_seconds,
            credential=credential,
        ),
        approved_tools=approved,
        timeout_seconds=primary_timeout,
        private_events_path=output / f"{arm}-primary-events.jsonl",
        private_diagnostics_path=output / f"{arm}-primary-stderr.log",
    )
    whole = time.perf_counter() - started
    try:
        tab_cleanup = close_leftover_owned_tab(directory)
    except Exception as error:
        tab_cleanup = {"error_type": type(error).__name__}
    packet = {
        "arm": arm,
        "tab_cleanup": tab_cleanup,
        "variant": variant,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "route_preference_in_prompt": False,
        "product_skill_disabled": True,
        "approved_tools": approved,
        "wheel_sha256": wheel_sha256,
        "primary": primary,
        "whole_operation_seconds": whole,
        **collect(directory),
        "budgets": {
            "browser_effects": 24,
            "session_seconds": session_seconds,
            "jev_steps": 24,
            "jev_seconds": 100,
            "jev_provider_requests": 50,
            "primary_cli_seconds": primary_timeout,
        },
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
    rehearsal.add_argument("--headless-config", type=Path)
    pair = modes.add_parser("pair")
    pair.add_argument("--output", type=Path, required=True)
    pair.add_argument("--arms", default="native,optional")
    pair.add_argument("--variant", type=int, choices=(0, 1), default=0)
    pair.add_argument("--primary-model", default="claude-opus-5-5")
    pair.add_argument("--effort", default="high")
    pair.add_argument("--credential-file", type=Path, required=True)
    pair.add_argument("--headless-config", type=Path)
    pair.add_argument("--session-seconds", type=int, default=600)
    pair.add_argument("--primary-timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if args.mode == "rehearse":
        report = rehearse(args.output, wheel=args.wheel, headless_config=args.headless_config)
        print(
            json.dumps(
                {key: report[key] for key in ("passed", "observed_actions", "whole_seconds")}
            )
        )
        return 0 if report["passed"] else 1
    arms = args.arms.split(",")
    if not arms or any(arm not in ("native", "optional") for arm in arms):
        parser.error("--arms must name native and/or optional")
    _secure_fs.make_private_directory(args.output, parents=True)
    wheel, wheel_sha256 = build_wheel(args.output / "wheel")
    summary = {"arms": arms, "wheel_sha256": wheel_sha256, "results": {}}
    for arm in arms:
        packet = run_arm(
            args.output,
            arm,
            wheel=wheel,
            wheel_sha256=wheel_sha256,
            variant=args.variant,
            model=args.primary_model,
            effort=args.effort,
            credential=args.credential_file,
            headless_config=args.headless_config,
            session_seconds=args.session_seconds,
            primary_timeout=args.primary_timeout,
        )
        summary["results"][arm] = {
            "primary_ok": packet["primary"]["ok"],
            "primary_reason": packet["primary"]["reason"],
            "route": packet["route"],
            "effects": packet["effects"],
            "independent_check": packet["independent_check"],
            "whole_operation_seconds": packet["whole_operation_seconds"],
        }
        print(json.dumps({arm: summary["results"][arm]}, ensure_ascii=False), flush=True)
    _write_json(args.output / "pair-summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
