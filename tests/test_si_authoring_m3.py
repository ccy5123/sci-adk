"""
SPEC-SI-AUTHORING-001 Milestone M3 (RED-first): the AUTHORED ``si.tex`` path -- the
freed ``si.tex`` slot (M1) filled with an AUTHORED belief artifact (the overflow of
``main.tex``), reusing the ``paper.py`` prose machinery (NOT ``render_si_latex``).
Design source: design/si-belief-record-split.md v0.4 (Pillar A).

Pillar A requirements pinned here (the authored-SI render path level):
  - REQ-SA-101 (AC-A1): the authored si.tex is produced by the paper.py prose pipeline
    (sanitizer + \\evval/\\status fidelity substitution + \\ref/\\cite/\\novelty
    passthrough), NOT the render_si_latex deterministic dump (no type-sorted record
    sections).
  - REQ-SA-102 (AC-A2): FREE authored structure -- sections render in the agent's order,
    no fixed record-type axis; the optional default skeleton is used only when the agent
    supplies no structure.
  - REQ-SA-103 (AC-A3): every measured value is fidelity-gated via \\evval/\\status
    (FAIL-LOUD on an unknown id/field/hypothesis), exactly as main.tex.
  - REQ-SA-104 (AC-A4): tables are HAND-AUTHORED -- a cell citing a recorded value is
    written with \\evval and gated cell-by-cell; the dump's tabular builder is NOT reused.
  - REQ-SA-105 (AC-A5): figure ownership is XOR across main.tex/si.tex from one shared
    figures/ file set (main_labels INTERSECT si_labels == EMPTY).
  - REQ-SA-106 (AC-A6): inline plain-text "Figure S<n>" refs + S-numbering preserved
    (\\thefigure/\\thetable = S\\arabic{...}).
  - REQ-SA-107 (AC-A7): a thin/absent SI is permitted -- a 1-hypothesis run gets a short
    authored si.tex or none, no degenerate-case machinery.

The render path is deterministic GIVEN the authored input (the AuthoredSI model); the
in-session agent authors that input at runtime -- there is NO LLM in the render path.
"""

from __future__ import annotations

import pytest

# Reuse the established record fixtures (do not re-author them -- the authored path is
# gated against the SAME record the dump tests use).
from tests.test_si import _basic_record, _figure, _hyp, _spec, _quant_ev, _claim

from sci_adk.core.claim import ClaimStatus
from sci_adk.render.figures import figure_labels
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import PaperProse


# ---------------------------------------------------------------------------
# AC-A1 [BELIEF-SIDE] -- the authored SI reuses the prose machinery, not the dump
# (REQ-SA-101). The model + the render entry point are NEW (M3).
# ---------------------------------------------------------------------------

def test_authored_si_model_and_render_path_exist():
    """The free-structured SI prose model + the authored render entry point exist."""
    from sci_adk.render.prose import AuthoredSI, SISection  # noqa: F401
    from sci_adk.render.authored_si import render_authored_si_latex  # noqa: F401


def test_authored_si_is_a_standalone_latex_document():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(
        title="Supplementary discussion",
        sections=[SISection(title="Extended discussion", body="An overflow note.")],
    )
    tex = render_authored_si_latex(si, spec, claims, evidence)
    assert r"\documentclass{article}" in tex
    assert r"\begin{document}" in tex
    assert r"\end{document}" in tex
    assert r"\usepackage[utf8]{inputenc}" in tex


def test_authored_si_is_NOT_the_record_dump():
    """REQ-SA-101 / AC-A1: the authored SI must NOT carry the type-sorted record dump
    sections (Evidence record / Quantitative data / Claims and verdicts / Record
    integrity) -- those live ONLY in the deterministic record artifact (record.tex)."""
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(
        sections=[SISection(title="Notes", body="Free prose, no dump.")],
    )
    tex = render_authored_si_latex(si, spec, claims, evidence)
    assert r"\section{Evidence record}" not in tex
    assert r"\section{Quantitative data}" not in tex
    assert r"\section{Claims and verdicts}" not in tex
    assert r"\section{Record integrity}" not in tex
    # And not the dump's identity line.
    assert "deterministic dump of every Evidence item" not in tex


