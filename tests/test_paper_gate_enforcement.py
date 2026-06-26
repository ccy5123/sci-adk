"""
RED-first: SPEC-PAPER-GATE-001 M1 -- P1 non-vacuous refusal + P2 number-audit wiring.

These exercise the verify-side wiring (loop/verify.py):

  - P1 (MP-4, REQ-PG-101/108, OD-1 strict + OD-8 immediate): a conclusion-bearing artifact
    (ANY ``paper/draft.tex`` per-run, OR ANY ``package/`` workspace) with NO frozen contract
    (``pubreqs.json`` / ``pkgreqs.json``) must REFUSE -- the gate reports a loud, actionable
    failure naming what to freeze, replacing the old silent vacuously-clean ``return []``.

  - P2 (MP-1, REQ-PG-201/202/204): with a frozen contract present, the number-audit FAILS
    (and names the unbacked token + location) for a manuscript containing a quantitative token
    absent from the recorded-value pool, and PASSES for an otherwise-identical manuscript whose
    every token is recorded.

All fixtures use NEUTRAL synthetic data (no domain/venue/study). Pure + deterministic + no LLM.
"""

from __future__ import annotations

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
    Provenance,
    Result,
)
from sci_adk.core.pkgreqs import PackageReqs
from sci_adk.core.pubreqs import PubReqs
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
from sci_adk.loop.verify import verify_package, verify_run

_NON_CIRC = "the verifier checks a property not baked into the generator"


# -- neutral synthetic run builder -------------------------------------------

def _spec(spec_id: str = "spec-x", hyp: str = "hyp-a") -> Spec:
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id=hyp, statement="a recorded statement",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="point >= threshold => support",
                params={"statistic": "point", "op": ">=", "value": 0.5},
            ),
            referent="formal", non_circularity=_NON_CIRC,
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp)],
    )


def _write_run(run_dir: Path, *, point: float = 0.61, hyp: str = "hyp-a") -> None:
    """A minimal recorded run: spec.json + one Evidence item + one reproducing Claim."""
    spec = _spec(hyp=hyp)
    (run_dir).mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(spec.model_dump_json(), encoding="utf-8")

    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(exist_ok=True)
    ev = EvidenceItem(
        id="ev-1", spec_id=spec.id, kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=hyp, direction=BearingDirection.SUPPORTS)],
    )
    (ev_dir / "ev-1.json").write_text(ev.model_dump_json(), encoding="utf-8")

    cl_dir = run_dir / "claims"
    cl_dir.mkdir(exist_ok=True)
    claim = Claim(
        id=f"claim-{hyp}", spec_id=spec.id, answers=hyp,
        statement="a recorded statement", status=ClaimStatus.SUPPORTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (cl_dir / f"claim-{hyp}.json").write_text(claim.model_dump_json(), encoding="utf-8")


def _draft(run_dir: Path, body: str) -> None:
    paper = run_dir / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "draft.tex").write_text(body, encoding="utf-8")


def _freeze_pubreqs(run_dir: Path, **kw) -> None:
    pubreqs = PubReqs(spec_id="spec-x", digest="fixture-digest", **kw)
    (run_dir / "pubreqs.json").write_text(pubreqs.model_dump_json(), encoding="utf-8")


# ===========================================================================
# P1 -- non-vacuous refusal (MP-4, REQ-PG-101/108, OD-1 strict + OD-8 immediate)
# ===========================================================================

def test_per_run_draft_without_frozen_pubreqs_refuses(tmp_path):
    """A conclusion-bearing draft.tex + NO pubreqs.json -> loud refusal, gate FAILS."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    _draft(run_dir, r"\section{Results}The value is 0.61.")
    # NO pubreqs.json frozen.
    report = verify_run(run_dir)
    assert not report.paper_requirements_clean
    assert not report.passed
    joined = " ".join(report.paper_requirements_problems).lower()
    assert "frozen" in joined or "freeze" in joined
    assert "pubreqs" in joined


def test_per_run_draft_with_frozen_pubreqs_does_not_refuse(tmp_path):
    """Same draft WITH a frozen pubreqs.json (and clean numbers) -> no refusal."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    # point=0.61 and confidence 0.9 are recorded; 0.5 is the threshold (recorded).
    _draft(run_dir, r"\section{Results}The value is 0.61 (confidence 0.9).")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    refusal = [p for p in report.paper_requirements_problems if "frozen" in p.lower()]
    assert refusal == []


