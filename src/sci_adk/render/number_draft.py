"""
Propose a number list for a paper (``sci-adk numbers draft``, design/declared-numbers.md
§4.4).

For each distinct literal of each document (in order of first occurrence), the helper
looks for every recorded field whose value equals the literal at its printed precision
(:func:`sci_adk.render.number_checks.printed_match`) and proposes:

  - ONE match  -> ``source`` filled in -- the entry is already a valid
    ``numbers.json`` entry;
  - several    -> ``candidates`` listed and NO source: the helper does not choose
    between two recorded values that print the same way;
  - none       -> ``unresolved: true``: a number with no recorded home, which goes back
    to the experiment stage (or is an identifier, which the author declares).

An ISO-8601 date-time (``2026-10-08T10:03:39Z``) is never matched: it is proposed as
``role: "identifier"``, the only role the checks accept for it, so no source is ever
offered for it or for a piece of it (the tokenizer reads it, like a hex digest, as one
word).

A literal that is part of a NAME is proposed as ``role: "identifier"`` too, never matched:
one glued by a hyphen to a preceding word that is capitalised (``SHA-256``, ``ISO-8601``)
or holds a digit (the ``005`` of ``a06-005``), or one that a file extension follows
(``table-2.csv``). The tokenizer still reads it -- it is a literal verify needs declared --
but a recorded count equal to 256 or 5 is a coincidence. When the same text also stands
as a number elsewhere in the document, that occurrence keeps its own proposal and the
identifier entry names the name as its ``context``. A lower-case word glued by a hyphen
(``criterion-5``) is not a name: it is proposed like any number.

Undecided proposals carry ``where`` -- up to three snippets of the text around the
literal -- and are deliberately NOT valid entries (``candidates`` / ``unresolved`` /
``where`` are unknown keys to the loader), so a draft cannot be copied to
``numbers.json`` without the author deciding them.

Fields searched, in this order (the order candidates are listed in): every Evidence item's
``Result`` scalars, ``ci`` bounds and numeric finding-JSON values; every numeric field of
``spec.json``; every text field of ``spec.json`` in which the literal is written as a
number; every reference year in ``references.bib``. Spec bookkeeping (``id``,
``version``, ``created_at``, ``prior_version_id``, ``spec_id``) is not searched: a paper's
"1" is not the Spec's version.

PURE, deterministic, no model, no network: it saves effort, and the author's choices are
what verify checks.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Mapping, Tuple

from sci_adk.core.numbers import CI_FIELDS, RESULT_SCALAR_FIELDS
from sci_adk.render.number_checks import NumberRecord, printed_match
from sci_adk.render.number_literals import (
    NumberLiteral,
    find_literals,
    find_text_literals,
    is_date_time,
)

_SKIP_KEYS = frozenset({"id", "version", "created_at", "prior_version_id", "spec_id"})
_ADDRESSABLE_KEY_RE = re.compile(r"[^.\[\]]+")
_DOCUMENT_ORDER = ("draft.tex", "si.tex")
_MAX_SNIPPETS = 3
# The word right before a hyphen (anchored at the hyphen), and a file extension right after
# a literal (".xls", ".csv", ".json"; not a decimal point -- a digit cannot start it).
_WORD_BEFORE_HYPHEN_RE = re.compile(r"[A-Za-z0-9]+$")
_FILE_EXTENSION_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,4}(?![A-Za-z0-9])")


def _name_around(literal: NumberLiteral, text: str) -> str | None:
    """The name ``literal`` is part of (see the module docs), as written -- ``SHA-256``,
    ``a06-005.xls``, ``table-2.csv`` -- or ``None`` when it stands as a number."""
    start = literal.start
    extension = _FILE_EXTENSION_RE.match(text, literal.end)
    end = extension.end() if extension else literal.end
    word = None
    if start >= 2 and text[start - 1] == "-":
        word = _WORD_BEFORE_HYPHEN_RE.search(text, 0, start - 1)
    if word is not None and any(c.isalpha() for c in word.group()):
        letters = [c for c in word.group() if c.isalpha()]
        named = (all(c.isupper() for c in letters) and len(letters) >= 2) or any(
            c.isdigit() for c in word.group())
        if named or extension:
            return text[word.start():end]
    if extension:
        head = re.search(r"[\w.-]*$", text[:start])
        return text[start - len(head.group()) if head else start:end]
    return None


def _leaves(node: Any, path: str = "") -> Iterator[Tuple[str, Any]]:
    """``(json path, value)`` for every scalar under ``node`` (bookkeeping keys skipped)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SKIP_KEYS or not _ADDRESSABLE_KEY_RE.fullmatch(str(key)):
                continue
            yield from _leaves(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, f"{path}[{index}]")
    elif path:
        yield path, node


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _recorded_numbers(record: NumberRecord) -> List[Tuple[Dict[str, str], float]]:
    """Every numeric value the record holds, with the source that names it."""
    out: List[Tuple[Dict[str, str], float]] = []
    for item in record.evidence:
        result = item.result
        for name in RESULT_SCALAR_FIELDS:
            value = getattr(result, name, None)
            if value is not None:
                out.append(({"evidence": item.id, "field": name}, float(value)))
        if result.ci:
            for name, bound in zip(CI_FIELDS, result.ci):
                out.append(({"evidence": item.id, "field": name}, float(bound)))
        if result.finding:
            try:
                data = json.loads(result.finding)
            except (json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, dict):
                for path, value in _leaves(data):
                    if _is_number(value):
                        out.append(({"evidence": item.id, "field": f"finding.{path}"},
                                    float(value)))
    for path, value in _leaves(record.spec_json):
        if _is_number(value):
            out.append(({"spec": path}, float(value)))
    return out


