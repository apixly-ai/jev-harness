"""Opt-in real open-task acceptance, direct comparison and unforced route choice."""

import argparse
import hashlib
import json
import os
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from open_tasks import ROOT, build, fixture, independent_check
from primary_cli import run_mcp_session


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def trial(out, family, arm, variant, credential_file, primary_model, missing=False):
    from apixly_jev_harness import AgentLoop, TaskScript

    directory = out / f"{family}-{variant}-{arm}"
    directory.mkdir(parents=True, exist_ok=False)
    case = fixture(directory / "sources", family, variant, missing)
    case["inputs"]["output"] = str(directory / "report.json")
    http = None
    if family != "files":
        http = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(Handler, directory=str(directory / "sources"))
        )
        Thread(target=http.serve_forever, daemon=True).start()
        case["inputs"]["url"] = f"http://127.0.0.1:{http.server_port}/index.html"
    case_path = directory / "actor.json"
    # Never put hidden route oracle into the MCP server/actor configuration.
    case_path.write_text(
        json.dumps({"goal": case["goal"], "inputs": case["inputs"]}), encoding="utf-8", newline="\n"
    )
    provenance = {
        "runtime": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
        },
        "runner": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                ROOT / "benchmarks/open_tasks.py",
                ROOT / "benchmarks/primary_cli.py",
            ]
        },
        "fixtures": {
            str(p.relative_to(directory / "sources")): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((directory / "sources").rglob("*"))
            if p.is_file()
        },
    }
    (directory / "provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8", newline="\n"
    )
    started = time.perf_counter()
    workflow = None
    try:
        if arm == "jev":
            os.environ["TYPESAFE_API_KEY_FILE"] = credential_file
            workflow = TaskScript(build)
            result = AgentLoop().run(
                workflow,
                goal=case["goal"],
                inputs=case["inputs"],
                max_steps=12,
                timeout_seconds=150,
                archive=directory / "jev.jsonl",
            )
            packet = {"route": "jev", "terminal": result, "actual_primary_usage": None}
        else:
            schema = {
                "type": "object",
                "properties": {"complete": {"type": "boolean"}, "summary": {"type": "string"}},
                "required": ["complete", "summary"],
                "additionalProperties": False,
            }
            prompt = (
                case["goal"]
                + "\nUse the available task tools. Return whether the saved report passes the task completion check and a concise summary."
            )
            result = run_mcp_session(
                prompt,
                schema,
                model=primary_model,
                mcp_command=str(ROOT / ".venv/bin/python"),
                mcp_args=[
                    str(ROOT / "benchmarks/open_tasks.py"),
                    "--server",
                    "--case",
                    str(case_path),
                    "--result",
                    str(directory / "server.json"),
                    "--mode",
                    "choice" if arm == "choice" else "direct",
                    "--credential-file",
                    credential_file,
                ],
                timeout_seconds=240,
                private_events_path=directory / "primary-events.jsonl",
                private_diagnostics_path=directory / "primary-stderr.log",
            )
            server_result = (
                json.loads((directory / "server.json").read_text(encoding="utf-8"))
                if (directory / "server.json").exists()
                else None
            )
            packet = {"route": arm, "primary": result, "server": server_result}
        packet["whole_operation_seconds"] = time.perf_counter() - started
        captures_path = directory / "server.captures.json"
        if workflow is not None and workflow._task is not None:
            captures_path.write_text(
                json.dumps(
                    {
                        ref: {"source": row["source"], "sha256": row["sha256"], "text": row["text"]}
                        for ref, row in workflow._task.store._sources.items()
                    }
                ),
                newline="\n",
                encoding="utf-8",
            )
        packet["independent_verification"] = independent_check(
            case, case["inputs"]["output"], captures_path=captures_path
        )
        packet["provenance"] = provenance
        packet["case"] = family
        packet["variant"] = variant
        packet["missing_source"] = missing
        packet["actor_received_expected_oracle"] = False
        packet["prompt_scope"] = (
            "goal plus saved-artifact result requirement; no instruction to inspect references or prefer a route"
        )
        (directory / "result.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2), newline="\n", encoding="utf-8"
        )
        return packet
    finally:
        if workflow is not None and workflow._task is not None:
            for pack in workflow._task.toolkits:
                if callable(getattr(pack, "close", None)):
                    pack.close()
        # A CLI host may terminate its stdio child before its Python finally runs.
        # Reconcile only tab IDs durably recorded as owned by this trial.
        receipt_path = directory / "server.json"
        if family == "browser" and arm != "jev" and receipt_path.exists():
            from jev_context.act.browser import CamofoxPage

            for owned in json.loads(receipt_path.read_text(encoding="utf-8")).get(
                "owned_browser_tabs", []
            ):
                page = CamofoxPage("general", tab=owned["tab"], base=owned["base"])
                page.api("DELETE", f"/tabs/{page.tab}", {"userId": page.user}, timeout=10)
        if http is not None:
            http.shutdown()
            http.server_close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--credential-file", required=True)
    p.add_argument("--primary-model", default="gpt-6.1-sol")
    p.add_argument(
        "--families",
        nargs="+",
        choices=["http", "files", "browser"],
        default=["http", "files", "browser"],
    )
    p.add_argument(
        "--arms",
        nargs="+",
        choices=["jev", "direct", "choice"],
        default=["jev", "direct", "choice"],
    )
    p.add_argument("--variant", type=int, choices=[0, 1], default=0)
    p.add_argument("--missing", action="store_true")
    args = p.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for family in args.families:
        for arm in args.arms:
            row = trial(
                args.output,
                family,
                arm,
                args.variant,
                args.credential_file,
                args.primary_model,
                args.missing,
            )
            rows.append(row)
            (args.output / "results.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), newline="\n", encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "family": family,
                        "arm": arm,
                        "independent_pass": row["independent_verification"]["passed"],
                        "seconds": row["whole_operation_seconds"],
                        "terminal": row.get("terminal", {}).get("status"),
                        "primary_ok": row.get("primary", {}).get("ok"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
