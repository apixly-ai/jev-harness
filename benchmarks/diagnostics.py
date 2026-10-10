"""Offline paired A/B: safe failure diagnostics through the real typed-batch seam."""

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
from unittest.mock import patch

from progress import snapshot

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "4f8e274bf598fbe674ee08eccccda1fa55655732"
SCENARIOS = {
    "credentials_missing": ["credentials_missing"],
    "credential_file_permissions": ["credential_file_permissions"],
    "http_401": ["http_401_body_suppressed"],
    "http_429": ["http_429_body_suppressed"],
    "unknown_provider_code": ["provider_unavailable"],
    "tool_uncertainty": ["below_min_top_probability", "below_min_margin"],
    "parameter_uncertainty": ["below_min_top_probability", "below_min_margin"],
    "model_review": ["model_review"],
    "no_match": ["no_matching_candidate"],
    "successful_selection": [],
}


def trial(scenario, archive):
    import httpx
    from jev_context.provider import Client, ProviderError

    from apixly_jev_harness import AgentLoop, Option, Parameter, Task, __version__

    private_marker = "SYNTHETIC_PRIVATE_PAYLOAD"
    requests = []
    effects = []
    state = {"done": False}
    started = time.perf_counter()
    task = Task(observe=lambda ctx: state.copy(), verify=lambda ctx, seen: seen["done"])

    @task.tool(
        "Inspect a permitted object",
        parameters={
            "target": Parameter(
                "Next required object",
                [Option("a", "First object", private_marker), Option("b", "Second object", 2)],
            )
        },
    )
    def inspect(target):
        effects.append(1)
        state["done"] = True
        return {"raw": private_marker}

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        if scenario in ("http_401", "http_429"):
            return httpx.Response(int(scenario[-3:]), text=private_marker)
        options = list(body["questions"]["target"]["criteria"])
        failed = scenario == "tool_uncertainty" or (
            scenario == "parameter_uncertainty" and len(requests) == 2
        )
        choice = {"model_review": "REVIEW", "no_match": "NONE"}.get(scenario, options[0])
        probabilities = {option: 0.0 for option in options}
        probabilities[choice] = 0.51 if failed else 1.0
        if failed:
            probabilities[options[1]] = 0.49
        return httpx.Response(
            200,
            json={
                "model": "jev-synthetic-resolved",
                "usage": {"input_tokens": 5, "output_tokens": 1},
                "answers": {
                    "target": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": 1.0,
                        "probabilities": probabilities,
                    }
                },
            },
        )

    client = Client(
        api_key="synthetic-test-key", transport=httpx.MockTransport(transport), sleep=lambda _: None
    )

    def unavailable(*args, **kwargs):
        raise ProviderError(private_marker if scenario == "unknown_provider_code" else scenario)

    with patch("apixly_jev_harness.backend.Client", lambda **kwargs: client):
        if scenario in (
            "credentials_missing",
            "credential_file_permissions",
            "unknown_provider_code",
        ):
            with patch("apixly_jev_harness.backend.provider_evaluate", unavailable):
                result = AgentLoop().run(task, goal="Inspect the required object", archive=archive)
        else:
            result = AgentLoop().run(task, goal="Inspect the required object", archive=archive)
    elapsed = time.perf_counter() - started
    expected_status = {"successful_selection": "done", "no_match": "blocked"}.get(
        scenario, "needs_review"
    )
    expected_stage = (
        "parameter_selection" if scenario == "parameter_uncertainty" else "tool_selection"
    )
    expected_diagnostic = None
    if SCENARIOS[scenario]:
        expected_diagnostic = {
            "stage": expected_stage,
            "reason_codes": SCENARIOS[scenario],
            "automatic_retry": False,
        }
        if expected_stage == "parameter_selection":
            expected_diagnostic.update(tool_id="inspect", parameter="target")
    calls = result["telemetry"]["calls"]
    unknown_expected = scenario in (
        "credentials_missing",
        "credential_file_permissions",
        "unknown_provider_code",
        "http_401",
        "http_429",
    )
    return {
        "scenario": scenario,
        "runtime_version": __version__,
        "expected_status": expected_status,
        "status": result["status"],
        "status_correct": result["status"] == expected_status,
        "expected_diagnostic": expected_diagnostic,
        "diagnostic": result.get("diagnostic"),
        "diagnostic_correct": result.get("diagnostic") == expected_diagnostic,
        "effects": len(effects),
        "effects_correct": len(effects) == int(scenario == "successful_selection"),
        "private_payload_in_terminal": private_marker in json.dumps(result),
        "reported_usage_unknown": result["telemetry"]["usage"] is None,
        "unknown_usage_preserved": not unknown_expected or result["telemetry"]["usage"] is None,
        "reported_model_resolved": [call.get("model_resolved") for call in calls],
        "reported_selection_stages": [call.get("stage") for call in calls],
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(result).encode()),
        "scripted_decisions": len(calls),
        "scripted_context_bytes": sum(call.get("context_bytes", 0) for call in calls),
        "mock_http_attempts": len(requests),
        "actual_model_usage": {"requests": 0, "models": {}, "input_tokens": 0, "output_tokens": 0},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument("--worker", choices=list(SCENARIOS), help=argparse.SUPPRESS)
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    parser.add_argument("--archive", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, args.source_dir)
        print(json.dumps(trial(args.worker, Path(args.archive))))
        return 0
    if not args.output:
        parser.error("--output is required")
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = snapshot(args.baseline_ref, root / "baseline")
        sources = {"baseline": root / "baseline/src", "candidate": ROOT / "src"}
        for scenario in SCENARIOS:
            for repeat in range(3):
                for arm in (
                    ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
                ):
                    env = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
                    raw = subprocess.check_output(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--worker",
                            scenario,
                            "--source-dir",
                            str(sources[arm]),
                            "--archive",
                            str(root / f"{scenario}-{repeat}-{arm}.jsonl"),
                        ],
                        env=env,
                        text=True,
                    )
                    row = json.loads(raw)
                    row.update(arm=arm, repeat=repeat + 1)
                    rows.append(row)
    summaries = {}
    for arm in ("baseline", "candidate"):
        group = [row for row in rows if row["arm"] == arm]
        summaries[arm] = {
            "runs": len(group),
            "status_correct": sum(row["status_correct"] for row in group),
            "diagnostic_correct": sum(row["diagnostic_correct"] for row in group),
            "effects_correct": sum(row["effects_correct"] for row in group),
            "unknown_usage_preserved": sum(row["unknown_usage_preserved"] for row in group),
            "statuses": {
                status: sum(row["status"] == status for row in group)
                for status in sorted({row["status"] for row in group})
            },
            "private_terminal_exposures": sum(row["private_payload_in_terminal"] for row in group),
            "median_whole_operation_seconds": statistics.median(
                row["whole_operation_seconds"] for row in group
            ),
            "returned_context_bytes": sum(row["returned_context_bytes"] for row in group),
            "scripted_decisions": sum(row["scripted_decisions"] for row in group),
            "scripted_context_bytes": sum(row["scripted_context_bytes"] for row in group),
            "mock_http_attempts": sum(row["mock_http_attempts"] for row in group),
            "actual_model_usage": {
                "requests": 0,
                "models": {},
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }
    report = {
        "mode": "offline-http-mock",
        "baseline_commit": baseline,
        "candidate": "working tree at invocation; published with its source commit",
        "candidate_source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "src/apixly_jev_harness").glob("*.py"))
        },
        "python_version": sys.version.split()[0],
        "reproduction": "python benchmarks/diagnostics.py --output local-results/decision-diagnostics-ab.json",
        "scope": "Ten fixed synthetic scenarios, three paired repeats through the actual pinned SDK/typed-batch with HTTPMock or injected sanitized ProviderError. Mock model identity and token usage are synthetic, not real inference. Expected diagnostic checks are protocol checks, not AI recovery or semantic accuracy measurements.",
        "negative_results": "Added diagnostics and stage tags increase terminal bytes. Unknown provider codes remain generic. Diagnostic coverage is actual selection calls; static candidate/policy/execution failures keep existing reasons. No live AI recovery trial.",
        "cost_conversion": "Zero outbound model requests and no paid savings claim. HTTP retries are simulated; the pinned provider already retries 429/503/529 up to three network attempts, unchanged here. Timings include task/client construction, loop, callbacks and journal writes; exclude interpreter/import/snapshot setup.",
        "summary": summaries,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summaries))
    return (
        0
        if all(
            row["status_correct"]
            and row["diagnostic_correct"]
            and row["effects_correct"]
            and row["unknown_usage_preserved"]
            and not row["private_payload_in_terminal"]
            for row in rows
            if row["arm"] == "candidate"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
