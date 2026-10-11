"""Read-only source discovery toolkit over caller-selected workspace roots."""

import copy
import hashlib
import itertools
import json
import os
import re
import stat
from collections import deque
from pathlib import Path, PurePosixPath

from .task import Option, Parameter


class _SourceError(Exception):
    pass


class WorkspaceTools:
    """Discover permitted regular files and capture source text without importing it.

    Reads use a caller-selected directory descriptor and reject all symlinks. Platforms
    without descriptor-relative, no-follow opens fail closed. Private evidence writes
    belong to the supplied store; source files are never written or executed.
    """

    name = "files"
    _MAX_BYTES = 1_000_000
    _MAX_SEARCH_BYTES = 10_000_000
    _MAX_MATCHES = 20
    _MAX_QUERIES = 80
    _EXCLUDED_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules"}

    def __init__(self, root, store, queries=(), max_files=200):
        self._root_fd = None
        if type(max_files) is not int or max_files < 1:
            raise ValueError("positive_workspace_file_limit_required")
        if isinstance(queries, (str, bytes)):
            raise ValueError("workspace_query_candidates_required")
        self._queries = []
        self._queries_truncated = False
        for query in queries:
            self._add_query(query, required=True)
        if (
            os.open not in os.supports_dir_fd
            or os.scandir not in os.supports_fd
            or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")
        ):
            raise ValueError("workspace_secure_open_unavailable")
        selected = Path(root).expanduser().absolute()
        if selected.is_symlink() or not selected.is_dir():
            raise ValueError("workspace_root_directory_required")
        self.root, self.store, self.max_files = selected.resolve(), store, max_files
        self._directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            self._root_fd = os.open(self.root, self._directory_flags)
        except OSError:
            raise ValueError("workspace_root_directory_required") from None
        self._files, self._captured, self._last = {}, {}, {}

    def close(self):
        if self._root_fd is not None:
            os.close(self._root_fd)
            self._root_fd = None

    def __del__(self):
        self.close()

    def _add_query(self, query, *, required=False):
        if type(query) is not str or not query.strip() or len(query) > 120:
            if required:
                raise ValueError("workspace_query_required")
            return
        try:
            query.encode("utf-8")
        except UnicodeError:
            if required:
                raise ValueError("workspace_query_required") from None
            return
        if query not in self._queries:
            if len(self._queries) >= self._MAX_QUERIES:
                if required:
                    raise ValueError("workspace_query_domain_too_large")
                self._queries_truncated = True
            else:
                self._queries.append(query)

    def _terms(self, text):
        for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]{2,63}\b", text[:2400]):
            self._add_query(match.group())

    def _directory(self, relative):
        if self._root_fd is None:
            raise _SourceError("workspace_closed")
        parts = PurePosixPath(relative).parts
        if PurePosixPath(relative).is_absolute() or any(x in ("..", ".") for x in parts):
            raise _SourceError("workspace_path_not_allowed")
        fd = os.dup(self._root_fd)
        try:
            for part in parts:
                child = os.open(part, self._directory_flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except OSError:
            os.close(fd)
            raise _SourceError("workspace_path_not_allowed") from None

    def _scan(self):
        files, skipped, queue = [], {"symlink": 0, "excluded": 0, "unreadable": 0}, deque([""])
        remaining, truncated = max(2000, self.max_files * 20), False
        while queue and remaining > 0:
            relative = queue.popleft()
            try:
                fd = self._directory(relative)
            except _SourceError:
                skipped["unreadable"] += 1
                continue
            try:
                with os.scandir(fd) as entries:
                    rows = list(itertools.islice(entries, remaining + 1))
                if len(rows) > remaining:
                    truncated = True
                    rows = rows[:remaining]
                remaining -= len(rows)
                for entry in sorted(rows, key=lambda row: row.name):
                    path = "/".join(x for x in (relative, entry.name) if x)
                    try:
                        path.encode("utf-8")
                        info = entry.stat(follow_symlinks=False)
                    except (OSError, UnicodeError):
                        skipped["unreadable"] += 1
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        skipped["symlink"] += 1
                    elif stat.S_ISDIR(info.st_mode):
                        if entry.name in self._EXCLUDED_DIRECTORIES:
                            skipped["excluded"] += 1
                        else:
                            queue.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        if entry.name == ".env" or entry.name.startswith(".env."):
                            skipped["excluded"] += 1
                            continue
                        if len(files) >= self.max_files:
                            truncated = True
                            return files, skipped, truncated
                        files.append(
                            {
                                "id": "file:" + hashlib.sha256(path.encode()).hexdigest()[:24],
                                "path": path,
                                "bytes": info.st_size,
                            }
                        )
                        self._add_query(PurePosixPath(path).stem)
            except OSError:
                skipped["unreadable"] += 1
            finally:
                os.close(fd)
        return files, skipped, truncated or bool(queue)

    def list_files(self):
        rows, skipped, truncated = self._scan()
        self._files = {row["id"]: row for row in rows}
        self._last = {"operation": "list", "count": len(rows), "truncated": truncated}
        return {
            "files": copy.deepcopy(rows),
            "count": len(rows),
            "truncated": truncated,
            "skipped": skipped,
        }

    def _read_text(self, path, *, remaining=None):
        relative = PurePosixPath(path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise _SourceError("workspace_path_not_allowed")
        parent = self._directory(relative.parent.as_posix() if len(relative.parts) > 1 else "")
        fd = None
        try:
            fd = os.open(
                relative.name,
                os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent,
            )
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise _SourceError("workspace_path_not_allowed")
            if info.st_size > self._MAX_BYTES:
                raise _SourceError("workspace_source_too_large")
            limit = self._MAX_BYTES if remaining is None else min(self._MAX_BYTES, remaining)
            if info.st_size > limit:
                raise _SourceError("workspace_search_byte_limit")
            with os.fdopen(fd, "rb") as stream:
                fd = None
                body = stream.read(limit + 1)
            if len(body) > limit:
                raise _SourceError(
                    "workspace_source_too_large"
                    if limit == self._MAX_BYTES
                    else "workspace_search_byte_limit"
                )
            return body.decode("utf-8")
        except UnicodeError:
            raise _SourceError("workspace_source_not_utf8") from None
        except OSError:
            raise _SourceError("workspace_path_not_allowed") from None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def _capture(self, file, text, *, metadata=None):
        row = self._files[file]
        ref = self.store.put(
            text,
            source="workspace:" + row["path"],
            metadata={"kind": "workspace_file", "path": row["path"], **(metadata or {})},
        )
        self._captured[file] = ref
        self._terms(text)
        return ref

    def read_file(self, file):
        if type(file) is not str or file not in self._files:
            raise ValueError("unknown_workspace_file")
        try:
            text = self._read_text(self._files[file]["path"])
        except _SourceError as error:
            self._last = {
                "operation": "read",
                "file": file,
                "status": "unreadable",
                "code": str(error),
            }
            return copy.deepcopy(self._last)
        ref = self._capture(file, text)
        card = self.store.describe(ref)
        self._last = {"operation": "read", "ref": ref, "source": card["source"]}
        return card

    def search_files(self, query):
        if type(query) is not str or query not in self._queries:
            raise ValueError("workspace_query_not_offered")
        listing = self.list_files()
        matches, spent, truncated = [], 0, listing["truncated"]
        unreadable = 0
        for file, row in self._files.items():
            if spent + row["bytes"] > self._MAX_SEARCH_BYTES:
                truncated = True
                break
            try:
                text = self._read_text(row["path"], remaining=self._MAX_SEARCH_BYTES - spent)
            except _SourceError as error:
                if str(error) == "workspace_search_byte_limit":
                    truncated = True
                    break
                unreadable += 1
                continue
            spent += len(text.encode("utf-8"))
            lines = [i + 1 for i, line in enumerate(text.splitlines()) if query in line]
            if not lines:
                continue
            if len(matches) >= self._MAX_MATCHES:
                truncated = True
                break
            ref = self._capture(file, text, metadata={"query": query, "match_lines": lines[:20]})
            matches.append({"id": file, "path": row["path"], "ref": ref, "lines": lines[:20]})
        self._last = {
            "operation": "search",
            "query": query,
            "count": len(matches),
            "truncated": truncated,
        }
        return {
            "matches": matches,
            "count": len(matches),
            "truncated": truncated,
            "unreadable": unreadable,
        }

    def observe(self):
        catalog = sorted((row["path"], row["bytes"]) for row in self._files.values())
        return {
            "file_count": len(catalog),
            "catalog_digest": hashlib.sha256(json.dumps(catalog).encode()).hexdigest(),
            "queries": list(self._queries),
            "queries_truncated": self._queries_truncated,
            "captured": [self.store.describe(ref) for ref in list(self._captured.values())[-8:]],
            "last": copy.deepcopy(self._last),
        }

    def _result_context(self, result):
        return {
            key: copy.deepcopy(result[key])
            for key in (
                "ref",
                "source",
                "characters",
                "sha256",
                "summary",
                "count",
                "truncated",
                "code",
                "status",
            )
            if key in result
        }

    def install(self, task):
        task.tool(
            "Discover regular source files within the permitted workspace; no source execution",
            name="files.list",
            result_context=self._result_context,
        )(self.list_files)
        task.tool(
            "Search permitted source text for a supplied or discovered literal term",
            name="files.search",
            parameters={
                "query": Parameter(
                    "A known term worth investigating for the goal",
                    lambda c, s: [
                        Option(str(i), f"Literal source term: {q}", q)
                        for i, q in enumerate(self._queries)
                    ],
                    selection="explore",
                )
            },
            result_context=self._result_context,
        )(self.search_files)
        task.tool(
            "Capture a discovered source file as evidence for bounded passage reading",
            name="files.read",
            parameters={
                "file": Parameter(
                    "Discovered permitted file relevant to the current investigation",
                    lambda c, s: [
                        Option(key, f"{row['path']} | {row['bytes']} bytes", key)
                        for key, row in self._files.items()
                    ],
                    selection="explore",
                )
            },
            result_context=self._result_context,
        )(self.read_file)
