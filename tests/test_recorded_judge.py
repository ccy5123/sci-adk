"""
Unit 3 (RED-first): ``RecordedJudge`` -- the deterministic, no-LLM judge.

design/rigor-shell-architecture.md §5.2 step 4: the loop re-enters by constructing a
``RecordedJudge(run_dir)`` whose ``judge_qualitative`` / ``judge_proof`` read the
chief verdict from ``verdicts/<hyp-id>.json`` and return a ``JudgeVerdict`` whose
direction/level/basis/counterexample come from ``chief`` and whose ``trail`` is the
loaded ``VerdictTrail``. No LLM, no network -- pure JSON deserialization (kernel-side,
F2). An absent verdict file -> an inconclusive-shaped verdict with NO trail, so the
engine refuses to bind and the checkpoint stays open.

Seam note: the ``Judge`` Protocol methods receive ``criterion`` (= ``rule.expression``)
but NOT the hypothesis id (the signature is fixed). A run has one verdict file per
hypothesis, each carrying ``rubric_expression == rule.expression``; ``RecordedJudge``
therefore resolves the right verdict by matching ``criterion`` to a trail's
``rubric_expression``. ``verdict_for(hyp_id)`` is a direct lookup for the loop/tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.core.claim import ConfidenceLevel
from sci_adk.core.evidence import BearingDirection
from sci_adk.loop.recorded_judge import RecordedJudge
from sci_adk.loop.verdict import (
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)


def _write_trail(run_dir: Path, hyp_id: str, *, direction, level, basis,
                 counterexample=False, rule_kind="proof",
                 rubric_expression="R", rubric_params=None):
    trail = VerdictTrail(
        hypothesis_id=hyp_id,
        rule_kind=rule_kind,
        rubric_expression=rubric_expression,
        rubric_params=rubric_params,
        panel=[PanelVerdict(direction=direction, level=level, basis="panelist",
                            counterexample=counterexample)],
        chief=ChiefVerdict(direction=direction, level=level, basis=basis,
                           counterexample=counterexample),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{hyp_id}.json").write_text(
        json.dumps(trail.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return trail


def test_recorded_judge_reproduces_chief_verdict_for_proof(tmp_path):
    _write_trail(tmp_path, "hyp-1", direction=BearingDirection.SUPPORTS,
                 level=ConfidenceLevel.STRONG, basis="panelist A decisive under R",
                 rubric_expression="the proof criterion")
    jv = RecordedJudge(tmp_path).judge_proof(
        "the proof criterion", "finding", None, ["proof_step"], {})
    assert jv.direction == BearingDirection.SUPPORTS
    assert jv.level == ConfidenceLevel.STRONG
    assert "decisive" in jv.basis
    assert jv.trail is not None
    assert jv.trail.hypothesis_id == "hyp-1"


def test_recorded_judge_reproduces_chief_verdict_for_qualitative(tmp_path):
    _write_trail(tmp_path, "hyp-q", direction=BearingDirection.REFUTES,
                 level=ConfidenceLevel.MODERATE, basis="criterion not met",
                 rule_kind="qualitative", rubric_expression="the qual criterion")
    jv = RecordedJudge(tmp_path).judge_qualitative("the qual criterion", "finding", {})
    assert jv.direction == BearingDirection.REFUTES
    assert jv.trail is not None


def test_recorded_judge_carries_counterexample_flag(tmp_path):
    _write_trail(tmp_path, "hyp-1", direction=BearingDirection.REFUTES,
                 level=ConfidenceLevel.STRONG, basis="counterexample found",
                 counterexample=True, rubric_expression="C")
    jv = RecordedJudge(tmp_path).judge_proof("C", "f", None, [], {})
    assert jv.counterexample is True
    assert jv.direction == BearingDirection.REFUTES


def test_recorded_judge_absent_file_is_inconclusive_without_trail(tmp_path):
    # No verdicts/ dir at all -> inconclusive-shaped, no trail (engine refuses).
    jv = RecordedJudge(tmp_path).judge_proof("R", "f", None, [], {})
    assert jv.direction == BearingDirection.INCONCLUSIVE
    assert jv.trail is None


def test_recorded_judge_unmatched_criterion_is_inconclusive_without_trail(tmp_path):
    # A verdict file exists but for a DIFFERENT rule expression -> no match ->
    # inconclusive, no trail (the engine must not bind a mismatched verdict).
    _write_trail(tmp_path, "hyp-1", direction=BearingDirection.SUPPORTS,
                 level=ConfidenceLevel.STRONG, basis="A", rubric_expression="other")
    jv = RecordedJudge(tmp_path).judge_proof("the asked criterion", "f", None, [], {})
    assert jv.direction == BearingDirection.INCONCLUSIVE
    assert jv.trail is None


def test_recorded_judge_verdict_for_keys_by_hypothesis_id(tmp_path):
    _write_trail(tmp_path, "hyp-a", direction=BearingDirection.SUPPORTS,
                 level=ConfidenceLevel.STRONG, basis="A decisive")
    _write_trail(tmp_path, "hyp-b", direction=BearingDirection.REFUTES,
                 level=ConfidenceLevel.STRONG, basis="B decisive")
    judge = RecordedJudge(tmp_path)
    assert judge.verdict_for("hyp-a").direction == BearingDirection.SUPPORTS
    assert judge.verdict_for("hyp-b").direction == BearingDirection.REFUTES
    assert judge.verdict_for("hyp-missing") is None


# -- Fix 1 (P8): malformed verdict file -> clear ValueError, not a raw crash ----

def test_recorded_judge_malformed_json_raises_valueerror_naming_file(tmp_path):
    # A truncated / typo'd hand-authored verdict file must fail with a clear,
    # file-naming ValueError -- never a raw JSONDecodeError traceback.
    vdir = tmp_path / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    bad = vdir / "hyp-1.json"
    bad.write_text('{"hypothesis_id": "hyp-1", "rule_kind":', encoding="utf-8")  # truncated
    with pytest.raises(ValueError) as exc:
        RecordedJudge(tmp_path).judge_proof("R", "f", None, [], {})
    assert "hyp-1.json" in str(exc.value)
    assert "malformed verdict file" in str(exc.value)


def test_recorded_judge_invalid_schema_raises_valueerror_naming_file(tmp_path):
    # Valid JSON but missing required VerdictTrail fields -> pydantic ValidationError,
    # surfaced as the same clear, file-naming ValueError.
    vdir = tmp_path / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    bad = vdir / "hyp-2.json"
    bad.write_text(json.dumps({"hypothesis_id": "hyp-2"}), encoding="utf-8")  # no panel/chief
    with pytest.raises(ValueError) as exc:
        RecordedJudge(tmp_path).judge_proof("R", "f", None, [], {})
    assert "hyp-2.json" in str(exc.value)
    assert "malformed verdict file" in str(exc.value)


# -- Fix 2 (P4): two trails matching one criterion -> refuse, do not mis-route --

def test_recorded_judge_duplicate_criterion_raises_naming_collisions(tmp_path):
    # If two hypotheses' verdicts share the SAME rubric_expression, the kernel
    # cannot correctly attribute belief -> it must raise, not silently first-match.
    _write_trail(tmp_path, "hyp-a", direction=BearingDirection.SUPPORTS,
                 level=ConfidenceLevel.STRONG, basis="A", rubric_expression="shared R")
    _write_trail(tmp_path, "hyp-b", direction=BearingDirection.REFUTES,
                 level=ConfidenceLevel.STRONG, basis="B", rubric_expression="shared R")
    with pytest.raises(ValueError) as exc:
        RecordedJudge(tmp_path).judge_proof("shared R", "f", None, [], {})
    msg = str(exc.value)
    assert "hyp-a" in msg and "hyp-b" in msg
    assert "shared R" in msg
