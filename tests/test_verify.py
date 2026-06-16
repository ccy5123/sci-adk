"""
RED-first: ``verify_run`` -- the headless, read-only belief audit (F6).

design/rigor-shell-architecture.md §6.2 / §7.1 / §8 F6: a third party re-derives the
belief from the *recorded* run and confirms it follows from the record -- without
Claude Code. verify:

  - re-applies the FROZEN ``DecisionRule`` to the RECORDED Evidence (numeric kinds
    autonomously; non-numeric via an injected ``RecordedJudge`` re-reading the
    recorded trails + the F2 gate) -- PURE, no persistence;
  - compares the re-derived ClaimStatus to the recorded ``Claim.status`` and reports
    per-hypothesis REPRODUCED / DIVERGED / UNRESOLVED;
  - is READ-ONLY: it re-runs NO experiment, calls NO LLM/capability, and overwrites
    NO recorded file;
  - is non-zero unless every recorded claim is reproduced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.core.claim import ClaimStatus
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
from sci_adk.loop.verify import VerifyOutcome, VerifyReport, verify_run

_PROOF_EXPR = "verified derivation => support; counterexample => refute"


# -- spec builders -----------------------------------------------------------

def _numeric_spec(spec_id: str, hyp_id: str = "hyp-n", value: float = 0.9) -> Spec:
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
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _proof_spec(spec_id: str, hyp_id: str = "hyp-p") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="the universal claim",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(kind=DecisionRuleKind.PROOF, expression=_PROOF_EXPR),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


# -- experiment seeders (fixture executors -- no Docker, no LLM) -------------

def _numeric_experiment(point: float, hyp_id: str = "hyp-n"):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            )
        ]
    return experiment


def _proof_experiment(hyp_id: str = "hyp-p"):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-proof", spec_id=s.id, kind=EvidenceKind.PROOF_STEP,
                provenance=Provenance(code_ref="fixture"),
                result=Result(type="qualitative", finding="the attempted proof body"),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.NEUTRAL)],
            )
        ]
    return experiment


def _seed(workspace: Path, spec: Spec, experiment) -> Path:
    run_dir = workspace / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=workspace)
    return run_dir


def _write_verdict(run_dir: Path, hyp_id: str, *, direction, counterexample=False,
                   basis="panelist A decisive under R", expr=_PROOF_EXPR):
    trail = VerdictTrail(
        hypothesis_id=hyp_id, rule_kind="proof", rubric_expression=expr, rubric_params=None,
        panel=[PanelVerdict(direction=direction, level="strong", basis="panelist",
                            counterexample=counterexample)],
        chief=ChiefVerdict(direction=direction, level="strong", basis=basis,
                           counterexample=counterexample),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{hyp_id}.json").write_text(
        json.dumps(trail.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def _resolve_proof(workspace: Path, spec_id: str) -> Path:
    """Seed a proof run AND record a counterexample verdict so its Claim is REFUTED."""
    spec = _proof_spec(spec_id)
    run_dir = _seed(workspace, spec, _proof_experiment())
    _write_verdict(run_dir, "hyp-p", direction=BearingDirection.REFUTES,
                   counterexample=True, basis="counterexample constructed")
    # Re-enter so the recorded claim is moved to REFUTED on disk.
    run_checkpoint_loop(run_dir=run_dir, spec=spec, workspace_dir=workspace)
    return run_dir


# -- (a) numeric claim reproduced -------------------------------------------

def test_verify_numeric_claim_reproduced(tmp_path):
    spec = _numeric_spec("v-num", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # 0.95 >= 0.9 -> supported
    report = verify_run(run_dir)
    assert isinstance(report, VerifyReport)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert by_hyp["hyp-n"].recorded_status == ClaimStatus.SUPPORTED
    assert by_hyp["hyp-n"].rederived_status == ClaimStatus.SUPPORTED
    assert by_hyp["hyp-n"].result == "REPRODUCED"
    assert report.all_reproduced is True


# -- (b) non-numeric claim re-derived from the recorded trail (reproduced) ----

def test_verify_nonnumeric_claim_reproduced_from_recorded_trail(tmp_path):
    run_dir = _resolve_proof(tmp_path, "v-proof")
    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    # The recorded claim is REFUTED (counterexample); verify re-derives the same from
    # the recorded trail via RecordedJudge -- no LLM.
    assert by_hyp["hyp-p"].recorded_status == ClaimStatus.REFUTED
    assert by_hyp["hyp-p"].rederived_status == ClaimStatus.REFUTED
    assert by_hyp["hyp-p"].result == "REPRODUCED"
    assert report.all_reproduced is True


def test_verify_nonnumeric_without_trail_is_unresolved(tmp_path):
    # A non-numeric hypothesis with NO recorded trail -> engine returns inconclusive
    # (F2) -> verify reports UNRESOLVED (not reproducible from record), not a clean
    # reproduction. There is no claims/ move, so the recorded claim is absent.
    spec = _proof_spec("v-proof-open")
    run_dir = _seed(tmp_path, spec, _proof_experiment())  # no verdict authored
    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert "hyp-p" in by_hyp
    assert by_hyp["hyp-p"].result == "UNRESOLVED"
    assert report.all_reproduced is False


# -- (c) DIVERGED: tamper a recorded claim -> verify catches it ---------------

def test_verify_diverged_when_recorded_claim_is_tampered(tmp_path):
    spec = _numeric_spec("v-div", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # genuinely supported
    # Tamper the recorded belief: flip the claim's status to refuted on disk.
    claim_path = run_dir / "claims" / "claim-hyp-n.json"
    blob = json.loads(claim_path.read_text(encoding="utf-8"))
    blob["status"] = "refuted"
    claim_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert by_hyp["hyp-n"].recorded_status == ClaimStatus.REFUTED
    assert by_hyp["hyp-n"].rederived_status == ClaimStatus.SUPPORTED
    assert by_hyp["hyp-n"].result == "DIVERGED"
    assert report.all_reproduced is False


def test_verify_diverged_when_recorded_evidence_is_tampered(tmp_path):
    # Tamper the recorded Evidence so the re-derived belief no longer matches the
    # recorded claim (which was computed from the original evidence).
    spec = _numeric_spec("v-div-ev", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # supported originally
    ev_path = run_dir / "evidence" / "ev-num.json"
    blob = json.loads(ev_path.read_text(encoding="utf-8"))
    blob["result"]["point"] = 0.10  # now below threshold -> re-derives refuted
    ev_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert by_hyp["hyp-n"].recorded_status == ClaimStatus.SUPPORTED
    assert by_hyp["hyp-n"].rederived_status == ClaimStatus.REFUTED
    assert by_hyp["hyp-n"].result == "DIVERGED"
    assert report.all_reproduced is False


# -- read-only invariant -----------------------------------------------------

def test_verify_is_read_only(tmp_path):
    spec = _numeric_spec("v-ro", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))

    def _snapshot(d: Path) -> dict:
        return {
            p.relative_to(d).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(d.rglob("*")) if p.is_file()
        }

    before = _snapshot(run_dir)
    verify_run(run_dir)
    after = _snapshot(run_dir)
    assert before.keys() == after.keys(), "verify created or deleted a file"
    for k in before:
        assert before[k][0] == after[k][0], f"verify modified file contents: {k}"


# -- Fix 1: verify shares ONE public verdict->status implementation -----------

def test_verify_uses_public_status_for_verdict_not_a_private_import():
    # The audit tool must NOT depend on a private name, and must NOT carry its own
    # copy of the verdict->status derivation (mapping + contested override). It must
    # reference the single public source of truth in claim_updater.
    import sci_adk.loop.verify as verify_mod
    from sci_adk.loop.claim_updater import status_for_verdict

    src = Path(verify_mod.__file__).read_text(encoding="utf-8")
    assert "_DIRECTION_TO_STATUS" not in src, "verify still imports the private mapping"
    assert "status_for_verdict" in src, "verify must call the public status_for_verdict"
    # And it is literally the same callable object (one implementation).
    assert verify_mod.status_for_verdict is status_for_verdict


def test_verify_report_carries_record_digest(tmp_path):
    spec = _numeric_spec("v-dig", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    report = verify_run(run_dir)
    assert isinstance(report.digest, str) and len(report.digest) == 64


def test_verify_missing_spec_raises(tmp_path):
    run_dir = tmp_path / "runs" / "nope"
    run_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises((FileNotFoundError, ValueError)):
        verify_run(run_dir)


# -- contested reproduction (mirror ClaimUpdater's CONTESTED override) --------

def test_verify_reproduces_contested_claim(tmp_path):
    # Two bearings -- one SUPPORTS, one REFUTES -> ClaimUpdater records CONTESTED.
    # verify must reproduce CONTESTED by applying the SAME override on the raw
    # bearings, not report a spurious DIVERGED.
    hyp_id = "hyp-c"
    spec = _numeric_spec("v-contested", hyp_id=hyp_id, value=0.9)

    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-sup", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="ev-ref", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.REFUTES)],
            ),
        ]
    run_dir = _seed(tmp_path, spec, experiment)
    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert by_hyp[hyp_id].recorded_status == ClaimStatus.CONTESTED
    assert by_hyp[hyp_id].rederived_status == ClaimStatus.CONTESTED
    assert by_hyp[hyp_id].result == "REPRODUCED"
    assert report.all_reproduced is True


def test_verify_outcome_is_frozen(tmp_path):
    spec = _numeric_spec("v-frozen", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    report = verify_run(run_dir)
    outcome = report.outcomes[0]
    assert isinstance(outcome, VerifyOutcome)
    with pytest.raises(Exception):
        outcome.result = "DIVERGED"  # frozen dataclass -> mutation refused
