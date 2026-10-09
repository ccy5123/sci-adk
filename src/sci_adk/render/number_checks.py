"""
The checks over a declared number list (design/declared-numbers.md §4.3).

``runs/<id>/numbers.json`` (:mod:`sci_adk.core.numbers`) states, for every number literal
in the paper, its role and where it comes from. These four PURE checks hold that statement
against the text and the record, and none of them reads meaning:

  1. Coverage (FAIL): every literal the tokenizer finds in ``draft.tex`` / ``si.tex``
     (:mod:`sci_adk.render.number_literals`) is covered by an entry with the same text
     and document -- and, when the entry has a ``context``, lies inside a match of it.
  2. Resolution (FAIL): every source exists, and the value it resolves to, rounded to the
     printed precision of the literal, equals the literal:
     ``|v - literal| <= 0.5 * 10**-d`` (d = decimals printed, 0 for an integer). The
     float slack is relative to that tolerance, so a literal like ``1.2e-12`` is not
     matched by every value within an absolute 1e-9. A derived entry is recomputed from
     its operands by the safe evaluator; a ``spec_text`` literal must be written as a
     standalone number IN the field it names; a citation year must equal the bib field.
     Identifier entries skip resolution.
  3. Stale entries (ADVISORY): an entry whose text (inside its context) no longer occurs
     in its document, or whose document is not rendered.
  4. Identifiers (ADVISORY): every identifier entry is listed, so each exemption is seen.

What replaced what: no year/page/date/version rule (the tokenizer finds, the list
declares), no derived-number policy (one declared computation instead of every pairwise
combination), no +/-0.005 / 1 % tolerance window (printed precision instead), and no Claim
confidence values in what a number may equal.

PURE (data in, problem lines out), deterministic, no LLM, no filesystem. The record arrives
as a :class:`NumberRecord` the caller builds (verify reads the run; this module reads
nothing). Like its siblings in ``render/`` it imports ``sci_adk.core`` and other render
modules only.

Reference: design/declared-numbers.md, src/sci_adk/core/numbers.py (the type),
src/sci_adk/render/declaration_checks.py (the sibling checks over the conclusion list).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.numbers import (
    CI_FIELDS,
    FINDING_PREFIX,
    NUMBERS_FILE,
    NumberEntry,
    NumberList,
    NumberSource,
    evaluate_formula,
    walk_json,
)
from sci_adk.render.number_literals import (
    NumberLiteral,
    canonical_text,
    find_literals,
    find_text_literals,
    parse_literal_text,
)
from sci_adk.render.paper import _latex_sanitize_prose

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")


@dataclass(frozen=True)
class NumberRecord:
    """What a number may come from: the run's record, as the caller read it.

    Attributes:
        spec_json: the frozen ``spec.json`` as raw JSON (paths address this, as written).
        evidence: the recorded Evidence items.
        bib_years: reference key -> its ``year`` field, from the run's ``references.bib``;
            ``None`` when the run has no bibliography (a citation entry then fails).
    """

    spec_json: Mapping[str, Any] = field(default_factory=dict)
    evidence: Sequence[EvidenceItem] = ()
    bib_years: Optional[Mapping[str, Optional[str]]] = None


class SourceError(ValueError):
    """A source that does not resolve to a value; the message says why."""


# -- values -------------------------------------------------------------------

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fmt_value(value: float) -> str:
    """A recorded value as a message shows it: integers bare, floats in full."""
    value = float(value)
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def printed_match(value: float, literal: NumberLiteral) -> bool:
    """True iff ``value`` rounded to the literal's printed precision equals the literal."""
    if literal.value is None or literal.decimals is None:
        return False
    tolerance = 0.5 * 10.0 ** (-literal.decimals)
    return abs(float(value) - literal.value) <= tolerance * (1 + 1e-9)


def _finding_data(item: EvidenceItem, path: str) -> Any:
    finding = item.result.finding
    if not finding:
        raise SourceError(f"Evidence {item.id!r} records no finding")
    try:
        data = json.loads(finding)
    except (json.JSONDecodeError, TypeError):
        raise SourceError(
            f"Evidence {item.id!r} has a prose finding, not JSON, so it has no {path!r} -- "
            f"the experiment stage records the value as a named number in the finding JSON"
        ) from None
    if not isinstance(data, dict):
        raise SourceError(f"Evidence {item.id!r}'s finding is JSON but not an object")
    return data


