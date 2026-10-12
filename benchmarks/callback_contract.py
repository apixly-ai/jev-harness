"""Offline paired callback admission and provider binding against v0.1.5."""

import argparse
import functools
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "17fa46f76267da428f96f4ca4240a9a07de14b9a"
ZERO_USAGE = {"requests": 0, "models": {}, "input_tokens": 0, "output_tokens": 0}


def rejected(role, kind=None, code="synchronous_callback_required"):
    return {
        "status": "rejected",
        "contract_error": {"code": code, "callback": role, **({"kind": kind} if kind else {})},
        "admission_body_invocations": 0,
        "body_invocations": 0,
        "effects": 0,
    }


CASES = {
    **{
        f"task_async_{role}": rejected(role, "coroutine")
        for role in ("observe", "verify", "authorize")
    },
    **{
        f"tool_{kind}": rejected("execute", kind)
        for kind in ("coroutine", "generator", "async_generator")
    },
    **{
        f"metadata_async_{role}": rejected(role, "coroutine")
        for role in ("available", "result_context")
    },
    **{
        f"provider_{kind}": rejected("choices", kind)
        for kind in ("coroutine", "generator", "async_generator")
    },
    **{
        f"partial_provider_{kind}": rejected("choices", kind)
        for kind in ("coroutine", "generator", "async_generator")
    },
    "provider_required_keyword": rejected("choices", code="provider_signature_unsupported"),
    "provider_two_arguments": {
        "status": "bound",
        "value": "synthetic",
        "provider_calls": 2,
        "admission_body_invocations": 0,
        "effects": 1,
    },
    "provider_three_arguments": {
        "status": "bound",
        "value": "A-child",
        "provider_calls": 1,
        "admission_body_invocations": 0,
        "effects": 1,
    },
    "provider_three_optional_keyword": {
        "status": "bound",
        "value": "A-child",
        "provider_calls": 1,
        "admission_body_invocations": 0,
        "effects": 1,
    },
    "provider_callable_with_lock": {
        "status": "bound",
        "value": "synthetic",
        "provider_calls": 2,
        "provider_identity_preserved": True,
        "admission_body_invocations": 0,
        "effects": 1,
    },
    "provider_partial_with_lock": {
        "status": "bound",
        "value": "synthetic",
        "provider_calls": 2,
        "provider_identity_preserved": True,
        "admission_body_invocations": 0,
        "effects": 1,
    },
    "static_snapshot": {
        "status": "bound",
        "value": {"value": "original"},
        "admission_body_invocations": 0,
        "effects": 1,
    },
    "workflow_generator_candidates": {
        "status": "done",
        "admission_body_invocations": 0,
        "effects": 1,
        "scripted_decisions": 1,
    },
    "sync_wraps_async_bridge": {
        "status": "observed",
        "value": {},
        "admission_body_invocations": 0,
        "effects": 0,
    },
    "ambiguous_provider_prefers_three": {
        "status": "bound",
        "value": "A",
        "provider_calls": 1,
        "admission_body_invocations": 0,
        "effects": 1,
    },
}


def source_hashes(source_dir):
    return {
        "src/apixly_jev_harness/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((Path(source_dir) / "apixly_jev_harness").glob("*.py"))
    }


def contract_projection(error):
    packet = {}
    code, role, kind = (getattr(error, key, None) for key in ("code", "callback", "kind"))
    if code in ("synchronous_callback_required", "provider_signature_unsupported"):
        packet["code"] = code
    if role in (
        "observe",
        "verify",
        "authorize",
        "execute",
        "available",
        "result_context",
        "choices",
    ):
        packet["callback"] = role
    if kind in ("coroutine", "generator", "async_generator"):
        packet["kind"] = kind
    return packet or None


