"""
Schema for the novelty (High) + contested (Medium) discovery triggers (RED-first).

design/literature-acquisition.md §"Discovery trigger model": two new hypothesis-bound
recording triggers join the implemented Spec-creation prior-art anchor. This module
locks the *schema* surface they need -- mirroring the prior-work / digitized patterns:

  1. ``Hypothesis.novelty`` -- a frozen anti-HARKing flag (a novelty/priority claim
     asserts "first/new", a universal-negative over the literature). Default False.
  2. two new ``EvidenceKind`` values -- ``NOVELTY_DECISION`` / ``CONTESTED_RECORD`` --
     kept SEPARATE from ``PRIOR_WORK_DECISION`` (whose closing-kind set is a
     load-bearing anchor that must stay unchanged).
  3. a frozen ``LiteratureDecision`` sub-model (mirrors ``DigitizedData``'s style) and
     ``EvidenceItem.literature_decision`` (parallel to ``EvidenceItem.digitized``),
     present only on the two new kinds.

No LLM anywhere: these are pure kernel data types.
"""

from __future__ import annotations

import pytest

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


# --------------------------------------------------------------------------- #
# 1. Hypothesis.novelty -- frozen anti-HARKing flag, default False
# --------------------------------------------------------------------------- #

def _hyp(novelty: bool | None = None) -> Hypothesis:
    kwargs = dict(
        id="hyp-1",
        statement="X is the first to do Y",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE, expression="clear and on-topic"
        ),
    )
    if novelty is not None:
        kwargs["novelty"] = novelty
    return Hypothesis(**kwargs)


def test_hypothesis_novelty_defaults_false():
    """Most hypotheses are not novelty claims -> fail-open default is False."""
    assert _hyp().novelty is False


def test_hypothesis_novelty_can_be_set_true():
    assert _hyp(novelty=True).novelty is True


def test_hypothesis_novelty_is_frozen():
    """The Spec is frozen (anti-HARKing): the flag cannot be flipped post-hoc."""
    hyp = _hyp(novelty=True)
    with pytest.raises(Exception):
        hyp.novelty = False  # frozen model -> ValidationError/TypeError


def test_hypothesis_novelty_round_trips():
    hyp = _hyp(novelty=True)
    restored = Hypothesis.model_validate(hyp.model_dump(mode="json"))
    assert restored == hyp
    assert restored.novelty is True


def test_hypothesis_without_novelty_round_trips_as_false():
    """A pre-existing Hypothesis JSON with no ``novelty`` key loads as False
    (additive, defaulted field -- older specs still validate)."""
    hyp = _hyp()
    blob = hyp.model_dump(mode="json")
    blob.pop("novelty", None)  # simulate a pre-feature spec on disk
    restored = Hypothesis.model_validate(blob)
    assert restored.novelty is False


# --------------------------------------------------------------------------- #
# 2. New EvidenceKinds -- separate from PRIOR_WORK_DECISION
# --------------------------------------------------------------------------- #

def test_novelty_decision_evidence_kind_exists():
    assert EvidenceKind.NOVELTY_DECISION.value == "novelty_decision"


def test_contested_record_evidence_kind_exists():
    assert EvidenceKind.CONTESTED_RECORD.value == "contested_record"


def test_new_kinds_are_distinct_from_prior_work_decision():
    """The new kinds must NOT collide with the Spec-creation prior-work kind --
    PRIOR_WORK_DECISION's closing-kind set is a load-bearing anchor that stays
    unchanged."""
    assert EvidenceKind.NOVELTY_DECISION is not EvidenceKind.PRIOR_WORK_DECISION
    assert EvidenceKind.CONTESTED_RECORD is not EvidenceKind.PRIOR_WORK_DECISION
    assert EvidenceKind.NOVELTY_DECISION is not EvidenceKind.CONTESTED_RECORD


# --------------------------------------------------------------------------- #
# 3. LiteratureDecision sub-model + EvidenceItem.literature_decision
# --------------------------------------------------------------------------- #

def test_literature_decision_constructs_searched():
    d = LiteratureDecision(
        outcome="searched",
        hypothesis_id="hyp-1",
        literature_evidence_id="evi-lit-x",
    )
    assert d.outcome == "searched"
    assert d.hypothesis_id == "hyp-1"
    assert d.literature_evidence_id == "evi-lit-x"
    assert d.reason is None


def test_literature_decision_constructs_skipped_with_reason():
    d = LiteratureDecision(
        outcome="skipped", hypothesis_id="hyp-1", reason="not a novelty claim after all"
    )
    assert d.outcome == "skipped"
    assert d.reason == "not a novelty claim after all"
    assert d.literature_evidence_id is None


def test_literature_decision_constructs_recorded():
    d = LiteratureDecision(outcome="recorded", hypothesis_id="hyp-1")
    assert d.outcome == "recorded"


def test_literature_decision_requires_nonempty_hypothesis_id():
    """These triggers are hypothesis-bound -- an empty hypothesis_id is refused."""
    with pytest.raises(Exception):
        LiteratureDecision(outcome="searched", hypothesis_id="")


def test_literature_decision_rejects_foreign_outcome():
    with pytest.raises(Exception):
        LiteratureDecision(outcome="believed", hypothesis_id="hyp-1")


def test_literature_decision_is_frozen():
    d = LiteratureDecision(outcome="recorded", hypothesis_id="hyp-1")
    with pytest.raises(Exception):
        d.outcome = "searched"


def test_literature_decision_round_trips():
    d = LiteratureDecision(
        outcome="searched", hypothesis_id="hyp-1", literature_evidence_id="evi-lit-x"
    )
    restored = LiteratureDecision.model_validate(d.model_dump(mode="json"))
    assert restored == d


def test_evidence_item_literature_decision_defaults_none():
    """Every non-decision kind carries no ``literature_decision`` (parallel to the
    digitized asymmetry)."""
    item = EvidenceItem(
        id="evi-1",
        spec_id="s",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x"),
        result=Result(type="qualitative", finding="f"),
    )
    assert item.literature_decision is None


def test_evidence_item_with_literature_decision_round_trips():
    """A NOVELTY_DECISION item carrying the payload round-trips through the single
    append-only log (model_dump/model_validate)."""
    item = EvidenceItem(
        id="evi-nov-1",
        spec_id="s",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref="novelty:searched"),
        result=Result(type="qualitative", finding="searched: DOIs=['10.1/x']"),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="searched", hypothesis_id="hyp-1", literature_evidence_id="evi-lit-x"
        ),
    )
    restored = EvidenceItem.model_validate(item.model_dump(mode="json"))
    assert restored == item
    assert restored.literature_decision is not None
    assert restored.literature_decision.outcome == "searched"
    assert restored.literature_decision.hypothesis_id == "hyp-1"
    # a recorded decision, not a belief
    assert restored.bears_on == []


def test_contested_record_item_carries_payload_and_round_trips():
    item = EvidenceItem(
        id="evi-con-1",
        spec_id="s",
        kind=EvidenceKind.CONTESTED_RECORD,
        provenance=Provenance(code_ref="contested:record"),
        result=Result(type="qualitative", finding="recorded: conflicting prior work"),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="recorded", hypothesis_id="hyp-1"
        ),
    )
    restored = EvidenceItem.model_validate(item.model_dump(mode="json"))
    assert restored == item
    assert restored.literature_decision.outcome == "recorded"


def test_literature_decision_is_exported():
    """The sub-model is part of the public evidence API (mirrors DigitizedData)."""
    import sci_adk.core.evidence as ev_mod

    assert "LiteratureDecision" in ev_mod.__all__
