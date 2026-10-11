"""Workspace discovery and evidence admission without running inspected source."""

import json
import os

import pytest

from apixly_jev_harness import Context, Engine, Task
from apixly_jev_harness.evidence import EvidenceStore
from apixly_jev_harness.workspace import WorkspaceTools


def workspace(tmp_path, *, queries=(), max_files=200):
    root = tmp_path / "source"
    root.mkdir()
    store = EvidenceStore()
    return root, store, WorkspaceTools(root, store, queries=queries, max_files=max_files)


def file_id(packet, path):
    return next(row["id"] for row in packet["files"] if row["path"] == path)


def test_listing_discovers_unknown_nested_files_and_excludes_private_metadata(tmp_path):
    root, store, tools = workspace(tmp_path)
    (root / "feature").mkdir()
    (root / "feature" / "answer.py").write_text("def inspect_me(): pass\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("private git configuration")
    (root / ".env").write_text("SECRET=fixture-only")
    before = tools.observe()
    packet = tools.list_files()
    assert [row["path"] for row in packet["files"]] == ["feature/answer.py"]
    assert packet["count"] == 1
    assert store.references() == []
    assert tools.observe() != before
    assert str(root) not in json.dumps(packet)


def test_read_retains_full_source_but_returns_only_reference_and_summary(tmp_path):
    root, store, tools = workspace(tmp_path)
    marker = "FULL_SOURCE_TAIL_MARKER"
    text = "Header for semantic investigation\n" + "x" * 5000 + marker
    (root / "large.txt").write_text(text)
    target = file_id(tools.list_files(), "large.txt")
    packet = tools.read_file(target)
    assert store.describe(packet["ref"])["characters"] == len(text)
    assert store.read(packet["ref"], len(text) - len(marker), len(marker))["text"] == marker
    assert marker not in json.dumps(packet)
    assert "text" not in packet
    assert str(root) not in json.dumps(packet)


def test_observe_and_providers_do_not_capture_or_read_source(tmp_path, monkeypatch):
    root, store, tools = workspace(tmp_path, queries=("entry",))
    (root / "entry.py").write_text("def entry(): return 42\n")
    tools.list_files()
    task = Task(observe=lambda ctx: tools.observe(), verify=lambda ctx, state: False)
    tools.install(task)
    initial = tools.observe()
    refs = store.references()
    monkeypatch.setattr(
        tools, "_read_text", lambda path: pytest.fail("provider/observe read source")
    )
    for _ in range(3):
        assert tools.observe() == initial
        assert task.candidates(Context("Inspect", {}, {}), initial)
        assert store.references() == refs


def test_search_discovers_source_refs_and_terms_without_executing_code(tmp_path):
    root, store, tools = workspace(tmp_path, queries=("TraceBeacon",))
    marker = tmp_path / "never-executed"
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "class TraceBeacon: pass\n"
    )
    (root / "unknown.py").write_text(source)
    packet = tools.search_files("TraceBeacon")
    assert packet["count"] == 1
    match = packet["matches"][0]
    assert match["path"] == "unknown.py"
    assert store.describe(match["ref"])["characters"] == len(source)
    assert "TraceBeacon" in tools.observe()["queries"]
    assert not marker.exists()
    assert "write_text('executed')" not in json.dumps(packet)


def test_new_terms_from_read_source_become_dynamic_search_choices(tmp_path):
    root, store, tools = workspace(tmp_path)
    (root / "entry.txt").write_text("Next dependency is StellarBoundary\n")
    tools.read_file(file_id(tools.list_files(), "entry.txt"))
    task = Task(observe=lambda ctx: tools.observe(), verify=lambda ctx, state: False)
    tools.install(task)
    actions = task.candidates(Context("Find dependency", {}, {}), tools.observe())
    search = next(action for action in actions if action.id == "files.search")
    assert "StellarBoundary" in search.description
    assert len(store.references()) == 1


@pytest.mark.parametrize("bad", ["../outside.txt", "/etc/passwd", "not-discovered"])
def test_read_accepts_discovered_ids_not_arbitrary_paths(tmp_path, bad):
    root, store, tools = workspace(tmp_path)
    with pytest.raises(ValueError, match="unknown_workspace_file"):
        tools.read_file(bad)
    assert store.references() == []


def test_symlink_sources_and_directories_are_not_discovered(tmp_path):
    root, store, tools = workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside secret marker")
    (root / "link.txt").symlink_to(outside / "secret.txt")
    (root / "linked-directory").symlink_to(outside, target_is_directory=True)
    packet = tools.list_files()
    assert packet["files"] == []
    assert packet["skipped"]["symlink"] == 2
    assert store.references() == []


def test_replacing_discovered_file_with_symlink_cannot_escape_root(tmp_path):
    root, store, tools = workspace(tmp_path)
    source = root / "source.txt"
    source.write_text("permitted source")
    target = file_id(tools.list_files(), "source.txt")
    outside = tmp_path / "secret.txt"
    outside.write_text("outside secret marker")
    source.unlink()
    source.symlink_to(outside)
    packet = tools.read_file(target)
    assert packet["status"] == "unreadable"
    assert packet["code"] == "workspace_path_not_allowed"
    assert store.references() == []
    assert "outside secret" not in json.dumps(packet)


