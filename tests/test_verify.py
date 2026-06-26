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

# These verify tests audit computational (formal) claims whose recorded Evidence is
# 'generated' (the experiment seeders below). referent='formal' + a non-circularity
# attestation let the evidence-validity gate ALLOW the binding verdicts during seeding
# (design/evidence-validity.md); verify then re-derives belief from the recorded run.
_NON_CIRC = "the verifier checks a property not baked into the generator"


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
                referent="formal",
                non_circularity=_NON_CIRC,
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
                referent="formal",
                non_circularity=_NON_CIRC,
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
                provenance=Provenance(code_ref="fixture", data_source="generated"),
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
                provenance=Provenance(code_ref="fixture", data_source="generated"),
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
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="ev-ref", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
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


# -- Phase 3: paper consistency as a verify-style HARD gate (D4) --------------
# verify becomes a third party that re-checks the RENDERED paper's internal
# \ref<->\label integrity (draft.tex AND si.tex), read-only, and fails the gate on a
# broken reference -- EVEN IF every claim reproduces. The claim signal (all_reproduced)
# keeps its meaning; the new fields (paper_consistency, paper_consistent, passed) sit
# alongside, and the combined exit gate is all_reproduced AND paper_consistent.

from sci_adk.render.consistency import LatexRefReport  # noqa: E402


def _write_paper(run_dir: Path, name: str, tex: str) -> None:
    paper = run_dir / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / name).write_text(tex, encoding="utf-8")


def _freeze_minimal_pubreqs(run_dir: Path) -> None:
    """Freeze a minimal compliant pubreqs.json so the SPEC-PAPER-GATE-001 P1 refusal is
    silenced for a conclusion-bearing draft.tex.

    Under the M1 non-vacuous posture (OD-1 strict + OD-8 immediate), ANY paper/draft.tex is a
    conclusion-bearing artifact that REQUIRES a frozen publishing contract -- a run that renders
    a paper but freezes no pubreqs.json now REFUSES (no silent clean pass). These tests target
    OTHER gates (consistency / cross-doc / tool-vocab), so they freeze the smallest contract
    that turns every contract-declared sub-check off; the P1 refusal and the P2 number-audit
    (which is unconditional once a draft exists) remain in force.
    """
    from sci_adk.core.pubreqs import PubReqs as _PubReqs
    from sci_adk.provenance import pubreqs_digest as _pubreqs_digest

    pr = _PubReqs(
        spec_id=run_dir.name, required_sections=[], figure_font_policy=False,
        image_min_dpi=None, reference_style=None, max_words=None,
        reproduction_bundle=False,
    )
    pr = pr.model_copy(update={"digest": _pubreqs_digest(pr)})
    (run_dir / "pubreqs.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")


