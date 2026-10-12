"""Owner-only files and descriptor-relative, no-follow directory access on each platform."""

import os

import pytest
from platform_support import (
    broaden_access,
    make_junction,
    make_symlink,
    owner_only,
    windows_only,
)

from apixly_jev_harness import _secure_fs


def test_directory_handle_lists_kinds_and_reads_only_regular_files(tmp_path):
    root = tmp_path / "root"
    (root / "nested").mkdir(parents=True)
    (root / "source.txt").write_bytes(b"line one\nline two\n")
    directory = _secure_fs.open_directory(root)
    try:
        rows = sorted(directory.entries(10))
        assert [row[:2] for row in rows] == [("nested", "directory"), ("source.txt", "file")]
        assert rows[1][2] == 18
        fd = directory.open_file("source.txt")
        with os.fdopen(fd, "rb") as stream:
            assert stream.read() == b"line one\nline two\n"
        with pytest.raises(OSError):
            directory.open_file("nested")
        with pytest.raises(OSError):
            directory.open_file("missing.txt")
        child = directory.child("nested")
        assert child.entries(10) == []
        child.close()
    finally:
        directory.close()


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "nul\x00"])
def test_names_cannot_traverse_or_escape_the_handle(tmp_path, name):
    directory = _secure_fs.open_directory(tmp_path)
    try:
        with pytest.raises(OSError):
            directory.child(name)
        with pytest.raises(OSError):
            directory.create_private(name)
    finally:
        directory.close()


def test_relative_create_rename_and_unlink_stay_in_the_open_directory(tmp_path):
    root = tmp_path / "responses"
    root.mkdir()
    directory = _secure_fs.open_directory(root)
    try:
        fd = directory.create_private("reply.pending")
        with os.fdopen(fd, "wb") as stream:
            stream.write(b'{"ok": true}')
        with pytest.raises(FileExistsError):
            directory.create_private("reply.pending")
        assert owner_only(root / "reply.pending")
        directory.rename("reply.pending", "reply.json")
        assert sorted(directory.names()) == ["reply.json"]
        assert (root / "reply.json").read_bytes() == b'{"ok": true}'
        directory.unlink("reply.json")
        assert directory.names() == []
    finally:
        directory.close()


def test_private_file_modes_are_exclusive_owner_only_and_reject_broadened_files(tmp_path):
    path = tmp_path / "artifact.json"
    fd = _secure_fs.open_private_file(path, "x")
    os.write(fd, b"{}\n")
    os.close(fd)
    assert path.read_bytes() == b"{}\n" and owner_only(path)
    with pytest.raises(FileExistsError):
        _secure_fs.open_private_file(path, "x+")
    fd = _secure_fs.open_private_file(path, "r+")
    try:
        assert _secure_fs.owner_only(fd)
    finally:
        os.close(fd)
    log = tmp_path / "audit.jsonl"
    for line in (b"1\n", b"2\n"):
        fd = _secure_fs.open_private_file(log, "a")
        os.write(fd, line)
        os.close(fd)
    assert log.read_bytes() == b"1\n2\n" and owner_only(log)
    broaden_access(log)
    assert not owner_only(log)
    with pytest.raises(OSError):
        _secure_fs.open_private_file(log, "a")
    with pytest.raises(ValueError):
        _secure_fs.open_private_file(path, "w")


def test_private_directory_is_owner_only_and_existing_link_is_not_accepted(tmp_path):
    target = tmp_path / "private"
    _secure_fs.make_private_directory(target)
    assert _secure_fs.path_owner_only(target, directory=True)
    _secure_fs.make_private_directory(target, exist_ok=True)
    with pytest.raises(FileExistsError):
        _secure_fs.make_private_directory(target)
    nested = tmp_path / "a" / "b"
    _secure_fs.make_private_directory(nested, parents=True)
    assert _secure_fs.path_owner_only(nested, directory=True)


def test_symlinked_entries_are_reported_as_links_and_never_opened(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside secret")
    make_symlink(root / "link.txt", outside)
    directory = _secure_fs.open_directory(root)
    try:
        assert directory.entries(10)[0][:2] == ("link.txt", "link")
        with pytest.raises(OSError):
            directory.open_file("link.txt")
        assert _secure_fs.is_link(root / "link.txt")
    finally:
        directory.close()
    with pytest.raises(OSError):
        _secure_fs.open_private_file(root / "link.txt", "r+")


@windows_only
def test_junctions_are_rejected_as_children_and_as_roots(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"outside secret")
    root = tmp_path / "root"
    root.mkdir()
    make_junction(root / "alias", outside)
    make_junction(tmp_path / "alias-root", outside)
    directory = _secure_fs.open_directory(root)
    try:
        assert directory.entries(10) == [("alias", "link", 0)]
        with pytest.raises(OSError):
            directory.child("alias")
        with pytest.raises(OSError):
            directory.open_file("alias")
    finally:
        directory.close()
    with pytest.raises(OSError):
        _secure_fs.open_directory(tmp_path / "alias-root")
    assert _secure_fs.is_link(root / "alias")


def test_backend_reports_availability_for_this_platform():
    assert _secure_fs.available() is True
