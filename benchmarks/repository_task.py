"""Caller-owned repository investigation contract, not a core route or fixture oracle.

A normal manifest supplies current version and entry identity. The script checks quoted
current test/release evidence mechanically; Jev still discovers source windows and picks
its tools/arguments. No benchmark expected values, source route oracle or AST simulation
are read here. The separate evaluator validates the actual fixture state transitions.
"""

import hashlib
import json


def build(inputs):
    from apixly_jev_harness import EvidenceStore, EvidenceTask, WorkspaceTools

    store = EvidenceStore()
    pack = WorkspaceTools(inputs["root"], store, queries=inputs["queries"])
    manifest = json.loads(pack._read_text("package.json"))
    version, entry = manifest["version"], manifest["entry"]
    entry_body = pack._read_text(entry)
    entry_hash = hashlib.sha256(entry_body.encode()).hexdigest()

    def implementation(row):
        return (
            row["source"] == "workspace:" + entry
            and row["sha256"] == entry_hash
            and "def submit(" in row["text"]
        )

    def reproduction(row):
        try:
            data = json.loads(row["text"])
        except (TypeError, ValueError):
            return False
        return (
            type(data) is dict
            and data.get("package_version") == version
            and data.get("worker_sha256") == entry_hash
            and data.get("scenario") == "retry_after_lost_ack"
            and type(data.get("expected_delivery_count")) is int
            and type(data.get("actual_delivery_count")) is int
            and data["expected_delivery_count"] >= 0
            and data["actual_delivery_count"] >= 0
            and data["actual_delivery_count"] > data["expected_delivery_count"]
            and data.get("status") == "failed"
        )

    def counterevidence(row):
        header = "## v" + version + "\n"
        if header not in row["text"]:
            return False
        current = row["text"].split(header, 1)[1].split("\n## ", 1)[0]
        return "Retry scheduling: enabled" in current

    checks = {
        "implementation": implementation,
        "reproduction": reproduction,
        "counterevidence": counterevidence,
    }

    def verify(ctx, state):
        records = state["evidence"]["records"]
        return all(
            any(row["label"] == label and check(row) for row in records)
            for label, check in checks.items()
        )

    task = EvidenceTask(
        [pack],
        store=store,
        labels=list(checks),
        output=inputs["output"],
        verify=verify,
        record_checks=checks,
    )
    original_observe = task._observe

    def observe(ctx):
        return {
            **original_observe(ctx),
            "known_repository": {
                "manifest_source": "workspace:package.json",
                "package_version": version,
                "entry": entry,
                "entry_sha256": entry_hash,
                "scope": "program-read manifest and entry identity; recorded-run and release evidence remain undiscovered",
            },
        }

    task._observe = observe
    return task
