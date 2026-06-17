"""
RED-first: ``sci-adk verify`` + ``record_digest`` coverage for digitized Evidence.

design/figure-digitization.md §5:
  - ``sci-adk verify``: for any COUNTED digitized item, re-confirm ``state==verified``
    + an independent-verifier record (extractor != verifier). A counted digitized that
    is proposed / unverified / self-certified -> reported DIVERGED/error.
  - ``record_digest``: must cover the VERIFICATION ARTIFACT of digitized items, so
    tampering with the verification record (not just the value) is caught.

The verification record lives inside ``EvidenceItem.digitized.verification``, which is
part of ``evidence/*.json`` -- already digested by ``record_digest`` (which folds the
typed EvidenceItem). These tests pin that a tampered verification changes the digest,
and that ``verify_run`` flags a counted digitized that is not properly verified.

No Docker, no LLM (engineering-layer tests; everything written to a tmp run dir).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
    EvidenceLink,
    EvidenceLinkRole,
    StatusChange,
)
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    DigitizedData,
    DigitizedVerification,
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
from sci_adk.loop.verify import DIVERGED, REPRODUCED, verify_run
from sci_adk.provenance import record_digest

_SPEC_ID = "dig-verify"
_HYP_ID = "hyp-dig"
_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)

_RULE = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="point >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)


def _spec() -> Spec:
    return Spec(
        id=_SPEC_ID,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=_HYP_ID,
                statement="organ dry weight from digitized figure",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=_RULE,
                referent="empirical",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=_HYP_ID)],
    )


def _digitized(
    *,
    state: str = "verified",
    verifier_id: Optional[str] = "agent-B",
    extractor: str = "agent-A",
    point: float = 0.9,
) -> EvidenceItem:
    verification = (
        DigitizedVerification(
            method="replot", verifier_id=verifier_id, result="reproduced",
            artifact="overlay.png",
        )
        if verifier_id is not None
        else None
    )
    return EvidenceItem(
        id="dig-1",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
        digitized=DigitizedData(
            quantity="dry_weight", value=point, unit="g", source="Fig 2",
            method="deterministic", read_uncert=0.05, state=state,
            verification=verification, extractor=extractor,
        ),
    )


def _supported_claim() -> Claim:
    return Claim(
        id=f"claim-{_HYP_ID}",
        spec_id=_SPEC_ID,
        answers=_HYP_ID,
        statement="organ dry weight from digitized figure",
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.8, basis="threshold met"),
        evidence_set=[EvidenceLink(evidence_id="dig-1", role=EvidenceLinkRole.SUPPORTING)],
        mode=HypothesisMode.CONFIRMATORY,
        history=[
            StatusChange(
                at=_T0,
                from_status=ClaimStatus.PROPOSED,
                to_status=ClaimStatus.SUPPORTED,
                triggered_by="dig-1",
                note="initial",
            )
        ],
    )


def _write_run(run_dir: Path, *, evidence: EvidenceItem, claim: Claim) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(
        json.dumps(_spec().model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / f"{evidence.id}.json").write_text(
        json.dumps(evidence.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    claims_dir = run_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    (claims_dir / f"{claim.id}.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# record_digest covers the digitized verification artifact.
# ---------------------------------------------------------------------------

def test_record_digest_changes_when_digitized_verification_tampered(tmp_path: Path):
    """The load-bearing requirement: tampering with the digitized VERIFICATION record
    (verifier_id) -- not the value -- must change the digest."""
    run_dir = tmp_path / "runs" / _SPEC_ID
    ev = _digitized(state="verified", verifier_id="agent-B")
    _write_run(run_dir, evidence=ev, claim=_supported_claim())
    before = record_digest(run_dir)

    # Tamper ONLY the verification record (forge a different verifier) -- value unchanged.
    tampered = ev.model_copy(
        update={
            "digitized": ev.digitized.model_copy(
                update={
                    "verification": ev.digitized.verification.model_copy(
                        update={"verifier_id": "agent-FORGED"}
                    )
                }
            )
        }
    )
    (run_dir / "evidence" / f"{ev.id}.json").write_text(
        json.dumps(tampered.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    after = record_digest(run_dir)
    assert before != after


def test_record_digest_changes_when_digitized_state_tampered(tmp_path: Path):
    """Flipping a recorded digitized item from verified -> proposed must change the
    digest (the audited surface includes the state)."""
    run_dir = tmp_path / "runs" / _SPEC_ID
    ev = _digitized(state="verified", verifier_id="agent-B")
    _write_run(run_dir, evidence=ev, claim=_supported_claim())
    before = record_digest(run_dir)
    tampered = ev.model_copy(
        update={"digitized": ev.digitized.model_copy(update={"state": "proposed"})}
    )
    (run_dir / "evidence" / f"{ev.id}.json").write_text(
        json.dumps(tampered.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    assert record_digest(run_dir) != before


# ---------------------------------------------------------------------------
# verify_run: a properly verified counted digitized reproduces.
# ---------------------------------------------------------------------------

def test_verify_run_reproduces_with_verified_independent_digitized(tmp_path: Path):
    run_dir = tmp_path / "runs" / _SPEC_ID
    ev = _digitized(state="verified", verifier_id="agent-B", extractor="agent-A")
    _write_run(run_dir, evidence=ev, claim=_supported_claim())
    report = verify_run(run_dir)
    assert report.all_reproduced
    assert report.outcomes[0].result == REPRODUCED


# ---------------------------------------------------------------------------
# verify_run: a counted digitized that is NOT properly verified is flagged.
# ---------------------------------------------------------------------------

def test_verify_run_flags_counted_proposed_digitized(tmp_path: Path):
    """A recorded SUPPORTED claim whose only supporting evidence is a *proposed*
    digitized item is not reproducible: the proposed item is excluded from eval, so
    the re-derivation cannot reach SUPPORTED -> not REPRODUCED (DIVERGED/UNRESOLVED)."""
    run_dir = tmp_path / "runs" / _SPEC_ID
    ev = _digitized(state="proposed", verifier_id=None)
    _write_run(run_dir, evidence=ev, claim=_supported_claim())
    report = verify_run(run_dir)
    assert not report.all_reproduced
    assert report.outcomes[0].result != REPRODUCED


def test_verify_run_flags_counted_self_certified_digitized(tmp_path: Path):
    """A recorded SUPPORTED claim backed by a counted digitized whose verifier ==
    extractor is self-certified -- the audit must flag it (DIVERGED), not reproduce."""
    run_dir = tmp_path / "runs" / _SPEC_ID
    ev = _digitized(state="verified", verifier_id="agent-A", extractor="agent-A")
    _write_run(run_dir, evidence=ev, claim=_supported_claim())
    report = verify_run(run_dir)
    assert not report.all_reproduced
    assert report.outcomes[0].result == DIVERGED


def test_verify_run_flags_counted_verified_missing_verifier(tmp_path: Path):
    """A recorded SUPPORTED claim backed by a digitized item marked verified but with
    no verifier record is flagged (an independent-verifier record is required)."""
    run_dir = tmp_path / "runs" / _SPEC_ID
    ev = _digitized(state="verified", verifier_id=None, extractor="agent-A")
    _write_run(run_dir, evidence=ev, claim=_supported_claim())
    report = verify_run(run_dir)
    assert not report.all_reproduced
    assert report.outcomes[0].result == DIVERGED
