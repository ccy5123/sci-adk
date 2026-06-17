"""
Render labeling (design/evidence-validity.md §4): the paper draft must be honestly
self-descriptive -- each claim shows its hypothesis ``referent`` and the
``data_source`` of its bearing Evidence, so a reader can tell an in-silico
computational result from a bare empirical "supported", and can tell an empirical
hypothesis still awaiting measured data.

This is reporting only -- it does NOT touch the adequacy gate. It fulfills the §4
promise that results are labelled by referent + data_source, never a bare "supported"
for a formal/generated result and never hiding that an empirical claim has no
measured data yet.
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
from sci_adk.render.paper import render_paper

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="point >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)


def _spec(hyp: Hypothesis, spec_id: str = "paper-label") -> Spec:
    return Spec(
        id=spec_id,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="method", expected_output="out"
        ),
        hypotheses=[hyp],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp.id)],
    )


def _claim(hyp: Hypothesis, status: ClaimStatus, ev_id: str = "ev-1") -> Claim:
    return Claim(
        id=f"claim-{hyp.id}",
        spec_id="paper-label",
        answers=hyp.id,
        statement=hyp.statement,
        status=status,
        confidence=Confidence(
            type=ConfidenceType.CREDENCE, value=0.9, basis="threshold rule: met"
        ),
        evidence_set=[EvidenceLink(evidence_id=ev_id, role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _evidence(ev_id: str, hyp_id: str, data_source, direction):
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id="paper-label",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source=data_source),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id=hyp_id, direction=direction)],
    )


# ---------------------------------------------------------------------------
# formal + generated + supported -> labelled as an in-silico/computational result.
# ---------------------------------------------------------------------------

def test_formal_generated_supported_is_labelled_computational():
    hyp = Hypothesis(
        id="hyp-f",
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent="formal",
        non_circularity="collisions could occur; the verifier checks for them",
    )
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-f", "generated", BearingDirection.SUPPORTS)

    draft = render_paper(spec, [claim], [ev])

    # The referent and data_source are shown factually ...
    assert "referent=formal" in draft
    assert "generated" in draft
    # ... and a formal/generated supported result is labelled in-silico/computational,
    # not a bare empirical "supported".
    assert "in-silico" in draft.lower() or "computational result" in draft.lower()


# ---------------------------------------------------------------------------
# empirical + proposed (no measured data) -> labelled as awaiting measured data.
# ---------------------------------------------------------------------------

def test_empirical_proposed_no_measured_is_labelled_awaiting_data():
    hyp = Hypothesis(
        id="hyp-e",
        statement="trait predicts organ dry weight",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=_THRESHOLD,
        referent="empirical",
    )
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.PROPOSED)
    # A neutral bearing with no measured data: legitimately awaiting measurement.
    ev = _evidence("ev-1", "hyp-e", None, BearingDirection.NEUTRAL)

    draft = render_paper(spec, [claim], [ev])

    assert "referent=empirical" in draft
    # Status is still shown ...
    assert "proposed" in draft.lower()
    # ... and the draft makes clear it is awaiting measured data.
    assert "awaiting measured data" in draft.lower()


# ---------------------------------------------------------------------------
# empirical + measured + supported -> a genuine empirical result (no false label).
# ---------------------------------------------------------------------------

def test_empirical_measured_supported_shows_measured_no_insilico_label():
    hyp = Hypothesis(
        id="hyp-m",
        statement="trait predicts organ dry weight",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=_THRESHOLD,
        referent="empirical",
    )
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-m", "measured", BearingDirection.SUPPORTS)

    draft = render_paper(spec, [claim], [ev])

    assert "referent=empirical" in draft
    assert "measured" in draft
    # A real empirical (measured) result must NOT be mislabelled as in-silico.
    assert "in-silico" not in draft.lower()
    # And it is not "awaiting measured data" -- it has measured data.
    assert "awaiting measured data" not in draft.lower()


def test_label_line_is_concise_one_per_claim():
    """The label is a short single line per claim (not a verbose block)."""
    hyp = Hypothesis(
        id="hyp-f",
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent="formal",
        non_circularity="collisions could occur; the verifier checks for them",
    )
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-f", "generated", BearingDirection.SUPPORTS)

    draft = render_paper(spec, [claim], [ev])
    # Exactly one evidence-validity label line for the single hypothesis.
    label_lines = [ln for ln in draft.splitlines() if "referent=" in ln]
    assert len(label_lines) == 1