def test_authored_si_preserves_ref_and_cite():
    """The authored body is authored LaTeX of a submission document: \\ref/\\cite
    cross-references survive verbatim so the SI can point at a figure / cite literature
    (the fidelity + novelty gates still run -- see the \\evval / \\novelty tests)."""
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(
        sections=[
            SISection(
                title="Refs",
                body=r"See \ref{fig:growth} and \cite{Smith2020}.",
            )
        ],
    )
    tex = render_authored_si_latex(si, spec, claims, evidence)
    assert r"\ref{fig:growth}" in tex      # cross-reference preserved
    assert r"\cite{Smith2020}" in tex      # citation preserved


# ---------------------------------------------------------------------------
# AC-A2 [BELIEF-SIDE] -- FREE authored structure (REQ-SA-102). Sections render in the
# agent's order; the optional default skeleton is used only when no structure is given.
# ---------------------------------------------------------------------------

def test_authored_si_sections_render_in_authored_order():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    # NON-default order: an extended-discussion section BEFORE a methods section.
    si = AuthoredSI(
        sections=[
            SISection(title="Extended discussion", body="disc body"),
            SISection(title="Supplementary methods", body="meth body"),
        ],
    )
    tex = render_authored_si_latex(si, spec, claims, evidence)
    i_disc = tex.index(r"\section{Extended discussion}")
    i_meth = tex.index(r"\section{Supplementary methods}")
    assert i_disc < i_meth  # the agent's order, not a forced record-type axis


def test_default_skeleton_is_optional_and_reorganizable():
    """The renderer MAY offer a conventional default skeleton, but the agent supplies
    structure freely -- the skeleton is not forced."""
    from sci_adk.render.prose import AuthoredSI

    skeleton = AuthoredSI.default_skeleton()
    titles = [s.title for s in skeleton.sections]
    # A conventional skeleton (Supplementary Methods / Notes / Figures / Tables); the
    # exact set is the renderer's offer, the agent reorganizes per overflow.
    assert "Supplementary Methods" in titles
    assert len(skeleton.sections) >= 2


# ---------------------------------------------------------------------------
# AC-A3 [BELIEF-SIDE] -- every measured value is fidelity-gated (REQ-SA-103).
# ---------------------------------------------------------------------------

def test_authored_si_substitutes_evval_and_status():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()  # ev-1 point=0.0, claim SUPPORTED on hyp-t1
    si = AuthoredSI(
        sections=[
            SISection(
                title="Result detail",
                body=r"The point was \evval{ev-1}{point}; verdict \status{hyp-t1}.",
            )
        ],
    )
    tex = render_authored_si_latex(si, spec, claims, evidence)
    # The macros are SUBSTITUTED with the recorded values (not left as literals).
    assert r"\evval" not in tex
    assert r"\status{" not in tex
    assert "supported" in tex  # the recorded verdict


def test_authored_si_fidelity_gate_fails_loud_on_unknown_evidence():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(
        sections=[SISection(title="Bad", body=r"value \evval{ev-DOES-NOT-EXIST}{point}.")],
    )
    with pytest.raises(ValueError):
        render_authored_si_latex(si, spec, claims, evidence)


# ---------------------------------------------------------------------------
# AC-A4 [BELIEF-SIDE] -- hand-authored tables, gated per cell; dump table NOT reused
# (REQ-SA-104).
# ---------------------------------------------------------------------------

def test_authored_si_table_is_hand_authored_and_gated_per_cell():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()  # ev-1 point=0.0, ev-2 point=9.0
    # A hand-authored tabular whose cells cite recorded values via \evval.
    table = (
        r"\begin{table}[htbp]\centering"
        r"\begin{tabular}{lr}"
        r"run & point \\"
        r"first & \evval{ev-1}{point} \\"
        r"second & \evval{ev-2}{point} \\"
        r"\end{tabular}"
        r"\caption{Hand-authored.}\label{tab:hand}"
        r"\end{table}"
    )
    si = AuthoredSI(sections=[SISection(title="Tables", body=table)])
    tex = render_authored_si_latex(si, spec, claims, evidence)
    # Each cited cell is the RECORDED value (gated cell-by-cell).
    assert "first & 0" in tex
    assert "second & 9" in tex
    # The dump's deterministic builder label is NOT present (its logic stays in record.tex).
    assert r"\label{tab:s1}" not in tex


