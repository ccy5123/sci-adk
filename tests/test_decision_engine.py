"""
Unit tests for the DecisionEngine skeleton (Phase D1).

Spec: design/decision-engine.md (CONFIRMED 2026-06-15), focus on
    - §2.1 / §2.2: evaluate(rule, results) -> Verdict; dispatch on rule.kind
    - §2.3: engine invariants D1-D8 (the handler contract)
    - Decision 1: dispatcher + five private _eval_<kind> handlers in loop/
    - Decision 5: kind -> ConfidenceType mapping (the *intended* type per kind)

These tests assert the engine's *routing + structural* contract, exercised here
with an EMPTY results view (no statistics to evaluate). They are deliberately
phase-robust: they hold both for the original Phase D1 skeleton and after Phase
D2 implemented the numeric kinds, because with no results every kind still
returns an INCONCLUSIVE verdict (numeric kinds: "no statistic"; proof/qualitative:
stub). Numeric semantics over real results live in test_decision_engine_numeric.py.

    (a) evaluate routes each of the 5 DecisionRuleKind values to its handler
        (the returned basis identifies the kind);
    (b) every kind yields Verdict.direction == BearingDirection.INCONCLUSIVE on an
        empty results view (D3);
    (c) Verdict.confidence.basis is non-empty and mentions the kind (D2);
    (d) the engine's *intended* Confidence.type per kind matches Decision 5;
    (e) no kind fabricates a numeric value on an empty/unresolved view (D8): no
        credence/posterior value is invented when there is nothing to evaluate;
    (f) proof/qualitative still mark the Phase D1 stub state; numeric kinds with
        no results mark the unresolved (inconclusive) state instead.
"""

import pytest

from sci_adk.core.spec import DecisionRule, DecisionRuleKind
from sci_adk.core.evidence import BearingDirection
from sci_adk.core.claim import ConfidenceType

from sci_adk.loop.decision_engine import (
    DecisionEngine,
    EvidenceForHypothesis,
    Verdict,
)


# ---------------------------------------------------------------------------
# Helpers: build a minimal VALID DecisionRule per kind using the real
# constructors. threshold/bayesian/interval REQUIRE non-empty params (Decision 3
# added INTERVAL to the required-params validator set); proof/qualitative do not
# require params.
# ---------------------------------------------------------------------------

def _rule(kind: DecisionRuleKind) -> DecisionRule:
    """Construct a minimal valid DecisionRule for the given kind."""
    if kind is DecisionRuleKind.THRESHOLD:
        return DecisionRule(
            kind=kind,
            expression="point >= 0.5 => support",
            params={"statistic": "point", "op": ">=", "value": 0.5},
        )
    if kind is DecisionRuleKind.BAYESIAN:
        return DecisionRule(
            kind=kind,
            expression="posterior odds > 10 => support",
            params={"min_odds": 10.0},
        )
    if kind is DecisionRuleKind.INTERVAL:
        # Decision 3 (design/decision-engine.md): interval rules now REQUIRE
        # params carrying the null value + support side. A bare interval rule no
        # longer validates (params are required for INTERVAL like THRESHOLD/BAYESIAN).
        return DecisionRule(
            kind=kind,
            expression="95% CI excludes 0 => support",
            params={"null_value": 0.0, "support_side": "excludes"},
        )
    if kind is DecisionRuleKind.PROOF:
        return DecisionRule(
            kind=kind,
            expression="verified derivation => support; counterexample => refute",
        )
    if kind is DecisionRuleKind.QUALITATIVE:
        return DecisionRule(
            kind=kind,
            expression="reviewer judges the construction novel and correct => support",
        )
    raise AssertionError(f"unhandled kind in test helper: {kind}")


# Decision 5 mapping (design/decision-engine.md §2.3 D4 + Decision 5 table):
# the *intended* ConfidenceType the engine will emit per kind once numeric
# evaluation lands in Phase D2.
_DECISION5_INTENDED_TYPE = {
    DecisionRuleKind.THRESHOLD: ConfidenceType.CREDENCE,
    DecisionRuleKind.BAYESIAN: ConfidenceType.POSTERIOR,
    DecisionRuleKind.INTERVAL: ConfidenceType.CREDENCE,
    DecisionRuleKind.PROOF: ConfidenceType.GRADED,
    DecisionRuleKind.QUALITATIVE: ConfidenceType.GRADED,
}

_ALL_KINDS = list(DecisionRuleKind)


@pytest.fixture
def engine() -> DecisionEngine:
    return DecisionEngine()


@pytest.fixture
def empty_results() -> EvidenceForHypothesis:
    """A Phase-D1 stub ignores results; an empty view is a valid input."""
    return EvidenceForHypothesis(pairs=[])


# ---------------------------------------------------------------------------
# (a) Routing: each kind reaches its own handler. We assert this through the
# observable contract (the basis names the kind) AND by spying on the private
# handler to confirm dispatch actually called the right method.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS, ids=[k.value for k in _ALL_KINDS])
def test_evaluate_routes_to_handler_for_each_kind(engine, empty_results, kind):
    """evaluate dispatches each DecisionRuleKind to its corresponding handler."""
    handler_name = f"_eval_{kind.value}"
    assert hasattr(engine, handler_name), (
        f"engine must expose a private handler {handler_name} (Decision 1)"
    )

    calls = {"count": 0}
    original = getattr(engine, handler_name)

    def spy(rule, results):
        calls["count"] += 1
        return original(rule, results)

    setattr(engine, handler_name, spy)

    verdict = engine.evaluate(_rule(kind), empty_results)

    assert calls["count"] == 1, f"{handler_name} should be invoked exactly once"
    assert isinstance(verdict, Verdict)


