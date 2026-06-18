"""
A GENERAL LaTeX ``\\ref``<->``\\label`` consistency checker (PURE, kernel render/).

design/paper-figures-and-si.md D4 / Phase 3: consistency surfaced as a verify-style
deterministic HARD gate -- "the engine checks, not the author". This module is the PURE
kernel behind that gate: given one LaTeX document as a string, it reports the
WITHIN-document reference integrity that pdflatex would otherwise only surface as a
silent ``??`` in the PDF (an unresolved ``\\ref``) or a "multiply defined label" log
warning (a duplicate ``\\label``).

How it differs from the Phase-1 ``figures.check_figure_consistency``: that one is
figure-only (it scans ``\\ref{fig:...}`` against a known figure-id SET, and also reports
ORPHAN figures -- defined-but-never-referenced -- as a render-time warning). This checker
is GENERAL across every label prefix (fig:/tab:/sec:/eq:/...) and is the GATE: it reports
only the two genuinely-broken conditions (unresolved refs, duplicate labels). An UNused
label is benign in a draft and is deliberately NOT a gate failure here.

Scope (within-document only): the cross-DOCUMENT main<->SI ``\\ref`` (e.g. a "Fig. S2"
in draft.tex resolving into si.tex) is DEFERRED -- it needs the LaTeX ``xr`` package and
a compile-order dependency (with Overleaf folder-upload UX wrinkles), so it is out of
scope for this phase. The user's headline need ("figure number unified with the paper
body") is exactly the WITHIN-document integrity this checker gates.

PURE: string in, report out -- no filesystem, no LLM, no network. Deterministic: the
report lists are sorted + de-duplicated. Lives in ``render/`` (the kernel) and imports
NOTHING from ``sci_adk.adapter`` (F4 seam) -- in fact it imports only ``re`` + pydantic.

Comment handling: a line whose first non-whitespace character is ``%`` is a LaTeX
comment; its ``\\ref`` / ``\\label`` never compile, so the whole line is stripped before
parsing (a ``\\ref`` on a commented line must not count as a real reference, and a
``\\label`` there must not count as a definition). This is a LINE-level strip only -- an
INLINE trailing comment (``\\ref{a} % note``) on an otherwise-live line is NOT removed
(handling escaped ``\\%`` and mid-line ``%`` correctly needs a real tokenizer; the
line-level rule covers the common fully-commented-out case and is the honest documented
limit).

Reference: design/paper-figures-and-si.md (D4, Phase 3), design/rigor-shell-architecture.md
(F4 kernel seam), src/sci_adk/render/figures.py (the Phase-1 figure-only sibling).
"""

from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

# A label key is the argument of \label / \ref / \eqref / \autoref: any non-empty run of
# characters up to the closing brace, excluding ``{`` / ``}`` (so a nested brace cannot be
# swallowed). This is intentionally permissive on the prefix (fig:/tab:/sec:/eq:/...) --
# the checker is GENERAL, not figure-only.
_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
# \ref, \eqref, \autoref are all reference forms; a dangling one is equally broken. (Other
# packages add \cref/\Cref/\vref/...; this set covers the forms the sci-adk render emits
# and the common base + amsmath/hyperref forms. Extending the alternation is the way to
# add more -- no other logic changes.)
_REF_RE = re.compile(r"\\(?:ref|eqref|autoref)\{([^{}]+)\}")


class LatexRefReport(BaseModel):
    """The within-document ``\\ref``<->``\\label`` integrity report for one LaTeX doc.

    Attributes:
        unresolved_refs: every distinct ref key (``\\ref{X}`` / ``\\eqref{X}`` /
            ``\\autoref{X}``) with NO matching ``\\label{X}`` in the same document --
            a broken reference (compiles to ``??``). Sorted, de-duplicated. A GATE
            failure.
        duplicate_labels: every label key defined by ``\\label`` more than once -- a
            LaTeX "multiply defined label" error. Sorted, de-duplicated. A GATE failure.
        ok: True iff BOTH gate-lists are empty. NOTE: an UNUSED label (defined but never
            referenced) is benign in a draft and is deliberately NOT reported and does
            NOT make ``ok`` False.
    """

    model_config = {"frozen": True}

    unresolved_refs: List[str] = Field(
        default_factory=list, description="Refs with no matching label (broken)"
    )
    duplicate_labels: List[str] = Field(
        default_factory=list, description="Labels defined more than once"
    )
    ok: bool = Field(..., description="True iff no unresolved ref and no duplicate label")


def _strip_comment_lines(tex: str) -> str:
    """Drop every fully-commented LaTeX line (first non-space char is ``%``).

    A ``\\ref`` / ``\\label`` on such a line never compiles, so it must not register.
    Line-level only -- an inline ``... % note`` on a live line is left intact (the
    documented, honest limit). Non-comment lines pass through unchanged so byte offsets
    of live content are preserved enough for regex scanning.
    """
    kept: List[str] = []
    for line in tex.splitlines():
        if line.lstrip().startswith("%"):
            continue
        kept.append(line)
    return "\n".join(kept)


def check_latex_ref_consistency(tex: str) -> LatexRefReport:
    """Scan one LaTeX document for ``\\ref``<->``\\label`` integrity (D4, the gate).

    PURE + deterministic. Parses all ``\\label{X}`` and all ``\\ref{X}`` /
    ``\\eqref{X}`` / ``\\autoref{X}`` (fully-commented lines stripped first), and reports
    the two genuinely-broken conditions:

      - ``unresolved_refs``: a ref to an X with no matching ``\\label{X}`` (compiles to
        ``??`` -- a broken reference);
      - ``duplicate_labels``: an X defined by ``\\label`` more than once (a LaTeX
        "multiply defined" error).

    An UNUSED label (defined, never referenced) is benign and intentionally NOT gated.

    Args:
        tex: a single LaTeX document body/source as a string.

    Returns:
        A :class:`LatexRefReport` -- ``ok`` iff no unresolved ref and no duplicate label.
    """
    live = _strip_comment_lines(tex)

    label_keys = _LABEL_RE.findall(live)
    ref_keys = _REF_RE.findall(live)

    defined: set[str] = set()
    duplicate: set[str] = set()
    for key in label_keys:
        if key in defined:
            duplicate.add(key)
        defined.add(key)

    unresolved = {key for key in ref_keys if key not in defined}

    unresolved_sorted = sorted(unresolved)
    duplicate_sorted = sorted(duplicate)
    return LatexRefReport(
        unresolved_refs=unresolved_sorted,
        duplicate_labels=duplicate_sorted,
        ok=not unresolved_sorted and not duplicate_sorted,
    )


__all__ = ["LatexRefReport", "check_latex_ref_consistency"]
