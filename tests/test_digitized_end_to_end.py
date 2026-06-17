"""
RED-first: end-to-end figure-digitization (synthetic figure -> Claim).

design/figure-digitization.md §8 item 4 (tests) + the user's full-MVP scope:
the whole lifecycle, exercised once end to end with NO GUI and NO LLM:

  synthetic figure case
    -> digitize(axis_calib, pixels)          (deterministic transform, search/)
    -> record_digitized(...) -> proposed     (NOT evidence-grade)
    -> [gate] proposed alone -> no SUPPORTED  (excluded)
    -> verify_digitized(item, verifier_id=B) -> verified  (independent replot, extractor!=verifier)
    -> [gate] verified counts as measured-grade -> empirical hypothesis SUPPORTED

This stitches the capability plugin (search/figure_digitize) to the kernel gate
(loop/claim_updater) the way a real run would, proving the borrow + build halves compose.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sci_adk.core.claim import ClaimStatus
from sci_adk.core.evidence import EvidenceKind
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
from sci_adk.search.figure_digitize import (
    AxisCalibration,
    AxisRef,
    digitize,
    record_digitized,
    verify_digitized,
)

_SPEC_ID = "spec-e2e-dig"
_HYP_ID = "hyp-e2e"
_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)


def _spec() -> Spec:
    return Spec(
        id=_SPEC_ID,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="A paper published organ dry-weight ONLY as a bar chart; no raw "
            "data and no in-text table values are available.",
            goal="Recover the published organ dry-weight value from the figure.",
            method="Digitize the bar chart; independently verify by replot overlay.",
            expected_output="The figure value, admissible only after independent verification.",
        ),
        hypotheses=[
            Hypothesis(
                id=_HYP_ID,
                statement="the published leaf dry weight equals ~50 g (point >= 0.5 in "
                "the normalized test metric)",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= 0.5 => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="empirical",
            )
        ],
        method=MethodPlan(approaches=["digitize"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="figure value recovered", answers=_HYP_ID)],
    )


def _calib() -> AxisCalibration:
    # Synthetic figure axes: x linear 100px->0 .. 500px->10 ; y linear 400px->0 .. 100px->100.
    return AxisCalibration(
        x=AxisRef(p1_pixel=100.0, p1_value=0.0, p2_pixel=500.0, p2_value=10.0, scale="linear"),
        y=AxisRef(p1_pixel=400.0, p1_value=0.0, p2_pixel=100.0, p2_value=100.0, scale="linear"),
    )


def test_end_to_end_digitize_proposed_then_verified_supports(tmp_path: Path):
    calib = _calib()

    # 1. digitize: the deterministic transform on an agent-picked pixel (the bar top).
    #    pixel (300, 250) -> data (x=5.0, y=50.0). We use y=50.0 as a "point" >= 0.5
    #    via a normalized metric of 0.9 (the metric is the test's; the digitized VALUE
    #    is the recovered figure number 50.0 g, recorded in digitized.value).
    (pt,) = digitize(calib, [(300.0, 250.0)], marker_radius_px=2.0)
    assert pt.value_y == 50.0

    # 2. record_digitized -> a PROPOSED item (extracted, not evidence-grade).
    proposed = record_digitized(
        ev_id="dig-1",
        spec_id=_SPEC_ID,
        quantity="leaf_dry_weight",
        unit="g",
        calib=calib,
        point_pixel=(300.0, 250.0),
        source="Fig 2 / 10.1234/rice",
        target_id=_HYP_ID,
        extractor="agent-A",
        # The normalized test metric the THRESHOLD rule reads (>= 0.5 => support).
        metric_point=0.9,
    )
    assert proposed.kind == EvidenceKind.DIGITIZED
    assert proposed.digitized.state == "proposed"
    assert proposed.digitized.value == 50.0  # the recovered figure number

    # 3. gate: a lone PROPOSED digitized item is excluded -> no SUPPORTED claim.
    claims = ClaimUpdater(_spec(), tmp_path).update_claims_from_evidence([proposed])
    assert claims == []

    # 4. verify_digitized: independent replot check by a DIFFERENT agent.
    verified = verify_digitized(proposed, verifier_id="agent-B")
    assert verified.digitized.state == "verified"
    assert verified.digitized.verification.verifier_id == "agent-B"
    assert verified.kind == EvidenceKind.DIGITIZED  # never auto-promoted to measured

    # 5. gate: the VERIFIED digitized item counts as measured-grade -> SUPPORTED.
    claims = ClaimUpdater(_spec(), tmp_path).update_claims_from_evidence([verified])
    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.SUPPORTED


def test_end_to_end_self_certified_verification_is_refused(tmp_path: Path):
    """If the extractor tries to verify their own digitization, verify_digitized refuses
    at the borrow layer; and even if such an item were constructed, the kernel gate also
    refuses it. Both halves enforce the self-certification ban."""
    calib = _calib()
    proposed = record_digitized(
        ev_id="dig-1", spec_id=_SPEC_ID, quantity="q", unit="g", calib=calib,
        point_pixel=(300.0, 250.0), source="Fig 2", target_id=_HYP_ID,
        extractor="agent-A", metric_point=0.9,
    )
    # Borrow layer refuses self-certification.
    import pytest
    with pytest.raises(ValueError):
        verify_digitized(proposed, verifier_id="agent-A")
