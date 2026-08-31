"""
Record-bound ARGUED verdicts for agent-authored paper prose (OD-R1,
design/reader-facing-prose.md §8).

The problem this closes. A paper is an ARGUMENT addressed to a skeptical peer, not a prose
rendering of the record (design/reader-facing-prose.md §2). But the only mechanism for
stating a verdict in prose was ``\\status{<hyp>}`` (``render/factref.py``), which
SUBSTITUTES the belief-state enum (``proposed``/``supported``/``contested``/``refuted``)
into the manuscript. So the engine wrote the record's vocabulary into the paper, and an
author who wanted an argued sentence had to leave the fidelity gate entirely (a bare
literal) -- rigor and argument were placed in opposition.

This module supplies the third option: the author writes the SENTENCE and DECLARES the
status it is written to; the engine CHECKS the declaration against the record and renders
only the sentence ::

    \\finding{<hypothesis-id>}{<status>}{<the author's argued sentence>}

Architecture (mirrors the LOCKED ``\\novelty`` architecture, ``render/novelty.py``):
SURVIVE + preamble ``\\newcommand{\\finding}[3]{#3}`` -- NOT substitute-away. LaTeX renders
only the 3rd arg, so the reader never meets the enum; the hyp/status SURVIVE into the
persisted ``.tex`` as metadata that ``sci-adk verify`` re-scans against the record, exactly
like the ``\\ref``<->``\\label`` and ``\\novelty`` re-scans.

WHY declaration beats substitution -- the record is NON-MONOTONE. A Claim's status is
revisable; new evidence can move ``supported`` to ``contested``. Under substitution the
next render silently rewrites that one word while the surrounding argument (the motivation,
the discussion, the implications) stays written for the OLD verdict -- the paper quietly
self-contradicts and every gate stays green. Under declaration the stale declaration no
longer matches the record, verify FAILS LOUD, and a human must rewrite the argument. A
belief revision should cost a rewrite, not a string replacement.

The FLOOR gate. The protocol's only prose rule was a CEILING (never state a Claim more
strongly than its status). A ceiling alone is optimized by asserting as little as possible,
which is what makes a conclusion fail to land. Its dual is structural and therefore
mechanically checkable: :func:`find_unargued_hypotheses` -- a document that argues ANY
hypothesis via ``\\finding`` must argue EVERY hypothesis the record actually decided. It is
opt-in per document (a manuscript with no markup is not retro-broken) and is the same shape
as the existing orphan-figure check: a declared thing must be referenced.

Honest limits (documented, like ``factref.py`` / ``novelty.py``):

  - The gate binds the DECLARATION, not the sentence. An author who declares the true
    status and still overstates in prose passes. That ceiling was never mechanically
    enforced anyway -- ``\\status`` only guaranteed the printed WORD was the recorded one,
    never that the surrounding sentence did not overstate -- so this gives up an
    appearance, not a guarantee. Judging a sentence against a status is semantic, and this
    project does not put an LLM on the verdict path.
  - A verdict written as plain prose with no ``\\finding`` command is not governed (the
    same bound as ``\\novelty`` and ``\\evval``). What changes is the INCENTIVE: under
    substitution, using the macro cost readability, so bypassing it bought something. Here
    the author writes their own sentence either way, so bypassing buys nothing.
  - The text (3rd arg) is FLAT: ``[^{}]*``, so no nested command and no braces. Put a
    ``\\cite`` / ``\\ref`` OUTSIDE the span.
  - ``word_count`` (``render/pubreqs_checks.py``) strips ``\\commands`` and braces but keeps
    their contents, so each markup adds its hyp id + status (2 tokens) to the counted
    prose. This matches the pre-existing ``\\novelty`` behaviour; it is not corrected here.

The macro is ``\\finding`` and NOT ``\\verdict`` because ``verdict`` is itself banned
manuscript vocabulary (``render/paper.py`` ``_PAPER_TOOL_WORD_RE``: "a paper states a
'result', not a 'verdict'"), and the surviving markup is scanned by that gate.

This module is PURE: it imports ``sci_adk.core`` ONLY (the F4 kernel seam -- no adapter, no
loop, no LLM, no fs/network), deterministic + fail-loud, exactly like ``render/novelty.py``.

Reference: design/reader-facing-prose.md (§2 the genre error, §8 OD-R1),
src/sci_adk/render/novelty.py (the locked sibling architecture),
src/sci_adk/render/factref.py (the substitute-away sibling this supersedes for verdicts).
"""

