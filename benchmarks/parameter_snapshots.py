"""Offline paired parameter-value snapshots against exact v0.1.14."""

import argparse
import copy
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "ad86eb02098b0a1ed0f1dc114e55ea735d97e068"
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_OPTION_VALUE"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "staged_option_dict_wait": {
        "mode": "option_dict",
        "group": "snapshot_fix",
        "mutate": "target_wait",
    },
    "staged_option_list_wait": {
        "mode": "option_list",
        "group": "snapshot_fix",
        "mutate": "target_wait",
    },
    "staged_raw_dict_wait": {"mode": "raw_dict", "group": "snapshot_fix", "mutate": "target_wait"},
    "staged_raw_list_wait": {"mode": "raw_list", "group": "snapshot_fix", "mutate": "target_wait"},
    "dependent_parent_wait": {
        "mode": "dependent",
        "group": "snapshot_fix",
        "mutate": "parent_wait",
    },
    "selected_later_option_wait": {
        "mode": "option_dict",
        "group": "snapshot_fix",
        "mutate": "target_wait",
        "select_last": True,
    },
    "private_option_unknown_usage": {
        "mode": "option_dict",
        "group": "snapshot_fix",
        "mutate": "target_wait",
        "private_value": True,
        "unknown_usage": True,
    },
    "joint_dynamic_wait": {
        "mode": "option_dict",
        "group": "compatibility",
        "strategy": "joint",
        "mutate": "tool_wait",
    },
    "singleton_dynamic": {"mode": "option_dict", "group": "compatibility", "singleton": True},
    "tool_wait_singleton_refresh": {
        "mode": "option_dict",
        "group": "compatibility",
        "singleton": True,
        "refresh": "tool_wait",
    },
    "tool_wait_multivalue_refresh": {
        "mode": "option_dict",
        "group": "compatibility",
        "refresh": "tool_wait",
    },
    "static_registration_snapshot": {
        "mode": "option_dict",
        "group": "compatibility",
        "static": True,
        "mutate": "after_registration",
    },
    "bool_value_preserved": {"mode": "bool", "group": "compatibility"},
    "numeric_value_preserved": {"mode": "numeric", "group": "compatibility"},
    "no_mutation_unknown_usage": {
        "mode": "option_dict",
        "group": "compatibility",
        "unknown_usage": True,
    },
    "earlier_choice_refreshes_later_domain": {
        "mode": "earlier_later",
        "group": "compatibility",
        "refresh": "first_wait",
    },
    "large_all_candidate_payloads": {
        "mode": "large",
        "group": "copy_cost",
        "option_count": 16,
        "payload_elements": 5000,
    },
    "unselected_copy_hook_failure": {
        "mode": "hook_failure",
        "group": "compatibility_narrowing",
        "unknown_usage": True,
    },
    "duplicate_ids_before_copy": {"mode": "duplicate", "group": "limits_compatibility"},
    "over_253_before_copy": {
        "mode": "oversize",
        "group": "limits_compatibility",
        "option_count": 254,
    },
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def trial(name, source_dir, arm):
    from apixly_jev_harness import AgentLoop, Option, Parameter, Task, __version__
    from apixly_jev_harness import __file__ as runtime_file

    config, mode = CASES[name], CASES[name]["mode"]
    requests, domain_records, provider_calls = [], [], {}
    counts = {
        "effects": 0,
        "mutations": 0,
        "copy_hook_calls": 0,
        "native_inference_attempts": 0,
        "real_network_attempts": 0,
    }
    state = {"processed_record": None, "processed_digest": None}
    current_record = {
        "id": "synthetic-preview" if config.get("refresh") else "synthetic-a",
        "payload": {"state": "before"},
    }
    if config.get("private_value"):
        current_record["private_scope"] = PRIVATE_MARKER
    current_list = [current_record["id"], {"state": "before"}]
    alternative = {"id": "synthetic-c", "payload": {"state": "other"}}

    class UncopyableDictionary(dict):
        def __deepcopy__(self, memo):
            counts["copy_hook_calls"] += 1
            raise RuntimeError(PRIVATE_MARKER)

    bad = UncopyableDictionary(id="synthetic-c", payload={"state": "uncopyable"})
    original_value = current_list if mode in {"option_list", "raw_list"} else current_record
    expected_value = copy.deepcopy(original_value)
    if config.get("refresh"):
        expected_value["id"] = "synthetic-a"
        expected_value["payload"]["state"] = "fresh"
    if mode == "bool":
        expected_value = True
    elif mode == "numeric":
        expected_value = 1.0
    elif mode == "large":
        expected_value = {"id": "synthetic-a", "payload": list(range(config["payload_elements"]))}

    def option_values():
        if mode in {"raw_dict", "raw_list"}:
            return [
                original_value,
                alternative if mode == "raw_dict" else ["synthetic-c", {"state": "other"}],
            ]
        if mode == "bool":
            return [
                Option("true", "Boolean true record", True),
                Option("number", "Numeric one record", 1),
            ]
        if mode == "numeric":
            return [
                Option("number", "Floating one record", 1.0),
                Option("true", "Boolean true record", True),
            ]
        if mode == "large":
            return [
                Option(
                    str(i),
                    "Large synthetic record " + str(i),
                    {
                        "id": "synthetic-a" if i == 0 else "synthetic-c-" + str(i),
                        "payload": list(range(config["payload_elements"])),
                    },
                )
                for i in range(config["option_count"])
            ]
        selected = Option(
            "selected",
            "Process current acquired source"
            if config.get("refresh")
            else "Process recorded synthetic-a",
            original_value,
        )
        other = Option("other", "Process synthetic-c", alternative)
        return (
            [other, selected]
            if config.get("select_last")
            else [selected]
            if config.get("singleton")
            else [selected, other]
        )

    # Persistent Option/raw value objects mirror an acquisition owner sharing its current records.
    persistent_options = option_values()
    if mode in {"hook_failure", "duplicate", "oversize"}:
        good = Option(
            "duplicate" if mode == "duplicate" else "selected",
            "Process synthetic-a",
            current_record,
        )
        bad_option = Option(
            "duplicate" if mode == "duplicate" else "uncopyable",
            "Unselected custom synthetic record",
            bad,
        )
        persistent_options = [good, bad_option]
        if mode == "oversize":
            persistent_options = [
                Option(str(i), "Synthetic record " + str(i), current_record)
                for i in range(config["option_count"] - 1)
            ] + [bad_option]

    def capture_domain(key, values):
        provider_calls[key] = provider_calls.get(key, 0) + 1
        source_values = [value.value if isinstance(value, Option) else value for value in values]
        domain_records.append(
            {
                "parameter": key,
                "option_count": len(values),
                "source_value_bytes": sum(len(encoded(value)) for value in source_values),
            }
        )
        return values

    def target_provider(ctx, seen):
        return capture_domain("target", persistent_options)

    def dependent_provider(ctx, seen, bound):
        if mode == "dependent":
            child = {
                "id": bound["parent"]["id"],
                "parent": bound["parent"]["id"],
                "child": "bounded",
            }
            return capture_domain(
                "target",
                [
                    Option("child", "Child of the selected parent", child),
                    Option("other", "Other child", alternative),
                ],
            )
        return capture_domain("target", persistent_options)

    def parent_provider(ctx, seen):
        return capture_domain(
            "parent",
            [
                Option("parent", "Parent synthetic-a", current_record),
                Option("other", "Other parent", alternative),
            ],
        )

    def first_provider(ctx, seen):
        return capture_domain(
            "first",
            [
                Option("anchor", "First fixed anchor", "anchor"),
                Option("other", "Other anchor", "other"),
            ],
        )

    if mode == "dependent":
        expected_args = {
            "parent": copy.deepcopy(current_record),
            "target": {"id": "synthetic-a", "parent": "synthetic-a", "child": "bounded"},
        }
    elif mode in {"hook_failure", "duplicate", "oversize"}:
        expected_args = {"parent": "anchor", "target": copy.deepcopy(current_record)}
    elif mode == "earlier_later":
        expected_args = {"first": "anchor", "target": expected_value}
    else:
        expected_args = {"target": expected_value}
    expected_digest = hashlib.sha256(encoded(expected_args)).hexdigest()

    def record_id(value):
        if type(value) is dict:
            return value["id"]
        if type(value) is list:
            return value[0]
        if mode == "bool":
            return "synthetic-a" if type(value) is bool and value is True else "synthetic-c"
        if mode == "numeric":
            return "synthetic-a" if type(value) is float and value == 1.0 else "synthetic-c"
        raise AssertionError("Unsupported fixed record shape")

    def processed(arguments):
        counts["effects"] += 1
        state["processed_record"] = record_id(arguments["target"])
        state["processed_digest"] = hashlib.sha256(encoded(arguments)).hexdigest()
        return dict(state)

    def mutate_source(refresh=False):
        counts["mutations"] += 1
        current_record["id"] = "synthetic-a" if refresh else "synthetic-b"
        current_record["payload"]["state"] = "fresh" if refresh else "after"
        current_list[0] = "synthetic-a" if refresh else "synthetic-b"
        current_list[1]["state"] = "fresh" if refresh else "after"
        if config.get("private_value"):
            current_record["private_scope"] = PRIVATE_MARKER + ":after"

    def forbid_native(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Snapshot fixtures prohibit native inference")

    def forbid_network(*args, **kwargs):
        counts["real_network_attempts"] += 1
        raise AssertionError("Snapshot fixtures prohibit real HTTP transport")

    def decide(parts, goal, workers, spec):
        context = spec.get("context", {})
        requests.append(
            {
                "stage": context.get("decision_stage"),
                "parameter": context.get("parameter"),
                "record_count": len(parts),
                "record_description_bytes": sum(len(part["text"].encode()) for part in parts),
                "selection_input_bytes": len(
                    json.dumps([parts, spec], ensure_ascii=False).encode()
                ),
                "shared_context_bytes": len(json.dumps(context, ensure_ascii=False).encode()),
                "private_value_exposures": json.dumps([parts, spec], ensure_ascii=False).count(
                    PRIVATE_MARKER
                ),
            }
        )
        if (
            context.get("parameter") == "target"
            and config.get("mutate") == "target_wait"
            or context.get("parameter") == "parent"
            and config.get("mutate") == "parent_wait"
            or context.get("decision_stage") == "tool_selection"
            and config.get("mutate") == "tool_wait"
        ):
            mutate_source()
        if (
            context.get("decision_stage") == "tool_selection"
            and config.get("refresh") == "tool_wait"
            or context.get("parameter") == "first"
            and config.get("refresh") == "first_wait"
        ):
            mutate_source(refresh=True)
        selected = (
            parts[-1]["id"]
            if context.get("parameter") == "target" and config.get("select_last")
            else parts[0]["id"]
        )
        return {
            part["id"]: {
                "status": "OK",
                "decision": "MATCH" if part["id"] == selected else "EXCLUDE",
            }
            for part in parts
        }, {
            "ok": True,
            "usage_complete": not config.get("unknown_usage", False),
            "usage": None
            if config.get("unknown_usage")
            else {"input_tokens": 7, "output_tokens": 2},
            "requests": 1,
            "models": {},
        }

    started = time.perf_counter()
    task = Task(
        observe=lambda ctx: dict(state),
        verify=lambda ctx, seen: (
            seen["processed_record"] == "synthetic-a"
            and seen["processed_digest"] == expected_digest
        ),
        strategy=config.get("strategy", "staged"),
    )
    if mode == "dependent" or mode in {"hook_failure", "duplicate", "oversize"}:
        parent = (
            Parameter("Choose parent record", parent_provider)
            if mode == "dependent"
            else Parameter("Fixed parent anchor", [Option("anchor", "Parent anchor", "anchor")])
        )

        @task.tool(
            "Process exactly the described synthetic-a record",
            parameters={
                "parent": parent,
                "target": Parameter(
                    "Child target for the selected parent",
                    dependent_provider,
                    depends_on=("parent",),
                ),
            },
        )
        def process_record(parent, target):
            return processed({"parent": parent, "target": target})
    elif mode == "earlier_later":

        @task.tool(
            "Process exactly the current synthetic-a record",
            parameters={
                "first": Parameter("First fixed anchor", first_provider),
                "target": Parameter("Fresh target after the first choice", target_provider),
            },
        )
        def process_record(first, target):
            return processed({"first": first, "target": target})
    else:

        @task.tool(
            "Process exactly the described synthetic-a record",
            parameters={
                "target": Parameter(
                    "Select the described target record",
                    persistent_options if config.get("static") else target_provider,
                )
            },
        )
        def process_record(target):
            return processed({"target": target})

    if config.get("mutate") == "after_registration":
        mutate_source()

    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "run.jsonl"
        with (
            patch("apixly_jev_harness.backend.native_run", forbid_native),
            patch("apixly_jev_harness.backend.provider_evaluate", forbid_native),
            patch("apixly_jev_harness.engine.analysis.evaluate", decide),
            patch("apixly_jev_harness.engine.time", SimpleNamespace(monotonic=lambda: 100.0)),
            patch("httpx.HTTPTransport.handle_request", forbid_network),
        ):
            packet = AgentLoop().run(
                task,
                goal="Process the exact record described as synthetic-a",
                max_steps=1,
                archive=archive,
            )
        elapsed = time.perf_counter() - started
        events = [json.loads(line)["event"] for line in archive.read_text().splitlines()]
    compact = {key: value for key, value in packet.items() if key != "archive"}
    is_failure = mode in {"duplicate", "oversize"} or mode == "hook_failure" and arm == "candidate"
    expected_status = "needs_review" if mode == "oversize" else "failed" if is_failure else "done"
    expected_decisions = (
        1
        if is_failure or config.get("strategy") == "joint" or config.get("singleton")
        else 3
        if mode in {"dependent", "earlier_later"}
        else 2
    )
    expected_provider_calls = (
        {}
        if config.get("static")
        else {"parent": 2, "target": 1}
        if mode == "dependent"
        else {"target": 1}
        if mode in {"hook_failure", "duplicate", "oversize"}
        else {"first": 2, "target": 2}
        if mode == "earlier_later"
        else {"target": 1}
        if config.get("strategy") == "joint"
        else {"target": 2}
    )
    expected_usage = (
        None
        if config.get("unknown_usage")
        else {"input_tokens": expected_decisions * 7, "output_tokens": expected_decisions * 2}
    )
    expected = {
        "status": expected_status,
        "effects": 0 if is_failure else 1,
        "steps": 0 if is_failure else 1,
        "processed_record": None if is_failure else "synthetic-a",
        "processed_digest": None if is_failure else expected_digest,
        "scripted_decisions": expected_decisions,
        "provider_calls": expected_provider_calls,
        "usage_complete": not config.get("unknown_usage", False),
        "reported_scripted_usage": expected_usage,
        "copy_hook_calls": 1 if mode == "hook_failure" and arm == "candidate" else 0,
    }
    result = {
        "status": packet["status"],
        "complete": packet["complete"],
        "reason": packet.get("reason"),
        "error_type": packet.get("error_type"),
        "effects": counts["effects"],
        "steps": packet["steps"],
        "processed_record": state["processed_record"],
        "processed_digest": state["processed_digest"],
        "target_matches_description": state["processed_record"] == "synthetic-a"
        and state["processed_digest"] == expected_digest,
        "intent_events": events.count("intent"),
        "scripted_decisions": len(requests),
        "provider_calls": provider_calls,
        "usage_complete": packet["telemetry"]["usage_complete"],
        "reported_scripted_usage": packet["telemetry"]["usage"],
        "copy_hook_calls": counts["copy_hook_calls"],
        "mutations": counts["mutations"],
        "domain_source_measurements": domain_records,
        "request_sizes": requests,
        "native_inference_attempts": counts["native_inference_attempts"],
        "real_network_attempts": counts["real_network_attempts"],
        "terminal_private_value_exposures": json.dumps(compact).count(PRIVATE_MARKER),
    }
    correct = (
        all(result[key] == value for key, value in expected.items())
        and result["intent_events"] == expected["effects"]
        and counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
        and result["terminal_private_value_exposures"] == 0
        and not any(request["private_value_exposures"] for request in requests)
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": {**config, "max_steps": 1, "frozen_loop_monotonic": 100.0},
        "expected": expected,
        "result": result,
        "correct": correct,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(compact, ensure_ascii=False).encode()),
        "actual_model_usage": ZERO_USAGE
        if counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
        else {
            "requests": None,
            "models": {},
            "input_tokens": None,
            "output_tokens": None,
            "usage_complete": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", choices=list(CASES), help=argparse.SUPPRESS)
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    parser.add_argument(
        "--arm", choices=["baseline", "candidate"], default="candidate", help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, args.source_dir)
        print(json.dumps(trial(args.worker, args.source_dir, args.arm)))
        return 0
    if not args.output:
        parser.error("--output is required")
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = snapshot(args.baseline_ref, root / "baseline")
        sources = {"baseline": root / "baseline/src", "candidate": ROOT / "src"}
        hashes = {arm: source_hashes(source) for arm, source in sources.items()}
        runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        for name in CASES:
            for repeat in range(3):
                for arm in (
                    ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                ):
                    env = {
                        key: value
                        for key, value in os.environ.items()
                        if not key.startswith("TYPESAFE_")
                    }
                    output = subprocess.check_output(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--worker",
                            name,
                            "--source-dir",
                            str(sources[arm]),
                            "--arm",
                            arm,
                        ],
                        env=env,
                        text=True,
                    )
                    row = json.loads(output)
                    row.update(arm=arm, repeat=repeat + 1)
                    if (
                        row.pop("source_sha256") != hashes[arm]
                        or not row["runtime_loaded_from_requested_source"]
                    ):
                        raise RuntimeError("runtime_source_changed_or_misloaded")
                    rows.append(row)
        if (
            any(source_hashes(source) != hashes[arm] for arm, source in sources.items())
            or runner_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        ):
            raise RuntimeError("benchmark_sources_changed_during_run")
    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        guard_hit = any(
            row["result"]["native_inference_attempts"] or row["result"]["real_network_attempts"]
            for row in group
        )
        summaries[arm] = {
            "runs": len(group),
            "correct": sum(row["correct"] for row in group),
            "groups": {
                kind: {
                    "runs": sum(row["fixture"]["group"] == kind for row in group),
                    "correct": sum(
                        row["correct"] and row["fixture"]["group"] == kind for row in group
                    ),
                }
                for kind in (
                    "snapshot_fix",
                    "compatibility",
                    "limits_compatibility",
                    "copy_cost",
                    "compatibility_narrowing",
                )
            },
            "wrong_processed_records": sum(
                row["result"]["effects"] > 0 and row["result"]["processed_record"] != "synthetic-a"
                for row in group
            ),
            "snapshot_fixture_runs": sum(
                row["fixture"]["group"] == "snapshot_fix" for row in group
            ),
            "snapshot_description_target_matches": sum(
                row["fixture"]["group"] == "snapshot_fix"
                and row["result"]["target_matches_description"]
                for row in group
            ),
            "effects": sum(row["result"]["effects"] for row in group),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "provider_calls": {
                key: sum(row["result"]["provider_calls"].get(key, 0) for row in group)
                for key in ("parent", "first", "target")
            },
            "copy_hook_calls": sum(row["result"]["copy_hook_calls"] for row in group),
            "unknown_scripted_usage_rows": sum(
                row["result"]["usage_complete"] is False for row in group
            ),
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
            ),
            "real_network_attempts": sum(row["result"]["real_network_attempts"] for row in group),
            "private_value_exposures": sum(
                row["result"]["terminal_private_value_exposures"]
                + sum(
                    request["private_value_exposures"] for request in row["result"]["request_sizes"]
                )
                for row in group
            ),
            "source_record_bytes": sum(
                domain["source_value_bytes"]
                for row in group
                for domain in row["result"]["domain_source_measurements"]
            ),
            "record_description_bytes": sum(
                request["record_description_bytes"]
                for row in group
                for request in row["result"]["request_sizes"]
            ),
            "selection_input_bytes": sum(
                request["selection_input_bytes"]
                for row in group
                for request in row["result"]["request_sizes"]
            ),
            "shared_context_bytes": sum(
                request["shared_context_bytes"]
                for row in group
                for request in row["result"]["request_sizes"]
            ),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "actual_model_usage": ZERO_USAGE
            if not guard_hit
            else {
                "requests": None,
                "models": {},
                "input_tokens": None,
                "output_tokens": None,
                "usage_complete": False,
            },
        }
    parity_keys = (
        "status",
        "complete",
        "reason",
        "error_type",
        "effects",
        "steps",
        "processed_record",
        "processed_digest",
        "intent_events",
        "scripted_decisions",
        "provider_calls",
        "usage_complete",
        "reported_scripted_usage",
        "copy_hook_calls",
        "mutations",
        "domain_source_measurements",
        "request_sizes",
    )
    compatible_groups = {"compatibility", "limits_compatibility", "copy_cost"}
    compatibility_parity = all(
        next(
            row
            for row in rows
            if row["case"] == case and row["repeat"] == repeat and row["arm"] == "baseline"
        )["result"][key]
        == next(
            row
            for row in rows
            if row["case"] == case and row["repeat"] == repeat and row["arm"] == "candidate"
        )["result"][key]
        for case, config in CASES.items()
        if config["group"] in compatible_groups
        for repeat in (1, 2, 3)
        for key in parity_keys
    )
    report = {
        "mode": "offline-synthetic-parameter-snapshots",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "compatibility_parity": compatibility_parity,
        "reproduction": "python benchmarks/parameter_snapshots.py --output local-results/parameter-snapshots-ab.json",
        "scope": "Twenty fixed synthetic tasks, three paired repeats with alternating arm order. Actual Engine/Task/scripted selection pauses mutate acquisition-owned Option/raw dict/list records while the current parameter's value choices await selection. Independent observed processed_record and full argument digest must match the described synthetic-a; wrong execution cannot become done and max_steps=1 prevents repetition. Controls preserve joint/singleton/static behavior, fresh provider domains after tool/earlier-parameter waits, bool/numeric types, unknown scripted usage and duplicate/253-domain gates. Private Option values never appear in public choice descriptions. Native inference and real HTTPTransport are forbidden; actual model/network/UI calls zero if guards stay zero.",
        "negative_results": "Copying every value in every refreshed domain adds local traversal/allocation and trusted deepcopy-hook work, including unselected values. A fixed 16-option domain with 5,000 integer payload elements per option measures whole-operation time; JSON source bytes are serialized representations, not actual extra heap allocation, and immutable objects can be reused. An unselected JSON-serializable custom dictionary with a failing deepcopy hook was previously skipped after selecting a good value; the treatment deliberately fails before execution and preserves prior unknown usage. That case uses distinct per-arm expected outcomes (baseline good done, treatment failed), is a compatibility narrowing and is excluded from snapshot-fix quality. Duplicate/over-253 gates still run before copying. Mutations here occur after domain materialization while scripted choice waits, not concurrently inside deepcopy; no atomic acquisition/copy-race guarantee is tested. Snapshots do not replace observed-world freshness checks, authorization or independent verification, do not cache future provider results and do not undo a baseline's wrong simulated effect. Deepcopy can execute trusted hooks and is not a sandbox or an unconditional guarantee for arbitrary custom objects. Quality here is synthetic candidate/value consistency in the seven mutation fixtures, not AI semantic quality, overall conformance/general success or real UI acceptance; no speed or fee gain is claimed.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only when both guards stay zero; guard hits record unknown actual usage and fail fixtures. Known/unknown scripted usage is separate. Real perf_counter timing includes registration/admission, fresh provider calls and scalar source-size collection, domain snapshots, scripted selection, value binding/effects, independent verification and private journal flush/fsync; excludes process/import/source-fixture construction and post-call analysis/source hashing. Loop-only frozen monotonic values stabilize context budgets without replacing whole-operation timing. Source-record bytes describe full acquisition value payloads; description/input/shared-context bytes are separate scripted decision surfaces, not provider tokens. Returned bytes omit local archive paths and raw private values.",
        "summary": summaries,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"compatibility_parity": compatibility_parity, "summary": summaries}))
    return (
        0
        if compatibility_parity and all(row["correct"] for row in rows if row["arm"] == "candidate")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