def evidence_value(item: EvidenceItem, field_name: str) -> float:
    """The numeric value an Evidence field holds (``point`` ... ``ci[0]`` ...
    ``finding.<key>``).

    Raises:
        SourceError: the field is empty, the finding is not JSON, the key is absent, or
            the value is not a number.
    """
    result = item.result
    if field_name in CI_FIELDS:
        if not result.ci:
            raise SourceError(f"Evidence {item.id!r} records no ci")
        return float(result.ci[0 if field_name == "ci[0]" else 1])
    if field_name.startswith(FINDING_PREFIX):
        path = field_name[len(FINDING_PREFIX):]
        data = _finding_data(item, path)
        try:
            value = walk_json(data, path)
        except KeyError as exc:
            raise SourceError(
                f"Evidence {item.id!r}'s finding has no {path!r} ({exc.args[0]})"
            ) from None
        if not _is_number(value):
            raise SourceError(
                f"Evidence {item.id!r}'s finding {path!r} is not a number ({value!r})"
            )
        return float(value)
    value = getattr(result, field_name, None)
    if value is None:
        raise SourceError(f"Evidence {item.id!r} records no {field_name}")
    return float(value)


def resolve_value(source: NumberSource, record: NumberRecord,
                  by_id: Optional[Mapping[str, EvidenceItem]] = None) -> float:
    """The numeric value an evidence or spec source resolves to.

    Raises:
        SourceError: the source does not resolve (named Evidence or path absent, value
            not a number), or it is a kind with no single numeric value.
    """
    if by_id is None:
        by_id = {item.id: item for item in record.evidence}
    if source.kind == "evidence":
        item = by_id.get(source.evidence)
        if item is None:
            raise SourceError(f"no Evidence item {source.evidence!r} in the record")
        return evidence_value(item, source.field)
    if source.kind == "spec":
        try:
            value = walk_json(record.spec_json, source.spec)
        except KeyError as exc:
            raise SourceError(f"spec.json has no {source.spec!r} ({exc.args[0]})") from None
        if not _is_number(value):
            raise SourceError(f"spec.json {source.spec!r} is not a number ({value!r})")
        return float(value)
    raise SourceError(f"a {source.kind} source has no single numeric value")


# -- shared helpers -------------------------------------------------------------

def _label(index: int, entry: NumberEntry) -> str:
    return f"numbers: numbers[{index}] ({entry.text!r}, {entry.document})"


def _blank_comments(text: str) -> str:
    return _COMMENT_RE.sub(lambda m: " " * len(m.group(0)), text)


def _context_spans(context: str, document_text: str) -> List[Tuple[int, int]]:
    """Every match of ``context`` in the document, whitespace-insensitive.

    Tried as written AND as render writes prose (``R²`` -> ``R$^2$``, ``95%`` -> ``95\\%``),
    so a context may be quoted from the rendered ``.tex`` or from the prose JSON.
    """
    haystack = _blank_comments(document_text)
    spans: List[Tuple[int, int]] = []
    for variant in dict.fromkeys((context.strip(), _latex_sanitize_prose(context.strip()))):
        chunks = variant.split()
        if not chunks:
            continue
        pattern = r"\s+".join(re.escape(chunk) for chunk in chunks)
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, haystack))
    return spans


