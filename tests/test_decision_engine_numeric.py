"""
Unit tests for the DecisionEngine numeric handlers (Phase D2).

Spec: design/decision-engine.md (CONFIRMED 2026-06-15), focus on
    - Decision 2: numeric kinds (threshold / bayesian / interval) Result-field +
      params -> direction + confidence mappings
    - Decision 3: interval null value comes from params (null_value + support_side);
      absent null_value -> inconclusive (D1), never a default
    - Decision 5: kind -> ConfidenceType (threshold/interval=credence,
      bayesian=posterior); basis always required (D2)
    - Decision 6: Bearing.weight is a per-result multiplier (default 1.0)
    - Decision 7: rule-scoped aggregation -- combine the per-result statistics
      first, then apply the rule once; combine method from params, default "latest"
    - D1: no numeric constant absent from rule.params; a missing required key
      yields INCONCLUSIVE with a basis naming the missing key (never a default)

Phase D2 scope is the THREE NUMERIC kinds ONLY. proof / qualitative remain Phase
D1 stubs (their LLM-judge / human routing is Phase D3); they are intentionally
NOT exercised here for numeric semantics.

These tests are written test-first (RED) and assert the real numeric behavior:
per numeric kind a supports / refutes / neutral(or inconclusive) case, a
missing-required-param -> inconclusive case (D1), the correct Confidence.type +
value (Decision 5), weight influence (Decision 6), and multi-result aggregation
with the default "latest" combine (Decision 7).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pytest

from sci_adk.core.claim import ConfidenceLevel, ConfidenceType
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.spec import DecisionRule, DecisionRuleKind
from sci_adk.loop.decision_engine import (
    DecisionEngine,
    EvidenceForHypothesis,
    Verdict,
)


# ---------------------------------------------------------------------------
# Builders: construct real EvidenceItem / Bearing pairs that bear on one
# hypothesis. The engine reads Result fields + Bearing.weight only; the
# (EvidenceItem, Bearing) view mirrors what ClaimUpdater pre-filters.
# ---------------------------------------------------------------------------

_HYP_ID = "hyp-001"


def _provenance() -> Provenance:
    return Provenance(code_ref="commit-abc:1", seed=0)


def _evidence_item(
    result: Result,
    *,
    eid: str = "ev-001",
    kind: EvidenceKind = EvidenceKind.EXPERIMENT_RUN,
    direction: BearingDirection = BearingDirection.SUPPORTS,
    weight: Optional[float] = None,
    target_id: str = _HYP_ID,
) -> Tuple[EvidenceItem, Bearing]:
    """Build one (EvidenceItem, Bearing) pair bearing on the hypothesis."""
    bearing = Bearing(target_id=target_id, direction=direction, weight=weight)
    item = EvidenceItem(
        id=eid,
        spec_id="spec-001",
        kind=kind,
        provenance=_provenance(),
        result=result,
        bears_on=[bearing],
    )
    return item, bearing


def _results(*pairs: Tuple[EvidenceItem, Bearing]) -> EvidenceForHypothesis:
    return EvidenceForHypothesis(pairs=list(pairs))


def _point_result(point: float) -> Result:
    return Result(type="quantitative", point=point)


def _posterior_result(posterior: float) -> Result:
    return Result(type="quantitative", posterior=posterior)


def _ci_result(lower: float, upper: float) -> Result:
    return Result(type="quantitative", ci=[lower, upper])


@pytest.fixture
def engine() -> DecisionEngine:
    return DecisionEngine()


# ===========================================================================
# THRESHOLD (Decision 2): Result.point vs params {"statistic","op","value"}.
# Direction: condition met -> supports; cleanly not met -> refutes; missing
# operand/param -> inconclusive (D1). Confidence: CREDENCE, margin-based value.
# ===========================================================================

def _threshold_rule(op: str = ">=", value: float = 0.5, **extra) -> DecisionRule:
    params = {"statistic": "point", "op": op, "value": value}
    params.update(extra)
    return DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression=f"point {op} {value} => support",
        params=params,
    )


class TestThreshold:
    def test_supports_when_condition_met(self, engine):
        verdict = engine.evaluate(
            _threshold_rule(">=", 0.5), _results(_evidence_item(_point_result(0.9)))
        )
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_refutes_when_cleanly_not_met(self, engine):
        verdict = engine.evaluate(
            _threshold_rule(">=", 0.5), _results(_evidence_item(_point_result(0.1)))
        )
        assert verdict.direction == BearingDirection.REFUTES

    def test_inconclusive_when_point_missing(self, engine):
        """D1/D3: a missing statistic operand yields inconclusive, not a guess."""
        verdict = engine.evaluate(
            _threshold_rule(">=", 0.5),
            _results(_evidence_item(Result(type="quantitative"))),  # point is None
        )
        assert verdict.direction == BearingDirection.INCONCLUSIVE

    def test_inconclusive_when_required_param_missing(self, engine):
        """D1: the engine must NOT substitute a default for a missing 'value' key;
        it returns inconclusive with a basis naming the missing key."""
        rule = DecisionRule(
            kind=DecisionRuleKind.THRESHOLD,
            expression="point passes threshold => support",
            params={"statistic": "point", "op": ">="},  # 'value' absent
        )
        verdict = engine.evaluate(rule, _results(_evidence_item(_point_result(0.9))))
        assert verdict.direction == BearingDirection.INCONCLUSIVE
        assert "value" in verdict.confidence.basis.lower()

    def test_confidence_type_is_credence_with_value(self, engine):
        """Decision 5: threshold -> CREDENCE; margin-based numeric value in [0,1]."""
        verdict = engine.evaluate(
            _threshold_rule(">=", 0.5), _results(_evidence_item(_point_result(0.9)))
        )
        assert verdict.confidence.type == ConfidenceType.CREDENCE
        assert verdict.confidence.value is not None
        assert 0.0 <= verdict.confidence.value <= 1.0
        assert verdict.confidence.level is None

    def test_basis_quotes_statistic_op_value(self, engine):
        """D2: basis quotes the statistic, op, and value that produced the verdict."""
        basis = engine.evaluate(
            _threshold_rule(">=", 0.5), _results(_evidence_item(_point_result(0.9)))
        ).confidence.basis.lower()
        assert "point" in basis
        assert ">=" in basis
        assert "0.5" in basis

    def test_larger_margin_gives_higher_confidence(self, engine):
        """Margin-based confidence is monotone: further past the threshold -> higher."""
        near = engine.evaluate(
            _threshold_rule(">=", 0.5), _results(_evidence_item(_point_result(0.55)))
        ).confidence.value
        far = engine.evaluate(
            _threshold_rule(">=", 0.5), _results(_evidence_item(_point_result(0.99)))
        ).confidence.value
        assert far > near

    def test_supports_with_less_than_operator(self, engine):
        """op '<' is honored: a small statistic meets a '<' threshold -> supports."""
        verdict = engine.evaluate(
            _threshold_rule("<", 0.5), _results(_evidence_item(_point_result(0.1)))
        )
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_aggregation_latest_is_default(self, engine):
        """Decision 7: with multiple results, default combine='latest' applies the
        rule to the most-recent statistic only. The latest point (0.1) fails >=0.5
        even though an earlier point (0.9) passed."""
        first = _evidence_item(_point_result(0.9), eid="ev-001")
        second = _evidence_item(_point_result(0.1), eid="ev-002")
        verdict = engine.evaluate(_threshold_rule(">=", 0.5), _results(first, second))
        assert verdict.direction == BearingDirection.REFUTES

    def test_aggregation_pool_is_minimal_latest_equivalent(self, engine):
        """Decision 7: 'pool' is a documented minimal implementation -- it behaves
        like 'latest' (no meta-analytic pooling yet) and is NOT silently faked as
        real pooling. Latest point (0.1) under pool fails >= 0.5 -> refutes, exactly
        as 'latest' would, and the basis records combine='pool'."""
        rule = _threshold_rule(">=", 0.5, combine="pool")
        first = _evidence_item(_point_result(0.9), eid="ev-001")
        second = _evidence_item(_point_result(0.1), eid="ev-002")
        verdict = engine.evaluate(rule, _results(first, second))
        assert verdict.direction == BearingDirection.REFUTES
        assert "pool" in verdict.confidence.basis.lower()

    def test_unsupported_combine_is_inconclusive(self, engine):
        """D1: an unrecognized combine method -> inconclusive, not a silent default."""
        rule = _threshold_rule(">=", 0.5, combine="nonsense")
        verdict = engine.evaluate(rule, _results(_evidence_item(_point_result(0.9))))
        assert verdict.direction == BearingDirection.INCONCLUSIVE
        assert "combine" in verdict.confidence.basis.lower()

    def test_latest_tiebreak_is_sequence_order(self, engine):
        """D5 determinism: when two results share an identical created_at timestamp,
        'latest' resolves to the later sequence position (arrival/append order), so
        the verdict is stable regardless of timestamp resolution."""
        from datetime import datetime, timezone

        ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        # Build two items with the SAME created_at; the second in sequence wins.
        early = EvidenceItem(
            id="ev-001", spec_id="spec-001", kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=_provenance(), result=_point_result(0.9), created_at=ts,
            bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
        )
        late = EvidenceItem(
            id="ev-002", spec_id="spec-001", kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=_provenance(), result=_point_result(0.1), created_at=ts,
            bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
        )
        e1 = (early, early.bears_on[0])
        e2 = (late, late.bears_on[0])
        # Sequence [early, late]: latest = late (0.1) -> refutes >= 0.5.
        v = engine.evaluate(_threshold_rule(">=", 0.5), _results(e1, e2))
        assert v.direction == BearingDirection.REFUTES

    def test_aggregation_mean_combines_statistics(self, engine):
        """Decision 7: combine='mean' averages the statistics, then applies the rule
        once. mean(0.9, 0.1) = 0.5 which meets >= 0.5 -> supports (whereas latest
        would refute)."""
        rule = _threshold_rule(">=", 0.5, combine="mean")
        first = _evidence_item(_point_result(0.9), eid="ev-001")
        second = _evidence_item(_point_result(0.1), eid="ev-002")
        verdict = engine.evaluate(rule, _results(first, second))
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_weight_influences_mean_aggregation(self, engine):
        """Decision 6: Bearing.weight is a per-result multiplier in the (mean)
        combine. Down-weighting the high statistic pulls the weighted mean below
        the threshold -> refutes; with equal weights it would support."""
        rule = _threshold_rule(">=", 0.5, combine="mean")
        # weighted mean = (0.9*0.1 + 0.1*1.0) / (0.1 + 1.0) = 0.19/1.1 ~= 0.17 < 0.5
        heavy_low = _evidence_item(_point_result(0.1), eid="ev-002", weight=1.0)
        light_high = _evidence_item(_point_result(0.9), eid="ev-001", weight=0.1)
        verdict = engine.evaluate(rule, _results(light_high, heavy_low))
        assert verdict.direction == BearingDirection.REFUTES

    def test_inconclusive_when_no_results(self, engine):
        """D1/D3: no results bearing on the hypothesis -> inconclusive."""
        verdict = engine.evaluate(_threshold_rule(">=", 0.5), _results())
        assert verdict.direction == BearingDirection.INCONCLUSIVE


# ===========================================================================
# BAYESIAN (Decision 2): Result.posterior -> odds p/(1-p) vs params {"min_odds"}.
# odds >= k -> supports; odds <= 1/k -> refutes; between -> neutral.
# Confidence: POSTERIOR, value = Result.posterior.
# ===========================================================================

def _bayesian_rule(min_odds: float = 10.0, **extra) -> DecisionRule:
    params = {"min_odds": min_odds}
    params.update(extra)
    return DecisionRule(
        kind=DecisionRuleKind.BAYESIAN,
        expression=f"posterior odds >= {min_odds} => support",
        params=params,
    )


class TestBayesian:
    def test_supports_when_odds_at_or_above_min(self, engine):
        """posterior 0.95 -> odds 19 >= 10 -> supports."""
        verdict = engine.evaluate(
            _bayesian_rule(10.0), _results(_evidence_item(_posterior_result(0.95)))
        )
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_refutes_when_odds_at_or_below_inverse(self, engine):
        """posterior 0.05 -> odds 0.0526 <= 1/10 -> refutes (symmetric evidence)."""
        verdict = engine.evaluate(
            _bayesian_rule(10.0), _results(_evidence_item(_posterior_result(0.05)))
        )
        assert verdict.direction == BearingDirection.REFUTES

    def test_neutral_between_thresholds(self, engine):
        """posterior 0.5 -> odds 1.0, between 1/10 and 10 -> neutral."""
        verdict = engine.evaluate(
            _bayesian_rule(10.0), _results(_evidence_item(_posterior_result(0.5)))
        )
        assert verdict.direction == BearingDirection.NEUTRAL

    def test_inconclusive_when_posterior_missing(self, engine):
        """D1/D3: posterior absent -> inconclusive, never a guessed probability."""
        verdict = engine.evaluate(
            _bayesian_rule(10.0),
            _results(_evidence_item(Result(type="quantitative"))),  # posterior None
        )
        assert verdict.direction == BearingDirection.INCONCLUSIVE

    def test_inconclusive_when_min_odds_missing(self, engine):
        """D1: missing 'min_odds' -> inconclusive with basis naming the key,
        never a default odds threshold."""
        rule = DecisionRule(
            kind=DecisionRuleKind.BAYESIAN,
            expression="posterior odds large => support",
            params={"other": 1.0},  # 'min_odds' absent (params non-empty so it validates)
        )
        verdict = engine.evaluate(rule, _results(_evidence_item(_posterior_result(0.95))))
        assert verdict.direction == BearingDirection.INCONCLUSIVE
        assert "min_odds" in verdict.confidence.basis.lower()

    def test_confidence_type_is_posterior_with_value_equal_posterior(self, engine):
        """Decision 5: bayesian -> POSTERIOR; value == Result.posterior."""
        verdict = engine.evaluate(
            _bayesian_rule(10.0), _results(_evidence_item(_posterior_result(0.95)))
        )
        assert verdict.confidence.type == ConfidenceType.POSTERIOR
        assert verdict.confidence.value == pytest.approx(0.95)
        assert verdict.confidence.level is None

    def test_basis_quotes_odds_and_min_odds(self, engine):
        """D2: basis quotes the computed odds and the min_odds threshold."""
        basis = engine.evaluate(
            _bayesian_rule(10.0), _results(_evidence_item(_posterior_result(0.95)))
        ).confidence.basis.lower()
        assert "odds" in basis
        assert "10" in basis

    def test_aggregation_latest_is_default(self, engine):
        """Decision 7: default combine='latest' uses the most-recent posterior.
        Latest 0.5 (odds 1) is neutral even though an earlier 0.95 supported."""
        first = _evidence_item(_posterior_result(0.95), eid="ev-001")
        second = _evidence_item(_posterior_result(0.5), eid="ev-002")
        verdict = engine.evaluate(_bayesian_rule(10.0), _results(first, second))
        assert verdict.direction == BearingDirection.NEUTRAL

    def test_weighted_mean_aggregation(self, engine):
        """Decision 6 + 7: combine='mean' takes the weighted mean of posteriors.
        Equal-weight mean(0.95, 0.5) = 0.725 -> odds ~2.6 -> neutral (< 10)."""
        rule = _bayesian_rule(10.0, combine="mean")
        first = _evidence_item(_posterior_result(0.95), eid="ev-001", weight=1.0)
        second = _evidence_item(_posterior_result(0.5), eid="ev-002", weight=1.0)
        verdict = engine.evaluate(rule, _results(first, second))
        assert verdict.direction == BearingDirection.NEUTRAL


# ===========================================================================
# INTERVAL (Decision 2 + 3): Result.ci=[lo,hi] vs null_value from params.
# support_side semantics: "above" => CI entirely above null supports;
# "below" => CI entirely below null supports; "excludes" => CI entirely on
# either side (excluding null) supports. CI contains null -> neutral.
# Confidence: CREDENCE, value from CI position/width vs null.
# ===========================================================================

def _interval_rule(null_value: float = 0.0, support_side: str = "excludes", **extra) -> DecisionRule:
    params = {"null_value": null_value, "support_side": support_side}
    params.update(extra)
    return DecisionRule(
        kind=DecisionRuleKind.INTERVAL,
        expression=f"95% CI {support_side} {null_value} => support",
        params=params,
    )


class TestInterval:
    def test_supports_when_ci_excludes_null_on_support_side(self, engine):
        """CI [0.2, 0.8] excludes null 0 -> supports (support_side='excludes')."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "excludes"), _results(_evidence_item(_ci_result(0.2, 0.8)))
        )
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_neutral_when_ci_contains_null(self, engine):
        """CI [-0.3, 0.5] contains null 0 -> neutral (the rule's 'includes => null')."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "excludes"), _results(_evidence_item(_ci_result(-0.3, 0.5)))
        )
        assert verdict.direction == BearingDirection.NEUTRAL

    def test_refutes_when_ci_on_refute_side(self, engine):
        """support_side='above': CI [-0.8, -0.2] is entirely below null -> refutes."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "above"), _results(_evidence_item(_ci_result(-0.8, -0.2)))
        )
        assert verdict.direction == BearingDirection.REFUTES

    def test_supports_above_when_ci_above_null(self, engine):
        """support_side='above': CI [0.2, 0.8] entirely above null -> supports."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "above"), _results(_evidence_item(_ci_result(0.2, 0.8)))
        )
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_supports_below_when_ci_below_null(self, engine):
        """support_side='below': CI [-0.8, -0.2] entirely below null -> supports."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "below"), _results(_evidence_item(_ci_result(-0.8, -0.2)))
        )
        assert verdict.direction == BearingDirection.SUPPORTS

    def test_inconclusive_when_ci_missing(self, engine):
        """D1/D3: ci absent -> inconclusive, never a guessed interval."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "excludes"),
            _results(_evidence_item(Result(type="quantitative"))),  # ci None
        )
        assert verdict.direction == BearingDirection.INCONCLUSIVE

    def test_inconclusive_when_null_value_missing(self, engine):
        """Decision 3 / D1: null_value absent -> inconclusive with basis naming the
        missing key. The engine MUST NOT assume 0."""
        rule = DecisionRule(
            kind=DecisionRuleKind.INTERVAL,
            expression="95% CI excludes the null => support",
            params={"support_side": "excludes"},  # 'null_value' absent
        )
        verdict = engine.evaluate(rule, _results(_evidence_item(_ci_result(0.2, 0.8))))
        assert verdict.direction == BearingDirection.INCONCLUSIVE
        assert "null_value" in verdict.confidence.basis.lower()

    def test_confidence_type_is_credence_with_value(self, engine):
        """Decision 5: interval -> CREDENCE; numeric value in [0,1] from CI vs null."""
        verdict = engine.evaluate(
            _interval_rule(0.0, "excludes"), _results(_evidence_item(_ci_result(0.2, 0.8)))
        )
        assert verdict.confidence.type == ConfidenceType.CREDENCE
        assert verdict.confidence.value is not None
        assert 0.0 <= verdict.confidence.value <= 1.0
        assert verdict.confidence.level is None

    def test_basis_quotes_ci_and_null_value(self, engine):
        """D2: basis quotes the CI used and the null value."""
        basis = engine.evaluate(
            _interval_rule(0.0, "excludes"), _results(_evidence_item(_ci_result(0.2, 0.8)))
        ).confidence.basis.lower()
        assert "0.2" in basis and "0.8" in basis  # the CI
        assert "null" in basis  # the null value reference

    def test_narrower_ci_farther_from_null_gives_higher_confidence(self, engine):
        """Confidence rises with distance from null and narrowness of the CI."""
        near_wide = engine.evaluate(
            _interval_rule(0.0, "excludes"), _results(_evidence_item(_ci_result(0.01, 0.6)))
        ).confidence.value
        far_narrow = engine.evaluate(
            _interval_rule(0.0, "excludes"), _results(_evidence_item(_ci_result(0.5, 0.6)))
        ).confidence.value
        assert far_narrow > near_wide

    def test_aggregation_latest_is_default(self, engine):
        """Decision 7: default combine='latest' uses the most-recent CI. Latest CI
        [-0.3, 0.5] contains null -> neutral even though earlier [0.2, 0.8] supported."""
        first = _evidence_item(_ci_result(0.2, 0.8), eid="ev-001")
        second = _evidence_item(_ci_result(-0.3, 0.5), eid="ev-002")
        verdict = engine.evaluate(_interval_rule(0.0, "excludes"), _results(first, second))
        assert verdict.direction == BearingDirection.NEUTRAL


# ===========================================================================
# Cross-cutting (D2): every numeric verdict carries a non-empty basis.
# ===========================================================================

class TestCrossCutting:
    @pytest.mark.parametrize(
        "rule, pair",
        [
            (_threshold_rule(">=", 0.5), _evidence_item(_point_result(0.9))),
            (_bayesian_rule(10.0), _evidence_item(_posterior_result(0.95))),
            (_interval_rule(0.0, "excludes"), _evidence_item(_ci_result(0.2, 0.8))),
        ],
        ids=["threshold", "bayesian", "interval"],
    )
    def test_basis_always_present(self, engine, rule, pair):
        """D2: every numeric Verdict has a non-empty basis."""
        verdict = engine.evaluate(rule, _results(pair))
        assert verdict.confidence.basis and verdict.confidence.basis.strip()

    @pytest.mark.parametrize(
        "rule, pair",
        [
            (_threshold_rule(">=", 0.5), _evidence_item(_point_result(0.9))),
            (_bayesian_rule(10.0), _evidence_item(_posterior_result(0.95))),
            (_interval_rule(0.0, "excludes"), _evidence_item(_ci_result(0.2, 0.8))),
        ],
        ids=["threshold", "bayesian", "interval"],
    )
    def test_emitted_type_matches_intended(self, engine, rule, pair):
        """D4 / Decision 5: the emitted Confidence.type equals
        intended_confidence_type(kind) for the numeric kinds."""
        verdict = engine.evaluate(rule, _results(pair))
        assert verdict.confidence.type == engine.intended_confidence_type(rule.kind)

    @pytest.mark.parametrize(
        "rule, pair",
        [
            (_threshold_rule(">=", 0.5), _evidence_item(_point_result(0.9))),
            (_bayesian_rule(10.0), _evidence_item(_posterior_result(0.95))),
            (_interval_rule(0.0, "excludes"), _evidence_item(_ci_result(0.2, 0.8))),
        ],
        ids=["threshold", "bayesian", "interval"],
    )
    def test_determinism_same_input_same_verdict(self, engine, rule, pair):
        """D5: a fixed (rule, results) input yields the same direction + value."""
        results = _results(pair)
        v1 = engine.evaluate(rule, results)
        v2 = engine.evaluate(rule, results)
        assert v1.direction == v2.direction
        assert v1.confidence.value == v2.confidence.value


# ===========================================================================
# proof / qualitative are NOT implemented in Phase D2: they remain stubs that
# return INCONCLUSIVE with a basis marking the stub state. Guard that D2 did not
# accidentally implement them.
# ===========================================================================

class TestNonNumericRemainStubs:
    def test_proof_remains_stub(self, engine):
        rule = DecisionRule(
            kind=DecisionRuleKind.PROOF,
            expression="verified derivation => support; counterexample => refute",
        )
        verdict = engine.evaluate(rule, _results())
        assert verdict.direction == BearingDirection.INCONCLUSIVE
        assert verdict.confidence.type == ConfidenceType.GRADED
        assert verdict.confidence.level == ConfidenceLevel.NONE
        basis = verdict.confidence.basis.lower()
        assert "stub" in basis or "not yet implemented" in basis

    def test_qualitative_remains_stub(self, engine):
        rule = DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE,
            expression="reviewer judges the construction novel and correct => support",
        )
        verdict = engine.evaluate(rule, _results())
        assert verdict.direction == BearingDirection.INCONCLUSIVE
        assert verdict.confidence.type == ConfidenceType.GRADED
        assert verdict.confidence.level == ConfidenceLevel.NONE
        basis = verdict.confidence.basis.lower()
        assert "stub" in basis or "not yet implemented" in basis
