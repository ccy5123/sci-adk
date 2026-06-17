"""
record_novelty_searched found-split + novelty_open / novelty_checkpoint (RED-first).

design/literature-acquisition.md §"Discovery trigger model" (B-replace): a novelty
*searched* decision now records its OUTCOME -- ``found_nothing`` (prior art search
returned nothing -> supports the novelty claim) or ``found_something`` (prior art
exists -> does not). ``record_novelty_searched`` gains a required ``found`` param
mapping "nothing"/"something" to the LiteratureDecision outcome.

``novelty_open(spec, hypothesis_id)`` mirrors ``contested_open``: True iff the
hypothesis is novelty=True AND its ``claim-novelty-<hyp>`` on disk is PROPOSED.
``novelty_checkpoint(spec, hyp, version, reason=...)`` builds the reason-tailored
NoveltyCheckpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
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
from sci_adk.loop.literature_triggers import (
    novelty_checkpoint,
    novelty_open,
    record_novelty_searched,
)
from sci_adk.loop.verdict import NoveltyCheckpoint
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult


def _spec(spec_id: str, hyp_id: str = "hyp-1", novelty: bool = True) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.QUALITATIVE, expression="clear"),
                novelty=novelty,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


class _FakeAdapter:
    def fetch(self, dois, out_dir, **opts):
        out_dir = Path(out_dir)
        return AcquisitionResult(
            returncode=0, output_dir=out_dir, manifest_path=out_dir / "manifest.csv",
            records=[AcquisitionRecord(doi=d, status="success", source="arxiv",
                                       license="cc-by", filename=f"{i}.pdf")
                     for i, d in enumerate(dois)],
            provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
        )


def _load_novelty_decisions(run_dir: Path) -> list[EvidenceItem]:
    ev_dir = run_dir / "evidence"
    out = []
    for p in sorted(ev_dir.glob("*.json")):
        item = EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        if item.kind is EvidenceKind.NOVELTY_DECISION:
            out.append(item)
    return out


def _write_novelty_claim(run_dir: Path, spec_id: str, status: ClaimStatus,
                         hyp_id: str = "hyp-1") -> None:
    claims_dir = run_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim = Claim(
        id=f"claim-novelty-{hyp_id}", spec_id=spec_id, answers=hyp_id,
        statement="novelty", status=status,
        confidence=Confidence(type=ConfidenceType.GRADED, level="moderate", basis="x"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (claims_dir / f"claim-novelty-{hyp_id}.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# record_novelty_searched found-split
# --------------------------------------------------------------------------- #

def test_record_novelty_searched_found_nothing_writes_found_nothing(tmp_path):
    spec = _spec("nov-fn")
    record_novelty_searched(
        spec, tmp_path, hypothesis_id="hyp-1", dois=["10.1/x"],
        adapter=_FakeAdapter(), email="x@y.z", found="nothing",
    )
    decisions = _load_novelty_decisions(tmp_path / "runs" / spec.id)
    outcomes = [d.literature_decision.outcome for d in decisions
                if d.literature_decision is not None]
    assert "found_nothing" in outcomes


def test_record_novelty_searched_found_something_writes_found_something(tmp_path):
    spec = _spec("nov-fs")
    record_novelty_searched(
        spec, tmp_path, hypothesis_id="hyp-1", dois=["10.1/x"],
        adapter=_FakeAdapter(), email="x@y.z", found="something",
    )
    decisions = _load_novelty_decisions(tmp_path / "runs" / spec.id)
    outcomes = [d.literature_decision.outcome for d in decisions
                if d.literature_decision is not None]
    assert "found_something" in outcomes


# --------------------------------------------------------------------------- #
# novelty_open
# --------------------------------------------------------------------------- #

def test_novelty_open_true_when_claim_proposed(tmp_path):
    spec = _spec("nov-open-prop")
    run_dir = tmp_path / "runs" / spec.id
    _write_novelty_claim(run_dir, spec.id, ClaimStatus.PROPOSED)
    assert novelty_open(spec, "hyp-1", tmp_path) is True


def test_novelty_open_false_when_claim_supported(tmp_path):
    spec = _spec("nov-open-sup")
    run_dir = tmp_path / "runs" / spec.id
    _write_novelty_claim(run_dir, spec.id, ClaimStatus.SUPPORTED)
    assert novelty_open(spec, "hyp-1", tmp_path) is False


def test_novelty_open_false_for_non_novelty_hypothesis(tmp_path):
    spec = _spec("nov-open-off", novelty=False)
    run_dir = tmp_path / "runs" / spec.id
    _write_novelty_claim(run_dir, spec.id, ClaimStatus.PROPOSED)
    assert novelty_open(spec, "hyp-1", tmp_path) is False


def test_novelty_open_true_when_no_claim_yet(tmp_path):
    """A novelty hypothesis with no recorded novelty claim is implicitly PROPOSED ->
    open."""
    spec = _spec("nov-open-noclaim")
    assert novelty_open(spec, "hyp-1", tmp_path) is True


# --------------------------------------------------------------------------- #
# novelty_checkpoint reason-tailoring
# --------------------------------------------------------------------------- #

def test_novelty_checkpoint_not_searched_reason():
    spec = _spec("nov-cp-ns")
    cp = novelty_checkpoint(spec, "hyp-1", 1, reason="not_searched")
    assert isinstance(cp, NoveltyCheckpoint)
    assert cp.hypothesis_id == "hyp-1"
    assert cp.spec_id == "nov-cp-ns"
    assert "search" in cp.prompt.lower()


def test_novelty_checkpoint_found_something_reason():
    spec = _spec("nov-cp-fs")
    cp = novelty_checkpoint(spec, "hyp-1", 1, reason="found_something")
    prompt = cp.prompt.lower()
    assert "amend" in prompt or "f7" in prompt
    assert "found" in prompt or "prior art" in prompt
