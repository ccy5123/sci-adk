"""
Tests for the ResearchCompiler orchestrator (deterministic core).

Network-free: a fake experiment hook stands in for the Docker run, so these
exercise the orchestration -- parse -> Spec -> Evidence -> Claims -> render ->
runs/ -- plus the agent-checkpoint surfacing for non-numeric rules. The parser
assigns qualitative rules by default, so the compiled hypotheses become agent
checkpoints (the zero-cost LLM model: surfaced for an in-session verdict, not
judged autonomously).
"""

import json

from datetime import datetime, timezone

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
from sci_adk.loop.compiler import CompileResult, ResearchCompiler

PROPOSAL = """# Background
Molecular graphs represent chemical structures as vertices and edges.

# Goal
A bijective Gödel-style encoding of molecular graphs exists.

# Expected Output
A unique integer per molecule and a decoding algorithm.

# Method
Prime-factor encoding; test injectivity in a Docker sandbox.
"""


def _fake_experiment(spec, workspace_dir):
    """Produce one Evidence item bearing (neutrally) on each hypothesis."""
    items = []
    for i, h in enumerate(spec.hypotheses):
        items.append(
            EvidenceItem(
                id=f"ev-fake-{i}",
                spec_id=spec.id,
                kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fake:test"),
                result=Result(type="qualitative", finding=f"finding for {h.id}"),
                bears_on=[Bearing(target_id=h.id, direction=BearingDirection.NEUTRAL)],
            )
        )
    return items


def test_compile_with_experiment_produces_claims_and_checkpoints(tmp_path):
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    result = compiler.compile(PROPOSAL, spec_id="t-compile", experiment=_fake_experiment)

    assert isinstance(result, CompileResult)
    n_hyp = len(result.spec.hypotheses)
    assert n_hyp >= 1

    # Evidence ran and Claims were produced for each hypothesis with bearing evidence.
    assert len(result.evidence) == n_hyp
    assert len(result.claims) == n_hyp

    # The parser assigns qualitative rules -> every hypothesis is an agent
    # checkpoint (no autonomous judging), and the finding is attached.
    assert result.needs_agent is True
    assert len(result.checkpoints) == n_hyp
    assert all(c.kind == "qualitative" for c in result.checkpoints)
    assert any("finding for" in c.finding for c in result.checkpoints)

    # Artifacts written under runs/<spec.id>/. The .tex is THE paper artifact;
    # draft.md is no longer emitted (render_paper stays a library fn).
    run_dir = tmp_path / "runs" / "t-compile"
    assert (run_dir / "spec.json").exists()
    assert result.paper_path == run_dir / "paper" / "draft.tex"
    assert result.paper_path.exists()
    assert not (run_dir / "paper" / "draft.md").exists()
    assert (run_dir / "checkpoints.md").exists()

    # spec.json is the compiled Spec.
    on_disk = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    assert on_disk["id"] == "t-compile"

    # The paper draft is the belief narrative: NO stage-dump Evidence/Hypotheses
    # sections (those record facts live in the SI); the qualitative checkpoints surface
    # as a Pending section. The SI carries the append-only Evidence record.
    paper = result.paper_path.read_text(encoding="utf-8")
    assert r"\section{Pending agent judgments}" in paper
    assert r"\section{Evidence}" not in paper
    assert r"\section{Hypotheses and findings}" not in paper
    # SPEC-SI-AUTHORING-001 M1: the deterministic dump is relocated to the deposit
    # record.tex (result.record_path); the paper/si.tex slot is freed.
    assert result.record_path is not None and result.record_path.exists()
    si = result.record_path.read_text(encoding="utf-8")
    assert r"\section{Evidence record}" in si


