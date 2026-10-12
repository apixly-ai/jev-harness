"""Offline policy/projection controls on the same generic runtime and source fixtures."""

import argparse
import copy
import hashlib
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from _private_files import secure_fs as _secure_fs
from jev_context.provider import Client

from apixly_jev_harness import AgentLoop, Option, Parameter, Task, __version__
from apixly_jev_harness.context import ContextPolicy
from apixly_jev_harness.engine import HOSTED_DEFAULT
from apixly_jev_harness.evidence import EvidenceStore
from apixly_jev_harness.toolkit import EvidenceTask, ToolkitSession
from apixly_jev_harness.web_tools import WebTools, _document

ROOT = Path(__file__).resolve().parents[1]
TAIL = "SYNTHETIC_TAIL_FACT"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
UNKNOWN_USAGE = {
    "requests": None,
    "models": {},
    "input_tokens": None,
    "output_tokens": None,
    "usage_complete": False,
}
# Responses are fixed before execution. The transport never sees the expectation table.
# Current-runtime save indexes reflect that already recorded windows are no longer offered.
CASES = {
    "ambiguous_legal_tool": [("c0", 0.39), ("c0", 0.99), ("c1", 0.99), ("c1", 0.99)],
    "exploratory_target": [("c0", 0.99), ("c0", 0.39)],
    "matched_target_low": [("c0", 0.99), ("c0", 0.39)],
    "matched_target_high": [("c0", 0.99), ("c0", 0.60)],
    "explicit_review_tool": [("REVIEW", 0.99)],
    "explicit_review_parameter": [("c0", 0.99), ("REVIEW", 0.99)],
    "child_match_low": [("c0", 0.99), ("c1", 0.99), ("c0", 0.39)],
    "child_after_label": [("c0", 0.99), ("c1", 0.99), ("c0", 0.60)],
    "unknown_reference": [],
    "foreign_link": [],
    "tail_read": [("c0", 0.99), ("c1", 0.99), ("c1", 0.99)],
    "twelve_records": [("c1", 0.99)],
    "unknown_http_usage": [None],
    "direct_then_delegate": [],
    "delegate_then_direct": [("c0", 0.99), ("c0", 0.99)],
}


def _control(task):
    task.tool_selection_policy = copy.deepcopy(HOSTED_DEFAULT)
    for tool in task._tools.values():
        tool["parameters"] = {
            name: Parameter(p.description, p.choices, p.depends_on, selection="match")
            for name, p in tool["parameters"].items()
        }


def _compact(value):
    if isinstance(value, dict):
        return {
            key: _compact(item) for key, item in value.items() if key not in ("archive", "path")
        }
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _expectation(case, arm):
    if case in ("unknown_reference", "foreign_link"):
        return "rejected", 0
    if case in ("direct_then_delegate", "delegate_then_direct"):
        return "rejected", 1
    if case in (
        "matched_target_low",
        "explicit_review_tool",
        "explicit_review_parameter",
        "child_match_low",
        "unknown_http_usage",
    ):
        return "needs_review", 0
    if case == "ambiguous_legal_tool":
        return ("needs_review", 0) if arm == "baseline" else ("done", 4)
    if case == "exploratory_target":
        return ("needs_review", 0) if arm == "baseline" else ("done", 1)
    if case == "twelve_records":
        return ("needs_review", 0) if arm == "baseline" else ("done", 1)
    return "done", 3 if case == "tail_read" else 1


