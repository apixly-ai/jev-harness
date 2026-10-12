"""Exact-source offline delegation lifecycle A/B; scripted IDs, no semantic inference."""

import argparse
import copy
import hashlib
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _private_files import secure_fs as _secure_fs

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "79d383dcf9ffedc535dc5182bfe5a17147f7e950"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "lazy_artifact_receipt": {"group": "handoff_fix"},
    "contextual_observation": {"group": "context_fix"},
    "lazy_joint_admission": {"group": "admission_fix"},
    "completion_contract": {"group": "completion_metadata"},
    "plain_staged_compatibility": {"group": "compatibility"},
    "review_unknown_usage": {"group": "compatibility", "unknown_scripted_usage": True},
}
GOAL = "Complete the registered synthetic evidence task"
FACTS = {"scope": "synthetic", "constraint": "registered operations only"}
MESSAGES = [{"role": "user", "content": "Use the supplied completion contract."}]
SOURCE_TEXT = "Cause: captured synthetic fact.\nProof: recorded synthetic observation."


def source_hashes(source):
    package = Path(source) / "apixly_jev_harness"
    return {
        "src/apixly_jev_harness/" + file.relative_to(package).as_posix(): hashlib.sha256(
            file.read_bytes()
        ).hexdigest()
        for file in sorted(package.rglob("*"))
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc"
    }


def snapshot(ref, destination):
    commit = subprocess.check_output(
        ["git", "rev-parse", ref + "^{commit}"], cwd=ROOT, text=True
    ).strip()
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit, "src/apixly_jev_harness"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid_package_snapshot_path")
        target = Path(destination) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", commit + ":" + name], cwd=ROOT))
    return commit


def copy_candidate(destination):
    source = ROOT / "src/apixly_jev_harness"
    target = Path(destination) / "src/apixly_jev_harness"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return Path(destination) / "src"


def _public(packet):
    if isinstance(packet, dict):
        return {
            key: (
                "<private-journal>"
                if key == "archive"
                else "<task-artifact>"
                if key == "path"
                else _public(value)
            )
            for key, value in packet.items()
            if key not in ("elapsed_seconds", "remaining_seconds")
        }
    if isinstance(packet, list):
        return [_public(value) for value in packet]
    return packet


