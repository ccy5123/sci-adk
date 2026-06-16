"""
Tests for the Phase D4 ClaimUpdater refactor (design/decision-engine.md §4).

These tests pin the *delegation* contract: ``ClaimUpdater`` no longer counts
``SUPPORTS``/``REFUTES`` bearings. Instead it hands the hypothesis's frozen
``DecisionRule`` and the bearing/results to ``DecisionEngine.evaluate`` and maps
the returned ``Verdict.direction`` to a ``ClaimStatus`` (Decision 8), using the
engine's ``Confidence`` directly (no hardcoded ``credence``).

The two non-trivial behaviors under test:

1. **CONTESTED override (the one judgment call, flagged for review).** The engine
   aggregates to ONE direction, so it cannot itself signal "mixed evidence". To
   preserve the contested capability the old vote-count had, the updater sets
   status=CONTESTED when the RAW bearings on the hypothesis contain BOTH a
   ``SUPPORTS`` and a ``REFUTES`` (matching ``ClaimStatus.CONTESTED`` "mixed
   evidence" + C5). Confidence still comes from the engine verdict.
2. **Non-monotone load-or-create (Decision 8 / C1 / C2).** A second run over an
   appended, refuting EvidenceItem recomputes the verdict over the FULL record and
   demotes a previously ``SUPPORTED`` claim, appending a new ``StatusChange`` to
   the append-only history that cites the triggering evidence.

No Docker: Spec / Hypothesis / DecisionRule / EvidenceItem / Bearing are all
constructed by hand. Engineering-layer tests (build harness domain) are
appropriate here (design/decision-engine.md §6 Phase D5 note).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pytest

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
)
from sci_adk.loop.claim_updater import ClaimUpdater, update_claims


# ---------------------------------------------------------------------------
# Hand-built fixtures. The point of building these by hand (rather than reusing
# tests/fixtures.py wholesale) is precise control over the decision-rule kind and
# the exact Result statistic each evidence item carries, so the mapping under
# test is unambiguous.
# ---------------------------------------------------------------------------

_HYP_ID = "hyp-encoding"
_SPEC_ID = "spec-d4-001"


def _spec_with_rule(rule: DecisionRule, hyp_id: str = _HYP_ID) -> Spec:
    """A minimal valid Spec carrying a single hypothesis with ``rule``."""
    return Spec(
        id=_SPEC_ID,
        created_at=datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        version=1,
        raw_proposal=RawProposal(
            background="bg",
            goal="goal",
            method="method",
            expected_output="output",
        ),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="Molecule graphs admit a bijective encoding",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=rule,
            )
        ],
        method=MethodPlan(approaches=["a"]),
        target_claims=[],
    )


def _evidence(
    ev_id: str,
    direction: BearingDirection,
    *,
    created_at: datetime,
    point: Optional[float] = None,
    posterior: Optional[float] = None,
    ci: Optional[List[float]] = None,
    finding: Optional[str] = None,
    weight: Optional[float] = None,
    target_id: str = _HYP_ID,
    kind: EvidenceKind = EvidenceKind.EXPERIMENT_RUN,
) -> EvidenceItem:
    """Build one EvidenceItem with a single bearing on ``target_id``."""
    if finding is not None:
        result = Result(type="qualitative", finding=finding)
    else:
        result = Result(type="quantitative", point=point, posterior=posterior, ci=ci)
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=kind,
        provenance=Provenance(code_ref="src/x.py:1"),
        result=result,
        bears_on=[Bearing(target_id=target_id, direction=direction, weight=weight)],
    )


_T0 = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 15, 11, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. Numeric rule whose evidence supports -> SUPPORTED, engine's confidence.
# ---------------------------------------------------------------------------


def test_threshold_support_maps_to_supported_with_engine_confidence(tmp_path: Path):
    """A threshold rule met by the evidence -> SUPPORTED; confidence is the
    engine's CREDENCE (NOT a hardcoded vote-count credence)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.9 => support",
        params={"statistic": "point", "op": ">=", "value": 0.9},
    )
    spec = _spec_with_rule(rule)
    ev = _evidence("ev-1", BearingDirection.SUPPORTS, created_at=_T0, point=0.97)

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    assert len(claims) == 1
    claim = claims[0]
    assert claim.status == ClaimStatus.SUPPORTED
    # Engine emits CREDENCE for threshold (Decision 5), with a real numeric value.
    assert claim.confidence.type == ConfidenceType.CREDENCE
    assert claim.confidence.value is not None and 0.0 <= claim.confidence.value <= 1.0
    # The basis must be the engine's (mentions the threshold rule), NOT the old
    # "N supporting, M refuting" vote-count basis.
    assert "threshold rule" in claim.confidence.basis
    assert "supporting" not in claim.confidence.basis


