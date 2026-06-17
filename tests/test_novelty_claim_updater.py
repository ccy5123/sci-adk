"""
Two-claim model at the Evidence->Claim chokepoint (RED-first, B-replace).

design/literature-acquisition.md §"Discovery trigger model": novelty is decoupled from
the experiment claim. ``ClaimUpdater.update_claims_from_evidence`` now:

  - derives the EXPERIMENT claim ``claim-<hyp.id>`` from EXPERIMENT evidence ONLY (the
    novelty HALT is gone -- the experiment claim never stops on novelty), AND
  - for every ``novelty=True`` hypothesis, load-or-creates and persists a SEPARATE
    novelty claim ``claim-novelty-<hyp.id>`` whose status is
    ``derive_novelty_status(hyp, novelty_decisions)`` (SUPPORTED iff a recorded
    found_nothing; else PROPOSED).

Both claims are RETURNED and PERSISTED. The novelty claim is a full revisable Claim
(append-only history, non-monotone): re-compiling after a found_nothing decision is
later added moves it PROPOSED -> SUPPORTED.

Safety floor: a found_something decision NEVER produces SUPPORTED (it stays PROPOSED) --
the false-novelty-claim structural block.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.core.claim import Claim, ClaimStatus
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


def _novelty_decision(hyp_id: str, outcome: str, item_id: str | None = None) -> EvidenceItem:
    return EvidenceItem(
        id=item_id or f"evi-nov-{outcome}",
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref=f"novelty:{outcome}"),
        result=Result(type="qualitative", finding=f"{outcome}: ..."),
        bears_on=[],
        literature_decision=LiteratureDecision(outcome=outcome, hypothesis_id=hyp_id),
    )


def _novelty_claim_path(tmp_path: Path, spec_id: str, hyp_id: str = "hyp-1") -> Path:
    return tmp_path / "runs" / spec_id / "claims" / f"claim-novelty-{hyp_id}.json"


def _experiment_claim_path(tmp_path: Path, spec_id: str, hyp_id: str = "hyp-1") -> Path:
    return tmp_path / "runs" / spec_id / "claims" / f"claim-{hyp_id}.json"


# --------------------------------------------------------------------------- #
# the experiment claim no longer halts on novelty
# --------------------------------------------------------------------------- #

def test_novelty_supports_no_decision_does_not_halt_experiment_claim(tmp_path):
    """No novelty decision: the experiment claim still derives (SUPPORTED) -- no HALT."""
    spec = _spec(True, "nov-noh-1")
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(
        [_supporting_evidence()]
    )
    by_id = {c.id: c for c in claims}
    assert by_id["claim-hyp-1"].status == ClaimStatus.SUPPORTED
    assert _experiment_claim_path(tmp_path, spec.id).exists()


def test_novelty_skip_does_not_halt_experiment_claim(tmp_path):
    spec = _spec(True, "nov-noh-2")
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "skipped")]
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(evidence)
    by_id = {c.id: c for c in claims}
    assert by_id["claim-hyp-1"].status == ClaimStatus.SUPPORTED


# --------------------------------------------------------------------------- #
# the novelty claim is emitted with the rule-derived status
# --------------------------------------------------------------------------- #

def test_novelty_claim_supported_on_found_nothing(tmp_path):
    spec = _spec(True, "nov-found-nothing")
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "found_nothing")]
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(evidence)
    by_id = {c.id: c for c in claims}
    # BOTH claims returned.
    assert "claim-hyp-1" in by_id
    assert "claim-novelty-hyp-1" in by_id
    nov = by_id["claim-novelty-hyp-1"]
    assert nov.status == ClaimStatus.SUPPORTED
    assert nov.answers == "hyp-1"
    # persisted on disk
    assert _novelty_claim_path(tmp_path, spec.id).exists()


def test_novelty_claim_proposed_when_no_decision(tmp_path):
    spec = _spec(True, "nov-none")
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(
        [_supporting_evidence()]
    )
    by_id = {c.id: c for c in claims}
    assert by_id["claim-novelty-hyp-1"].status == ClaimStatus.PROPOSED


def test_novelty_claim_proposed_on_skip(tmp_path):
    spec = _spec(True, "nov-skip")
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "skipped")]
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(evidence)
    by_id = {c.id: c for c in claims}
    assert by_id["claim-novelty-hyp-1"].status == ClaimStatus.PROPOSED


def test_novelty_claim_never_supported_on_found_something(tmp_path):
    """SAFETY FLOOR / false-novelty-claim block: found_something -> PROPOSED, never
    SUPPORTED."""
    spec = _spec(True, "nov-found-something")
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "found_something")]
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(evidence)
    by_id = {c.id: c for c in claims}
    assert by_id["claim-novelty-hyp-1"].status == ClaimStatus.PROPOSED


# --------------------------------------------------------------------------- #
# non-novelty hypotheses get NO novelty claim
# --------------------------------------------------------------------------- #

def test_non_novelty_hypothesis_gets_no_novelty_claim(tmp_path):
    spec = _spec(False, "nov-off")
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(
        [_supporting_evidence(), _novelty_decision("hyp-1", "found_nothing")]
    )
    by_id = {c.id: c for c in claims}
    assert "claim-hyp-1" in by_id
    assert "claim-novelty-hyp-1" not in by_id
    assert not _novelty_claim_path(tmp_path, spec.id).exists()


# --------------------------------------------------------------------------- #
# the novelty claim exists even when the experiment claim does NOT
# (the novelty pass is NOT gated by the experiment-evidence continue)
# --------------------------------------------------------------------------- #

def test_novelty_claim_emitted_without_any_experiment_evidence(tmp_path):
    """A novelty=True hypothesis with NO experiment evidence (so no experiment claim)
    still gets its novelty claim derived from the recorded decision."""
    spec = _spec(True, "nov-no-exp")
    evidence = [_novelty_decision("hyp-1", "found_nothing")]
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(evidence)
    by_id = {c.id: c for c in claims}
    # No experiment claim (no counted experiment evidence) ...
    assert "claim-hyp-1" not in by_id
    assert not _experiment_claim_path(tmp_path, spec.id).exists()
    # ... but the novelty claim is present and SUPPORTED.
    assert by_id["claim-novelty-hyp-1"].status == ClaimStatus.SUPPORTED


# --------------------------------------------------------------------------- #
# idempotent + non-monotone (PROPOSED -> SUPPORTED on a later found_nothing)
# --------------------------------------------------------------------------- #

def test_novelty_claim_idempotent_recompile(tmp_path):
    """Re-compiling with the same record yields the same novelty-claim status and does
    not pile up spurious history entries."""
    spec = _spec(True, "nov-idem")
    evidence = [_supporting_evidence(), _novelty_decision("hyp-1", "found_nothing")]
    updater = ClaimUpdater(spec, tmp_path)

    updater.update_claims_from_evidence(evidence)
    first = Claim.model_validate(
        json.loads(_novelty_claim_path(tmp_path, spec.id).read_text(encoding="utf-8"))
    )
    updater.update_claims_from_evidence(evidence)
    second = Claim.model_validate(
        json.loads(_novelty_claim_path(tmp_path, spec.id).read_text(encoding="utf-8"))
    )
    assert first.status == ClaimStatus.SUPPORTED
    assert second.status == ClaimStatus.SUPPORTED
    # No new StatusChange on a stable re-compile.
    assert len(second.history) == len(first.history)


def test_novelty_claim_non_monotone_proposed_then_supported(tmp_path):
    """PROPOSED -> SUPPORTED when a found_nothing decision is added on a later compile.
    The move is recorded in the append-only history (C1/C2)."""
    spec = _spec(True, "nov-nonmono")
    updater = ClaimUpdater(spec, tmp_path)

    # First compile: no decision -> PROPOSED.
    updater.update_claims_from_evidence([_supporting_evidence()])
    proposed = Claim.model_validate(
        json.loads(_novelty_claim_path(tmp_path, spec.id).read_text(encoding="utf-8"))
    )
    assert proposed.status == ClaimStatus.PROPOSED

    # Second compile: a found_nothing decision is now in the record -> SUPPORTED.
    updater.update_claims_from_evidence(
        [_supporting_evidence(), _novelty_decision("hyp-1", "found_nothing")]
    )
    supported = Claim.model_validate(
        json.loads(_novelty_claim_path(tmp_path, spec.id).read_text(encoding="utf-8"))
    )
    assert supported.status == ClaimStatus.SUPPORTED
    # The status move is recorded (append-only history grew).
    assert len(supported.history) > len(proposed.history)
    last = supported.history[-1]
    assert last.to_status == ClaimStatus.SUPPORTED


# --------------------------------------------------------------------------- #
# decisions never enter the experiment verdict
# --------------------------------------------------------------------------- #

def test_novelty_decision_does_not_change_experiment_verdict(tmp_path):
    """A NOVELTY_DECISION (bears_on=[]) must not alter the experiment DecisionEngine
    verdict: the SUPPORTED experiment claim's supporting set is just the experiment
    evidence."""
    spec = _spec(True, "nov-no-verdict-change")
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence(
        [_supporting_evidence(point=0.95), _novelty_decision("hyp-1", "found_nothing")]
    )
    by_id = {c.id: c for c in claims}
    exp = by_id["claim-hyp-1"]
    assert exp.status == ClaimStatus.SUPPORTED
    supporting = exp.get_supporting_evidence()
    assert {link.evidence_id for link in supporting} == {"ev-num"}
