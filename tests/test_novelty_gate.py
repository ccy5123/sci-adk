"""
Novelty status derivation (2-kind, B-replace).

design/literature-acquisition.md §"Novelty -- definition (2-kind)": novelty is two
INDEPENDENT kinds (result | method), each a 1st-class revisable Claim derived by a RULE.

  ``derive_novelty_status(hypothesis, kind, novelty_decisions) -> ClaimStatus``

returns ``ClaimStatus.SUPPORTED`` iff some ``NOVELTY_DECISION`` whose
``literature_decision.hypothesis_id == hypothesis.id`` AND
``literature_decision.kind == kind`` has outcome ``"found_nothing"`` (a recorded
prior-art search of THAT kind that returned nothing), else ``ClaimStatus.PROPOSED``.

Safety floor (the whole point): a ``found_something`` decision NEVER yields SUPPORTED;
no decision / a ``skipped`` decision -> PROPOSED; and a found_nothing on the OTHER kind
NEVER satisfies this one (result and method are independent claims). The predicate is
PURE: it never raises (the HALT is gone, replaced by a non-HALT compile-time checkpoint).

The predicate takes the novelty DECISION items (kind==NOVELTY_DECISION) NOT bearing
evidence -- decisions carry ``bears_on=[]`` and never enter the DecisionEngine. It is
decoupled from the experiment verdict (no ``verdict_direction`` param).
"""

from __future__ import annotations

from typing import Optional

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

def _hyp(
    novelty_result: bool = False,
    novelty_method: bool = False,
    hyp_id: str = "hyp-1",
) -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="first to show Z",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE, expression="clear and on-topic"
        ),
        novelty_result=novelty_result,
        novelty_method=novelty_method,
    )


def _novelty_decision(
    hyp_id: str,
    outcome: str,
    kind: Optional[str] = "result",
    item_id: str = "evi-nov-1",
) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref=f"novelty:{kind}:{outcome}"),
        result=Result(type="qualitative", finding=f"{kind} {outcome}: ..."),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome=outcome, hypothesis_id=hyp_id, kind=kind
        ),
    )


# --------------------------------------------------------------------------- #
# SUPPORTED iff a recorded found_nothing prior-art search of THAT kind
# --------------------------------------------------------------------------- #

def test_found_nothing_yields_supported_result():
    """A recorded result prior-art search that returned nothing -> SUPPORTED result."""
    decisions = [_novelty_decision("hyp-1", "found_nothing", kind="result")]
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", decisions
    ) == ClaimStatus.SUPPORTED


def test_found_nothing_yields_supported_method():
    """A recorded method prior-art search that returned nothing -> SUPPORTED method."""
    decisions = [_novelty_decision("hyp-1", "found_nothing", kind="method")]
    assert derive_novelty_status(
        _hyp(novelty_method=True), "method", decisions
    ) == ClaimStatus.SUPPORTED


def test_no_decision_yields_proposed():
    """No novelty decision at all -> PROPOSED (the search has not been done)."""
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", []
    ) == ClaimStatus.PROPOSED


def test_skipped_decision_yields_proposed():
    """A skipped novelty decision does NOT support the claim (no search) -> PROPOSED."""
    decisions = [_novelty_decision("hyp-1", "skipped", kind="result")]
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", decisions
    ) == ClaimStatus.PROPOSED


def test_found_something_never_yields_supported():
    """SAFETY FLOOR: a found_something decision (prior art exists) NEVER yields
    SUPPORTED; it stays PROPOSED (active refuted-promotion is deferred with render)."""
    decisions = [_novelty_decision("hyp-1", "found_something", kind="result")]
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", decisions
    ) == ClaimStatus.PROPOSED


# --------------------------------------------------------------------------- #
# the two kinds are INDEPENDENT (the ``kind ==`` match is load-bearing)
# --------------------------------------------------------------------------- #

def test_found_nothing_on_result_does_not_satisfy_method():
    """A result found_nothing must NOT support the method claim -- the axes are
    independent and each is searched/derived separately (anti-HARKing)."""
    decisions = [_novelty_decision("hyp-1", "found_nothing", kind="result")]
    h = _hyp(novelty_result=True, novelty_method=True)
    assert derive_novelty_status(h, "result", decisions) == ClaimStatus.SUPPORTED
    assert derive_novelty_status(h, "method", decisions) == ClaimStatus.PROPOSED


