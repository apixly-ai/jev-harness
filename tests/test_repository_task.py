"""Source-derived actor checks reject old recorded evidence without an oracle."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
from adoption_cases import fixture
from repository_task import build


@pytest.mark.parametrize("variant", [0, 1])
def test_current_source_identity_checks_without_expected_answers(tmp_path, variant):
    case = fixture(tmp_path / "sources", "medium", variant)
    task = build({**case["inputs"], "output": str(tmp_path / "report.json")})
    pack = task.toolkits[0]
    files = pack.list_files()["files"]
    try:
        for label, path in [
            ("implementation", "src/worker.py"),
            ("reproduction", "tests/results/current.json"),
            ("counterevidence", "docs/releases.md"),
        ]:
            card = pack.read_file(next(row["id"] for row in files if row["path"] == path))
            passage = {"ref": card["ref"], "offset": 0, "limit": 1200}
            assert task._supports(label, passage)
        old = pack.read_file(
            next(row["id"] for row in files if row["path"] == "tests/results/previous.json")
        )
        assert not task._supports("reproduction", {"ref": old["ref"], "offset": 0, "limit": 1200})
    finally:
        pack.close()


@pytest.mark.parametrize(
    "change",
    [
        {"package_version": "1.9.0"},
        {"worker_sha256": "0" * 64},
        {"expected_delivery_count": True},
        {"actual_delivery_count": True},
        {"expected_delivery_count": -1},
        {"actual_delivery_count": -1},
    ],
)
def test_invalid_record_identity_or_count_is_not_offered(tmp_path, change):
    import json

    case = fixture(tmp_path / "sources", "medium", 0)
    task = build({**case["inputs"], "output": str(tmp_path / "report.json")})
    try:
        data = json.loads((tmp_path / "sources/tests/results/current.json").read_text())
        row = {"text": json.dumps({**data, **change})}
        assert not task.record_checks["reproduction"](row)
    finally:
        task.toolkits[0].close()


def test_prior_release_enablement_and_missing_record_stay_incomplete(tmp_path):
    case = fixture(tmp_path / "sources", "missing", 1)
    task = build({**case["inputs"], "output": str(tmp_path / "report.json")})
    try:
        seen = task.observe(None)
        assert seen["known_repository"]["package_version"] == "2.5.0"
        assert seen["known_repository"]["entry"] == "src/worker.py"
        assert not task.record_checks["counterevidence"](
            {
                "text": "## v2.5.0\nRetry scheduling: disabled.\n\n## v1.9.0\nRetry scheduling: enabled.\n"
            }
        )
        assert not task.verify(None, seen)
    finally:
        task.toolkits[0].close()
