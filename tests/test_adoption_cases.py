"""Repository fixtures validate source-backed meaning, not marker-only completion."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def cases(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("adoption_cases")


def cited(case, label, text=None, source=None):
    relative = case["expected"][label] if source is None else source
    body = (Path(case["inputs"]["root"]) / relative).read_text()
    quote = body if text is None else text
    start = body.find(quote)
    assert start >= 0
    return {
        "label": label,
        "source": "workspace:" + relative,
        "ref": "fixture:" + label,
        "offset": start,
        "end": start + len(quote),
        "total": len(body),
        "text": quote,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }


def report(tmp_path, rows):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"records": rows}), encoding="utf-8", newline="\n")
    return path


@pytest.mark.parametrize("variant", [0, 1])
def test_short_is_a_single_requested_manifest_fact(cases, tmp_path, variant):
    case = cases.fixture(tmp_path / "sources", "short", variant)
    assert list(case["inputs"]["requirements"]) == ["version"]
    assert len(list(Path(case["inputs"]["root"]).rglob("*"))) == 1
    assert "package.json" in case["goal"]
    assert (
        cases.independent_check(case, report(tmp_path, [cited(case, "version")]))["passed"] is True
    )


@pytest.mark.parametrize("variant", [0, 1])
def test_medium_truth_is_supported_by_ast_and_pure_transitions(cases, tmp_path, variant):
    case = cases.fixture(tmp_path / "sources", "medium", variant)
    checked = cases.mechanical_check(case)
    assert checked["passed"] is True
    assert checked["record_consistent"] is True
    assert checked["simulation"]["lost_ack_delivery_count"] == 2
    assert checked["simulation"]["normal_retry_delivery_count"] == 1
    assert checked["profile"]["reserve_before_dispatch"] is bool(variant)
    assert checked["profile"]["lost_ack_discards_reservation"] is bool(variant)
    root = Path(case["inputs"]["root"])
    assert 6 <= len([p for p in root.rglob("*") if p.is_file()]) <= 8
    assert "Cause:" not in (root / "src/worker.py").read_text()
    assert (
        cases.independent_check(
            case, report(tmp_path, [cited(case, label) for label in case["expected"]])
        )["passed"]
        is True
    )


def test_variants_change_real_code_condition_record_and_counterevidence(cases, tmp_path):
    first = cases.fixture(tmp_path / "one", "medium", 0)
    second = cases.fixture(tmp_path / "two", "medium", 1)
    a, b = cases.mechanical_check(first), cases.mechanical_check(second)
    assert a["profile"] != b["profile"]
    assert a["simulation"]["lost_ack_events"] != b["simulation"]["lost_ack_events"]
    assert first["expected_values"] != second["expected_values"]
    assert (Path(first["inputs"]["root"]) / "tests/results/current.json").read_text() != (
        Path(second["inputs"]["root"]) / "tests/results/current.json"
    ).read_text()


@pytest.mark.parametrize("level", ["short", "medium", "missing"])
def test_actor_contract_contains_schema_categories_but_no_truth_or_next_step(
    cases, tmp_path, level
):
    case = cases.fixture(tmp_path / "sources", level, 0)
    assert set(case["inputs"]) == {"kind", "root", "queries", "requirements"}
    actor = json.dumps({"goal": case["goal"], "inputs": case["inputs"]})
    assert (
        "expected_sources" not in actor and "expected_values" not in actor and "oracle" not in actor
    )
    assert "reserve_before_dispatch" not in actor and "lost_ack_discards_reservation" not in actor
    assert "2.4.0" not in actor and "actual_delivery_count" not in actor
    assert set(case["inputs"]["requirements"]) <= {
        "version",
        "implementation",
        "reproduction",
        "counterevidence",
    }
    for marker in case["inputs"]["requirements"].values():
        assert len(marker) <= 20


@pytest.mark.parametrize("level", ["short", "medium"])
def test_marker_header_can_pass_actor_schema_but_not_semantic_evaluator(cases, tmp_path, level):
    from open_tasks import build

    case = cases.fixture(tmp_path / "sources", level, 0)
    case["inputs"]["output"] = str(tmp_path / "saved.json")
    task = build(case["inputs"])
    pack = task.toolkits[0]
    try:
        catalog = pack.list_files()["files"]
        for label, relative in case["expected"].items():
            file_id = next(x["id"] for x in catalog if x["path"] == relative)
            ref = pack.read_file(file_id)["ref"]
            body = task.store.read(ref)["text"]
            marker = case["inputs"]["requirements"][label]
            task.record_evidence(
                {"ref": ref, "offset": body.index(marker), "limit": len(marker)}, label
            )
        task.save_report()
        assert task.verify(None, task.observe(None)) is True
        assert cases.independent_check(case, task.output)["passed"] is False
    finally:
        pack.close()


@pytest.mark.parametrize("variant", [0, 1])
def test_archived_result_and_wrong_release_section_are_not_current_evidence(
    cases, tmp_path, variant
):
    case = cases.fixture(tmp_path / "sources", "medium", variant)
    rows = [cited(case, label) for label in case["expected"]]
    index = next(i for i, row in enumerate(rows) if row["label"] == "reproduction")
    rows[index] = cited(case, "reproduction", source="tests/results/previous.json")
    assert cases.independent_check(case, report(tmp_path, rows))["labels"]["reproduction"] is False
    rows = [cited(case, label) for label in case["expected"]]
    body = (Path(case["inputs"]["root"]) / "docs/releases.md").read_text()
    old = body[body.index("## v1.9.0") :]
    index = next(i for i, row in enumerate(rows) if row["label"] == "counterevidence")
    rows[index] = cited(case, "counterevidence", old)
    assert (
        cases.independent_check(case, report(tmp_path, rows))["labels"]["counterevidence"] is False
    )


def test_authentic_version_header_without_version_value_fails(cases, tmp_path):
    case = cases.fixture(tmp_path / "sources", "short", 1)
    row = cited(case, "version", '"version":')
    assert cases.independent_check(case, report(tmp_path, [row]))["passed"] is False


def test_quote_not_supported_by_original_bytes_fails_despite_matching_marker(cases, tmp_path):
    case = cases.fixture(tmp_path / "sources", "medium", 0)
    rows = [cited(case, label) for label in case["expected"]]
    rows[0]["text"] += "invented explanation"
    rows[0]["end"] += len("invented explanation")
    assert cases.independent_check(case, report(tmp_path, rows))["passed"] is False


def test_source_identity_and_total_length_are_independently_checked(cases, tmp_path):
    case = cases.fixture(tmp_path / "sources", "short", 0)
    row = cited(case, "version")
    row["source"] = "other-root/package.json"
    assert cases.independent_check(case, report(tmp_path, [row]))["passed"] is False
    row = cited(case, "version")
    row["total"] += 1
    assert cases.independent_check(case, report(tmp_path, [row]))["passed"] is False


@pytest.mark.parametrize("variant", [0, 1])
def test_missing_record_does_not_use_existing_test_or_older_result_as_proof(
    cases, tmp_path, variant
):
    case = cases.fixture(tmp_path / "sources", "missing", variant)
    assert not (Path(case["inputs"]["root"]) / "tests/results/current.json").exists()
    checked = cases.mechanical_check(case)
    assert checked["passed"] is True and checked["record_present"] is False
    rows = [cited(case, label) for label in case["expected"] if label != "reproduction"]
    rows.append(cited(case, "reproduction", source="tests/results/previous.json"))
    assert cases.independent_check(case, report(tmp_path, rows))["passed"] is False


def test_mechanical_validator_rejects_unsupported_ast_without_execution(
    cases, tmp_path, monkeypatch
):
    case = cases.fixture(tmp_path / "sources", "medium", 0)
    worker = Path(case["inputs"]["root"]) / "src/worker.py"
    worker.write_text(
        'import os\nos.system("SHOULD_NEVER_EXECUTE")\n', encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr("os.system", lambda *a: pytest.fail("Fixture source must not execute"))
    assert cases.mechanical_check(case)["passed"] is False


def test_current_record_inconsistent_with_pure_transition_fails(cases, tmp_path):
    case = cases.fixture(tmp_path / "sources", "medium", 0)
    path = Path(case["inputs"]["root"]) / "tests/results/current.json"
    record = json.loads(path.read_text())
    record["actual_delivery_count"] = 1
    path.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
    assert cases.mechanical_check(case)["passed"] is False
    assert (
        cases.independent_check(
            case, report(tmp_path, [cited(case, label) for label in case["expected"]])
        )["passed"]
        is False
    )


def test_fixture_never_overwrites_existing_source_directory(cases, tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    owner = root / "owner.txt"
    owner.write_text("keep", encoding="utf-8", newline="\n")
    with pytest.raises(FileExistsError):
        cases.fixture(root, "medium", 0)
    assert owner.read_text() == "keep"


def test_source_identity_and_authentic_quote_must_belong_to_same_record(cases, tmp_path):
    case = cases.fixture(tmp_path / "sources", "short", 0)
    different_scope = cited(case, "version")
    different_scope["source"] = "another-workspace/package.json"
    invented_quote = cited(case, "version")
    invented_quote["text"] += "UNSUPPORTED_SOURCE_TEXT"
    invented_quote["end"] += len("UNSUPPORTED_SOURCE_TEXT")
    assert (
        cases.independent_check(case, report(tmp_path, [different_scope, invented_quote]))["passed"]
        is False
    )
