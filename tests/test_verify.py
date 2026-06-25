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
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a} The collision count is 0.")
    _write_paper(run_dir, "si.tex",
                 r"\label{tab:s1} Table~\ref{tab:s1}. The append-only Evidence record; "
                 r"frozen Spec; engine-derived verdicts; result.point.")
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
    report = verify_run(run_dir)
    assert report.all_reproduced is True   # the claim reproduces (refuted==refuted)
    assert report.paper_consistent is True
    assert report.passed is True
