"""
Search log: how a literature search was done (design/parallel-literature-search.md §4.2/§4.4).

A literature decision (prior-work / novelty / contested / inquiry) records WHICH DOIs were
found and the outcome. The search log adds HOW: which academic indexes were queried, with
which query strings, when, and which of them failed. Without it a ``found_nothing`` from
one phrasing on one index is indistinguishable from a thorough search.

Two shapes:
  - :class:`SearchLogFile` -- one searcher's notes file, validated as given (fail-closed:
    unknown fields, an empty query list, a bad status or a non-UTC timestamp are refused).
  - :class:`SearchLogRecord` -- what is stored on ``Provenance.search_log``: the
    ``searched_at`` of every file plus their ``queries`` and ``candidates`` concatenated
    in file order.

No LLM, no network: this module only parses and validates JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Literal, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

_FROZEN_STRICT = {"frozen": True, "extra": "forbid", "str_strip_whitespace": True}


def _require_utc_iso8601(value: str) -> str:
    """Accept an ISO-8601 timestamp carrying an explicit UTC offset (``Z`` or ``+00:00``)."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"searched_at is not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(
            f"searched_at must be UTC with an explicit offset ('Z' or '+00:00'): {value!r}"
        )
    return value


class SearchQuery(BaseModel):
    """One query against one index: what was asked, and whether the index answered."""

    model_config = _FROZEN_STRICT

    index: str = Field(..., min_length=1, description="e.g. openalex, arxiv, crossref, web")
    query: str = Field(..., min_length=1, description="the exact query string sent")
    status: Literal["ok", "failed"] = Field(..., description="ok = the index answered")
    n_results: Optional[int] = Field(default=None, ge=0)
    detail: Optional[str] = Field(default=None, description="e.g. 'HTTP 429'")


class SearchCandidate(BaseModel):
    """A paper the search surfaced, with the searcher's relevance judgement."""

    model_config = _FROZEN_STRICT

    doi: str = Field(..., min_length=1)
    title: str
    relevance: Literal["same", "related", "unrelated"]
    basis: str = Field(..., description="one line: what in the paper matches or differs")


class SearchLogFile(BaseModel):
    """One searcher's notes file (design §4.2). ``hypothesis_id``/``kind`` are optional so
    the Spec-bound prior-work decision can carry a log too."""

    model_config = _FROZEN_STRICT

    hypothesis_id: Optional[str] = Field(default=None, min_length=1)
    kind: Optional[Literal["result", "method"]] = None
    searched_at: str
    queries: List[SearchQuery] = Field(..., min_length=1)
    candidates: List[SearchCandidate] = Field(default_factory=list)
    proposed_outcome: Optional[Literal["found-nothing", "found-prior-art"]] = None

    @field_validator("searched_at")
    @classmethod
    def _searched_at_is_utc(cls, value: str) -> str:
        return _require_utc_iso8601(value)


class SearchLogRecord(BaseModel):
    """The search log as stored on ``Provenance.search_log``: one ``searched_at`` per
    notes file, and the queries/candidates of all files concatenated in file order."""

    model_config = _FROZEN_STRICT

    searched_at: List[str] = Field(..., min_length=1)
    queries: List[SearchQuery] = Field(..., min_length=1)
    candidates: List[SearchCandidate] = Field(default_factory=list)

    @field_validator("searched_at")
    @classmethod
    def _each_searched_at_is_utc(cls, values: List[str]) -> List[str]:
        return [_require_utc_iso8601(v) for v in values]

    def ok_indexes(self) -> Set[str]:
        """Distinct indexes (case-insensitive) that answered at least one query."""
        return {q.index.lower() for q in self.queries if q.status == "ok"}


def load_search_logs(
    paths: Sequence[Path],
) -> Tuple[List[SearchLogFile], SearchLogRecord]:
    """Read and validate every notes file, then merge them into one record.

    Raises:
        ValueError: naming the offending file when one is missing, is not JSON, or does
            not match the schema. Callers turn this into a clean CLI error BEFORE any
            acquisition or write.
    """
    if not paths:
        raise ValueError("no search-log file given")
    files: List[SearchLogFile] = []
    for path in paths:
        path = Path(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"search log {path}: cannot read ({exc.strerror})") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"search log {path}: not valid JSON ({exc.msg})") from exc
        try:
            files.append(SearchLogFile.model_validate(raw))
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
                for err in exc.errors()
            )
            raise ValueError(f"search log {path}: {problems}") from exc
    record = SearchLogRecord(
        searched_at=[f.searched_at for f in files],
        queries=[q for f in files for q in f.queries],
        candidates=[c for f in files for c in f.candidates],
    )
    return files, record


def search_log_target_mismatches(
    paths: Sequence[Path],
    files: Sequence[SearchLogFile],
    *,
    hypothesis_id: Optional[str],
    kind: Optional[str],
) -> List[str]:
    """Lines naming every file whose ``hypothesis_id``/``kind`` (when present) disagrees
    with the decision being recorded. ``None`` for an argument skips that check."""
    problems: List[str] = []
    for path, f in zip(paths, files):
        if hypothesis_id is not None and f.hypothesis_id not in (None, hypothesis_id):
            problems.append(
                f"search log {path}: hypothesis_id {f.hypothesis_id!r} does not match "
                f"--hypothesis {hypothesis_id!r}"
            )
        if kind is not None and f.kind not in (None, kind):
            problems.append(
                f"search log {path}: kind {f.kind!r} does not match --kind {kind!r}"
            )
    return problems


__all__ = [
    "SearchCandidate",
    "SearchLogFile",
    "SearchLogRecord",
    "SearchQuery",
    "load_search_logs",
    "search_log_target_mismatches",
]
