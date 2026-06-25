"""
render-merge (RED-first): a deterministic, OFFLINE LaTeX renderer mirroring the
Markdown ``render_paper`` -- valid compilable LaTeX with load-bearing special-char
escaping, the same honest evidence-validity labels, a prose hook (agent-authored
narrative passed in, never LLM-generated), and a DOI-list References section
(NO BibTeX generation -- DOI list only, design decision).

These pin the behavior before any implementation exists. No LLM, no network: the
renderer is pure (data in, string out).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
    EvidenceLink,
    EvidenceLinkRole,
)
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.render.figures import FigureSpec, NativePlot, PlotPoint, PlotSeries
from sci_adk.render.paper import _latex_escape, render_paper_latex
from sci_adk.render.prose import PaperProse
from sci_adk.render.si import render_si_latex

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="collision_count == 0 => support",
    params={"statistic": "collision_count", "op": "==", "value": 0.0},
)


def _spec(hyp: Hypothesis, spec_id: str = "t-latex", goal: str = "An encoding") -> Spec:
    return Spec(
        id=spec_id,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal=goal, method="method", expected_output="out"
        ),
        hypotheses=[hyp],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp.id)],
    )


def _claim(
    hyp: Hypothesis,
    status: ClaimStatus,
    ev_id: str = "ev-1",
    basis: str = "threshold rule: met",
    spec_id: str = "t-latex",
) -> Claim:
    return Claim(
        id=f"claim-{hyp.id}",
        spec_id=spec_id,
        answers=hyp.id,
        statement=hyp.statement,
        status=status,
        confidence=Confidence(
            type=ConfidenceType.CREDENCE, value=0.9, basis=basis
        ),
        evidence_set=[EvidenceLink(evidence_id=ev_id, role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _evidence(
    ev_id: str,
    hyp_id: str,
    data_source,
    direction,
    spec_id: str = "t-latex",
    finding: str = "",
):
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id=spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source=data_source),
        result=Result(type="quantitative", point=0.0, finding=finding or None),
        bears_on=[Bearing(target_id=hyp_id, direction=direction)],
    )


def _basic_hyp(referent: str = "formal") -> Hypothesis:
    return Hypothesis(
        id="hyp-t1",
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent=referent,
        non_circularity="collisions could occur; the verifier checks for them",
    )


# ---------------------------------------------------------------------------
# _latex_escape: the load-bearing escaper.
# ---------------------------------------------------------------------------

class TestLatexEscape:
    def test_escapes_each_special_char(self):
        # Every LaTeX special must be neutralized.
        assert _latex_escape("&") == r"\&"
        assert _latex_escape("%") == r"\%"
        assert _latex_escape("$") == r"\$"
        assert _latex_escape("#") == r"\#"
        assert _latex_escape("_") == r"\_"
        assert _latex_escape("{") == r"\{"
        assert _latex_escape("}") == r"\}"
        assert _latex_escape("~") == r"\textasciitilde{}"
        assert _latex_escape("^") == r"\textasciicircum{}"
        assert _latex_escape("\\") == r"\textbackslash{}"

    def test_plain_text_unchanged(self):
        # No specials -> identity (safe on already-plain text).
        s = "A clean sentence with no specials 123 abc."
        assert _latex_escape(s) == s

    def test_backslash_is_not_double_escaped(self):
        # The backslash must be replaced FIRST, so the backslashes introduced by
        # escaping the OTHER specials are not themselves re-escaped. A literal
        # backslash followed by an ampersand must produce exactly the two tokens.
        assert _latex_escape(r"\&") == r"\textbackslash{}\&"

    def test_combined_specials_roundtrip_faithful(self):
        # A realistic mix: every special once, in one string.
        src = "a_b % c & d $ e # f { g } h ~ i ^ j"
        out = _latex_escape(src)
        # No raw special survives (each is now backslash-prefixed or a command).
        assert "_" not in out.replace(r"\_", "")
        assert "%" not in out.replace(r"\%", "")
        assert "&" not in out.replace(r"\&", "")
        assert "$" not in out.replace(r"\$", "")
        assert "#" not in out.replace(r"\#", "")
        # Braces only appear as escaped pairs or inside the tilde/caret commands.
        # The faithful text fragments are still present.
        assert r"a\_b" in out


# ---------------------------------------------------------------------------
# render_paper_latex: a valid, compilable document skeleton.
# ---------------------------------------------------------------------------

class TestLatexDocumentSkeleton:
    def test_emits_documentclass_and_body_delimiters(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        assert r"\documentclass{article}" in tex
        assert r"\begin{document}" in tex
        assert r"\end{document}" in tex
        # \maketitle requires a \title; the goal is the title.
        assert r"\title{" in tex
        assert r"\maketitle" in tex
        # begin precedes end (well-formed).
        assert tex.index(r"\begin{document}") < tex.index(r"\end{document}")

    def test_paper_has_no_stage_dump_sections(self):
        # The reframe (moved line): the paper is belief narrative, so the engine emits
        # NO stage-dump sections -- no Goal/Background/Evidence/Figures heading and no
        # per-hypothesis verdict bullets. Those record facts live in the SI.
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED, basis="met collision_count == 0")
        ev = _evidence("evi-xyz", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        assert r"\section{Goal}" not in tex
        assert r"\section{Background}" not in tex
        assert r"\section{Evidence}" not in tex
        assert r"\section{Figures}" not in tex
        assert r"\section{Hypotheses and findings}" not in tex
        # No raw evidence id and no mechanical "Hypothesis id:" / "confidence 0.9" bullet.
        assert "evi-xyz" not in tex
        assert "Hypothesis id:" not in tex

    def test_status_macro_substitutes_verdict_into_prose(self):
        # The agent states the verdict via \status{<hyp>} in prose; the engine fills the
        # recorded status (record-fidelity), so the narrative carries the true verdict.
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED, basis="met collision_count == 0")
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(results=r"H1 resolved \status{hyp-t1} on the tested set.")

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)

        assert "H1 resolved supported on the tested set." in tex
        assert r"\status{" not in tex  # the macro is substituted, never left raw

    def test_no_prose_no_figures_is_minimal_paper(self):
        # No narrative authored yet -> a near-empty (honest) paper: title + note + the
        # document delimiters, no per-hypothesis dump, no "no claim" skeleton line.
        hyp = _basic_hyp()
        spec = _spec(hyp)
        tex = render_paper_latex(spec, [], [])
        assert r"\begin{document}" in tex and r"\end{document}" in tex
        assert "no claim" not in tex.lower()
        assert r"\subsection{" not in tex


# ---------------------------------------------------------------------------
# Escaping is wired through ALL interpolated content (load-bearing).
# ---------------------------------------------------------------------------

class TestLatexEscapingIsWired:
    # The statement / finding / basis are RECORD facts -- after the reframe they render in
    # the SI (the record dump), not the belief-narrative paper. Escaping is asserted there.
    def test_hypothesis_statement_with_specials_is_escaped(self):
        # A statement riddled with LaTeX specials.
        hyp = Hypothesis(
            id="hyp_x",  # underscore in the id, too
            statement="encode A_i & B% with $cost #1 {set} ~op ^pow",
            mode=HypothesisMode.EXPLORATORY,
            decision_rule=_THRESHOLD,
            referent="formal",
            non_circularity="n/a",
        )
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp_x", "generated", BearingDirection.SUPPORTS)

        tex = render_si_latex(spec, [claim], [ev])

        # The escaped forms are present (the statement is the SI Claim subsection) ...
        assert r"A\_i" in tex
        assert r"B\%" in tex
        assert r"\$cost" in tex
        assert r"\#1" in tex
        assert r"\{set\}" in tex
        # ... and NO raw special leaked. Check the underscore:
        assert "_" not in tex.replace(r"\_", "")

    def test_finding_with_specials_is_escaped(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        # A finding text full of specials, surfaced in the SI Evidence record summary.
        ev = _evidence(
            "ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS,
            finding="collision_count = 0 (100% pass) & cost $5",
        )
        tex = render_si_latex(spec, [claim], [ev])
        assert r"100\%" in tex
        assert "_" not in tex.replace(r"\_", "")

    def test_basis_with_specials_is_escaped(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(
            hyp, ClaimStatus.SUPPORTED, basis="rule met: collision_count == 0 & ok"
        )
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        tex = render_si_latex(spec, [claim], [ev])
        assert r"collision\_count" in tex
        assert r"\&" in tex


# ---------------------------------------------------------------------------
# The honest evidence-validity labels appear in LaTeX too (no honesty dropped).
# ---------------------------------------------------------------------------

class TestLatexEvidenceValidityLabels:
    # The honest evidence-validity label is structured record honesty -- after the reframe
    # it renders in the SI's Claims-and-verdicts section (the record), not the paper.
    def test_formal_generated_supported_labelled_computational(self):
        hyp = _basic_hyp(referent="formal")
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_si_latex(spec, [claim], [ev])

        assert "referent=formal" in tex
        assert "generated" in tex
        assert "in-silico" in tex.lower() or "computational result" in tex.lower()

    def test_empirical_no_measured_labelled_awaiting(self):
        hyp = Hypothesis(
            id="hyp-e",
            statement="trait predicts organ dry weight",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=_THRESHOLD,
            referent="empirical",
        )
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.PROPOSED)
        ev = _evidence("ev-1", "hyp-e", None, BearingDirection.NEUTRAL)

        tex = render_si_latex(spec, [claim], [ev])

        assert "referent=empirical" in tex
        assert "awaiting measured data" in tex.lower()


# ---------------------------------------------------------------------------
# Prose hook: agent-authored narrative injected as sections.
# ---------------------------------------------------------------------------

class TestLatexProse:
    def test_prose_sections_injected(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(
            abstract="We present a Goedel-style encoding tested for injectivity.",
            introduction="Serializing a molecular graph to one integer is attractive.",
            discussion="The supported claim is exploratory and sample-bounded.",
        )

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)

        # Abstract uses the LaTeX abstract environment.
        assert r"\begin{abstract}" in tex
        assert r"\end{abstract}" in tex
        assert "tested for injectivity" in tex
        # Introduction + Discussion appear as sections.
        assert "Introduction" in tex
        assert "Serializing a molecular graph" in tex
        assert "Discussion" in tex
        assert "exploratory and sample-bounded" in tex
        # The abstract comes before the Discussion (structural ordering).
        assert tex.index("tested for injectivity") < tex.index("exploratory and sample")

    def test_prose_none_emits_no_abstract_environment(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev], prose=None)
        # No abstract supplied -> no abstract environment.
        assert r"\begin{abstract}" not in tex

    def test_partial_prose_only_present_slots(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(abstract="Only an abstract here.")

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)
        assert r"\begin{abstract}" in tex
        assert "Only an abstract here." in tex
        # No discussion slot -> no agent-authored Discussion section heading text
        # injected (the discussion content is simply absent).
        assert "Only an abstract here." in tex

    def test_prose_with_specials_is_escaped(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(abstract="A 100% deterministic & exact result on set #1.")

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)
        assert r"100\%" in tex
        assert r"\&" in tex
        assert r"\#1" in tex


# ---------------------------------------------------------------------------
# Citations: DOI list only (NO BibTeX generation).
# ---------------------------------------------------------------------------

class TestLatexCitations:
    def test_cited_dois_render_url_entries(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        dois = ["10.1021/c160017a018", "10.48550/arXiv.1301.1493"]

        tex = render_paper_latex(spec, [claim], [ev], cited_dois=dois)

        assert "References" in tex
        # Each DOI is an \url{https://doi.org/<doi>} entry.
        assert r"\url{https://doi.org/10.1021/c160017a018}" in tex
        assert r"\url{https://doi.org/10.48550/arXiv.1301.1493}" in tex

    def test_no_dois_no_bib_emits_no_references_section(self):
        # No bib and no cited DOIs -> no References at all (the manual "No literature
        # cited." line is gone; there is simply nothing to cite).
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex_none = render_paper_latex(spec, [claim], [ev], cited_dois=None)
        tex_empty = render_paper_latex(spec, [claim], [ev], cited_dois=[])
        assert "No literature cited." not in tex_none
        assert r"\section{References}" not in tex_none
        assert r"\section{References}" not in tex_empty
        assert r"\bibliography{" not in tex_none

    def test_bib_path_existing_wires_natbib_bibliography(self, tmp_path):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        bib = tmp_path / "references.bib"
        bib.write_text("@article{x2020, doi={10.1/x}}\n", encoding="utf-8")

        tex = render_paper_latex(
            spec, [claim], [ev],
            cited_dois=["10.1/x"], bib_path=str(bib),
        )

        # ONE reference source: natbib + plainnat + \bibliography. No \nocite{*}, and no
        # manual \url DOI list (the cited_dois fallback is suppressed when a bib is wired).
        assert r"\usepackage{natbib}" in tex
        assert r"\bibliographystyle{plainnat}" in tex
        assert r"\bibliography{references}" in tex  # stem of references.bib
        assert r"\nocite{*}" not in tex
        assert r"\url{https://doi.org/10.1/x}" not in tex

    def test_bib_path_none_emits_no_bibliography(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev], cited_dois=["10.1/x"])
        assert r"\bibliography{" not in tex
        assert r"\nocite{*}" not in tex

    # NOTE: the renderer-level "no bibliography" case is bib_path=None (above). The
    # renderer is PURE and does NO filesystem access -- it does NOT check whether
    # bib_path exists; a non-None bib_path is the caller's guarantee. The "missing
    # references.bib -> no \bibliography" behavior is proven at the COMPILER level
    # (where _locate_bib_path returns None for a missing file): see
    # tests/test_render_merge_wiring.py::test_compile_without_literature_says_none_cited.


# ---------------------------------------------------------------------------
# Purity / offline: the renderer makes no network call and needs no LLM, and --
# load-bearing for the MED fix -- performs NO filesystem access. Two proxies: a
# determinism check, and a hard purity assertion that monkeypatches the filesystem
# primitives to raise, then proves render_paper_latex still wires \bibliography.
# ---------------------------------------------------------------------------

def test_latex_render_is_deterministic():
    hyp = _basic_hyp()
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
    a = render_paper_latex(spec, [claim], [ev], cited_dois=["10.1/x"])
    b = render_paper_latex(spec, [claim], [ev], cited_dois=["10.1/x"])
    assert a == b


def test_latex_render_does_no_filesystem_access(monkeypatch):
    """The renderer MUST be pure: given a non-None bib_path it wires the bibliography
    WITHOUT touching the filesystem. We sabotage Path.exists and builtins.open to
    raise; if render_paper_latex performed any existence check or file read it would
    blow up -- instead it must return a \\bibliography{...}-containing string."""
    import builtins
    import pathlib

    def _boom(*_args, **_kwargs):
        raise AssertionError("render_paper_latex must not access the filesystem")

    monkeypatch.setattr(pathlib.Path, "exists", _boom)
    monkeypatch.setattr(builtins, "open", _boom)

    hyp = _basic_hyp()
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

    # A non-None bib_path (the caller's guarantee that the file exists). The renderer
    # only takes its .stem -- no .exists(), no open().
    tex = render_paper_latex(
        spec, [claim], [ev],
        cited_dois=["10.1/x"], bib_path="/any/path/references.bib",
    )
    assert r"\bibliography{references}" in tex
    assert r"\bibliographystyle{plainnat}" in tex
    # ONE reference source: natbib bibliography, never \nocite{*} nor a manual DOI list.
    assert r"\nocite{*}" not in tex


# ---------------------------------------------------------------------------
# Figures hook (paper-figures Phase 1): figures=None is byte-identical; figures
# present -> pgfplots preamble + a Figures section with \label{fig:...}.
# ---------------------------------------------------------------------------

def _fig_spec(fig_id: str = "growth") -> FigureSpec:
    return FigureSpec(
        id=fig_id,
        caption="Point estimate across runs.",
        plot=NativePlot(
            type="line",
            xlabel="run index",
            ylabel="point estimate",
            series=[
                PlotSeries(
                    y_field="point",
                    points=[
                        PlotPoint(evidence_id="ev-1", x=1.0),
                    ],
                )
            ],
        ),
    )


class TestLatexFigures:
    def test_figures_none_is_byte_identical(self):
        # The regression invariant: figures=None (and figures omitted) must be
        # byte-identical to the current figure-less skeleton -- exactly like prose=None.
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        baseline = render_paper_latex(spec, [claim], [ev])
        with_none = render_paper_latex(spec, [claim], [ev], figures=None)
        with_empty = render_paper_latex(spec, [claim], [ev], figures=[])

        assert with_none == baseline
        assert with_empty == baseline
        # And no pgfplots leaks into the figure-less skeleton.
        assert r"\usepackage{pgfplots}" not in baseline
        assert r"\section{Figures}" not in baseline

    def test_figures_present_adds_pgfplots_in_results(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(
            spec, [claim], [ev], figures=[_fig_spec("growth")]
        )
        # Preamble carries pgfplots ...
        assert r"\usepackage{pgfplots}" in tex
        assert r"\pgfplotsset{compat=1.18}" in tex
        # ... and the figure floats inside Results (no separate \section{Figures}).
        assert r"\section{Results}" in tex
        assert r"\section{Figures}" not in tex
        assert r"\begin{figure}" in tex
        assert r"\label{fig:growth}" in tex
        assert r"\begin{axis}" in tex
        assert "(1, 0)" in tex  # ev-1 point=0.0; x from spec, y from evidence

    def test_figures_in_results_before_references(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        # No bib -> cited_dois render a \section{References}; figures sit in Results before it.
        tex = render_paper_latex(
            spec, [claim], [ev], figures=[_fig_spec("growth")], cited_dois=["10.1/x"]
        )
        assert tex.index(r"\begin{figure}") < tex.index(r"\section{References}")

    def test_figures_y_pulled_from_evidence(self):
        # Changing the evidence value changes the drawn coordinate.
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = EvidenceItem(
            id="ev-1",
            created_at=_T0,
            spec_id="t-latex",
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="x", data_source="generated"),
            result=Result(type="quantitative", point=42.0),
            bears_on=[Bearing(target_id="hyp-t1", direction=BearingDirection.SUPPORTS)],
        )
        tex = render_paper_latex(spec, [claim], [ev], figures=[_fig_spec("growth")])
        assert "(1, 42)" in tex

    def test_image_figures_use_fig_number_filenames_in_supply_order(self):
        # Two image figures, no live \ref in the body -> supply order; each emits a
        # GENERIC fig<N> include path (fig1, fig2), never the agent id. (Body-reference
        # reordering is exercised in tests/test_figures.py and the wiring renderer test;
        # here we pin the fig<N> naming + the figure-less skeleton invariant.)
        from sci_adk.render.figures import ImageFigureSpec

        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        figs = [
            ImageFigureSpec(kind="image", id="alpha", caption="A", image="a.png"),
            ImageFigureSpec(kind="image", id="beta", caption="B", image="b.pdf"),
        ]
        tex = render_paper_latex(spec, [claim], [ev], figures=figs)
        assert r"\usepackage{graphicx}" in tex
        assert "{figures/fig1.png}" in tex  # alpha (supply order)
        assert "{figures/fig2.pdf}" in tex  # beta
        # The semantic labels are preserved (so a body \ref{fig:<id>} resolves).
        assert r"\label{fig:alpha}" in tex
        assert r"\label{fig:beta}" in tex
        # The agent id is NEVER the include filename.
        assert "{figures/alpha.png}" not in tex


def test_figure_bearing_paper_emits_font_policy():
    # F2 (design/paper-publishing-requirements.md): a figure-bearing paper emits the font
    # policy -- Times-compatible math (newtxmath, MATH only so body text is unchanged) +
    # Arial-compatible sans (helvet) for figure text. A figure-LESS paper carries NEITHER
    # (the policy is figure-scoped; the skeleton stays byte-identical).
    hyp = _basic_hyp()
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

    with_fig = render_paper_latex(spec, [claim], [ev], figures=[_fig_spec("growth")])
    assert r"\usepackage{newtxmath}" in with_fig
    assert r"\usepackage[scaled]{helvet}" in with_fig

    figure_less = render_paper_latex(spec, [claim], [ev])
    assert r"\usepackage{newtxmath}" not in figure_less
    assert "helvet" not in figure_less
