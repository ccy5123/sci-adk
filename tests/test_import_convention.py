"""
Regression guard for the unified import convention.

Context: the repo previously mixed two import roots -- source modules used
``from src.sci_adk...`` while tests used ``from sci_adk...`` (pythonpath=src).
Because ``src.sci_adk.core.claim`` and ``sci_adk.core.claim`` are two distinct
module objects loaded from the SAME file, each defined its own ``Confidence``
class. A ``Confidence`` instance produced inside an engine module (imported one
way) therefore failed ``isinstance(..., Confidence)`` against the class imported
the other way -- the "duplicate-identity trap".

The fix normalized every import to the single ``sci_adk.*`` root. This test
locks that fix: it asserts the ``Confidence`` class used inside the engine's
module IS the exact same object as the one the test imports, and that a real
Verdict's confidence passes ``isinstance``. Under the old split this test would
have FAILED (two distinct class objects); under the unified convention it PASSES.
"""

import pytest

from sci_adk.core.claim import Confidence
from sci_adk.core.spec import DecisionRule, DecisionRuleKind
from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
import sci_adk.loop.decision_engine as decision_engine_mod


def test_confidence_class_identity_is_unified():
    """The engine module and the test resolve the SAME ``Confidence`` object.

    This is the core anti-regression assertion: a duplicate-module split would
    bind two distinct class objects under the same name. ``is`` makes that
    failure observable, where ``isinstance`` alone could be fooled by structural
    equality.
    """
    assert decision_engine_mod.Confidence is Confidence


def test_verdict_confidence_passes_isinstance():
    """A Verdict built by DecisionEngine carries a genuine ``Confidence``.

    The cross-boundary ``isinstance`` check below is exactly what broke under
    the dual-identity trap; it must hold now that imports are unified.
    """
    engine = DecisionEngine()
    rule = DecisionRule(
        kind=DecisionRuleKind.QUALITATIVE,
        expression="reviewer judges the construction novel and correct => support",
    )
    verdict = engine.evaluate(rule, EvidenceForHypothesis(pairs=[]))

    assert isinstance(verdict.confidence, Confidence) is True
    # And the instance's own class is the unified class object, not a twin.
    assert type(verdict.confidence) is Confidence
