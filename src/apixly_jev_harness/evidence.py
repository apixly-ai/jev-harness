"""Capture-specific source references and bounded reads, without result caching."""

import copy
import hashlib
import json

from .engine import DecisionStop
from .task import Option


class EvidenceStore:
    def __init__(self, *, max_characters=1_000_000, read_limit=1200):
        if type(max_characters) is not int or max_characters < 1:
            raise ValueError("positive_evidence_limit_required")
        if type(read_limit) is not int or not 1 <= read_limit <= 1200:
            raise ValueError("invalid_evidence_read_limit")
        self.max_characters, self.read_limit = max_characters, read_limit
        self._sources = {}

    def put(self, text, source, metadata=None):
        if type(text) is not str or type(source) is not str or not source:
            raise ValueError("evidence_text_and_source_required")
        if len(text) > self.max_characters:
            raise DecisionStop("needs_review", "evidence_source_too_large")
        metadata = {} if metadata is None else copy.deepcopy(metadata)
        if type(metadata) is not dict:
            raise ValueError("evidence_metadata_object_required")
        json.dumps(metadata, allow_nan=False).encode("utf-8")
        ref = f"evidence:{len(self._sources) + 1}"
        self._sources[ref] = {
            "ref": ref,
            "source": source,
            "text": text,
            "characters": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "metadata": metadata,
        }
        return ref

    def _get(self, ref):
        if type(ref) is not str or ref not in self._sources:
            raise ValueError("unknown_evidence_reference")
        return self._sources[ref]

    def describe(self, ref):
        row = self._get(ref)
        return {
            "ref": ref,
            "source": row["source"],
            "characters": row["characters"],
            "sha256": row["sha256"],
            "summary": row["text"][:240],
            "metadata": copy.deepcopy(row["metadata"]),
        }

    def references(self):
        return [self.describe(ref) for ref in self._sources]

    def read(self, ref, offset=0, limit=1200):
        row = self._get(ref)
        if (
            type(offset) is not int
            or not 0 <= offset <= row["characters"]
            or type(limit) is not int
            or not 1 <= limit <= self.read_limit
        ):
            raise ValueError("invalid_evidence_window")
        end = min(offset + limit, row["characters"])
        return {
            "ref": ref,
            "source": row["source"],
            "offset": offset,
            "end": end,
            "total": row["characters"],
            "text": row["text"][offset:end],
            "sha256": row["sha256"],
        }

    def chunk_options(self, ref=None, *, page=0):
        refs = [ref] if ref is not None else list(self._sources)
        if type(page) is not int or page < 0:
            raise ValueError("invalid_evidence_page")
        options = []
        for key in refs:
            row = self._get(key)
            for start in range(0, max(1, row["characters"]), self.read_limit):
                end = min(start + self.read_limit, row["characters"])
                options.append(
                    Option(
                        f"{key}:{start}",
                        f"{row['source']} | characters {start}:{end} | {row['text'][start : start + 100]}",
                        {"ref": key, "offset": start, "limit": self.read_limit},
                    )
                )
        return options[page * 250 : (page + 1) * 250]

    def page_count(self):
        count = sum(
            max(1, (x["characters"] + self.read_limit - 1) // self.read_limit)
            for x in self._sources.values()
        )
        return (count + 249) // 250
