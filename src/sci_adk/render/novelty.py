"""
Record-fidelity novelty/priority gate for agent-authored paper prose (N2 render +
N3 verify; design/literature-acquisition.md §"Render-time novelty gate").

The paper (belief) must never assert a novelty/priority claim the record does not back --
the same family as the evidence-validity gate (synthetic data cannot make a SUPPORTED
empirical claim), the paper-consistency gate (a dangling ``\\ref`` fails verify), and the
factref fidelity gate (``\\evval``/``\\status``, ``render/factref.py``). This module is the
novelty member of that family.

A novelty claim is asserted ONLY via the explicit markup ::

    \\novelty{result|method}{hyp-id}{text}

It is NEVER inferred from free prose -- no keyword scan, no NLP. This mirrors the
``\\ref``<->``\\label`` gate: the engine checks markup against the record deterministically.

Architecture (LOCKED): SURVIVE + preamble newcommand (NOT substitute-away). Unlike the
factref macros (which the engine REPLACES with the recorded value), the ``\\novelty`` markup
SURVIVES into the persisted ``.tex``; a preamble ``\\newcommand{\\novelty}[3]{#3}`` makes
LaTeX render only the 3rd arg (the text), while the kind/hyp stay as metadata that
``sci-adk verify`` re-scans against the record -- symmetry with the ``\\ref``<->``\\label``
re-scan. For each markup the engine re-derives the per-{hyp, kind} novelty claim status via
the SINGLE source of truth :func:`sci_adk.core.validity.derive_novelty_status` (never the
recorded claim):

  - **SUPPORTED** -> the rendered text gets a record-derived honest scope baked in:
    ``<text> (to our knowledge, as of <YYYY-MM-DD>)`` -- the engine rendering FROM the
    record (definition property 2: an absence claim is intrinsically "to our knowledge, as
    of the recorded search"), the date taken from the LATEST backing ``found_nothing``
    NOVELTY_DECISION. NOT a fallback hedge for an unsearched claim.
  - **NOT SUPPORTED / unknown hyp / bad kind** -> HARD fail: ``ValueError`` at render time
    (naming {hyp, kind} + the remedy), and a non-zero ``sci-adk verify``.

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

The hypothesis id (2nd arg) carries its own constraint: it is emitted RAW and so must be a
LaTeX-emit-safe slug (enforced in :func:`novelty_scope_suffix`). And, like the ``\\ref`` gate,
a "first" written as plain prose (no ``\\novelty`` command) is not governed -- the discipline
is "assert novelty via the command".

Reference: design/literature-acquisition.md, src/sci_adk/render/factref.py (the sibling
record-fidelity, fail-loud render gate), src/sci_adk/core/validity.py
(``derive_novelty_status`` -- the single source of truth).
"""

from __future__ import annotations

import re
from typing import Sequence

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
# and ``\novelty{r} {h}{t}`` ALL expand via the preamble ``\newcommand`` and PRINT. The regex
# therefore allows ``\s*`` in exactly the spots LaTeX does -- after the command name and
# between the arg groups -- so a whitespace-spaced ``\novelty`` cannot render an unbacked
# priority claim AND evade the gate (a hand-edited ``.tex`` that LaTeX would accept must not
# slip past :func:`find_unsupported_novelty`). The ``\s*`` are OUTSIDE the captured groups,
# so the captured kind/hyp/text are unchanged (no leading/trailing whitespace leaks into the id).
NOVELTY_RENDER_RE = re.compile(
    r"\\novelty\s*\{([^{}]*)\}\s*\{([^{}]+)\}\s*\{([^{}]*)\}"
)

# Verify-side scan: capture (kind, hyp), IGNORE the 3rd arg (the text -- which by render
# time carries the baked-in scope and may itself be long). Anchored on the literal
# ``\novelty ...{...}{...}{`` (whitespace-tolerant, same spots as the render regex) so it
# captures every assertion LaTeX would render. It does NOT match the preamble
# ``\newcommand{\novelty}[3]{#3}`` -- there ``\novelty`` is followed immediately by ``}`` (the
# close of the ``\newcommand`` name group), and ``\s*\{`` requires a ``{`` next -> no match.
NOVELTY_SCAN_RE = re.compile(r"\\novelty\s*\{([^{}]*)\}\s*\{([^{}]+)\}\s*\{")

# The preamble snippet that makes LaTeX render only the text (3rd arg). Emitted by the
# renderers ONLY when ``\novelty`` markup is present (byte-identical when absent).
NOVELTY_NEWCOMMAND = r"\newcommand{\novelty}[3]{#3}"

_VALID_KINDS = ("result", "method")

# A LaTeX-EMIT-SAFE hypothesis id. The wrapper emits ``hyp`` RAW into arg-2 of the surviving
# ``\novelty{kind}{hyp}{text}`` (escaping it would break the emit==scan round-trip the verify
# re-scan relies on), so an id carrying a LaTeX tokenization-special would silently CORRUPT
# the ``.tex`` (e.g. ``%`` comments out the rest of the line) while verify stays green. The
# gate therefore REFUSES a non-emit-safe id (fail loud) rather than escaping it. Real ids
# (``hyp-001``, ``h1``, ``hyp_t1``, ``hyp.a``, ``hyp:b``) match; ``_`` ``-`` ``.`` ``:`` are
# inert in the dropped arg-2 position (the ``\newcommand`` renders only #3); ``%`` ``\`` ``#``
# ``$`` ``&`` ``~`` ``^`` ``{`` ``}`` and whitespace are rejected.
_EMIT_SAFE_HYP_RE = re.compile(r"[A-Za-z0-9._:\-]+")


