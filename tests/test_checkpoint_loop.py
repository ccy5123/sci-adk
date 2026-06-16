"""
Unit 3 (RED-first): the turnkey checkpoint loop + typed checkpoint persistence.

design/rigor-shell-architecture.md §5: ``run_checkpoint_loop`` is a thin, no-LLM
kernel-side orchestrator that
  (1) compiles;
  (2) writes typed ``checkpoints/<hyp-id>.json`` (and keeps the ``checkpoints.md``
      human view);
  (3) re-enters with ``RecordedJudge(run_dir)`` injected when verdict files exist;
  (4) reaches a FIXPOINT -- recompile until no new checkpoint appears (a confident
      PROOF raises an engine-generated human-spot-check checkpoint on recompile);
  (5) is idempotent per F5 -- it does not re-run the experiment when Evidence for
      this (spec version + capability) already exists; reuses it.

These tests are deterministic: a fake experiment hook stands in for Docker, and
verdicts are written to disk (no LLM is ever invoked).
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.core.claim import ClaimStatus, ConfidenceLevel
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
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
from sci_adk.loop.checkpoint_loop import LoopResult, run_checkpoint_loop
from sci_adk.loop.verdict import (
    CheckpointModel,
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)

_NUM_RULE = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="collision_count == 0 => support",
    params={"statistic": "point", "op": "==", "value": 0.0},
)
_QUAL_EXPR = "the construction is clear, novel, and correct"
_QUAL_RULE = DecisionRule(kind=DecisionRuleKind.QUALITATIVE, expression=_QUAL_EXPR)
_PROOF_EXPR = "verified derivation => support; counterexample => refute"
_PROOF_RULE = DecisionRule(kind=DecisionRuleKind.PROOF, expression=_PROOF_EXPR)


def _spec(spec_id: str, rule: DecisionRule, hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="method", expected_output="out"
        ),
        hypotheses=[
            Hypothesis(id=hyp_id, statement="the claim under test",
                       mode=HypothesisMode.CONFIRMATORY, decision_rule=rule)
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _point_experiment(point: float, hyp_id: str = "hyp-1"):
    def fn(spec, workspace_dir):
        return [
            EvidenceItem(
                id="ev-num",
                spec_id=spec.id,
                kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fake"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.NEUTRAL)],
            )
        ]
    return fn


def _finding_experiment(finding: str, hyp_id: str = "hyp-1"):
    def fn(spec, workspace_dir):
        return [
            EvidenceItem(
                id="ev-find",
                spec_id=spec.id,
                kind=EvidenceKind.PROOF_STEP,
                provenance=Provenance(code_ref="fake"),
                result=Result(type="qualitative", finding=finding),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.NEUTRAL)],
            )
        ]
    return fn


def _write_verdict(run_dir: Path, hyp_id: str, rule: DecisionRule, *, direction,
                   level=ConfidenceLevel.STRONG, basis="decisive under R",
                   counterexample=False):
    trail = VerdictTrail(
        hypothesis_id=hyp_id,
        rule_kind=rule.kind.value,
        rubric_expression=rule.expression,
        rubric_params=rule.params,
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


# -- numeric-only: one pass, no judge ----------------------------------------

def test_numeric_only_spec_resolves_in_one_pass(tmp_path):
    result = run_checkpoint_loop(
        run_dir=tmp_path / "runs" / "num", spec=_spec("num", _NUM_RULE),
        experiment=_point_experiment(0.0), workspace_dir=tmp_path,
    )
    assert isinstance(result, LoopResult)
    assert result.unresolved == []
    assert len(result.claims) == 1
    assert result.claims[0].status == ClaimStatus.SUPPORTED
    assert result.iterations == 1  # numeric needs no re-entry


# -- typed checkpoint persistence --------------------------------------------

def test_loop_writes_typed_checkpoint_json_and_markdown_view(tmp_path):
    run_dir = tmp_path / "runs" / "qual"
    run_checkpoint_loop(
        run_dir=run_dir, spec=_spec("qual", _QUAL_RULE),
        experiment=_finding_experiment("a clear construction"), workspace_dir=tmp_path,
    )
    cp_json = run_dir / "checkpoints" / "hyp-1.json"
    assert cp_json.exists()
    cp = CheckpointModel.model_validate(json.loads(cp_json.read_text()))
    assert cp.hypothesis_id == "hyp-1"
    assert cp.kind == "qualitative"
    assert "clear construction" in cp.finding
    # The human view is still generated.
    assert (run_dir / "checkpoints.md").exists()


# -- qualitative: resolves on re-entry ---------------------------------------

def test_qualitative_unresolved_then_resolves_on_reentry(tmp_path):
    run_dir = tmp_path / "runs" / "qual2"
    spec = _spec("qual2", _QUAL_RULE)

    # First pass: no verdict on disk -> the qualitative hypothesis is unresolved.
    first = run_checkpoint_loop(
        run_dir=run_dir, spec=spec,
        experiment=_finding_experiment("clear and novel"), workspace_dir=tmp_path,
    )
    assert "hyp-1" in first.unresolved
    assert first.claims[0].status == ClaimStatus.PROPOSED  # inconclusive

    # Agent authors the verdict; re-enter -> RecordedJudge resolves it.
    _write_verdict(run_dir, "hyp-1", _QUAL_RULE, direction=BearingDirection.SUPPORTS)
    second = run_checkpoint_loop(
        run_dir=run_dir, spec=spec,
        experiment=_finding_experiment("clear and novel"), workspace_dir=tmp_path,
    )
    assert second.unresolved == []
    assert second.claims[0].status == ClaimStatus.SUPPORTED


# -- proof: confident verified does NOT auto-support (fixpoint spot-check) ----

def test_proof_confident_verified_does_not_auto_support_raises_spotcheck(tmp_path):
    run_dir = tmp_path / "runs" / "proof"
    spec = _spec("proof", _PROOF_RULE)
    _write_verdict(run_dir, "hyp-1", _PROOF_RULE, direction=BearingDirection.SUPPORTS,
                   basis="derivation verified, panelist A decisive")
    result = run_checkpoint_loop(
        run_dir=run_dir, spec=spec,
        experiment=_finding_experiment("the proof body"), workspace_dir=tmp_path,
    )
    # The engine refuses to self-certify the proof: it stays unresolved (the human
    # spot-check the engine demands is itself an open checkpoint), never SUPPORTED.
    assert result.claims[0].status != ClaimStatus.SUPPORTED
    assert "hyp-1" in result.unresolved
    assert "spot-check" in result.claims[0].confidence.basis.lower()
    # Fixpoint terminated (did not loop forever on the engine-raised checkpoint).
    assert result.iterations >= 1


def test_proof_counterexample_verdict_refutes(tmp_path):
    run_dir = tmp_path / "runs" / "proof-cx"
    spec = _spec("proof-cx", _PROOF_RULE)
    _write_verdict(run_dir, "hyp-1", _PROOF_RULE, direction=BearingDirection.REFUTES,
                   basis="a counterexample was constructed", counterexample=True)
    result = run_checkpoint_loop(
        run_dir=run_dir, spec=spec,
        experiment=_finding_experiment("attempted proof"), workspace_dir=tmp_path,
    )
    assert result.claims[0].status == ClaimStatus.REFUTED
    assert result.unresolved == []  # a decisive refutation is resolved


# -- idempotency (F5) --------------------------------------------------------

def test_loop_is_idempotent_reuses_evidence_no_spurious_status_change(tmp_path):
    run_dir = tmp_path / "runs" / "idem"
    spec = _spec("idem", _QUAL_RULE)
    _write_verdict(run_dir, "hyp-1", _QUAL_RULE, direction=BearingDirection.SUPPORTS)

    runs = []

    def counting_experiment(s, w):
        runs.append(1)
        return _finding_experiment("clear")(s, w)

    first = run_checkpoint_loop(
        run_dir=run_dir, spec=spec, experiment=counting_experiment,
        workspace_dir=tmp_path,
    )
    n_runs_after_first = len(runs)
    first_status = first.claims[0].status
    first_history_len = len(first.claims[0].history)

    second = run_checkpoint_loop(
        run_dir=run_dir, spec=spec, experiment=counting_experiment,
        workspace_dir=tmp_path,
    )
    # Same Claim status; no spurious StatusChange appended; experiment NOT re-run
    # (Evidence for this spec version already exists -> reuse, F5).
    assert second.claims[0].status == first_status == ClaimStatus.SUPPORTED
    assert len(second.claims[0].history) == first_history_len
    assert len(runs) == n_runs_after_first  # experiment not re-executed on re-run
