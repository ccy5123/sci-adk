"""
Regression tests for the render-layer reframe ("move the line",
design/render-architecture-reframe.md): the deterministic record-fidelity spine + the
agent-narrative paper + the \\evval/\\status fidelity gate.

These lock the NEW behaviors the reframe introduced (paper IMRaD + record-derived facts
via macros; SI = the de-duplicated, captioned, natbib-cited record dump), complementing
the contract updates in test_paper_latex / test_si / test_render_merge_wiring.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from sci_adk.render.paper import check_paper_tool_vocabulary, render_paper_latex
from sci_adk.render.prose import PaperProse
from sci_adk.render.si import render_si_latex

_T0 = datetime(2026, 6, 22, 9, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="collision_count == 0 => support",
    params={"statistic": "collision_count", "op": "==", "value": 0.0},
)


def _hyp(hyp_id: str = "hyp-001") -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent="formal",
        non_circularity="collisions could occur; the verifier checks",
    )


def _spec(hyp: Hypothesis, spec_id: str = "t1-godel") -> Spec:
    return Spec(
        id=spec_id,
        created_at=_T0,
        version=4,
        raw_proposal=RawProposal(
            background="bg", goal="H1 injective ... long wall ...",
            method="method", expected_output="out",
        ),
        hypotheses=[hyp],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp.id)],
    )


def _threshold_claim(hyp: Hypothesis, value: float = 0.0) -> Claim:
    """A claim as the threshold engine produces it: credence with the value=0 default."""
    return Claim(
        id=f"claim-{hyp.id}",
        spec_id="t1-godel",
        answers=hyp.id,
        statement=hyp.statement,
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(
            type=ConfidenceType.CREDENCE, value=value,
            basis="threshold rule: statistic 'point'=0 == 0 is met",
        ),
        evidence_set=[EvidenceLink(evidence_id="ev-c", role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _lit(ev_id: str) -> EvidenceItem:
    """A literature item with a fixed finding (so repeats are byte-identical)."""
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id="t1-godel",
        kind=EvidenceKind.LITERATURE,
        provenance=Provenance(code_ref="x"),
        result=Result(
            type="qualitative",
            finding='{"acquired": [{"doi": "10.1186/s13321-015-0068-4", '
                    '"source": "openalex", "license": "cc-by", "filename": "Heller2015.pdf"}]}',
        ),
        bears_on=[Bearing(target_id="hyp-001", direction=BearingDirection.NEUTRAL)],
    )


def _experiment(ev_id: str, point: float, finding: str) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id="t1-godel",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(type="quantitative", point=point, finding=finding),
        bears_on=[Bearing(target_id="hyp-001", direction=BearingDirection.SUPPORTS)],
    )


# -- 2.1 confidence-0 suppression (SI) ----------------------------------------

def test_si_suppresses_uninformative_credence_zero():
    hyp = _hyp()
    spec = _spec(hyp)
    claim = _threshold_claim(hyp, value=0.0)
    ev = _experiment("ev-c", 0.0, '{"collision_count": 0}')

    si = render_si_latex(spec, [claim], [ev])

    assert "Status: supported" in si
    # The uninformative "confidence 0 (credence)" never appears next to SUPPORTED ...
    assert "confidence 0 (credence)" not in si
    assert "confidence 0" not in si
    # ... but the basis (the real judgment, C3) is still present.
    assert "threshold rule" in si


def test_si_shows_meaningful_confidence():
    hyp = _hyp()
    spec = _spec(hyp)
    claim = _threshold_claim(hyp, value=0.92)  # a meaningful credence is shown
    ev = _experiment("ev-c", 0.0, '{"collision_count": 0}')

    si = render_si_latex(spec, [claim], [ev])
    assert "confidence 0.92" in si


# -- 3.3 dedup (SI) -----------------------------------------------------------

def test_si_collapses_repeated_literature_with_count():
    hyp = _hyp()
    spec = _spec(hyp)
    # Six byte-identical literature acquisitions of the same DOI.
    lits = [_lit(f"evi-lit-{i}") for i in range(6)]

    si = render_si_latex(spec, [], lits)

    # Only the FIRST id is rendered, with a (recorded 6x) count -- not six lines.
    assert "evi-lit-0" in si
    assert "(recorded 6x)" in si
    assert "evi-lit-5" not in si
    assert si.count("Heller2015.pdf") == 1


def test_si_does_not_collapse_distinct_findings():
    hyp = _hyp()
    spec = _spec(hyp)
    # Two experiment runs with DISTINCT findings (the demo + the designed run): kept apart.
    a = _experiment("evi-demo", 0.0, '{"collision_count": 0, "n_molecules": 6}')
    b = _experiment("evi-designed", 0.0, '{"collision_count": 0, "n_molecules": 13}')

    si = render_si_latex(spec, [], [a, b])
    assert "evi-demo" in si
    assert "evi-designed" in si
    assert "(recorded" not in si  # nothing collapsed


# -- 3.1 structured finding (no raw JSON dump / no mid-token truncation) -------

def test_si_finding_is_structured_not_truncated_json():
    hyp = _hyp()
    spec = _spec(hyp)
    lit = _lit("evi-lit-0")
    si = render_si_latex(spec, [], [lit])
    # The structured summary surfaces the fields cleanly; the closing brace/quote of the
    # DOI/filename is never cut mid-token (the old 120-char cap bug).
    assert "Heller2015.pdf" in si
    assert "openalex" in si
    assert "cc-by" in si


# -- 7.1 SI quantitative table: float + caption + label + S-numbering ---------

def test_si_quantitative_table_is_captioned_labelled_and_referenced():
    hyp = _hyp()
    spec = _spec(hyp)
    ev = _experiment("evi-c", 0.0, '{"collision_count": 0}')

    si = render_si_latex(spec, [], [ev])

    assert r"\begin{table}" in si
    assert r"\caption{" in si
    assert r"\label{tab:s1}" in si
    assert r"\ref{tab:s1}" in si  # referenced within the SI (resolves; verify gate ok)
    # S-prefixed numbering so a main-paper "Table S1" matches.
    assert r"\renewcommand{\thetable}{S\arabic{table}}" in si


# -- 6.2 SI bibliography (natbib) ---------------------------------------------

def test_si_wires_natbib_bibliography_when_bib_present():
    hyp = _hyp()
    spec = _spec(hyp)
    ev = _experiment("evi-c", 0.0, '{"collision_count": 0}')

    si = render_si_latex(spec, [], [ev], bib_path="/x/references.bib")
    assert r"\usepackage{natbib}" in si
    assert r"\bibliographystyle{plainnat}" in si
    assert r"\bibliography{references}" in si


def test_si_no_bibliography_when_bib_absent():
    hyp = _hyp()
    spec = _spec(hyp)
    ev = _experiment("evi-c", 0.0, '{"collision_count": 0}')
    si = render_si_latex(spec, [], [ev])
    assert r"\usepackage{natbib}" in si  # natbib always loaded (prose may cite)
    assert r"\bibliography{" not in si


# -- \evval substitutes a finding-JSON fact into the PAPER prose --------------

def test_paper_evval_substitutes_finding_json_field():
    hyp = _hyp()
    spec = _spec(hyp)
    claim = _threshold_claim(hyp)
    ev = _experiment(
        "evi-designed", 0.0,
        '{"collision_count": 0, "n_distinct_noniso_pairs": 73, "n_molecules": 13}',
    )
    prose = PaperProse(
        results=r"Zero collisions over \evval{evi-designed}{n_distinct_noniso_pairs} "
                r"pairs (\evval{evi-designed}{n_molecules} molecules); H1 \status{hyp-001}."
    )
    tex = render_paper_latex(spec, [claim], [ev], prose=prose)
    assert "Zero collisions over 73 pairs (13 molecules); H1 supported." in tex
    assert r"\evval{" not in tex
    assert r"\status{" not in tex


# -- 1.1 title: agent title, else spec.id (never the goal wall) ---------------

def test_paper_title_is_agent_title_then_spec_id():
    hyp = _hyp()
    spec = _spec(hyp)
    claim = _threshold_claim(hyp)
    ev = _experiment("ev-c", 0.0, '{"collision_count": 0}')

    # Agent title used verbatim.
    tex = render_paper_latex(
        spec, [claim], [ev], prose=PaperProse(title="A Godel-style Molecular Index")
    )
    assert r"\title{A Godel-style Molecular Index}" in tex
    assert "long wall" not in tex  # the goal wall never reaches the title

    # No title -> spec.id fallback (still never the goal wall).
    tex2 = render_paper_latex(spec, [claim], [ev])
    assert r"\title{t1-godel}" in tex2
    assert "long wall" not in tex2


# -- §10 tool-vocabulary leakage (paper narrative; SI exempt) ------------------

def test_paper_author_and_note_are_tool_agnostic():
    hyp = _hyp()
    spec = _spec(hyp)
    claim = _threshold_claim(hyp)
    ev = _experiment("ev-c", 0.0, '{"collision_count": 0}')

    # No author supplied -> empty \author{}; the paper never names the toolchain and
    # carries no "compiled by sci-adk ... Belief state ... Evidence" provenance note.
    tex = render_paper_latex(spec, [claim], [ev])
    assert r"\author{}" in tex
    assert "sci-adk" not in tex
    assert "Belief state is revisable" not in tex
    assert "compiled by sci-adk" not in tex.lower()

    # An author supplied -> used verbatim.
    tex2 = render_paper_latex(
        spec, [claim], [ev], prose=PaperProse(author="A. Researcher")
    )
    assert r"\author{A. Researcher}" in tex2


def test_check_paper_tool_vocabulary_flags_leaks():
    leaky = (
        r"We pre-registered in the frozen Spec; the engine-derived verdicts "
        r"reproduce under the sci-adk verify audit (append-only Evidence record, "
        r"result.point)."
    )
    found = check_paper_tool_vocabulary(leaky)
    for term in ("sci-adk", "frozen spec", "engine-derived", "verify audit",
                 "append-only", "evidence record", "result.point", "verdicts", "Spec"):
        assert term in found


def test_check_paper_tool_vocabulary_clean_science_passes():
    clean = (
        r"We specified the two acceptance thresholds in advance, before computing any "
        r"statistic. The measured collision count is 0, so injectivity holds. Code and "
        r"data are available so the analysis can be independently re-run. "
        r"Specifically, the specification of each test molecule is given."
    )
    # No false positive on legitimate science ("Specifically"/"specification" are not the
    # proper noun "Spec"; lowercase "spec" is fine).
    assert check_paper_tool_vocabulary(clean) == []


def test_rendered_paper_with_clean_prose_is_tool_agnostic():
    hyp = _hyp()
    spec = _spec(hyp)
    claim = _threshold_claim(hyp)
    ev = _experiment(
        "evi-c", 0.0, '{"collision_count": 0, "n_molecules": 13}'
    )
    prose = PaperProse(
        title="A Godel-style Molecular Index",
        abstract="We demonstrate an injective, recoverable integer index for molecules.",
        results=r"The measured collision count is \evval{evi-c}{point} over "
                r"\evval{evi-c}{n_molecules} molecules, so injectivity holds (H1 "
                r"\status{hyp-001}). Code and data are available for independent re-run.",
    )
    tex = render_paper_latex(spec, [claim], [ev], prose=prose)
    assert check_paper_tool_vocabulary(tex) == []
