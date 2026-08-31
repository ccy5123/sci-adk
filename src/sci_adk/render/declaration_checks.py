"""
The deterministic checks over a conclusion declaration list (design §11.3).

Three PURE functions, none of which reads meaning. They implement the middle layer of
design/reader-facing-prose.md §11.2 -- the one idea being to turn a semantic question into
a comparison of two values, and to escalate what cannot be reduced that way rather than
auto-deciding it:

  - :func:`status_mismatches`      -- declared status  vs  the recorded experiment Claim.
  - :func:`unanchored_sentences`   -- the quoted sentence  vs  the manuscript text.
  - :func:`undeclared_hypotheses`  -- the completeness floor.

What they deliberately do NOT do: judge whether a sentence overstates the status it
declares. That is semantic, and no language model sits on the verdict path (spec.md
Exclusions). It is escalated to the advisory reviewer of design §11.4.

This module is PURE: it imports ``sci_adk.core`` ONLY (the F4 kernel seam -- no adapter, no
loop, no LLM, no fs/network), and is deterministic + total (it returns problem lines, it
does not raise on a bad manuscript). It lives in ``render/`` beside its siblings
``pubreqs_checks.py``, ``number_audit.py``, and ``consistency.py``.

Reference: design/reader-facing-prose.md §11, src/sci_adk/core/declarations.py (the type),
src/sci_adk/render/number_audit.py (the sibling deterministic audit over the same document).
"""

from __future__ import annotations

import re
from typing import Sequence

from sci_adk.core.claim import Claim
from sci_adk.core.declarations import ConclusionReview, Declarations
from sci_adk.core.spec import Spec