def test_found_nothing_on_method_does_not_satisfy_result():
    decisions = [_novelty_decision("hyp-1", "found_nothing", kind="method")]
    h = _hyp(novelty_result=True, novelty_method=True)
    assert derive_novelty_status(h, "method", decisions) == ClaimStatus.SUPPORTED
    assert derive_novelty_status(h, "result", decisions) == ClaimStatus.PROPOSED


def test_both_kinds_independently_supported_when_both_searched():
    """Both axes get their own found_nothing -> both SUPPORTED (orthogonal quadrant)."""
    decisions = [
        _novelty_decision("hyp-1", "found_nothing", kind="result", item_id="evi-r"),
        _novelty_decision("hyp-1", "found_nothing", kind="method", item_id="evi-m"),
    ]
    h = _hyp(novelty_result=True, novelty_method=True)
    assert derive_novelty_status(h, "result", decisions) == ClaimStatus.SUPPORTED
    assert derive_novelty_status(h, "method", decisions) == ClaimStatus.SUPPORTED


# --------------------------------------------------------------------------- #
# binding to the hypothesis id + fail-closed guards
# --------------------------------------------------------------------------- #

def test_found_nothing_for_another_hypothesis_does_not_support():
    """A found_nothing decision bound to a DIFFERENT hypothesis must not support this
    one (the decision is hypothesis-bound via its payload)."""
    decisions = [_novelty_decision("hyp-OTHER", "found_nothing", kind="result")]
    assert derive_novelty_status(
        _hyp(novelty_result=True, hyp_id="hyp-1"), "result", decisions
    ) == ClaimStatus.PROPOSED


def test_unset_kind_never_supported_even_with_found_nothing():
    """SAFETY-FLOOR HARDENING (defense-in-depth): a kind whose flag is UNSET always
    yields PROPOSED, even with a matching found_nothing decision for that kind -- a kind
    is novelty only when its own flag is set (anti-HARKing)."""
    decisions = [_novelty_decision("hyp-1", "found_nothing", kind="result")]
    # novelty_result flag is False -> the result kind is not a novelty claim here.
    assert derive_novelty_status(
        _hyp(novelty_result=False), "result", decisions
    ) == ClaimStatus.PROPOSED


def test_found_nothing_alongside_found_something_still_supported():
    """If the record holds a found_nothing for this {hyp, kind}, the presence of an
    additional found_something does not erase the recorded null search -> SUPPORTED."""
    decisions = [
        _novelty_decision("hyp-1", "found_something", kind="result", item_id="evi-a"),
        _novelty_decision("hyp-1", "found_nothing", kind="result", item_id="evi-b"),
    ]
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", decisions
    ) == ClaimStatus.SUPPORTED


def test_null_payload_does_not_support():
    """Fail-closed: a NOVELTY_DECISION whose payload is absent carries no outcome,
    so it must NOT support -> PROPOSED."""
    null_payload = EvidenceItem(
        id="evi-nov-null",
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref="novelty:result:found_nothing"),
        result=Result(type="qualitative", finding="found_nothing: ..."),
        bears_on=[],
        literature_decision=None,
    )
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", [null_payload]
    ) == ClaimStatus.PROPOSED


def test_kindless_payload_does_not_support():
    """Fail-closed: a NOVELTY_DECISION payload with no kind (kind=None) cannot satisfy a
    specific kind -- the ``kind ==`` match fails for both result and method."""
    kindless = _novelty_decision("hyp-1", "found_nothing", kind=None)
    h = _hyp(novelty_result=True, novelty_method=True)
    assert derive_novelty_status(h, "result", [kindless]) == ClaimStatus.PROPOSED
    assert derive_novelty_status(h, "method", [kindless]) == ClaimStatus.PROPOSED


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
            outcome="found_nothing", hypothesis_id="hyp-1", kind="result"
        ),
    )
    assert derive_novelty_status(
        _hyp(novelty_result=True), "result", [wrong_kind]
    ) == ClaimStatus.PROPOSED


def test_pure_predicate_never_raises():
    """The predicate replaces the HALT: it must return a ClaimStatus, never raise --
    even on a novelty hypothesis with no decision (which used to HALT)."""
    assert derive_novelty_status(_hyp(novelty_result=True), "result", []) in (
        ClaimStatus.PROPOSED,
        ClaimStatus.SUPPORTED,
    )