def test_compile_without_experiment_still_emits_spec_and_draft(tmp_path):
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    result = compiler.compile(PROPOSAL, spec_id="t-noexp")

    assert result.evidence == []
    assert result.claims == []
    # qualitative hypotheses are still flagged for the agent (finding empty).
    assert result.needs_agent is True
    run_dir = tmp_path / "runs" / "t-noexp"
    assert (run_dir / "spec.json").exists()
    assert (run_dir / "paper" / "draft.tex").exists()
    assert not (run_dir / "paper" / "draft.md").exists()
    paper = (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8")
    # No stage-dump Goal section; qualitative hypotheses still surface as Pending.
    assert r"\section{Goal}" not in paper
    assert r"\section{Pending agent judgments}" in paper
    assert r"\title{" in paper


def test_si_records_status_when_claims_exist(tmp_path):
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-status", experiment=_fake_experiment)
    # qualitative + no judge -> PROPOSED (inconclusive), recorded in the deposit record
    # (result.record_path, SPEC-SI-AUTHORING-001 M1), not the belief-narrative paper.
    assert result.record_path is not None
    si = result.record_path.read_text(encoding="utf-8")
    assert "Status: proposed" in si


def test_compile_writes_typed_checkpoint_json_alongside_markdown(tmp_path):
    # Unit 3: the compiler now writes typed checkpoints/<hyp-id>.json (the contract)
    # AND keeps checkpoints.md as a generated human view (F1).
    #
    # Note: checkpoints/ now also holds the Spec-time prior_work.json AND the spec-gate
    # science.json (other arms of the recording-type checkpoint family); select the JUDGE
    # files explicitly so this test verifies the judge-checkpoint contract specifically.
    from sci_adk.loop.verdict import CheckpointModel

    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-typed-cp", experiment=_fake_experiment)
    run_dir = tmp_path / "runs" / "t-typed-cp"
    cp_dir = run_dir / "checkpoints"
    assert cp_dir.is_dir()
    _recording_cp = {"prior_work.json", "science.json"}
    judge_files = sorted(
        p for p in cp_dir.glob("*.json") if p.name not in _recording_cp
    )
    assert len(judge_files) == len(result.checkpoints) >= 1
    cp = CheckpointModel.model_validate(json.loads(judge_files[0].read_text()))
    assert cp.kind == "qualitative"
    assert cp.spec_version == result.spec.version
    # The Markdown view still exists.
    assert (run_dir / "checkpoints.md").exists()


# ---------------------------------------------------------------------------
# F3 reproduction bundle (design/paper-publishing-requirements.md §3): stage_render
# resolves each Evidence item's code_ref -> (co-located script | bare-ref pointer),
# inlines the listings in the SI, co-locates paper/code/, and writes paper/reproduce.py.
# A code_ref-free run leaves paper/ byte-identical to today (the regression invariant).
# Bare commits are fail-open POINTERs, never errors.
# ---------------------------------------------------------------------------

_F3_AT = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
_F3_HYP = "hyp-f3"


def _f3_spec(spec_id: str) -> Spec:
    """A numeric (threshold) Spec that resolves autonomously (no judge/checkpoint)."""
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
                id=_F3_HYP,
                statement="the tested metric is zero on the designed set",
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=rule,
                referent="formal",
                non_circularity=(
                    "the generator does not guarantee a zero metric; the verifier "
                    "checks it independently, so a zero is informative"
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[
            TargetClaim(id="tc", statement="the metric is zero", answers=_F3_HYP)
        ],
    )


def _f3_evidence(spec_id: str, eid: str, code_ref):
    return EvidenceItem(
        id=eid,
        created_at=_F3_AT,
        spec_id=spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref=code_ref, data_source="generated"),
        result=Result(type="quantitative", point=0.0, finding="metric=0"),
        bears_on=[Bearing(target_id=_F3_HYP, direction=BearingDirection.SUPPORTS)],
    )


def _render_with_evidence(tmp_path, spec, evidence):
    """init-spec (lay down the run dir) then stage_render with in-memory evidence.

    SPEC-SI-AUTHORING-001 M4: stage_render now returns
    ``(paper_path, si_path, record_path, figure_consistency)``. The F3 reproduction-bundle
    content lives in the DETERMINISTIC record dump, which M1 relocated to the deposit
    ``record.tex`` -- so these tests read ``record_path`` (the dump), not the authored
    ``si_path`` (which is None here: no AuthoredSI is supplied)."""
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_init_spec(spec=spec)
    # derive claims from the same evidence so the record dump/paper are well-formed.
    claims, *_ = compiler.stage_derive_claim(spec, evidence=evidence)
    paper_path, _si_path, record_path, _fc = compiler.stage_render(
        spec, evidence=evidence, claims=claims
    )
    return compiler, paper_path, record_path


def test_f3_no_code_ref_paper_dir_byte_identical(tmp_path):
    """A run whose Evidence carries NO code_ref produces paper/ byte-identical to today:
    no paper/code/, no reproduce.py, no 'Reproduction code' SI section."""
    spec = _f3_spec("t-f3-none")
    # code_ref=None on every item -> nothing to resolve.
    evidence = [_f3_evidence(spec.id, "ev-1", None)]
    _c, paper_path, si_path = _render_with_evidence(tmp_path, spec, evidence)

    paper_dir = paper_path.parent
    assert not (paper_dir / "code").exists()
    assert not (paper_dir / "reproduce.py").exists()
    si = si_path.read_text(encoding="utf-8")
    assert r"\section{Reproduction code}" not in si
    assert r"\usepackage{listings}" not in si
    # The main paper (tool-agnostic) never carries a code listing or reproduce ref.
    paper = paper_path.read_text(encoding="utf-8")
    assert r"\begin{lstlisting}" not in paper
    assert "reproduce.py" not in paper
    assert r"\section{Reproduction code}" not in paper


