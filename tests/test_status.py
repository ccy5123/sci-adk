"""
``sci-adk status <run>`` -- the terse, read-only session-state snapshot (D1, RED-first).

design/research-session-enforcement.md §6 D1: a read-only verb that reports WHAT IS
RECORDED and WHAT IS PENDING for a run dir, consumed by a future ``UserPromptSubmit``
re-anchor hook. It does NO recompile / experiment / LLM / write / re-derivation -- it
reports recorded statuses + open decisions only (re-derivation is ``verify``'s job).

These tests build fake run dirs (reusing the ``run_checkpoint_loop`` /
``ResearchCompiler`` seeders the verify/cli suites use) and assert that
``session_status``:

  - empty/missing run -> "nothing recorded" report, empty lists, exit-0-friendly;
  - a PROPOSED experiment claim -> listed unresolved; headline counts it;
  - a CONTESTED claim -> listed in contested;
  - a flagged result-novelty hyp with a PROPOSED ``claim-novelty-result-<hyp>`` ->
    novelty_unresolved lists ``"<hyp>:result"``; once a found_nothing decision of that
    kind is recorded (claim SUPPORTED) -> not listed;
  - prior_work open vs recorded;
  - a ``checkpoints/<hyp>.json`` without a matching ``verdicts/<hyp>.json`` ->
    awaiting-verdict; with the verdict present -> not.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
)
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
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
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.status import (
    StatusReport,
    render_status_text,
    session_status,
)

_NON_CIRC = "the verifier checks a property not baked into the generator"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _spec(spec_id: str, hyp_id: str = "hyp-x", novelty: bool = False,
          value: float = 0.9) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m",
                                 expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="s",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": value},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
                novelty_result=novelty,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _write_spec(run_dir: Path, spec: Spec) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2), encoding="utf-8")


def _write_claim(run_dir: Path, claim: Claim) -> None:
    claims_dir = run_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    (claims_dir / f"{claim.id}.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8")


def _claim(spec_id: str, hyp_id: str, status: ClaimStatus,
           *, novelty: bool = False, kind: str = "result") -> Claim:
    cid = f"claim-novelty-{kind}-{hyp_id}" if novelty else f"claim-{hyp_id}"
    return Claim(
        id=cid, spec_id=spec_id, answers=hyp_id, statement="c",
        status=status,
        confidence=Confidence(type=ConfidenceType.GRADED, level="moderate",
                              basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )


def _experiment_supports(point: float, hyp_id: str = "hyp-x"):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id,
                                  direction=BearingDirection.SUPPORTS)],
            ),
        ]
    return experiment


def _found_nothing_experiment(point: float, hyp_id: str = "hyp-x"):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id,
                                  direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-found-nothing", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:result:found_nothing"),
                result=Result(type="qualitative",
                              finding="result found_nothing: DOIs=['10.1/x']"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id=hyp_id, kind="result",
                    literature_evidence_id="evi-lit-x"),
            ),
        ]
    return experiment


# --------------------------------------------------------------------------- #
# empty / missing run dir
# --------------------------------------------------------------------------- #

def test_missing_run_dir_is_nothing_recorded(tmp_path):
    report = session_status(tmp_path / "runs" / "does-not-exist")
    assert isinstance(report, StatusReport)
    assert report.unresolved_claim_ids == []
    assert report.contested_claim_ids == []
    assert report.novelty_unresolved == []
    assert report.contested_pending == []
    assert report.checkpoints_awaiting_verdict == []
    assert report.prior_work_open is False
    assert "nothing recorded" in report.headline.lower()


def test_spec_present_no_claims_is_nothing_recorded(tmp_path):
    spec = _spec("sp-empty")
    _write_spec(tmp_path / "runs" / spec.id, spec)
    report = session_status(tmp_path / "runs" / spec.id)
    assert report.spec_id == "sp-empty"
    assert report.unresolved_claim_ids == []
    assert "nothing recorded" in report.headline.lower()


# --------------------------------------------------------------------------- #
# PROPOSED experiment claim -> unresolved
# --------------------------------------------------------------------------- #

def test_proposed_experiment_claim_is_unresolved(tmp_path):
    spec = _spec("sp-prop")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.PROPOSED))

    report = session_status(run_dir)
    assert "claim-hyp-x" in report.unresolved_claim_ids
    assert report.claim_counts.get("proposed") == 1
    assert "claim-hyp-x" not in report.contested_claim_ids
    # the headline mentions the unresolved count
    assert "1 unresolved" in report.headline


def test_supported_experiment_claim_is_not_unresolved(tmp_path):
    spec = _spec("sp-sup")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.SUPPORTED))

    report = session_status(run_dir)
    assert report.unresolved_claim_ids == []
    assert report.claim_counts.get("supported") == 1


# --------------------------------------------------------------------------- #
# CONTESTED claim -> contested list
# --------------------------------------------------------------------------- #

def test_contested_claim_is_listed(tmp_path):
    spec = _spec("sp-con")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.CONTESTED))

    report = session_status(run_dir)
    assert "claim-hyp-x" in report.contested_claim_ids
    assert report.claim_counts.get("contested") == 1
    # a contested claim is also a pending contested *decision* (no CONTESTED_RECORD yet)
    assert "hyp-x" in report.contested_pending


# --------------------------------------------------------------------------- #
# novelty open vs recorded
# --------------------------------------------------------------------------- #

def test_novelty_proposed_is_unresolved(tmp_path):
    """A flagged result-novelty hyp with a PROPOSED claim-novelty-result-<hyp> and no
    found_nothing decision -> novelty_unresolved lists ``"<hyp>:result"`` (the entry
    encodes both the hypothesis id and the kind)."""
    spec = _spec("sp-nov-open", novelty=True)
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.PROPOSED,
                                 novelty=True, kind="result"))

    report = session_status(run_dir)
    assert "hyp-x:result" in report.novelty_unresolved


def test_novelty_found_nothing_is_resolved(tmp_path):
    """Once a found_nothing NOVELTY_DECISION is recorded (the kind's claim SUPPORTED), the
    novelty checkpoint is closed -> not listed."""
    spec = _spec("sp-nov-closed", novelty=True)
    run_dir = tmp_path / "runs" / spec.id
    # the loop derives a SUPPORTED result-novelty claim from the found_nothing decision
    run_checkpoint_loop(run_dir=run_dir, spec=spec,
                        experiment=_found_nothing_experiment(0.95),
                        workspace_dir=tmp_path)

    nov_claim = run_dir / "claims" / "claim-novelty-result-hyp-x.json"
    assert json.loads(nov_claim.read_text(encoding="utf-8"))["status"] == "supported"

    report = session_status(run_dir)
    assert report.novelty_unresolved == []


# --------------------------------------------------------------------------- #
# prior-work open vs recorded
# --------------------------------------------------------------------------- #

def test_prior_work_open_when_no_decision_recorded(tmp_path):
    spec = _spec("sp-pw-open")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.PROPOSED))

    report = session_status(run_dir)
    assert report.prior_work_open is True


def test_prior_work_closed_when_decision_recorded(tmp_path):
    spec = _spec("sp-pw-closed")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.PROPOSED))
    # record an explicit PRIOR_WORK_DECISION (the only thing that closes the checkpoint)
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    item = EvidenceItem(
        id="evi-pw-decision", spec_id=spec.id,
        kind=EvidenceKind.PRIOR_WORK_DECISION,
        provenance=Provenance(code_ref="prior-work:skip"),
        result=Result(type="qualitative", finding="skipped: out of scope"),
        bears_on=[],
    )
    (ev_dir / "evi-pw-decision.json").write_text(
        json.dumps(item.model_dump(mode="json"), indent=2), encoding="utf-8")

    report = session_status(run_dir)
    assert report.prior_work_open is False


# --------------------------------------------------------------------------- #
# checkpoint awaiting a verdict
# --------------------------------------------------------------------------- #

def test_checkpoint_without_verdict_is_awaiting(tmp_path):
    spec = _spec("sp-ckpt")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    ckpt_dir = run_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    (ckpt_dir / "hyp-x.json").write_text("{}", encoding="utf-8")

    report = session_status(run_dir)
    assert "hyp-x" in report.checkpoints_awaiting_verdict


def test_checkpoint_with_verdict_is_not_awaiting(tmp_path):
    spec = _spec("sp-ckpt-done")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    ckpt_dir = run_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    (ckpt_dir / "hyp-x.json").write_text("{}", encoding="utf-8")
    verd_dir = run_dir / "verdicts"
    verd_dir.mkdir(parents=True, exist_ok=True)
    (verd_dir / "hyp-x.json").write_text("{}", encoding="utf-8")

    report = session_status(run_dir)
    assert "hyp-x" not in report.checkpoints_awaiting_verdict


def test_prior_work_checkpoint_not_in_awaiting_verdict(tmp_path):
    """Regression lock: ``checkpoints/prior_work.json`` is a RECORDING checkpoint whose
    open/closed state is the ``prior_work_open`` predicate, NOT a ``verdicts/<id>.json``
    trail -- so it must never be reported as awaiting a verdict (it has no verdict file
    by design). A real proof/qualitative ``checkpoints/<hyp>.json`` with no verdict still
    must be. Pins the ``if hyp_id == "prior_work": continue`` guard in
    ``_checkpoints_awaiting_verdict``."""
    spec = _spec("sp-ckpt-pw")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    ckpt_dir = run_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    # the prior-work recording checkpoint (never carries a verdict trail) ...
    (ckpt_dir / "prior_work.json").write_text("{}", encoding="utf-8")
    # ... alongside a real hypothesis checkpoint with no matching verdict
    (ckpt_dir / "hyp-x.json").write_text("{}", encoding="utf-8")

    report = session_status(run_dir)
    assert "hyp-x" in report.checkpoints_awaiting_verdict
    assert "prior_work" not in report.checkpoints_awaiting_verdict


# --------------------------------------------------------------------------- #
# headline + render
# --------------------------------------------------------------------------- #

def test_clean_run_headline_says_nothing_pending(tmp_path):
    spec = _spec("sp-clean")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.SUPPORTED))
    # close prior-work so nothing is pending
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    item = EvidenceItem(
        id="evi-pw", spec_id=spec.id, kind=EvidenceKind.PRIOR_WORK_DECISION,
        provenance=Provenance(code_ref="prior-work:skip"),
        result=Result(type="qualitative", finding="skipped"),
        bears_on=[],
    )
    (ev_dir / "evi-pw.json").write_text(
        json.dumps(item.model_dump(mode="json"), indent=2), encoding="utf-8")

    report = session_status(run_dir)
    assert "nothing pending" in report.headline.lower() \
        or "all recorded claims resolved" in report.headline.lower()


def test_render_status_text_headline_first_and_nonempty(tmp_path):
    spec = _spec("sp-render")
    run_dir = tmp_path / "runs" / spec.id
    _write_spec(run_dir, spec)
    _write_claim(run_dir, _claim(spec.id, "hyp-x", ClaimStatus.PROPOSED))

    report = session_status(run_dir)
    text = render_status_text(report)
    assert text  # non-empty
    assert text.splitlines()[0] == report.headline
    assert "claim-hyp-x" in text


# --------------------------------------------------------------------------- #
# only hypothesis judge checkpoints await a verdict (real-run checkpoints/ dir)
# --------------------------------------------------------------------------- #

_REAL_RUN = Path(__file__).parent / "fixtures" / "amend_bcfkow" / "run"


def _copy_real_run(tmp_path: Path) -> Path:
    """Copy the real BCF/Kow run (spec + evidence + prior_work.json + an empty
    science.json) to <tmp>/runs/<spec.id> and add the amendment receipt that
    amend-spec writes next to them."""
    import shutil

    spec_id = json.loads((_REAL_RUN / "spec.json").read_text(encoding="utf-8"))["id"]
    run_dir = tmp_path / "runs" / spec_id
    shutil.copytree(_REAL_RUN, run_dir)
    (run_dir / "checkpoints" / "amendment-v2.json").write_text(json.dumps({
        "spec_id": spec_id, "prior_version": 1, "new_version": 2,
        "rationale": "method rewritten", "recorded_at": "2026-10-08T12:00:00+00:00",
        "prior_spec_sha256": "0" * 64,
    }), encoding="utf-8")
    return run_dir


def test_science_audit_and_amendment_receipt_never_await_a_verdict(tmp_path):
    """Regression: a real run reported "2 checkpoints awaiting verdict" for
    science.json (0 findings) and amendment-v2.json. Neither is a judge
    checkpoint; neither is cleared by a verdicts/<id>.json."""
    run_dir = _copy_real_run(tmp_path)
    assert sorted(p.name for p in (run_dir / "checkpoints").iterdir()) == [
        "amendment-v2.json", "prior_work.json", "science.json"]

    report = session_status(run_dir)
    assert report.checkpoints_awaiting_verdict == []
    assert "awaiting verdict" not in report.headline


def test_science_findings_are_not_verdict_checkpoints(tmp_path):
    """Science-guard findings are resolved by a Spec amendment that re-runs the audit
    (design/science-guards.md), never by a recorded verdict -- so even a science.json
    WITH findings is not counted as awaiting a verdict."""
    run_dir = _copy_real_run(tmp_path)
    (run_dir / "checkpoints" / "science.json").write_text(json.dumps({"findings": [
        {"guard": "G2", "hypothesis_id": "H1", "message": "no power analysis"}]}),
        encoding="utf-8")

    assert session_status(run_dir).checkpoints_awaiting_verdict == []


def test_contested_and_novelty_reminders_are_not_verdict_checkpoints(tmp_path):
    """<hyp>.contested.json / <hyp>.novelty.json reminders close on a recorded
    Evidence decision (reported via contested_pending / novelty_unresolved), not on a
    verdicts/ file -- they must not be counted here as well."""
    run_dir = _copy_real_run(tmp_path)
    ckpt = run_dir / "checkpoints"
    base = {"hypothesis_id": "H1", "spec_id": "SPEC-BCFKOW-001", "spec_version": 1,
            "prompt": "p"}
    (ckpt / "H1.contested.json").write_text(
        json.dumps({"checkpoint_type": "contested", **base}), encoding="utf-8")
    (ckpt / "H1.novelty.json").write_text(
        json.dumps({"checkpoint_type": "novelty", **base}), encoding="utf-8")

    assert session_status(run_dir).checkpoints_awaiting_verdict == []


def test_real_run_judge_checkpoint_still_awaits_until_verdict(tmp_path):
    """A proof/qualitative judge checkpoint <hyp>.json beside the non-verdict files
    is still counted, and stops being counted once verdicts/<hyp>.json exists."""
    run_dir = _copy_real_run(tmp_path)
    (run_dir / "checkpoints" / "H2.json").write_text(json.dumps({
        "checkpoint_type": "judge", "hypothesis_id": "H2", "kind": "qualitative",
        "expression": "e", "finding": "", "spec_version": 2}), encoding="utf-8")

    report = session_status(run_dir)
    assert report.checkpoints_awaiting_verdict == ["H2"]
    assert "1 checkpoint awaiting verdict" in report.headline

    (run_dir / "verdicts").mkdir()
    (run_dir / "verdicts" / "H2.json").write_text("{}", encoding="utf-8")
    assert session_status(run_dir).checkpoints_awaiting_verdict == []
