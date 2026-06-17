"""
RED-first: the digitized adequacy gate, COMPOSED with evidence-validity.

design/figure-digitization.md §5 + the user's confirmation. This is the trickiest part
-- the gate composes with ``check_evidence_adequacy`` at the ClaimUpdater chokepoint:

  (a) a ``digitized`` item in state ``proposed`` is EXCLUDED from DecisionRule
      evaluation -- it does not count toward "measured", and it does NOT halt
      (it is simply not evidence-grade yet, like a pending checkpoint).

  (b) a ``digitized`` item that would COUNT (bears on a binding SUPPORTS/REFUTES)
      MUST be ``state=="verified"`` AND carry ``verification.verifier_id`` that is
      present and != the extractor (self-certification ban applied to this kind).
      Missing -> refuse (ValidityHalt).

  (c) NEVER auto-promote digitized -> measured: it stays ``kind=digitized``. BUT a
      ``verified`` digitized item counts as MEASURED-GRADE for the empirical-referent
      adequacy check (it satisfies "an empirical hypothesis needs >=1 measured item").
      A ``proposed`` digitized item does NOT satisfy it.

Net effect against the rice-style case:
  - empirical hypothesis backed ONLY by ``proposed`` digitized -> still HALTS (no measured);
  - backed by a ``verified`` digitized (extractor != verifier) -> satisfies measured,
    can support.

The existing evidence-validity gate is NOT weakened -- it is composed with. These tests
construct everything by hand (no Docker, no LLM, no digitizer dependency: the digitized
EvidenceItems are built directly so the gate is tested in isolation).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

from sci_adk.core.claim import ClaimStatus
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
from sci_adk.core.validity import ValidityHalt
from sci_adk.loop.claim_updater import ClaimUpdater

_SPEC_ID = "spec-dig-gate"
_HYP_ID = "hyp-dig"
_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 17, 11, 0, 0, tzinfo=timezone.utc)

_THRESHOLD_RULE = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="point >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)


def _hyp(referent: str = "empirical", *, hyp_id: str = _HYP_ID) -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="organ dry weight predicted from digitized figure values",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=_THRESHOLD_RULE,
        referent=referent,
    )


def _spec(hyp: Hypothesis, spec_id: str = _SPEC_ID) -> Spec:
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


def _digitized(
    ev_id: str,
    *,
    state: str,
    direction: BearingDirection = BearingDirection.SUPPORTS,
    verifier_id: Optional[str] = None,
    extractor: str = "agent-A",
    point: float = 0.9,
    created_at: datetime = _T0,
    target_id: str = _HYP_ID,
    data_source=None,
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
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1", data_source=data_source),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=target_id, direction=direction)],
        digitized=DigitizedData(
            quantity="dry_weight", value=point, unit="g", source="Fig 2",
            method="deterministic", read_uncert=0.05, state=state,
            verification=verification, extractor=extractor,
        ),
    )


def _measured(
    ev_id: str,
    *,
    direction: BearingDirection = BearingDirection.SUPPORTS,
    point: float = 0.9,
    created_at: datetime = _T0,
) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="lab.py:1", data_source="measured"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=_HYP_ID, direction=direction)],
    )


# ---------------------------------------------------------------------------
# (a) proposed digitized -> EXCLUDED from eval: no count, no halt.
# ---------------------------------------------------------------------------

def test_proposed_digitized_alone_does_not_halt_but_yields_no_supported_claim(tmp_path: Path):
    """A lone ``proposed`` digitized item is not evidence-grade: it must NOT halt
    (it is a pending candidate, not a fabrication), but it also must NOT produce a
    SUPPORTED empirical claim (it is excluded from the verdict)."""
    spec = _spec(_hyp("empirical"))
    ev = _digitized("dig-1", state="proposed", point=0.9)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    # Excluded from eval -> the engine sees NO bearing -> no Claim is created at all
    # (the updater skips a hypothesis with no relevant -- i.e. counted -- evidence).
    assert claims == []
    claims_dir = tmp_path / "runs" / _SPEC_ID / "claims"
    assert not claims_dir.exists() or list(claims_dir.glob("*.json")) == []


def test_proposed_digitized_does_not_count_toward_measured(tmp_path: Path):
    """An empirical hypothesis backed ONLY by a proposed digitized item still HALTS
    when something binding is also present -- the proposed item does not satisfy the
    measured requirement. Here a binding generated item forces the measured check, and
    the proposed digitized cannot rescue it."""
    spec = _spec(_hyp("empirical"))
    # A binding generated item (counts, but is not measured) + a proposed digitized
    # (excluded). The empirical measured requirement is unmet -> HALT.
    gen = EvidenceItem(
        id="ev-gen",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
    )
    prop = _digitized("dig-1", state="proposed", point=0.95)
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([gen, prop])
    assert "measured" in str(exc.value).lower()


def test_proposed_digitized_excluded_even_on_formal(tmp_path: Path):
    """Exclusion of proposed digitized is kind-level, independent of referent: a formal
    hypothesis with ONLY a proposed digitized item creates no Claim (nothing to judge)."""
    spec = _spec(_hyp("formal", hyp_id=_HYP_ID))
    ev = _digitized("dig-1", state="proposed", point=0.9)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert claims == []


# ---------------------------------------------------------------------------
# (b) a digitized item that would COUNT must be verified + extractor != verifier.
# ---------------------------------------------------------------------------

def test_verified_digitized_independent_verifier_counts_and_supports(tmp_path: Path):
    """A ``verified`` digitized item (extractor != verifier) is COUNTED and satisfies
    the empirical measured-grade requirement -> the empirical hypothesis is SUPPORTED."""
    spec = _spec(_hyp("empirical"))
    ev = _digitized("dig-1", state="verified", verifier_id="agent-B",
                    extractor="agent-A", point=0.9)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.SUPPORTED


def test_verified_digitized_self_certified_is_refused(tmp_path: Path):
    """A counted digitized item whose verifier_id == extractor is self-certification ->
    refuse (ValidityHalt). The one who read the value off the plot may not certify it."""
    spec = _spec(_hyp("empirical"))
    ev = _digitized("dig-1", state="verified", verifier_id="agent-A",
                    extractor="agent-A", point=0.9)
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    msg = str(exc.value).lower()
    assert "verifier" in msg or "self" in msg


def test_counted_digitized_verified_missing_verifier_is_refused(tmp_path: Path):
    """A counted digitized item in state ``verified`` but with NO verifier_id recorded
    is refused -- a counted digitized must carry an independent-verifier record."""
    spec = _spec(_hyp("empirical"))
    # state verified but verification omitted (verifier_id absent).
    ev = EvidenceItem(
        id="dig-1",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1"),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
        digitized=DigitizedData(
            quantity="q", value=0.9, unit="g", source="Fig 2",
            method="deterministic", read_uncert=0.05, state="verified",
            verification=None, extractor="agent-A",
        ),
    )
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert "verif" in str(exc.value).lower()


def test_counted_digitized_with_none_extractor_is_refused(tmp_path: Path):
    """DEFENSE-IN-DEPTH (the extractor=None self-cert bypass).

    A digitized item whose ``extractor`` is None cannot normally be constructed (the
    schema is fail-closed), but a malformed/forged item (e.g. deserialized from a
    tampered record, here built via ``model_construct`` to skip validation) with
    ``extractor=None`` and ``verifier_id='agent-B'`` previously read as independent
    (``'agent-B' != None`` -> True) and yielded a SUPPORTED empirical Claim -- a
    self-certified digitization passing the gate. The gate guard now refuses any counted
    digitized item with no recorded extractor: it can NEVER count as independently
    verified."""
    spec = _spec(_hyp("empirical"))
    forged = DigitizedData.model_construct(
        quantity="q", value=0.9, unit="g", source="Fig 2", method="deterministic",
        axis_calib=None, read_uncert=0.05, state="verified",
        verification=DigitizedVerification(
            method="replot", verifier_id="agent-B", result="reproduced", artifact="o.png"
        ),
        extractor=None,  # bypass: no recorded extractor identity
    )
    ev = EvidenceItem(
        id="dig-1",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1"),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
        digitized=forged,
    )
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    claims_dir = tmp_path / "runs" / _SPEC_ID / "claims"
    assert not claims_dir.exists() or list(claims_dir.glob("*.json")) == []


def test_counted_digitized_with_empty_extractor_is_refused(tmp_path: Path):
    """DEFENSE-IN-DEPTH: an empty-string extractor (forged past the schema) must also be
    refused -- an empty extractor must never satisfy 'verifier_id != extractor'."""
    spec = _spec(_hyp("empirical"))
    forged = DigitizedData.model_construct(
        quantity="q", value=0.9, unit="g", source="Fig 2", method="deterministic",
        axis_calib=None, read_uncert=0.05, state="verified",
        verification=DigitizedVerification(
            method="replot", verifier_id="agent-B", result="reproduced", artifact="o.png"
        ),
        extractor="   ",  # whitespace-only: not a real identity
    )
    ev = EvidenceItem(
        id="dig-1",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1"),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
        digitized=forged,
    )
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])


def test_counted_digitized_in_proposed_state_with_binding_is_refused(tmp_path: Path):
    """If a digitized item's bearing would BIND (SUPPORTS) it must be verified. But a
    proposed digitized is EXCLUDED, so on its own it cannot bind. This test pins the
    interaction: a proposed digitized + a measured item that binds -> the measured
    drives the verdict (SUPPORTED) and the proposed digitized is simply excluded
    (no refusal, because the proposed item is not what is counted)."""
    spec = _spec(_hyp("empirical"))
    meas = _measured("ev-meas", point=0.9, created_at=_T0)
    prop = _digitized("dig-1", state="proposed", point=0.95, created_at=_T1)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([meas, prop])
    # The measured item satisfies the gate and binds; the proposed digitized is excluded.
    assert claims[0].status == ClaimStatus.SUPPORTED


# ---------------------------------------------------------------------------
# (c) never auto-promote: digitized stays kind=digitized; verified counts as measured.
# ---------------------------------------------------------------------------

def test_verified_digitized_stays_digitized_kind(tmp_path: Path):
    """The gate NEVER mutates a digitized item to kind=measured: the persisted record
    keeps kind=digitized even though it counts as measured-grade for the gate."""
    spec = _spec(_hyp("empirical"))
    ev = _digitized("dig-1", state="verified", verifier_id="agent-B",
                    extractor="agent-A", point=0.9)
    # The item handed in is unchanged (frozen) and remains kind=digitized.
    ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert ev.kind == EvidenceKind.DIGITIZED
    assert ev.digitized.state == "verified"  # not "measured", not mutated


def test_verified_digitized_mixed_with_measured_supports(tmp_path: Path):
    """A verified digitized item alongside a measured item: both count; SUPPORTED."""
    spec = _spec(_hyp("empirical"))
    meas = _measured("ev-meas", point=0.9, created_at=_T0)
    dig = _digitized("dig-1", state="verified", verifier_id="agent-B",
                     extractor="agent-A", point=0.95, created_at=_T1)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([meas, dig])
    assert claims[0].status == ClaimStatus.SUPPORTED


# ---------------------------------------------------------------------------
# RICE-STYLE COMPOSE: empirical hypothesis driven by digitized figure values.
# ---------------------------------------------------------------------------

def test_rice_style_only_proposed_digitized_halts_no_supported(tmp_path: Path):
    """RICE-STYLE COMPOSE (proposed branch).

    An empirical hypothesis whose ONLY would-be-binding evidence is a *proposed*
    digitized item alongside a binding generated item: no measured-grade item exists
    (the proposed digitized does not satisfy it) -> HALT, exactly as the rice case.
    """
    spec = _spec(_hyp("empirical"))
    gen = EvidenceItem(
        id="ev-gen",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(type="quantitative", point=0.87),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
    )
    prop = _digitized("dig-1", state="proposed", point=0.9)
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([gen, prop])
    claims_dir = tmp_path / "runs" / _SPEC_ID / "claims"
    assert not claims_dir.exists() or list(claims_dir.glob("*.json")) == []


def test_rice_style_verified_digitized_satisfies_measured_and_supports(tmp_path: Path):
    """RICE-STYLE COMPOSE (verified branch).

    The SAME empirical hypothesis, now backed by a *verified* digitized item
    (extractor != verifier), satisfies the measured-grade requirement and is SUPPORTED.
    A figure-only empirical result is admissible ONLY after independent verification.
    """
    spec = _spec(_hyp("empirical"))
    dig = _digitized("dig-1", state="verified", verifier_id="agent-B",
                     extractor="agent-A", point=0.9)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([dig])
    assert claims[0].status == ClaimStatus.SUPPORTED


def test_synthetic_proxy_digitized_on_empirical_still_halts(tmp_path: Path):
    """Composition does NOT weaken evidence-validity: a digitized item whose provenance
    is synthetic_proxy bearing on an empirical hypothesis still halts unconditionally
    (the existing Guard 3 item 1). A verified digitized is measured-GRADE, but a
    synthetic_proxy provenance is a fabrication regardless of digitized state."""
    spec = _spec(_hyp("empirical"))
    ev = _digitized("dig-1", state="verified", verifier_id="agent-B",
                    extractor="agent-A", point=0.9, data_source="synthetic_proxy")
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert "synthetic_proxy" in str(exc.value)
