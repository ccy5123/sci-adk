"""
Unit 1 (RED-first): the typed checkpoint + verdict-trail schema.

These lock the on-disk *contract* behind ``checkpoints/<hyp-id>.json`` and
``verdicts/<hyp-id>.json`` (design/rigor-shell-architecture.md §4.3/§4.4, F1/F2).
The verdict trail is MANDATORY and schematized: a binding non-numeric verdict
carries the N independent panel opinions, the frozen rubric R copied for replay,
and the chief's single adjudication. The models must round-trip via Pydantic v2
(``model_validate`` / ``model_dump(mode="json")``) so a replay can re-derive the
verdict deterministically (E3).

``JudgeVerdict`` gains an optional ``trail`` field (additive, default None) so the
engine can read the trail off the returned verdict without changing the Judge
Protocol signatures.
"""

from __future__ import annotations

import pytest

from sci_adk.core.claim import ConfidenceLevel
from sci_adk.core.evidence import BearingDirection
from sci_adk.loop.judge import JudgeVerdict
from sci_adk.loop.verdict import (
    CheckpointModel,
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)


# -- CheckpointModel ---------------------------------------------------------

def test_checkpoint_model_round_trips():
    cp = CheckpointModel(
        hypothesis_id="hyp-1",
        kind="proof",
        expression="verified derivation => support; counterexample => refute",
        finding="the proof body the agent should judge",
        spec_version=1,
    )
    dumped = cp.model_dump(mode="json")
    restored = CheckpointModel.model_validate(dumped)
    assert restored == cp
    assert restored.hypothesis_id == "hyp-1"
    assert restored.kind == "proof"
    assert restored.spec_version == 1


def test_checkpoint_model_rejects_unknown_kind():
    with pytest.raises(ValueError):
        CheckpointModel(
            hypothesis_id="hyp-1",
            kind="threshold",  # numeric kinds are never checkpoints
            expression="x",
            spec_version=1,
        )


def test_checkpoint_model_finding_defaults_empty():
    cp = CheckpointModel(
        hypothesis_id="hyp-1",
        kind="qualitative",
        expression="clear and on-topic",
        spec_version=2,
    )
    assert cp.finding == ""


# -- VerdictTrail (the chief-over-N shape) -----------------------------------

def _panel(direction=BearingDirection.SUPPORTS, level=ConfidenceLevel.STRONG,
           basis="panelist reasoning", counterexample=False):
    return PanelVerdict(
        direction=direction, level=level, basis=basis, counterexample=counterexample
    )


def _trail(
    *,
    hypothesis_id="hyp-1",
    rule_kind="proof",
    rubric_expression="verified derivation => support",
    rubric_params=None,
    panel=None,
    chief=None,
):
    return VerdictTrail(
        hypothesis_id=hypothesis_id,
        rule_kind=rule_kind,
        rubric_expression=rubric_expression,
        rubric_params=rubric_params,
        panel=panel if panel is not None else [_panel()],
        chief=chief
        if chief is not None
        else ChiefVerdict(
            direction=BearingDirection.SUPPORTS,
            level=ConfidenceLevel.STRONG,
            basis="panelist 1 reasoning is decisive under R",
        ),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )


def test_verdict_trail_round_trips():
    trail = _trail(
        rubric_params={"min_witnesses": 3},
        panel=[_panel(basis="p1"), _panel(basis="p2", level=ConfidenceLevel.MODERATE)],
    )
    dumped = trail.model_dump(mode="json")
    restored = VerdictTrail.model_validate(dumped)
    assert restored == trail
    assert len(restored.panel) == 2
    assert restored.rubric_params == {"min_witnesses": 3}
    assert restored.chief.direction == BearingDirection.SUPPORTS


def test_verdict_trail_requires_nonempty_panel():
    with pytest.raises(ValueError):
        _trail(panel=[])


def test_verdict_trail_requires_nonempty_rubric_expression():
    with pytest.raises(ValueError):
        VerdictTrail(
            hypothesis_id="hyp-1",
            rule_kind="proof",
            rubric_expression="",  # empty rubric is not replayable
            rubric_params=None,
            panel=[_panel()],
            chief=ChiefVerdict(
                direction=BearingDirection.SUPPORTS,
                level=ConfidenceLevel.STRONG,
                basis="decisive",
            ),
            provenance=VerdictProvenance(spec_version=1, timestamp="t"),
        )


def test_chief_verdict_requires_nonempty_basis():
    # The chief MUST state which panel reasoning is decisive under R (§4.4).
    with pytest.raises(ValueError):
        ChiefVerdict(
            direction=BearingDirection.SUPPORTS,
            level=ConfidenceLevel.STRONG,
            basis="   ",
        )


def test_verdict_trail_params_optional():
    trail = _trail(rubric_params=None)
    restored = VerdictTrail.model_validate(trail.model_dump(mode="json"))
    assert restored.rubric_params is None


# -- JudgeVerdict additive trail field ---------------------------------------

def test_judge_verdict_trail_defaults_none_backward_constructible():
    # The positional constructor used across the existing tests must still work.
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "verified")
    assert jv.trail is None


def test_judge_verdict_can_carry_a_trail():
    trail = _trail()
    jv = JudgeVerdict(
        BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "verified", trail=trail
    )
    assert jv.trail is trail
