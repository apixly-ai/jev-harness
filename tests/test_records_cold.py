"""Large-volume triage eval: hidden-label check, neutral contract and bounded Jev route."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def records(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("records_cold")


@pytest.fixture
def triage(records):
    return importlib.import_module("records_triage")


def session_for(records, tmp_path, optional=True):
    return records.RecordsSession(tmp_path / "s", tmp_path / "runtime", optional=optional)


def write_report(session, value):
    (session.work / "report.json").write_text(json.dumps(value), encoding="utf-8")


def test_generator_is_deterministic_varied_and_labels_stay_private(triage, tmp_path):
    first, labels = triage.generate(400, seed=7)
    again, _ = triage.generate(400, seed=7)
    assert first == again and len({r["id"] for r in first}) == 400
    assert 0.15 < sum(labels.values()) / 400 < 0.30
    assert all(set(r) == {"id", "service", "text"} for r in first)
    path = tmp_path / "records.jsonl"
    triage.write_corpus(path, first)
    assert "true" not in path.read_text(encoding="utf-8").lower().split('"text"')[0]
    words = {"staging", "resolved", "drill", "internal", "maintenance"}
    positives = [r["text"].lower() for r in first if labels[r["id"]]]
    assert not any(any(w in text for w in words) for text in positives)
    negatives = [r["text"].lower() for r in first if not labels[r["id"]]]
    assert sum("fail" in t or "error" in t or "timing out" in t for t in negatives) > 40


def test_check_scores_saved_report_without_revealing_labels(records, tmp_path):
    session = session_for(records, tmp_path)
    assert session.check_goal()["problems"] == ["not_saved"]
    truth = sorted(k for k, v in session.labels.items() if v)
    write_report(session, {"ids": truth})
    public = session.check_goal()
    assert public == {
        "passed": True,
        "saved": True,
        "submitted": len(truth),
        "unknown_ids": 0,
        "problems": [],
        "check": "independent_hidden_label_score",
    }
    write_report(session, {"ids": truth[: len(truth) // 2] + ["evt-unknown"]})
    public = session.check_goal()
    assert public["passed"] is False and public["problems"] == ["accuracy_below_threshold"]
    assert "precision" not in json.dumps(public) and truth[0] not in json.dumps(public)
    assert session.private_score()["recall"] < 0.6
    write_report(session, {"ids": "all"})
    assert session.check_goal()["problems"] == ["invalid_report"]
    live = json.loads((session.directory / "check-live.json").read_text(encoding="utf-8"))
    assert live["checks"] == 4 and live["private"]["problem"] == "invalid_report"


def test_contract_is_neutral_and_only_the_optional_arm_can_run_scripts(records):
    prompt = records.actor_prompt()
    assert "0.95" in prompt and "/work/report.json" in prompt
    assert "jev" not in prompt.lower() and "prefer" not in prompt.lower()
    native = {t["name"] for t in records.tools(False)}
    optional = {t["name"]: t for t in records.tools(True)}
    assert native == {"shell", "check_goal"} and set(optional) == native | {"run_script"}
    description = optional["run_script"]["description"]
    assert "Up to 3 executions" in description and "150 provider requests" in description
    assert "prefer" not in description.lower() and "cheap" not in description.lower()
    assert "init-task /work/task.py --toolkit records" in records.API_NOTES


def test_run_script_preflight_and_budget_gates_run_no_container(records, tmp_path):
    session = session_for(records, tmp_path)
    packet = session.run_script("missing.py")
    assert packet["phase"] == "script_preflight" and packet["execution_attempted"] is False
    assert session.executions == 0
    (session.work / "task.py").write_text("workflow = 1\n", encoding="utf-8")
    changed = session.run_script("task.py", inputs={"output": "/tmp/x.json"})
    assert changed["error"] == "bound_inputs_changed" and session.executions == 0
    session.executions = 3
    with pytest.raises(ValueError, match="unavailable_or_exhausted"):
        session.run_script("task.py")
    session.executions, session.provider_requests_used = 1, 149
    with pytest.raises(ValueError, match="provider_budget_exhausted"):
        session.run_script("task.py")
    native = session_for(records, tmp_path / "n", optional=False)
    with pytest.raises(ValueError, match="unavailable"):
        native.run_script("task.py")


def test_pair_serve_paths_are_absolute_and_live_only_for_optional(records, monkeypatch, tmp_path):
    pair = importlib.import_module("records_pair")
    monkeypatch.chdir(tmp_path)
    native = pair.serve_arguments("n", "native", wheel="w.whl", credential="key")
    optional = pair.serve_arguments("o", "optional", wheel="w.whl", credential="key")
    assert "--live" not in native and optional[-3:-1] == ["--live", "--credential-file"]
    for arguments in (native, optional):
        for flag in ("--directory", "--wheel"):
            assert Path(arguments[arguments.index(flag) + 1]).is_absolute()


def test_pair_final_score_recomputes_from_deterministic_labels(records, tmp_path):
    pair = importlib.import_module("records_pair")
    triage = importlib.import_module("records_triage")
    case = records.CASES["template"]
    assert pair.final_score(tmp_path, case) == {"passed": False, "problem": "not_saved"}
    _, labels = triage.generate(case["count"], seed=case["seed"])
    (tmp_path / "work").mkdir()
    truth = [k for k, v in labels.items() if v]
    (tmp_path / "work" / "report.json").write_text(json.dumps({"ids": truth}), encoding="utf-8")
    assert pair.final_score(tmp_path, case)["passed"] is True


def test_natural_fixture_is_frozen_labelled_and_states_the_correction_rule(records, tmp_path):
    case = records.CASES["natural"]
    corpus, labels = records.load_corpus(case)
    assert len(corpus) == 1000 and 0.2 < sum(labels.values()) / 1000 < 0.4
    assert all(set(row) == {"id", "service", "text"} for row in corpus)
    assert "latest statement decides" in records.actor_prompt(case)
    assert "latest statement" not in records.actor_prompt(records.CASES["template"])
    session = records.RecordsSession(tmp_path / "s", tmp_path / "rt", optional=False, case=case)
    written = (session.corpus / "records.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in written] == corpus
    assert not (session.corpus / "labels.json").exists()