def has_novelty_markup(text: str) -> bool:
    """True iff ``text`` contains at least one ``\\novelty{kind}{hyp}{`` assertion.

    Uses the verify-side scan (it does not match the preamble ``\\newcommand``). Pure.
    """
    return NOVELTY_SCAN_RE.search(text) is not None


def _latest_found_nothing_date(
    hyp_id: str, kind: str, novelty_decisions: Sequence[EvidenceItem]
) -> str:
    """The ``YYYY-MM-DD`` scope date for a SUPPORTED {hyp, kind} novelty claim.

    The backing search timestamp is the parent EvidenceItem's append-only ``created_at``
    (``LiteratureDecision`` carries no own date -- the model docstring names ``created_at``
    the search timestamp). When several ``found_nothing`` decisions exist for this
    {hyp, kind}, the LATEST one is used (the most recent confirmation), deterministically
    tie-broken by ``ev.id``. The caller guarantees the status is SUPPORTED, so at least one
    qualifying decision exists.
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
    # SUPPORTED <=> qualifying is non-empty (same predicate as derive_novelty_status), so
    # this max is always over >= 1 item. Latest created_at; ties broken by id (stable).
    latest = max(qualifying, key=lambda ev: (ev.created_at, ev.id))
    return latest.created_at.strftime("%Y-%m-%d")


def novelty_scope_suffix(
    kind: str,
    hyp_id: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
) -> str:
    """The record-derived honest-scope suffix for one ``\\novelty{kind}{hyp}{...}`` markup.

    Re-derives the {hyp, kind} novelty status via the SINGLE source of truth
    :func:`sci_adk.core.validity.derive_novelty_status` (NEVER the recorded claim) and:

      - SUPPORTED  -> returns `` (to our knowledge, as of <YYYY-MM-DD>)`` (leading space;
        plain ASCII), the date from the LATEST backing ``found_nothing`` decision -- the
        intrinsic "as of the recorded search" bound attached deterministically FROM the
        record (definition property 2).
      - anything else (unsupported / unknown hyp / bad kind) -> raises ``ValueError``
        naming {hyp, kind} + the remedy (the HARD fail; the engine never softens).

    PURE + FAIL-LOUD, the same contract as ``factref._resolve_*``.

    The ``hyp_id`` MUST be a LaTeX-emit-safe slug (``[A-Za-z0-9._:-]+``): the wrapper emits it
    RAW into the surviving ``\\novelty`` markup, so an id with a tokenization-special (``%``
    ``\\`` ``#`` ``$`` ``&`` ``~`` ``^`` ``{`` ``}`` or whitespace) would corrupt the ``.tex``
    while leaving verify green. Such an id is REFUSED here (fail loud), not escaped -- escaping
    would break the emit==scan round-trip the verify re-scan depends on.

    Raises:
        ValueError: ``kind`` not in {result, method}; ``hyp_id`` not a LaTeX-emit-safe slug;
            ``hyp_id`` absent from ``spec``; or the {hyp, kind} novelty claim does not
            re-derive SUPPORTED from the record.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"\\novelty has an invalid kind '{kind}' (must be 'result' or 'method') "
            f"for hypothesis '{hyp_id}' -- fix the markup."
        )
    # The id is emitted RAW into the surviving \novelty markup -- refuse a non-emit-safe id
    # (it would corrupt the .tex, e.g. a '%' comments out the line) rather than escape it
    # (escaping would break the emit==scan round-trip the verify re-scan relies on).
    if _EMIT_SAFE_HYP_RE.fullmatch(hyp_id) is None:
        raise ValueError(
            f"\\novelty cites hypothesis id '{hyp_id}', which is not LaTeX-emit-safe "
            f"(allowed: letters, digits, '.', '_', ':', '-'). It is emitted raw into the "
            f"paper markup, so a tokenization-special (%, backslash, #, $, &, ~, ^, braces, "
            f"whitespace) would corrupt the document -- rename the hypothesis id."
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
    date = _latest_found_nothing_date(hyp_id, kind, novelty_decisions)
    return f" (to our knowledge, as of {date})"


def find_unsupported_novelty(
    tex: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
) -> list[str]:
    """Return one problem line per ``\\novelty`` markup in ``tex`` that fails the gate.

    PURE. Re-scans a rendered/persisted ``.tex`` for every ``\\novelty{kind}{hyp}{`` and
    re-runs the SAME record re-derivation as the renderer (:func:`novelty_scope_suffix`);
    a ``ValueError`` -> a one-line problem (``<kind>-novelty for '<hyp>': <reason>``). So a
    tampered / missing decision is caught HEADLESS by ``sci-adk verify``, symmetric with the
    ``\\ref``<->``\\label`` re-scan. De-duplicated, sorted for a stable report. Clean tex
    (every assertion supported, or none) -> ``[]``.
    """
    problems: set[str] = set()
    for match in NOVELTY_SCAN_RE.finditer(tex):
        kind, hyp_id = match.group(1), match.group(2)
        try:
            novelty_scope_suffix(kind, hyp_id, spec, novelty_decisions)
        except ValueError as exc:
            problems.add(f"{kind}-novelty for '{hyp_id}': {exc}")
    return sorted(problems)


__all__ = [
    "NOVELTY_RENDER_RE",
    "NOVELTY_SCAN_RE",
    "NOVELTY_NEWCOMMAND",
    "has_novelty_markup",
    "novelty_scope_suffix",
    "find_unsupported_novelty",
]