def trial(case, arm):
    if case not in CASES or arm not in ("baseline", "candidate"):
        raise ValueError("unknown_protocol_fixture")
    script = copy.deepcopy(CASES[case])
    request_protocol, policies, request_sizes = [], [], []
    counts = {"mock": 0, "real": 0}
    effects, provider_labels, verifier_counts = [], [], []
    tail_visible, observation_size = False, None
    artifact_count, before_switch, after_switch = None, None, None
    original_decide = AgentLoop.decide

    def decide(self, records, **kwargs):
        policies.append(copy.deepcopy(kwargs["analysis_spec"]["uncertainty"]))
        return original_decide(self, records, **kwargs)

    def transport(request):
        nonlocal tail_visible
        body = json.loads(request.content)
        shared = body["state"]["context"]
        question = body["questions"]["target"]
        instructions = question["instructions"]
        request_protocol.append(
            {
                "stage": shared["decision_stage"],
                "parameter": shared.get("parameter"),
                "bound_reference_ids": {
                    key: value["id"] for key, value in shared.get("bound_references", {}).items()
                },
                "exploration_criterion": "Destination content may be unknown" in instructions,
                "whole_goal_removed_from_parameter_task": shared.get("parameter_selection_kind")
                == "explore"
                and "Entire goal:" not in body["state"]["task"],
            }
        )
        request_sizes.append(
            {
                "input_bytes": len(request.content),
                "context_bytes": len(json.dumps(shared, ensure_ascii=False).encode()),
            }
        )
        if case == "tail_read" and shared.get("step") == 1:
            tail_visible = tail_visible or TAIL in json.dumps(shared, ensure_ascii=False)
        index = counts["mock"]
        counts["mock"] += 1
        if index >= len(script):
            raise AssertionError("fixed_response_sequence_exhausted")
        answer = script[index]
        if answer is None:
            return httpx.Response(413, text="Synthetic request refused; usage unknown")
        choice, probability = answer
        options = list(question["criteria"])
        if choice not in options:
            raise AssertionError("frozen_choice_not_currently_offered")
        probabilities = {key: 0.0 for key in options}
        probabilities[choice] = probability
        others = [key for key in options if key != choice]
        if probability == 0.39:
            for key, value in zip(others[:3], (0.35, 0.22, 0.04)):
                probabilities[key] = value
        else:
            probabilities[others[0]] = 1.0 - probability
        return httpx.Response(
            200,
            json={
                "model": "jev-synthetic-protocol",
                "usage": {"input_tokens": 7, "output_tokens": 1},
                "answers": {
                    "target": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": probability,
                        "probabilities": probabilities,
                    }
                },
            },
        )

    def forbidden(*args, **kwargs):
        counts["real"] += 1
        raise AssertionError("Protocol benchmark forbids real HTTP")

    class LegacyHistory(ContextPolicy):
        def build(self, ctx, observation):
            result = super().build(ctx, observation)
            for entry in result["history"]:
                admitted = entry.get("result")
                if isinstance(admitted, dict) and isinstance(admitted.get("text"), str):
                    admitted["text"] = admitted["text"][:240]
            return result

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="jev-toolkit-protocol-") as directory:
        root = Path(directory)
        artifact, archive = root / "evidence.json", root / "run.jsonl"
        client = Client(
            api_key="synthetic-key",
            transport=httpx.MockTransport(transport),
            sleep=lambda _: None,
        )
        policy = None
        if case in ("ambiguous_legal_tool", "tail_read", "twelve_records", "foreign_link"):
            store = EvidenceStore()
            packs = []
            if case == "ambiguous_legal_tool":

                class Discovery:
                    name = "discovery"

                    def observe(self):
                        return {"collected": bool(effects)}

                    def install(self, task):
                        for index in range(3):

                            def make(index=index):
                                def inspect():
                                    effects.append("inspect")
                                    ref = store.put(
                                        "A captured permitted source fact.", f"source:{index}"
                                    )
                                    return store.describe(ref)

                                return inspect

                            task.tool(
                                "Inspect a permitted unknown source to gather evidence",
                                name=f"inspect:{index}",
                                available=lambda c, s: not effects,
                                result_context=lambda value: value,
                            )(make())

                packs = [Discovery()]
            if case == "foreign_link":

                class Source:
                    def capture(self):
                        return _document(
                            {
                                "url": "https://fixture.invalid/",
                                "title": "Entry",
                                "text": "Entry source",
                                "links": [{"label": "Outside", "url": "https://outside.invalid/"}],
                            },
                            {"https://fixture.invalid"},
                            {"kind": "literal_fixture"},
                        )

                    def follow(self, reference, snapshot):
                        effects.append("foreign_follow")
                        raise AssertionError("Foreign target must not execute")

                packs = [WebTools(Source(), store=store)]
            if case == "tail_read":
                store.put("x" * 700 + TAIL, "source:tail")

            def verify(ctx, seen):
                rows = seen["evidence"]["records"]
                verifier_counts.append(len(rows))
                if case == "twelve_records":
                    return len(rows) == 12 and all(len(row["text"]) == 1200 for row in rows)
                return len(rows) == 1 and (case != "tail_read" or TAIL in rows[0]["text"])

            task = EvidenceTask(packs, store=store, labels=["fact"], output=artifact, verify=verify)
            if case == "twelve_records":
                for index in range(12):
                    ref = store.put("x" * 1200, f"source:{index}")
                    task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "fact")
            original_execute = task.execute

            def execute(ctx, action):
                # Count actual registered operations, including reads and saved artifacts.
                before = len(effects)
                result = original_execute(ctx, action)
                if len(effects) == before:
                    effects.append(action.id)
                return result

            task.execute = execute
            if arm == "baseline" and case in ("tail_read", "twelve_records"):
                original_state = task._observe

                def legacy_state(ctx):
                    state = original_state(ctx)
                    state["evidence"].pop("last_read", None)
                    state["evidence"]["sources"] = store.references()
                    state["evidence"]["records"] = copy.deepcopy(task.records)
                    return state

                task._observe = legacy_state
                policy = LegacyHistory()
            observation_size = len(json.dumps(task.observe(None), ensure_ascii=False))
        else:
            state = {"done": False}

            def verify(ctx, seen):
                return artifact.is_file() and seen["done"]

            task = Task(observe=lambda c: dict(state), verify=verify)
            if case.startswith("child_"):

                def children(ctx, seen, bound):
                    provider_labels.append(bound["label"])
                    return [
                        Option(
                            f"{bound['label']}:{index}",
                            f"Source for category {bound['label']}",
                            index,
                        )
                        for index in range(3)
                    ]

                @task.tool(
                    "Record a source under a requested category",
                    parameters={
                        "label": Parameter(
                            "Choose the requested category",
                            [Option(x, x, x) for x in ("cause", "proof")],
                            selection="explore",
                        ),
                        "passage": Parameter(
                            "Source supporting the selected category",
                            children,
                            depends_on=("label",),
                        ),
                    },
                    result_context=lambda value: value,
                )
                def record(label, passage):
                    effects.append("record")
                    artifact.write_text(
                        json.dumps({"label": label, "passage": passage}),
                        newline="\n",
                        encoding="utf-8",
                    )
                    state["done"] = True
                    return {"saved": True}
            else:
                selection = (
                    "explore"
                    if case in ("exploratory_target", "explicit_review_parameter")
                    else "match"
                )

                @task.tool(
                    "Inspect one permitted source",
                    parameters={
                        "target": Parameter(
                            "A permitted branch whose contents will be discovered",
                            [
                                Option(x, f"Permitted source {x}", x)
                                for x in ("alpha", "beta", "gamma")
                            ],
                            selection=selection,
                        )
                    },
                    result_context=lambda value: value,
                )
                def inspect(target):
                    effects.append(target)
                    artifact.write_text(
                        json.dumps({"source": target}), encoding="utf-8", newline="\n"
                    )
                    state["done"] = True
                    return {"saved": True}

        if arm == "baseline":
            _control(task)
        before_switch = after_switch = None
        with (
            patch("apixly_jev_harness.backend.Client", lambda **kwargs: client),
            patch.object(AgentLoop, "decide", decide),
            patch("httpx.HTTPTransport.handle_request", forbidden),
        ):
            if case in (
                "unknown_reference",
                "foreign_link",
                "direct_then_delegate",
                "delegate_then_direct",
            ):
                session = ToolkitSession(
                    task, goal="Investigate permitted sources", archive=archive
                )
                session.observe()
                try:
                    if case == "delegate_then_direct":
                        session.delegate()
                        before_switch = len(effects)
                    elif case == "direct_then_delegate":
                        session.operate("inspect", {"target": "alpha"})
                        before_switch = len(effects)
                    if case == "foreign_link":
                        session.operate("web.open_link", {"link": "https://outside.invalid/"})
                    elif case == "direct_then_delegate":
                        session.delegate()
                    else:
                        session.operate(
                            "inspect",
                            {"target": "invented" if case == "unknown_reference" else "alpha"},
                        )
                    packet = {"status": "unexpected_acceptance", "complete": False}
                except ValueError:
                    packet = {"status": "rejected", "complete": False}
                after_switch = len(effects)
            else:
                packet = AgentLoop().run(
                    task,
                    goal="Inspect permitted sources and save independently checked evidence",
                    max_steps=8,
                    context_policy=policy,
                    archive=archive,
                )
            if artifact.exists() and isinstance(task, EvidenceTask):
                artifact_count = len(json.loads(artifact.read_text(encoding="utf-8"))["records"])
        if not client.closed:
            client.close()
        telemetry = packet.get("telemetry", {})
        if archive.exists() and not telemetry:
            entries = [
                json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()
            ]
            telemetry = next(
                (
                    entry["result"]["telemetry"]
                    for entry in reversed(entries)
                    if entry["event"] == "terminal"
                ),
                {},
            )
        returned_bytes = len(json.dumps(_compact(packet), ensure_ascii=False).encode())
        elapsed = time.perf_counter() - started
    expected_status, expected_effects = _expectation(case, arm)
    met = packet["status"] == expected_status and len(effects) == expected_effects
    if case == "tail_read":
        met = met and tail_visible == (arm == "candidate")
    if case == "twelve_records" and arm == "candidate":
        met = met and verifier_counts == [12] and artifact_count == 12 and observation_size < 15000
    return {
        "case": case,
        "arm": arm,
        "runtime_version": __version__,
        "expected_status": expected_status,
        "expected_effects": expected_effects,
        "expected_outcome_met": met and counts["real"] == 0,
        "status": packet["status"],
        "reason": packet.get("reason"),
        "effects": len(effects),
        "effects_before_rejected_switch": before_switch,
        "effects_after_rejected_switch": after_switch,
        "mock_sdk_attempts": counts["mock"],
        "real_network_attempts": counts["real"],
        "scripted_usage_complete": telemetry.get("usage_complete", True),
        "scripted_usage": telemetry.get("usage", {"input_tokens": 0, "output_tokens": 0}),
        "actual_model_usage": copy.deepcopy(UNKNOWN_USAGE if counts["real"] else ZERO_USAGE),
        "selection_policies": policies,
        "request_protocol": request_protocol,
        "provider_bound_labels": provider_labels,
        "tail_visible_after_read": tail_visible,
        "observation_characters": observation_size,
        "verifier_record_counts": verifier_counts,
        "artifact_record_count": artifact_count,
        "request_bytes": sum(row["input_bytes"] for row in request_sizes),
        "context_bytes": sum(row["context_bytes"] for row in request_sizes),
        "returned_context_bytes": returned_bytes,
        "whole_operation_seconds": elapsed,
    }