def test_per_run_no_draft_is_not_conclusion_bearing(tmp_path):
    """A run with NO paper/draft.tex is NOT conclusion-bearing -> no refusal (EC-1 spirit)."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    # No draft.tex, no pubreqs.json.
    report = verify_run(run_dir)
    assert report.paper_requirements_clean
    assert report.passed


def test_package_without_frozen_pkgreqs_refuses(tmp_path):
    """ANY package/ + NO pkgreqs.json -> loud refusal (OD-1 strict), gate FAILS."""
    ws = tmp_path
    pkg = ws / "package"
    pkg.mkdir()
    (pkg / "01_manuscript").mkdir()
    (pkg / "01_manuscript" / "main.tex").write_text(
        r"\section{Results}A value.", encoding="utf-8"
    )
    # NO pkgreqs.json.
    report = verify_package(ws)
    assert not report.package_requirements_clean
    assert not report.passed
    joined = " ".join(report.package_requirements_problems).lower()
    assert "frozen" in joined or "freeze" in joined
    assert "pkgreqs" in joined


def test_no_package_is_not_conclusion_bearing(tmp_path):
    """No package/ at all -> vacuously clean (nothing to gate), no refusal."""
    report = verify_package(tmp_path)
    assert report.package_requirements_clean
    assert report.passed


def test_per_run_refusal_does_not_weaken_claim_reproduction(tmp_path):
    """REQ-PG-107: the new refusal is ADDITIVE -- a non-reproducing claim still FAILS."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    # Tamper: rewrite the claim to a status that does NOT re-derive (point >= 0.5 => supported,
    # so a recorded REFUTED claim diverges).
    claim = Claim(
        id="claim-hyp-a", spec_id="spec-x", answers="hyp-a",
        statement="s", status=ClaimStatus.REFUTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (run_dir / "claims" / "claim-hyp-a.json").write_text(
        claim.model_dump_json(), encoding="utf-8"
    )
    report = verify_run(run_dir)
    assert not report.all_reproduced  # the existing record-green gate still fires
    assert not report.passed


# ===========================================================================
# P2 -- number-audit wiring (MP-1, REQ-PG-201/202/204)
# ===========================================================================

def test_per_run_number_audit_fails_on_unbacked_token(tmp_path):
    """A draft with a number absent from the recorded pool FAILS verify and names it."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    _draft(run_dir, r"\section{Results}The value is 0.61 but baseline 0.42 is unrecorded.")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert not report.paper_requirements_clean
    assert not report.passed
    joined = " ".join(report.paper_requirements_problems)
    assert "0.42" in joined
    assert "draft.tex" in joined


def test_per_run_number_audit_passes_on_fully_backed_manuscript(tmp_path):
    """The otherwise-identical manuscript whose every token is recorded PASSES (no false +)."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    # 0.61 (point), 0.9 (claim confidence), 0.5 (threshold) all recorded.
    _draft(run_dir, r"\section{Results}The value is 0.61 (confidence 0.9, threshold 0.5).")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean
    assert report.passed


def test_package_number_audit_fails_on_unbacked_token(tmp_path):
    """MP-1: a package main.tex with an unbacked number FAILS verify_package and names it."""
    ws = tmp_path
    pkg = ws / "package"
    (pkg / "01_manuscript").mkdir(parents=True)
    (pkg / "01_manuscript" / "main.tex").write_text(
        r"\section{Results}The recorded value 0.61, but 0.42 is unbacked.",
        encoding="utf-8",
    )
    data = pkg / "02_data"
    data.mkdir()
    (data / "claims_all.csv").write_text(
        "run_id,hyp_id,status,point_statistic,threshold\n"
        "r1,h1,supported,0.61,0.5\n",
        encoding="utf-8",
    )
    pkgreqs = PackageReqs(digest="fixture-digest")
    (ws / "pkgreqs.json").write_text(pkgreqs.model_dump_json(), encoding="utf-8")
    report = verify_package(ws)
    joined = " ".join(report.package_requirements_problems)
    assert "0.42" in joined
    assert "main.tex" in joined
    assert not report.package_requirements_clean


def test_package_number_audit_passes_on_backed_manuscript(tmp_path):
    """No false positive: a package whose every main.tex token is in 02_data passes the audit."""
    ws = tmp_path
    pkg = ws / "package"
    (pkg / "01_manuscript").mkdir(parents=True)
    (pkg / "01_manuscript" / "main.tex").write_text(
        r"\section{Results}The recorded value 0.61 over threshold 0.5.",
        encoding="utf-8",
    )
    data = pkg / "02_data"
    data.mkdir()
    (data / "claims_all.csv").write_text(
        "run_id,hyp_id,status,point_statistic,threshold\n"
        "r1,h1,supported,0.61,0.5\n",
        encoding="utf-8",
    )
    pkgreqs = PackageReqs(digest="fixture-digest")
    (ws / "pkgreqs.json").write_text(pkgreqs.model_dump_json(), encoding="utf-8")
    report = verify_package(ws)
    audit = [p for p in report.package_requirements_problems if "number audit" in p]
    assert audit == []