def test_f3_bare_commit_is_pointer_no_file_no_error(tmp_path):
    """A 40-hex git commit code_ref is a fail-open POINTER: the SI records the ref, no
    paper/code/ file is created for it, no error, and reproduce.py documents the commit."""
    spec = _f3_spec("t-f3-pointer")
    commit = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"
    evidence = [_f3_evidence(spec.id, "ev-1", commit)]
    _c, paper_path, si_path = _render_with_evidence(tmp_path, spec, evidence)
    paper_dir = paper_path.parent

    si = si_path.read_text(encoding="utf-8")
    assert r"\section{Reproduction code}" in si
    assert commit in si
    # Pointer-only: no listings package, no inlined body.
    assert r"\usepackage{listings}" not in si
    assert r"\begin{lstlisting}" not in si
    # No co-located code file for a bare commit (fail-open).
    assert not (paper_dir / "code").exists()
    # reproduce.py is still written and documents the commit (never executes it).
    repro = paper_dir / "reproduce.py"
    assert repro.exists()
    repro_text = repro.read_text(encoding="utf-8")
    assert commit in repro_text
    assert "POINTERS = [" in repro_text
    # It must be valid Python.
    compile(repro_text, "reproduce.py", "exec")


def test_f3_resolvable_script_inlined_colocated_and_driven(tmp_path):
    """A code_ref pointing at a real co-located file: the SI inlines the body in an
    lstlisting (+ listings package), the script is copied into paper/code/, and
    reproduce.py references it."""
    spec = _f3_spec("t-f3-script")
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_init_spec(spec=spec)
    run_dir = tmp_path / "runs" / spec.id
    # Build a real generating script under the run dir, referenced by a run-dir-relative
    # code_ref (the natural home of co-located code).
    script_rel = "code/encode.py"
    script_abs = run_dir / script_rel
    script_abs.parent.mkdir(parents=True, exist_ok=True)
    script_abs.write_text("print('reproduced')\n", encoding="utf-8")

    evidence = [_f3_evidence(spec.id, "ev-1", script_rel)]
    claims, *_ = compiler.stage_derive_claim(spec, evidence=evidence)
    # M4: 4-tuple; the F3 reproduction content lives in the deposit record dump (record_path).
    paper_path, _si_path, record_path, _fc = compiler.stage_render(
        spec, evidence=evidence, claims=claims
    )
    paper_dir = paper_path.parent

    # Record dump: inlined body + listings package.
    si = record_path.read_text(encoding="utf-8")
    assert r"\section{Reproduction code}" in si
    assert r"\usepackage{listings}" in si
    assert r"\begin{lstlisting}" in si
    assert "print('reproduced')" in si

    # paper/code/ has the co-located script (basename), byte-equal to the source.
    colocated = paper_dir / "code" / "encode.py"
    assert colocated.exists()
    assert colocated.read_text(encoding="utf-8") == "print('reproduced')\n"

    # reproduce.py references the script + its filename, and is valid Python.
    repro_text = (paper_dir / "reproduce.py").read_text(encoding="utf-8")
    assert "encode.py" in repro_text
    assert script_rel in repro_text  # the real recorded code_ref
    assert "execute_python" in repro_text
    compile(repro_text, "reproduce.py", "exec")

    # The main paper stays tool-agnostic: no code listing leaks into draft.tex.
    paper = paper_path.read_text(encoding="utf-8")
    assert r"\begin{lstlisting}" not in paper
    assert "print('reproduced')" not in paper


def test_f3_reproduce_references_only_recorded_refs(tmp_path):
    """reproduce.py contains ONLY the code_refs actually recorded -- no fabrication."""
    spec = _f3_spec("t-f3-onlyrecorded")
    commit = "0011223344556677889900aabbccddeeff001122"
    evidence = [_f3_evidence(spec.id, "ev-1", commit)]
    _c, paper_path, _si = _render_with_evidence(tmp_path, spec, evidence)
    repro_text = (paper_path.parent / "reproduce.py").read_text(encoding="utf-8")
    # The recorded commit is present; an unrecorded ref must not be invented.
    assert commit in repro_text
    assert "deadbeef" not in repro_text


# ---------------------------------------------------------------------------
# P2 (field report): a RESOLVED (SUPPORTED/REFUTED) proof/qualitative hypothesis must NOT
# render a "Pending agent judgments" section. Otherwise a fully-resolved run carries stale
# pending scaffolding whose boilerplate ("verdict") + dumped finding digits trip the §10
# tool-vocabulary and number-audit gates -- the run failing verify on its OWN auto-output.
# ---------------------------------------------------------------------------

