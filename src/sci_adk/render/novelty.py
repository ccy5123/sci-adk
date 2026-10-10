"""
Record-fidelity novelty/priority gate for agent-authored paper prose (N2 render +
N3 verify; design/literature-acquisition.md §"Render-time novelty gate").

The paper (belief) must never assert a novelty/priority claim the record does not back --
the same family as the evidence-validity gate (synthetic data cannot make a SUPPORTED
empirical claim), the paper-consistency gate (a dangling ``\\ref`` fails verify), and the
factref fidelity gate (``\\evval``/``\\status``, ``render/factref.py``). This module is the
novelty member of that family.

A novelty claim is asserted ONLY via the explicit markup, in the AUTHORED prose
(``prose.json`` / ``si.json``) ::

    \\novelty{result|method}{hyp-id}{text}

It is NEVER inferred from free prose -- no keyword scan, no NLP. This mirrors the
``\\ref``<->``\\label`` gate: the engine checks markup against the record deterministically.

Rendered source is PLAIN (no macro). What is submitted is the ``.tex`` source, which may
carry no markup a reviewer would not recognize, so the renderer replaces each markup span
with the sentence alone plus a scope taken FROM the record, and hands the binding
``{document, kind, hypothesis, sentence}`` to the compiler, which writes it to a side file
that is never submitted (``runs/<id>/novelty_sentences.json``, beside
``declarations.json``). ``sci-adk verify`` re-derives every binding in that file, checks
that its sentence ends with the scope the record gives now, and that the sentence is still
in its document (:func:`find_unbacked_novelty_sentences`). For
each markup / binding the engine re-derives the per-{hyp, kind} novelty claim status via the
SINGLE source of truth :func:`sci_adk.core.validity.derive_novelty_status` (never the
recorded claim):

  - **SUPPORTED** -> the rendered sentence gets the scope of the search behind it:
    ``<text> (no such report was found in searches of <indexes> on <date>)`` -- the
    indexes that ANSWERED in the backing ``found_nothing`` decisions' search logs and the
    date(s) of those searches (an absence claim is intrinsically bounded by the search that
    produced it). With no search log on record the scope is ``(as of <date>)``, the date of
    the latest backing decision. Never a stock softener.
  - **NOT SUPPORTED / unknown hyp / bad kind** -> HARD fail: ``ValueError`` at render time
    (naming {hyp, kind} + the remedy), and a non-zero ``sci-adk verify``.

Backward compatibility: drafts rendered before the plain-sentence change carry the markup
itself (and a preamble ``\\newcommand{\\novelty}[3]{#3}``). ``verify`` still re-scans every
``.tex`` for that markup (:func:`find_unsupported_novelty`), so such a draft is checked as
before.

This module is PURE: it imports ``sci_adk.core`` ONLY (the F4 kernel seam -- no adapter, no
loop, no LLM, no fs/network), and is deterministic + fail-loud, exactly like
``render/factref.py``.

Honest limit -- the ``\\novelty`` TEXT (3rd arg) is FLAT (documented, like ``factref.py`` /
``consistency.py``). The 3rd arg accepts plain prose ONLY:

  - NO nested commands -- a ``\\ref`` / ``\\cite`` (or any other ``\\command``) inside the
    span is escaped to literal text, NOT rendered. To cite or cross-reference a novelty
    claim, put the ``\\cite`` / ``\\ref`` OUTSIDE the ``\\novelty{...}{...}{...}`` span.
  - NO braces in the text -- the regex's ``[^{}]*`` text group stops at the first ``{`` or
    ``}``, so a ``{`` inside the intended text would truncate the match (or break it). Keep
    the text brace-free.

And, like the ``\\ref`` gate, a "first" written as plain prose (no ``\\novelty`` command) is
not governed -- the discipline is "assert novelty via the command". The same holds for a
rendered sentence whose binding was removed from the side file: the side file is the
binding, as the surviving markup used to be.

Reference: design/literature-acquisition.md, src/sci_adk/render/factref.py (the sibling
record-fidelity, fail-loud render gate), src/sci_adk/core/validity.py
(``derive_novelty_status`` -- the single source of truth), src/sci_adk/core/search_log.py
(the search log the scope is read from).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from sci_adk.core.claim import ClaimStatus
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import Spec
from sci_adk.core.validity import derive_novelty_status

# Render-side match: ``\novelty{<kind>}{<hyp>}{<text>}`` -- three single-level brace groups
# (none containing a nested brace, mirroring factref's ``[^{}]``). The kind is captured
# LOOSELY (``[^{}]*``) so a BAD kind (e.g. ``\novelty{resul}{...}{...}``) still MATCHES and
# fails loud in :func:`novelty_scope_suffix`, rather than silently slipping past the regex.
# The hyp is non-empty (an id is never blank); the text may be empty.
#
# WHITESPACE TOLERANCE (the tamper-boundary closure): LaTeX skips whitespace after a control
# word and between brace-delimited arguments, so ``\novelty {r}{h}{t}``, ``\novelty\n{r}{h}{t}``
# and ``\novelty{r} {h}{t}`` ALL expand via a ``\newcommand`` and PRINT. The regex therefore
# allows ``\s*`` in exactly the spots LaTeX does -- after the command name and between the
# arg groups -- so a whitespace-spaced ``\novelty`` cannot render an unbacked priority claim
# AND evade the gate. The ``\s*`` are OUTSIDE the captured groups, so the captured
# kind/hyp/text are unchanged (no leading/trailing whitespace leaks into the id).
NOVELTY_RENDER_RE = re.compile(
    r"\\novelty\s*\{([^{}]*)\}\s*\{([^{}]+)\}\s*\{([^{}]*)\}"
)

# Verify-side scan of a persisted ``.tex`` (drafts rendered before the plain-sentence
# change, or hand-edited ones): capture (kind, hyp), IGNORE the 3rd arg. Anchored on the
# literal ``\novelty ...{...}{...}{`` (whitespace-tolerant, same spots as the render regex)
# so it captures every assertion LaTeX would render. It does NOT match the preamble
# ``\newcommand{\novelty}[3]{#3}`` -- there ``\novelty`` is followed immediately by ``}``
# (the close of the ``\newcommand`` name group), and ``\s*\{`` requires a ``{`` next.
NOVELTY_SCAN_RE = re.compile(r"\\novelty\s*\{([^{}]*)\}\s*\{([^{}]+)\}\s*\{")

# The preamble macro drafts rendered BEFORE the plain-sentence change carry (it made LaTeX
# print only the text arg). No longer emitted; kept so old sources can be recognised.
NOVELTY_NEWCOMMAND = r"\newcommand{\novelty}[3]{#3}"

# The side file (beside spec.json / declarations.json, never submitted) that binds each
# rendered novelty sentence to the {kind, hypothesis} the record must back.
NOVELTY_SENTENCES_FILE = "novelty_sentences.json"

_VALID_KINDS = ("result", "method")

# A LaTeX-EMIT-SAFE hypothesis id, checked only where the id IS in the ``.tex``: the
# surviving markup of a draft rendered before the plain-sentence change. An id there with a
# LaTeX tokenization-special would silently corrupt the source (e.g. ``%`` comments out the
# rest of the line) while the scan still read it, so such markup is reported as a problem.
# ``_`` ``-`` ``.`` ``:`` are inert in the dropped arg-2 position; ``%`` ``\`` ``#`` ``$``
# ``&`` ``~`` ``^`` ``{`` ``}`` and whitespace are not. A rendered plain sentence never
# carries the id, so the render path does not need this check.
_EMIT_SAFE_HYP_RE = re.compile(r"[A-Za-z0-9._:\-]+")

# How a recorded index name is printed in the scope. Keys are lower-cased with spaces,
# ``_`` and ``-`` removed; an index not listed is printed as recorded (and escaped by the
# caller like any other text). Field-neutral: general academic indexes plus the web.
_WEB = "the web"
_INDEX_NAMES: Dict[str, str] = {
    "openalex": "OpenAlex",
    "arxiv": "arXiv",
    "crossref": "Crossref",
    "semanticscholar": "Semantic Scholar",
    "s2": "Semantic Scholar",
    "pubmed": "PubMed",
    "europepmc": "Europe PMC",
    "openreview": "OpenReview",
    "googlescholar": "Google Scholar",
    "scopus": "Scopus",
    "webofscience": "Web of Science",
    "dblp": "dblp",
    "web": _WEB,
    "websearch": _WEB,
    "openweb": _WEB,
}

_COMMENT_RE = re.compile(r"(?<!\\)%.*?$", re.MULTILINE)
_WS_RE = re.compile(r"\s+")

# The shortest sentence render writes: one character of claim text (an empty text is
# refused, :func:`require_novelty_text`) plus the shortest scope, " (as of YYYY-MM-DD)".
# A bound sentence shorter than this did not come from render.
_MIN_SENTENCE_CHARS = len("x (as of 2026-01-01)")


@dataclass(frozen=True)
class NoveltySentence:
    """One rendered novelty sentence and the {kind, hypothesis} the record must back.

    ``sentence`` is the text exactly as it appears in ``document`` (the author's text,
    escaped as the renderer escapes it, plus the record-derived scope), so ``verify`` can
    find it there.
    """

    document: str
    kind: str
    hypothesis_id: str
    sentence: str

    def to_json(self) -> Dict[str, str]:
        return {
            "document": self.document,
            "kind": self.kind,
            "hypothesis_id": self.hypothesis_id,
            "sentence": self.sentence,
        }


def has_novelty_markup(text: str) -> bool:
    """True iff ``text`` contains at least one ``\\novelty{kind}{hyp}{`` assertion.

    Uses the verify-side scan (it does not match the preamble ``\\newcommand``). Pure.
    """
    return NOVELTY_SCAN_RE.search(text) is not None


def _found_nothing_decisions(
    hyp_id: str, kind: str, novelty_decisions: Sequence[EvidenceItem]
) -> List[EvidenceItem]:
    """The ``found_nothing`` NOVELTY_DECISIONs for one {hyp, kind}, oldest first.

    The same predicate as :func:`derive_novelty_status`'s SUPPORTED branch. Ordered by the
    append-only ``created_at`` (the decision's own timestamp), ties broken by ``ev.id``.
    """
    qualifying = [
        ev
        for ev in novelty_decisions
        if ev.kind == EvidenceKind.NOVELTY_DECISION
        and ev.literature_decision is not None
        and ev.literature_decision.hypothesis_id == hyp_id
        and ev.literature_decision.kind == kind
        and ev.literature_decision.outcome == "found_nothing"
    ]
    return sorted(qualifying, key=lambda ev: (ev.created_at, ev.id))


def _index_display_name(index: str) -> str:
    key = re.sub(r"[\s_\-]", "", index.lower())
    return _INDEX_NAMES.get(key, index.strip())


def _utc_date(timestamp: str) -> str:
    """``YYYY-MM-DD`` (UTC) of a search-log timestamp (validated UTC ISO-8601 on record)."""
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _join_names(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _search_scope(decisions: Sequence[EvidenceItem]) -> Optional[str]:
    """The scope sentence from the search logs of ``decisions`` (one {hyp, kind}).

    Names each index that answered at least one query (a failed index was not searched),
    once (case-insensitively, as first spelled), in order of first appearance -- the web
    last -- and the date(s) of the searches
    that produced those answers. ``None`` when no decision carries a log in which an index
    answered (the caller then falls back to the decision date).
    """
    names: List[str] = []
    seen: set[str] = set()  # case-folded: "InspireHEP" and "inspirehep" are one index
    dates: set[str] = set()
    for ev in decisions:
        log = ev.provenance.search_log
        if log is None:
            continue
        answered = [q.index for q in log.queries if q.status == "ok"]
        if not answered:
            continue
        for index in answered:
            name = _index_display_name(index)
            if name.casefold() not in seen:
                seen.add(name.casefold())
                names.append(name)
        dates.update(_utc_date(t) for t in log.searched_at)
    if not names:
        return None
    names = [n for n in names if n != _WEB] + [n for n in names if n == _WEB]
    first, last = min(dates), max(dates)
    when = f"on {first}" if first == last else f"between {first} and {last}"
    return f" (no such report was found in searches of {_join_names(names)} {when})"


# @MX:ANCHOR: [AUTO] the one novelty re-derivation shared by the render gate
#   (novelty_scope_suffix), the old-markup verify scan and the side-file verify check.
# @MX:REASON: [AUTO] render and verify must refuse exactly the same assertions; a change here
#   changes which novelty sentences can reach a paper and which ones verify fails.
def _require_backed(
    kind: str,
    hyp_id: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
) -> List[EvidenceItem]:
    """Re-derive one {hyp, kind} assertion; return its backing ``found_nothing`` decisions.

    Raises:
        ValueError: ``kind`` not in {result, method}; ``hyp_id`` absent from ``spec``; or
            the {hyp, kind} novelty claim does not re-derive SUPPORTED from the record.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"\\novelty has an invalid kind '{kind}' (must be 'result' or 'method') "
            f"for hypothesis '{hyp_id}' -- fix the markup."
        )
    hypothesis = next((h for h in spec.hypotheses if h.id == hyp_id), None)
    if hypothesis is None:
        raise ValueError(
            f"\\novelty{{{kind}}}{{{hyp_id}}} cites unknown hypothesis '{hyp_id}' -- a "
            f"novelty assertion must reference a real Spec hypothesis."
        )
    status = derive_novelty_status(hypothesis, kind, novelty_decisions)
    if status != ClaimStatus.SUPPORTED:
        raise ValueError(
            f"{kind}-novelty for '{hyp_id}' is asserted in the paper but NOT supported by "
            f"the record (no recorded found_nothing prior-art search for this {{hyp, "
            f"kind}}). Remedy: record one via `sci-adk novelty <run> --hypothesis "
            f"{hyp_id} --kind {kind} --searched ... --outcome found-nothing`, or remove "
            f"the \\novelty assertion."
        )
    return _found_nothing_decisions(hyp_id, kind, novelty_decisions)


def novelty_scope_suffix(
    kind: str,
    hyp_id: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
) -> str:
    """The record-derived scope for one ``\\novelty{kind}{hyp}{...}`` assertion.

    Re-derives the {hyp, kind} novelty status via the SINGLE source of truth
    :func:`sci_adk.core.validity.derive_novelty_status` (NEVER the recorded claim) and:

      - SUPPORTED -> returns the scope of the search behind it (leading space; plain text,
        to be escaped by the caller like any other text):
        `` (no such report was found in searches of OpenAlex, arXiv and Crossref on
        2026-10-08)`` -- the indexes that answered in the backing ``found_nothing``
        decisions' search logs, and the date (or ``between <first> and <last>``) of those
        searches. When no backing decision has a log in which an index answered:
        `` (as of <YYYY-MM-DD>)``, the date of the LATEST backing decision.
      - anything else (unsupported / unknown hyp / bad kind) -> raises ``ValueError``
        naming {hyp, kind} + the remedy (the HARD fail; the engine never softens).

    PURE + FAIL-LOUD, the same contract as ``factref._resolve_*``.

    Raises:
        ValueError: ``kind`` not in {result, method}; ``hyp_id`` absent from ``spec``; or
            the {hyp, kind} novelty claim does not re-derive SUPPORTED from the record.
    """
    backing = _require_backed(kind, hyp_id, spec, novelty_decisions)
    scope = _search_scope(backing)
    if scope is not None:
        return scope
    # SUPPORTED <=> backing is non-empty (same predicate as derive_novelty_status). The
    # decision's created_at is the timestamp of the recorded search.
    return f" (as of {backing[-1].created_at.strftime('%Y-%m-%d')})"


def require_novelty_text(kind: str, hyp_id: str, text: str) -> None:
    """Refuse a ``\\novelty{kind}{hyp}{}`` whose text is empty or whitespace.

    The claim belongs INSIDE the markup: an empty span renders the scope alone, bound to
    nothing the reader can see as a claim, and the claim written around it is ungoverned.
    Verify refuses the same binding (a sentence that is only its scope). PURE.

    Raises:
        ValueError: ``text`` is empty after stripping whitespace.
    """
    if not text.strip():
        raise ValueError(
            f"\\novelty{{{kind}}}{{{hyp_id}}} has no text -- the claim goes inside the "
            f"markup: \\novelty{{{kind}}}{{{hyp_id}}}{{<the sentence that claims it>}}."
        )


def find_unsupported_novelty(
    tex: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
) -> list[str]:
    """Return one problem line per ``\\novelty`` markup in ``tex`` that fails the gate.

    PURE. For sources that still CARRY the markup -- drafts rendered before the
    plain-sentence change, or a hand-edited ``.tex``. Re-scans for every
    ``\\novelty{kind}{hyp}{`` and re-runs the SAME record re-derivation as the renderer; a
    failure -> a one-line problem (``<kind>-novelty for '<hyp>': <reason>``). A markup whose
    hypothesis id is not LaTeX-emit-safe is a problem too: the id is IN this source, where a
    tokenization-special corrupts it. De-duplicated, sorted for a stable report. Clean tex
    (every assertion supported, or none) -> ``[]``.
    """
    problems: set[str] = set()
    for match in NOVELTY_SCAN_RE.finditer(tex):
        kind, hyp_id = match.group(1), match.group(2)
        if _EMIT_SAFE_HYP_RE.fullmatch(hyp_id) is None:
            problems.add(
                f"{kind}-novelty for '{hyp_id}': the hypothesis id is not LaTeX-emit-safe "
                f"(allowed: letters, digits, '.', '_', ':', '-'); in this markup a "
                f"tokenization-special (%, backslash, #, $, &, ~, ^, braces, whitespace) "
                f"corrupts the document -- re-render the paper, which writes the plain "
                f"sentence."
            )
            continue
        try:
            _require_backed(kind, hyp_id, spec, novelty_decisions)
        except ValueError as exc:
            problems.add(f"{kind}-novelty for '{hyp_id}': {exc}")
    return sorted(problems)


def _normalize(text: str) -> str:
    """Collapse whitespace runs (LaTeX re-wraps prose freely); an EXACT match otherwise."""
    return _WS_RE.sub(" ", text).strip()


def _scope_problem(where: str, needle: str, scope: str) -> Optional[str]:
    """Why the whitespace-normalized ``needle`` does not end with ``scope``, or ``None``.

    ``scope`` is the normalized, escaped suffix the record gives now. The renderer writes
    ``<text><suffix>`` with a leading space in the suffix, so a valid sentence is ``scope``
    itself (no text -- a problem of its own) or ends with ``" " + scope``.
    """
    if needle != scope and not needle.endswith(" " + scope):
        return (
            f'{where}: the scope at the end of its sentence is not the search on record, '
            f'which gives "{scope}" -- re-render the paper, which rewrites the scope.'
        )
    if not needle[: len(needle) - len(scope)].strip():
        return (
            f"{where}: its sentence is only the scope, with no claim text -- put the claim "
            f"inside the \\novelty text and re-render."
        )
    return None


def find_unbacked_novelty_sentences(
    sentences: Sequence[NoveltySentence],
    documents: Mapping[str, str],
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
    *,
    escape: Callable[[str], str],
) -> Dict[str, List[str]]:
    """Problems with the rendered novelty sentences, keyed by document name.

    PURE. ``documents`` maps a document name (``draft.tex`` / ``si.tex``) to its source;
    ``escape`` is the renderer's LaTeX escaper (``paper._latex_sanitize``), which the
    renderer applied to the scope -- passed in because this module imports
    ``sci_adk.core`` only. For each binding:

      - its {kind, hypothesis} must re-derive SUPPORTED from the record (the same
        re-derivation as the renderer; an unbacked one is a problem, as the surviving
        markup was);
      - its sentence must end with the scope the record gives NOW
        (:func:`novelty_scope_suffix`, escaped), after some claim text. A different scope
        means the search behind the sentence is not the one it names (a later search, or
        a removed decision with another still backing the claim): re-render;
      - its document must exist, and its sentence must still be in it (whitespace-
        normalized, LaTeX comments stripped). A miss means the sentence was edited or
        removed after render, so the binding no longer describes the paper.

    De-duplicated and sorted per document; ``{}`` when every binding holds.
    """
    problems: Dict[str, set[str]] = {}
    for entry in sentences:
        where = f"{entry.kind}-novelty for '{entry.hypothesis_id}'"
        needle = _normalize(entry.sentence)
        try:
            suffix = novelty_scope_suffix(
                entry.kind, entry.hypothesis_id, spec, novelty_decisions
            )
        except ValueError as exc:  # the message already names {kind, hypothesis}
            problems.setdefault(entry.document, set()).add(str(exc))
        else:
            scope_problem = _scope_problem(where, needle, _normalize(escape(suffix)))
            if scope_problem is not None:
                problems.setdefault(entry.document, set()).add(scope_problem)
        source = documents.get(entry.document)
        if source is None:
            problems.setdefault(entry.document, set()).add(
                f"{where}: its sentence is bound to {entry.document}, which does not exist "
                f"-- re-render the paper."
            )
            continue
        if needle not in _normalize(_COMMENT_RE.sub("", source)):
            excerpt = needle if len(needle) <= 70 else needle[:67] + "..."
            problems.setdefault(entry.document, set()).add(
                f'{where}: the sentence bound to it is no longer in {entry.document} '
                f'("{excerpt}") -- it was edited or removed after render. Edit the '
                f"\\novelty text in the authored prose and re-render, which re-binds it."
            )
    return {doc: sorted(lines) for doc, lines in problems.items()}


def novelty_sentences_payload(
    spec_id: str, sentences: Sequence[NoveltySentence]
) -> Dict[str, Any]:
    """The JSON object written to :data:`NOVELTY_SENTENCES_FILE`."""
    return {"spec_id": spec_id, "sentences": [s.to_json() for s in sentences]}


def parse_novelty_sentences(raw: Any, spec_id: str) -> List[NoveltySentence]:
    """Read the :data:`NOVELTY_SENTENCES_FILE` object back (fail-closed).

    A bound sentence shorter than :data:`_MIN_SENTENCE_CHARS` (whitespace-normalized) is
    refused: render never writes one, and an empty or near-empty needle would be found in
    any document.

    Raises:
        ValueError: not an object of the written shape, an unknown or missing field, a
            non-string value, an empty or very short sentence, or a ``spec_id`` other than
            ``spec_id``.
    """
    if not isinstance(raw, dict) or set(raw) != {"spec_id", "sentences"}:
        raise ValueError("expected an object with exactly 'spec_id' and 'sentences'")
    if raw["spec_id"] != spec_id:
        raise ValueError(
            f"written for Spec '{raw['spec_id']}', but this run is Spec '{spec_id}'"
        )
    if not isinstance(raw["sentences"], list):
        raise ValueError("'sentences' must be a list")
    fields = ("document", "kind", "hypothesis_id", "sentence")
    out: List[NoveltySentence] = []
    for i, item in enumerate(raw["sentences"]):
        if (
            not isinstance(item, dict)
            or set(item) != set(fields)
            or not all(isinstance(item[f], str) for f in fields)
        ):
            raise ValueError(
                f"sentences[{i}] must be an object with exactly the string fields "
                f"{', '.join(fields)}"
            )
        if len(_normalize(item["sentence"])) < _MIN_SENTENCE_CHARS:
            raise ValueError(
                f"sentences[{i}] binds an empty or very short sentence "
                f"({item['sentence']!r}); a rendered novelty sentence is its claim text "
                f"followed by the scope of the search"
            )
        out.append(NoveltySentence(**{f: item[f] for f in fields}))
    return out


__all__ = [
    "NOVELTY_RENDER_RE",
    "NOVELTY_SCAN_RE",
    "NOVELTY_NEWCOMMAND",
    "NOVELTY_SENTENCES_FILE",
    "NoveltySentence",
    "has_novelty_markup",
    "novelty_scope_suffix",
    "require_novelty_text",
    "find_unsupported_novelty",
    "find_unbacked_novelty_sentences",
    "novelty_sentences_payload",
    "parse_novelty_sentences",
]
