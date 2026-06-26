"""
RED-first: the ``sci-adk verify <run-dir>`` verb.

design/rigor-shell-architecture.md §7.1 / §8 F6: ``verify`` re-applies the frozen
criteria to the recorded Evidence (NOT a re-run), with no capability and no LLM, so a
third party can audit the verdicts without Claude Code. CI-style: exit 0 iff every
recorded claim is reproduced; non-zero on any DIVERGED / UNRESOLVED. The existing
``run`` / ``resolve`` verbs keep working unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.cli import main
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
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verdict import (
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)


def _numeric_spec(spec_id: str, hyp_id: str = "hyp-n", value: float = 0.9) -> Spec:
    # referent='formal' + attestation: a computational claim whose recorded Evidence is
    # 'generated' (see _seed_numeric). Lets the evidence-validity gate allow the binding
    # SUPPORTS verdict during seeding (design/evidence-validity.md); verify then audits.
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="the numeric claim",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": value},
                ),
                referent="formal",
                non_circularity="the verifier checks a property not baked into the generator",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _seed_numeric(workspace: Path, spec: Spec, point: float, hyp_id: str = "hyp-n") -> Path:
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            )
        ]
    run_dir = workspace / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=workspace)
    return run_dir


def test_verify_reproduced_exits_zero(tmp_path, capsys):
    spec = _numeric_spec("cli-ok", value=0.9)
    run_dir = _seed_numeric(tmp_path, spec, 0.95)
    _freeze_minimal_pubreqs(run_dir)  # M1: the seeded draft.tex is conclusion-bearing
    rc = main(["verify", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hyp-n" in out
    assert "REPRODUCED" in out
    assert "digest" in out.lower()


def test_verify_diverged_exits_nonzero(tmp_path, capsys):
    spec = _numeric_spec("cli-div", value=0.9)
    run_dir = _seed_numeric(tmp_path, spec, 0.95)
    # Tamper the recorded claim status.
    claim_path = run_dir / "claims" / "claim-hyp-n.json"
    blob = json.loads(claim_path.read_text(encoding="utf-8"))
    blob["status"] = "refuted"
    claim_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    rc = main(["verify", str(run_dir)])
    out = capsys.readouterr().out
    assert rc != 0
    assert "DIVERGED" in out


def test_verify_prints_digest_and_is_stable_run_to_run(tmp_path, capsys):
    spec = _numeric_spec("cli-dig", value=0.9)
    run_dir = _seed_numeric(tmp_path, spec, 0.95)
    main(["verify", str(run_dir)])
    out1 = capsys.readouterr().out
    main(["verify", str(run_dir)])
    out2 = capsys.readouterr().out
    # The printed digest line is identical run-to-run (deterministic).
    dig1 = [ln for ln in out1.splitlines() if "digest" in ln.lower()]
    dig2 = [ln for ln in out2.splitlines() if "digest" in ln.lower()]
    assert dig1 and dig1 == dig2


def test_verify_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["verify", str(tmp_path / "runs" / "does-not-exist")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err.lower() or "no spec" in err.lower()


# -- Fix 2: ambiguous criterion -> friendly error, not a raw traceback --------

_SHARED_EXPR = "verified derivation => support; counterexample => refute"


def _ambiguous_proof_spec(spec_id: str) -> Spec:
    """Two proof hypotheses that share an IDENTICAL rule.expression.

    RecordedJudge cannot attribute belief under that ambiguity (the Judge Protocol
    carries the criterion, not the hypothesis id) and raises ValueError. verify must
    surface that as a friendly error, never a raw traceback.
    """
    def hyp(hid: str) -> Hypothesis:
        return Hypothesis(
            id=hid, statement=f"claim {hid}", mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(kind=DecisionRuleKind.PROOF, expression=_SHARED_EXPR),
        )
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[hyp("hyp-a"), hyp("hyp-b")],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-a")],
    )


def _write_trail(run_dir: Path, hyp_id: str) -> None:
    trail = VerdictTrail(
        hypothesis_id=hyp_id, rule_kind="proof", rubric_expression=_SHARED_EXPR,
        rubric_params=None,
        panel=[PanelVerdict(direction=BearingDirection.SUPPORTS, level="strong",
                            basis="panelist")],
        chief=ChiefVerdict(direction=BearingDirection.SUPPORTS, level="strong",
                           basis="decisive under R"),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{hyp_id}.json").write_text(
        json.dumps(trail.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def test_verify_ambiguous_criterion_friendly_error_no_traceback(tmp_path, capsys):
    spec = _ambiguous_proof_spec("cli-ambig")

    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-1", spec_id=s.id, kind=EvidenceKind.PROOF_STEP,
                provenance=Provenance(code_ref="fixture"),
                result=Result(type="qualitative", finding="proof body"),
                bears_on=[
                    Bearing(target_id="hyp-a", direction=BearingDirection.NEUTRAL),
                    Bearing(target_id="hyp-b", direction=BearingDirection.NEUTRAL),
                ],
            )
        ]
    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=tmp_path)
    # Two trails sharing the same rubric_expression -> ambiguous match in RecordedJudge.
    _write_trail(run_dir, "hyp-a")
    _write_trail(run_dir, "hyp-b")

    rc = main(["verify", str(run_dir)])
    captured = capsys.readouterr()
    assert rc != 0
    # Friendly stderr naming the collision, no raw traceback leaked.
    assert "ambiguous" in captured.err.lower()
    assert "hyp-a" in captured.err and "hyp-b" in captured.err
    assert "Traceback (most recent call last)" not in captured.err


# -- Phase 3: the paper-consistency gate via the CLI (D4) ---------------------

def _write_paper(run_dir: Path, name: str, tex: str) -> None:
    paper = run_dir / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / name).write_text(tex, encoding="utf-8")


def _freeze_minimal_pubreqs(run_dir: Path) -> None:
    """Freeze a minimal compliant pubreqs.json so the SPEC-PAPER-GATE-001 P1 refusal is
    silenced for a conclusion-bearing draft.tex (M1, OD-1 strict + OD-8 immediate). These CLI
    tests target the exit-code behaviour of OTHER gates, so they freeze the smallest contract."""
    from sci_adk.core.pubreqs import PubReqs as _PubReqs
    from sci_adk.provenance import pubreqs_digest as _pubreqs_digest

    pr = _PubReqs(
        spec_id=run_dir.name, required_sections=[], figure_font_policy=False,
        image_min_dpi=None, reference_style=None, max_words=None,
        reproduction_bundle=False,
    )
    pr = pr.model_copy(update={"digest": _pubreqs_digest(pr)})
    (run_dir / "pubreqs.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")


def test_verify_inconsistent_paper_exits_nonzero_and_prints_unresolved(tmp_path, capsys):
    # A reproducing run whose RENDERED draft.tex has a dangling \ref must exit non-zero
    # (the combined gate) and print the unresolved reference so a third party sees why.
    spec = _numeric_spec("cli-paper-bad", value=0.9)
    run_dir = _seed_numeric(tmp_path, spec, 0.95)  # claim genuinely reproduces
    _write_paper(run_dir, "draft.tex", r"See Figure~\ref{fig:ghost}.")  # no \label

    rc = main(["verify", str(run_dir)])
    captured = capsys.readouterr()
    assert rc != 0
    # The claim still reproduces, but the paper gate fails -- and the report names the
    # broken reference + the offending file.
    combined = captured.out + captured.err
    assert "fig:ghost" in combined
    assert "draft.tex" in combined


def test_verify_consistent_paper_exits_zero(tmp_path, capsys):
    spec = _numeric_spec("cli-paper-ok", value=0.9)
    run_dir = _seed_numeric(tmp_path, spec, 0.95)
    _write_paper(run_dir, "draft.tex", r"\label{fig:a} See Figure~\ref{fig:a}.")
    _write_paper(run_dir, "si.tex", r"\label{tab:s1}\ref{tab:s1}")
    _freeze_minimal_pubreqs(run_dir)  # M1: a draft.tex is conclusion-bearing -> needs a contract

    rc = main(["verify", str(run_dir)])
    assert rc == 0


def test_verify_no_paper_exits_zero_unchanged(tmp_path, capsys):
    # No paper/draft.tex -> the run is NOT conclusion-bearing, the paper gate is vacuously
    # satisfied; exit behavior is unchanged (M1: the vacuous-clean path survives for a
    # pre-paper run). _seed_numeric renders a paper/, so remove it to exercise the path.
    import shutil

    spec = _numeric_spec("cli-paper-none", value=0.9)
    run_dir = _seed_numeric(tmp_path, spec, 0.95)
    shutil.rmtree(run_dir / "paper")
    rc = main(["verify", str(run_dir)])
    assert rc == 0
