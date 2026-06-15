"""
sci-adk DecisionEngine (Phase D1 skeleton).

The DecisionEngine turns the research *record* (Evidence bearing on a
hypothesis) into *belief* (a direction + confidence) according to the
per-Spec ``DecisionRule`` the user pre-registered -- never against a global
constant. This closes the gap described in design/decision-engine.md §1, where
``ClaimUpdater`` currently ignores ``hypothesis.decision_rule`` and reduces every
result to a vote count.

Spec: design/decision-engine.md (CONFIRMED 2026-06-15)
    - §2.1   signature: evaluate(rule, results) -> Verdict
    - §2.2   dispatcher: match on rule.kind -> one _eval_<kind> handler per kind
    - §2.3   invariants D1-D8 (the handler contract; see DecisionEngine docstring)
    - Decision 1   dispatcher + file location (this module lives in loop/)
    - Decision 5   kind -> ConfidenceType mapping

Phase scope (design/decision-engine.md §6):
    This module now implements **Phase D2 (numeric kinds)**: the ``threshold``,
    ``bayesian``, and ``interval`` handlers perform real numeric evaluation per
    Decisions 2, 3, 5, 6, 7, reading every number from ``rule.params`` (D1). The
    ``proof`` and ``qualitative`` handlers remain **Phase D1 stubs** (their
    LLM-judge / human routing is Phase D3, Decision 4). This module still does
    not touch ``ClaimUpdater`` (Phase D4) -- the engine returns a ``Verdict`` and
    nothing consumes it yet beyond tests.

Two-environment note (design/tool-policy.md, §1 of the design doc):
    This is sci-adk *product* runtime code. No hardcoded success metric enters
    the engine -- every threshold it will ever use (Phase D2+) comes from
    ``DecisionRule.params`` of the Spec under evaluation (D1).

A note on the stub Confidence (D8 vs Decision 5):
    D8 forbids fabricating a *numeric* verdict to appear decisive, and the
    ``Confidence`` validators (claim.py:143-156) reject a credence/posterior
    type that carries no numeric ``value`` and a graded type that carries no
    ``level``. An unresolved stub has no honest numeric value, so emitting the
    Decision-5 *numeric* type (credence/posterior) on a stub would force a
    fabricated number -- exactly the D8 violation. The faithful Phase-D1
    encoding of "unresolved, no numeric verdict yet" is therefore
    ``ConfidenceType.GRADED`` with ``ConfidenceLevel.NONE`` (which literally
    means "no confidence", claim.py:92) and a basis that names the kind and
    marks the stub. The Decision-5 numeric type per kind is recorded separately
    via ``intended_confidence_type`` so Phase D2 can wire it in without
    guessing, and it is verified by the tests today.
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from pydantic import BaseModel, Field

from sci_adk.core.claim import Confidence, ConfidenceLevel, ConfidenceType
from sci_adk.core.evidence import Bearing, BearingDirection, EvidenceItem, Result
from sci_adk.core.spec import DecisionRule, DecisionRuleKind


class Verdict(BaseModel):
    """
    The engine's answer for one hypothesis: a direction + a confidence.

    Verdict is a transient, loop-level result value -- NOT a persisted core
    type (design/decision-engine.md §2.1). It is frozen because, once computed
    for a fixed ``(rule, results)`` input, it must not be mutated (it mirrors
    the determinism intent of D5). ``ClaimUpdater`` consumes a Verdict and
    assembles / updates the persisted ``Claim`` from it (Decision 1 / Phase D4).

    Attributes:
        direction: supports | refutes | neutral | inconclusive (reused from
            evidence.py; all four are first-class outcomes, D3).
        confidence: type + value/level + REQUIRED basis (reused from claim.py;
            basis is the load-bearing field, D2 / C3).
    """

    model_config = {"frozen": True}

    direction: BearingDirection = Field(..., description="Direction the evidence points")
    confidence: Confidence = Field(..., description="Confidence with a required basis")


class EvidenceForHypothesis(BaseModel):
    """
    A thin, pre-filtered view of the Evidence bearing on ONE hypothesis.

    This is a minimal wrapper, NOT a new persisted type
    (design/decision-engine.md §2.1). The caller (``ClaimUpdater``) pre-filters
    the append-only Evidence log down to the ``(EvidenceItem, Bearing)`` pairs
    whose ``Bearing.target_id`` equals the hypothesis id, exactly as it already
    does (claim_updater.py:67-71). The engine never reaches into the full log.

    Attributes:
        pairs: the ``(EvidenceItem, Bearing)`` pairs bearing on the hypothesis.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    pairs: List[Tuple[EvidenceItem, Bearing]] = Field(
        default_factory=list,
        description="(EvidenceItem, Bearing) pairs bearing on one hypothesis",
    )


