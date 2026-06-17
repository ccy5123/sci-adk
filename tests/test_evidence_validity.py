"""
Evidence-validity enforcement -- RED-first (design/evidence-validity.md).

These tests pin the referent-typed adequacy gate (E1-E4 + the non-circularity
attestation) that closes the rice-failure defect: a run on an EMPIRICAL proposal
that uses SYNTHETIC data must HALT, not report "supported".

The line is NOT synthetic-vs-real; it is whether the data INSTANTIATES the claim's
referent (formal: generated instances are genuine evidence -- T-1) or PROXIES an
external referent it does not contain (empirical: needs measured data).

Placement under test:
  - E1  Hypothesis.referent (frozen, default "empirical" -- fail-closed).
  - E2  Provenance.data_source (default None -- treated as "not measured").
  - E3  adequacy gate (HARD ValidityHalt) at the Evidence->Claim chokepoint
        (ClaimUpdater), surfaced by the CLI as a friendly non-zero exit.
  - E4  config halt for the contact email (search/paperforge_adapter + sci_adk.config).
  - attestation: a formal/generated hypothesis with no non-circularity statement is
        SURFACED (a checkpoint), never auto-proven.

No Docker, no LLM: Spec / Hypothesis / DecisionRule / EvidenceItem / Bearing are all
constructed by hand (engineering-layer tests, the build-harness domain).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pytest

from sci_adk.core.claim import ClaimStatus
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
from sci_adk.core.validity import ValidityHalt
from sci_adk.loop.claim_updater import ClaimUpdater

_SPEC_ID = "spec-ev-validity"
_HYP_ID = "hyp-ev"
_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 17, 11, 0, 0, tzinfo=timezone.utc)

# A numeric threshold rule met by point >= 0.5 (so a single supporting point
# above 0.5 produces a BINDING SUPPORTS verdict from the engine).
_THRESHOLD_RULE = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="point >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)


def _hyp(
    referent: str,
    *,
    rule: DecisionRule = _THRESHOLD_RULE,
    non_circularity: Optional[str] = None,
    hyp_id: str = _HYP_ID,
) -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="the claim under test",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=rule,
        referent=referent,
        non_circularity=non_circularity,
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


def _evidence(
    ev_id: str,
    direction: BearingDirection,
    *,
    data_source: Optional[str],
    point: Optional[float] = None,
    created_at: datetime = _T0,
    target_id: str = _HYP_ID,
) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="src/x.py:1", data_source=data_source),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=target_id, direction=direction)],
    )


# ---------------------------------------------------------------------------
# E1: Hypothesis.referent -- frozen, default "empirical" (fail-closed).
# ---------------------------------------------------------------------------

def test_referent_defaults_to_empirical():
    """An unmarked hypothesis is the strictest case -- empirical (real data required)."""
    h = Hypothesis(
        id="h",
        statement="s",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=_THRESHOLD_RULE,
    )
    assert h.referent == "empirical"


def test_referent_rejects_unknown_value():
    """Only formal | empirical are allowed (a typo cannot smuggle a third class)."""
    with pytest.raises(Exception):
        Hypothesis(
            id="h",
            statement="s",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=_THRESHOLD_RULE,
            referent="experimental",  # not a valid referent class
        )


def test_referent_is_frozen_in_spec():
    """referent is frozen (anti-HARKing): it cannot be mutated after construction."""
    h = _hyp("empirical")
    with pytest.raises(Exception):
        h.referent = "formal"  # frozen model -> mutation refused


# ---------------------------------------------------------------------------
# E2: Provenance.data_source -- default None.
# ---------------------------------------------------------------------------

def test_data_source_defaults_to_none():
    assert Provenance(code_ref="x").data_source is None


def test_data_source_rejects_unknown_value():
    with pytest.raises(Exception):
        Provenance(code_ref="x", data_source="fabricated")


# ---------------------------------------------------------------------------
# E3 case A: synthetic_proxy bearing on an EMPIRICAL hypothesis -> HALT.
# ---------------------------------------------------------------------------

def test_synthetic_proxy_on_empirical_halts(tmp_path: Path):
    """A fabricated stand-in for an external referent is a category error -- halt,
    even though the bearing direction here would otherwise be binding."""
    spec = _spec(_hyp("empirical"))
    ev = _evidence("ev-1", BearingDirection.SUPPORTS,
                   data_source="synthetic_proxy", point=0.9)
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert "synthetic_proxy" in str(exc.value)
    assert "empirical" in str(exc.value)


def test_synthetic_proxy_on_empirical_halts_even_when_neutral(tmp_path: Path):
    """The synthetic_proxy->empirical halt is UNCONDITIONAL: a neutral bearing (which
    would yield a non-binding verdict) still halts, because the fabrication itself is
    the error (not the verdict it would produce)."""
    spec = _spec(_hyp("empirical"))
    ev = _evidence("ev-1", BearingDirection.NEUTRAL,
                   data_source="synthetic_proxy", point=0.9)
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])


# ---------------------------------------------------------------------------
# E3 case B: EMPIRICAL hypothesis, binding verdict, NO measured item -> HALT.
# ---------------------------------------------------------------------------

def test_empirical_binding_with_no_measured_halts(tmp_path: Path):
    """An empirical hypothesis whose bearing evidence would bind (SUPPORTS) but
    carries no measured item (here: generated) halts -- the rice failure stops here."""
    spec = _spec(_hyp("empirical"))
    ev = _evidence("ev-1", BearingDirection.SUPPORTS,
                   data_source="generated", point=0.9)
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert "measured" in str(exc.value).lower()


def test_empirical_binding_with_none_source_halts(tmp_path: Path):
    """data_source=None is treated as 'not measured' (fail-closed): a binding empirical
    verdict over only None-sourced evidence halts exactly as generated would."""
    spec = _spec(_hyp("empirical"))
    ev = _evidence("ev-1", BearingDirection.SUPPORTS, data_source=None, point=0.9)
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])


def test_empirical_non_binding_does_not_halt(tmp_path: Path):
    """A non-binding (INCONCLUSIVE) verdict on an empirical hypothesis yields a PROPOSED
    claim and must NOT halt: belief is gated, the record is not. An empirical hypothesis
    may legitimately await real data without halting.

    The threshold engine derives direction from the STATISTIC, so a non-binding verdict
    needs evidence that carries no 'point' (here a qualitative finding) -> INCONCLUSIVE
    -> PROPOSED. This is the 'awaiting real data' state, not an affirmation."""
    spec = _spec(_hyp("empirical"))
    ev = EvidenceItem(
        id="ev-1",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="src/x.py:1", data_source=None),
        result=Result(type="qualitative", finding="awaiting measured data"),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.NEUTRAL)],
    )
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.PROPOSED


def test_empirical_binding_with_measured_is_allowed(tmp_path: Path):
    """An empirical hypothesis backed by MEASURED data binds normally -> SUPPORTED."""
    spec = _spec(_hyp("empirical"))
    ev = _evidence("ev-1", BearingDirection.SUPPORTS,
                   data_source="measured", point=0.9)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert claims[0].status == ClaimStatus.SUPPORTED


def test_empirical_measured_mixed_with_generated_is_allowed(tmp_path: Path):
    """At least one measured item among the bearing evidence satisfies the gate."""
    spec = _spec(_hyp("empirical"))
    gen = _evidence("ev-gen", BearingDirection.SUPPORTS,
                    data_source="generated", point=0.9, created_at=_T0)
    meas = _evidence("ev-meas", BearingDirection.SUPPORTS,
                     data_source="measured", point=0.95, created_at=_T1)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([gen, meas])
    assert claims[0].status == ClaimStatus.SUPPORTED


# ---------------------------------------------------------------------------
# E3 case C: generated -> formal -> ALLOWED (the T-1-style legitimate case).
# ---------------------------------------------------------------------------

def test_generated_on_formal_with_attestation_is_allowed(tmp_path: Path):
    """generated Evidence on a formal hypothesis (with a non-circularity attestation)
    binds normally -> SUPPORTED. This is the legitimate computational result (T-1)."""
    spec = _spec(_hyp("formal", non_circularity="collisions could occur; the verifier "
                                                "independently checks for them"))
    ev = _evidence("ev-1", BearingDirection.SUPPORTS,
                   data_source="generated", point=0.9)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert claims[0].status == ClaimStatus.SUPPORTED


# ---------------------------------------------------------------------------
# Attestation: formal/generated WITHOUT a non-circularity statement is SURFACED.
# ---------------------------------------------------------------------------

def test_formal_generated_missing_attestation_is_surfaced(tmp_path: Path):
    """A formal hypothesis reaching a BINDING verdict on generated evidence but with
    NO non-circularity attestation is surfaced (not auto-proven): the gate records the
    missing-attestation concern rather than silently certifying. We model 'surfaced'
    as a ValidityHalt naming non-circularity -- the engine refuses to bind a formal
    generated result it cannot even record an attestation for."""
    spec = _spec(_hyp("formal", non_circularity=None))
    ev = _evidence("ev-1", BearingDirection.SUPPORTS,
                   data_source="generated", point=0.9)
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert "non-circular" in str(exc.value).lower()


def test_formal_generated_missing_attestation_non_binding_does_not_halt(tmp_path: Path):
    """A non-binding formal/generated verdict (INCONCLUSIVE) does not need the
    attestation yet -- nothing is being certified, so no surfacing. Evidence carries no
    'point' so the threshold engine returns INCONCLUSIVE."""
    spec = _spec(_hyp("formal", non_circularity=None))
    ev = EvidenceItem(
        id="ev-1",
        created_at=_T0,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="src/x.py:1", data_source="generated"),
        result=Result(type="qualitative", finding="no statistic yet"),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.NEUTRAL)],
    )
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert claims[0].status == ClaimStatus.PROPOSED


# ---------------------------------------------------------------------------
# THE RICE-FAILURE REGRESSION: empirical hypotheses + synthetic data -> HALT.
# This is the exact behavior the user was angry about.
# ---------------------------------------------------------------------------

def test_rice_failure_regression_synthetic_on_empirical_halts(tmp_path: Path):
    """REGRESSION (the rice organ dry-weight failure).

    Four EMPIRICAL hypotheses (predict rice organ dry-weight from measured traits),
    fed SYNTHETIC data, must HALT -- not report '4/4 SUPPORTED / validated milestone'.
    The pipeline can no longer self-certify an ungrounded empirical result.
    """
    organs = ["leaf", "stem", "root", "panicle"]
    hyps = [
        Hypothesis(
            id=f"hyp-{organ}",
            statement=f"plant traits predict {organ} dry weight (R^2 >= 0.5)",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="R2 >= 0.5 => support",
                params={"statistic": "point", "op": ">=", "value": 0.5},
            ),
            # referent omitted on purpose -> defaults to "empirical" (fail-closed):
            # exactly the unmarked-empirical case the rice run was.
        )
        for organ in organs
    ]
    spec = Spec(
        id="rice-dry-weight",
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="Rice organ dry-weight prediction from plant traits.",
            goal="Predict leaf/stem/root/panicle dry weight from measured traits.",
            method="Regress organ dry weight on measured plant traits.",
            expected_output="A predictive model per organ (R^2 >= 0.5).",
        ),
        hypotheses=hyps,
        method=MethodPlan(approaches=["regression"], tools=[]),
        target_claims=[
            TargetClaim(id=f"tc-{o}", statement=f"{o} predicted", answers=f"hyp-{o}")
            for o in organs
        ],
    )
    # SYNTHETIC data: every "measurement" is a fabricated stand-in (synthetic_proxy),
    # each above the R^2 threshold so the OLD pipeline would have called them SUPPORTED.
    synthetic_evidence = [
        EvidenceItem(
            id=f"ev-{organ}",
            created_at=_T0,
            spec_id="rice-dry-weight",
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="synthetic.py:1",
                                  data_source="synthetic_proxy"),
            result=Result(type="quantitative", point=0.87),  # "great" R^2
            bears_on=[Bearing(target_id=f"hyp-{organ}",
                              direction=BearingDirection.SUPPORTS)],
        )
        for organ in organs
    ]

    # The pipeline HALTS on synthetic-on-empirical; no Claim is recorded.
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path).update_claims_from_evidence(synthetic_evidence)

    # The halt names the category error (synthetic proxy fed to an empirical claim).
    msg = str(exc.value).lower()
    assert "synthetic_proxy" in str(exc.value)
    assert "empirical" in msg
    # And critically: NO claim JSON was persisted (nothing was self-certified).
    claims_dir = tmp_path / "runs" / "rice-dry-weight" / "claims"
    assert not claims_dir.exists() or list(claims_dir.glob("*.json")) == []
