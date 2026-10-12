"""Blind synthetic open tasks over shared toolkits; continuous primary vs Jev loops.

Actor tools/providers never read the independent expected-source oracle. Live is opt-in.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def build(inputs):
    from apixly_jev_harness.evidence import EvidenceStore
    from apixly_jev_harness.toolkit import EvidenceTask
    from apixly_jev_harness.web_tools import CamofoxProvider, HttpProvider, WebTools
    from apixly_jev_harness.workspace import WorkspaceTools

    store = EvidenceStore()
    if inputs["kind"] == "files":
        pack = WorkspaceTools(inputs["root"], store, queries=inputs["queries"])
    else:
        provider = (
            CamofoxProvider(url=inputs["url"], session="general")
            if inputs["kind"] == "browser"
            else HttpProvider(inputs["url"])
        )
        pack = WebTools(provider, store)

    def verify(ctx, state):
        rows = state["evidence"]["records"]
        return all(
            any(row["label"] == label and text in row["text"] for row in rows)
            for label, text in inputs["requirements"].items()
        )

    return EvidenceTask(
        [pack],
        store=store,
        labels=list(inputs["requirements"]),
        output=inputs["output"],
        verify=verify,
        record_checks={
            label: (lambda row, marker=marker: marker in row["text"])
            for label, marker in inputs["requirements"].items()
        },
    )


def fixture(directory, family, variant=0, missing=False):
    directory.mkdir(parents=True, exist_ok=True)
    salt = "spruce" if variant == 0 else "maple"
    if family == "files":
        files = {
            "README.md": "Worker service. Inspect submit and retry paths and existing tests.",
            f"src/{salt}_worker.py": "def submit(job):\n    # Cause: retry dispatch precedes duplicate reservation.\n    dispatch(job)\n    reserve(job.id)\n",
            f"tests/test_{salt}_worker.txt": "Recorded reproduction: the same job is dispatched twice after retry.",
            "docs/legacy.txt": "Old release: retries were disabled. Not the current worker behavior.",
        }
        if missing:
            files.pop(f"tests/test_{salt}_worker.txt")
        for name, text in files.items():
            p = directory / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        return {
            "goal": "Investigate the current worker duplicate-submission failure. Find source evidence for the cause and a recorded reproduction; save both under cause and proof.",
            "inputs": {
                "kind": "files",
                "root": str(directory),
                "queries": ["submit", "retry", "duplicate"],
                "requirements": {
                    "cause": "Cause:",
                    "proof": "Recorded reproduction:",
                },
            },
            "expected_values": {
                "cause": "retry dispatch precedes duplicate reservation",
                "proof": "the same job is dispatched twice after retry",
            },
            "expected": {
                "cause": f"src/{salt}_worker.py",
                "proof": f"tests/test_{salt}_worker.txt",
            },
        }
    if family == "http":
        facts = {
            "deployment": "Deployment method: OCI container.",
            "storage": "Persistent datastore: SQLite.",
        }
        goal = "Research the current AsterDesk deployment requirements from the entry page. Save source evidence for deployment method and persistent datastore under deployment and storage."
    else:
        facts = {
            "dependency": "Pending dependency: identity-check.",
            "event": "Current event: job-741 blocked by identity-check.",
        }
        goal = "Diagnose why synthetic job-741 is incomplete. Find its pending dependency and matching current event; save evidence under dependency and event."
    entry = [
        "<h1>Service information</h1><p>Follow current resources and their references.</p>",
        '<a href="legacy.html">Details</a>',
        f'<a href="{salt}-index.html">Details</a>',
    ]
    if variant:
        entry.reverse()
    pages = {
        "index.html": "\n".join(entry),
        "legacy.html": '<h1>Historical archive</h1><p>Old release; historical data is not the current service.</p><a href="index.html">Current entry</a>',
        f"{salt}-index.html": "<h1>Current resources</h1>"
        + "".join(f'<a href="{salt}-{label}.html">{label.title()} resource</a>' for label in facts),
    }
    for label, text in facts.items():
        if missing and label == list(facts)[-1]:
            pages[f"{salt}-{label}.html"] = (
                "<h1>Resource unavailable</h1><p>The required current source is unavailable.</p>"
            )
        else:
            pages[f"{salt}-{label}.html"] = (
                f'<h1>{label.title()} reference</h1><p>{text}</p><a href="{salt}-index.html">Other current resources</a>'
            )
    for name, text in pages.items():
        (directory / name).write_text(text, encoding="utf-8", newline="\n")
    return {
        "goal": goal,
        "inputs": {
            "kind": "browser" if family == "browser" else "http",
            "requirements": {label: text.split(":", 1)[0] + ":" for label, text in facts.items()},
        },
        "expected_values": facts,
        "expected": {label: f"{salt}-{label}.html" for label in facts},
    }


def independent_check(case, report_path, *, captures_path=None):
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"passed": False, "reason": "artifact_missing_or_invalid"}
    captures = {}
    if captures_path is not None:
        try:
            captures = json.loads(Path(captures_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    matches = {}
    source_root = (
        Path(case["source_directory"])
        if "source_directory" in case
        else Path(case["inputs"].get("root", Path(report_path).parent / "sources"))
    )
    for label, expected in case["expected"].items():
        rows = [x for x in report.get("records", []) if x.get("label") == label]
        original = (
            (source_root / expected).read_text(encoding="utf-8")
            if (source_root / expected).exists()
            else ""
        )
        if case["inputs"]["kind"] == "http":
            from apixly_jev_harness.web_tools import _TextPage

            parser = _TextPage()
            parser.feed(original)
            original = parser.document("")["text"]

        def authentic(row):
            if case["inputs"]["kind"] == "browser":
                # Static browser fixtures: independently normalize visible source text.
                from apixly_jev_harness.web_tools import _TextPage

                parser = _TextPage()
                parser.feed(original)
                normalized = " ".join(parser.document("")["text"].split())
                offset, end = row.get("offset"), row.get("end")
                return any(
                    type(offset) is int
                    and type(end) is int
                    and capture.get("source", "").endswith(expected)
                    and type(capture.get("text")) is str
                    and 0 <= offset <= end <= len(capture["text"])
                    and row.get("total") == len(capture["text"])
                    and row.get("text") == capture["text"][offset:end]
                    and row.get("sha256")
                    == hashlib.sha256(capture["text"].encode()).hexdigest()
                    == capture.get("sha256")
                    and " ".join(capture["text"].split()) == normalized
                    for capture in captures.values()
                )
            offset, end = row.get("offset"), row.get("end")
            return (
                type(offset) is int
                and type(end) is int
                and 0 <= offset <= end <= len(original)
                and row.get("text") == original[offset:end]
                and row.get("sha256") == hashlib.sha256(original.encode()).hexdigest()
            )

        matches[label] = any(
            x.get("source", "").endswith(expected)
            and case["inputs"]["requirements"][label] in x.get("text", "")
            and case.get("expected_values", {}).get(label, "") in x.get("text", "")
            and authentic(x)
            for x in rows
        )
    return {
        "passed": all(matches.values()),
        "labels": matches,
        "records": len(report.get("records", [])),
    }


def server(args):
    from apixly_jev_harness.mcp import serve
    from apixly_jev_harness.toolkit import TaskScript, ToolkitSession

    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    # The server receives inputs only; expected-route oracle is not admitted to actor tools.
    inputs = case["inputs"]
    if args.credential_file:
        os.environ["TYPESAFE_API_KEY_FILE"] = args.credential_file
    workflow = TaskScript(build)
    session = ToolkitSession(
        workflow,
        goal=case["goal"],
        inputs=inputs,
        max_steps=12,
        timeout_seconds=180,
        archive=str(Path(args.result).with_suffix(".jev.jsonl")),
    )
    started = time.monotonic()

    def checkpoint():
        task = workflow._task
        packet = {
            "steps": session.steps,
            "routes": session.events,
            "seconds": time.monotonic() - started,
            "uncertain": session._uncertain,
            "artifact": inputs["output"],
            "owned_browser_tabs": [],
        }
        if task is not None:
            packet["complete"] = task.verify(session.ctx, task.observe(session.ctx))
            for pack in task.toolkits:
                surface = getattr(getattr(pack, "provider", None), "surface", None)
                if surface is not None and getattr(surface, "owned", False) and surface.tab:
                    packet["owned_browser_tabs"].append(
                        {"base": surface.base, "user": surface.user, "tab": surface.tab}
                    )
            captures = {
                ref: {"source": row["source"], "sha256": row["sha256"], "text": row["text"]}
                for ref, row in task.store._sources.items()
            }
            Path(args.result).with_suffix(".captures.json").write_text(
                json.dumps(captures), newline="\n", encoding="utf-8"
            )
        Path(args.result).write_text(json.dumps(packet, indent=2), encoding="utf-8", newline="\n")

    try:
        serve(session, allow_delegate=args.mode == "choice", checkpoint=checkpoint)
    finally:
        checkpoint()
        if workflow._task is not None:
            for pack in workflow._task.toolkits:
                if callable(getattr(pack, "close", None)):
                    pack.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--server", action="store_true")
    p.add_argument("--case")
    p.add_argument("--result")
    p.add_argument("--mode", choices=["direct", "choice"], default="direct")
    p.add_argument("--credential-file")
    args = p.parse_args()
    if args.server:
        server(args)
    else:
        raise SystemExit("Use the opt-in acceptance runner; no automatic model dispatch.")


if __name__ == "__main__":
    main()