def test_authored_si_table_cell_unbacked_value_fails_loud():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    table = (
        r"\begin{tabular}{lr}x & \evval{ev-1}{NOT_A_FIELD} \\\end{tabular}"
    )
    si = AuthoredSI(sections=[SISection(title="T", body=table)])
    with pytest.raises(ValueError):
        render_authored_si_latex(si, spec, claims, evidence)


# ---------------------------------------------------------------------------
# AC-A5 [BELIEF-SIDE] -- figure ownership is XOR across main/SI from one shared file
# set (REQ-SA-105): main_labels INTERSECT si_labels == EMPTY.
# ---------------------------------------------------------------------------

def test_figure_ownership_is_xor_across_main_and_si():
    from sci_adk.render.authored_si import (
        render_authored_si_latex,
        si_figure_labels,
    )
    from sci_adk.render.prose import AuthoredSI

    spec, claims, evidence = _basic_record()

    # Main paper owns fig "growth"; the SI owns a DIFFERENT supplementary fig "detail".
    main_fig = _figure(fig_id="growth", ev_id="ev-1")
    si_fig = _figure(fig_id="detail", ev_id="ev-2")

    main_prose = PaperProse(
        title="Main", results=r"Main result, see \ref{fig:growth}."
    )
    main_tex = render_paper_latex(
        spec, claims, evidence, prose=main_prose, figures=[main_fig]
    )
    si = AuthoredSI(
        sections=[],
        figures=[si_fig],
    )
    si_tex = render_authored_si_latex(si, spec, claims, evidence)

    main_labels = set(figure_labels([main_fig]))
    si_labels = set(si_figure_labels(si))
    # XOR: a figure label appears in exactly one document.
    assert main_labels & si_labels == set()
    # Each label is in fact present in its own rendered document.
    assert r"\label{fig:growth}" in main_tex
    assert r"\label{fig:detail}" in si_tex
    # One shared figures/ file set: the SI image/native figures reference figures/... ;
    # here both are native (inline), so the contract is the label-set disjointness above.


# ---------------------------------------------------------------------------
# AC-A6 [BELIEF-SIDE] -- inline plain-text S-refs + S-numbering preserved (REQ-SA-106).
# ---------------------------------------------------------------------------

def test_authored_si_preserves_s_numbering_convention():
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(sections=[SISection(title="N", body="x")], figures=[_figure()])
    tex = render_authored_si_latex(si, spec, claims, evidence)
    assert r"\renewcommand{\thefigure}{S\arabic{figure}}" in tex
    assert r"\renewcommand{\thetable}{S\arabic{table}}" in tex


def test_authored_si_inline_plain_text_s_ref_survives():
    """An author writes an inline plain-text "(Figure S1)" in the body -- it must survive
    verbatim (it is not a \\ref macro; it is the cross-doc plain-text convention)."""
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(
        sections=[SISection(title="N", body="See the supplement (Figure S1).")],
    )
    tex = render_authored_si_latex(si, spec, claims, evidence)
    assert "(Figure S1)" in tex


# ---------------------------------------------------------------------------
# AC-A7 [BELIEF-SIDE] -- thin/absent SI permitted (REQ-SA-107).
# ---------------------------------------------------------------------------

def test_thin_authored_si_with_no_sections_is_valid():
    """A 1-hypothesis run with no overflow: an EMPTY authored SI still renders a minimal,
    valid standalone document (no degenerate-case machinery)."""
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI

    hyp = _hyp()
    spec = _spec(hyp)
    evidence = [_quant_ev("ev-1", point=1.0)]
    claims = [_claim(hyp, ClaimStatus.SUPPORTED, ev_id="ev-1")]

    si = AuthoredSI(sections=[])
    tex = render_authored_si_latex(si, spec, claims, evidence)
    assert r"\documentclass{article}" in tex
    assert r"\end{document}" in tex


def test_absent_authored_si_is_permitted_via_none():
    """Absent SI: the render path returns None for an AuthoredSI that is itself None --
    a run may carry no si.tex at all (the caller writes nothing)."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    assert render_authored_si_latex(None, spec, claims, evidence) is None