def test_replacing_parent_directory_with_symlink_cannot_escape_root(tmp_path):
    root, store, tools = workspace(tmp_path)
    directory = root / "nested"
    directory.mkdir()
    (directory / "source.txt").write_text("permitted source")
    target = file_id(tools.list_files(), "nested/source.txt")
    (directory / "source.txt").unlink()
    directory.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.txt").write_text("outside secret marker")
    directory.symlink_to(outside, target_is_directory=True)
    assert tools.read_file(target)["code"] == "workspace_path_not_allowed"
    assert store.references() == []


def test_binary_and_overlarge_files_have_explicit_bounded_outcomes(tmp_path):
    root, store, tools = workspace(tmp_path)
    (root / "binary.bin").write_bytes(b"\xff\xfe\x00")
    (root / "huge.txt").write_bytes(b"x" * 1_000_001)
    files = tools.list_files()
    binary = tools.read_file(file_id(files, "binary.bin"))
    huge = tools.read_file(file_id(files, "huge.txt"))
    assert binary["code"] == "workspace_source_not_utf8"
    assert huge["code"] == "workspace_source_too_large"
    assert store.references() == []


def test_listing_limit_is_reported_without_claiming_complete_search(tmp_path):
    root, store, tools = workspace(tmp_path, max_files=1)
    (root / "a.txt").write_text("a")
    (root / "b.txt").write_text("b")
    packet = tools.list_files()
    assert packet["count"] == 1
    assert packet["truncated"] is True
    assert store.references() == []


def test_search_read_budget_uses_actual_source_size_after_listing(tmp_path, monkeypatch):
    root, store, tools = workspace(tmp_path, queries=("needle",))
    source = root / "changing.txt"
    source.write_text("needle")
    tools._MAX_SEARCH_BYTES = 20
    original = tools._read_text

    def grow(path, **kwargs):
        source.write_text("needle " * 20)
        return original(path, **kwargs)

    monkeypatch.setattr(tools, "_read_text", grow)
    result = tools.search_files("needle")
    assert result["truncated"] is True
    assert store.references() == []


def test_given_query_limit_rejects_instead_of_silently_dropping_candidates(tmp_path):
    with pytest.raises(ValueError, match="workspace_query_domain_too_large"):
        WorkspaceTools(tmp_path, EvidenceStore(), queries=[f"query{i}" for i in range(81)])


def test_read_observes_changed_source_instead_of_reusing_an_old_capture(tmp_path):
    root, store, tools = workspace(tmp_path)
    source = root / "changing.txt"
    source.write_text("first source")
    target = file_id(tools.list_files(), "changing.txt")
    first = tools.read_file(target)
    source.write_text("second source")
    second = tools.read_file(target)
    assert first["ref"] != second["ref"]
    assert first["sha256"] != second["sha256"]
    assert store.read(first["ref"])["text"] == "first source"
    assert store.read(second["ref"])["text"] == "second source"


def test_discovered_file_replaced_by_fifo_is_rejected_without_blocking(tmp_path):
    root, store, tools = workspace(tmp_path)
    source = root / "changing.txt"
    source.write_text("regular file")
    target = file_id(tools.list_files(), "changing.txt")
    source.unlink()
    os.mkfifo(source)
    assert tools.read_file(target)["code"] == "workspace_path_not_allowed"
    assert store.references() == []


def test_unsupported_secure_open_has_no_unsafe_path_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(ValueError, match="workspace_secure_open_unavailable"):
        WorkspaceTools(tmp_path, EvidenceStore())


@pytest.mark.parametrize("bad", [0, -1, True, 1.2])
def test_invalid_file_bounds_are_not_silently_defaulted(tmp_path, bad):
    with pytest.raises(ValueError, match="positive_workspace_file_limit_required"):
        WorkspaceTools(tmp_path, EvidenceStore(), max_files=bad)


def test_workspace_reuses_task_and_engine_with_scripted_selection_only(tmp_path):
    root, store, tools = workspace(tmp_path)
    (root / "unexpected.txt").write_text("Evidence for the requested investigation")
    task = Task(
        observe=lambda ctx: tools.observe(),
        verify=lambda ctx, state: bool(store.references()),
    )
    tools.install(task)

    class Scripted(Engine):
        def decide(self, records, goal, **kwargs):
            selected = "files.list" if not tools.observe()["file_count"] else "files.read"
            return {
                "ok": True,
                "complete": True,
                "selected_ids": [selected],
                "review_ids": [],
                "telemetry": {
                    "requests": 0,
                    "usage_complete": False,
                    "usage": None,
                },
            }

    result = Scripted().run(task, goal="Discover source evidence", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done"
    assert result["steps"] == 2
    assert result["telemetry"]["usage"] is None
    assert len(store.references()) == 1
    assert not (root / "run.jsonl").exists()