def _qualitative_spec(spec_id: str, hyp_id: str = "hyp-q") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="the qualitative criterion holds",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.QUALITATIVE,
                    expression="the criterion holds => support",
                ),
                referent="formal",
                non_circularity="the verifier checks a property not baked into the generator",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def test_stage_render_pending_section_gated_on_claim_resolution(tmp_path):
    from sci_adk.core.claim import Claim

    spec = _qualitative_spec("t-p2")
    evidence = [
        EvidenceItem(
            id="ev-q", spec_id=spec.id, kind=EvidenceKind.PROOF_STEP,
            provenance=Provenance(code_ref="fixture", data_source="generated"),
            result=Result(type="qualitative", finding="the proof body for hyp-q"),
            bears_on=[Bearing(target_id="hyp-q", direction=BearingDirection.SUPPORTS)],
        )
    ]
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_init_spec(spec=spec)

    # Regression guard: with NO resolved claim the checkpoint is still pending -> section shown.
    p_open, *_ = compiler.stage_render(spec, evidence=evidence, claims=[])
    assert r"\section{Pending agent judgments}" in p_open.read_text(encoding="utf-8")

    # P2: once the hypothesis' Claim is SUPPORTED, it is no longer pending -> NO section.
    resolved = Claim.create_null_result_claim(
        id="claim-hyp-q", spec_id=spec.id, answers="hyp-q",
        statement="the criterion holds", mode=HypothesisMode.CONFIRMATORY,
    )
    assert resolved.is_supported()
    p_res, *_ = compiler.stage_render(spec, evidence=evidence, claims=[resolved])
    assert r"\section{Pending agent judgments}" not in p_res.read_text(encoding="utf-8")


def test_stage_render_pending_not_dropped_by_supported_novelty_claim(tmp_path):
    # P2 edge: a per-kind NOVELTY claim (id 'claim-novelty-<kind>-<hyp>') shares
    # answers==hyp with the main claim. A SUPPORTED novelty claim must NOT mark the
    # hypothesis resolved -- the pending checkpoint tracks the MAIN experiment claim, still
    # PROPOSED here. The filter keys on the MAIN claim id, not Claim.answers.
    from sci_adk.core.claim import Claim

    spec = _qualitative_spec("t-p2-novelty")
    evidence = [
        EvidenceItem(
            id="ev-q", spec_id=spec.id, kind=EvidenceKind.PROOF_STEP,
            provenance=Provenance(code_ref="fixture", data_source="generated"),
            result=Result(type="qualitative", finding="the proof body for hyp-q"),
            bears_on=[Bearing(target_id="hyp-q", direction=BearingDirection.SUPPORTS)],
        )
    ]
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_init_spec(spec=spec)

    novelty_supported = Claim.create_null_result_claim(
        id="claim-novelty-result-hyp-q", spec_id=spec.id, answers="hyp-q",
        statement="Result-novelty: the qualitative criterion holds",
        mode=HypothesisMode.CONFIRMATORY,
    )
    assert novelty_supported.is_supported()
    # The MAIN claim is absent/unresolved -> the pending section MUST remain.
    p, *_ = compiler.stage_render(spec, evidence=evidence, claims=[novelty_supported])
    assert r"\section{Pending agent judgments}" in p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Proactive prior-work enforcement: the orchestrated "start research" path refuses to run
# experiments until the Spec-anchor prior-work DECISION is recorded (search-or-skip). The
# raw library primitive default is unchanged (no enforcement) so direct callers/tests are
# unaffected. It forces a DECISION, not a search (a recorded skip-with-reason clears it).
# ---------------------------------------------------------------------------

def test_compile_enforce_prior_work_halts_until_recorded(tmp_path):
    import pytest

    from sci_adk.loop.prior_work import PriorWorkHalt, record_prior_work_skip

    spec = _f3_spec("t-pw-enforce")
    compiler = ResearchCompiler(workspace_dir=tmp_path)

    # enforce on + no prior-work decision -> halt BEFORE experiments. The run dir + spec are
    # already laid down (stage_init_spec ran), so the human can record the decision.
    with pytest.raises(PriorWorkHalt):
        compiler.compile("", spec=spec, enforce_prior_work=True)
    assert (tmp_path / "runs" / "t-pw-enforce" / "spec.json").is_file()

    # Record a skip-with-reason -> the halt clears; the same enforced compile now proceeds.
    record_prior_work_skip(spec, tmp_path, reason="covered by an upstream review")
    result = compiler.compile("", spec=spec, enforce_prior_work=True)
    assert result.spec.id == "t-pw-enforce"


def test_compile_default_does_not_enforce_prior_work(tmp_path):
    # The raw primitive default is unchanged: no flag -> no halt, even with prior-work open.
    spec = _f3_spec("t-pw-default")
    result = ResearchCompiler(workspace_dir=tmp_path).compile("", spec=spec)  # no raise
    assert result.spec.id == "t-pw-default"