def _inside(literal: NumberLiteral, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(start <= literal.start and literal.end <= end for start, end in spans)


def _literals(documents: Mapping[str, str]) -> Dict[str, List[NumberLiteral]]:
    return {name: find_literals(text, name) for name, text in documents.items()}


def _entries_by_key(numbers: NumberList) -> Dict[Tuple[str, str], List[NumberEntry]]:
    by_key: Dict[Tuple[str, str], List[NumberEntry]] = {}
    for entry in numbers.numbers:
        by_key.setdefault((canonical_text(entry.text), entry.document), []).append(entry)
    return by_key


# -- 1. coverage ----------------------------------------------------------------

def coverage_problems(numbers: NumberList, documents: Mapping[str, str]) -> List[str]:
    """Check 1: every literal of every present document is covered by an entry.

    ``documents`` maps a document name (``draft.tex`` / ``si.tex``) to its text; a
    document that is not rendered is simply absent. One problem line per uncovered
    (text, document), with the occurrence count and the first snippet.
    """
    by_key = _entries_by_key(numbers)
    problems: List[str] = []
    for document, literals in _literals(documents).items():
        text = documents[document]
        spans_cache: Dict[str, List[Tuple[int, int]]] = {}
        missing: Dict[str, List[NumberLiteral]] = {}
        outside: Dict[str, List[NumberLiteral]] = {}
        for lit in literals:
            entries = by_key.get((lit.text, document), [])
            if not entries:
                missing.setdefault(lit.text, []).append(lit)
                continue
            if any(e.context is None for e in entries):
                continue
            covered = False
            for e in entries:
                spans = spans_cache.setdefault(e.context, _context_spans(e.context, text))
                if _inside(lit, spans):
                    covered = True
                    break
            if not covered:
                outside.setdefault(lit.text, []).append(lit)
        for value, lits in missing.items():
            where = (f"{len(lits)} occurrences; first: \"{lits[0].snippet}\""
                     if len(lits) > 1 else f"\"{lits[0].snippet}\"")
            problems.append(
                f"numbers: {document} states {value} ({where}) with no entry in "
                f"{NUMBERS_FILE} -- add it with the recorded source it comes from, or role "
                f"\"identifier\" if it is not a quantity."
            )
        for value, lits in outside.items():
            problems.append(
                f"numbers: {document} states {value} {len(lits)} time(s) outside the "
                f"context of every entry for it (first: \"{lits[0].snippet}\") -- add an "
                f"entry whose context covers these, or widen a context."
            )
    return problems


# -- 2. resolution ---------------------------------------------------------------
# One helper per role; each returns why the entry does not resolve, or None.

def _citation_reason(source: NumberSource, literal: NumberLiteral,
                     record: NumberRecord) -> Optional[str]:
    if record.bib_years is None:
        return (f"the run has no references.bib (looked in literature/ and "
                f"artifacts/literature/), so the year of {source.bib!r} cannot be read")
    if source.bib not in record.bib_years:
        return f"references.bib has no entry {source.bib!r}"
    year = (record.bib_years[source.bib] or "").strip().strip("{}").strip()
    if not year:
        return f"references.bib entry {source.bib!r} has no year"
    if year != literal.text:
        return f"the year of {source.bib!r} is {year}, not {literal.text}"
    return None


def _spec_text_reason(source: NumberSource, literal: NumberLiteral,
                      record: NumberRecord) -> Optional[str]:
    try:
        value = walk_json(record.spec_json, source.spec_text)
    except KeyError as exc:
        return f"spec.json has no {source.spec_text!r} ({exc.args[0]})"
    if not isinstance(value, str):
        return (f"spec.json {source.spec_text!r} is not a text field (it is a "
                f"{type(value).__name__}) -- name one text field, e.g. with [N] for a "
                f"list item")
    if literal.text not in {lit.text for lit in find_text_literals(value)}:
        return f"{literal.text} is not written as a number in spec.json {source.spec_text!r}"
    return None


def _recorded_reason(source: NumberSource, literal: NumberLiteral, record: NumberRecord,
                     by_id: Mapping[str, EvidenceItem]) -> Optional[str]:
    try:
        value = resolve_value(source, record, by_id)
    except SourceError as exc:
        return str(exc)
    if printed_match(value, literal):
        return None
    where = (f"{source.field} of Evidence {source.evidence!r}"
             if source.kind == "evidence" else f"spec.json {source.spec!r}")
    return f"{where} is {fmt_value(value)}, which does not print as {literal.text}"


def _derived_reason(entry: NumberEntry, literal: NumberLiteral, record: NumberRecord,
                    by_id: Mapping[str, EvidenceItem]) -> Optional[str]:
    values: Dict[str, float] = {}
    for name, operand in (entry.operands or {}).items():
        try:
            values[name] = resolve_value(operand, record, by_id)
        except SourceError as exc:
            return f"operand {name!r}: {exc}"
    try:
        computed = evaluate_formula(entry.formula, values)
    except ValueError as exc:
        return str(exc)
    if printed_match(computed, literal):
        return None
    return f"{entry.formula} gives {fmt_value(computed)}, which does not print as {literal.text}"


def _resolution_reason(entry: NumberEntry, record: NumberRecord,
                       by_id: Mapping[str, EvidenceItem]) -> Optional[str]:
    literal = parse_literal_text(entry.text)
    if literal is None:
        found = [lit.text for lit in find_text_literals(canonical_text(entry.text))]
        return (f"{entry.text!r} is not one number as the document is read (the tokenizer "
                f"reads {', '.join(found) if found else 'no number'}) -- write the literal "
                f"alone, without a unit or '%'")
    if entry.role == "identifier":
        return None
    if entry.role == "citation":
        return _citation_reason(entry.source, literal, record)
    if entry.source is not None and entry.source.kind == "spec_text":
        return _spec_text_reason(entry.source, literal, record)
    if literal.value is None:
        return (f"{literal.text} is joined digit groups, not one number -- declare it role "
                f"\"identifier\", or give a spec_text source where it is written")
    if entry.role == "recorded":
        return _recorded_reason(entry.source, literal, record, by_id)
    return _derived_reason(entry, literal, record, by_id)


def resolution_problems(numbers: NumberList, record: NumberRecord) -> List[str]:
    """Check 2: every entry's source resolves and matches the literal at printed precision.

    One problem line per failing entry, naming its index, text and document. Identifier
    entries are not resolved (their text must still be one literal).
    """
    by_id = {item.id: item for item in record.evidence}
    problems = []
    for index, entry in enumerate(numbers.numbers):
        reason = _resolution_reason(entry, record, by_id)
        if reason is not None:
            problems.append(f"{_label(index, entry)}: {reason}.")
    return problems


# -- 3. stale entries and 4. identifiers (advisory) --------------------------------

def stale_entries(numbers: NumberList, documents: Mapping[str, str]) -> List[str]:
    """Check 3 (advisory): entries that no longer describe anything in the document."""
    literals = _literals(documents)
    lines: List[str] = []
    absent: Dict[str, int] = {}
    for index, entry in enumerate(numbers.numbers):
        if entry.document not in documents:
            absent[entry.document] = absent.get(entry.document, 0) + 1
            continue
        parsed = parse_literal_text(entry.text)
        if parsed is None:
            continue  # resolution reports a malformed text
        matches = [lit for lit in literals[entry.document] if lit.text == parsed.text]
        if entry.context is not None:
            spans = _context_spans(entry.context, documents[entry.document])
            matches = [lit for lit in matches if _inside(lit, spans)]
        if not matches:
            where = " inside its context" if entry.context is not None else ""
            lines.append(
                f"{_label(index, entry)} matches no number in {entry.document}{where} -- "
                f"remove it, or correct its text or context."
            )
    for document, count in absent.items():
        noun = "entry names" if count == 1 else "entries name"
        lines.append(
            f"numbers: {count} {noun} {document}, which is not in paper/ (not rendered "
            f"yet?) -- not checked against the text."
        )
    return lines


def identifier_listing(numbers: NumberList) -> List[str]:
    """Check 4 (advisory): one line per identifier entry -- every exemption is visible."""
    lines = []
    for entry in numbers.numbers:
        if entry.role != "identifier":
            continue
        context = f" (context: \"{entry.context}\")" if entry.context else ""
        lines.append(
            f"numbers: identifier {entry.text} in {entry.document}{context} -- listed, not "
            f"checked against the record."
        )
    return lines


# @MX:NOTE: [AUTO] The single entry point verify calls for a run that HAS numbers.json
#   (design/declared-numbers.md §5): it REPLACES the pattern audit for that run. Failures
#   (coverage, resolution) gate; stale entries and the identifier listing are advisory.
#   Pure: the caller passes the rendered documents and the record it read.
def number_list_checks(
    numbers: NumberList,
    documents: Mapping[str, str],
    record: NumberRecord,
) -> Tuple[List[str], List[str]]:
    """All four checks: ``(problems, advisory)``.

    ``problems`` (coverage + resolution) fail verify; ``advisory`` (stale entries +
    the identifier listing) is surfaced and never gates.
    """
    problems = coverage_problems(numbers, documents) + resolution_problems(numbers, record)
    advisory = stale_entries(numbers, documents) + identifier_listing(numbers)
    return problems, advisory


__all__ = [
    "NumberRecord",
    "SourceError",
    "coverage_problems",
    "evidence_value",
    "fmt_value",
    "identifier_listing",
    "number_list_checks",
    "printed_match",
    "resolution_problems",
    "resolve_value",
    "stale_entries",
]