from __future__ import annotations

import re
from typing import Sequence

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.spec import Spec

# Render-side: capture (hyp, status, text). Whitespace-tolerant OUTSIDE the captured groups
# (same posture as NOVELTY_RENDER_RE) so no leading/trailing space leaks into an id.
FINDING_RENDER_RE = re.compile(
    r"\\finding\s*\{([^{}]+)\}\s*\{([^{}]+)\}\s*\{([^{}]*)\}"
)

# Verify-side scan: capture (hyp, status), IGNORE the 3rd arg (the author's sentence, which
# may be long). Anchored on ``\finding ...{...}{...}{`` so it matches every assertion LaTeX
# would render. It does NOT match the preamble ``\newcommand{\finding}[3]{#3}`` -- there
# ``\finding`` is followed immediately by ``}``, and ``\s*\{`` requires a ``{`` next.
FINDING_SCAN_RE = re.compile(r"\\finding\s*\{([^{}]+)\}\s*\{([^{}]+)\}\s*\{")

# The preamble snippet that makes LaTeX render only the author's sentence (3rd arg).
# Emitted by the renderer ONLY when ``\finding`` markup is present (byte-identical when
# absent), the same regression invariant as NOVELTY_NEWCOMMAND.
FINDING_NEWCOMMAND = r"\newcommand{\finding}[3]{#3}"

# A LaTeX-EMIT-SAFE hypothesis id: the wrapper emits it RAW into the surviving markup
# (escaping would break the emit==scan round-trip the verify re-scan relies on), so an id
# carrying a tokenization-special would silently CORRUPT the .tex while verify stayed green.
# Refused (fail loud), not escaped -- identical rule and rationale to novelty.py.
_EMIT_SAFE_HYP_RE = re.compile(r"[A-Za-z0-9._:\-]+")

_VALID_STATUSES = tuple(s.value for s in ClaimStatus)


def has_finding_markup(text: str) -> bool:
    """True iff ``text`` contains at least one ``\\finding{hyp}{status}{`` assertion.

    Uses the verify-side scan (it does not match the preamble ``\\newcommand``). Pure.
    """
    return FINDING_SCAN_RE.search(text) is not None


def _experiment_claim_by_hyp(claims: Sequence[Claim]) -> dict[str, Claim]:
    """Map hypothesis id -> its EXPERIMENT Claim (novelty sub-claims excluded).

    Same keying as ``factref.substitute_factrefs``: ``\\finding`` states the HEADLINE
    verdict, never a novelty sub-verdict.
    """
    return {c.answers: c for c in claims if not c.id.startswith("claim-novelty-")}


