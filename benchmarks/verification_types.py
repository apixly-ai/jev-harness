"""Offline paired mechanical verifier type checks against exact v0.1.13."""

import argparse
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
BASELINE = "8e25a38293284265edb4d3b512234f42bfa53d2c"
LABEL = "Synthetic control"
PRIVATE_MARKER = "SYNTHETIC_CUSTOM_EQ_PRIVATE"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
FALSE_COMPLETIONS = (
    "expected_true_observed_one",
    "expected_false_observed_zero",
    "expected_one_observed_true",
    "nested_list_bool_number",
    "nested_dict_bool_number",
    "nested_tuple_bool_number",
    "dict_key_true_one",
    "dict_key_false_zero",
    "text_observed_list",
    "text_observed_dict",
    "unsupported_expected_value",
    "unsupported_expected_nested",
    "unsupported_expected_key",
    "observed_str_subclass_checked_key",
    "observed_str_subclass_label_key",
    "metaclass_float_spoof_expected",
    "root_text_alias_key",
    "root_controls_alias_key",
)
COMPATIBILITY = {
    "same_boolean": True,
    "int_float_numeric": True,
    "numeric_dictionary_keys": True,
    "same_list_types": True,
    "same_tuple_types": True,
    "observed_null": True,
    "missing_field": False,
    "duplicate_label": False,
    "text_substring": True,
    "list_tuple_mismatch": False,
    "custom_verifier_unchanged": True,
}
CASES = {
    **{name: {"group": "false_completion", "expected_match": False} for name in FALSE_COMPLETIONS},
    **{
        name: {"group": "compatibility", "expected_match": matches}
        for name, matches in COMPATIBILITY.items()
    },
    "unsupported_expected_outer_key": {
        "group": "construction_fix",
        "expected_match": None,
        "construction_error": "ValueError",
    },
    "expected_str_subclass_outer_key": {
        "group": "construction_fix",
        "expected_match": None,
        "construction_error": "ValueError",
    },
    "empty_text_subclass_fake_strip": {
        "group": "construction_fix",
        "expected_match": None,
        "construction_error": "ValueError",
    },
    "continue_after_numeric_known": {
        "group": "continuation_fix",
        "expected_match": False,
        "continuation": True,
    },
    "continue_after_numeric_unknown": {
        "group": "continuation_fix",
        "expected_match": False,
        "continuation": True,
        "unknown_usage": True,
    },
    "compatible_continuation_unknown": {
        "group": "compatibility",
        "expected_match": False,
        "continuation": True,
        "unknown_usage": True,
    },
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def type_shape(value):
    kind = type(value)
    if any(kind is supported for supported in (type(None), bool, int, float, str)):
        return kind.__name__
    if kind is list or kind is tuple:
        return {"type": kind.__name__, "items": [type_shape(item) for item in value]}
    if kind is dict:
        return {
            "type": "dict",
            "entries": [
                {"key": type_shape(key), "value": type_shape(item)} for key, item in value.items()
            ],
        }
    return "unsupported_python_object"


def trial(name, source_dir):
    from apixly_jev_harness import AgentLoop, Task, __version__, verify_state
    from apixly_jev_harness import __file__ as runtime_file

    config = CASES[name]
    counts = {
        "effects": 0,
        "custom_eq_calls": 0,
        "metaclass_eq_calls": 0,
        "custom_float_calls": 0,
        "custom_strip_calls": 0,
        "native_inference_attempts": 0,
        "real_network_attempts": 0,
    }
    requests = []

    class UnsupportedExpected:
        def __deepcopy__(self, memo):
            return self

        def __eq__(self, other):
            counts["custom_eq_calls"] += 1
            return True

        def __hash__(self):
            return 0

    unsupported = UnsupportedExpected()

    class UnsupportedFieldKey(UnsupportedExpected):
        def __hash__(self):
            return hash("checked")

    class StringSubclassKey(str):
        __hash__ = str.__hash__

        def __deepcopy__(self, memo):
            return self

        def __eq__(self, other):
            counts["custom_eq_calls"] += 1
            return str.__eq__(self, other)

    class FloatSpoofMeta(type):
        def __hash__(self):
            return hash(float)

        def __eq__(self, other):
            counts["metaclass_eq_calls"] += 1
            return other is float

    class FloatSpoofExpected(UnsupportedExpected, metaclass=FloatSpoofMeta):
        def __float__(self):
            counts["custom_float_calls"] += 1
            return 0.0

    class RootAliasKey(str):
        def __new__(cls, target):
            value = str.__new__(cls, "unrelated")
            value.lookup_target = target
            return value

        def __deepcopy__(self, memo):
            return self

        def __hash__(self):
            return hash(self.lookup_target)

        def __eq__(self, other):
            counts["custom_eq_calls"] += 1
            return type(other) is str and other == self.lookup_target

    class EmptyTextTarget(str):
        def strip(self, *args):
            counts["custom_strip_calls"] += 1
            return PRIVATE_MARKER

    text, checks, state = None, [], {}
    if name in {"text_observed_list", "text_observed_dict", "text_substring"}:
        text = "Complete"
        state["text"] = (
            ["Complete"]
            if name == "text_observed_list"
            else {"Complete": True}
            if name == "text_observed_dict"
            else "Task Complete now"
        )
    elif name == "empty_text_subclass_fake_strip":
        text = EmptyTextTarget("")
        state = {}
    elif name in {"root_text_alias_key", "root_controls_alias_key"}:
        if name == "root_text_alias_key":
            text = "Complete"
            state = {RootAliasKey("text"): "Task Complete now"}
        else:
            checks = [{"label": LABEL, "checked": True}]
            state = {RootAliasKey("controls"): [{"label": LABEL, "checked": True}]}
    elif config.get("construction_error"):
        field_key = (
            UnsupportedFieldKey()
            if name == "unsupported_expected_outer_key"
            else StringSubclassKey("checked")
        )
        checks = [{"label": LABEL, field_key: True}]
        state = {"controls": [{"label": LABEL, "checked": True}]}
    else:
        expected, observed = {
            "expected_true_observed_one": (True, 1),
            "expected_false_observed_zero": (False, 0),
            "expected_one_observed_true": (1, True),
            "nested_list_bool_number": ([True, {"flag": False}], [1, {"flag": 0}]),
            "nested_dict_bool_number": (
                {"items": [{"checked": True}]},
                {"items": [{"checked": 1}]},
            ),
            "nested_tuple_bool_number": ((True, {"flag": False}), (1, {"flag": 0})),
            "dict_key_true_one": ({True: "value"}, {1: "value"}),
            "dict_key_false_zero": ({False: "value"}, {0: "value"}),
            "unsupported_expected_value": (unsupported, 0),
            "unsupported_expected_nested": ([unsupported], [0]),
            "unsupported_expected_key": ({unsupported: "value"}, {0: "value"}),
            "observed_str_subclass_checked_key": (True, True),
            "observed_str_subclass_label_key": (True, True),
            "metaclass_float_spoof_expected": (FloatSpoofExpected(), 0),
            "same_boolean": (True, True),
            "int_float_numeric": (1, 1.0),
            "numeric_dictionary_keys": ({1: "value"}, {1.0: "value"}),
            "same_list_types": ([1, True, None], [1.0, True, None]),
            "same_tuple_types": ((1, True, None), (1.0, True, None)),
            "observed_null": (None, None),
            "missing_field": (None, None),
            "duplicate_label": ("value", "value"),
            "list_tuple_mismatch": ([1], (1,)),
            "custom_verifier_unchanged": (True, 1),
            "continue_after_numeric_known": (True, 1),
            "continue_after_numeric_unknown": (True, 1),
            "compatible_continuation_unknown": (True, False),
        }[name]
        field = (
            "checked"
            if name
            in {
                "expected_true_observed_one",
                "expected_false_observed_zero",
                "same_boolean",
                "custom_verifier_unchanged",
                "observed_str_subclass_checked_key",
                "observed_str_subclass_label_key",
            }
            or config.get("continuation")
            else "value"
        )
        checks = [{"label": LABEL, field: expected}]
        control = {"label": LABEL, field: observed}
        if name == "observed_str_subclass_checked_key":
            control = {"label": LABEL, StringSubclassKey("checked"): True}
        elif name == "observed_str_subclass_label_key":
            control = {StringSubclassKey("label"): LABEL, "checked": True}
        if name == "missing_field":
            control.pop(field)
        state["controls"] = [control, dict(control)] if name == "duplicate_label" else [control]

    initial_shape = type_shape(state)
    expected_shape = type_shape(checks) if checks else {"text": type_shape(text)}

    def forbid_native(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Verifier fixtures prohibit native inference")

    def forbid_network(*args, **kwargs):
        counts["real_network_attempts"] += 1
        raise AssertionError("Verifier fixtures prohibit real HTTP transport")

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

    initial_result = None
    initial_eq_calls = 0
    magic_keys = (
        "custom_eq_calls",
        "metaclass_eq_calls",
        "custom_float_calls",
        "custom_strip_calls",
    )
    comparison_magic_calls = {key: 0 for key in magic_keys}
    preparation_magic_calls = {key: 0 for key in magic_keys}
    construction_error = None
    packet, events = None, []
    started = time.perf_counter()
    custom_expected_boolean = True
    try:
        verifier = (
            (lambda ctx, seen: seen["controls"][0]["checked"] == custom_expected_boolean)
            if name == "custom_verifier_unchanged"
            else verify_state(text=text, controls=checks)
        )
    except ValueError as error:
        construction_error = type(error).__name__
        preparation_magic_calls = {key: counts[key] for key in magic_keys}
    else:
        preparation_magic_calls = {key: counts[key] for key in magic_keys}

        def tracked_verifier(ctx, seen):
            before_comparison = {key: counts[key] for key in magic_keys}
            try:
                return verifier(ctx, seen)
            finally:
                for key in magic_keys:
                    comparison_magic_calls[key] += counts[key] - before_comparison[key]

        initial_result = tracked_verifier(None, state)
        initial_eq_calls = counts["custom_eq_calls"]
        workflow = Task(observe=lambda ctx: state, verify=tracked_verifier)
        if config.get("continuation"):

            @workflow.tool("Write an explicit boolean completion observation")
            def complete():
                counts["effects"] += 1
                state["controls"][0]["checked"] = True

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
                    workflow,
                    goal="Verify one synthetic observable condition",
                    max_steps=1,
                    archive=archive,
                )
            elapsed = time.perf_counter() - started
            events = [
                json.loads(line)["event"]
                for line in archive.read_text(encoding="utf-8").splitlines()
            ]
    if construction_error:
        elapsed = time.perf_counter() - started
    compact = (
        {key: value for key, value in packet.items() if key != "archive"}
        if packet
        else {"helper_construction_error_type": construction_error}
    )
    expected_effects = int(bool(config.get("continuation")))
    expected_status = (
        "rejected"
        if config.get("construction_error")
        else "done"
        if config.get("continuation") or config["expected_match"]
        else "blocked"
    )
    expected_usage_complete = not config.get("unknown_usage", False) if expected_effects else True
    expected_usage = (
        None
        if not expected_usage_complete
        else {"input_tokens": 7, "output_tokens": 2}
        if expected_effects
        else {"input_tokens": 0, "output_tokens": 0}
    )
    expected_metadata = {
        "initial_match": config["expected_match"],
        "status": expected_status,
        "effects": expected_effects,
        "steps": None if config.get("construction_error") else expected_effects,
        "construction_error_type": config.get("construction_error"),
        "scripted_decisions": expected_effects,
        "usage_complete": expected_usage_complete,
        "reported_scripted_usage": expected_usage,
    }
    result = {
        "initial_match": initial_result,
        "status": packet["status"] if packet else "rejected",
        "complete": packet["complete"] if packet else None,
        "reason": packet.get("reason") if packet else None,
        "construction_error_type": construction_error,
        "effects": counts["effects"],
        "steps": packet["steps"] if packet else None,
        "intent_events": events.count("intent"),
        "scripted_decisions": len(requests),
        "usage_complete": packet["telemetry"]["usage_complete"] if packet else True,
        "reported_scripted_usage": packet["telemetry"]["usage"]
        if packet
        else {"input_tokens": 0, "output_tokens": 0},
        "custom_eq_calls_initial": initial_eq_calls,
        "custom_eq_calls_total": counts["custom_eq_calls"],
        "metaclass_eq_calls": counts["metaclass_eq_calls"],
        "custom_float_calls": counts["custom_float_calls"],
        "custom_strip_calls": counts["custom_strip_calls"],
        "preparation_magic_calls": preparation_magic_calls,
        "helper_comparison_magic_calls": comparison_magic_calls,
        "other_loop_magic_calls": {
            key: counts[key] - preparation_magic_calls[key] - comparison_magic_calls[key]
            for key in magic_keys
        },
        "custom_eq_private_marker_digest": hashlib.sha256(PRIVATE_MARKER.encode()).hexdigest(),
        "native_inference_attempts": counts["native_inference_attempts"],
        "real_network_attempts": counts["real_network_attempts"],
        "raw_private_marker_exposures": json.dumps(compact).count(PRIVATE_MARKER),
        "request_sizes": requests,
    }
    correct = (
        all(result[key] == value for key, value in expected_metadata.items())
        and result["intent_events"] == expected_effects
        and all(value == 0 for value in comparison_magic_calls.values())
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
        "fixture": {
            **config,
            "expected_type_shape": expected_shape,
            "observed_initial_type_shape": initial_shape,
            "frozen_loop_monotonic": 100.0,
        },
        "expected": expected_metadata,
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
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, args.source_dir)
        print(json.dumps(trial(args.worker, args.source_dir)))
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
                    "false_completion",
                    "construction_fix",
                    "continuation_fix",
                    "compatibility",
                )
            },
            "mechanical_false_initial_matches": sum(
                row["result"]["initial_match"] is True
                and row["expected"]["initial_match"] is not True
                for row in group
            ),
            "false_completed_no_tool_rows": sum(
                row["fixture"]["group"] in {"false_completion", "construction_fix"}
                and row["result"]["complete"] is True
                for row in group
            ),
            "custom_eq_calls": sum(row["result"]["custom_eq_calls_total"] for row in group),
            "metaclass_eq_calls": sum(row["result"]["metaclass_eq_calls"] for row in group),
            "custom_float_calls": sum(row["result"]["custom_float_calls"] for row in group),
            "custom_strip_calls": sum(row["result"]["custom_strip_calls"] for row in group),
            "helper_comparison_magic_calls": {
                key: sum(row["result"]["helper_comparison_magic_calls"][key] for row in group)
                for key in (
                    "custom_eq_calls",
                    "metaclass_eq_calls",
                    "custom_float_calls",
                    "custom_strip_calls",
                )
            },
            "helper_construction_rejections": sum(
                row["result"]["construction_error_type"] is not None for row in group
            ),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "effects": sum(row["result"]["effects"] for row in group),
            "unknown_scripted_usage_rows": sum(
                row["result"]["usage_complete"] is False for row in group
            ),
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
        "initial_match",
        "status",
        "complete",
        "reason",
        "steps",
        "effects",
        "intent_events",
        "scripted_decisions",
        "usage_complete",
        "reported_scripted_usage",
        "request_sizes",
        "custom_eq_calls_total",
        "metaclass_eq_calls",
        "custom_float_calls",
        "custom_strip_calls",
        "construction_error_type",
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
        "mode": "offline-synthetic-verification-types",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "compatibility_parity": compatibility_parity,
        "reproduction": "python benchmarks/verification_types.py --output local-results/verification-types-ab.json",
        "scope": "Thirty-five fixed synthetic verifier fixtures, three paired repeats with alternating arm order. Actual Engine/Task without tools proves eighteen helper false-completion cases become blocked with zero inference/effects; three invalid expected outer-key/text-subclass contracts reject at helper construction without an Engine run or terminal packet. Fixtures cover bool/number distinction, nested list/dict/tuple values, typed dictionary keys, observed text type, unsupported equality/metaclass objects and observed record/root string-subclass alias keys. Valid numeric int/float comparison, same container types, null/missing/duplicates/text substring and caller-owned custom verifier behavior remain compatible. Two formerly false-completed tasks continue to a scripted tool that writes true and then verify; one compatible continuation preserves unknown prior scripted usage in both arms. Private equality detail is represented only by fixed type shapes/digests/call counts; counters retain the complete observed helper/loop sequence rather than claiming all deepcopy/JSON hooks disappear. Native inference and real HTTPTransport are forbidden during loop execution; all fixture helper/magic definitions are fixed local counters with no external calls. Actual model/network/UI calls zero if guards are never hit.",
        "negative_results": "Correctly rejecting a false initial match can require an additional scripted decision/effect, output context and journal work. An initial smoke assertion wrongly required all magic hooks across construction and the entire loop to be zero: two observed string-subclass-key fixtures each retain one other-loop equality call, and the metaclass fixture retains one preparation equality call while helper comparison calls remain zero. The corrected comparison-scoped assertion retains all accumulated counts. Construction rejections deliberately have no Engine terminal and are not presented as blocked/done. The formerly false-done continuation baseline has no call and known zero scripted usage; only the treatment's continued unknown-usage case has an unknown call, which stays unknown. Quality improvement here is mechanical helper type correctness, not AI semantic quality, a real browser/desktop acceptance, global input admission or arbitrary custom verifier correctness. JSON journaling does not restore original tuple/list types or recover dictionary keys already collapsed by Python construction. Helper comparison avoids unsupported equality hooks; trusted callback/deepcopy/serialization definitions remain outside a sandbox and can still execute code. No speed or fee gain is claimed.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only when both guards stay zero; guard hits record unknown actual usage and fail fixtures. Known/unknown scripted usage is separate from actual usage. Real perf_counter timing includes helper construction/initial check, Task registration, loop admission, optional scripted selection/effect, independent helper verification and private journal flush/fsync; excludes process/import/input-fixture setup and terminal analysis/source hashes. Loop-only frozen monotonic values stabilize request budgets without replacing whole-operation timing. Returned bytes omit local archive paths and count a fixed exception-type projection for constructor-only failures, not a fabricated Engine packet. Scalar context/input sizes are not provider-token counts.",
        "summary": summaries,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"compatibility_parity": compatibility_parity, "summary": summaries}))
    return (
        0
        if compatibility_parity and all(row["correct"] for row in rows if row["arm"] == "candidate")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
