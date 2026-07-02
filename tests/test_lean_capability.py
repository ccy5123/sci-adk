"""
Lean 4 formal-proof capability (adapter). A FAKE checker stands in for a real Lean+Mathlib
container (no Docker, no Lean), so these are deterministic and network-free -- exactly as
T-1 is tested with a fake experiment. They lock the contract:
  * checker PASS -> a FORMAL_PROOF item bearing SUPPORTS (the engine then binds SUPPORTED
    decisively, no judge / no human);
  * checker FAIL -> a PROOF_STEP item bearing NEUTRAL (the claim stays inconclusive).
"""

from __future__ import annotations

from typing import Any, Dict, List

from sci_adk.adapter.lean_capability import LeanProofTask, lean_experiment
from sci_adk.core.claim import ClaimStatus
from sci_adk.core.evidence import BearingDirection, EvidenceKind
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
from sci_adk.loop.compiler import ResearchCompiler

_HYP = "hyp-thm"
_NON_CIRC = "the checker verifies a property not baked into the statement generator"


def _proof_spec(spec_id: str) -> Spec:
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id=_HYP, statement="the theorem holds", mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.PROOF,
                expression="lean-verified => support; counterexample => refute"),
            referent="formal", non_circularity=_NON_CIRC)],
        method=MethodPlan(approaches=["lean"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=_HYP)],
    )


class _FakeLean:
    """A scripted Lean checker: returns a fixed exit code; records the command."""

    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        self.calls: List[List[str]] = []

    def execute_command(self, command: List[str], capture_output: bool = True) -> Dict[str, Any]:
        self.calls.append(command)
        return {
            "success": self.returncode == 0,
            "returncode": self.returncode,
            "stdout": "",
            "stderr": self.stderr,
            "provenance": {"image_name": "sci-adk-lean", "image_id": "sha256:fake"},
        }


def test_lean_pass_emits_formal_proof_supports(tmp_path):
    fake = _FakeLean(returncode=0)
    spec = _proof_spec("lean-pass")
    task = LeanProofTask(hypothesis_id=_HYP, lean_source="theorem t : True := trivial")
    items = lean_experiment([task], executor=fake)(spec, tmp_path)

    assert len(items) == 1
    assert items[0].kind is EvidenceKind.FORMAL_PROOF
    assert items[0].bears_on[0].direction is BearingDirection.SUPPORTS
    assert items[0].provenance.code_ref == "proof.lean"
    assert fake.calls == [["lean", "proof.lean"]]        # it ran the checker on the file
    assert (tmp_path / "proof.lean").read_text() == "theorem t : True := trivial"


def test_lean_error_exit0_is_not_verified(tmp_path):
    # REAL Lean behavior: `lean <file>` exits 0 EVEN on an error (it prints an `error:`
    # diagnostic). The capability must NOT trust exit code alone -> an `error:` in the
    # output means NOT verified (a NEUTRAL PROOF_STEP, not a FORMAL_PROOF).
    fake = _FakeLean(returncode=0, stderr="proof.lean:1:24: error: unsolved goals")
    spec = _proof_spec("lean-err")
    task = LeanProofTask(hypothesis_id=_HYP, lean_source="theorem t : False := by trivial")
    items = lean_experiment([task], executor=fake)(spec, tmp_path)

    assert len(items) == 1
    assert items[0].kind is EvidenceKind.PROOF_STEP     # NOT a FORMAL_PROOF, NOT a counterexample
    assert items[0].bears_on[0].direction is BearingDirection.NEUTRAL
    assert "did NOT verify" in (items[0].result.finding or "")


def test_lean_sorry_is_not_verified(tmp_path):
    # A `sorry` hole compiles with only a warning (exit 0). It is NOT a proof -> not verified.
    fake = _FakeLean(returncode=0, stderr="proof.lean:1:8: warning: declaration uses `sorry`")
    spec = _proof_spec("lean-sorry")
    task = LeanProofTask(hypothesis_id=_HYP, lean_source="theorem t : True := by sorry")
    items = lean_experiment([task], executor=fake)(spec, tmp_path)

    assert items[0].kind is EvidenceKind.PROOF_STEP
    assert "sorry" in (items[0].result.finding or "").lower()


def test_lean_pass_end_to_end_binds_supported_without_judge(tmp_path):
    # The capability + kernel together: a Lean PASS makes the PROOF claim SUPPORTED with no
    # judge and no human spot-check (the machine-checked resolution of PROOF -> SUPPORTED).
    fake = _FakeLean(returncode=0)
    spec = _proof_spec("lean-e2e")
    task = LeanProofTask(hypothesis_id=_HYP, lean_source="theorem t : True := trivial")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=lean_experiment([task], executor=fake))
    claim = {c.answers: c for c in result.claims}[_HYP]
    assert claim.status is ClaimStatus.SUPPORTED


def test_lean_fail_end_to_end_stays_proposed(tmp_path):
    # A failed check does not support and does not refute -> the claim stays PROPOSED
    # (inconclusive), never falsely SUPPORTED or REFUTED.
    fake = _FakeLean(returncode=0, stderr="proof.lean:1:0: error: unsolved goals")
    spec = _proof_spec("lean-e2e-fail")
    task = LeanProofTask(hypothesis_id=_HYP, lean_source="theorem t : False := by trivial")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=lean_experiment([task], executor=fake))
    claim = {c.answers: c for c in result.claims}[_HYP]
    assert claim.status is ClaimStatus.PROPOSED
