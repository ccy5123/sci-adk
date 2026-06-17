"""
Phase D5: T-1 end-to-end verification (design/decision-engine.md §6).

Ties the chain together at the engineering layer:

  The canonical T-1 interval rule drives the verdict from a CI, and a
  SYNTHETIC refuting Evidence (CI flipped to the other side of the null,
  arriving later) demotes a SUPPORTED Claim non-monotonically -- a new
  StatusChange is appended (C1 non-monotone movement, C2 append-only history).

The interval rule needs a CI, so the non-monotone demotion uses synthetic
CI-carrying Evidence exactly as §6 specifies ("a synthetic refuting Evidence").
This confirms the per-Spec DecisionRule -- not a vote -- is the sole authority
for the verdict (D1).

The real Docker-backed T-1 experiment end-to-end (Spec -> container ->
DecisionEngine -> Claim) is covered by tests/test_t1_adapter.py against the
injective Gödel encoding in sci_adk.adapter.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sci_adk.core.claim import ClaimStatus, ConfidenceType
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
from sci_adk.loop.claim_updater import ClaimUpdater

_HYP = "hyp-t1-encoding"
_SPEC_ID = "t1-e2e"
_T0 = datetime(2026, 6, 16, 10, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 16, 11, 0, 0, tzinfo=timezone.utc)


def _t1_spec(rule: DecisionRule) -> Spec:
    """A minimal T-1 Spec: one molecular-encoding hypothesis carrying ``rule``."""
    return Spec(
        id=_SPEC_ID,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="Molecular graphs encoded as integers via Gödel-style numbering.",
            goal="A bijective prime-encoding of molecular graphs exists.",
            method="Encode H2O/CO2/CH4 and test injectivity in a Docker sandbox.",
            expected_output="A unique integer per molecule; injectivity demonstrated.",
        ),
        hypotheses=[
            # referent='formal': the T-1 injectivity claim is about the encoding map
            # (a formal object); the CI-carrying Evidence below is 'generated'. The
            # evidence-validity gate allows generated->formal (design/evidence-validity.md).
            Hypothesis(
                id=_HYP,
                statement="Molecule graphs admit a bijective Gödel-style encoding",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=rule,
                referent="formal",
                non_circularity="the encoding is checked for collisions on a generated "
                "set; collisions are not precluded by construction",
            )
        ],
        method=MethodPlan(approaches=["prime-factor encoding"], tools=[]),
        target_claims=[
            TargetClaim(id="tc-t1",
                        statement="A bijective encoding exists", answers=_HYP)
        ],
    )


def _ci_evidence(
    ev_id: str,
    lower: float,
    upper: float,
    *,
    created_at: datetime,
    direction: BearingDirection = BearingDirection.NEUTRAL,
) -> EvidenceItem:
    """Synthetic Evidence carrying a CI, bearing on the T-1 hypothesis.

    The bearing is NEUTRAL so the verdict is driven purely by the interval rule
    over the CI (not by the bearing vote), and a mix of NEUTRAL bearings never
    trips the ClaimUpdater's CONTESTED override -- isolating the demotion to the
    engine's recomputed verdict.
    """
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        # data_source='generated': an in-silico instance of the formal referent (the
        # encoding's behavior), not a synthetic proxy for an external phenomenon.
        provenance=Provenance(code_ref="synthetic:d5", data_source="generated"),
        result=Result(type="quantitative", ci=[lower, upper]),
        bears_on=[Bearing(target_id=_HYP, direction=direction)],
    )


def test_t1_interval_rule_drives_nonmonotone_demotion(tmp_path):
    """(2) The canonical T-1 interval rule drives the verdict from a CI; a later
    SYNTHETIC refuting Evidence demotes the SUPPORTED Claim to REFUTED, appending
    a new StatusChange (non-monotone belief over an append-only record)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.INTERVAL,
        expression="95% CI strictly above 0 => support; strictly below => refute",
        params={"null_value": 0.0, "support_side": "above", "confidence_level": 0.95},
    )
    spec = _t1_spec(rule)
    updater = ClaimUpdater(spec, tmp_path)

    # First evidence: CI entirely above null (0) -> interval rule -> SUPPORTS.
    support = _ci_evidence("ev-d5-support", 2.0, 5.0, created_at=_T0)
    claim1 = updater.update_claims_from_evidence([support])[0]
    assert claim1.status == ClaimStatus.SUPPORTED
    assert claim1.confidence.type == ConfidenceType.CREDENCE
    assert "interval rule" in claim1.confidence.basis  # the rule drove it, not a vote

    # Append a SYNTHETIC refuting result: CI entirely BELOW null, arriving later.
    # Re-evaluated over the full append-only record (combine='latest'), the newest
    # CI flips the verdict to REFUTES.
    refute = _ci_evidence("ev-d5-refute", -5.0, -2.0, created_at=_T1)
    claim2 = updater.update_claims_from_evidence([support, refute])[0]

    # Non-monotone demotion: SUPPORTED -> REFUTED, driven by the interval rule.
    assert claim2.status == ClaimStatus.REFUTED
    assert "interval rule" in claim2.confidence.basis

    # A NEW StatusChange records the demotion, citing the refuting evidence (C1/C2).
    last = claim2.history[-1]
    assert last.from_status == ClaimStatus.SUPPORTED
    assert last.to_status == ClaimStatus.REFUTED
    assert last.triggered_by == "ev-d5-refute"