def _source_hashes():
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
    }


_IMPORTED_SOURCE_HASHES = _source_hashes()


def run_benchmark(repeats=3):
    if type(repeats) is not int or repeats < 1:
        raise ValueError("positive_repeat_count_required")
    hashes = _source_hashes()
    if hashes != _IMPORTED_SOURCE_HASHES:
        raise RuntimeError("runtime_source_changed_since_import")
    runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = []
    for index, case in enumerate(CASES):
        for repeat in range(repeats):
            arms = (
                ("baseline", "candidate")
                if (index + repeat) % 2 == 0
                else ("candidate", "baseline")
            )
            for arm in arms:
                rows.append({**trial(case, arm), "repeat": repeat + 1})
    if (
        hashes != _source_hashes()
        or runner_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        raise RuntimeError("benchmark_source_changed")
    summary = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        summary[arm] = {
            "runs": len(group),
            "expected_outcomes_met": sum(row["expected_outcome_met"] for row in group),
            "statuses": {
                status: sum(row["status"] == status for row in group)
                for status in sorted({row["status"] for row in group})
            },
            "effects": sum(row["effects"] for row in group),
            "mock_sdk_attempts": sum(row["mock_sdk_attempts"] for row in group),
            "unknown_scripted_usage_rows": sum(not row["scripted_usage_complete"] for row in group),
            "request_bytes": sum(row["request_bytes"] for row in group),
            "context_bytes": sum(row["context_bytes"] for row in group),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "actual_model_usage": copy.deepcopy(
                ZERO_USAGE
                if all(row["actual_model_usage"]["usage_complete"] for row in group)
                else UNKNOWN_USAGE
            ),
        }
    return {
        "mode": "offline-policy-projection-control",
        "semantic_accuracy_measured": False,
        "baseline_scope": "Documented match-policy and legacy-projection injection on the same candidate runtime, not a published v0.1.17 source comparison. Control uses HOSTED_DEFAULT for tools and Parameter.selection=match. Only tail/12-record cases remove last_read, restore full records/sources and shorten admitted historical text to 240 characters.",
        "candidate_scope": "Explicit EvidenceTask tool policy and Parameter.selection=explore, with current reference projection. Tail visibility is measured on the first decision after reading, before recording that passage. Ordinary match parameters and explicit model REVIEW stay unchanged. Route/ref guards are compatibility controls on both arms.",
        "baseline_source_sha256": hashes,
        "candidate_source_sha256": hashes,
        "runner_sha256": runner_hash,
        "fixed_responses": CASES,
        "repeats": repeats,
        "scope": "Fixed synthetic resources and literal choice/probability sequences. The real pinned SDK runs through HTTPMock; fixtures execute registered Python/file/evidence operations. Provider/executor do not inspect expected outcomes or hidden answers. Captured protocol/size scalars are not semantic quality or browser/primary-agent acceptance.",
        "negative_results": "Additional admitted exploratory steps increase mock decisions, input/context and local work; expected outcomes include REVIEW/rejection. Unknown mock HTTP usage stays unknown. Context projection improves only these fixtures, not unlimited history. No semantic accuracy, invoice, speed or savings claim; source-reference storage is not result caching.",
        "timing_scope": "Real perf_counter includes per-trial fixture/task creation, SDK mock decisions, registered effects, artifact checks and private journal fsync; excludes module imports, source hashing and report serialization.",
        "reproduction": "Use the report source hashes with a full checkout and .[dev]; python benchmarks/toolkit_protocol.py --output local-results/toolkit-protocol-ab.json",
        "summary": summary,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    report = run_benchmark(args.repeats)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = _secure_fs.open_private_file(path, "x")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"mode": report["mode"], "summary": report["summary"]}))
    return 0 if all(row["expected_outcome_met"] for row in report["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