def _write(path, value):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    fd = _secure_fs.open_private_file(path, "x")
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def trial(name, source_dir):
    import httpx

    from apixly_jev_harness import (
        EvidenceStore,
        EvidenceTask,
        Task,
        TaskScript,
        __version__,
    )
    from apixly_jev_harness import __file__ as runtime_file
    from apixly_jev_harness.engine import Engine
    from apixly_jev_harness.toolkit import ToolkitSession

    counts = {
        key: 0
        for key in (
            "factory_calls",
            "task_constructs",
            "observe_callbacks",
            "verify_callbacks",
            "candidate_callbacks",
            "execute_callbacks",
            "effects",
            "artifact_writes",
            "native_inference_attempts",
            "real_network_attempts",
        )
    }
    requests = []
    call_plan = []
    observed = None
    terminal = None
    completion_before = completion_after = None
    forwarded = []
    external = {"done": False}

    def native_forbidden(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("native_inference_forbidden")

    def network_forbidden(*args, **kwargs):
        counts["real_network_attempts"] += 1
        raise AssertionError("real_network_forbidden")

    class Client:
        stats = {"requests": 0, "clients_created": 0, "client_reuses": 0}

        def __init__(self, **kwargs):
            self.stats = dict(self.stats)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class CountingTask(Task):
        def observe(self, ctx):
            counts["observe_callbacks"] += 1
            return super().observe(ctx)

        def verify(self, ctx, state):
            counts["verify_callbacks"] += 1
            return super().verify(ctx, state)

        def candidates(self, ctx, state):
            counts["candidate_callbacks"] += 1
            return super().candidates(ctx, state)

        def execute(self, ctx, action):
            counts["execute_callbacks"] += 1
            return super().execute(ctx, action)

    class CountingEvidenceTask(EvidenceTask):
        def observe(self, ctx):
            counts["observe_callbacks"] += 1
            return super().observe(ctx)

        def verify(self, ctx, state):
            counts["verify_callbacks"] += 1
            return super().verify(ctx, state)

        def candidates(self, ctx, state):
            counts["candidate_callbacks"] += 1
            return super().candidates(ctx, state)

        def execute(self, ctx, action):
            counts["execute_callbacks"] += 1
            counts["effects"] += 1
            if action.params["tool"] == "save_report":
                counts["artifact_writes"] += 1
            return super().execute(ctx, action)

    def decide(self, records, *, goal, context=None, analysis_spec=None):
        index = len(requests)
        requests.append(
            {
                "stage": context.get("decision_stage"),
                "context_bytes": len(
                    json.dumps(context, ensure_ascii=False, sort_keys=True).encode()
                ),
                "selection_input_bytes": len(
                    json.dumps(
                        {"records": records, "goal": goal, "context": context},
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode()
                ),
            }
        )
        unresolved = name == "review_unknown_usage" and index == 1
        wanted = call_plan[min(index, len(call_plan) - 1)]
        selected = next(
            row["id"]
            for row in records
            if row["id"] == wanted or row["id"].startswith(wanted + ":")
        )
        return {
            "ok": True,
            "complete": not unresolved,
            "selected_ids": [] if unresolved else [selected],
            "review_ids": [selected] if unresolved else [],
            "telemetry": {
                "requests": 1,
                "usage_complete": not unresolved,
                "usage": None if unresolved else {"input_tokens": 7, "output_tokens": 2},
                "models": {},
                "unknown_usage_attempts": int(unresolved),
                "scope": "scripted_lifecycle_selector_not_model",
            },
        }

    with tempfile.TemporaryDirectory(prefix="jev-delegation-lifecycle-") as directory:
        output, archive = Path(directory) / "artifact.json", Path(directory) / "journal.jsonl"

        def evidence_factory(inputs):
            counts["factory_calls"] += 1
            counts["task_constructs"] += 1
            store = EvidenceStore()
            store.put(SOURCE_TEXT, "fixture:source")
            labels = ["proof"] if name == "lazy_artifact_receipt" else ["cause", "proof"]

            def verify(ctx, state):
                return all(
                    any(row["label"] == label for row in state["evidence"]["records"])
                    for label in labels
                )

            return CountingEvidenceTask(
                [], store=store, labels=labels, output=inputs["output"], verify=verify
            )

        def ordinary_factory(inputs):
            counts["factory_calls"] += 1
            counts["task_constructs"] += 1
            if name == "contextual_observation":
                task = CountingTask(
                    observe=lambda c: {"count": len(c.results)}, verify=lambda c, s: s["count"] == 1
                )
            else:
                task = CountingTask(
                    observe=lambda c: dict(external),
                    verify=lambda c, s: s["done"] if name == "lazy_joint_admission" else False,
                    strategy="joint" if name == "lazy_joint_admission" else "staged",
                )

            @task.tool(
                "Execute a registered synthetic read/effect",
                name="inspect",
                result_context=lambda result: result,
            )
            def inspect():
                counts["effects"] += 1
                external["done"] = True
                if name == "lazy_joint_admission":
                    _write(output, {"effect": 1})
                    counts["artifact_writes"] += 1
                return {"observed": True}

            return task

        def staged_task():
            counts["task_constructs"] += 1
            expected = {"goal": GOAL, "facts": FACTS, "messages": MESSAGES}

            def verify(ctx, state):
                return (
                    output.is_file() and json.loads(output.read_text(encoding="utf-8")) == expected
                )

            task = CountingTask(observe=lambda c: dict(external), verify=verify)

            @task.tool(
                "Save synthetic context evidence",
                name="inspect",
                result_context=lambda result: result,
            )
            def inspect():
                counts["effects"] += 1
                value = {
                    "goal": context_seen.goal,
                    "facts": context_seen.facts,
                    "messages": context_seen.messages,
                }
                forwarded.append(copy.deepcopy(value))
                _write(output, value)
                counts["artifact_writes"] += 1
                external["done"] = True
                return {"saved": True}

            def observe(ctx):
                nonlocal context_seen
                context_seen = ctx
                return dict(external)

            task._observe = observe
            task.artifact_receipt = lambda: {
                "path": str(output),
                "exists": output.is_file(),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest()
                if output.is_file()
                else None,
            }
            return task

        context_seen = None
        with (
            patch("apixly_jev_harness.backend.Client", Client),
            patch("apixly_jev_harness.backend.native_run", native_forbidden),
            patch("apixly_jev_harness.backend.provider_evaluate", native_forbidden),
            patch.object(Engine, "decide", decide),
            patch.object(httpx.HTTPTransport, "handle_request", network_forbidden),
            patch.object(urllib.request, "urlopen", network_forbidden),
            patch.object(socket, "create_connection", network_forbidden),
        ):
            started = time.perf_counter()
            if name in ("lazy_artifact_receipt", "completion_contract"):
                workflow = TaskScript(evidence_factory)
                call_plan = ["read_evidence", "record_evidence", "save_report"]
            elif name == "plain_staged_compatibility":
                workflow = staged_task()
                call_plan = ["inspect"]
            else:
                workflow = TaskScript(ordinary_factory)
                call_plan = ["inspect", "inspect"]
            session = ToolkitSession(
                workflow,
                goal=GOAL,
                inputs={"output": str(output)},
                context=FACTS,
                max_steps=6,
                timeout_seconds=60,
                archive=str(archive),
            )
            session.ctx.messages = copy.deepcopy(MESSAGES)
            if name == "completion_contract":
                before = session.observe()
                completion_before = before["observation"].get("completion")
                passage = before["tools"][0]["parameters"]["passage"]["choices"][0]["id"]
                session.operate(
                    "read_evidence", {"passage": passage}, state_ref=before["state_ref"]
                )
                current = session.observe()
                child = session.resolve(
                    "record_evidence", {"label": "cause"}, state_ref=current["state_ref"]
                )["parameters"]["passage"]["choices"][0]["id"]
                session.operate(
                    "record_evidence",
                    {"label": "cause", "passage": child},
                    state_ref=current["state_ref"],
                )
                current = session.observe()
                session.operate("save_report", {}, state_ref=current["state_ref"])
                observed = session.observe()
                completion_after = observed["observation"].get("completion")
                terminal = {
                    "status": "partial_saved_report",
                    "complete": False,
                    "steps": session.steps,
                    "telemetry": {
                        "requests": 0,
                        "usage_complete": True,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                        "calls": [],
                    },
                }
            else:
                terminal = session.delegate()
                if name != "lazy_joint_admission":
                    observed = session.observe()
            receipt = (
                terminal.get("artifact")
                if name != "completion_contract"
                else observed["delegation"].get("artifact")
            )
            artifact_valid = None
            artifact_hash = None
            if output.is_file():
                body = output.read_bytes()
                artifact_hash = hashlib.sha256(body).hexdigest()
                saved = json.loads(body)
                if name in ("lazy_artifact_receipt", "completion_contract"):
                    rows = saved["records"]
                    artifact_valid = bool(rows) and all(
                        row["source"] == "fixture:source"
                        and row["sha256"] == hashlib.sha256(SOURCE_TEXT.encode()).hexdigest()
                        and row["text"] == SOURCE_TEXT[row["offset"] : row["end"]]
                        for row in rows
                    )
                elif name == "plain_staged_compatibility":
                    artifact_valid = saved == {"goal": GOAL, "facts": FACTS, "messages": MESSAGES}
                elif name == "lazy_joint_admission":
                    artifact_valid = saved == {"effect": 1}
                if receipt is not None:
                    artifact_valid = (
                        artifact_valid
                        and receipt.get("path") == str(output)
                        and receipt.get("sha256") == artifact_hash
                        and receipt.get("exists") is True
                    )
            elapsed = time.perf_counter() - started
            journal_events = (
                [
                    json.loads(line)["event"]
                    for line in archive.read_text(encoding="utf-8").splitlines()
                ]
                if archive.exists()
                else []
            )

    telemetry = terminal["telemetry"]
    calls = telemetry.get("calls", [])
    known = {
        key: sum(
            call.get("usage", {}).get(key, 0)
            for call in calls
            if isinstance(call.get("usage"), dict)
        )
        for key in ("input_tokens", "output_tokens")
    }
    result = {
        "status": terminal["status"],
        "complete": terminal["complete"],
        "steps": terminal["steps"],
        "artifact_returned": receipt is not None,
        "artifact_independently_verified": artifact_valid,
        "artifact_sha256": artifact_hash,
        "artifact_matches_records": receipt.get("matches_records") if receipt else None,
        "followup_results": observed.get("observation", {}).get("count") if observed else None,
        "followup_complete": observed["complete"] if observed else None,
        "followup_context_results": len(session.ctx.results),
        "followup_context_step": session.ctx.step,
        "forwarded_context_correct": bool(forwarded)
        and forwarded == [{"goal": GOAL, "facts": FACTS, "messages": MESSAGES}],
        "completion_before": completion_before,
        "completion_after": completion_after,
        "scripted_decisions": len(requests),
        "scripted_requests": telemetry["requests"],
        "scripted_usage_complete": telemetry["usage_complete"],
        "reported_scripted_usage": telemetry["usage"],
        "known_scripted_usage": known,
        "unknown_scripted_usage_calls": sum(call.get("usage_complete") is False for call in calls),
        "request_sizes": requests,
        "journal_intents": journal_events.count("intent"),
        **counts,
    }
    expectations = {
        "lazy_artifact_receipt": {
            "status": "done",
            "artifact_returned": True,
            "artifact_independently_verified": True,
            "factory_calls": 1,
            "artifact_writes": 1,
            "effects": 3,
        },
        "contextual_observation": {
            "status": "done",
            "followup_results": 1,
            "followup_complete": True,
            "followup_context_step": 1,
            "effects": 1,
        },
        "lazy_joint_admission": {
            "status": "failed",
            "effects": 0,
            "scripted_decisions": 0,
            "factory_calls": 1,
            "artifact_writes": 0,
        },
        "completion_contract": {
            "status": "partial_saved_report",
            "completion_before": {
                "required_labels": ["cause", "proof"],
                "missing_labels": ["cause", "proof"],
                "report_matches_records": False,
                "independent_check_required": True,
            },
            "completion_after": {
                "required_labels": ["cause", "proof"],
                "missing_labels": ["proof"],
                "report_matches_records": True,
                "independent_check_required": True,
            },
            "followup_complete": False,
            "artifact_independently_verified": True,
        },
        "plain_staged_compatibility": {
            "status": "done",
            "forwarded_context_correct": True,
            "artifact_returned": True,
            "artifact_independently_verified": True,
            "effects": 1,
        },
        "review_unknown_usage": {
            "status": "needs_review",
            "effects": 1,
            "scripted_requests": 2,
            "scripted_usage_complete": False,
            "reported_scripted_usage": None,
            "known_scripted_usage": {"input_tokens": 7, "output_tokens": 2},
            "unknown_scripted_usage_calls": 1,
        },
    }
    expected = expectations[name]
    correct = (
        all(result[key] == value for key, value in expected.items())
        and counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
    )
    returned = {"terminal": _public(terminal), "followup": _public(observed)}
    return {
        "case": name,
        "fixture": CASES[name],
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "expected": expected,
        "result": result,
        "correct": correct,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(
            json.dumps(returned, ensure_ascii=False, sort_keys=True).encode()
        ),
        "shared_context_bytes": sum(row["context_bytes"] for row in requests),
        "selection_input_bytes": sum(row["selection_input_bytes"] for row in requests),
        "actual_model_usage": copy.deepcopy(ZERO_USAGE)
        if not counts["native_inference_attempts"] and not counts["real_network_attempts"]
        else {
            "requests": None,
            "models": {},
            "input_tokens": None,
            "output_tokens": None,
            "usage_complete": False,
        },
    }


def worker(case, source_dir):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TYPESAFE_", "JEV_TEXT_", "CAMOFOX_"))
    }
    output = subprocess.check_output(
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "--worker",
            case,
            "--source-dir",
            str(source_dir),
        ],
        env=env,
        text=True,
        timeout=60,
    )
    return json.loads(output)