def test_bayesian_support_emits_posterior_confidence(tmp_path: Path):
    """A bayesian rule -> POSTERIOR confidence type (proves we are not flattening
    every kind to credence as the placeholder did)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.BAYESIAN,
        expression="posterior odds > 10 => support",
        params={"min_odds": 10.0},
    )
    spec = _spec_with_rule(rule)
    # posterior 0.95 -> odds 19 >= 10 -> supports
    ev = _evidence("ev-1", BearingDirection.SUPPORTS, created_at=_T0, posterior=0.95)

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    claim = claims[0]
    assert claim.status == ClaimStatus.SUPPORTED
    assert claim.confidence.type == ConfidenceType.POSTERIOR
    assert claim.confidence.value == pytest.approx(0.95)


def test_interval_support_maps_to_supported(tmp_path: Path):
    """An interval rule whose CI excludes the null on the support side -> SUPPORTED."""
    rule = DecisionRule(
        kind=DecisionRuleKind.INTERVAL,
        expression="95% CI excludes 0 => support",
        params={"null_value": 0.0, "support_side": "excludes"},
    )
    spec = _spec_with_rule(rule)
    ev = _evidence("ev-1", BearingDirection.SUPPORTS, created_at=_T0, ci=[0.2, 0.8])

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    claim = claims[0]
    assert claim.status == ClaimStatus.SUPPORTED
    assert claim.confidence.type == ConfidenceType.CREDENCE


# ---------------------------------------------------------------------------
# 2. Numeric rule whose evidence refutes -> REFUTED.
# ---------------------------------------------------------------------------


def test_threshold_not_met_maps_to_refuted(tmp_path: Path):
    """A threshold rule cleanly NOT met -> REFUTED (engine direction=refutes)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.9 => support",
        params={"statistic": "point", "op": ">=", "value": 0.9},
    )
    spec = _spec_with_rule(rule)
    # point 0.10 fails the >= 0.9 threshold -> refutes
    ev = _evidence("ev-1", BearingDirection.REFUTES, created_at=_T0, point=0.10)

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    claim = claims[0]
    assert claim.status == ClaimStatus.REFUTED
    assert claim.confidence.type == ConfidenceType.CREDENCE


# ---------------------------------------------------------------------------
# 3. Raw bearings with BOTH supports and refutes -> CONTESTED (the judgment call).
# ---------------------------------------------------------------------------


def test_mixed_raw_bearings_map_to_contested(tmp_path: Path):
    """When the raw bearings on the hypothesis contain BOTH a SUPPORTS and a
    REFUTES, the updater sets CONTESTED regardless of the engine's aggregated
    direction. Confidence is still taken from the engine verdict."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.5 => support",
        params={"statistic": "point", "op": ">=", "value": 0.5},
    )
    spec = _spec_with_rule(rule)
    ev_support = _evidence("ev-sup", BearingDirection.SUPPORTS, created_at=_T0, point=0.9)
    ev_refute = _evidence("ev-ref", BearingDirection.REFUTES, created_at=_T1, point=0.1)

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev_support, ev_refute])

    claim = claims[0]
    assert claim.status == ClaimStatus.CONTESTED
    # Confidence still flows from the engine (a credence for threshold), not a
    # fabricated contested value.
    assert claim.confidence.type == ConfidenceType.CREDENCE
    assert claim.confidence.basis  # non-empty (C3)
    # evidence_set is record-keeping (C5): both a supporting and a refuting link.
    roles = {link.role.value for link in claim.evidence_set}
    assert roles == {"supporting", "refuting"}


# ---------------------------------------------------------------------------
# 4. proof / qualitative rule -> engine stub inconclusive -> PROPOSED.
# ---------------------------------------------------------------------------


def test_proof_rule_without_judge_maps_to_proposed(tmp_path: Path):
    """A proof rule with no judge injected (and no counterexample) yields the
    engine's inconclusive verdict (Phase D3 routing) -> PROPOSED, carrying the
    GRADED/NONE confidence (no fabricated number, D8)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.PROOF,
        expression="Verified derivation or counterexample exists",
    )
    spec = _spec_with_rule(rule)
    ev = _evidence(
        "ev-1",
        BearingDirection.SUPPORTS,
        created_at=_T0,
        finding="a derivation",
        kind=EvidenceKind.PROOF_STEP,
    )

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    claim = claims[0]
    assert claim.status == ClaimStatus.PROPOSED
    # Inconclusive confidence is GRADED/NONE per the engine (no fabricated number, D8).
    assert claim.confidence.type == ConfidenceType.GRADED
    assert "judge" in claim.confidence.basis.lower()


