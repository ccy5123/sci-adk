"""
Novelty hard gate (RED-first).

design/literature-acquisition.md §"Discovery trigger model" (High trigger): a
novelty/priority claim asserts "first/new" -- a universal-negative over the
literature. Its validity rests on a prior-art search having been done. So:

  ``check_novelty_adequacy(hypothesis, novelty_decisions, verdict_direction)``

fires a ``ValidityHalt`` when
  - ``hypothesis.novelty is True`` AND
  - ``verdict_direction == SUPPORTS`` AND
  - there is NO ``NOVELTY_DECISION`` for this hypothesis with ``outcome=="searched"``.

SUPPORTS-only (narrower than the other adequacy gates): REFUTES/NEUTRAL/INCONCLUSIVE
never trip it. A novelty ``outcome=="skipped"`` decision does NOT satisfy the gate
(skipping the search guts the claim's only evidentiary basis).

The two escapes the HALT must name:
  (a) perform a prior-art search and record it
      (``sci-adk novelty <run> --hypothesis <id> --searched <dois>``), or
  (b) drop the novelty flag via a Spec amendment (F7, ``spec.amend(...)``, human-only)
      -- never a silent edit.

The gate takes the novelty DECISION items (kind==NOVELTY_DECISION whose
``literature_decision.hypothesis_id == hypothesis.id``), NOT bearing evidence --
decisions carry ``bears_on=[]`` and never enter the DecisionEngine.

This is the kernel, deterministic, no-LLM application of "agents propose, the engine
judges, no self-certification" to the novelty trigger; it REUSES ``ValidityHalt``.
"""

from __future__ import annotations

import pytest

from sci_adk.core.evidence import (
    BearingDirection,
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
from sci_adk.core.validity import ValidityHalt, check_novelty_adequacy


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
# the gate fires
# --------------------------------------------------------------------------- #

def test_novelty_supports_no_decision_halts():
    """novelty + SUPPORTS + no novelty decision -> HALT."""
    with pytest.raises(ValidityHalt):
        check_novelty_adequacy(_hyp(True), [], BearingDirection.SUPPORTS)


def test_novelty_supports_skip_decision_halts():
    """A skipped novelty decision does NOT satisfy the gate (skipping guts the
    claim's evidentiary basis) -> still HALT."""
    decisions = [_novelty_decision("hyp-1", "skipped")]
    with pytest.raises(ValidityHalt):
        check_novelty_adequacy(_hyp(True), decisions, BearingDirection.SUPPORTS)


def test_novelty_halt_is_bound_to_the_hypothesis_id():
    try:
        check_novelty_adequacy(_hyp(True, "hyp-7"), [], BearingDirection.SUPPORTS)
    except ValidityHalt as halt:
        assert halt.hypothesis_id == "hyp-7"
    else:  # pragma: no cover - the call must raise
        pytest.fail("expected a ValidityHalt")


def test_novelty_halt_message_names_both_F7_escapes():
    """The HALT must name BOTH escapes: (a) search+record via the CLI verb, and
    (b) drop the novelty flag through a Spec amendment (F7, human-only)."""
    try:
        check_novelty_adequacy(_hyp(True), [], BearingDirection.SUPPORTS)
    except ValidityHalt as halt:
        reason = halt.reason.lower()
        # (a) the searched-record escape (the CLI verb)
        assert "--searched" in halt.reason
        assert "novelty" in reason
        # (b) the Spec-amendment escape (F7, human-only)
        assert "amend" in reason
        assert "f7" in reason
    else:  # pragma: no cover
        pytest.fail("expected a ValidityHalt")


# --------------------------------------------------------------------------- #
# the gate passes
# --------------------------------------------------------------------------- #

def test_novelty_supports_searched_decision_passes():
    """novelty + SUPPORTS + a SEARCHED novelty decision -> passes (no raise)."""
    decisions = [_novelty_decision("hyp-1", "searched")]
    # passes silently (returns None)
    assert check_novelty_adequacy(_hyp(True), decisions, BearingDirection.SUPPORTS) is None


def test_novelty_refutes_no_decision_passes():
    """SUPPORTS-only: a novelty hypothesis that is REFUTED never trips the gate."""
    assert check_novelty_adequacy(_hyp(True), [], BearingDirection.REFUTES) is None


def test_novelty_neutral_passes():
    assert check_novelty_adequacy(_hyp(True), [], BearingDirection.NEUTRAL) is None


def test_novelty_inconclusive_passes():
    assert check_novelty_adequacy(_hyp(True), [], BearingDirection.INCONCLUSIVE) is None


def test_non_novelty_supports_no_decision_passes():
    """novelty=False -> the gate is inert regardless of direction/decisions."""
    assert check_novelty_adequacy(_hyp(False), [], BearingDirection.SUPPORTS) is None


def test_searched_decision_for_another_hypothesis_does_not_satisfy():
    """A searched decision bound to a DIFFERENT hypothesis must not satisfy this
    hypothesis's gate (the decision is hypothesis-bound via its payload)."""
    decisions = [_novelty_decision("hyp-OTHER", "searched")]
    with pytest.raises(ValidityHalt):
        check_novelty_adequacy(_hyp(True, "hyp-1"), decisions, BearingDirection.SUPPORTS)


# --------------------------------------------------------------------------- #
# fail-closed guards (promoted from evaluator-active probes)
# --------------------------------------------------------------------------- #

def test_novelty_decision_with_null_payload_does_not_satisfy():
    """Fail-closed: a NOVELTY_DECISION whose ``literature_decision`` payload is absent
    carries no ``searched`` outcome, so it must NOT satisfy the gate (still HALT). Guards
    the ``ev.literature_decision is not None`` branch in ``check_novelty_adequacy``
    against a future refactor that drops it."""
    null_payload = EvidenceItem(
        id="evi-nov-null",
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref="novelty:searched"),
        result=Result(type="qualitative", finding="searched: ..."),
        bears_on=[],
        literature_decision=None,  # payload explicitly absent
    )
    with pytest.raises(ValidityHalt):
        check_novelty_adequacy(_hyp(True), [null_payload], BearingDirection.SUPPORTS)


def test_wrong_kind_with_searched_payload_does_not_satisfy():
    """Fail-closed: a non-NOVELTY_DECISION item (here CONTESTED_RECORD) carrying a
    ``searched`` payload must NOT satisfy the gate -- ``check_novelty_adequacy`` filters
    on ``kind == NOVELTY_DECISION``, so a wrong-kind item with a searched payload still
    HALTs. Guards the load-bearing kind filter."""
    wrong_kind = EvidenceItem(
        id="evi-contested-searched",
        spec_id="s",
        kind=EvidenceKind.CONTESTED_RECORD,
        provenance=Provenance(code_ref="contested"),
        result=Result(type="qualitative", finding="searched: ..."),
        bears_on=[],
        literature_decision=LiteratureDecision(outcome="searched", hypothesis_id="hyp-1"),
    )
    with pytest.raises(ValidityHalt):
        check_novelty_adequacy(_hyp(True), [wrong_kind], BearingDirection.SUPPORTS)
