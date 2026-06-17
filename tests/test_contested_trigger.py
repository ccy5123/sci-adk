"""
Contested trigger (Medium): a recording-type checkpoint, NO gate, NO halt (RED-first).

design/literature-acquisition.md §"Discovery trigger model" (Medium trigger): when a
claim conflicts (becomes CONTESTED), the rigor is RECORDING, not searching -- a
timestamp so literature that arrived AFTER the conflict stays visible (anti
post-hoc-rationalization). The append-only ``created_at`` ordering supplies the
anti-post-hoc timestamp; the ``CONTESTED_RECORD`` decision makes the post-conflict
literature decision explicit.

This module locks:
  1. ``ContestedCheckpoint`` -- the hypothesis-bound "contested" arm of the
     ``Checkpoint`` discriminated union (mirrors ``PriorWorkCheckpoint`` but bound to a
     hypothesis); the legacy default tag stays "judge".
  2. ``record_contested`` -- writes a ``CONTESTED_RECORD`` (outcome="recorded",
     bears_on=[], hypothesis-bound via the payload). NO halt anywhere.
  3. ``contested_open`` -- True iff the claim for that hypothesis is CONTESTED but no
     ``CONTESTED_RECORD`` exists for it yet (read-only, no LLM).
  4. ``contested_checkpoint`` -- the builder.
  5. the regression guard: a CONTESTED_RECORD does NOT close the Spec-creation
     prior_work checkpoint (separate kinds).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
)
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _spec(spec_id: str = "con-spec", hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="a contested claim",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.QUALITATIVE, expression="clear and on-topic"
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _write_contested_claim(workspace: Path, spec: Spec, hyp_id: str = "hyp-1") -> None:
    """Persist a CONTESTED Claim for ``hyp_id`` under runs/<spec.id>/claims/."""
    claims_dir = workspace / "runs" / spec.id / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim = Claim(
        id=f"claim-{hyp_id}",
        spec_id=spec.id,
        answers=hyp_id,
        statement="a contested claim",
        status=ClaimStatus.CONTESTED,
        confidence=Confidence(
            type=ConfidenceType.GRADED, level="moderate",
            basis="support and refutation coexist",
        ),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (claims_dir / f"{claim.id}.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# 1. ContestedCheckpoint -- the "contested" arm of the union
# --------------------------------------------------------------------------- #

def test_contested_checkpoint_fields():
    from sci_adk.loop.verdict import ContestedCheckpoint

    cp = ContestedCheckpoint(
        hypothesis_id="hyp-1", spec_id="con-spec", spec_version=1, prompt="record it"
    )
    assert cp.checkpoint_type == "contested"
    assert cp.hypothesis_id == "hyp-1"
    assert cp.spec_id == "con-spec"
    assert cp.spec_version == 1


def test_contested_checkpoint_round_trips():
    from sci_adk.loop.verdict import ContestedCheckpoint

    cp = ContestedCheckpoint(
        hypothesis_id="hyp-1", spec_id="con-spec", spec_version=2, prompt="record it"
    )
    restored = ContestedCheckpoint.model_validate(cp.model_dump(mode="json"))
    assert restored == cp


def test_contested_checkpoint_in_discriminated_union():
    """The tagged union routes a ``contested`` payload to ``ContestedCheckpoint`` and
    keeps the legacy "judge" default for tag-less files."""
    from pydantic import TypeAdapter

    from sci_adk.loop.verdict import (
        Checkpoint,
        ContestedCheckpoint,
        JudgeCheckpoint,
        PriorWorkCheckpoint,
    )

    adapter = TypeAdapter(Checkpoint)

    con = ContestedCheckpoint(
        hypothesis_id="hyp-1", spec_id="s", spec_version=1, prompt="record"
    )
    con_back = adapter.validate_python(con.model_dump(mode="json"))
    assert isinstance(con_back, ContestedCheckpoint)

    # legacy judge file (no checkpoint_type) still loads as JudgeCheckpoint
    legacy = {
        "hypothesis_id": "hyp-1", "kind": "proof",
        "expression": "verified derivation => support", "spec_version": 1,
    }
    assert isinstance(adapter.validate_python(legacy), JudgeCheckpoint)

    # prior_work still routes correctly (no regression)
    pw = PriorWorkCheckpoint(spec_id="s", spec_version=1, prompt="x")
    assert isinstance(
        adapter.validate_python(pw.model_dump(mode="json")), PriorWorkCheckpoint
    )


def test_contested_checkpoint_is_exported():
    import sci_adk.loop.verdict as verdict_mod

    assert "ContestedCheckpoint" in verdict_mod.__all__


# --------------------------------------------------------------------------- #
# 2. contested_checkpoint builder + contested_open predicate
# --------------------------------------------------------------------------- #

def test_contested_checkpoint_builder():
    from sci_adk.loop.literature_triggers import contested_checkpoint
    from sci_adk.loop.verdict import ContestedCheckpoint

    spec = _spec("con-build")
    cp = contested_checkpoint(spec, "hyp-1", spec.version)
    assert isinstance(cp, ContestedCheckpoint)
    assert cp.hypothesis_id == "hyp-1"
    assert cp.spec_id == "con-build"
    assert cp.spec_version == spec.version
    assert cp.prompt  # a non-empty reminder


def test_contested_open_true_when_claim_contested_and_no_record(tmp_path):
    from sci_adk.loop.literature_triggers import contested_open

    spec = _spec("con-open")
    _write_contested_claim(tmp_path, spec)
    assert contested_open(spec, "hyp-1", tmp_path) is True


def test_contested_open_false_when_claim_not_contested(tmp_path):
    """No CONTESTED claim for the hypothesis -> nothing to surface (not open)."""
    from sci_adk.loop.literature_triggers import contested_open

    spec = _spec("con-not-contested")
    # claims dir exists but holds no contested claim for hyp-1
    (tmp_path / "runs" / spec.id / "claims").mkdir(parents=True, exist_ok=True)
    assert contested_open(spec, "hyp-1", tmp_path) is False


# --------------------------------------------------------------------------- #
# 3. record_contested -- writes a CONTESTED_RECORD, NO halt
# --------------------------------------------------------------------------- #

def test_record_contested_writes_record_and_flips_open_false(tmp_path):
    from sci_adk.loop.literature_triggers import contested_open, record_contested

    spec = _spec("con-record")
    _write_contested_claim(tmp_path, spec)
    assert contested_open(spec, "hyp-1", tmp_path) is True

    item = record_contested(
        spec, tmp_path, hypothesis_id="hyp-1",
        reason_or_note="conflicting prior work surfaced after the result",
    )
    assert item.kind is EvidenceKind.CONTESTED_RECORD
    # hypothesis-bound via the payload, and a recorded decision (not a belief)
    assert item.literature_decision is not None
    assert item.literature_decision.outcome == "recorded"
    assert item.literature_decision.hypothesis_id == "hyp-1"
    assert item.bears_on == []
    # persisted into the single append-only log
    assert (tmp_path / "runs" / spec.id / "evidence" / f"{item.id}.json").exists()
    # the checkpoint is now closed
    assert contested_open(spec, "hyp-1", tmp_path) is False


def test_record_contested_is_hypothesis_scoped(tmp_path):
    """A CONTESTED_RECORD for hyp-1 must NOT close an open contested checkpoint for a
    DIFFERENT contested hypothesis (the record is hypothesis-bound via the payload)."""
    from sci_adk.loop.literature_triggers import contested_open, record_contested

    spec = Spec(
        id="con-two",
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(id="hyp-1", statement="c1", mode=HypothesisMode.CONFIRMATORY,
                       decision_rule=DecisionRule(kind=DecisionRuleKind.QUALITATIVE,
                                                  expression="e1")),
            Hypothesis(id="hyp-2", statement="c2", mode=HypothesisMode.CONFIRMATORY,
                       decision_rule=DecisionRule(kind=DecisionRuleKind.QUALITATIVE,
                                                  expression="e2")),
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-1")],
    )
    _write_contested_claim(tmp_path, spec, "hyp-1")
    _write_contested_claim(tmp_path, spec, "hyp-2")

    record_contested(spec, tmp_path, hypothesis_id="hyp-1", reason_or_note="r")
    # hyp-1 closed, hyp-2 still open
    assert contested_open(spec, "hyp-1", tmp_path) is False
    assert contested_open(spec, "hyp-2", tmp_path) is True


def test_record_contested_does_not_raise_any_halt(tmp_path):
    """Explicit: the contested trigger NEVER halts (it is recording, not gating)."""
    from sci_adk.core.validity import ValidityHalt
    from sci_adk.loop.literature_triggers import record_contested

    spec = _spec("con-nohalt")
    _write_contested_claim(tmp_path, spec)
    try:
        record_contested(spec, tmp_path, hypothesis_id="hyp-1", reason_or_note="note")
    except ValidityHalt:  # pragma: no cover - must not happen
        pytest.fail("contested trigger must never raise a ValidityHalt")