# Decision 5 (design/decision-engine.md §2.3 D4 + Decision 5 table): the
# ConfidenceType the engine is intended to emit per rule kind once numeric
# evaluation lands (Phase D2). The stub does not emit these numeric types yet
# (see the module docstring's D8-vs-Decision-5 note); this mapping pins the
# contract so Phase D2 wiring is unambiguous.
_INTENDED_CONFIDENCE_TYPE: dict[DecisionRuleKind, ConfidenceType] = {
    DecisionRuleKind.THRESHOLD: ConfidenceType.CREDENCE,
    DecisionRuleKind.BAYESIAN: ConfidenceType.POSTERIOR,
    DecisionRuleKind.INTERVAL: ConfidenceType.CREDENCE,
    DecisionRuleKind.PROOF: ConfidenceType.GRADED,
    DecisionRuleKind.QUALITATIVE: ConfidenceType.GRADED,
}


class DecisionEngine:
    """
    Evaluates a hypothesis's pre-registered ``DecisionRule`` against the
    Evidence bearing on it, returning a ``Verdict`` (direction + confidence).

    The engine holds NO state and NO numeric constants (D1): every number it
    will ever use comes from ``rule.params`` of the Spec under evaluation. The
    single public method ``evaluate`` dispatches on ``rule.kind`` to one private
    ``_eval_<kind>`` handler; each handler is a pure
    ``(rule, EvidenceForHypothesis) -> Verdict`` function (§2.2, Decision 1).

    Handler contract -- engine invariants D1-D8 (design/decision-engine.md §2.3).
    These hold for every handler. In Phase D1 the handlers are stubs, so only
    the structural invariants (D1 no-constant, D2 basis, D3 inconclusive is a
    verdict, D4 type-follows-kind, D8 no fabrication) are exercised; numeric
    enforcement (D5 determinism on numbers, D6 rule-scoped aggregation, D7 no
    Spec mutation in the numeric path) lands in Phase D2/D4.

        D1 (rule authority).      direction + confidence derive only from
                                  ``rule`` and the supplied results; no numeric
                                  constant absent from ``rule.params`` is used.
                                  A missing required threshold yields
                                  ``inconclusive`` with a basis naming the gap,
                                  never a substituted default.
        D2 (basis always present).Every ``Verdict.confidence.basis`` is
                                  non-empty and states which rule produced it
                                  (mirrors C3).
        D3 (null is a verdict).   refutes / neutral / inconclusive are complete,
                                  first-class verdicts, never errors or "stuck"
                                  states (mirrors E2).
        D4 (kind -> Confidence.type). The emitted ``Confidence.type`` is a
                                  function of ``rule.kind`` (Decision 5); the
                                  engine never invents a type the kind does not
                                  imply.
        D5 (determinism).         For a fixed ``(rule, results)`` input,
                                  ``evaluate`` returns the same direction and the
                                  same numeric value/level. Only *new* Evidence
                                  moves a verdict.
        D6 (aggregation is rule-scoped). When several results bear on one
                                  hypothesis, the handler for ``rule.kind``
                                  defines how they combine (Decision 7); there is
                                  no engine-wide aggregation policy.
        D7 (no Spec mutation).    The engine reads the frozen ``DecisionRule``;
                                  it never amends a Spec (S5).
        D8 (escalation over fabrication). For kinds that cannot be reduced to a
                                  formula (proof / qualitative), the engine routes
                                  to an LLM-judge and/or human checkpoint
                                  (Decision 4); it never fabricates a numeric
                                  verdict to appear decisive. An unresolved
                                  judgment yields ``inconclusive`` with a basis
                                  requesting the checkpoint.
    """

    def evaluate(self, rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict:
        """
        Dispatch on ``rule.kind`` to the matching ``_eval_<kind>`` handler.

        Args:
            rule: the hypothesis's frozen ``DecisionRule`` (the sole authority
                for direction and confidence, D1).
            results: the pre-filtered ``(EvidenceItem, Bearing)`` pairs bearing
                on the hypothesis.

        Returns:
            A ``Verdict``: direction + confidence (with a required basis, D2).
        """
        # @MX:ANCHOR: [AUTO] sole public entry that turns the record into belief
        # @MX:REASON: [AUTO] every Claim's direction+confidence flows through this
        #   dispatch; ClaimUpdater (Phase D4) and all engine tests call it, and the
        #   per-Spec DecisionRule is its only authority (D1). Changing the (rule,
        #   results) -> Verdict contract ripples to every downstream Claim.
        match rule.kind:
            case DecisionRuleKind.THRESHOLD:
                return self._eval_threshold(rule, results)
            case DecisionRuleKind.BAYESIAN:
                return self._eval_bayesian(rule, results)
            case DecisionRuleKind.INTERVAL:
                return self._eval_interval(rule, results)
            case DecisionRuleKind.PROOF:
                return self._eval_proof(rule, results)
            case DecisionRuleKind.QUALITATIVE:
                return self._eval_qualitative(rule, results)

    def intended_confidence_type(self, kind: DecisionRuleKind) -> ConfidenceType:
        """
        Return the ``ConfidenceType`` the engine is intended to emit for ``kind``
        once numeric evaluation lands (Decision 5).

        Phase D1 stubs do not yet emit these numeric types (see the module
        docstring's D8-vs-Decision-5 note); this accessor pins the mapping so it
        is verifiable now and so Phase D2 can wire it in without guessing (D4).
        """
        return _INTENDED_CONFIDENCE_TYPE[kind]

    # ------------------------------------------------------------------
    # Phase D2 numeric handlers (threshold / bayesian / interval).
    #
    # Each reads its statistic from the relevant ``Result`` field and its
    # thresholds from ``rule.params`` ONLY (D1): no numeric constant absent from
    # ``params`` is ever used, and a missing required key yields ``inconclusive``
    # with a basis naming the gap -- never a substituted default. Multiple results
    # are combined first, then the rule is applied once (Decision 7, D6);
    # ``Bearing.weight`` (default 1.0) is the per-result multiplier (Decision 6).
    # The emitted ``Confidence.type`` follows Decision 5 (threshold/interval ->
    # credence, bayesian -> posterior), matching ``intended_confidence_type``.
    # ------------------------------------------------------------------

    # Supported comparison operators for the threshold kind. Each maps to a pure
    # predicate; the operator itself comes from ``params`` (D1), not a constant.
    _THRESHOLD_OPS: dict[str, Callable[[float, float], bool]] = {
        ">=": lambda x, t: x >= t,
        ">": lambda x, t: x > t,
        "<=": lambda x, t: x <= t,
        "<": lambda x, t: x < t,
        "==": lambda x, t: x == t,
        "!=": lambda x, t: x != t,
    }

    def _eval_threshold(self, rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict:
        """
        Compare a combined statistic to a params threshold (Decision 2).

        Reads ``Result.point`` (the statistic). Params:
        ``{"statistic": "point", "op": ">=", "value": <x>}`` plus an optional
        ``{"combine": "latest"|"mean"|"pool"}`` (Decision 7, default ``latest``).
        Condition met -> ``supports``; cleanly not met -> ``refutes``; a missing
        operand or required param -> ``inconclusive`` (D1/D3). Confidence is
        ``credence`` with a margin-based value in [0, 1].
        """
        params = rule.params or {}

        op_token = params.get("op")
        if op_token is None:
            return self._inconclusive(rule, "missing required param 'op'")
        if "value" not in params:
            return self._inconclusive(rule, "missing required param 'value'")
        op = self._THRESHOLD_OPS.get(str(op_token))
        if op is None:
            return self._inconclusive(
                rule, f"unsupported op '{op_token}' (expected one of {sorted(self._THRESHOLD_OPS)})"
            )
        try:
            threshold = float(params["value"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self._inconclusive(rule, f"param 'value' is not numeric: {params['value']!r}")

        combine = self._combine_method(rule)
        if combine is None:
            return self._inconclusive(
                rule, f"unsupported combine '{params.get('combine')}' (expected latest|mean|pool)"
            )

        statistic = self._combine_statistic(results, "point", combine)
        if statistic is None:
            return self._inconclusive(
                rule, "no result carries a 'point' statistic to compare against the threshold"
            )

        met = op(statistic, threshold)
        direction = BearingDirection.SUPPORTS if met else BearingDirection.REFUTES

        # Margin-based credence: how decisively the statistic clears (or misses)
        # the threshold. Larger |statistic - threshold| -> higher confidence. The
        # squashing constant below is a *confidence-shaping* scalar, NOT a metric
        # threshold (it never decides direction -- direction is purely op(stat,
        # threshold)); D1 governs metric constants, which all come from params.
        margin = abs(statistic - threshold)
        value = self._squash(margin)
        basis = (
            f"threshold rule: statistic 'point'={statistic:.6g} {op_token} {threshold:.6g} "
            f"is {'met' if met else 'not met'} (combine='{combine}', margin={margin:.6g})"
        )
        return self._credence_verdict(direction, value, basis)

    def _eval_bayesian(self, rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict:
        """
        Compare combined posterior odds to a params threshold (Decision 2).

        Reads ``Result.posterior`` (a probability in [0, 1]); converts to odds
        ``p/(1-p)``. Params: ``{"min_odds": <k>}`` plus optional ``combine``
        (default ``latest``). odds >= k -> ``supports``; odds <= 1/k -> ``refutes``;
        between -> ``neutral``. A missing ``min_odds`` or posterior ->
        ``inconclusive`` (D1/D3). Confidence is ``posterior`` with
        ``value = combined posterior``.
        """
        params = rule.params or {}

        if "min_odds" not in params:
            return self._inconclusive(rule, "missing required param 'min_odds'")
        try:
            min_odds = float(params["min_odds"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self._inconclusive(rule, f"param 'min_odds' is not numeric: {params['min_odds']!r}")
        if min_odds <= 0:
            return self._inconclusive(rule, f"param 'min_odds' must be positive, got {min_odds:.6g}")

        combine = self._combine_method(rule)
        if combine is None:
            return self._inconclusive(
                rule, f"unsupported combine '{params.get('combine')}' (expected latest|mean|pool)"
            )

        posterior = self._combine_statistic(results, "posterior", combine)
        if posterior is None:
            return self._inconclusive(
                rule, "no result carries a 'posterior' probability to convert to odds"
            )

        # Convert probability to odds. p == 1 is unbounded support; p == 0 is
        # unbounded evidence against. Both are decisive at any finite min_odds.
        if posterior >= 1.0:
            odds = math.inf
        elif posterior <= 0.0:
            odds = 0.0
        else:
            odds = posterior / (1.0 - posterior)

        if odds >= min_odds:
            direction = BearingDirection.SUPPORTS
        elif odds <= 1.0 / min_odds:
            direction = BearingDirection.REFUTES
        else:
            direction = BearingDirection.NEUTRAL

        odds_text = "inf" if math.isinf(odds) else f"{odds:.6g}"
        basis = (
            f"bayesian rule: posterior={posterior:.6g} -> odds={odds_text} vs "
            f"min_odds={min_odds:.6g} (supports if odds>={min_odds:.6g}, refutes if "
            f"odds<={1.0 / min_odds:.6g}); combine='{combine}'"
        )
        # Decision 5: bayesian -> POSTERIOR, value == the (combined) posterior.
        return Verdict(
            direction=direction,
            confidence=Confidence(
                type=ConfidenceType.POSTERIOR,
                value=posterior,
                basis=basis,
            ),
        )

    def _eval_interval(self, rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict:
        """
        Test a combined confidence/credible interval against a params null value
        (Decision 2 + Decision 3).

        Reads ``Result.ci = [lower, upper]``. The null value comes from
        ``params["null_value"]`` (Decision 3 -- never assumed 0); ``support_side``
        selects the semantics:

        - ``"above"``: CI entirely above null -> ``supports``; entirely below ->
          ``refutes``.
        - ``"below"``: CI entirely below null -> ``supports``; entirely above ->
          ``refutes``.
        - ``"excludes"``: CI entirely on either side of null -> ``supports`` (a
          two-sided exclusion has no distinct refute side).

        A CI that contains the null -> ``neutral`` (the rule's "includes => null").
        Missing ``null_value`` / ``ci`` -> ``inconclusive`` (D1/D3). Confidence is
        ``credence`` from the CI's distance from null relative to its width.
        """
        params = rule.params or {}

        if "null_value" not in params:
            return self._inconclusive(rule, "missing required param 'null_value'")
        try:
            null_value = float(params["null_value"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self._inconclusive(
                rule, f"param 'null_value' is not numeric: {params['null_value']!r}"
            )
        support_side = str(params.get("support_side", "excludes"))
        if support_side not in ("excludes", "above", "below"):
            return self._inconclusive(
                rule, f"unsupported support_side '{support_side}' (expected excludes|above|below)"
            )

        combine = self._combine_method(rule)
        if combine is None:
            return self._inconclusive(
                rule, f"unsupported combine '{params.get('combine')}' (expected latest|mean|pool)"
            )

        ci = self._combine_interval(results, combine)
        if ci is None:
            return self._inconclusive(
                rule, "no result carries a 'ci' interval to test against the null value"
            )
        lower, upper = ci

        contains_null = lower <= null_value <= upper
        if contains_null:
            direction = BearingDirection.NEUTRAL
        else:
            entirely_above = lower > null_value
            if support_side == "above":
                direction = BearingDirection.SUPPORTS if entirely_above else BearingDirection.REFUTES
            elif support_side == "below":
                direction = BearingDirection.SUPPORTS if not entirely_above else BearingDirection.REFUTES
            else:  # "excludes": either side of the null is support, no refute side
                direction = BearingDirection.SUPPORTS

        value = self._interval_confidence(lower, upper, null_value, contains_null)
        side_text = "contains" if contains_null else ("above" if lower > null_value else "below")
        basis = (
            f"interval rule: CI=[{lower:.6g}, {upper:.6g}] {side_text} null_value={null_value:.6g} "
            f"(support_side='{support_side}', combine='{combine}')"
        )
        return self._credence_verdict(direction, value, basis)

    # ------------------------------------------------------------------
    # Phase D1 stub handlers (non-numeric kinds; routing is Phase D3).
    # ------------------------------------------------------------------

    def _eval_proof(self, rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict:
        # @MX:TODO: [AUTO] Phase D3 - route to LLM-judge + human spot-check (Decision 4)
        return self._stub_verdict(rule)

    def _eval_qualitative(self, rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict:
        # @MX:TODO: [AUTO] Phase D3 - route to LLM-judge with human fallback (Decision 4)
        return self._stub_verdict(rule)

    @staticmethod
    def _stub_verdict(rule: DecisionRule) -> Verdict:
        """
        Build the shared Phase-D1 stub verdict for a rule.

        Returns ``inconclusive`` (D3) with a graded ``NONE`` confidence -- the
        honest "no verdict yet" encoding that fabricates no number (D8) -- and a
        basis naming the rule kind and marking the stub (D2). See the module
        docstring for why GRADED/NONE is used rather than the Decision-5 numeric
        type on a stub.
        """
        return Verdict(
            direction=BearingDirection.INCONCLUSIVE,
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.NONE,
                basis=(
                    f"Phase D1 stub for '{rule.kind.value}' decision rule: "
                    f"not yet implemented (numeric/routing evaluation lands in a "
                    f"later phase); no verdict can be drawn from the record yet"
                ),
            ),
        )

    # ------------------------------------------------------------------
    # Shared numeric helpers (Decision 6 weight, Decision 7 aggregation, and the
    # confidence-shaping + verdict-building utilities). These hold NO metric
    # constant: thresholds always arrive via the handlers from ``rule.params``.
    # ------------------------------------------------------------------

    # The combine methods the engine knows (Decision 7). ``pool`` is currently a
    # MINIMAL implementation: it behaves like ``latest`` (no meta-analytic
    # pooling yet). This simplification is explicit per the Phase-D2 spec note
    # (design/decision-engine.md Decision 7) -- it is recorded here and surfaced
    # in the verdict basis (combine='pool'), never silently faked as real pooling.
    _COMBINE_METHODS = ("latest", "mean", "pool")

    def _combine_method(self, rule: DecisionRule) -> Optional[str]:
        """
        Resolve the combine method from ``params['combine']`` (Decision 7).

        Defaults to ``latest`` when absent (the most recent Evidence is the
        current best estimate). Returns ``None`` for an unrecognized method so the
        caller can return ``inconclusive`` rather than guess.
        """
        params = rule.params or {}
        combine = str(params.get("combine", "latest"))
        if combine not in self._COMBINE_METHODS:
            return None
        return combine

    @staticmethod
    def _weight(bearing: Bearing) -> float:
        """Decision 6: ``Bearing.weight`` as a multiplier, defaulting to 1.0."""
        return 1.0 if bearing.weight is None else float(bearing.weight)

    @staticmethod
    def _scalar_field(result: Result, field_name: str) -> Optional[float]:
        """Read a scalar statistic field from a Result, or None if absent."""
        value = getattr(result, field_name, None)
        return None if value is None else float(value)

    def _combine_statistic(
        self,
        results: EvidenceForHypothesis,
        field_name: str,
        combine: str,
    ) -> Optional[float]:
        """
        Combine a scalar ``Result`` statistic across all bearing results into one
        number, then the caller applies the rule once (Decision 7, D6).

        - ``latest``: the statistic from the most recently created EvidenceItem.
        - ``mean``: the weighted mean over all results carrying the statistic
          (weights from ``Bearing.weight``, default 1.0, Decision 6).
        - ``pool``: minimal -- treated as ``latest`` (see ``_COMBINE_METHODS``).

        Returns ``None`` when no bearing result carries the statistic, so the
        handler can return ``inconclusive`` (D1/D3) rather than substitute a value.
        """
        present = [
            (idx, item, bearing, self._scalar_field(item.result, field_name))
            for idx, (item, bearing) in enumerate(results.pairs)
        ]
        present = [(idx, item, bearing, val) for idx, item, bearing, val in present if val is not None]
        if not present:
            return None

        if combine == "mean":
            total_w = sum(self._weight(bearing) for _, _, bearing, _ in present)
            if total_w <= 0:
                return None
            return sum(self._weight(bearing) * val for _, _, bearing, val in present) / total_w

        # latest / pool: the statistic from the most recently created item. Ties on
        # created_at break toward the later sequence position (append/arrival
        # order), keeping the verdict deterministic (D5).
        _, _, _, latest_val = max(present, key=lambda t: (t[1].created_at, t[0]))
        return latest_val

    def _combine_interval(
        self,
        results: EvidenceForHypothesis,
        combine: str,
    ) -> Optional[Tuple[float, float]]:
        """
        Combine ``Result.ci`` intervals across bearing results into one interval
        (Decision 7, D6).

        - ``latest``: the CI from the most recently created EvidenceItem.
        - ``mean``: the weighted mean of the lower and upper bounds separately
          (weights from ``Bearing.weight``, default 1.0).
        - ``pool``: minimal -- treated as ``latest``.

        Returns ``None`` when no bearing result carries a CI.
        """
        present = [
            (idx, item, bearing, item.result.ci)
            for idx, (item, bearing) in enumerate(results.pairs)
            if item.result.ci is not None and len(item.result.ci) == 2
        ]
        if not present:
            return None

        if combine == "mean":
            total_w = sum(self._weight(bearing) for _, _, bearing, _ in present)
            if total_w <= 0:
                return None
            lower = sum(self._weight(bearing) * ci[0] for _, _, bearing, ci in present) / total_w
            upper = sum(self._weight(bearing) * ci[1] for _, _, bearing, ci in present) / total_w
            return (lower, upper)

        # latest / pool, with deterministic tie-break on sequence position (D5).
        _, _, _, latest_ci = max(present, key=lambda t: (t[1].created_at, t[0]))
        return (float(latest_ci[0]), float(latest_ci[1]))

    @staticmethod
    def _squash(margin: float) -> float:
        """
        Map a non-negative margin to a continuous credence in [0, 1).

        ``1 - exp(-margin)`` is monotone increasing in the margin, 0 at margin 0,
        and asymptotes to 1 -- giving "further past/short of the threshold ->
        higher confidence" (Decision 2) without any metric constant deciding the
        direction. This is confidence shaping only; direction is decided upstream
        by the rule's own op/params (D1).
        """
        return 1.0 - math.exp(-abs(margin))

    def _interval_confidence(
        self,
        lower: float,
        upper: float,
        null_value: float,
        contains_null: bool,
    ) -> float:
        """
        Credence for an interval verdict from the CI's distance from null relative
        to its width (Decision 2): a narrow CI far from null -> higher confidence.

        Distance is from the nearer endpoint to the null. When the CI contains the
        null the distance is 0, so confidence is 0 (genuinely uninformative about
        a directional effect). Width 0 (a degenerate point CI) yields confidence
        from the distance alone via the squash.
        """
        if contains_null:
            return 0.0
        distance = min(abs(lower - null_value), abs(upper - null_value))
        width = abs(upper - lower)
        # Distance-to-width ratio rewards tight intervals far from null; the raw
        # ratio is squashed to [0, 1). A zero-width CI collapses to the distance.
        ratio = distance / width if width > 0 else distance
        return self._squash(ratio)

    @staticmethod
    def _credence_verdict(direction: BearingDirection, value: float, basis: str) -> Verdict:
        """Assemble a CREDENCE verdict (Decision 5 for threshold/interval)."""
        return Verdict(
            direction=direction,
            confidence=Confidence(
                type=ConfidenceType.CREDENCE,
                value=value,
                basis=basis,
            ),
        )

    @staticmethod
    def _inconclusive(rule: DecisionRule, reason: str) -> Verdict:
        """
        Build an ``inconclusive`` verdict for a numeric kind that cannot evaluate
        (D1/D3): a missing required param, a missing statistic, or no results.

        Uses GRADED/NONE confidence -- the honest "no numeric verdict" encoding
        that fabricates no value (D8) -- with a basis that names the rule kind and
        the specific reason (so a missing key is legible). This mirrors the stub
        verdict's encoding but carries a precise, evaluation-time reason.
        """
        return Verdict(
            direction=BearingDirection.INCONCLUSIVE,
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.NONE,
                basis=f"{rule.kind.value} rule inconclusive: {reason}",
            ),
        )


__all__ = [
    "Verdict",
    "EvidenceForHypothesis",
    "DecisionEngine",
]
