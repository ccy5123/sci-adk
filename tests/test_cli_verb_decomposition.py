"""
Step 2 (design/sci-adk-as-moai.md §4.6): the 6 standalone CLI verbs + the `run`
wrapper, and the byte-identity regression that pins the decomposition.

The monolithic `sci-adk run` is decomposed into stage verbs (`init-spec`, `amend-spec`,
`execute`, `append-evidence`, `derive-claim`, `render`) while `run` stays the 5-stage
chained wrapper. These tests cover, per verb, a happy path + a key error path; a full
`run`-vs-verb-chain integration; and the load-bearing guarantee: the decomposed chain
yields paper artifacts BYTE-IDENTICAL to the monolithic `compile()` over the same
Evidence.

All tests are no-LLM / no-Docker: a deterministic injected experiment fn (fixed
EvidenceItem id + created_at) makes the rendered output reproducible so byte-identity is
checkable without timestamp drift.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
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
from sci_adk.loop.compiler import ResearchCompiler

# A fixed instant so the injected experiment's EvidenceItem is fully deterministic
# (id + created_at), making the rendered paper reproducible across compile/verb paths.
_FIXED_AT = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
_HYP_ID = "hyp-x"


def _numeric_spec(spec_id: str) -> Spec:
    """A numeric (threshold) Spec that resolves autonomously -- no judge, no checkpoint.

    referent='formal' + non_circularity so the evidence-validity gate allows a binding
    SUPPORTED verdict on a 'generated' Evidence item.
    """
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="metric == 0 => support; > 0 => refute",
        params={"statistic": "metric", "op": "==", "value": 0.0},
    )
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="m", expected_output="o"
        ),
        hypotheses=[
            Hypothesis(
                id=_HYP_ID,
                statement="the tested metric is zero on the designed set",
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=rule,
                referent="formal",
                non_circularity=(
                    "the generator does not guarantee a zero metric; the verifier checks "
                    "it independently, so a zero is informative, not baked in"
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[
            TargetClaim(id="tc", statement="the metric is zero", answers=_HYP_ID)
        ],
    )


def _deterministic_evidence(spec: Spec) -> EvidenceItem:
    """A single SUPPORTS EvidenceItem with a FIXED id + created_at (reproducible render)."""
    return EvidenceItem(
        id="evi-fixed-0001",
        created_at=_FIXED_AT,
        spec_id=spec.id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=0.0, finding="metric=0"),
        bears_on=[Bearing(target_id=_HYP_ID, direction=BearingDirection.SUPPORTS)],
    )


def _experiment_fn(spec: Spec):
    """A deterministic ExperimentFn that produces the fixed EvidenceItem (no Docker)."""
    item = _deterministic_evidence(spec)

    def _run(_spec, _workspace):
        return [item]

    return _run


def _seed_spec_and_evidence(workspace: Path, spec_id: str) -> Path:
    """init-spec + execute (via the compiler stages directly) to lay down a run dir."""
    spec = _numeric_spec(spec_id)
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_init_spec(spec=spec)
    compiler.stage_execute(spec, experiment=_experiment_fn(spec))
    return workspace / "runs" / spec_id


def _evidence(spec_id: str, eid: str, hyp_id: str, point: float, finding: str):
    """A SUPPORTS EvidenceItem with a FIXED created_at (so ordering can ONLY come from
    the filename sort, not a created_at tie-break -- the robust-invariant stressor)."""
    return EvidenceItem(
        id=eid,
        created_at=_FIXED_AT,
        spec_id=spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=point, finding=finding),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
    )


def _multi_evidence_experiment(spec: Spec):
    """An ExperimentFn whose PRODUCTION order != sorted-id order.

    Produces ``evi-9-last`` THEN ``evi-1-first``: sorting by filename REVERSES the
    production order. If any path rendered production order while another rendered sorted
    order, draft.tex/si.tex (which iterate Evidence) would diverge -- this is the exact
    multi-evidence case the single-item fixtures could never catch. Both items bear on the
    one hypothesis with the SAME _FIXED_AT, so a created_at sort cannot disambiguate them
    either -- only the filename sort is robust.
    """
    items = [
        _evidence(spec.id, "evi-9-last", _HYP_ID, 0.0, "finding-LAST"),
        _evidence(spec.id, "evi-1-first", _HYP_ID, 0.0, "finding-FIRST"),
    ]

    def _run(_spec, _workspace):
        return list(items)

    return _run


def _multi_hyp_novelty_spec(spec_id: str) -> Spec:
    """A 2-hypothesis Spec, the second flagged result-novelty (derives a novelty claim).

    Exercises the multi-hypothesis claim ordering AND the per-{hyp,kind} novelty pass, so
    the verb path's claim reload (which must reproduce ClaimUpdater's order: experiment
    claims per hypothesis, then novelty claims) is genuinely stressed.
    """
    def _rule():
        return DecisionRule(
            kind=DecisionRuleKind.THRESHOLD,
            expression="metric == 0 => support; > 0 => refute",
            params={"statistic": "metric", "op": "==", "value": 0.0},
        )

    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="m", expected_output="o"
        ),
        hypotheses=[
            Hypothesis(
                id="hyp-a",
                statement="hypothesis A metric is zero",
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=_rule(),
                referent="formal",
                non_circularity="verifier independent of generator (A)",
            ),
            Hypothesis(
                id="hyp-b",
                statement="hypothesis B metric is zero, and it is novel",
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=_rule(),
                referent="formal",
                non_circularity="verifier independent of generator (B)",
                novelty_result=True,
            ),
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[
            TargetClaim(id="tc-a", statement="A is zero", answers="hyp-a"),
            TargetClaim(id="tc-b", statement="B is zero", answers="hyp-b"),
        ],
    )


def _multi_hyp_experiment(spec: Spec):
    """An ExperimentFn for the 2-hypothesis spec: one SUPPORTS item per hypothesis.

    Production order (B then A) again differs from sorted-id order so the multi-evidence
    ordering invariant is stressed alongside the multi-hypothesis claim ordering.
    """
    items = [
        _evidence(spec.id, "evi-b-item", "hyp-b", 0.0, "finding-B"),
        _evidence(spec.id, "evi-a-item", "hyp-a", 0.0, "finding-A"),
    ]

    def _run(_spec, _workspace):
        return list(items)

    return _run


def _draft_si_via_compile(workspace: Path, spec: Spec, experiment):
    """Render draft.tex + si.tex via the monolithic compile() path."""
    result = ResearchCompiler(workspace_dir=workspace).compile(
        "", spec=spec, experiment=experiment
    )
    return (
        result.paper_path.read_text(encoding="utf-8"),
        result.si_path.read_text(encoding="utf-8"),
    )


def _draft_si_via_verbs(workspace: Path, spec: Spec, experiment):
    """Render draft.tex + si.tex via the stage-by-stage verb path (disk round-trip)."""
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_init_spec(spec=spec)
    compiler.stage_execute(spec, experiment=experiment)
    compiler.stage_derive_claim(spec)
    paper_path, si_path, _fc = compiler.stage_render(spec)
    return (
        paper_path.read_text(encoding="utf-8"),
        si_path.read_text(encoding="utf-8"),
    )


# --------------------------------------------------------------------------- #
# Byte-identity regression -- the load-bearing decomposition guarantee.
# --------------------------------------------------------------------------- #

def test_decomposed_chain_byte_identical_to_monolith(tmp_path):
    """The verb-style stage chain yields draft.tex + si.tex BYTE-IDENTICAL to compile().

    `compile()` is the monolithic chain (threads Evidence in memory); the verb path runs
    the SAME stage functions but reloads Evidence/Claims from disk between stages. Over
    the SAME deterministic Evidence the two MUST agree byte-for-byte -- the contract that
    makes `run` indistinguishable from `init-spec -> ... -> render`.
    """
    # (a) monolithic compile() into workspace A.
    ws_a = tmp_path / "mono"
    spec_a = _numeric_spec("bi-mono")
    result = ResearchCompiler(workspace_dir=ws_a).compile(
        "", spec=spec_a, experiment=_experiment_fn(spec_a)
    )
    mono_draft = result.paper_path.read_text(encoding="utf-8")
    mono_si = result.si_path.read_text(encoding="utf-8")

    # (b) verb-style stage chain into workspace B (disk round-trip between stages).
    ws_b = tmp_path / "verbs"
    spec_b = _numeric_spec("bi-mono")  # SAME id so rendered ids/content match
    compiler = ResearchCompiler(workspace_dir=ws_b)
    compiler.stage_init_spec(spec=spec_b)
    compiler.stage_execute(spec_b, experiment=_experiment_fn(spec_b))
    # derive-claim + render read Evidence/Claims FROM DISK (no in-memory pass-through).
    compiler.stage_derive_claim(spec_b)
    paper_path, si_path, _fc = compiler.stage_render(spec_b)
    verb_draft = paper_path.read_text(encoding="utf-8")
    verb_si = si_path.read_text(encoding="utf-8")

    assert verb_draft == mono_draft, "draft.tex diverged between compile() and verb chain"
    assert verb_si == mono_si, "si.tex diverged between compile() and verb chain"


def test_chain_byte_identical_multi_evidence_production_order_ne_sorted(tmp_path):
    """NON-VACUOUS multi-evidence regression: production order != sorted-id order.

    The experiment produces ``evi-9-last`` then ``evi-1-first`` (production order), which
    the filename sort REVERSES. Before the canonical-order fix, compile() rendered Evidence
    in production order (9, 1) while the verb chain reloaded sorted (1, 9) -> draft.tex AND
    si.tex diverged. This test asserts they now agree. It would FAIL against the pre-fix
    code (confirmed: production '9-then-1' vs verb '1-then-9'), so it is a real guard, not
    a vacuous single-item check.
    """
    spec_mono = _numeric_spec("bi-multi")
    mono_draft, mono_si = _draft_si_via_compile(
        tmp_path / "mono", spec_mono, _multi_evidence_experiment(spec_mono)
    )
    spec_verb = _numeric_spec("bi-multi")  # SAME id so rendered content matches
    verb_draft, verb_si = _draft_si_via_verbs(
        tmp_path / "verbs", spec_verb, _multi_evidence_experiment(spec_verb)
    )

    assert verb_draft == mono_draft, (
        "draft.tex diverged on a multi-evidence run (production order != sorted-id order)"
    )
    assert verb_si == mono_si, (
        "si.tex diverged on a multi-evidence run (production order != sorted-id order)"
    )
    # Sanity: the SI record dump renders the canonical (sorted) Evidence order --
    # evi-1-first precedes evi-9-last. (The belief-narrative draft no longer dumps the
    # raw Evidence ids after the reframe; the record lives in the SI.)
    assert mono_si.find("evi-1-first") < mono_si.find("evi-9-last")


def test_chain_byte_identical_multi_hypothesis_and_novelty(tmp_path):
    """NON-VACUOUS multi-hypothesis + novelty regression.

    Two hypotheses (one result-novelty flagged) with one Evidence item each, produced in
    an order (B then A) that the filename sort reverses. This stresses BOTH the
    multi-evidence ordering invariant AND the verb path's claim reload, which must
    reproduce ClaimUpdater's order (experiment claims per hypothesis, then per-{hyp,kind}
    novelty claims). draft.tex + si.tex must be byte-identical across compile() and verbs.
    """
    spec_mono = _multi_hyp_novelty_spec("bi-multihyp")
    mono_draft, mono_si = _draft_si_via_compile(
        tmp_path / "mono", spec_mono, _multi_hyp_experiment(spec_mono)
    )
    spec_verb = _multi_hyp_novelty_spec("bi-multihyp")
    verb_draft, verb_si = _draft_si_via_verbs(
        tmp_path / "verbs", spec_verb, _multi_hyp_experiment(spec_verb)
    )

    assert verb_draft == mono_draft, "draft.tex diverged on a multi-hypothesis+novelty run"
    assert verb_si == mono_si, "si.tex diverged on a multi-hypothesis+novelty run"
    # Sanity: the novelty hypothesis produced a novelty claim, and both render it.
    assert "novelty" in mono_draft.lower() or "novelty" in mono_si.lower()


@pytest.mark.integration
def test_run_t1_demo_byte_identical_to_verb_chain_via_cli(tmp_path):
    """End-to-end via the CLI: `run --t1-demo` matches `init-spec/execute/derive/render`.

    The verb chain persists the t1 Evidence (whose id carries a fresh timestamp); `run`
    over a workspace pre-seeded with that SAME Evidence replays it (F5) instead of
    re-generating, so both rendered papers are byte-identical -- proving `run` IS the chain
    at the CLI boundary, even for the real (non-deterministic-id) t1 capability.
    """
    # verb chain into workspace A (real CLI verbs, t1-demo capability).
    ws_a = tmp_path / "verbs"
    assert main(["init-spec", "--t1-demo", "-o", str(ws_a)]) == 0
    run_a = ws_a / "runs" / "t1-godel"
    assert main(["execute", str(run_a), "--t1-demo"]) == 0
    # --no-strict-science on BOTH the verb chain and `run` below: this is a byte-identity
    # plumbing test (run == verb chain), not a science test. The bare t1 demo has no
    # negative control, so a strict derive/run would HALT (design/science-guards.md G3);
    # both paths run lenient so the comparison exercises the decomposition, not the gate.
    assert main(["derive-claim", str(run_a), "--no-strict-science"]) == 0
    assert main(["render", str(run_a)]) == 0
    verb_draft = (run_a / "paper" / "draft.tex").read_text(encoding="utf-8")
    verb_si = (run_a / "paper" / "si.tex").read_text(encoding="utf-8")

    # workspace B: pre-seed the SAME Evidence (so F5 reuse fires), then `run --t1-demo`.
    ws_b = tmp_path / "runw"
    assert main(["init-spec", "--t1-demo", "-o", str(ws_b)]) == 0
    ev_dir_b = ws_b / "runs" / "t1-godel" / "evidence"
    ev_dir_b.mkdir(parents=True, exist_ok=True)
    for src in (run_a / "evidence").glob("*.json"):
        (ev_dir_b / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["run", "--t1-demo", "--no-strict-science", "-o", str(ws_b)]) == 0
    run_b = ws_b / "runs" / "t1-godel"
    run_draft = (run_b / "paper" / "draft.tex").read_text(encoding="utf-8")
    run_si = (run_b / "paper" / "si.tex").read_text(encoding="utf-8")

    assert run_draft == verb_draft, "run --t1-demo draft.tex != verb-chain draft.tex"
    assert run_si == verb_si, "run --t1-demo si.tex != verb-chain si.tex"


# --------------------------------------------------------------------------- #
# init-spec
# --------------------------------------------------------------------------- #

def test_init_spec_t1_demo_writes_spec_and_prior_work(tmp_path, capsys):
    rc = main(["init-spec", "--t1-demo", "-o", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "froze Spec 't1-godel'" in out
    run_dir = tmp_path / "runs" / "t1-godel"
    assert (run_dir / "spec.json").exists()
    assert (run_dir / "checkpoints" / "prior_work.json").exists()
    # No experiment ran yet -> no evidence/claims/paper.
    assert not (run_dir / "evidence").exists()


def test_init_spec_from_proposal(tmp_path, capsys):
    proposal = tmp_path / "p.md"
    proposal.write_text(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n",
        encoding="utf-8",
    )
    rc = main(["init-spec", str(proposal), "-o", str(tmp_path), "--spec-id", "is-prop"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "froze Spec 'is-prop'" in out
    assert (tmp_path / "runs" / "is-prop" / "spec.json").exists()


def test_init_spec_no_input_errors(tmp_path, capsys):
    rc = main(["init-spec", "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "proposal" in err.lower() or "capability" in err.lower()


# --------------------------------------------------------------------------- #
# amend-spec
# --------------------------------------------------------------------------- #

def test_amend_spec_bumps_version_and_writes_receipt(tmp_path, capsys):
    spec = _numeric_spec("am-ok")
    run_dir = tmp_path / "runs" / "am-ok"
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)

    rc = main(["amend-spec", str(run_dir), "--rationale", "tighten the threshold"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "v1 -> v2" in out
    # spec.json now holds v2.
    reloaded = Spec.model_validate(
        json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    )
    assert reloaded.version == 2
    assert reloaded.amendment_rationale == "tighten the threshold"
    # The checkpoint receipt is on disk and well-formed.
    receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["prior_version"] == 1
    assert receipt["new_version"] == 2
    assert receipt["rationale"] == "tighten the threshold"


def test_amend_spec_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["amend-spec", str(tmp_path / "runs" / "nope"), "--rationale", "r"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no spec.json" in err.lower() or "not found" in err.lower()


def test_amend_spec_blank_rationale_errors_s5(tmp_path, capsys):
    spec = _numeric_spec("am-blank")
    run_dir = tmp_path / "runs" / "am-blank"
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    rc = main(["amend-spec", str(run_dir), "--rationale", "   "])
    err = capsys.readouterr().err
    assert rc == 2
    assert "rationale" in err.lower()
    assert "Traceback (most recent call last)" not in err
    # spec.json must NOT have been amended.
    reloaded = Spec.model_validate(
        json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    )
    assert reloaded.version == 1


# --------------------------------------------------------------------------- #
# execute
# --------------------------------------------------------------------------- #

@pytest.mark.integration
def test_execute_t1_demo_produces_evidence(tmp_path, capsys):
    main(["init-spec", "--t1-demo", "-o", str(tmp_path)])
    run_dir = tmp_path / "runs" / "t1-godel"
    rc = main(["execute", str(run_dir), "--t1-demo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "produced 1 Evidence item" in out
    assert list((run_dir / "evidence").glob("*.json"))


def test_execute_reuses_recorded_evidence_f5(tmp_path, capsys):
    """A second execute over a populated run replays (F5) -- no second evidence file."""
    run_dir = _seed_spec_and_evidence(tmp_path, "ex-reuse")
    before = {p.name for p in (run_dir / "evidence").glob("*.json")}
    # No capability supplied: with recorded evidence, execute replays it.
    rc = main(["execute", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    after = {p.name for p in (run_dir / "evidence").glob("*.json")}
    assert before == after, "F5 reuse must not append a new evidence file"
    assert "produced 1 Evidence item" in out


def test_execute_no_experiment_no_evidence_errors(tmp_path, capsys):
    """Bare execute with no capability AND no recorded evidence is a friendly error."""
    spec = _numeric_spec("ex-empty")
    run_dir = tmp_path / "runs" / "ex-empty"
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    rc = main(["execute", str(run_dir)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no experiment" in err.lower() or "no recorded evidence" in err.lower()


def test_execute_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["execute", str(tmp_path / "runs" / "nope"), "--t1-demo"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no spec.json" in err.lower() or "not found" in err.lower()


# --------------------------------------------------------------------------- #
# append-evidence
# --------------------------------------------------------------------------- #

def test_append_evidence_appends_item(tmp_path, capsys):
    spec = _numeric_spec("ae-ok")
    run_dir = tmp_path / "runs" / "ae-ok"
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)

    item = _deterministic_evidence(spec)
    ev_file = tmp_path / "ev.json"
    ev_file.write_text(
        json.dumps(item.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    rc = main(["append-evidence", str(run_dir), "--evidence", str(ev_file)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "evi-fixed-0001" in out
    assert (run_dir / "evidence" / "evi-fixed-0001.json").exists()


def test_append_evidence_missing_file_errors(tmp_path, capsys):
    spec = _numeric_spec("ae-missing")
    run_dir = tmp_path / "runs" / "ae-missing"
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    rc = main(["append-evidence", str(run_dir), "--evidence", str(tmp_path / "nope.json")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "evidence file not found" in err.lower()


def test_append_evidence_malformed_json_errors_no_traceback(tmp_path, capsys):
    spec = _numeric_spec("ae-bad")
    run_dir = tmp_path / "runs" / "ae-bad"
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    bad = tmp_path / "bad.json"
    bad.write_text('{"id": "x",', encoding="utf-8")
    rc = main(["append-evidence", str(run_dir), "--evidence", str(bad)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "invalid evidence json" in err.lower()
    assert "Traceback (most recent call last)" not in err


# --------------------------------------------------------------------------- #
# derive-claim
# --------------------------------------------------------------------------- #

def test_derive_claim_derives_supported(tmp_path, capsys):
    run_dir = _seed_spec_and_evidence(tmp_path, "dc-ok")
    # --no-strict-science: this verb test seeds a formal+threshold spec with no negative
    # control; strict derive (the default) would correctly HALT it (G3). Run lenient to test
    # the derive-claim VERB plumbing; the strict halt is covered in test_science_guards.
    rc = main(["derive-claim", str(run_dir), "--no-strict-science"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "derived 1 Claim" in out
    assert "supported" in out.lower()
    assert (run_dir / "claims" / f"claim-{_HYP_ID}.json").exists()


def test_derive_claim_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["derive-claim", str(tmp_path / "runs" / "nope")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no spec.json" in err.lower() or "not found" in err.lower()


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #

def test_render_compiles_paper(tmp_path, capsys):
    run_dir = _seed_spec_and_evidence(tmp_path, "rd-ok")
    main(["derive-claim", str(run_dir)])
    rc = main(["render", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "compiled paper" in out
    assert (run_dir / "paper" / "draft.tex").exists()
    assert (run_dir / "paper" / "si.tex").exists()


def test_render_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["render", str(tmp_path / "runs" / "nope")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no spec.json" in err.lower() or "not found" in err.lower()


# --------------------------------------------------------------------------- #
# run wrapper integration -- the full chain still produces everything.
# --------------------------------------------------------------------------- #

@pytest.mark.integration
def test_run_wrapper_full_chain_produces_all_artifacts(tmp_path, capsys):
    # --no-strict-science: full-chain ARTIFACT plumbing test (does run produce all files?),
    # not a science test. The bare t1 demo has no negative control -> strict would HALT (G3).
    rc = main(["run", "--t1-demo", "--no-strict-science", "-o", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "compiled Spec 't1-godel'" in out
    run_dir = tmp_path / "runs" / "t1-godel"
    assert (run_dir / "spec.json").exists()
    assert list((run_dir / "evidence").glob("*.json"))
    assert (run_dir / "claims" / "claim-hyp-t1.json").exists()
    assert (run_dir / "paper" / "draft.tex").exists()
    assert (run_dir / "paper" / "si.tex").exists()
    assert (run_dir / "checkpoints" / "prior_work.json").exists()


@pytest.mark.integration
def test_render_warns_in_multi_run_workspace_pf7(tmp_path, capsys):
    """PF-7 (design/near-submission-package.md): a per-run render in a multi-run
    workspace WARNS and points to `package` -- route-to-package + warn, never a refuse."""
    ws = tmp_path
    assert main(["init-spec", "--t1-demo", "-o", str(ws)]) == 0
    run = ws / "runs" / "t1-godel"
    assert main(["execute", str(run), "--t1-demo"]) == 0
    assert main(["derive-claim", str(run), "--no-strict-science"]) == 0

    # single-run workspace: no PF-7 warning
    assert main(["render", str(run)]) == 0
    err_single = capsys.readouterr().err
    assert "per-run internal record" not in err_single

    # a second run (any dir carrying a spec.json) makes it a multi-run workspace
    second = ws / "runs" / "second"
    second.mkdir()
    (second / "spec.json").write_text(
        (run / "spec.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    # render still succeeds (no refuse) but now warns and points to `package`
    assert main(["render", str(run)]) == 0
    err_multi = capsys.readouterr().err
    assert "per-run internal record" in err_multi
    assert "sci-adk package" in err_multi
