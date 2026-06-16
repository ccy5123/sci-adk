"""
Unit 4 (RED-first): the ``sci-adk resolve <run-dir>`` verb.

design/rigor-shell-architecture.md §7.1: ``resolve`` drives the §5 checkpoint loop
over an existing run dir -- it prints the unresolved checkpoints (so the in-session
agent knows which ``verdicts/<hyp-id>.json`` to author) and reports the resolved
claims after re-entry. The existing ``run`` verb keeps working unchanged.

These tests use the T-1 capability's Spec but drive the loop with a fixture
executor (no Docker, no LLM) by writing a run dir directly, then invoking the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.cli import main
from sci_adk.core.claim import ConfidenceLevel
from sci_adk.core.evidence import BearingDirection
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verdict import (
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)
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
from sci_adk.core.evidence import (
    Bearing,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)

_PROOF_EXPR = "verified derivation => support; counterexample => refute"


def _proof_spec(spec_id: str, hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="m", expected_output="o"
        ),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="the universal claim",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.PROOF, expression=_PROOF_EXPR
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _seed_run(workspace: Path, spec: Spec, hyp_id: str = "hyp-1") -> Path:
    """Compile once via the loop to lay down spec.json / evidence/ / checkpoints/."""
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-1", spec_id=s.id, kind=EvidenceKind.PROOF_STEP,
                provenance=Provenance(code_ref="fixture"),
                result=Result(type="qualitative", finding="the attempted proof body"),
                bears_on=[Bearing(target_id=hyp_id,
                                  direction=BearingDirection.NEUTRAL)],
            )
        ]
    run_dir = workspace / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=workspace)
    return run_dir


def _write_verdict(run_dir: Path, hyp_id: str, *, direction, counterexample=False,
                   basis="panelist A decisive under R"):
    trail = VerdictTrail(
        hypothesis_id=hyp_id, rule_kind="proof", rubric_expression=_PROOF_EXPR,
        rubric_params=None,
        panel=[PanelVerdict(direction=direction, level=ConfidenceLevel.STRONG,
                            basis="panelist", counterexample=counterexample)],
        chief=ChiefVerdict(direction=direction, level=ConfidenceLevel.STRONG,
                           basis=basis, counterexample=counterexample),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{hyp_id}.json").write_text(
        json.dumps(trail.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def test_resolve_reports_unresolved_checkpoints(tmp_path, capsys):
    spec = _proof_spec("res-unresolved")
    run_dir = _seed_run(tmp_path, spec)
    # No verdict yet -> resolve should report the open checkpoint and exit 0.
    rc = main(["resolve", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hyp-1" in out
    assert "unresolved" in out.lower()


def test_resolve_reports_refuted_after_counterexample_verdict(tmp_path, capsys):
    spec = _proof_spec("res-refuted")
    run_dir = _seed_run(tmp_path, spec)
    _write_verdict(run_dir, "hyp-1", direction=BearingDirection.REFUTES,
                   counterexample=True, basis="counterexample constructed")
    rc = main(["resolve", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "refuted" in out.lower()


def test_resolve_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["resolve", str(tmp_path / "runs" / "does-not-exist")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not found" in err.lower() or "no spec" in err.lower()


def test_resolve_malformed_verdict_file_friendly_error_no_traceback(tmp_path, capsys):
    # Fix 1 (P8): a corrupt verdicts/<hyp>.json must produce a friendly stderr
    # message naming the offending file and a nonzero exit -- never a raw traceback.
    spec = _proof_spec("res-malformed")
    run_dir = _seed_run(tmp_path, spec)
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "hyp-1.json").write_text('{"hypothesis_id": "hyp-1",', encoding="utf-8")

    rc = main(["resolve", str(run_dir)])
    captured = capsys.readouterr()
    assert rc != 0
    assert "hyp-1.json" in captured.err
    assert "malformed verdict file" in captured.err
    # No raw traceback leaked to stderr.
    assert "Traceback (most recent call last)" not in captured.err


def test_run_verb_still_works(tmp_path, capsys):
    # Regression: the existing run verb must keep compiling unchanged.
    proposal = tmp_path / "p.md"
    proposal.write_text(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n",
        encoding="utf-8",
    )
    rc = main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "run-ok"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "compiled Spec 'run-ok'" in out
