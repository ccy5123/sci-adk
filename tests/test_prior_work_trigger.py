"""
Spec-time prior-work trigger (RED-first).

design/literature-acquisition.md §"Discovery trigger model": at Spec creation the
compiler emits a *recording-type* prior_work checkpoint -- a reminder that prior
art has not yet been considered. It is NOT a judgment: no verdict trail, not
hypothesis-bound. It stays open until a prior-work decision is recorded in the
single append-only Evidence log, either:

  - **searched**  -> a ``LITERATURE`` EvidenceItem (existing acquisition path), or
  - **not searched** -> a ``PRIOR_WORK_DECISION`` EvidenceItem carrying the reason
    (a recorded null -- Invariant E2: null results are results).

These tests lock:
  1. the checkpoint discriminator (judge kind unchanged; prior_work kind distinct);
  2. the new ``PRIOR_WORK_DECISION`` EvidenceKind round-trips in the normal log;
  3. the Spec-time emit (recording-type, not hypothesis-bound);
  4. the searched / not-searched recorders that close the checkpoint;
  5. a one-cycle demo of BOTH outcomes (a required deliverable).

No LLM anywhere: discovery is the in-session agent's web_search upstream; this
code only records the *decision* and (searched path) drives the existing acquirer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.core.evidence import EvidenceItem, EvidenceKind
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


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _spec(spec_id: str = "pw-spec", version: int = 1) -> Spec:
    return Spec(
        id=spec_id,
        version=version,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="m", expected_output="o"
        ),
        hypotheses=[
            Hypothesis(
                id="hyp-1",
                statement="a universal claim",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.QUALITATIVE,
                    expression="clear and on-topic",
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-1")],
    )


# --------------------------------------------------------------------------- #
# 1. CheckpointModel discriminator -- judge kind UNCHANGED, prior_work distinct
# --------------------------------------------------------------------------- #

def test_judge_checkpoint_round_trips_unchanged():
    """The judge checkpoint keeps its exact shape (no regression for the rail)."""
    from sci_adk.loop.verdict import JudgeCheckpoint

    cp = JudgeCheckpoint(
        hypothesis_id="hyp-1",
        kind="proof",
        expression="verified derivation => support; counterexample => refute",
        finding="the proof body the agent should judge",
        spec_version=1,
    )
    dumped = cp.model_dump(mode="json")
    restored = JudgeCheckpoint.model_validate(dumped)
    assert restored == cp
    assert restored.kind == "proof"
    assert restored.hypothesis_id == "hyp-1"


def test_checkpoint_model_is_judge_checkpoint_alias():
    """``CheckpointModel`` (the historical name) IS the judge checkpoint."""
    from sci_adk.loop.verdict import CheckpointModel, JudgeCheckpoint

    assert CheckpointModel is JudgeCheckpoint


def test_prior_work_checkpoint_has_its_own_fields_no_judge_fields():
    """prior_work carries spec_id / trigger / spec_version / prompt -- and does
    NOT require the judge fields (hypothesis_id, expression)."""
    from sci_adk.loop.verdict import PriorWorkCheckpoint

    cp = PriorWorkCheckpoint(
        spec_id="pw-spec",
        spec_version=1,
        prompt="Has this been done? Search prior work before any result exists.",
    )
    assert cp.spec_id == "pw-spec"
    assert cp.trigger == "spec_creation"          # the only trigger for now
    assert cp.spec_version == 1
    # judge-only fields are absent on the model
    assert not hasattr(cp, "hypothesis_id")
    assert not hasattr(cp, "expression")


def test_prior_work_checkpoint_round_trips():
    from sci_adk.loop.verdict import PriorWorkCheckpoint

    cp = PriorWorkCheckpoint(spec_id="pw-spec", spec_version=2, prompt="check it")
    restored = PriorWorkCheckpoint.model_validate(cp.model_dump(mode="json"))
    assert restored == cp


def test_prior_work_checkpoint_rejects_foreign_trigger():
    """Only the Spec-creation trigger exists now (the others are deferred)."""
    from sci_adk.loop.verdict import PriorWorkCheckpoint

    with pytest.raises(ValueError):
        PriorWorkCheckpoint(
            spec_id="pw-spec",
            spec_version=1,
            prompt="x",
            trigger="paper_render",   # deferred trigger -- not allowed yet
        )


def test_checkpoint_discriminated_union_routes_by_checkpoint_type():
    """The tagged union picks the right member by ``checkpoint_type`` on load."""
    from pydantic import TypeAdapter

    from sci_adk.loop.verdict import (
        Checkpoint,
        JudgeCheckpoint,
        PriorWorkCheckpoint,
    )

    adapter = TypeAdapter(Checkpoint)

    judge = JudgeCheckpoint(
        hypothesis_id="hyp-1", kind="qualitative",
        expression="clear and on-topic", spec_version=1,
    )
    pw = PriorWorkCheckpoint(spec_id="pw-spec", spec_version=1, prompt="check")

    judge_back = adapter.validate_python(judge.model_dump(mode="json"))
    pw_back = adapter.validate_python(pw.model_dump(mode="json"))

    assert isinstance(judge_back, JudgeCheckpoint)
    assert isinstance(pw_back, PriorWorkCheckpoint)


def test_judge_fields_rejected_on_prior_work_member():
    """A prior_work payload carrying judge-only keys is rejected (type safety)."""
    from pydantic import TypeAdapter, ValidationError

    from sci_adk.loop.verdict import Checkpoint

    adapter = TypeAdapter(Checkpoint)
    bad = {
        "checkpoint_type": "prior_work",
        "spec_id": "pw-spec",
        "spec_version": 1,
        "prompt": "check",
        "hypothesis_id": "hyp-1",   # judge-only -> forbidden on prior_work
        "expression": "x",
    }
    with pytest.raises(ValidationError):
        adapter.validate_python(bad)


def test_type_adapter_loads_legacy_judge_file_without_discriminator():
    """Fix 2: a pre-existing judge checkpoint on disk lacks ``checkpoint_type`` (it
    predates the discriminator). ``TypeAdapter(Checkpoint)`` must still load it as a
    JudgeCheckpoint (missing tag defaults to "judge") -- the docstring contract that
    the union loads either arm must actually hold for legacy files."""
    from pydantic import TypeAdapter

    from sci_adk.loop.verdict import Checkpoint, JudgeCheckpoint

    adapter = TypeAdapter(Checkpoint)
    legacy = {
        # NO "checkpoint_type" key -- exactly what older judge files contain.
        "hypothesis_id": "hyp-1",
        "kind": "proof",
        "expression": "verified derivation => support",
        "finding": "the proof body",
        "spec_version": 1,
    }
    loaded = adapter.validate_python(legacy)
    assert isinstance(loaded, JudgeCheckpoint)
    assert loaded.kind == "proof"
    assert loaded.checkpoint_type == "judge"


# --------------------------------------------------------------------------- #
# 2. PRIOR_WORK_DECISION EvidenceKind -- round-trips in the SINGLE log
# --------------------------------------------------------------------------- #

def test_prior_work_decision_evidence_kind_exists():
    assert EvidenceKind.PRIOR_WORK_DECISION.value == "prior_work_decision"


def test_prior_work_decision_evidence_item_round_trips():
    """The skip decision is a normal EvidenceItem -> the record-only re-read keeps
    working (additive enum value, ordinary (de)serialization)."""
    from sci_adk.core.evidence import Provenance, Result

    item = EvidenceItem(
        id="evi-pw-decision-1",
        spec_id="pw-spec",
        kind=EvidenceKind.PRIOR_WORK_DECISION,
        provenance=Provenance(code_ref="prior_work:skip"),
        result=Result(type="qualitative",
                      finding="skipped: pure-math reframing, no empirical prior art"),
        bears_on=[],
    )
    restored = EvidenceItem.model_validate(item.model_dump(mode="json"))
    assert restored == item
    assert restored.kind is EvidenceKind.PRIOR_WORK_DECISION
    # a recorded null: not bound to any hypothesis/claim
    assert restored.bears_on == []


# --------------------------------------------------------------------------- #
# 3. Spec-time emit -- recording-type, not hypothesis-bound, no trail
# --------------------------------------------------------------------------- #

def test_compile_emits_prior_work_checkpoint_at_spec_creation(tmp_path):
    from sci_adk.loop.compiler import ResearchCompiler

    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n",
        spec_id="pw-emit",
    )
    pw = result.prior_work_checkpoint
    assert pw is not None
    assert pw.spec_id == "pw-emit"
    assert pw.trigger == "spec_creation"
    assert pw.spec_version == result.spec.version
    # recording-type: not bound to a hypothesis, carries no verdict-trail fields
    assert not hasattr(pw, "hypothesis_id")
    assert not hasattr(pw, "expression")


def test_compile_writes_typed_prior_work_checkpoint_json(tmp_path):
    """The prior_work checkpoint is persisted as a typed checkpoints/*.json with a
    discriminator so it is distinguishable from judge checkpoints on disk."""
    from sci_adk.loop.compiler import ResearchCompiler

    ResearchCompiler(workspace_dir=tmp_path).compile(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n",
        spec_id="pw-disk",
    )
    cp_path = tmp_path / "runs" / "pw-disk" / "checkpoints" / "prior_work.json"
    assert cp_path.exists()
    data = json.loads(cp_path.read_text(encoding="utf-8"))
    assert data["checkpoint_type"] == "prior_work"
    assert data["trigger"] == "spec_creation"
    assert data["spec_id"] == "pw-disk"


def test_prior_work_checkpoint_open_until_decision_recorded(tmp_path):
    """Open when no LITERATURE / PRIOR_WORK_DECISION evidence exists for the Spec."""
    from sci_adk.loop.prior_work import prior_work_open

    spec = _spec("pw-open")
    (tmp_path / "runs" / spec.id / "evidence").mkdir(parents=True, exist_ok=True)
    assert prior_work_open(spec, tmp_path) is True


# --------------------------------------------------------------------------- #
# 4. The two recorders -- searched (LITERATURE) / not searched (PRIOR_WORK_DECISION)
# --------------------------------------------------------------------------- #

def test_record_prior_work_skip_writes_decision_evidence_with_reason(tmp_path):
    from sci_adk.loop.prior_work import prior_work_open, record_prior_work_skip

    spec = _spec("pw-skip")
    reason = "reframed as a pure-math injectivity proof; no empirical prior art applies"
    item = record_prior_work_skip(spec, tmp_path, reason=reason)

    assert item.kind is EvidenceKind.PRIOR_WORK_DECISION
    assert reason in (item.result.finding or "")
    assert item.bears_on == []                     # a recorded decision, not a belief
    # persisted into the single evidence log
    ev_path = tmp_path / "runs" / spec.id / "evidence" / f"{item.id}.json"
    assert ev_path.exists()
    # and the checkpoint is now closed
    assert prior_work_open(spec, tmp_path) is False


def test_record_prior_work_skip_requires_a_reason(tmp_path):
    """A null result is still a *recorded* result -- an empty reason is refused."""
    from sci_adk.loop.prior_work import record_prior_work_skip

    spec = _spec("pw-skip-noreason")
    with pytest.raises(ValueError):
        record_prior_work_skip(spec, tmp_path, reason="   ")


def test_searched_path_closes_checkpoint_via_literature_evidence(tmp_path):
    """The searched path drives the EXISTING acquirer -> a LITERATURE EvidenceItem
    closes the checkpoint (we do not reinvent acquisition)."""
    from sci_adk.loop.prior_work import prior_work_open, record_prior_work_searched
    from sci_adk.search.paperforge_adapter import (
        AcquisitionRecord,
        AcquisitionResult,
    )

    class _FakeAdapter:
        def fetch(self, dois, out_dir, **opts):
            out_dir = Path(out_dir)
            records = [
                AcquisitionRecord(doi=d, status="success", source="arxiv",
                                  license="cc-by", filename=f"{i}.pdf")
                for i, d in enumerate(dois)
            ]
            return AcquisitionResult(
                returncode=0,
                output_dir=out_dir,
                manifest_path=out_dir / "manifest.csv",
                records=records,
                provenance={"pinned_sha": "deadbeef", "installed_version": "0.1"},
            )

    spec = _spec("pw-searched")
    # The searched path now requires a contact email by default (E4); this test
    # exercises the acquisition/decision mechanics, not the email policy, so inject a
    # test email to satisfy the requirement (a real adapter is faked out anyway).
    outcome = record_prior_work_searched(
        spec, tmp_path, dois=["10.1/x"], adapter=_FakeAdapter(),
        email="prior-work-test@example.org",
    )
    # the acquisition artifact is the LITERATURE item ...
    assert outcome.evidence.kind is EvidenceKind.LITERATURE
    # ... and the searched path also recorded an explicit prior-art DECISION, which
    # is what actually closes the checkpoint (Fix 1: never a bare LITERATURE item).
    assert prior_work_open(spec, tmp_path) is False


# --------------------------------------------------------------------------- #
# 4b. Fix 1 -- the DECISION (not a bare acquisition) closes the checkpoint
# --------------------------------------------------------------------------- #

def _make_fake_adapter():
    """A paperforge stand-in that 'acquires' every DOI successfully (no network)."""
    from sci_adk.search.paperforge_adapter import (
        AcquisitionRecord,
        AcquisitionResult,
    )

    class _FakeAdapter:
        def fetch(self, dois, out_dir, **opts):
            out_dir = Path(out_dir)
            return AcquisitionResult(
                returncode=0,
                output_dir=out_dir,
                manifest_path=out_dir / "manifest.csv",
                records=[AcquisitionRecord(doi=d, status="success", source="arxiv",
                                           license="cc-by", filename=f"{i}.pdf")
                         for i, d in enumerate(dois)],
                provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
            )

    return _FakeAdapter()


def test_bare_literature_item_does_NOT_close_the_checkpoint(tmp_path):
    """A LITERATURE item acquired for some OTHER reason (no PRIOR_WORK_DECISION) must
    NOT close the prior-work checkpoint -- the checkpoint closes solely on an explicit
    prior-art decision record (Fix 1). Otherwise a future trigger that acquires
    literature would spuriously satisfy the Spec-time prior-art check."""
    from sci_adk.loop.literature_acquirer import LiteratureAcquirer
    from sci_adk.loop.prior_work import prior_work_open

    spec = _spec("pw-bare-lit")
    # Acquire a LITERATURE item directly (NOT via the prior-work recorder), as a
    # later trigger might -- no prior-art decision is recorded.
    outcome = LiteratureAcquirer(
        spec, tmp_path, adapter=_make_fake_adapter()
    ).acquire(["10.9/other"])
    assert outcome.evidence.kind is EvidenceKind.LITERATURE
    # The checkpoint is still OPEN: a bare acquisition is not a prior-art decision.
    assert prior_work_open(spec, tmp_path) is True


def test_searched_path_writes_an_explicit_prior_work_decision(tmp_path):
    """The searched path emits BOTH a LITERATURE acquisition artifact AND an explicit
    PRIOR_WORK_DECISION record; only the latter closes the checkpoint (Fix 1)."""
    from sci_adk.core.evidence import EvidenceItem
    from sci_adk.loop.prior_work import prior_work_open, record_prior_work_searched

    spec = _spec("pw-searched-decision")
    assert prior_work_open(spec, tmp_path) is True
    record_prior_work_searched(
        spec, tmp_path, dois=["10.1/a", "10.1/b"], adapter=_make_fake_adapter(),
        email="prior-work-test@example.org")

    # Scan the single append-only log: both kinds are present.
    ev_dir = tmp_path / "runs" / spec.id / "evidence"
    items = [
        EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(ev_dir.glob("*.json"))
    ]
    kinds = [i.kind for i in items]
    assert EvidenceKind.LITERATURE in kinds
    assert EvidenceKind.PRIOR_WORK_DECISION in kinds

    decision = next(i for i in items if i.kind is EvidenceKind.PRIOR_WORK_DECISION)
    assert "searched" in (decision.result.finding or "").lower()
    assert "10.1/a" in (decision.result.finding or "")
    assert decision.bears_on == []   # a decision, not a belief
    assert prior_work_open(spec, tmp_path) is False


# --------------------------------------------------------------------------- #
# 5. REQUIRED one-cycle demo of BOTH outcomes
# --------------------------------------------------------------------------- #

def test_one_cycle_demo_both_outcomes(tmp_path):
    """Required deliverable: a single demo showing what is recorded for the
    *searched* outcome vs the *not-searched* outcome, starting from the Spec-time
    checkpoint in each case."""
    from sci_adk.loop.compiler import ResearchCompiler
    from sci_adk.loop.prior_work import (
        prior_work_open,
        record_prior_work_searched,
        record_prior_work_skip,
    )
    from sci_adk.search.paperforge_adapter import (
        AcquisitionRecord,
        AcquisitionResult,
    )

    class _FakeAdapter:
        def fetch(self, dois, out_dir, **opts):
            out_dir = Path(out_dir)
            return AcquisitionResult(
                returncode=0,
                output_dir=out_dir,
                manifest_path=out_dir / "manifest.csv",
                records=[AcquisitionRecord(doi=d, status="success", source="arxiv",
                                           license="cc-by", filename=f"{i}.pdf")
                         for i, d in enumerate(dois)],
                provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
            )

    proposal = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"

    # -- Outcome A: SEARCHED --------------------------------------------------
    res_a = ResearchCompiler(workspace_dir=tmp_path).compile(
        proposal, spec_id="demo-searched")
    spec_a = res_a.spec
    assert res_a.prior_work_checkpoint.trigger == "spec_creation"
    assert prior_work_open(spec_a, tmp_path) is True            # open at Spec time
    out = record_prior_work_searched(
        spec_a, tmp_path, dois=["10.48550/arXiv.1706.03762"], adapter=_FakeAdapter(),
        email="prior-work-test@example.org")
    assert out.evidence.kind is EvidenceKind.LITERATURE
    assert prior_work_open(spec_a, tmp_path) is False           # now closed

    # -- Outcome B: NOT SEARCHED ---------------------------------------------
    res_b = ResearchCompiler(workspace_dir=tmp_path).compile(
        proposal, spec_id="demo-skipped")
    spec_b = res_b.spec
    assert res_b.prior_work_checkpoint.trigger == "spec_creation"
    assert prior_work_open(spec_b, tmp_path) is True            # open at Spec time
    item = record_prior_work_skip(
        spec_b, tmp_path,
        reason="pure-math reframing; no empirical prior art applies")
    assert item.kind is EvidenceKind.PRIOR_WORK_DECISION
    assert prior_work_open(spec_b, tmp_path) is False           # now closed

    # The two outcomes are distinguishable in the single log by EvidenceKind.
    assert out.evidence.kind is not item.kind
