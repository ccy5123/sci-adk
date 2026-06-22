"""
Schema for the novelty (High) + contested (Medium) discovery triggers (RED-first).

design/literature-acquisition.md §"Discovery trigger model": two new hypothesis-bound
recording triggers join the implemented Spec-creation prior-art anchor. This module
locks the *schema* surface they need -- mirroring the prior-work / digitized patterns:

  1. ``Hypothesis.novelty_result`` / ``Hypothesis.novelty_method`` -- two independent
     frozen anti-HARKing flags (2-kind: a result-novelty claim asserts no prior work
     established the RESULT; a method-novelty claim, no prior work used the METHOD). Each
     defaults False.
  2. two new ``EvidenceKind`` values -- ``NOVELTY_DECISION`` / ``CONTESTED_RECORD`` --
     kept SEPARATE from ``PRIOR_WORK_DECISION`` (whose closing-kind set is a
     load-bearing anchor that must stay unchanged).
  3. a frozen ``LiteratureDecision`` sub-model (mirrors ``DigitizedData``'s style) with a
     ``kind: result|method`` axis on the NOVELTY_DECISION payload, and
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
# 1. Hypothesis.novelty_result / novelty_method -- two frozen anti-HARKing flags
# --------------------------------------------------------------------------- #

def _hyp(
    novelty_result: bool | None = None, novelty_method: bool | None = None
) -> Hypothesis:
    kwargs = dict(
        id="hyp-1",
        statement="X is the first to do Y",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE, expression="clear and on-topic"
        ),
    )
    if novelty_result is not None:
        kwargs["novelty_result"] = novelty_result
    if novelty_method is not None:
        kwargs["novelty_method"] = novelty_method
    return Hypothesis(**kwargs)


def test_hypothesis_novelty_flags_default_false():
    """Most hypotheses are not novelty claims -> both kind flags default False."""
    h = _hyp()
    assert h.novelty_result is False
    assert h.novelty_method is False


def test_hypothesis_novelty_flags_are_independent():
    """The two axes are orthogonal -- setting one does not set the other."""
    h_result = _hyp(novelty_result=True)
    assert h_result.novelty_result is True
    assert h_result.novelty_method is False

    h_method = _hyp(novelty_method=True)
    assert h_method.novelty_result is False
    assert h_method.novelty_method is True


def test_hypothesis_novelty_both_kinds_can_be_set():
    h = _hyp(novelty_result=True, novelty_method=True)
    assert h.novelty_result is True
    assert h.novelty_method is True


def test_hypothesis_novelty_flags_are_frozen():
    """The Spec is frozen (anti-HARKing): neither flag can be flipped post-hoc."""
    hyp = _hyp(novelty_result=True, novelty_method=True)
    with pytest.raises(Exception):
        hyp.novelty_result = False  # frozen model -> ValidationError/TypeError
    with pytest.raises(Exception):
        hyp.novelty_method = False


def test_hypothesis_novelty_flags_round_trip():
    hyp = _hyp(novelty_result=True, novelty_method=False)
    restored = Hypothesis.model_validate(hyp.model_dump(mode="json"))
    assert restored == hyp
    assert restored.novelty_result is True
    assert restored.novelty_method is False


def test_hypothesis_without_novelty_keys_round_trips_as_false():
    """A Hypothesis JSON with no ``novelty_result``/``novelty_method`` keys loads as
    False (defaulted fields -- a spec authored without the flags still validates)."""
    hyp = _hyp()
    blob = hyp.model_dump(mode="json")
    blob.pop("novelty_result", None)
    blob.pop("novelty_method", None)
    restored = Hypothesis.model_validate(blob)
    assert restored.novelty_result is False
    assert restored.novelty_method is False


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
    assert d.kind is None  # kindless unless this is a NOVELTY_DECISION payload


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
    assert d.kind is None  # CONTESTED_RECORD is kindless


def test_literature_decision_kind_defaults_none():
    """The novelty axis is None unless explicitly set (CONTESTED_RECORD / prior-work)."""
    d = LiteratureDecision(outcome="found_nothing", hypothesis_id="hyp-1")
    assert d.kind is None


@pytest.mark.parametrize("kind", ["result", "method"])
def test_literature_decision_accepts_novelty_kind(kind):
    d = LiteratureDecision(
        outcome="found_nothing", hypothesis_id="hyp-1", kind=kind,
        literature_evidence_id="evi-lit-x",
    )
    assert d.kind == kind


def test_literature_decision_rejects_foreign_kind():
    with pytest.raises(Exception):
        LiteratureDecision(
            outcome="found_nothing", hypothesis_id="hyp-1", kind="conclusion"
        )


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
        outcome="found_nothing", hypothesis_id="hyp-1", kind="method",
        literature_evidence_id="evi-lit-x",
    )
    restored = LiteratureDecision.model_validate(d.model_dump(mode="json"))
    assert restored == d
    assert restored.kind == "method"


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
        provenance=Provenance(code_ref="novelty:result:found_nothing"),
        result=Result(type="qualitative", finding="result-novelty found_nothing"),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="found_nothing", hypothesis_id="hyp-1", kind="result",
            literature_evidence_id="evi-lit-x",
        ),
    )
    restored = EvidenceItem.model_validate(item.model_dump(mode="json"))
    assert restored == item
    assert restored.literature_decision is not None
    assert restored.literature_decision.outcome == "found_nothing"
    assert restored.literature_decision.hypothesis_id == "hyp-1"
    assert restored.literature_decision.kind == "result"
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