def _spec_text_literals(record: NumberRecord) -> List[Tuple[Dict[str, str], set]]:
    """For every text field of the Spec, the literal texts written in it."""
    out: List[Tuple[Dict[str, str], set]] = []
    for path, value in _leaves(record.spec_json):
        if isinstance(value, str):
            texts = {lit.text for lit in find_text_literals(value)}
            if texts:
                out.append(({"spec_text": path}, texts))
    return out


def _candidates(literal: NumberLiteral, numbers, texts, record: NumberRecord) -> List[dict]:
    found: List[dict] = []
    if literal.value is not None:
        found.extend(src for src, value in numbers if printed_match(value, literal))
    found.extend(src for src, written in texts if literal.text in written)
    years = record.bib_years or {}
    for key in sorted(years):
        if (years[key] or "").strip().strip("{}").strip() == literal.text:
            found.append({"bib": key, "field": "year"})
    return [dict(src) for src in found]


def propose_numbers(
    documents: Mapping[str, str],
    record: NumberRecord,
    spec_id: str,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """``(draft, summary)``: the proposed number list and its resolved / ambiguous /
    unresolved / identifier (date-time) counts.

    ``documents`` maps ``draft.tex`` / ``si.tex`` to the text verify will read. The draft
    has the shape of ``numbers.json`` (``{"spec_id", "numbers"}``) with one proposal per
    distinct (text, document), in order of first occurrence.
    """
    numbers = _recorded_numbers(record)
    texts = _spec_text_literals(record)
    order = [d for d in _DOCUMENT_ORDER if d in documents]
    order += sorted(d for d in documents if d not in _DOCUMENT_ORDER)

    proposals: List[Dict[str, Any]] = []
    summary = {"resolved": 0, "ambiguous": 0, "unresolved": 0, "identifier": 0}
    for document in order:
        source_text = documents[document]
        seen: Dict[str, List[NumberLiteral]] = {}
        for lit in find_literals(source_text, document):
            seen.setdefault(lit.text, []).append(lit)
        for text, all_occurrences in seen.items():
            entry: Dict[str, Any] = {"text": text, "document": document}
            if is_date_time(text):
                # The only role a date-time may have (number_checks); never matched.
                entry["role"] = "identifier"
                summary["identifier"] += 1
                proposals.append(entry)
                continue
            names = {id(lit): _name_around(lit, source_text) for lit in all_occurrences}
            occurrences = [lit for lit in all_occurrences if names[id(lit)] is None]
            if not occurrences:
                # Every occurrence is part of a name: an identifier, never matched.
                entry["role"] = "identifier"
                summary["identifier"] += 1
                proposals.append(entry)
                continue
            named = list(dict.fromkeys(n for n in names.values() if n is not None))
            candidates = _candidates(occurrences[0], numbers, texts, record)
            if len(candidates) == 1:
                entry["source"] = candidates[0]
                summary["resolved"] += 1
            else:
                if candidates:
                    entry["candidates"] = candidates
                    summary["ambiguous"] += 1
                else:
                    entry["unresolved"] = True
                    summary["unresolved"] += 1
                entry["where"] = [lit.snippet for lit in occurrences[:_MAX_SNIPPETS]]
            proposals.append(entry)
            for name in named:
                # The same text inside a name: an identifier, located by the name.
                proposals.append({"text": text, "document": document,
                                  "role": "identifier", "context": name})
                summary["identifier"] += 1
    return {"spec_id": spec_id, "numbers": proposals}, summary


__all__ = ["propose_numbers"]