# LaTeX comments: a ``%`` that is not escaped (``\%``) starts a comment. Stripped BEFORE
# quote matching so a sentence that survives only inside a commented-out block does not
# count as present in the manuscript (that would be a silent false pass).
_COMMENT_RE = re.compile(r"(?<!\\)%.*?$", re.MULTILINE)
_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Collapse whitespace runs to a single space and strip.

    LaTeX line-wraps prose freely, so a sentence copied out of the manuscript will differ
    from the source in line breaks and indentation but nothing else. Normalizing both sides
    makes the match robust to re-wrapping while staying an EXACT comparison in every other
    respect -- no fuzzy matching, no edit distance: an author who rewrites the sentence must
    re-declare it, which is the whole point of the anchor check.
    """
    return _WS_RE.sub(" ", text).strip()


def _experiment_claim_by_hyp(claims: Sequence[Claim]) -> dict[str, Claim]:
    """Map hypothesis id -> its EXPERIMENT Claim (novelty sub-claims excluded).

    Same keying as ``factref.substitute_factrefs``: a declaration states the HEADLINE
    verdict for a hypothesis, never a novelty sub-verdict.
    """
    return {c.answers: c for c in claims if not c.id.startswith("claim-novelty-")}


def status_mismatches(
    declarations: Declarations,
    claims: Sequence[Claim],
) -> list[str]:
    """Check 1: every declared status is still the one the record derives.

    Belief is NON-MONOTONE -- new evidence can move a Claim's status. When it does, the
    sentence AND the argument built around it were written for the old verdict, so the
    remedy is to rewrite the passage, not to re-word one clause. Returns one problem line
    per stale (or unanswerable) declaration; ``[]`` when every declaration is faithful.

    A declaration for a hypothesis with no experiment Claim is also a problem: the paper
    states a conclusion the record never derived.
    """
    by_hyp = _experiment_claim_by_hyp(claims)
    problems: list[str] = []
    for decl in declarations.declarations:
        claim = by_hyp.get(decl.hypothesis_id)
        if claim is None:
            problems.append(
                f"declaration for '{decl.hypothesis_id}': the paper states a conclusion "
                f"for a hypothesis the record never decided (no experiment Claim answers "
                f"it) -- remove the conclusion, or finish the run."
            )
            continue
        recorded = claim.status.value if hasattr(claim.status, "value") else str(claim.status)
        declared = (
            decl.status.value if hasattr(decl.status, "value") else str(decl.status)
        )
        if recorded != declared:
            problems.append(
                f"declaration for '{decl.hypothesis_id}': written to '{declared}' but the "
                f"record now derives '{recorded}'. The sentence and the argument around it "
                f"were written for the old verdict -- rewrite the passage, then declare "
                f"'{recorded}'."
            )
    return sorted(problems)


def unanchored_sentences(
    declarations: Declarations,
    tex: str,
) -> list[str]:
    """Check 2: every declared sentence still appears in the manuscript.

    Whitespace-normalized substring match over the manuscript with LaTeX comments stripped.
    A miss means the author edited (or removed) the sentence the declaration was made
    about, so the declaration has silently detached from its subject and must be re-made.

    This is what a line number could not do and an in-document macro did not do: a macro's
    text argument can be rewritten freely with nothing noticing. The check cannot judge the
    NEW sentence -- only that it is no longer the one that was declared.
    """
    haystack = _normalize(_COMMENT_RE.sub("", tex))
    problems: list[str] = []
    for decl in declarations.declarations:
        needle = _normalize(decl.sentence)
        if needle and needle not in haystack:
            excerpt = needle if len(needle) <= 70 else needle[:67] + "..."
            problems.append(
                f"declaration for '{decl.hypothesis_id}': the declared sentence is no "
                f'longer in {declarations.document} ("{excerpt}") -- it was edited or '
                f"removed, so the declaration no longer describes the paper. Re-declare "
                f"the sentence as it now reads."
            )
    return sorted(problems)


def undeclared_hypotheses(
    declarations: Declarations,
    spec: Spec,
    claims: Sequence[Claim],
) -> list[str]:
    """Check 3 (the FLOOR): every DECIDED hypothesis is declared somewhere.

    The structural dual of the ceiling rule ("never state a Claim more strongly than its
    status"). A ceiling alone is satisfied by asserting as little as possible, and an
    author free to declare only the favourable results would silently omit the rest. Same
    shape as the existing orphan-figure check: a declared thing must be referenced.

    Opt-in at the RUN level, not per hypothesis: a run with no declaration list is not
    gated at all (see :func:`sci_adk.core.declarations.load_declarations`), but once the
    list exists it must be complete. A hypothesis with NO experiment Claim is skipped --
    nothing can be concluded about a question the record never decided.
    """
    decided = _experiment_claim_by_hyp(claims)
    declared = declarations.declared_hypotheses
    return sorted(
        f"hypothesis '{h.id}' has a derived verdict on the record but no conclusion is "
        f"declared for it -- state its conclusion in the paper and declare it "
        f"(recorded status: '{decided[h.id].status.value}'), or the paper silently omits "
        f"a result the run registered."
        for h in spec.hypotheses
        if h.id in decided and h.id not in declared
    )


def declaration_problems(
    declarations: Declarations,
    spec: Spec,
    claims: Sequence[Claim],
    tex: str,
) -> list[str]:
    """All three checks over one run, in a stable order. ``[]`` means clean."""
    return (
        status_mismatches(declarations, claims)
        + unanchored_sentences(declarations, tex)
        + undeclared_hypotheses(declarations, spec, claims)
    )


def declaration_disagreements(
    declarations: Declarations,
    review: ConclusionReview,
) -> list[str]:
    """ADVISORY: where an independent reading of a sentence differs from its declaration.

    PURE. The third layer of design §11.2 -- and the ONLY one that involves a model, which
    is why its output can never gate. The reviewer was not asked to find overstatement; it
    was asked which status each sentence asserts, WITHOUT being told what the author
    declared (:class:`sci_adk.core.declarations.ReadConclusion`). This function computes the
    disagreement. So a faithful paper produces silence, and the finding is a comparison
    rather than a model's assertion that something is wrong.

    Both directions come out of the same comparison, deliberately: a sentence read as
    STRONGER than declared overstates; one read as WEAKER understates. Flagging only the
    first would reward hedging and re-create the defect that motivated the design (§4).

    A reading the reviewer could not resolve (``reads_as=None``) gets its own line -- an
    unreadable conclusion is itself worth a person's attention, and silently dropping it
    would make the signal look cleaner than it is. A reading for a hypothesis that is not
    declared is reported too, rather than ignored.
    """
    declared = {d.hypothesis_id: d for d in declarations.declarations}
    lines: list[str] = []
    for reading in review.readings:
        decl = declared.get(reading.hypothesis_id)
        if decl is None:
            lines.append(
                f"conclusion review for '{reading.hypothesis_id}': the reviewer read a "
                f"conclusion for a hypothesis the declaration list does not cover."
            )
            continue
        if reading.reads_as is None:
            lines.append(
                f"conclusion review for '{reading.hypothesis_id}': the reviewer could not "
                f"tell what status the sentence asserts"
                + (f" ({reading.basis})" if reading.basis else "")
                + " -- a conclusion a careful reader cannot resolve is worth rewriting."
            )
            continue
        read_as = (
            reading.reads_as.value
            if hasattr(reading.reads_as, "value")
            else str(reading.reads_as)
        )
        declared_status = (
            decl.status.value if hasattr(decl.status, "value") else str(decl.status)
        )
        if read_as != declared_status:
            lines.append(
                f"conclusion review for '{reading.hypothesis_id}': declared "
                f"'{declared_status}', but an independent reader took the sentence to "
                f"assert '{read_as}'"
                + (f" ({reading.basis})" if reading.basis else "")
                + ". Advisory only -- read the sentence and decide."
            )
    return sorted(lines)


__all__ = [
    "status_mismatches",
    "unanchored_sentences",
    "undeclared_hypotheses",
    "declaration_problems",
    "declaration_disagreements",
]