def trial(name, source_dir):
    from apixly_jev_harness import Action, AgentLoop, Parameter, Task, Workflow, __version__
    from apixly_jev_harness import __file__ as runtime_file

    counters = {"body_invocations": 0, "provider_calls": 0, "effects": 0, "native_attempts": 0}
    requests = []
    packet = {"status": "accepted", "admission_body_invocations": 0}

    def body():
        counters["body_invocations"] += 1

    async def deferred_async(*args):
        body()
        raise AssertionError("Deferred synthetic callback must not be invoked")

    def deferred_generator(*args):
        body()
        raise AssertionError("Deferred synthetic callback must not be invoked")
        yield None

    async def deferred_async_generator(*args):
        body()
        raise AssertionError("Deferred synthetic callback must not be invoked")
        yield None

    async def async_effect():
        body()
        raise AssertionError("Deferred synthetic callback must not be invoked")

    def generator_effect():
        body()
        raise AssertionError("Deferred synthetic callback must not be invoked")
        yield None

    async def async_generator_effect():
        body()
        raise AssertionError("Deferred synthetic callback must not be invoked")
        yield None

    class AsyncProvider:
        async def __call__(self, prefix, ctx, state):
            body()
            raise AssertionError("Deferred synthetic provider must not be invoked")

    class GeneratorProvider:
        def __call__(self, prefix, ctx, state):
            body()
            raise AssertionError("Deferred synthetic provider must not be invoked")
            yield prefix

    class AsyncGeneratorProvider:
        async def __call__(self, prefix, ctx, state):
            body()
            raise AssertionError("Deferred synthetic provider must not be invoked")
            yield prefix

    def forbidden(*args, **kwargs):
        counters["native_attempts"] += 1
        raise AssertionError("Offline benchmark prohibits native inference")

    def decide(parts, goal, workers, spec):
        requests.append(len(json.dumps([parts, spec], sort_keys=True).encode()))
        return {
            item["id"]: {"status": "OK", "decision": "MATCH" if index == 0 else "EXCLUDE"}
            for index, item in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "requests": 1,
            "models": {},
        }

    def task():
        return Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    def invoke_provider(provider, *, dependent=False, identity=False):
        workflow = task()
        parameters = {
            "target": Parameter(
                "Synthetic choices", provider, depends_on=("parent",) if dependent else ()
            )
        }
        if dependent:
            parameters = {"parent": ["A"], **parameters}

            @workflow.tool("Bind synthetic dependent value", parameters=parameters)
            def inspect(parent, target):
                counters["effects"] += 1
                return target
        else:

            @workflow.tool("Bind synthetic value", parameters=parameters)
            def inspect(target):
                counters["effects"] += 1
                return target

        packet["admission_body_invocations"] = counters["body_invocations"]
        if identity:
            packet["provider_identity_preserved"] = (
                workflow._tools["inspect"]["parameters"]["target"].choices is provider
            )
        actions = workflow.candidates(None, {})
        action = workflow.bind(None, {}, actions[0], forbidden)
        packet.update(status="bound", value=workflow.execute(None, action))

    started = time.perf_counter()
    with (
        patch("apixly_jev_harness.backend.native_run", forbidden),
        patch("apixly_jev_harness.backend.provider_evaluate", forbidden),
        patch("apixly_jev_harness.engine.analysis.evaluate", decide),
    ):
        try:
            if name.startswith("task_async_"):
                role = name.removeprefix("task_async_")
                Task(
                    **{
                        "observe": lambda ctx: {},
                        "verify": lambda ctx, seen: False,
                        role: deferred_async,
                    }
                )
            elif name.startswith("tool_"):
                callback = {
                    "coroutine": async_effect,
                    "generator": generator_effect,
                    "async_generator": async_generator_effect,
                }[name.removeprefix("tool_")]
                task().tool("Synthetic deferred effect", name="effect")(callback)
            elif name.startswith("metadata_async_"):
                role = name.removeprefix("metadata_async_")
                task().tool("Synthetic metadata", **{role: deferred_async})(lambda: None)
            elif name.startswith("partial_provider_"):
                provider = {
                    "coroutine": AsyncProvider,
                    "generator": GeneratorProvider,
                    "async_generator": AsyncGeneratorProvider,
                }[name.removeprefix("partial_provider_")]()
                Parameter(
                    "Synthetic choices", functools.partial(functools.partial(provider, "fixed"))
                )
            elif name in {"provider_coroutine", "provider_generator", "provider_async_generator"}:
                provider = {
                    "coroutine": deferred_async,
                    "generator": deferred_generator,
                    "async_generator": deferred_async_generator,
                }[name.removeprefix("provider_")]
                Parameter("Synthetic choices", provider)
            elif name == "provider_required_keyword":

                def provider(ctx, state, *, required):
                    body()
                    raise AssertionError("Unsupported synthetic provider must not be invoked")

                Parameter("Synthetic choices", provider)
            elif name == "provider_two_arguments":

                def provider(ctx, state):
                    body()
                    counters["provider_calls"] += 1
                    return ["synthetic"]

                invoke_provider(provider)
            elif name in {"provider_three_arguments", "provider_three_optional_keyword"}:

                def provider_three(ctx, state, bound):
                    body()
                    counters["provider_calls"] += 1
                    return [bound["parent"] + "-child"]

                def provider_keyword(ctx, state, bound, *, suffix="child"):
                    body()
                    counters["provider_calls"] += 1
                    return [bound["parent"] + "-" + suffix]

                invoke_provider(
                    provider_three if name == "provider_three_arguments" else provider_keyword,
                    dependent=True,
                )
            elif name in {"provider_callable_with_lock", "provider_partial_with_lock"}:

                class LockedProvider:
                    def __init__(self):
                        self.lock = threading.Lock()

                    def __call__(self, ctx, state):
                        with self.lock:
                            body()
                            counters["provider_calls"] += 1
                            return ["synthetic"]

                class PrefixProvider(LockedProvider):
                    def __call__(self, prefix, ctx, state):
                        with self.lock:
                            body()
                            counters["provider_calls"] += 1
                            return [prefix]

                provider = (
                    LockedProvider()
                    if name == "provider_callable_with_lock"
                    else functools.partial(PrefixProvider(), "synthetic")
                )
                invoke_provider(provider, identity=True)
            elif name == "static_snapshot":
                values = [{"value": "original"}]
                workflow = task()

                @workflow.tool(
                    "Snapshot synthetic values",
                    parameters={"target": Parameter("Static choice", values)},
                )
                def inspect(target):
                    counters["effects"] += 1
                    return target

                values[0]["value"] = "changed"
                actions = workflow.candidates(None, {})
                action = workflow.bind(None, {}, actions[0], forbidden)
                packet.update(status="bound", value=workflow.execute(None, action))
            elif name == "workflow_generator_candidates":

                class GeneratorCandidates(Workflow):
                    def observe(self, ctx):
                        body()
                        return {"done": counters["effects"] == 1}

                    def verify(self, ctx, state):
                        body()
                        return state["done"]

                    def candidates(self, ctx, state):
                        body()
                        yield Action("inspect", "Inspect synthetic state")

                    def execute(self, ctx, action):
                        body()
                        counters["effects"] += 1

                with tempfile.TemporaryDirectory() as directory:
                    result = AgentLoop().run(
                        GeneratorCandidates(),
                        goal="Inspect one synthetic state",
                        archive=Path(directory) / "run.jsonl",
                        max_steps=2,
                    )
                    packet["status"] = result["status"]
                    packet["runtime_terminal_bytes"] = len(
                        json.dumps(
                            {key: value for key, value in result.items() if key != "archive"}
                        ).encode()
                    )
                    packet["reported_scripted_usage_complete"] = result["telemetry"][
                        "usage_complete"
                    ]
            elif name == "sync_wraps_async_bridge":

                @functools.wraps(deferred_async)
                def bridge(ctx):
                    body()
                    return {}

                workflow = Task(observe=bridge, verify=lambda ctx, state: True)
                packet["admission_body_invocations"] = counters["body_invocations"]
                packet.update(status="observed", value=workflow.observe(None))
            elif name == "ambiguous_provider_prefers_three":

                def provider(ctx, state, bound=None, *, suffix="synthetic"):
                    body()
                    counters["provider_calls"] += 1
                    return [bound["parent"] if bound is not None else "NO_BOUND"]

                invoke_provider(provider, dependent=True)
            else:
                raise AssertionError("Unknown fixed fixture")
        except Exception as error:
            packet.update(status="rejected", error_type=type(error).__name__)
            projection = contract_projection(error)
            if projection:
                packet["contract_error"] = projection
    elapsed = time.perf_counter() - started
    packet.update(**counters, scripted_decisions=len(requests))
    expected = CASES[name]
    correct = (
        all(packet.get(key) == value for key, value in expected.items())
        and counters["native_attempts"] == 0
    )
    result = {
        "case": name,
        "runtime_version": __version__,
        "runtime_loaded_from_requested_source": Path(runtime_file)
        .resolve()
        .is_relative_to(Path(source_dir).resolve()),
        "source_sha256": source_hashes(source_dir),
        "expected": expected,
        "result": packet,
        "correct": correct,
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(packet, sort_keys=True).encode()),
        "scripted_decision_bytes": sum(requests),
        "actual_model_usage": ZERO_USAGE,
    }
    return result


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
        summaries[arm] = {
            "runs": len(group),
            "correct": sum(row["correct"] for row in group),
            "statuses": {
                status: sum(row["result"]["status"] == status for row in group)
                for status in sorted({row["result"]["status"] for row in group})
            },
            "admission_body_invocations": sum(
                row["result"]["admission_body_invocations"] for row in group
            ),
            "native_inference_attempts": sum(row["result"]["native_attempts"] for row in group),
            "scripted_decisions": sum(row["result"]["scripted_decisions"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "scripted_decision_bytes": sum(row["scripted_decision_bytes"] for row in group),
            "actual_model_usage": ZERO_USAGE,
        }
    report = {
        "mode": "offline-synthetic-callback-contract",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "baseline_source_sha256": hashes["baseline"],
        "candidate_source_sha256": hashes["candidate"],
        "runner_sha256": runner_hash,
        "python_version": sys.version.split()[0],
        "cases": CASES,
        "reproduction": "python benchmarks/callback_contract.py --output local-results/callback-contract-ab.json",
        "scope": "Twenty-four fixed synthetic fixtures, three paired repeats with alternating arm order. Deferred baseline callbacks are only constructed/registered, never invoked or materialized. Positive fixtures bind singleton values and one generator Workflow runs a scripted decision. Native inference entrypoints are forbidden in each worker; actual model/UI/network calls are zero. This measures Python callback admission and provider binding, not semantic accuracy, async execution or a sandbox.",
        "negative_results": "Introspection and fixed contract metadata add local time/context overhead. Signature bindability does not prove callback return types or bound I/O. When both two and three positional arguments bind, three is preferred; optional/variadic providers previously called with two may now receive bound parents and need an explicit two-argument wrapper. Dynamic providers retain their callable identity and resource lifetime; static candidates retain a snapshot. No speed, accuracy or fee gain is claimed.",
        "cost_conversion": "Zero actual model calls; no tariff or savings assumed. Whole-operation timing includes callback fixture construction, admission, successful singleton binding/execution and one permitted private synthetic journal where applicable; excludes process/import/snapshot setup. Scripted telemetry is separated from actual model usage. Returned context bytes measure compact fixture results with runtime archive paths excluded.",
        "summary": summaries,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summaries))
    return 0 if all(row["correct"] for row in rows if row["arm"] == "candidate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
