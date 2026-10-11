"""Offline paired Task action admission against exact v0.1.16."""

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
from enum import Enum, IntEnum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "dd6a63325e149a287e3600d0ae9b7bd2789a83dd"
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_ACTION_DETAIL"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "execute_bool_numeric_alias": {"mode": "lowlevel", "kind": "bool_alias", "group": "guard_fix"},
    "execute_nested_bool_numeric": {
        "mode": "lowlevel",
        "kind": "nested_alias",
        "group": "guard_fix",
    },
    "execute_dict_key_bool_numeric": {
        "mode": "lowlevel",
        "kind": "key_alias",
        "group": "guard_fix",
    },
    "joint_bind_irreversible_numeric": {
        "mode": "lowlevel",
        "kind": "irreversible",
        "group": "guard_fix",
        "strategy": "joint",
        "guard_phase": "bind",
    },
    "execute_custom_equality_spoof": {
        "mode": "lowlevel",
        "kind": "custom_value",
        "group": "guard_fix",
    },
    "bind_fake_action_class_spoof": {
        "mode": "lowlevel",
        "kind": "fake_action",
        "group": "guard_fix",
        "guard_phase": "bind",
    },
    "execute_action_subclass_spoof": {
        "mode": "lowlevel",
        "kind": "action_subclass",
        "group": "guard_fix",
    },
    "staged_numeric_alias_compatible": {
        "mode": "lowlevel",
        "kind": "numeric_alias",
        "group": "compatibility",
    },
    "joint_numeric_alias_compatible": {
        "mode": "lowlevel",
        "kind": "numeric_alias",
        "group": "compatibility",
        "strategy": "joint",
    },
    "numeric_dict_key_alias_compatible": {
        "mode": "lowlevel",
        "kind": "numeric_key",
        "group": "compatibility",
    },
    "engine_staged_normal": {"mode": "engine", "kind": "normal", "group": "compatibility"},
    "engine_joint_normal": {
        "mode": "engine",
        "kind": "normal",
        "group": "compatibility",
        "strategy": "joint",
    },
    "engine_dependent_fresh_unknown": {
        "mode": "engine",
        "kind": "dependent",
        "group": "compatibility",
        "unknown_usage": True,
    },
    "unmodified_int_enum_value": {
        "mode": "engine",
        "kind": "int_enum",
        "group": "compatibility_narrowing",
    },
    "unmodified_string_enum_value": {
        "mode": "engine",
        "kind": "string_enum",
        "group": "compatibility_narrowing",
    },
    "unmodified_dict_subclass_value": {
        "mode": "engine",
        "kind": "dict_subclass",
        "group": "compatibility_narrowing",
    },
    "bind_dict_subclass_metadata": {
        "mode": "engine",
        "kind": "metadata_subclass",
        "group": "compatibility_narrowing",
    },
    "unmodified_string_enum_tool_id": {
        "mode": "engine",
        "kind": "enum_id",
        "group": "compatibility_narrowing",
    },
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def trial(name, source_dir, arm):
    from apixly_jev_harness import Action, AgentLoop, Option, Parameter, Task, __version__
    from apixly_jev_harness import __file__ as runtime_file

    config, kind = CASES[name], CASES[name]["kind"]
    counts = {
        "effects": 0,
        "custom_eq_calls": 0,
        "class_property_reads": 0,
        "provider_calls": 0,
        "native_inference_attempts": 0,
        "real_network_attempts": 0,
    }
    requests, received_labels = [], []
    state = {"progress": 0}

    class IntegerValue(IntEnum):
        ONE = 1

    class StringValue(str, Enum):
        VALUE = "authorized"
        TOOL = "process_record"

    class JsonDictionary(dict):
        pass

    class CustomEqual:
        def __deepcopy__(self, memo):
            return self

        def __eq__(self, other):
            counts["custom_eq_calls"] += 1
            return True

    class FakeAction:
        def __init__(self, source):
            self.id, self.description = source.id, source.description
            self.params, self.irreversible = copy.deepcopy(source.params), source.irreversible

        @property
        def __class__(self):
            counts["class_property_reads"] += 1
            return Action

        def __eq__(self, other):
            counts["custom_eq_calls"] += 1
            return True

        def __ne__(self, other):
            return not self.__eq__(other)

    class ActionSubclass(Action):
        @property
        def __class__(self):
            counts["class_property_reads"] += 1
            return Action

    value = {
        "bool_alias": True,
        "nested_alias": {"values": [True, False]},
        "key_alias": {True: "authorized"},
        "numeric_alias": 1,
        "numeric_key": {1: "authorized"},
        "int_enum": IntegerValue.ONE,
        "string_enum": StringValue.VALUE,
        "dict_subclass": JsonDictionary(authorized=True),
    }.get(kind, True)

    def label(target):
        if type(target) is CustomEqual:
            return "unsupported_custom_value"
        if type(target) is IntegerValue:
            return "int_enum"
        if type(target) is StringValue:
            return "string_enum"
        if type(target) is JsonDictionary:
            return "dict_subclass"
        if type(target) is bool:
            return "builtin_boolean"
        if type(target) is int:
            return "builtin_integer"
        if type(target) is float:
            return "builtin_float"
        if type(target) is dict:
            return "builtin_dictionary"
        return "other_fixed_value"

    class MetadataTask(Task):
        def candidates(self, ctx, seen):
            actions = super().candidates(ctx, seen)
            for action in actions:
                object.__setattr__(action, "params", JsonDictionary(action.params))
            return actions

    task_class = MetadataTask if kind == "metadata_subclass" else Task
    target_progress = 3 if kind == "dependent" else 1
    task = task_class(
        observe=lambda ctx: dict(state),
        verify=lambda ctx, seen: seen["progress"] == target_progress,
        strategy=config.get("strategy", "staged"),
    )
    if kind == "dependent":

        def provider(ctx, seen, bound):
            counts["provider_calls"] += 1
            return [
                Option(
                    "current",
                    "Fresh amount from current observation and parent",
                    seen["progress"] + bound["parent"],
                )
            ]

        @task.tool(
            "Reach the synthetic target using fresh dependent values",
            parameters={
                "parent": [1],
                "target": Parameter("Fresh dependent amount", provider, depends_on=("parent",)),
            },
        )
        def process_record(parent, target):
            counts["effects"] += 1
            received_labels.append(label(target))
            state["progress"] += target
    else:

        @task.tool(
            "Apply the program's admitted synthetic value",
            name=StringValue.TOOL if kind == "enum_id" else None,
            parameters={
                "target": Parameter(
                    "One admitted synthetic value",
                    [Option("authorized", "Authorized synthetic value", value)],
                )
            },
        )
        def process_record(target):
            counts["effects"] += 1
            received_labels.append(label(target))
            state["progress"] = 1

    def mutate(action):
        if kind == "fake_action":
            return FakeAction(action)
        if kind == "action_subclass":
            return ActionSubclass(
                action.id, action.description, copy.deepcopy(action.params), action.irreversible
            )
        attempted = copy.deepcopy(action)
        if kind == "irreversible":
            object.__setattr__(attempted, "irreversible", 0)
        else:
            changed = {
                "bool_alias": 1,
                "nested_alias": {"values": [1, 0]},
                "key_alias": {1: "authorized"},
                "numeric_alias": 1.0,
                "numeric_key": {1.0: "authorized"},
                "custom_value": CustomEqual(),
            }[kind]
            attempted.params["arguments"]["target"] = changed
        return attempted

    def forbid_native(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Action fixtures prohibit native inference")

    def forbid_network(*args, **kwargs):
        counts["real_network_attempts"] += 1
        raise AssertionError("Action fixtures prohibit real HTTP transport")

    def decide(parts, goal, workers, spec):
        requests.append(
            {
                "selection_input_bytes": len(
                    json.dumps([parts, spec], ensure_ascii=False).encode()
                ),
                "shared_context_bytes": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False).encode()
                ),
            }
        )
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": not config.get("unknown_usage", False),
            "usage": None
            if config.get("unknown_usage")
            else {"input_tokens": 7, "output_tokens": 2},
            "requests": 1,
            "models": {},
        }

    def no_parameter_choice(*args, **kwargs):
        raise AssertionError("Fixed singleton domain needs no semantic parameter choice")

    packet, error_code, error_type, stopped_phase = None, None, None, None
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "run.jsonl"
        with (
            patch("apixly_jev_harness.backend.native_run", forbid_native),
            patch("apixly_jev_harness.backend.provider_evaluate", forbid_native),
            patch("apixly_jev_harness.engine.analysis.evaluate", decide),
            patch("apixly_jev_harness.engine.time", SimpleNamespace(monotonic=lambda: 100.0)),
            patch("httpx.HTTPTransport.handle_request", forbid_network),
        ):
            if config["mode"] == "engine":
                packet = AgentLoop().run(
                    task, goal="Complete the admitted synthetic task", max_steps=3, archive=archive
                )
            else:
                try:
                    offered = task.candidates(None, dict(state))[0]
                    if config.get("guard_phase") == "bind":
                        stopped_phase = "bind"
                        bound = task.bind(None, dict(state), mutate(offered), no_parameter_choice)
                    else:
                        bound = task.bind(None, dict(state), offered, no_parameter_choice)
                    stopped_phase = "execute"
                    task.execute(
                        None, mutate(bound) if config.get("guard_phase") != "bind" else bound
                    )
                    stopped_phase = None
                except ValueError as error:
                    error_type = type(error).__name__
                    code = str(error)
                    error_code = (
                        code
                        if code in {"action_not_offered", "action_not_bound"}
                        else "other_fixed_error"
                    )
        elapsed = time.perf_counter() - started
        events = (
            [json.loads(line)["event"] for line in archive.read_text().splitlines()]
            if archive.exists()
            else []
        )
    compact = (
        {key: value for key, value in packet.items() if key != "archive"}
        if packet
        else {
            "status": "rejected" if error_type else "accepted",
            "error_type": error_type,
            "code": error_code,
        }
    )
    status = packet["status"] if packet else compact["status"]
    target_rejected = config["group"] == "guard_fix"
    narrowed = config["group"] == "compatibility_narrowing" and arm == "candidate"
    if config["mode"] == "lowlevel":
        expected_status = "rejected" if target_rejected else "accepted"
        expected_steps, expected_calls = None, 0
        expected_code = (
            ("action_not_offered" if config.get("guard_phase") == "bind" else "action_not_bound")
            if target_rejected
            else None
        )
    else:
        expected_status = (
            "failed"
            if narrowed and kind in {"metadata_subclass", "enum_id"}
            else "execution_uncertain"
            if narrowed
            else "done"
        )
        expected_steps, expected_calls, expected_code = (
            0 if narrowed else 2 if kind == "dependent" else 1,
            2 if kind == "dependent" else 1,
            None,
        )
    expected_effects = 0 if target_rejected or narrowed else 2 if kind == "dependent" else 1
    expected_usage = (
        None
        if config.get("unknown_usage")
        else {"input_tokens": expected_calls * 7, "output_tokens": expected_calls * 2}
    )
    expected = {
        "status": expected_status,
        "effects": expected_effects,
        "steps": expected_steps,
        "scripted_decisions": expected_calls,
        "code": expected_code,
        "usage_complete": not config.get("unknown_usage", False),
        "reported_scripted_usage": expected_usage,
        "provider_calls": 2 if kind == "dependent" else 0,
    }
    result = {
        "status": status,
        "complete": packet.get("complete") if packet else None,
        "reason": packet.get("reason") if packet else None,
        "code": error_code,
        "error_type": packet.get("error_type") if packet else error_type,
        "stopped_guard_phase": stopped_phase,
        "steps": packet.get("steps") if packet else None,
        "effects": counts["effects"],
        "intent_events": events.count("intent"),
        "scripted_decisions": len(requests),
        "provider_calls": counts["provider_calls"],
        "received_value_labels": received_labels,
        "usage_complete": packet["telemetry"]["usage_complete"] if packet else True,
        "reported_scripted_usage": packet["telemetry"]["usage"]
        if packet
        else {"input_tokens": 0, "output_tokens": 0},
        "action_id_present": "action_id" in packet if packet else False,
        "custom_eq_calls": counts["custom_eq_calls"],
        "class_property_reads": counts["class_property_reads"],
        "request_sizes": requests,
        "native_inference_attempts": counts["native_inference_attempts"],
        "real_network_attempts": counts["real_network_attempts"],
        "raw_private_marker_exposures": json.dumps(compact).count(PRIVATE_MARKER),
    }
    correct = (
        all(result[key] == value for key, value in expected.items())
        and counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
        and result["raw_private_marker_exposures"] == 0
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": {**config, "frozen_loop_monotonic": 100.0},
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
                for kind in ("guard_fix", "compatibility", "compatibility_narrowing")
            },
            "manual_guard_fix_accepted": sum(
                row["fixture"]["group"] == "guard_fix" and row["result"]["status"] == "accepted"
                for row in group
            ),
            "effects": sum(row["result"]["effects"] for row in group),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "provider_calls": sum(row["result"]["provider_calls"] for row in group),
            "unknown_scripted_usage_rows": sum(
                row["result"]["usage_complete"] is False for row in group
            ),
            "execution_uncertain_rows": sum(
                row["result"]["status"] == "execution_uncertain" for row in group
            ),
            "execution_uncertain_body_zero_rows": sum(
                row["result"]["status"] == "execution_uncertain" and row["result"]["effects"] == 0
                for row in group
            ),
            "custom_eq_calls": sum(row["result"]["custom_eq_calls"] for row in group),
            "class_property_reads": sum(row["result"]["class_property_reads"] for row in group),
            "native_inference_attempts": sum(
                row["result"]["native_inference_attempts"] for row in group
            ),
            "real_network_attempts": sum(row["result"]["real_network_attempts"] for row in group),
            "raw_private_marker_exposures": sum(
                row["result"]["raw_private_marker_exposures"] for row in group
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
        "code",
        "error_type",
        "steps",
        "effects",
        "intent_events",
        "scripted_decisions",
        "provider_calls",
        "received_value_labels",
        "usage_complete",
        "reported_scripted_usage",
        "action_id_present",
        "request_sizes",
    )
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
        if config["group"] == "compatibility"
        for repeat in (1, 2, 3)
        for key in parity_keys
    )
    report = {
        "mode": "offline-synthetic-action-identity",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "compatibility_parity": compatibility_parity,
        "reproduction": "python benchmarks/action_identity.py --output local-results/action-identity-ab.json",
        "scope": "Eighteen fixed synthetic tasks, three paired repeats with alternating arm order. Seven public low-level Task API fixtures manually replace offered/bound action fields or types; bool/number aliases, nested key/list aliases, numeric irreversible metadata and custom/FakeAction/subclass equality must not pass the typed guard. Standard Engine never performs these action mutations and this is not a model-output attack. Six compatibility fixtures preserve staged/joint numeric 1/1.0 and numeric dictionary-key equivalence, normal Engine progression and two fresh dependent actions with unknown scripted usage. Five per-arm negative fixtures record unmodified JSON-compatible enums/dictionary subclasses or metadata previously accepted and now rejected. Native inference and real HTTPTransport are forbidden; actual model/network/UI calls zero if guards stay zero.",
        "negative_results": "The same-action comparison is recursive and adds local guard work; no speed or fee gain is claimed. Exact builtin-value/action/id requirements narrow compatibility: a baseline's unmodified IntEnum, string enum or dictionary subclass can execute correctly, while treatment bind rejects with failed or an execute guard triggers execution_uncertain before the measured tool body. That conservative executed/intent window remains; these synthetic body-zero rows do not prove global absence of side effects or permit reruns. Negative fixtures use distinct per-arm expected outcomes and are excluded from manual-mutation guard quality. Numeric int/float equivalence intentionally remains. This is synthetic API identity consistency, not AI semantic quality, actual UI acceptance, a Python sandbox or a general capability boundary; trusted deepcopy/serialization and caller code can still run hooks.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only when both guards remain zero; guard hits record unknown actual usage and fail fixtures. Scripted usage is separate from actual usage. Real perf_counter timing includes Task domain materialization/binding/guards/execution or actual Engine admission, scripted selection, effects and private journal flush/fsync; excludes imports/task-fixture setup and post-call analysis/source hashing. Loop-only frozen monotonic values stabilize context budgets without replacing real timing. Returned bytes omit local archive paths and use a fixed exception projection for direct API rejection, not a fabricated Engine terminal. Scalar input/context sizes do not count provider tokens.",
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
