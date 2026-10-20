import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def pair(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "benchmarks"))
    return importlib.import_module("model_pair")


def scripted_provider(seen):
    expected = {
        case["expected_id"]
        for case in json.loads(
            Path(
                Path(__file__).resolve().parents[1] / "benchmarks/tool-choice-cases.json"
            ).read_text()
        )["cases"]
    }

    def evaluate(body, client, cache=None):
        # Offline stand-in for the provider: no network, credential or billable usage.
        seen.append(body["model"])
        criteria = body["questions"]["target"]["criteria"]
        offered = {k: v for k, v in criteria.items() if isinstance(v, dict)}
        choice = next(
            (k for k, v in offered.items() if v.get("properties", {}).get("id") in expected),
            next((k for k, v in offered.items() if v.get("text") == "2"), "c0"),
        )
        return {
            "ok": True,
            "model": body["model"],
            "answers": {
                "target": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 1.0,
                    "probabilities": {k: float(k == choice) for k in criteria},
                }
            },
            "usage": {"input_tokens": 1, "output_tokens": 0},
            "usage_complete": True,
        }

    return evaluate


def test_arms_differ_only_in_requested_model_and_alternate_order(pair, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr("apixly_jev_harness.backend.provider_evaluate", scripted_provider(seen))
    output = tmp_path / "pair.json"
    assert pair.main(["--live", "--output", str(output), "--repeats", "1"]) == 0
    report = json.loads(output.read_text())
    assert report["status"] == "completed" and len(report["rows"]) == report["planned_probes"]
    assert set(seen) == set(pair.MODELS)
    firsts = [row["model_requested"] for row in report["rows"][0:26:2]]
    assert len(set(firsts)) == 2  # Neither model always goes first.
    for model in pair.MODELS:
        summary = report["summary"][model]
        assert summary["tool_choice"]["runs"] == 12
        assert summary["tool_choice"]["admitted_expected"] == 12
        assert summary["counter"] == {"runs": 1, "complete": 1, "fewest_calls": 1, "decisions": 3}
        assert summary["resolved_models"] == [model]
        assert summary["usage_complete"] is True


def test_moving_alias_is_rejected_before_the_receipt_is_reserved(pair, tmp_path):
    output = tmp_path / "pair.json"
    with pytest.raises(ValueError, match="versioned_jev_model_required"):
        pair.main(["--live", "--output", str(output), "--models", "jev-1.13.0", "jev-preview"])
    assert not output.exists()
