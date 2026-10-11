import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def benchmark(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("toolkit_protocol")


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "case",
    [
        "ambiguous_legal_tool",
        "exploratory_target",
        "matched_target_low",
        "matched_target_high",
        "explicit_review_tool",
        "explicit_review_parameter",
        "child_match_low",
        "child_after_label",
        "unknown_reference",
        "foreign_link",
        "tail_read",
        "twelve_records",
        "unknown_http_usage",
        "direct_then_delegate",
        "delegate_then_direct",
    ],
)
def test_frozen_mock_cases_meet_declared_outcomes_without_real_models(benchmark, arm, case):
    row = benchmark.trial(case, arm)
    assert row["expected_outcome_met"] is True
    assert row["real_network_attempts"] == 0
    assert row["actual_model_usage"] == {
        "requests": 0,
        "models": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "usage_complete": True,
    }
    assert row["whole_operation_seconds"] >= 0


def test_parameter_policy_and_request_scope_are_separate_from_semantic_quality(benchmark):
    old = benchmark.trial("exploratory_target", "baseline")
    new = benchmark.trial("exploratory_target", "candidate")
    assert old["status"] == "needs_review" and old["effects"] == 0
    assert new["status"] == "done" and new["effects"] == 1
    assert old["selection_policies"][-1]["min_top_probability"] == 0.55
    assert old["selection_policies"][-1]["min_margin"] == 0.10
    assert new["selection_policies"][-1]["min_top_probability"] == 0.30
    assert new["selection_policies"][-1]["min_margin"] == 0
    assert old["request_protocol"][-1]["exploration_criterion"] is False
    assert new["request_protocol"][-1]["exploration_criterion"] is True
    assert new["request_protocol"][-1]["whole_goal_removed_from_parameter_task"] is True


def test_match_policy_and_explicit_review_stay_fail_closed(benchmark):
    for arm in ("baseline", "candidate"):
        strict = benchmark.trial("matched_target_low", arm)
        assert strict["selection_policies"][-1]["min_top_probability"] == 0.55
        assert strict["selection_policies"][-1]["min_margin"] == 0.10
        assert strict["status"] == "needs_review" and strict["effects"] == 0
        for case in ("explicit_review_tool", "explicit_review_parameter"):
            row = benchmark.trial(case, arm)
            assert row["status"] == "needs_review" and row["effects"] == 0


def test_child_provider_only_runs_after_label_and_uses_strict_matching(benchmark):
    row = benchmark.trial("child_after_label", "candidate")
    assert row["provider_bound_labels"] and set(row["provider_bound_labels"]) == {"proof"}
    assert [x["parameter"] for x in row["request_protocol"]] == [None, "label", "passage"]
    assert row["selection_policies"][-1]["min_top_probability"] == 0.55
    assert row["selection_policies"][-1]["min_margin"] == 0.10
    low = benchmark.trial("child_match_low", "candidate")
    assert low["status"] == "needs_review" and low["effects"] == 0


def test_reference_projection_and_tail_are_observable_but_verification_sees_originals(benchmark):
    old = benchmark.trial("twelve_records", "baseline")
    new = benchmark.trial("twelve_records", "candidate")
    assert old["observation_characters"] > 15000 and old["status"] == "needs_review"
    assert new["observation_characters"] < 15000 and new["status"] == "done"
    assert new["verifier_record_counts"] == [12]
    assert new["artifact_record_count"] == 12
    assert benchmark.trial("tail_read", "baseline")["tail_visible_after_read"] is False
    assert benchmark.trial("tail_read", "candidate")["tail_visible_after_read"] is True


def test_unknown_mock_usage_and_both_route_switch_guards_are_preserved(benchmark):
    for arm in ("baseline", "candidate"):
        failed = benchmark.trial("unknown_http_usage", arm)
        assert failed["scripted_usage_complete"] is False and failed["scripted_usage"] is None
        for case in ("direct_then_delegate", "delegate_then_direct"):
            row = benchmark.trial(case, arm)
            assert row["status"] == "rejected" and row["effects"] == 1
            assert row["effects_after_rejected_switch"] == row["effects_before_rejected_switch"]


def test_report_has_control_scope_real_zero_usage_and_retains_negative_results(benchmark):
    report = benchmark.run_benchmark(repeats=1)
    assert report["mode"] == "offline-policy-projection-control"
    assert "not a published v0.1.17 source" in report["baseline_scope"]
    assert len(report["rows"]) == 30
    assert all(row["expected_outcome_met"] for row in report["rows"])
    assert report["semantic_accuracy_measured"] is False
    assert report["candidate_source_sha256"] == report["baseline_source_sha256"]
    assert report["summary"]["baseline"]["runs"] == 15
    assert report["summary"]["candidate"]["runs"] == 15
    assert report["summary"]["candidate"]["actual_model_usage"]["requests"] == 0
    assert "additional" in report["negative_results"].lower()
    assert "unknown" in report["negative_results"].lower()
    assert "source" in report["reproduction"]
    assert "SYNTHETIC_TAIL_FACT" not in json.dumps(report)


def test_unexpected_nonmock_transport_does_not_claim_zero_actual_usage(benchmark, monkeypatch):
    import httpx

    original = benchmark.Client
    monkeypatch.setattr(
        benchmark,
        "Client",
        lambda **kwargs: original(api_key="synthetic-key", transport=httpx.HTTPTransport()),
    )
    row = benchmark.trial("matched_target_high", "candidate")
    assert row["real_network_attempts"] > 0
    assert row["expected_outcome_met"] is False
    assert row["actual_model_usage"]["requests"] is None
    assert row["actual_model_usage"]["usage_complete"] is False
