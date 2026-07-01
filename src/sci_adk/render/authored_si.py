"""
The AUTHORED ``si.tex`` render path (SPEC-SI-AUTHORING-001, Pillar A / artifact ②).

design/si-belief-record-split.md v0.4 relocates the record/belief boundary by ARTIFACT
TYPE: ``main.tex`` and ``si.tex`` are both AUTHORED belief, and the auditable RECORD is
the deposit (``runs/`` + ``sci-adk verify`` + the deterministic ``record.tex``). M1 freed
the ``si.tex`` slot by relocating the deterministic dump to the deposit's ``record.tex``.
This module fills that freed slot with the AUTHORED belief artifact -- the OVERFLOW of
``main.tex``.

It REUSES the ``paper.py`` prose machinery, NOT the ``render_si_latex`` dump (REQ-SA-101):

  - the SAME per-slot pipeline ``render_paper_latex`` uses -- ``substitute_factrefs``
    (fidelity, FAIL-LOUD) -> ``_novelty_prose`` (which calls ``_latex_sanitize_prose``,
    so ``\\ref`` / ``\\cite`` / ``\\novelty`` survive verbatim and everything else is
    escaped). So every measured value the SI states is the record's (REQ-SA-103), a
    hand-authored table cell citing ``\\evval`` is gated cell-by-cell (REQ-SA-104), and a
    bare ``\\status`` resolves to the recorded verdict -- the SI narrative is the agent's,
    the numbers are the record's.

It KEEPS the SI conventions from ``si.py`` (S-numbering + the per-kind figure-package
preamble guards) but DROPS the type-sorted record sections (R4 -- the SI is FREE-structured,
not the IMRaD skeleton of ``render_paper_latex`` and not the record dump of
``render_si_latex``):

  - ``\\thefigure`` / ``\\thetable`` = ``S\\arabic{...}`` so a main-paper plain-text
    "Figure S<n>" matches the printed SI number (REQ-SA-106), and the author's inline
    "(Figure S<n>)" text survives verbatim (it is prose, not a ``\\ref``);
  - ``pgfplots`` only when a native SI figure is present, ``graphicx`` only when an image
    SI figure is present -- a figure-less SI stays minimal.

Figure ownership is XOR across ``main.tex`` / ``si.tex`` (REQ-SA-105): the SI owns ONLY
its ``AuthoredSI.figures`` (the supplementary set); the main figures live only in
``render_paper_latex``. Both draw on the SAME co-located ``figures/`` file set.

This module lives in ``render/`` (the kernel) and imports ``sci_adk.core`` + sibling
render helpers ONLY (the F4 seam -- no adapter, no loop, no LLM, no fs/network). PURE +
deterministic GIVEN the authored input: the in-session agent authors the ``AuthoredSI``
at runtime (never sci-adk-generated, the same spirit as ``PaperProse``); same inputs ->
byte-identical output.

Reference: design/si-belief-record-split.md (v0.4, Pillar A), design/abstractions.md,
design/directory-structure.md (render/), src/sci_adk/render/paper.py (the reused prose
pipeline), src/sci_adk/render/si.py (the S-numbering + figure-package conventions).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from sci_adk.core.claim import Claim
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import Spec
from sci_adk.render.factref import substitute_factrefs
from sci_adk.render.figures import (
    AnyFigure,
    figure_labels,
    order_figures_by_reference,
    render_figure,
)
from sci_adk.render.novelty import (
    NOVELTY_NEWCOMMAND,
    NOVELTY_RENDER_RE,
    has_novelty_markup,
    novelty_scope_suffix,
)
from sci_adk.render.paper import _latex_sanitize
from sci_adk.render.prose import AuthoredSI


def _render_si_novelty(
    text: str, spec: Spec, novelty_decisions: Sequence[EvidenceItem]
) -> str:
    """Render ``\\novelty{kind}{hyp}{text}`` markup in AUTHORED SI LaTeX (FAIL-LOUD gate).

    The authored-SI twin of :func:`paper._novelty_prose`, with ONE deliberate difference:
    the surrounding authored LaTeX is emitted VERBATIM (NOT prose-escaped), because the SI
    body is authored LaTeX of a submission document (hand-authored tables, REQ-SA-104).
    It still SPLIT-and-stitches on :data:`novelty.NOVELTY_RENDER_RE` exactly as
    ``_novelty_prose`` does, so the ``\\novelty`` gate is identical:

      - each gap between/around the spans -> emitted verbatim (the author's LaTeX);
      - each span ``\\novelty{kind}{hyp}{inner}`` -> re-emitted SURVIVING into the ``.tex``
        with the record-derived honest scope baked in by :func:`novelty.novelty_scope_suffix`
        (FAIL-LOUD: an unsupported / unknown-hyp / bad-kind novelty raises ``ValueError``).

    Text with NO ``\\novelty`` markup is returned unchanged. PURE + FAIL-LOUD.
    """
    out: List[str] = []
    pos = 0
    for match in NOVELTY_RENDER_RE.finditer(text):
        out.append(text[pos : match.start()])  # gap -> authored LaTeX, verbatim
        kind, hyp, inner = match.group(1), match.group(2), match.group(3)
        suffix = novelty_scope_suffix(kind, hyp, spec, novelty_decisions)  # fail-loud
        out.append("\\novelty{" + kind + "}{" + hyp + "}{" + inner + suffix + "}")
        pos = match.end()
    out.append(text[pos:])  # trailing gap / whole string if no spans
    return "".join(out)


def si_figure_labels(si: AuthoredSI) -> List[str]:
    """The ``fig:<id>`` labels the authored SI owns (the supplementary figure set).

    PURE. The SINGLE source of truth for "which figure labels live in ``si.tex``", used by
    the figure-ownership XOR check (REQ-SA-105): a caller intersects this with the main
    paper's :func:`figures.figure_labels` and asserts the intersection is empty (a figure
    is owned by exactly one document). Reuses ``figure_labels`` so the unique-id
    enforcement is shared (a duplicate SI figure id fails loud, same as the main paper).
    """
    return figure_labels(si.figures)


def render_authored_si_latex(
    si: Optional[AuthoredSI],
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    bib_path: Optional[str] = None,
) -> Optional[str]:
    """Render the AUTHORED ``si.tex`` (belief artifact ②) -- REUSE the prose pipeline.

    PURE + deterministic GIVEN the authored input + FAIL-LOUD (an unbacked ``\\evval`` /
    ``\\status`` raises ``ValueError`` via :func:`factref.substitute_factrefs`). Reuses the
    SAME per-slot pipeline ``render_paper_latex`` applies to its prose -- factref
    substitution -> ``\\novelty`` render + the prose sanitizer (``\\ref`` / ``\\cite``
    preserved). NOT routed through ``render_si_latex`` (no record-dump sections).

    Args:
        si: the authored Supporting Information (title + free-structured sections + the
            supplementary figures the SI owns). ``None`` -> the run carries NO ``si.tex``
            (a thin/absent SI is permitted, REQ-SA-107): this returns ``None`` and the
            caller writes nothing. An ``AuthoredSI`` with no sections renders a minimal,
            valid standalone document.
        spec: the compiled Spec (its id is the title fallback + the document header).
        claims: the run's Claims (their statuses back ``\\status{<hyp>}`` in the prose).
        evidence: the Evidence record (``\\evval`` values resolve here); optional.
        bib_path: optional path of the SI's co-located ``references_SI.bib`` (M6,
            REQ-SA-601). When supplied, ``\\bibliographystyle{plainnat}`` +
            ``\\bibliography{<stem>}`` (``<stem> = Path(bib_path).stem``) are emitted
            before ``\\end{document}`` -- so the author's ``\\citep``/``\\cite`` resolve
            instead of rendering ``[?]`` (symmetric to ``paper.py:831-834`` and
            ``si.py:540-543``). ``None`` (a citation-free SI, or no pool) -> NO
            ``\\bibliography`` line (REQ-SA-602). The renderer stays PURE: it never
            reads the file; the caller (the compiler) builds + co-locates it.

    Returns:
        A STANDALONE LaTeX document string, or ``None`` when ``si`` is ``None``.

    Raises:
        ValueError: on an unbacked ``\\evval``/``\\status`` macro, an unknown figure id,
            or a duplicate figure id (record fidelity -- never invent a fact or clobber a
            label).
    """
    if si is None:
        return None

    evidence = list(evidence or [])
    claims = list(claims)
    figures: List[AnyFigure] = list(si.figures)
    # Novelty decisions (bears_on=[]) back the \novelty{} markup re-derivation (N2 gate),
    # exactly as the paper/SI-dump prose slots get the gate.
    novelty_decisions = [
        ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
    ]

    def _slot(text: str) -> str:
        # The authored SI body is AUTHORED LaTeX of a SUBMISSION belief document: it
        # legitimately carries hand-authored tables (\begin{tabular} ... & ... \\, REQ-SA-104)
        # and other authored structure, so -- unlike a main-paper PROSE slot -- it is NOT
        # passed through the prose ESCAPER (which would mangle a table into literal text).
        # The author owns the LaTeX correctness of their own section, the same honest limit
        # as row completeness (design §4 / §8.2).
        #
        # What DOES run -- the gates that make the SI's numbers the record's (the load-bearing
        # reuse, REQ-SA-101/103): (1) substitute_factrefs (\evval/\status fidelity, FAIL-LOUD;
        # a hand-authored table's \evval cells are substituted to recorded values CELL BY CELL,
        # REQ-SA-104), then (2) the \novelty render+gate (FAIL-LOUD on an unbacked novelty
        # claim, scope baked from the record). \ref/\cite and all authored LaTeX pass through
        # verbatim. A bare-literal number is outside the fidelity gate (the documented honest
        # limit, identical to main.tex; the P2 number-audit -- already wired over si.tex --
        # is the belief-side backstop).
        return _render_si_novelty(
            substitute_factrefs(text.strip(), evidence, claims),
            spec,
            novelty_decisions,
        )

    # Title: the agent's SI title, else spec.id (the same short fallback the paper uses).
    title = (si.title.strip() if si.title else "") or spec.id

    lines: List[str] = []
    # -- Preamble (standalone document; same base packages as the paper / dump). Figure
    #    packages are added PER KIND (mirrors si.py): pgfplots only for a native figure,
    #    graphicx only for an image figure -- a figure-less SI stays minimal.
    has_native = any(f.kind == "native" for f in figures)
    has_image = any(f.kind == "image" for f in figures)
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\usepackage{url}")
    lines.append(r"\usepackage{natbib}")
    if has_native or has_image:
        # Figure font policy (design/paper-publishing-requirements.md F2), mirroring the
        # paper/dump: newtxmath (Times-compatible math) + helvet (Arial-compatible sans).
        lines.append(r"\usepackage{amsmath}")
        lines.append(r"\usepackage{newtxmath}")
        lines.append(r"\usepackage[scaled]{helvet}")
    if has_native:
        lines.append(r"\usepackage{pgfplots}")
        lines.append(r"\pgfplotsset{compat=1.18}")
    if has_image:
        lines.append(r"\usepackage{graphicx}")
    # \novelty{kind}{hyp}{text} survives into si.tex; this \newcommand makes LaTeX render
    # only the text. Emitted ONLY when an authored section carries novelty markup.
    has_nov = any(has_novelty_markup(s.body) for s in si.sections if s.body)
    if has_nov:
        lines.append(NOVELTY_NEWCOMMAND)
    # SI numbering convention (REQ-SA-106): tables/figures are S-prefixed, so a main-paper
    # plain-text "Figure S<n>" matches this document's printed number (cross-document \ref
    # via xr is DROPPED, design §6 -- linkage stays plain-text S-refs + the cross-doc gate).
    lines.append(r"\renewcommand{\thetable}{S\arabic{table}}")
    lines.append(r"\renewcommand{\thefigure}{S\arabic{figure}}")
    lines.append(f"\\title{{{_latex_sanitize(title)}}}")
    lines.append(r"\author{}")
    lines.append(r"\date{\today}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")

    # -- Authored sections, IN AUTHORED ORDER (free structure; no record-type axis). Each
    #    body goes through the reused prose pipeline (fidelity + novelty + sanitizer), so a
    #    hand-authored table's \evval cells are gated cell-by-cell here (REQ-SA-104) and an
    #    inline plain-text "(Figure S<n>)" survives verbatim (REQ-SA-106).
    for section in si.sections:
        lines.append(f"\\section{{{_latex_sanitize(section.title)}}}")
        if section.body:
            lines.append(_slot(section.body))
        lines.append("")

    # -- Supplementary figures the SI OWNS (REQ-SA-105: XOR with the main paper). Numbered
    #    in supply order against the authored body (the SI is standalone; its figures are
    #    its own set, not shared with the main paper's numbering). render_figure routes by
    #    kind (native pgfplots from the record / image \includegraphics of figures/fig<N>).
    if figures:
        body_latex = "\n".join(s.body for s in si.sections if s.body)
        lines.append(r"\section{Figures}")
        lines.append("")
        for number, fig in order_figures_by_reference(figures, body_latex):
            lines.append(render_figure(fig, evidence, number))
            lines.append("")

    # -- Bibliography (M6, REQ-SA-601/602): the SI's OWN references, symmetric to the main
    #    paper (paper.py:831-834) and the record dump (si.py:540-543). The author's
    #    \citep/\cite survive the _slot pipeline verbatim; a supplied bib_path attaches the
    #    co-located references_SI.bib so they resolve. bib_path=None (a citation-free SI or
    #    no pool) emits NOTHING -- \usepackage{natbib} above is harmless without it.
    if bib_path is not None:
        stem = Path(bib_path).stem
        lines.append(r"\bibliographystyle{plainnat}")
        lines.append(f"\\bibliography{{{stem}}}")

    lines.append(r"\end{document}")
    return "\n".join(lines)


__all__ = ["render_authored_si_latex", "si_figure_labels"]
