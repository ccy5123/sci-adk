"""
Supporting Information Phase 2 (RED-first): a deterministic STANDALONE ``si.tex``
renderer that dumps the full sci-adk RECORD (design/paper-figures-and-si.md, D3).

record / belief <-> SI / paper: the SI is the RECORD -- a no-authoring deterministic
dump of everything sci-adk stores (every Evidence item, the numeric data tables, ALL
figures, every Claim's verdict + the frozen decision rule it was judged against, and a
record-integrity line). The main paper (draft.tex) is the belief narrative. The SI is
the most natural deterministic render of the record, so it needs no LLM at render time.

These pin the behavior before any implementation exists. The renderer is PURE (data
in, string out), deterministic (re-render byte-identical), and emits a STANDALONE
LaTeX document (``\\documentclass{article}`` ... ``\\end{document}``) so ``si.tex``
compiles on its own as a folder-upload sibling of ``draft.tex`` -- with NO
``\\includegraphics`` / ``\\input`` / external file ref (it uploads alone).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceLevel,
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
from sci_adk.render.si import render_si_latex

_T0 = datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)

_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="collision_count == 0 => support",
    params={"statistic": "collision_count", "op": "==", "value": 0.0},
)


# ---------------------------------------------------------------------------
# Fixtures: a Spec (>=1 hypothesis + decision_rule), 2-3 EvidenceItems with
# numeric results (+ one qualitative-only), 1-2 Claims with status + basis.
# ---------------------------------------------------------------------------

def _hyp(hyp_id: str = "hyp-t1", referent: str = "formal") -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent=referent,
        non_circularity="collisions could occur; the verifier checks for them",
    )


def _spec(*hyps: Hypothesis, spec_id: str = "t-si", goal: str = "An encoding") -> Spec:
    hlist = list(hyps) or [_hyp()]
    return Spec(
        id=spec_id,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal=goal, method="method", expected_output="out"
        ),
        hypotheses=hlist,
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hlist[0].id)],
    )


def _quant_ev(
    ev_id: str,
    hyp_id: str = "hyp-t1",
    *,
    point=0.0,
    effect_size=None,
    p_value=None,
    spec_id: str = "t-si",
    data_source="generated",
    direction=BearingDirection.SUPPORTS,
) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id=spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="commit:abc", data_source=data_source),
        result=Result(
            type="quantitative",
            point=point,
            effect_size=effect_size,
            p_value=p_value,
        ),
        bears_on=[Bearing(target_id=hyp_id, direction=direction)],
    )


def _qual_ev(
    ev_id: str,
    hyp_id: str = "hyp-t1",
    *,
    finding: str = "a qualitative observation",
    spec_id: str = "t-si",
) -> EvidenceItem:
    """A qualitative-only item: no numeric point -- must still appear in the Evidence
    record dump (no invented numbers)."""
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id=spec_id,
        kind=EvidenceKind.OBSERVATION,
        provenance=Provenance(code_ref="note"),
        result=Result(type="qualitative", finding=finding),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.NEUTRAL)],
    )


def _claim(
    hyp: Hypothesis,
    status: ClaimStatus = ClaimStatus.SUPPORTED,
    *,
    ev_id: str = "ev-1",
    basis: str = "threshold rule met: zero collisions over the tested set",
    spec_id: str = "t-si",
) -> Claim:
    return Claim(
        id=f"claim-{hyp.id}",
        spec_id=spec_id,
        answers=hyp.id,
        statement=hyp.statement,
        status=status,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis=basis),
        evidence_set=[EvidenceLink(evidence_id=ev_id, role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _figure(fig_id: str = "growth", ev_id: str = "ev-1") -> FigureSpec:
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
                    points=[PlotPoint(evidence_id=ev_id, x=1.0)],
                )
            ],
        ),
    )


def _basic_record():
    """A small but complete record: 1 hyp, 2 quant + 1 qual evidence, 1 claim."""
    hyp = _hyp()
    spec = _spec(hyp)
    evidence = [
        _quant_ev("ev-1", point=0.0, effect_size=1.5),
        _quant_ev("ev-2", point=9.0, p_value=0.01),
        _qual_ev("ev-3"),
    ]
    claims = [_claim(hyp, ClaimStatus.SUPPORTED, ev_id="ev-1")]
    return spec, claims, evidence


# ---------------------------------------------------------------------------
# Standalone document structure.
# ---------------------------------------------------------------------------

class TestStandaloneDocument:
    def test_is_a_standalone_latex_document(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        assert r"\documentclass{article}" in si
        assert r"\begin{document}" in si
        assert r"\end{document}" in si
        # The preamble must be present so it compiles alone.
        assert r"\usepackage[utf8]{inputenc}" in si

    def test_title_is_supporting_information_plus_spec_title(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        assert "Supporting Information" in si

    def test_self_contained_no_external_file_ref(self):
        """``si.tex`` uploads alone: no \\includegraphics / \\input / external file
        ref (native figures are text)."""
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence, figures=[_figure("growth", "ev-1")])
        assert r"\includegraphics" not in si
        assert r"\input{" not in si
        assert r"\include{" not in si


# ---------------------------------------------------------------------------
# Evidence record: every item appears (the complete append-only record).
# ---------------------------------------------------------------------------

class TestEvidenceRecord:
    def test_every_evidence_id_appears(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        for ev in evidence:
            assert ev.id in si, f"evidence id {ev.id} missing from the SI record"

    def test_qualitative_only_item_appears_without_inventing_numbers(self):
        """A qualitative-only item (no point) still appears in the Evidence record --
        with its finding text, never a fabricated number."""
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        # The qualitative item's id and its finding are present.
        assert "ev-3" in si
        assert "a qualitative observation" in si

    def test_evidence_kind_and_provenance_surface(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        # The kind of an item and its data_source (capability/provenance) show up.
        # The underscore is LaTeX-escaped (faithful record), so match the escaped form.
        assert r"experiment\_run" in si
        assert "generated" in si


# ---------------------------------------------------------------------------
# Quantitative data table: reflects the actual Result values (record fidelity).
# ---------------------------------------------------------------------------

class TestQuantitativeTable:
    def test_has_a_tabular_with_numeric_values(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        assert r"\begin{tabular}" in si
        assert r"\end{tabular}" in si

    def test_table_reflects_actual_result_values(self):
        """Change a Result value -> the rendered SI changes (record fidelity)."""
        hyp = _hyp()
        spec = _spec(hyp)
        claims = [_claim(hyp)]
        ev_low = [_quant_ev("ev-1", point=9.0)]
        ev_high = [_quant_ev("ev-1", point=42.0)]

        si_low = render_si_latex(spec, claims, ev_low)
        si_high = render_si_latex(spec, claims, ev_high)

        assert "9" in si_low
        assert "42" in si_high
        assert si_low != si_high

    def test_empty_numeric_columns_skipped_deterministically(self):
        """A column with no values across any item is skipped (deterministic)."""
        hyp = _hyp()
        spec = _spec(hyp)
        claims = [_claim(hyp)]
        # Only `point` carries values; posterior/residual/predictive_error are all None.
        evidence = [_quant_ev("ev-1", point=1.0), _quant_ev("ev-2", point=2.0)]
        si = render_si_latex(spec, claims, evidence)
        # `point` is present as a column header; an all-empty column header is not.
        assert "point" in si
        assert "predictive_error" not in si

    def test_ci_field_rendered_as_list_in_table(self):
        """The ``ci`` field is the only NON-scalar numeric field and appears in practice
        (a credible/confidence interval). It must render in the quantitative table as the
        exact ``_fmt_cell`` list format ``[lo, hi]`` -- this closes the real coverage gap
        (every other numeric field is a plain scalar)."""
        hyp = _hyp()
        spec = _spec(hyp)
        claims = [_claim(hyp)]
        evidence = [
            EvidenceItem(
                id="ev-ci",
                created_at=_T0,
                spec_id="t-si",
                kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="c", data_source="generated"),
                result=Result(type="quantitative", point=1.0, ci=[0.1, 0.9]),
                bears_on=[
                    Bearing(target_id="hyp-t1", direction=BearingDirection.SUPPORTS)
                ],
            )
        ]
        si = render_si_latex(spec, claims, evidence)
        # The `ci` column header is present and the interval renders as [lo, hi].
        assert "ci" in si
        assert "[0.1, 0.9]" in si

    def test_nan_inf_result_renders_as_literal_text_without_raising(self):
        """A NaN/inf Result value renders in the SI table as the literal compile-safe
        text ``nan``/``inf`` WITHOUT raising -- the value IS in the record, and a LaTeX
        ``tabular`` cell is plain text (compile-safe). This pins the DELIBERATE ASYMMETRY
        vs ``render_native_figure``, which raises ValueError on NaN/inf because pgfplots
        coordinates cannot be non-finite."""
        hyp = _hyp()
        spec = _spec(hyp)
        claims = [_claim(hyp)]
        ev_nan = [_quant_ev("ev-nan", point=float("nan"))]
        ev_inf = [_quant_ev("ev-inf", point=float("inf"))]

        # Neither render raises ...
        si_nan = render_si_latex(spec, claims, ev_nan)
        si_inf = render_si_latex(spec, claims, ev_inf)

        # ... and the non-finite value is present as literal text in the table.
        assert "nan" in si_nan
        assert "inf" in si_inf


# ---------------------------------------------------------------------------
# Claims and verdicts: status, confidence + basis, links, decision rule.
# ---------------------------------------------------------------------------

class TestClaimsAndVerdicts:
    def test_status_and_basis_present_for_each_claim(self):
        hyp = _hyp()
        spec = _spec(hyp)
        evidence = [_quant_ev("ev-1", point=0.0)]
        claim = _claim(hyp, ClaimStatus.SUPPORTED, basis="the load-bearing basis text")
        si = render_si_latex(spec, [claim], evidence)
        assert "supported" in si
        # C3: the basis is always present.
        assert "the load-bearing basis text" in si

    def test_decision_rule_present(self):
        """The frozen decision rule a hypothesis was judged against appears.

        The underscore is LaTeX-escaped (faithful record), so match the escaped form.
        """
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        assert r"collision\_count == 0 => support" in si

    def test_supporting_and_refuting_links_surface(self):
        hyp = _hyp()
        spec = _spec(hyp)
        evidence = [
            _quant_ev("ev-sup", point=0.0, direction=BearingDirection.SUPPORTS),
            _quant_ev("ev-ref", point=1.0, direction=BearingDirection.REFUTES),
        ]
        claim = Claim(
            id=f"claim-{hyp.id}",
            spec_id="t-si",
            answers=hyp.id,
            statement=hyp.statement,
            status=ClaimStatus.CONTESTED,
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.MODERATE,
                basis="mixed evidence",
            ),
            evidence_set=[
                EvidenceLink(evidence_id="ev-sup", role=EvidenceLinkRole.SUPPORTING),
                EvidenceLink(evidence_id="ev-ref", role=EvidenceLinkRole.REFUTING),
            ],
            mode=hyp.mode,
        )
        si = render_si_latex(spec, [claim], evidence)
        # Both the supporting and refuting evidence ids appear in the verdict block.
        assert "ev-sup" in si
        assert "ev-ref" in si


# ---------------------------------------------------------------------------
# Figures: ALL figures rendered; pgfplots preamble present when figures present.
# ---------------------------------------------------------------------------

class TestFigures:
    def test_all_figures_rendered_with_pgfplots(self):
        spec, claims, evidence = _basic_record()
        figs = [_figure("growth", "ev-1"), _figure("decay", "ev-2")]
        si = render_si_latex(spec, claims, evidence, figures=figs)
        assert r"\usepackage{pgfplots}" in si
        assert r"\pgfplotsset{compat=1.18}" in si
        assert r"\begin{figure}" in si
        assert r"\label{fig:growth}" in si
        assert r"\label{fig:decay}" in si

    def test_no_pgfplots_when_no_figures(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence)
        assert r"\usepackage{pgfplots}" not in si
        assert r"\begin{figure}" not in si

    def test_figure_y_pulled_from_record(self):
        hyp = _hyp()
        spec = _spec(hyp)
        claims = [_claim(hyp)]
        evidence = [_quant_ev("ev-1", point=7.0)]
        si = render_si_latex(spec, claims, evidence, figures=[_figure("growth", "ev-1")])
        # x=1 from the spec, y=7 pulled from the Evidence record.
        assert "(1, 7)" in si


# ---------------------------------------------------------------------------
# Record integrity: digest embedded when given; verify-note when None.
# ---------------------------------------------------------------------------

class TestRecordIntegrity:
    def test_digest_embedded_when_provided(self):
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence, digest="abc123")
        assert "abc123" in si
        assert "sha256" in si

    def test_verify_note_when_digest_none(self):
        """digest=None -> no fake digest; the integrity section points to
        ``sci-adk verify`` (which computes the digest over the persisted run)."""
        spec, claims, evidence = _basic_record()
        si = render_si_latex(spec, claims, evidence, digest=None)
        assert "sci-adk verify" in si
        # No fabricated digest line.
        assert "Record digest (sha256):" not in si


# ---------------------------------------------------------------------------
# Determinism: same inputs -> byte-identical output.
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_two_renders_byte_identical(self):
        spec, claims, evidence = _basic_record()
        figs = [_figure("growth", "ev-1")]
        a = render_si_latex(spec, claims, evidence, figures=figs, digest="abc123")
        b = render_si_latex(spec, claims, evidence, figures=figs, digest="abc123")
        assert a == b

    def test_deterministic_with_no_figures_no_digest(self):
        spec, claims, evidence = _basic_record()
        a = render_si_latex(spec, claims, evidence)
        b = render_si_latex(spec, claims, evidence)
        assert a == b