def summarize(rows):
    summary = {}
    for arm in ("baseline", "candidate"):
        selected = [row for row in rows if row["arm"] == arm]
        summary[arm] = {
            "runs": len(selected),
            "correct": sum(row["correct"] for row in selected),
            "groups": {
                group: {
                    "runs": sum(row["fixture"]["group"] == group for row in selected),
                    "correct": sum(
                        row["fixture"]["group"] == group and row["correct"] for row in selected
                    ),
                }
                for group in sorted({value["group"] for value in CASES.values()})
            },
            "effects": sum(row["result"]["effects"] for row in selected),
            "artifact_writes": sum(row["result"]["artifact_writes"] for row in selected),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in selected),
            "unknown_scripted_usage_rows": sum(
                row["result"]["scripted_usage_complete"] is False for row in selected
            ),
            "observe_callbacks": sum(row["result"]["observe_callbacks"] for row in selected),
            "verify_callbacks": sum(row["result"]["verify_callbacks"] for row in selected),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in selected),
            "shared_context_bytes": sum(row["shared_context_bytes"] for row in selected),
            "selection_input_bytes": sum(row["selection_input_bytes"] for row in selected),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in selected
            ),
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in selected
            ),
            "real_network_attempts": sum(
                row["result"]["real_network_attempts"] for row in selected
            ),
            "actual_model_usage": (
                copy.deepcopy(ZERO_USAGE)
                if not any(
                    row["result"]["native_inference_attempts"]
                    or row["result"]["real_network_attempts"]
                    for row in selected
                )
                else {
                    "requests": None,
                    "models": {},
                    "input_tokens": None,
                    "output_tokens": None,
                    "usage_complete": False,
                }
            ),
        }
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", choices=list(CASES), help=argparse.SUPPRESS)
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        sys.path.insert(0, args.source_dir)
        print(json.dumps(trial(args.worker, args.source_dir), ensure_ascii=False))
        return 0
    if not args.output:
        parser.error("--output is required")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        output.open("x", encoding="utf-8", newline="\n") as stream,
        tempfile.TemporaryDirectory(prefix="jev-source-pair-") as directory,
    ):
        root = Path(directory)
        baseline = snapshot(args.baseline_ref, root / "baseline")
        candidate_hashes = source_hashes(ROOT / "src")
        sources = {
            "baseline": root / "baseline/src",
            "candidate": copy_candidate(root / "candidate"),
        }
        hashes = {arm: source_hashes(source) for arm, source in sources.items()}
        runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if hashes["candidate"] != candidate_hashes:
            raise RuntimeError("candidate_snapshot_mismatch")
        rows = []
        for case in CASES:
            for repeat in range(3):
                for arm in (
                    ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                ):
                    row = worker(case, sources[arm])
                    if (
                        row.pop("source_sha256") != hashes[arm]
                        or not row["runtime_loaded_from_requested_source"]
                    ):
                        raise RuntimeError("runtime_source_changed_or_misloaded")
                    row.update(arm=arm, repeat=repeat + 1)
                    rows.append(row)
        if (
            any(source_hashes(source) != hashes[arm] for arm, source in sources.items())
            or source_hashes(ROOT / "src") != candidate_hashes
            or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != runner_hash
        ):
            raise RuntimeError("benchmark_source_changed_during_run")
        parity_keys = (
            "status",
            "complete",
            "effects",
            "artifact_writes",
            "artifact_returned",
            "artifact_independently_verified",
            "forwarded_context_correct",
            "scripted_decisions",
            "scripted_requests",
            "scripted_usage_complete",
            "reported_scripted_usage",
            "known_scripted_usage",
            "unknown_scripted_usage_calls",
        )
        pairs = {(row["case"], row["repeat"], row["arm"]): row for row in rows}
        parity = all(
            pairs[(case, repeat, "baseline")]["result"][key]
            == pairs[(case, repeat, "candidate")]["result"][key]
            for case, info in CASES.items()
            if info["group"] == "compatibility"
            for repeat in (1, 2, 3)
            for key in parity_keys
        )
        report = {
            "mode": "offline-scripted-delegation-lifecycle",
            "baseline_commit": baseline,
            "candidate": "working-tree source snapshot at invocation",
            "baseline_source_sha256": hashes["baseline"],
            "candidate_source_sha256": hashes["candidate"],
            "runner_sha256": runner_hash,
            "python_version": sys.version.split()[0],
            "cases": CASES,
            "compatibility_parity": parity,
            "compatibility_parity_fields": parity_keys,
            "scope": "Six fixed lifecycle fixtures, three paired repeats with alternating arm order. Real Engine/Task/ToolkitSession callbacks, registered operations, independent artifact byte/source checks and journal flush/fsync are exercised. Engine.decide returns scripted IDs, not semantic inference. Baseline whole package is materialized with git show; both packages run in isolated processes. Source hashes are not imported-bytecode attestations. No browser/desktop/model operations occur; real network and native/provider inference guards are installed.",
            "timing": "Real perf_counter covers task/factory/session construction, callback dispatch, scripted decisions, registered local operations, artifact fd writes/fsync, journal flush/fsync, verification and followup observation. It excludes subprocess/interpreter imports, source snapshot setup, patch installation and terminal metric/source-hash analysis.",
            "context_metrics": "Shared context and selection-input bytes are sums over scripted decision callbacks. Returned bytes cover canonicalized terminal plus followup packets, with local paths replaced and timing fields omitted. Byte counts are not tokens or billable cost.",
            "negative_results": "New completion metadata and artifact forwarding add returned/context bytes and local checks; those costs are reported rather than claimed as a speed or quality benefit. Earlier lazy-joint rejection changes status and skips one deliberately scripted effect/decision. A baseline missing receipt is a handoff failure, not failed artifact creation. Context transfer improves lifecycle observation, not a direct/Jev route switch or durable resume. Timings are local small synthetic samples; no semantic correctness, model speed, autonomous adoption, token savings, tariff conversion or invoice advantage is established. Unknown scripted usage remains null and distinct from actual zero model calls.",
            "reproduction": "python benchmarks/delegation_lifecycle.py --output local-results/delegation-lifecycle-ab.json",
            "cost_conversion": "Actual model usage is zero only when forbidden native/network guards remain zero. Scripted known and unknown usage is retained separately; no current tariff or financial conversion is assumed.",
            "summary": summarize(rows),
            "rows": rows,
        }
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"compatibility_parity": parity, "summary": report["summary"]}))
    return (
        0
        if parity
        and all(row["correct"] for row in rows if row["arm"] == "candidate")
        and not any(
            row["result"]["native_inference_attempts"] or row["result"]["real_network_attempts"]
            for row in rows
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
