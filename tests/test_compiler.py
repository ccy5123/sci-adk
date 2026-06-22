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

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
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
    assert result.si_path is not None and result.si_path.exists()
    si = result.si_path.read_text(encoding="utf-8")
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
    # qualitative + no judge -> PROPOSED (inconclusive), recorded in the SI (the record),
    # not the belief-narrative paper.
    assert result.si_path is not None
    si = result.si_path.read_text(encoding="utf-8")
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