@pytest.mark.parametrize("kind", _ALL_KINDS, ids=[k.value for k in _ALL_KINDS])
def test_basis_identifies_the_kind(engine, empty_results, kind):
    """D2: basis is non-empty and names the rule kind that produced the verdict."""
    verdict = engine.evaluate(_rule(kind), empty_results)
    basis = verdict.confidence.basis
    assert basis and basis.strip(), "D2: basis must be non-empty"
    assert kind.value in basis.lower(), (
        f"D2: basis must mention the rule kind '{kind.value}', got: {basis!r}"
    )


# ---------------------------------------------------------------------------
# (b) Every kind yields INCONCLUSIVE in the skeleton (D3: inconclusive is a
# first-class verdict, not an error).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS, ids=[k.value for k in _ALL_KINDS])
def test_stub_returns_inconclusive(engine, empty_results, kind):
    """Phase D1: every handler stub returns direction == INCONCLUSIVE (D3)."""
    verdict = engine.evaluate(_rule(kind), empty_results)
    assert verdict.direction == BearingDirection.INCONCLUSIVE


# ---------------------------------------------------------------------------
# (c) basis marks the unresolved (inconclusive) state explicitly (D8). Post-D3
# every handler is implemented: numeric kinds with no statistic, and proof/
# qualitative with no judge + no counterexample, all return an inconclusive
# verdict whose basis says so. The old Phase-D1 "stub" wording is gone.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS, ids=[k.value for k in _ALL_KINDS])
def test_basis_marks_unresolved_state(engine, empty_results, kind):
    """D8: an unresolved verdict (no results; for proof/qualitative also no judge)
    marks the inconclusive state in its basis -- and no 'stub' wording remains now
    that every handler is implemented (Phase D2 numeric + Phase D3 routing)."""
    basis = engine.evaluate(_rule(kind), empty_results).confidence.basis.lower()
    assert "inconclusive" in basis, (
        f"unresolved verdict should mark the inconclusive state, got: {basis!r}"
    )
    assert "stub" not in basis, (
        f"Phase-D1 stub wording should be gone post-D3, got: {basis!r}"
    )


# ---------------------------------------------------------------------------
# (d) Decision 5: the engine exposes the *intended* ConfidenceType per kind,
# and it matches the doc mapping. This pins the mapping now so Phase D2 wiring
# is verified, even though the stub does not yet emit a numeric value/level.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS, ids=[k.value for k in _ALL_KINDS])
def test_intended_confidence_type_matches_decision5(engine, kind):
    """Decision 5: kind -> ConfidenceType mapping is faithful to the doc."""
    assert engine.intended_confidence_type(kind) == _DECISION5_INTENDED_TYPE[kind]


# ---------------------------------------------------------------------------
# (e) D8: a stub must NOT fabricate a numeric verdict. No credence/posterior
# numeric value is invented on an unresolved stub.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS, ids=[k.value for k in _ALL_KINDS])
def test_stub_does_not_fabricate_numeric_value(engine, empty_results, kind):
    """D8: an unresolved stub carries no fabricated numeric confidence value."""
    confidence = engine.evaluate(_rule(kind), empty_results).confidence
    assert confidence.value is None, (
        "D8: stub must not invent a numeric credence/posterior value"
    )


# ---------------------------------------------------------------------------
# Verdict / EvidenceForHypothesis are transient loop-level values (doc §2.1):
# Verdict is frozen (a result type), and confidence always carries a basis (D2).
# ---------------------------------------------------------------------------

def test_verdict_is_frozen(engine, empty_results):
    """Verdict is a transient frozen result type (doc §2.1)."""
    verdict = engine.evaluate(_rule(DecisionRuleKind.THRESHOLD), empty_results)
    with pytest.raises(Exception):
        verdict.direction = BearingDirection.SUPPORTS  # type: ignore[misc]


def test_verdict_carries_a_confidence_with_basis(engine, empty_results):
    """Every Verdict carries a Confidence whose basis is required (D2 / C3).

    Note: this asserts the *structural* Confidence contract (a ConfidenceType
    plus a non-empty basis). The whole repo now uses a single import root
    (``from sci_adk...`` with ``pythonpath=src``), so core types resolve to one
    module object and the earlier dual-identity hazard no longer exists. These
    behavioral assertions remain because the D2/C3 contract is about structure,
    not class identity; see ``test_import_convention.py`` for the explicit
    identity guard that locks the unified convention.
    """
    confidence = engine.evaluate(_rule(DecisionRuleKind.QUALITATIVE), empty_results).confidence
    assert type(confidence).__name__ == "Confidence"
    # ConfidenceType membership check by value (consistent with the contract).
    assert confidence.type in set(ConfidenceType)
    assert confidence.basis.strip()
