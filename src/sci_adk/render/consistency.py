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

Two scopes live here:

  - :func:`check_latex_ref_consistency` -- the WITHIN-document ``\\ref``<->``\\label``
    gate (one ``.tex`` at a time);
  - :func:`check_cross_doc_s_refs` -- a STATIC cross-DOCUMENT gate for the plain-text
    "Figure S<n>" / "Table S<n>" a main paper writes to cite an SI float. A real LaTeX
    ``\\ref`` cannot cross the compile boundary without the ``xr`` package (Overleaf
    folder-upload UX wrinkles), so the SI renumbers its floats ``S1, S2, ...`` via
    ``\\thefigure``/``\\thetable`` = ``S\\arabic{...}`` and the author cites them as bare
    text. That text is otherwise UNGATED -- a "Figure S3" with only two SI figures ships
    a silent dangling reference. This checker closes that gap by COUNTING the SI's floats
    (the Nth ``\\begin{figure}`` renders as "Figure SN") and confirming every main-paper
    "Figure/Table S<n>" resolves to one that exists. No recompile, no ``xr`` package, no
    LLM -- the same deterministic-checker-over-explicit-markup spirit as the rest.

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

# A main-paper cross-document reference to an SI float, written as PLAIN TEXT (not a
# ``\ref`` -- it cannot cross the compile boundary without ``xr``). Matches the
# convention the SI emits ("Figure S1" / "Table S2"): a float word, an optional ``~``/
# space, then an UPPER-CASE ``S`` + digits. The float word is allowed in its capitalised
# or abbreviated forms (Figure/Figures/Fig/Fig. and Table/Tables/Tab/Tab.); ``S`` is
# required upper-case because the SI's ``\thefigure``/``\thetable`` rename emits ``S``.
_CROSS_DOC_SREF_RE = re.compile(
    r"(?P<kind>Figures?|Fig\.?|Tables?|Tab\.?)\s*~?\s*S(?P<num>\d+)"
)
# The SI's S-numbered floats: the Nth captioned ``\begin{figure}`` is "Figure SN", the
# Nth ``\begin{table}`` is "Table SN" (the SI sets ``\thefigure``/``\thetable`` =
# ``S\arabic{...}`` and every SI float is captioned -- a render/si.py invariant). Counting
# the float environments therefore yields the max valid S-number per kind. ``figure*`` /
# ``table*`` are tolerated for robustness though render/si.py emits the unstarred forms.
_SI_FIGURE_ENV_RE = re.compile(r"\\begin\{figure\*?\}")
_SI_TABLE_ENV_RE = re.compile(r"\\begin\{table\*?\}")


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


class CrossDocRefReport(BaseModel):
    """The cross-document "Figure/Table S<n>" integrity report (main paper -> SI).

    Attributes:
        unresolved_refs: every distinct plain-text "Figure S<n>" / "Table S<n>" cited in
            the MAIN paper that points past the SI's float count (the SI has fewer than
            ``n`` figures / tables, so "Figure S<n>" would compile to a number no SI float
            carries). Normalised to ``"Figure S<n>"`` / ``"Table S<n>"``, sorted by (kind,
            number), de-duplicated. A GATE failure.
        ok: True iff ``unresolved_refs`` is empty.

    Honest limit (documented, like the within-document checker's comment rule): this gates
    only the MAIN-paper -> SI direction (the SI is the only document whose floats are
    S-renumbered); an ``S0`` / non-existent number is caught, but a citation to the WRONG
    (existing) SI float number is not (positional counting cannot know intent). Section
    cross-references are out of scope -- the SI does not S-renumber sections.
    """

    model_config = {"frozen": True}

    unresolved_refs: List[str] = Field(
        default_factory=list,
        description="Main-paper 'Figure/Table S<n>' citations with no such SI float",
    )
    ok: bool = Field(..., description="True iff every cross-doc S-reference resolves")


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


def check_cross_doc_s_refs(draft_tex: str, si_tex: str) -> CrossDocRefReport:
    """Gate the main paper's plain-text "Figure/Table S<n>" citations against the SI.

    PURE + deterministic. The SI renumbers its floats ``S1, S2, ...`` (``\\thefigure`` /
    ``\\thetable`` = ``S\\arabic{...}``), so a main paper cites an SI float as the bare
    text "Figure S1" -- a string LaTeX never resolves across the compile boundary, hence
    otherwise UNGATED. This counts the SI's float environments (the Nth ``\\begin{figure}``
    is "Figure SN") and reports every main-paper "Figure/Table S<n>" that points past that
    count (a silent dangling cross-reference).

    Fully-commented lines are stripped from BOTH documents first (a citation or a float on
    a ``%`` line never compiles). No recompile, no ``xr`` package, no LLM.

    Args:
        draft_tex: the main paper LaTeX source (the citing document).
        si_tex: the Supporting Information LaTeX source (the cited document).

    Returns:
        A :class:`CrossDocRefReport` -- ``ok`` iff every main-paper "Figure/Table S<n>"
        resolves to an SI float that exists.
    """
    draft_live = _strip_comment_lines(draft_tex)
    si_live = _strip_comment_lines(si_tex)

    n_figures = len(_SI_FIGURE_ENV_RE.findall(si_live))
    n_tables = len(_SI_TABLE_ENV_RE.findall(si_live))

    unresolved: set[tuple[str, int]] = set()
    for match in _CROSS_DOC_SREF_RE.finditer(draft_live):
        is_figure = match.group("kind").lower().startswith("fig")
        number = int(match.group("num"))
        available = n_figures if is_figure else n_tables
        if number < 1 or number > available:
            unresolved.add(("Figure" if is_figure else "Table", number))

    ordered = sorted(unresolved, key=lambda kn: (kn[0], kn[1]))
    unresolved_refs = [f"{kind} S{number}" for kind, number in ordered]
    return CrossDocRefReport(unresolved_refs=unresolved_refs, ok=not unresolved_refs)


__all__ = [
    "LatexRefReport",
    "check_latex_ref_consistency",
    "CrossDocRefReport",
    "check_cross_doc_s_refs",
]
