"""Offline paired provider signature binding against exact v0.1.12."""

import argparse
import functools
import hashlib
import inspect
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
BASELINE = "851a865345230a0d151de60679cd776fcac16070"
PRIVATE_PREFIX = "SYNTHETIC_PRIVATE_ARGUMENT_"
PARENT = PRIVATE_PREFIX + "PARENT"
PREFIX = PRIVATE_PREFIX + "PREFIX:"
ZERO_USAGE = {
    "requests": 0,
    "models": {},
    "input_tokens": 0,
    "output_tokens": 0,
    "usage_complete": True,
}
CASES = {
    "explicit_three_wraps_two": {"kind": "three_wraps_two", "group": "binding_fix", "arity": 3},
    "explicit_two_wraps_three": {"kind": "two_wraps_three", "group": "binding_fix", "arity": 2},
    "partial_prefix_three_wraps_two": {
        "kind": "partial_bridge",
        "group": "binding_fix",
        "arity": 3,
    },
    "bound_method_three_wraps_two": {"kind": "bound_method", "group": "binding_fix", "arity": 3},
    "callable_three_wraps_two": {"kind": "callable_object", "group": "binding_fix", "arity": 3},
    "optional_three_wraps_two_known": {
        "kind": "optional_bridge",
        "group": "binding_fix",
        "arity": 3,
    },
    "optional_three_wraps_two_unknown": {
        "kind": "optional_bridge",
        "group": "binding_fix",
        "arity": 3,
        "unknown_usage": True,
    },
    "named_three_variadic_wraps_two": {
        "kind": "named_variadic_bridge",
        "group": "binding_fix",
        "arity": 3,
    },
    "plain_two": {"kind": "plain_two", "group": "compatibility", "arity": 2},
    "plain_three": {"kind": "plain_three", "group": "compatibility", "arity": 3},
    "plain_optional_three": {"kind": "plain_optional", "group": "compatibility", "arity": 3},
    "explicit_signature_two": {"kind": "explicit_signature", "group": "compatibility", "arity": 2},
    "generic_wraps_two": {"kind": "generic_two", "group": "compatibility", "arity": 2},
    "generic_wraps_three": {"kind": "generic_three", "group": "compatibility", "arity": 3},
    "partial_generic_three": {"kind": "partial_generic", "group": "compatibility", "arity": 3},
    "plain_four_rejected": {
        "kind": "plain_four",
        "group": "compatibility",
        "code": "provider_signature_unsupported",
    },
    "coroutine_rejected": {
        "kind": "coroutine",
        "group": "compatibility",
        "code": "synchronous_callback_required",
    },
    "actual_four_wraps_two_rejected": {
        "kind": "four_wraps_two",
        "group": "admission_fix",
        "code": "provider_signature_unsupported",
    },
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def value_digest(parent, target):
    return hashlib.sha256((parent + "\0" + target).encode()).hexdigest()


def trial(name, source_dir):
    from apixly_jev_harness import AgentLoop, Option, Parameter, Task, __version__
    from apixly_jev_harness import __file__ as runtime_file
    from apixly_jev_harness.callbacks import provider_arity

    config = CASES[name]
    counts = {
        "provider_body_calls": 0,
        "wrapped_body_calls": 0,
        "effects": 0,
        "native_inference_attempts": 0,
        "real_network_attempts": 0,
    }
    requests, received_arities = [], []
    target = (
        (PREFIX if config["kind"] in {"partial_bridge", "partial_generic"} else "")
        + PARENT
        + ":child"
    )
    expected_digest = value_digest(PARENT, target)
    state = {"selected_digest": None}

    def option(value):
        return [Option("selected", "Synthetic authorized child", value)]

    def advertised_two(ctx, seen):
        counts["wrapped_body_calls"] += 1
        return option(target)

    def advertised_three(ctx, seen, bound):
        counts["wrapped_body_calls"] += 1
        return option(bound["parent"] + ":child")

    def advertised_prefix(prefix, ctx, seen, bound):
        counts["wrapped_body_calls"] += 1
        return option(prefix + bound["parent"] + ":child")

    def advertised_method(self, ctx, seen):
        raise AssertionError("Advertised method is introspection only")

    def called(arity):
        counts["provider_body_calls"] += 1
        received_arities.append(arity)

    kind = config["kind"]
    if kind in {"three_wraps_two", "named_variadic_bridge"}:
        if kind == "three_wraps_two":

            @functools.wraps(advertised_two)
            def provider(ctx, seen, bound):
                called(3)
                return option(bound["parent"] + ":child")
        else:

            @functools.wraps(advertised_two)
            def provider(ctx, seen, bound, *args):
                called(3 + len(args))
                return option(bound["parent"] + ":child")
    elif kind == "two_wraps_three":

        @functools.wraps(advertised_three)
        def provider(ctx, seen):
            called(2)
            return option(target)
    elif kind == "partial_bridge":

        @functools.wraps(advertised_two)
        def bridge(prefix, ctx, seen, bound):
            called(3)
            return option(prefix + bound["parent"] + ":child")

        provider = functools.partial(bridge, PREFIX)
    elif kind in {"bound_method", "callable_object"}:

        class Bridge:
            @functools.wraps(advertised_method)
            def choices(self, ctx, seen, bound):
                called(3)
                return option(bound["parent"] + ":child")

            @functools.wraps(advertised_method)
            def __call__(self, ctx, seen, bound):
                called(3)
                return option(bound["parent"] + ":child")

        provider = Bridge().choices if kind == "bound_method" else Bridge()
    elif kind in {"optional_bridge", "plain_optional"}:

        def optional(ctx, seen, bound=None):
            called(3 if bound is not None else 2)
            return option(
                bound["parent"] + ":child"
                if bound is not None
                else PRIVATE_PREFIX + "WRONG_UNBOUND"
            )

        provider = (
            functools.wraps(advertised_two)(optional) if kind == "optional_bridge" else optional
        )
    elif kind == "plain_two":

        def provider(ctx, seen):
            called(2)
            return option(target)
    elif kind == "plain_three":

        def provider(ctx, seen, bound):
            called(3)
            return option(bound["parent"] + ":child")
    elif kind == "explicit_signature":

        def provider(*args, **kwargs):
            called(len(args))
            return option(target)

        provider.__signature__ = inspect.signature(advertised_two)
    elif kind in {"generic_two", "generic_three", "partial_generic"}:
        advertised = {
            "generic_two": advertised_two,
            "generic_three": advertised_three,
            "partial_generic": advertised_prefix,
        }[kind]

        @functools.wraps(advertised)
        def forwarder(*args, **kwargs):
            called(len(args) - (1 if kind == "partial_generic" else 0))
            return advertised(*args, **kwargs)

        provider = functools.partial(forwarder, PREFIX) if kind == "partial_generic" else forwarder
    elif kind in {"plain_four", "four_wraps_two"}:

        def four(ctx, seen, bound, required):
            called(4)
            raise AssertionError("Invalid provider must never run")

        provider = functools.wraps(advertised_two)(four) if kind == "four_wraps_two" else four
    elif kind == "coroutine":

        async def provider(ctx, seen):
            called(2)
            raise AssertionError("Coroutine must never run")
    else:
        raise AssertionError("Unknown fixed fixture")

    def forbid_native(*args, **kwargs):
        counts["native_inference_attempts"] += 1
        raise AssertionError("Provider fixtures prohibit native inference")

    def forbid_network(*args, **kwargs):
        counts["real_network_attempts"] += 1
        raise AssertionError("Provider fixtures prohibit real HTTP transport")

    def decide(parts, goal, workers, spec):
        encoded = json.dumps([parts, spec], ensure_ascii=False)
        requests.append(
            {
                "selection_input_bytes": len(encoded.encode()),
                "shared_context_bytes": len(
                    json.dumps(spec.get("context", {}), ensure_ascii=False).encode()
                ),
                "private_value_exposures": encoded.count(PRIVATE_PREFIX),
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

    packet, code, error_type, admitted, chosen_arity = None, None, None, False, None
    admission_body_calls = 0
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
            try:
                parameter = Parameter(
                    "Select synthetic dependent child", provider, depends_on=("parent",)
                )
                workflow = Task(
                    observe=lambda ctx: dict(state),
                    verify=lambda ctx, seen: seen["selected_digest"] == expected_digest,
                )

                @workflow.tool(
                    "Verify one synthetic dependent binding",
                    parameters={
                        "parent": Parameter(
                            "Fixed synthetic parent",
                            [Option("parent", "Synthetic authorized parent", PARENT)],
                        ),
                        "target": parameter,
                    },
                )
                def inspect_binding(parent, target):
                    counts["effects"] += 1
                    state["selected_digest"] = value_digest(parent, target)
                    return {"selected_digest": state["selected_digest"]}

                admitted = True
                chosen_arity = provider_arity(provider)
                admission_body_calls = counts["provider_body_calls"] + counts["wrapped_body_calls"]
                packet = AgentLoop().run(
                    workflow,
                    goal="Resolve one synthetic dependent binding",
                    max_steps=1,
                    archive=archive,
                )
            except ValueError as error:
                error_type = type(error).__name__
                supplied_code = getattr(error, "code", None)
                code = (
                    supplied_code
                    if supplied_code
                    in {"provider_signature_unsupported", "synchronous_callback_required"}
                    else None
                )
            elapsed = time.perf_counter() - started
        events = (
            [json.loads(line)["event"] for line in archive.read_text(encoding="utf-8").splitlines()]
            if archive.exists()
            else []
        )
    compact = (
        {key: value for key, value in packet.items() if key != "archive"}
        if packet
        else {"admitted": admitted, "code": code, "error_type": error_type}
    )
    telemetry = packet.get("telemetry", {}) if packet else {}
    status = packet["status"] if packet else "rejected"
    expects_reject = "code" in config
    expected = {
        "status": "rejected" if expects_reject else "done",
        "admitted": not expects_reject,
        "code": config.get("code"),
        "chosen_arity": config.get("arity"),
        "effects": 0 if expects_reject else 1,
        "steps": None if expects_reject else 1,
        "scripted_decisions": 0 if expects_reject else 1,
        "usage_complete": True if expects_reject else not config.get("unknown_usage", False),
        "reported_scripted_usage": {"input_tokens": 0, "output_tokens": 0}
        if expects_reject
        else None
        if config.get("unknown_usage")
        else {"input_tokens": 7, "output_tokens": 2},
    }
    terminal_exposures = json.dumps(compact, ensure_ascii=False).count(PRIVATE_PREFIX)
    binding_correct = (
        state["selected_digest"] == expected_digest
        if not expects_reject
        else state["selected_digest"] is None
    )
    result = {
        "status": status,
        "admitted": admitted,
        "code": code,
        "error_type": packet.get("error_type") if packet else error_type,
        "chosen_arity": chosen_arity,
        "received_arities": received_arities,
        "effects": counts["effects"],
        "steps": packet.get("steps") if packet else None,
        "intent_events": events.count("intent"),
        "scripted_decisions": len(requests),
        "usage_complete": telemetry.get("usage_complete", True),
        "reported_scripted_usage": telemetry.get("usage", {"input_tokens": 0, "output_tokens": 0}),
        "admission_body_calls": admission_body_calls,
        "provider_body_calls": counts["provider_body_calls"],
        "wrapped_body_calls": counts["wrapped_body_calls"],
        "binding_correct": binding_correct,
        "expected_value_digest": expected_digest,
        "observed_value_digest": state["selected_digest"],
        "request_sizes": requests,
        "terminal_private_value_exposures": terminal_exposures,
        "native_inference_attempts": counts["native_inference_attempts"],
        "real_network_attempts": counts["real_network_attempts"],
    }
    behavior_keys = (
        "status",
        "admitted",
        "code",
        "chosen_arity",
        "effects",
        "steps",
        "scripted_decisions",
        "usage_complete",
        "reported_scripted_usage",
    )
    correct = (
        all(result[key] == expected[key] for key in behavior_keys)
        and binding_correct
        and admission_body_calls == 0
        and (not received_arities if expects_reject else received_arities == [config["arity"]])
        and counts["native_inference_attempts"] == counts["real_network_attempts"] == 0
        and terminal_exposures == 0
        and not any(request["private_value_exposures"] for request in requests)
    )
    return {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "fixture": config,
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
                for kind in ("binding_fix", "admission_fix", "compatibility")
            },
            "binding_correct": sum(row["result"]["binding_correct"] for row in group),
            "admission_body_calls": sum(row["result"]["admission_body_calls"] for row in group),
            "provider_body_calls": sum(row["result"]["provider_body_calls"] for row in group),
            "effects": sum(row["result"]["effects"] for row in group),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
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
        "admitted",
        "code",
        "chosen_arity",
        "received_arities",
        "effects",
        "steps",
        "scripted_decisions",
        "usage_complete",
        "reported_scripted_usage",
        "observed_value_digest",
        "provider_body_calls",
        "wrapped_body_calls",
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
        "mode": "offline-synthetic-provider-signature",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "compatibility_parity": compatibility_parity,
        "reproduction": "python benchmarks/provider_signature.py --output local-results/provider-signature-ab.json",
        "scope": "Eighteen fixed synthetic providers, three paired repeats with alternating arm order. Binding fixes cover explicit two/three-argument wrappers, a prefix-bound partial, methods/callable objects, optional parents and a named three-slot variadic wrapper. An actual four-slot wrapper rejects before inference; compatibility covers plain/optional signatures, explicit __signature__, transparent generic two/three/partial forwarding and existing invalid/coroutine admission. Real Engine/Task binding uses scripted tool selection and singleton parameter candidates; an independent observable digest verifier checks exact program-owned private argument values. Public evidence contains only fixed labels/counts/digests, not raw arguments. Native inference and real HTTPTransport are forbidden; actual model/network/UI calls zero if guards are never hit.",
        "negative_results": "Signature inspection adds local work; successful binding may produce more terminal bytes/effects than a baseline registration/runtime failure. Earlier admission of incompatible providers changes phase and avoids a scripted decision, without proving real fee savings. Both supported signatures and deliberately rejected providers are counted by fixture expectation, not AI semantic accuracy. Explicit __signature__ is respected as the trusted author's contract and can still misdescribe actual behavior. Inspection never proves body return types, effects or transparent forwarding. Task.tool function signature handling is unchanged. The optional-parent baseline executes a supplied wrong candidate once and independent verification remains incomplete; max_steps=1 bounds that negative case. No speed, model quality or fee gain is claimed.",
        "cost_conversion": "No tariff or savings assumed. Actual model usage is zero only when both guards remain zero; guard hits record unknown actual usage and fail the fixture. Known/unknown scripted request usage is preserved separately from actual usage. Real whole-operation perf_counter timing includes parameter/tool admission, synthetic workflow registration, scripted selection, trusted provider binding/effects, independent verification and private journal flush/fsync; excludes process/import/provider-factory setup and terminal analysis/source hashes. Loop-only frozen monotonic values stabilize request budgets without replacing whole-operation timing. Returned bytes omit local archive paths; request scalar sizes are not provider-token counts.",
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
