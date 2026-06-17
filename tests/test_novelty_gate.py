"""
Novelty status derivation (RED-first, B-replace).

design/literature-acquisition.md §"Discovery trigger model" (High trigger): novelty
is no longer a run-HALT. It is a 1st-class revisable Claim derived by a RULE.

  ``derive_novelty_status(hypothesis, novelty_decisions) -> ClaimStatus``

returns ``ClaimStatus.SUPPORTED`` iff some ``NOVELTY_DECISION`` bound to
``hypothesis.id`` has outcome ``"found_nothing"`` (a recorded prior-art search that
returned nothing), else ``ClaimStatus.PROPOSED``.

Safety floor (the whole point): a ``found_something`` decision NEVER yields SUPPORTED
(it stays PROPOSED). No decision / a ``skipped`` decision -> PROPOSED. The predicate is
PURE: it never raises (the HALT is gone, replaced by a non-HALT compile-time checkpoint).

The predicate takes the novelty DECISION items (kind==NOVELTY_DECISION whose
``literature_decision.hypothesis_id == hypothesis.id``), NOT bearing evidence --
decisions carry ``bears_on=[]`` and never enter the DecisionEngine. It is decoupled
from the experiment verdict (no ``verdict_direction`` param).
"""

from __future__ import annotations

from sci_adk.core.claim import ClaimStatus
from sci_adk.core.evidence import (
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
    Provenance,
    Result,
)
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
)
from sci_adk.core.validity import derive_novelty_status


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _hyp(novelty: bool, hyp_id: str = "hyp-1") -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="first to show Z",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE, expression="clear and on-topic"
        ),
        novelty=novelty,
    )


def _novelty_decision(
    hyp_id: str, outcome: str, item_id: str = "evi-nov-1"
) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref=f"novelty:{outcome}"),
        result=Result(type="qualitative", finding=f"{outcome}: ..."),
        bears_on=[],
        literature_decision=LiteratureDecision(outcome=outcome, hypothesis_id=hyp_id),
    )


# --------------------------------------------------------------------------- #
# SUPPORTED iff a recorded found_nothing prior-art search
# --------------------------------------------------------------------------- #

def test_found_nothing_yields_supported():
    """A recorded prior-art search that returned nothing -> SUPPORTED novelty."""
    decisions = [_novelty_decision("hyp-1", "found_nothing")]
    assert derive_novelty_status(_hyp(True), decisions) == ClaimStatus.SUPPORTED


def test_no_decision_yields_proposed():
    """No novelty decision at all -> PROPOSED (the search has not been done)."""
    assert derive_novelty_status(_hyp(True), []) == ClaimStatus.PROPOSED


def test_skipped_decision_yields_proposed():
    """A skipped novelty decision does NOT support the claim (no search) -> PROPOSED."""
    decisions = [_novelty_decision("hyp-1", "skipped")]
    assert derive_novelty_status(_hyp(True), decisions) == ClaimStatus.PROPOSED


def test_found_something_never_yields_supported():
    """SAFETY FLOOR: a found_something decision (prior art exists) NEVER yields
    SUPPORTED; it stays PROPOSED (active refuted-promotion is deferred with render)."""
    decisions = [_novelty_decision("hyp-1", "found_something")]
    assert derive_novelty_status(_hyp(True), decisions) == ClaimStatus.PROPOSED


# --------------------------------------------------------------------------- #
# binding to the hypothesis id + fail-closed guards
# --------------------------------------------------------------------------- #

def test_found_nothing_for_another_hypothesis_does_not_support():
    """A found_nothing decision bound to a DIFFERENT hypothesis must not support this
    one (the decision is hypothesis-bound via its payload)."""
    decisions = [_novelty_decision("hyp-OTHER", "found_nothing")]
    assert derive_novelty_status(_hyp(True, "hyp-1"), decisions) == ClaimStatus.PROPOSED


def test_non_novelty_hypothesis_never_supported_even_with_found_nothing():
    """SAFETY-FLOOR HARDENING (defense-in-depth): a non-novelty hypothesis ALWAYS yields
    PROPOSED, even with a matching found_nothing decision -- the guard makes the code
    match the docstring so a mis-bound decision can never fabricate a SUPPORTED novelty
    claim for a hypothesis that is not a novelty claim."""
    decisions = [_novelty_decision("hyp-1", "found_nothing")]
    assert derive_novelty_status(_hyp(False), decisions) == ClaimStatus.PROPOSED


def test_found_nothing_alongside_found_something_still_supported():
    """If the record holds a found_nothing for this hypothesis, the presence of an
    additional found_something does not erase the recorded null search -> SUPPORTED."""
    decisions = [
        _novelty_decision("hyp-1", "found_something", item_id="evi-a"),
        _novelty_decision("hyp-1", "found_nothing", item_id="evi-b"),
    ]
    assert derive_novelty_status(_hyp(True), decisions) == ClaimStatus.SUPPORTED


def test_null_payload_does_not_support():
    """Fail-closed: a NOVELTY_DECISION whose payload is absent carries no outcome,
    so it must NOT support -> PROPOSED."""
    null_payload = EvidenceItem(
        id="evi-nov-null",
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref="novelty:found_nothing"),
        result=Result(type="qualitative", finding="found_nothing: ..."),
        bears_on=[],
        literature_decision=None,
    )
    assert derive_novelty_status(_hyp(True), [null_payload]) == ClaimStatus.PROPOSED


def test_wrong_kind_with_found_nothing_payload_does_not_support():
    """Fail-closed: a non-NOVELTY_DECISION item (here CONTESTED_RECORD) carrying a
    found_nothing payload must NOT support -- the predicate filters on
    kind==NOVELTY_DECISION."""
    wrong_kind = EvidenceItem(
        id="evi-contested",
        spec_id="s",
        kind=EvidenceKind.CONTESTED_RECORD,
        provenance=Provenance(code_ref="contested"),
        result=Result(type="qualitative", finding="found_nothing: ..."),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="found_nothing", hypothesis_id="hyp-1"
        ),
    )
    assert derive_novelty_status(_hyp(True), [wrong_kind]) == ClaimStatus.PROPOSED


def test_pure_predicate_never_raises():
    """The predicate replaces the HALT: it must return a ClaimStatus, never raise --
    even on a novelty hypothesis with no decision (which used to HALT)."""
    # No assertion of value beyond "did not raise"; the value is covered above.
    assert derive_novelty_status(_hyp(True), []) in (
        ClaimStatus.PROPOSED,
        ClaimStatus.SUPPORTED,
    )