def test_verify_no_paper_is_consistent(tmp_path):
    # A run with NO paper/ dir: paper_consistent is True (nothing to check), exit gate
    # unchanged. The new fields exist; paper_consistency is empty. (_seed renders a
    # paper/ via the compiler, so remove it to exercise the genuine no-paper path.)
    spec = _numeric_spec("v-nopaper", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    import shutil
    shutil.rmtree(run_dir / "paper")
    report = verify_run(run_dir)
    assert report.paper_consistency == {}
    assert report.paper_consistent is True
    assert report.all_reproduced is True
    assert report.passed is True


def test_verify_seeded_skeletal_paper_is_consistent(tmp_path):
    # The real compiler-rendered draft.tex + si.tex (no figures, no broken refs) MUST be
    # internally consistent -- the gate does not false-fail on a clean skeleton.
    spec = _numeric_spec("v-skeleton", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # compiler writes paper/
    _freeze_minimal_pubreqs(run_dir)  # M1: a draft.tex is conclusion-bearing -> needs a contract
    report = verify_run(run_dir)
    assert set(report.paper_consistency) == {"draft.tex", "si.tex"}
    assert report.paper_consistent is True
    assert report.passed is True


def test_verify_consistent_paper_passes(tmp_path):
    spec = _numeric_spec("v-goodpaper", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\label{fig:a} See Figure~\ref{fig:a}.")
    _write_paper(run_dir, "si.tex",
                 r"\label{tab:s1} Table~\ref{tab:s1}.")
    _freeze_minimal_pubreqs(run_dir)  # M1: a draft.tex is conclusion-bearing -> needs a contract
    report = verify_run(run_dir)
    assert set(report.paper_consistency) == {"draft.tex", "si.tex"}
    assert all(isinstance(r, LatexRefReport) for r in report.paper_consistency.values())
    assert report.paper_consistency["draft.tex"].ok is True
    assert report.paper_consistent is True
    assert report.all_reproduced is True
    assert report.passed is True


def test_verify_dangling_ref_in_draft_fails_gate_even_if_claims_reproduce(tmp_path):
    # The headline Phase-3 gate: a dangling \ref in draft.tex makes paper_consistent
    # False and passed False, EVEN THOUGH the claim reproduces (all_reproduced True).
    spec = _numeric_spec("v-ghostref", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # claim genuinely supported
    _write_paper(run_dir, "draft.tex", r"See Figure~\ref{fig:ghost}.")  # no \label
    report = verify_run(run_dir)
    assert report.all_reproduced is True            # claim signal UNCHANGED in meaning
    assert "draft.tex" in report.paper_consistency
    assert report.paper_consistency["draft.tex"].unresolved_refs == ["fig:ghost"]
    assert report.paper_consistency["draft.tex"].ok is False
    assert report.paper_consistent is False
    assert report.passed is False                   # combined gate fails


def test_verify_dangling_ref_in_si_fails_gate(tmp_path):
    # The gate covers si.tex too (both documents are checked WITHIN themselves).
    spec = _numeric_spec("v-sighost", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a}")  # draft is clean
    _write_paper(run_dir, "si.tex", r"Table~\ref{tab:ghost}.")        # si is broken
    report = verify_run(run_dir)
    assert report.paper_consistency["draft.tex"].ok is True
    assert report.paper_consistency["si.tex"].ok is False
    assert report.paper_consistency["si.tex"].unresolved_refs == ["tab:ghost"]
    assert report.paper_consistent is False
    assert report.passed is False


def test_verify_duplicate_label_fails_gate(tmp_path):
    spec = _numeric_spec("v-duplabel", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a}\label{fig:a}")
    report = verify_run(run_dir)
    assert report.paper_consistency["draft.tex"].duplicate_labels == ["fig:a"]
    assert report.paper_consistent is False
    assert report.passed is False


# -- cross-document "Figure/Table S<n>" gate (main paper -> SI) ----------------
# A real \ref cannot cross the compile boundary, so a main paper cites SI floats as the
# plain text "Figure S1"; the within-document gate never sees it. This static gate counts
# the SI's floats and fails the combined exit gate on a citation past that count.

def test_verify_seeded_skeleton_is_cross_doc_clean(tmp_path):
    # The compiler-rendered skeleton cites no "Figure S<n>", so the cross-doc gate is
    # vacuously clean -- it must not false-fail an ordinary run.
    spec = _numeric_spec("v-xdoc-skeleton", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _freeze_minimal_pubreqs(run_dir)  # M1: a draft.tex is conclusion-bearing -> needs a contract
    report = verify_run(run_dir)
    assert report.paper_cross_doc_refs == []
    assert report.paper_cross_doc_clean is True
    assert report.passed is True


def test_verify_resolved_cross_doc_s_ref_passes(tmp_path):
    # draft cites "Figure S1"; the SI has one captioned figure (-> Figure S1) -> resolves.
    spec = _numeric_spec("v-xdoc-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"As shown in Figure S1, the property holds.")
    _write_paper(run_dir, "si.tex",
                 r"\begin{figure}[htbp]\caption{a}\label{fig:a}\end{figure}")
    _freeze_minimal_pubreqs(run_dir)  # M1: a draft.tex is conclusion-bearing -> needs a contract
    report = verify_run(run_dir)
    assert report.paper_cross_doc_refs == []
    assert report.paper_cross_doc_clean is True
    assert report.passed is True


def test_verify_dangling_cross_doc_s_ref_fails_gate_even_if_claims_reproduce(tmp_path):
    # The headline cross-doc gate: "Figure S2" with only ONE SI figure is a silent dangling
    # cross-reference. The claim reproduces AND each document is internally consistent, yet
    # the combined gate fails -- the gap the within-document checker structurally cannot see.
    spec = _numeric_spec("v-xdoc-ghost", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"See Figure S2 for the extended sweep.")
    _write_paper(run_dir, "si.tex",
                 r"\begin{figure}[htbp]\caption{a}\label{fig:a}\end{figure}")
    report = verify_run(run_dir)
    assert report.all_reproduced is True             # claim signal unchanged
    assert report.paper_consistent is True           # each doc internally clean
    assert report.paper_cross_doc_refs == ["Figure S2"]
    assert report.paper_cross_doc_clean is False
    assert report.passed is False                    # combined gate fails


def test_verify_residual_factref_macro_fails_gate(tmp_path):
    # The fidelity gate (the "moved line"): a rendered .tex must carry NO \evval/\status
    # macro (the engine substitutes them at render time). A residual one means substitution
    # was bypassed / the .tex was hand-edited -> paper_factref_clean False, passed False --
    # EVEN THOUGH the claim reproduces and the \ref/\label integrity is fine.
    spec = _numeric_spec("v-factref", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"Zero collisions over \evval{ev-x}{point} pairs.")
    report = verify_run(run_dir)
    assert report.all_reproduced is True            # claim signal unchanged
    assert report.paper_consistent is True          # ref/label integrity is fine
    assert report.paper_factref_clean is False       # but a residual fact macro survived
    assert report.paper_factrefs["draft.tex"] == [r"\evval{ev-x}{point}"]
    assert report.passed is False                   # combined gate fails


def test_verify_no_residual_factref_is_clean(tmp_path):
    spec = _numeric_spec("v-factref-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a} zero collisions.")
    report = verify_run(run_dir)
    assert report.paper_factrefs == {}
    assert report.paper_factref_clean is True


def test_verify_tool_vocabulary_leak_in_paper_fails_gate(tmp_path):
    # §10: the PAPER must read as tool-agnostic science. A tool-vocabulary leak in
    # draft.tex fails the gate (paper_tool_clean False, passed False), EVEN THOUGH the
    # claim reproduces and \ref/\label integrity is fine.
    spec = _numeric_spec("v-toolvocab", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"We pre-registered in the frozen Spec; the engine-derived verdicts hold.")
    report = verify_run(run_dir)
    assert report.all_reproduced is True
    assert report.paper_consistent is True
    assert report.paper_tool_clean is False
    assert "frozen spec" in report.paper_tool_vocab
    assert "verdicts" in report.paper_tool_vocab
    assert report.passed is False


def test_verify_tool_vocabulary_in_si_is_exempt(tmp_path):
    # The SI is the record dump and legitimately uses sci-adk vocabulary -- it is NOT
    # gated. A clean draft.tex + a vocabulary-rich si.tex still passes the tool gate.
    spec = _numeric_spec("v-si-exempt", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    # M1: a draft.tex is conclusion-bearing -> needs a frozen contract AND every quantitative
    # token must trace to the record. This test targets the SI tool-vocab exemption, so the
    # draft prose carries no unbacked literal (the point estimate 0.95 IS recorded).
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a} The point estimate is 0.95.")
    _write_paper(run_dir, "si.tex",
                 r"\label{tab:s1} Table~\ref{tab:s1}. The append-only Evidence record; "
                 r"frozen Spec; engine-derived verdicts; result.point.")
    _freeze_minimal_pubreqs(run_dir)
    report = verify_run(run_dir)
    assert report.paper_tool_clean is True   # the SI's vocabulary is exempt
    assert report.paper_tool_vocab == []
    assert report.passed is True


def test_verify_paper_check_is_read_only(tmp_path):
    # Adding the paper check must not break the read-only invariant: verify reads the
    # .tex, never writes/recompiles.
    spec = _numeric_spec("v-paper-ro", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"See \ref{fig:ghost}.")  # broken on purpose

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


def test_verify_all_reproduced_unchanged_when_no_paper(tmp_path):
    # Regression guard: existing callers/tests read all_reproduced as the CLAIMS-only
    # signal. It must keep that meaning regardless of paper presence.
    spec = _numeric_spec("v-meaning", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.10))  # 0.10 < 0.9 -> refuted, but
    # the claim still reproduces (recorded refuted == re-derived refuted).
    _freeze_minimal_pubreqs(run_dir)  # M1: the seeded draft.tex is conclusion-bearing
    report = verify_run(run_dir)
    assert report.all_reproduced is True   # the claim reproduces (refuted==refuted)
    assert report.paper_consistent is True
    assert report.passed is True


# -- F1 publishing-requirements umbrella gate (design §1.3) -------------------
# verify gains paper_requirements_clean: the umbrella that consumes F2 (font/DPI) + F3
# (reproduction bundle) + section/reference/word-count checks the FROZEN pubreqs.json
# declares. When pubreqs.json is ABSENT the gate is vacuously clean (backward compatible);
# advisory + max_pages are surfaced but NEVER gated.

import struct as _struct  # noqa: E402
import zlib as _zlib  # noqa: E402

from sci_adk.core.pubreqs import DEFAULT_REQUIRED_SECTIONS, PubReqs  # noqa: E402
from sci_adk.provenance import pubreqs_digest  # noqa: E402


def _write_pubreqs(run_dir: Path, **kwargs) -> PubReqs:
    """Freeze a pubreqs.json at the RUN ROOT (with its digest), like `pubreqs freeze`."""
    kwargs.setdefault("spec_id", run_dir.name)
    pr = PubReqs(**kwargs)
    pr = pr.model_copy(update={"digest": pubreqs_digest(pr)})
    (run_dir / "pubreqs.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")
    return pr


def _png_bytes(width: int, height: int = 10) -> bytes:
    """A minimal valid PNG with a chosen IHDR width (header-only -- stdlib, no Pillow)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def _chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        return _struct.pack(">I", len(data)) + body + _struct.pack(
            ">I", _zlib.crc32(body) & 0xFFFFFFFF
        )

    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IEND", b"")


def test_verify_no_pubreqs_with_draft_refuses(tmp_path):
    # SPEC-PAPER-GATE-001 P1 (OD-1 strict + OD-8 immediate): the OLD "no pubreqs.json ->
    # vacuously clean" posture is OVERTURNED for a conclusion-bearing artifact. A run that
    # renders a paper/draft.tex but freezes NO pubreqs.json now REFUSES -- a loud, actionable
    # failure naming what to freeze, NOT a silent clean pass (REQ-PG-101/108).
    spec = _numeric_spec("v-noreqs", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # compiler renders draft.tex
    assert (run_dir / "paper" / "draft.tex").is_file()
    assert not (run_dir / "pubreqs.json").exists()
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is False
    assert report.passed is False
    joined = " ".join(report.paper_requirements_problems).lower()
    assert "frozen" in joined or "freeze" in joined  # actionable
    assert "pubreqs" in joined


def test_verify_no_draft_is_vacuously_clean(tmp_path):
    # The vacuous-clean path SURVIVES for a NON-conclusion-bearing run: a run with NO
    # paper/draft.tex declared no paper, so the publishing gate is a no-op and the run passes
    # exactly as before (every pre-paper run is unchanged -- EC-1 spirit).
    import shutil

    spec = _numeric_spec("v-nodraft", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    shutil.rmtree(run_dir / "paper")  # remove the rendered paper -> not conclusion-bearing
    assert not (run_dir / "pubreqs.json").exists()
    report = verify_run(run_dir)
    assert report.paper_requirements_problems == []
    assert report.paper_requirements_clean is True
    assert report.passed is True


def test_verify_required_sections_present_passes(tmp_path):
    spec = _numeric_spec("v-reqsec-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\begin{abstract}x\end{abstract}"
                 r"\section{Introduction}a\section{Methods}b"
                 r"\section{Results}c\section{Discussion}d\section{Conclusion}e")
    _write_pubreqs(run_dir, required_sections=list(DEFAULT_REQUIRED_SECTIONS),
                   figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True
    assert report.passed is True


def test_verify_missing_required_section_fails_gate(tmp_path):
    # A missing \section makes paper_requirements_clean False and the combined gate fail,
    # EVEN THOUGH the claim reproduces.
    spec = _numeric_spec("v-reqsec-miss", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\begin{abstract}x\end{abstract}"
                 r"\section{Introduction}a\section{Results}c\section{Discussion}d")  # no Methods
    _write_pubreqs(run_dir, required_sections=list(DEFAULT_REQUIRED_SECTIONS),
                   figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.all_reproduced is True              # claim signal unchanged
    assert report.paper_requirements_clean is False
    assert any("Methods" in p for p in report.paper_requirements_problems)
    assert report.passed is False


def test_verify_figure_font_policy_present_passes(tmp_path):
    # A figure-bearing draft.tex WITH the F2 preamble passes the font policy gate.
    spec = _numeric_spec("v-font-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\usepackage{newtxmath}" "\n" r"\usepackage[scaled]{helvet}" "\n"
                 r"\begin{figure}\begin{tikzpicture}\end{tikzpicture}\end{figure}")
    _write_pubreqs(run_dir, figure_font_policy=True, image_min_dpi=None,
                   reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True
    assert report.passed is True


def test_verify_figure_font_policy_stripped_fails_gate(tmp_path):
    # A figure-bearing draft.tex with the F2 packages STRIPPED (hand-edited) fails the gate.
    spec = _numeric_spec("v-font-strip", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\begin{figure}\begin{tikzpicture}\end{tikzpicture}\end{figure}")
    _write_pubreqs(run_dir, figure_font_policy=True, image_min_dpi=None,
                   reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is False
    assert any("newtxmath" in p for p in report.paper_requirements_problems)
    assert report.passed is False


def test_verify_figureless_doc_font_policy_is_na(tmp_path):
    # A figure-LESS draft.tex makes the font policy N/A -> clean (the F2 regression invariant).
    spec = _numeric_spec("v-font-na", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"\section{Introduction}prose only, no figure.")
    _write_pubreqs(run_dir, figure_font_policy=True, image_min_dpi=None,
                   reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True
    assert report.passed is True


def test_verify_image_dpi_high_passes_low_fails(tmp_path):
    # A high-DPI raster passes; a low-DPI raster fails; a vector figure is skipped.
    spec = _numeric_spec("v-dpi", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    figs = run_dir / "paper" / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    (figs / "fig1.png").write_bytes(_png_bytes(2000))   # 2000/6.5 ~= 307 DPI -> clean
    # font preamble present so the font gate is not the thing failing.
    _write_paper(run_dir, "draft.tex",
                 r"\usepackage{newtxmath}\usepackage[scaled]{helvet}"
                 r"\includegraphics{figures/fig1.png}")
    _write_pubreqs(run_dir, figure_font_policy=True, image_min_dpi=300,
                   reproduction_bundle=False)
    assert verify_run(run_dir).paper_requirements_clean is True

    # Now a low-DPI raster fails.
    (figs / "fig1.png").write_bytes(_png_bytes(500))    # 500/6.5 ~= 77 DPI -> fail
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is False
    assert any("DPI" in p for p in report.paper_requirements_problems)
    assert report.passed is False


def test_verify_image_dpi_vector_is_skipped(tmp_path):
    spec = _numeric_spec("v-dpi-vec", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\usepackage{newtxmath}\usepackage[scaled]{helvet}"
                 r"\includegraphics[width=\textwidth]{figures/fig1.pdf}")  # vector -> skipped
    _write_pubreqs(run_dir, figure_font_policy=True, image_min_dpi=300,
                   reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True
    assert report.passed is True


def test_verify_reproduction_bundle_all_pointer_passes_fail_open(tmp_path):
    # OF-4 FAIL-OPEN: a seeded run records code_ref="fixture" (no co-located script) -> the
    # compiler writes reproduce.py documenting it but NO paper/code/. An honest pointer-only
    # bundle MUST PASS the gate (we never require paper/code/ to be non-empty).
    spec = _numeric_spec("v-repro-pointer", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    assert (run_dir / "paper" / "reproduce.py").is_file()
    assert not (run_dir / "paper" / "code").exists()    # pointer-only: no co-located scripts
    _write_pubreqs(run_dir, figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=True)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True       # fail-open on the honest pointer
    assert report.passed is True


def test_verify_reproduction_bundle_resolvable_script_passes(tmp_path):
    # A resolvable-script bundle: reproduce.py references the recorded code_ref AND a non-empty
    # paper/code/ holds the co-located script. The gate passes (it references the real ref).
    spec = _numeric_spec("v-repro-script", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    code_dir = run_dir / "paper" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "gen.py").write_text("print('regenerate')\n", encoding="utf-8")
    # Rewrite reproduce.py to a script-shaped driver that still references the recorded
    # code_ref ('fixture' -- the seeded evidence's provenance.code_ref).
    (run_dir / "paper" / "reproduce.py").write_text(
        'SCRIPTS = [("ev", "fixture", "gen.py")]\nPOINTERS = []\n', encoding="utf-8"
    )
    _write_pubreqs(run_dir, figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=True)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True
    assert report.passed is True


def test_verify_reproduction_bundle_missing_reproduce_py_fails(tmp_path):
    # reproduction_bundle declared, the record holds a code_ref, but reproduce.py was deleted
    # -> fail (a declared bundle the paper does not carry).
    spec = _numeric_spec("v-repro-missing", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    (run_dir / "paper" / "reproduce.py").unlink()
    _write_pubreqs(run_dir, figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=True)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is False
    assert any("reproduce.py is missing" in p for p in report.paper_requirements_problems)
    assert report.passed is False


def test_verify_reproduction_bundle_driver_omits_recorded_ref_fails(tmp_path):
    # reproduce.py exists but references NONE of the recorded code_refs (out of sync with the
    # record) -> fail (it does not reference the real recorded code_ref).
    spec = _numeric_spec("v-repro-stale", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    (run_dir / "paper" / "reproduce.py").write_text(
        "SCRIPTS = []\nPOINTERS = []\n# no recorded refs\n", encoding="utf-8"
    )
    _write_pubreqs(run_dir, figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=True)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is False
    assert any("does not reference recorded" in p
               for p in report.paper_requirements_problems)
    assert report.passed is False


def test_verify_advisory_and_max_pages_are_never_gated(tmp_path):
    # advisory + max_pages are surfaced but NEVER fail the gate: a run that satisfies every
    # GATED requirement passes even with an advisory note and a max_pages set.
    spec = _numeric_spec("v-advisory", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"\section{Introduction}short prose.")
    _write_pubreqs(run_dir, figure_font_policy=False, image_min_dpi=None,
                   reproduction_bundle=False, max_pages=1,
                   advisory=["double-blind review", "data availability statement required"])
    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True    # max_pages/advisory never gate
    assert report.passed is True


def test_verify_requirements_gate_is_read_only(tmp_path):
    # The new gate must not break the read-only invariant: it reads pubreqs.json + draft.tex
    # + figures + reproduce.py, never writes/recompiles.
    spec = _numeric_spec("v-reqs-ro", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\begin{figure}\begin{tikzpicture}\end{tikzpicture}\end{figure}")  # font fail
    _write_pubreqs(run_dir, figure_font_policy=True, image_min_dpi=300,
                   reproduction_bundle=True)

    def _snapshot(d: Path) -> dict:
        return {
            p.relative_to(d).as_posix(): p.read_bytes()
            for p in sorted(d.rglob("*")) if p.is_file()
        }

    before = _snapshot(run_dir)
    verify_run(run_dir)
    after = _snapshot(run_dir)
    assert before.keys() == after.keys(), "verify created or deleted a file"
    for k in before:
        assert before[k] == after[k], f"verify modified file contents: {k}"
