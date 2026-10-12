"""Offline source-paired delegation lifecycle regressions, never semantic model calls."""

import importlib
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def lifecycle(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("delegation_lifecycle")


def candidate(lifecycle, case):
    return lifecycle.worker(case, lifecycle.ROOT / "src")


def test_lazy_first_delegation_returns_independently_checked_saved_receipt(lifecycle):
    row = candidate(lifecycle, "lazy_artifact_receipt")
    assert row["result"]["status"] == "done"
    assert row["result"]["artifact_returned"] is True
    assert row["result"]["artifact_independently_verified"] is True
    assert row["result"]["factory_calls"] == 1
    assert row["result"]["artifact_writes"] == 1
    assert row["correct"] is True


def test_followup_observation_uses_actual_delegate_results_context(lifecycle):
    row = candidate(lifecycle, "contextual_observation")
    assert row["result"]["status"] == "done"
    assert row["result"]["followup_results"] == 1
    assert row["result"]["followup_complete"] is True
    assert row["result"]["followup_context_step"] == 1


def test_joint_lazy_factory_is_stopped_before_scripted_decision_or_effect(lifecycle):
    row = candidate(lifecycle, "lazy_joint_admission")
    assert row["result"]["status"] == "failed"
    assert row["result"]["effects"] == 0
    assert row["result"]["scripted_decisions"] == 0
    assert row["result"]["factory_calls"] == 1
    assert row["actual_model_usage"]["requests"] == 0


def test_required_labels_are_visible_while_saved_partial_report_remains_incomplete(lifecycle):
    row = candidate(lifecycle, "completion_contract")
    before, after = row["result"]["completion_before"], row["result"]["completion_after"]
    assert before["required_labels"] == ["cause", "proof"]
    assert before["missing_labels"] == ["cause", "proof"]
    assert before["report_matches_records"] is False
    assert after["missing_labels"] == ["proof"]
    assert after["report_matches_records"] is True
    assert row["result"]["followup_complete"] is False
    assert row["result"]["artifact_independently_verified"] is True


def test_plain_staged_task_preserves_goal_facts_messages_and_artifact(lifecycle):
    row = candidate(lifecycle, "plain_staged_compatibility")
    assert row["result"]["status"] == "done"
    assert row["result"]["forwarded_context_correct"] is True
    assert row["result"]["artifact_returned"] is True
    assert row["result"]["artifact_independently_verified"] is True


def test_unknown_scripted_usage_and_review_remain_unknown_not_zero(lifecycle):
    row = candidate(lifecycle, "review_unknown_usage")
    assert row["result"]["status"] == "needs_review"
    assert row["result"]["scripted_usage_complete"] is False
    assert row["result"]["reported_scripted_usage"] is None
    assert row["result"]["known_scripted_usage"] == {"input_tokens": 7, "output_tokens": 2}
    assert row["result"]["unknown_scripted_usage_calls"] == 1
    assert row["result"]["effects"] == 1
    assert row["actual_model_usage"]["requests"] == 0


def test_exact_baseline_snapshot_contains_the_entire_package(lifecycle, tmp_path):
    commit = lifecycle.snapshot(lifecycle.BASELINE, tmp_path / "baseline")
    assert commit == "79d383dcf9ffedc535dc5182bfe5a17147f7e950"
    source = tmp_path / "baseline/src"
    hashes = lifecycle.source_hashes(source)
    assert "src/apixly_jev_harness/toolkit.py" in hashes
    assert "src/apixly_jev_harness/evidence.py" in hashes
    assert "src/apixly_jev_harness/mcp.py" in hashes
    assert len(hashes) > 15
    assert '__version__ = "0.2.0"' in (source / "apixly_jev_harness/__init__.py").read_text()


@pytest.mark.skipif(
    os.name == "nt",
    reason="historical baseline 79d383d predates Windows owner-only report support",
)
def test_paired_report_retains_baseline_failures_and_compatibility(lifecycle, tmp_path):
    output = tmp_path / "report.json"
    assert lifecycle.main(["--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert len(report["rows"]) == 36
    assert report["baseline_commit"] == lifecycle.BASELINE
    assert report["summary"]["candidate"]["correct"] == 18
    assert report["summary"]["baseline"]["correct"] == 6
    assert report["compatibility_parity"] is True
    assert report["summary"]["candidate"]["unknown_scripted_usage_rows"] == 3
    assert report["summary"]["baseline"]["unknown_scripted_usage_rows"] == 3
    assert all(row["actual_model_usage"]["requests"] == 0 for row in report["rows"])
    baseline_joint = [
        x for x in report["rows"] if x["arm"] == "baseline" and x["case"] == "lazy_joint_admission"
    ]
    assert all(x["result"]["effects"] == 1 for x in baseline_joint)
    assert report["negative_results"] and report["candidate_source_sha256"]


def test_existing_output_is_never_replaced_or_used_for_new_trials(lifecycle, tmp_path, monkeypatch):
    output = tmp_path / "owner.json"
    output.write_text("owner retained evidence", encoding="utf-8", newline="\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("Existing output must fail before subprocess trials")

    monkeypatch.setattr(lifecycle, "worker", forbidden)
    with pytest.raises(FileExistsError):
        lifecycle.main(["--output", str(output)])
    assert output.read_text() == "owner retained evidence"
