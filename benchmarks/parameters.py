"""Offline A/B: joint-call enumeration versus staged parameter binding."""

import argparse
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from jev_harness import AgentLoop, Parameter, Task


def trial(strategy, size):
    state = {"done": False, "chosen": None}
    task = Task(
        observe=lambda ctx: state.copy(), verify=lambda ctx, seen: seen["done"], strategy=strategy
    )

    @task.tool(
        "Select values",
        parameters={
            "a": Parameter("First value", list(range(size))),
            "b": Parameter("Second value", list(range(size))),
        },
    )
    def select(a, b):
        state.update(done=True, chosen=[a, b])

    requests = []

    def fake(parts, goal, workers, spec):
        requests.append(len(json.dumps([parts, spec]).encode()))
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, p in enumerate(parts)
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "requests": 1,
            "models": {},
        }

    with (
        tempfile.TemporaryDirectory() as directory,
        patch("jev_harness.engine.analysis.evaluate", fake),
    ):
        started = time.perf_counter()
        result = AgentLoop().run(
            task, goal="Select the first values", archive=Path(directory) / "run.jsonl"
        )
        elapsed = time.perf_counter() - started
    expected = "done" if strategy == "staged" or size * size <= 250 else "needs_review"
    return {
        "strategy": strategy,
        "size": size,
        "expected": expected,
        "status": result["status"],
        "correct": result["status"] == expected,
        "chosen": state["chosen"],
        "whole_operation_seconds": elapsed,
        "returned_context_bytes": len(json.dumps(result).encode()),
        "scripted_decision_bytes": sum(requests),
        "scripted_decisions": len(requests),
        "actual_model_usage": {"requests": 0, "models": {}, "input_tokens": 0, "output_tokens": 0},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [
        trial(strategy, size)
        for size in (2, 10, 100)
        for strategy in ("joint", "staged")
        for _ in range(3)
    ]
    report = {
        "mode": "offline-scripted",
        "rows": rows,
        "scope": "Fixed synthetic domains; no semantic inference or real model quality measurement.",
        "negative_results": "Staged selection uses more decisions than joint binding for small independent domains. Joint rejects a 100x100 Cartesian space; staged supports it.",
        "cost_conversion": "Zero actual model calls. No paid savings or tariff assumed.",
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"correct": sum(row["correct"] for row in rows), "runs": len(rows)}))
    return 0 if all(row["correct"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
