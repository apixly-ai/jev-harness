import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def benchmark(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "benchmarks"))
    return importlib.import_module("tool_choice")


def test_interrupted_selection_usage_is_unknown_not_zero(benchmark, monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise TimeoutError("Synthetic interrupted inference with uncertain attempts")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", unavailable)
    case = json.loads(benchmark.CASES.read_text())["cases"][0]
    # Exercise live reporting using an offline injected failure; no network or credential use.
    row = benchmark.trial(case, False, tmp_path / "run.jsonl", live=True)
    assert row["status"] == "failed"
    assert row["actual_model_usage"]["network_attempts"] is None
    row["arm"] = "candidate"
    summary = benchmark.summarize([row])["candidate"]
    assert summary["actual_network_attempts"] is None
    assert summary["unknown_network_attempt_rows"] == 1
    assert summary["known_network_attempts"] == 0


def test_runtime_failure_stops_probe_but_quality_review_can_continue(benchmark):
    assert benchmark.should_stop(
        {"status": "failed", "provider_failure_codes": [], "intent_or_effect_events": 0}
    )
    assert benchmark.should_stop(
        {
            "status": "execution_uncertain",
            "provider_failure_codes": [],
            "intent_or_effect_events": 1,
        }
    )
    assert not benchmark.should_stop(
        {"status": "needs_review", "provider_failure_codes": [], "intent_or_effect_events": 0}
    )
    assert benchmark.should_stop(
        {
            "status": "needs_review",
            "provider_failure_codes": ["credentials_missing"],
            "intent_or_effect_events": 0,
        }
    )