def check_finding(
    hyp_id: str,
    declared_status: str,
    claims: Sequence[Claim],
) -> None:
    """Check one ``\\finding{hyp}{status}{...}`` declaration against the record.

    PURE + FAIL-LOUD, the same contract as ``factref._resolve_*`` and
    ``novelty.novelty_scope_suffix``. Returns ``None`` when the declaration is faithful.

    Args:
        hyp_id: the hypothesis the sentence argues about (arg 1).
        declared_status: the status the author declares they wrote to (arg 2).
        claims: the run's Claims (the experiment Claim per hypothesis answers this).

    Raises:
        ValueError: ``hyp_id`` is not a LaTeX-emit-safe slug; ``declared_status`` is not a
            ClaimStatus value; the hypothesis has no experiment Claim; or the declared
            status differs from the recorded one (the belief-revision catch).
    """
    if _EMIT_SAFE_HYP_RE.fullmatch(hyp_id) is None:
        raise ValueError(
            f"\\finding cites hypothesis id '{hyp_id}', which is not LaTeX-emit-safe "
            f"(allowed: letters, digits, '.', '_', ':', '-'). It is emitted raw into the "
            f"paper markup, so a tokenization-special (%, backslash, #, $, &, ~, ^, braces, "
            f"whitespace) would corrupt the document -- rename the hypothesis id."
        )
    if declared_status not in _VALID_STATUSES:
        raise ValueError(
            f"\\finding{{{hyp_id}}}{{{declared_status}}} declares an unknown status "
            f"'{declared_status}' -- it must be one of {', '.join(_VALID_STATUSES)}."
        )
    claim = _experiment_claim_by_hyp(claims).get(hyp_id)
    if claim is None:
        raise ValueError(
            f"\\finding cites hypothesis '{hyp_id}' with no experiment Claim -- a paper "
            f"cannot argue a conclusion the record never derived (record fidelity)."
        )
    recorded = claim.status.value if hasattr(claim.status, "value") else str(claim.status)
    if recorded != declared_status:
        raise ValueError(
            f"\\finding for '{hyp_id}' is written to status '{declared_status}' but the "
            f"record now derives '{recorded}'. Belief is revisable: the sentence and the "
            f"argument around it were written for the old verdict and must be rewritten, "
            f"not silently re-worded. Rewrite the passage, then declare '{recorded}'."
        )


def find_mismatched_findings(tex: str, claims: Sequence[Claim]) -> list[str]:
    """Return one problem line per ``\\finding`` markup in ``tex`` that fails the gate.

    PURE. Re-scans a rendered/persisted ``.tex`` for every ``\\finding{hyp}{status}{`` and
    re-runs the SAME check the renderer ran (:func:`check_finding`); a ``ValueError`` ->
    a one-line problem. So a belief revision after render -- or a hand-edited ``.tex`` --
    is caught HEADLESS by ``sci-adk verify``, symmetric with the ``\\novelty`` re-scan.
    De-duplicated, sorted for a stable report.
    """
    problems: set[str] = set()
    for match in FINDING_SCAN_RE.finditer(tex):
        hyp_id, declared = match.group(1), match.group(2)
        try:
            check_finding(hyp_id, declared, claims)
        except ValueError as exc:
            problems.add(f"finding for '{hyp_id}': {exc}")
    return sorted(problems)


def find_unargued_hypotheses(
    tex: str,
    spec: Spec,
    claims: Sequence[Claim],
) -> list[str]:
    """The FLOOR gate: every DECIDED hypothesis must be argued somewhere in ``tex``.

    PURE. The structural dual of the ceiling rule ("never state a Claim more strongly than
    its status"), which alone is optimized by silent omission. Same shape as the existing
    orphan-figure check: a declared thing must be referenced.

    OPT-IN PER DOCUMENT: a ``tex`` with NO ``\\finding`` markup returns ``[]`` -- a
    manuscript that does not use the mechanism is not retro-broken. Once a document argues
    one hypothesis this way, it must argue them all.

    A hypothesis with NO experiment Claim is SKIPPED: nothing can be argued about a
    question the record never decided (the run is simply not finished for it).
    """
    if not has_finding_markup(tex):
        return []
    argued = {m.group(1) for m in FINDING_SCAN_RE.finditer(tex)}
    decided = _experiment_claim_by_hyp(claims)
    problems = [
        f"hypothesis '{h.id}' has a derived verdict on the record but is argued nowhere "
        f"in the manuscript -- state its conclusion via "
        f"\\finding{{{h.id}}}{{{decided[h.id].status.value}}}{{...}}, or the paper "
        f"silently omits a result it registered."
        for h in spec.hypotheses
        if h.id in decided and h.id not in argued
    ]
    return sorted(problems)


__all__ = [
    "FINDING_RENDER_RE",
    "FINDING_SCAN_RE",
    "FINDING_NEWCOMMAND",
    "has_finding_markup",
    "check_finding",
    "find_mismatched_findings",
    "find_unargued_hypotheses",
]
