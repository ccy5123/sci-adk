"""
Novelty gate composed at the Evidence->Claim chokepoint (RED-first).

design/literature-acquisition.md §"Discovery trigger model": the novelty gate runs in
``ClaimUpdater.update_claims_from_evidence`` alongside the existing
``check_digitized_adequacy`` / ``check_evidence_adequacy`` calls. A halt propagates out
(no Claim written), exactly like the other gates.

End-to-end matrix:
  - novelty + SUPPORTS + no novelty decision      -> ValidityHalt, NO Claim
  - novelty + SUPPORTS + a SKIPPED novelty decision -> ValidityHalt, NO Claim
  - novelty + SUPPORTS + a SEARCHED novelty decision -> Claim persists SUPPORTED
  - novelty + REFUTES + no decision               -> passes (SUPPORTS-only), REFUTED Claim
  - novelty=False + SUPPORTS + no decision        -> passes (gate inert), SUPPORTED Claim

Also: a NOVELTY_DECISION item (bears_on=[]) does NOT change any DecisionEngine verdict
(it is a record, not a belief -- it never enters EvidenceForHypothesis).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sci_adk.core.claim import ClaimStatus
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
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
from sci_adk.core.validity import ValidityHalt
from sci_adk.loop.claim_updater import ClaimUpdater


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _spec(novelty: bool, spec_id: str, hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                # A formal referent with a non-circularity attestation keeps the
                # evidence-validity gate from firing on 'generated' data, so we isolate
                # the NOVELTY gate under test.
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
                referent="formal",
                non_circularity="the verifier checks a property not baked into the generator",
                novelty=novelty,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _supporting_evidence(hyp_id: str = "hyp-1", point: float = 0.95) -> EvidenceItem:
    return EvidenceItem(
        id="ev-num",
        spec_id="s",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
    )


def _refuting_evidence(hyp_id: str = "hyp-1", point: float = 0.10) -> EvidenceItem:
    return EvidenceItem(
        id="ev-num",
        spec_id="s",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.REFUTES)],
    )


def _novelty_decision(hyp_id: str, outcome: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"evi-nov-{outcome}",
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref=f"novelty:{outcome}"),
        result=Result(type="qualitative", finding=f"{outcome}: ..."),
        bears_on=[],
        literature_decision=LiteratureDecision(outcome=outcome, hypothesis_id=hyp_id),
    )


# --------------------------------------------------------------------------- #
# the gate halts (no Claim written)
# --------------------------------------------------------------------------- #

def test_novelty_supports_no_decision_halts_no_claim(tmp_path):
    spec = _spec(True, "nov-halt-1")
    updater = ClaimUpdater(spec, tmp_path)
    with pytest.raises(ValidityHalt):
        updater.update_claims_from_evidence([_supporting_evidence()])
    # NO Claim was written.
    assert not (tmp_path / "runs" / spec.id / "claims" / "claim-hyp-1.json").exists()


def test_novelty_supports_skip_decision_halts_no_claim(tmp_path):
    spec = _spec(True, "nov-halt-2")
    updater = ClaimUpdater(spec, tmp_path)
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "skipped")]
    with pytest.raises(ValidityHalt):
        updater.update_claims_from_evidence(evidence)
    assert not (tmp_path / "runs" / spec.id / "claims" / "claim-hyp-1.json").exists()


# --------------------------------------------------------------------------- #
# the gate passes (Claim persists)
# --------------------------------------------------------------------------- #

def test_novelty_supports_searched_decision_persists_supported(tmp_path):
    spec = _spec(True, "nov-ok")
    updater = ClaimUpdater(spec, tmp_path)
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "searched")]
    claims = updater.update_claims_from_evidence(evidence)
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.SUPPORTED
    assert (tmp_path / "runs" / spec.id / "claims" / "claim-hyp-1.json").exists()


def test_novelty_refutes_no_decision_passes_refuted(tmp_path):
    """SUPPORTS-only: a REFUTED novelty hypothesis is unaffected by the gate."""
    spec = _spec(True, "nov-refute")
    updater = ClaimUpdater(spec, tmp_path)
    claims = updater.update_claims_from_evidence([_refuting_evidence()])
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.REFUTED


def test_non_novelty_supports_no_decision_passes_supported(tmp_path):
    """novelty=False -> the gate is inert; a normal SUPPORTED claim persists."""
    spec = _spec(False, "nov-off")
    updater = ClaimUpdater(spec, tmp_path)
    claims = updater.update_claims_from_evidence([_supporting_evidence()])
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.SUPPORTED


# --------------------------------------------------------------------------- #
# decisions never enter the verdict
# --------------------------------------------------------------------------- #

def test_novelty_decision_does_not_change_the_verdict(tmp_path):
    """A NOVELTY_DECISION (bears_on=[]) must not alter the DecisionEngine verdict: the
    SUPPORTED claim is identical whether or not a searched decision is present (the
    decision only un-blocks the gate; it contributes nothing to belief)."""
    spec = _spec(True, "nov-no-verdict-change")
    updater = ClaimUpdater(spec, tmp_path)
    claims = updater.update_claims_from_evidence(
        [_supporting_evidence(point=0.95), _novelty_decision("hyp-1", "searched")]
    )
    assert claims[0].status == ClaimStatus.SUPPORTED
    # The supporting evidence is the only counted bearing; the decision contributed no
    # bearing (it is a record, not a belief).
    supporting = claims[0].get_supporting_evidence()
    assert {link.evidence_id for link in supporting} == {"ev-num"}