def test_qualitative_rule_without_judge_maps_to_proposed(tmp_path: Path):
    """A qualitative rule with no judge also yields inconclusive -> PROPOSED."""
    rule = DecisionRule(
        kind=DecisionRuleKind.QUALITATIVE,
        expression="Expert consensus on structural preservation",
    )
    spec = _spec_with_rule(rule)
    ev = _evidence(
        "ev-1",
        BearingDirection.SUPPORTS,
        created_at=_T0,
        finding="experts agree",
    )

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    claim = claims[0]
    assert claim.status == ClaimStatus.PROPOSED
    assert claim.confidence.type == ConfidenceType.GRADED


# ---------------------------------------------------------------------------
# 5. Non-monotone demotion: SUPPORTED then (append refuting evidence) demoted,
#    with a NEW StatusChange appended to history citing the triggering evidence.
# ---------------------------------------------------------------------------


def test_non_monotone_demotion_appends_status_change(tmp_path: Path):
    """First run with supporting evidence -> SUPPORTED. Second run after appending
    refuting evidence recomputes over the FULL record and demotes the claim; the
    append-only history grows and the new StatusChange cites the triggering
    (latest) evidence (Decision 8, C1/C2)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.5 => support",
        params={"statistic": "point", "op": ">=", "value": 0.5},
    )
    spec = _spec_with_rule(rule)
    updater = ClaimUpdater(spec, tmp_path)

    # Run 1: a single supporting result above the threshold -> SUPPORTED.
    ev_support = _evidence("ev-sup", BearingDirection.SUPPORTS, created_at=_T0, point=0.9)
    first = updater.update_claims_from_evidence([ev_support])[0]
    assert first.status == ClaimStatus.SUPPORTED
    history_len_after_first = len(first.history)
    assert history_len_after_first == 1  # one initial StatusChange

    # Run 2: the append-only record now also contains a refuting result. The
    # combined latest statistic (0.1) misses the threshold AND both directions are
    # present in the raw bearings -> the claim must move off SUPPORTED.
    ev_refute = _evidence("ev-ref", BearingDirection.REFUTES, created_at=_T1, point=0.1)
    second = updater.update_claims_from_evidence([ev_support, ev_refute])[0]

    # Status moved (demotion is legal and expected, not a regression).
    assert second.status != ClaimStatus.SUPPORTED
    assert second.status in (ClaimStatus.CONTESTED, ClaimStatus.REFUTED)
    # Append-only history grew by exactly one new StatusChange.
    assert len(second.history) == history_len_after_first + 1
    latest_change = second.history[-1]
    assert latest_change.from_status == ClaimStatus.SUPPORTED
    assert latest_change.to_status == second.status
    # The new change cites the triggering (latest-arriving) evidence id.
    assert latest_change.triggered_by == "ev-ref"


def test_non_monotone_stable_status_does_not_append(tmp_path: Path):
    """Re-running with no status change must NOT append a spurious StatusChange
    (only NEW evidence that moves the verdict appends history; D5 determinism)."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.5 => support",
        params={"statistic": "point", "op": ">=", "value": 0.5},
    )
    spec = _spec_with_rule(rule)
    updater = ClaimUpdater(spec, tmp_path)

    ev = _evidence("ev-sup", BearingDirection.SUPPORTS, created_at=_T0, point=0.9)
    first = updater.update_claims_from_evidence([ev])[0]
    assert first.status == ClaimStatus.SUPPORTED
    len_after_first = len(first.history)

    # Same evidence, same verdict -> status unchanged -> no new history entry.
    second = updater.update_claims_from_evidence([ev])[0]
    assert second.status == ClaimStatus.SUPPORTED
    assert len(second.history) == len_after_first


# ---------------------------------------------------------------------------
# 6. The public convenience function still works (signature preserved).
# ---------------------------------------------------------------------------


def test_update_claims_convenience_function(tmp_path: Path):
    """``update_claims(spec, evidence, workspace_dir)`` still works end-to-end and
    persists a claim JSON file under runs/<spec.id>/claims/."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.9 => support",
        params={"statistic": "point", "op": ">=", "value": 0.9},
    )
    spec = _spec_with_rule(rule)
    ev = _evidence("ev-1", BearingDirection.SUPPORTS, created_at=_T0, point=0.97)

    claims = update_claims(spec, [ev], tmp_path)

    assert len(claims) == 1
    assert claims[0].status == ClaimStatus.SUPPORTED
    claim_file = tmp_path / "runs" / _SPEC_ID / "claims" / f"claim-{_HYP_ID}.json"
    assert claim_file.exists()


def test_no_relevant_evidence_yields_no_claim(tmp_path: Path):
    """Evidence bearing on a different hypothesis is filtered out (pre-filter at
    claim_updater.py:67-71 is preserved) -> no claim produced."""
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="point >= 0.9 => support",
        params={"statistic": "point", "op": ">=", "value": 0.9},
    )
    spec = _spec_with_rule(rule)
    other = _evidence(
        "ev-other",
        BearingDirection.SUPPORTS,
        created_at=_T0,
        point=0.97,
        target_id="some-other-hyp",
    )

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([other])

    assert claims == []
