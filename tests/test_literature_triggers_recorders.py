"""
novelty + contested recorders (RED-first) -- shared writer, reuse the acquirer.

design/literature-acquisition.md §"Discovery trigger model": the novelty and contested
recorders sit beside the Spec-creation prior-work recorders and reuse a SHARED
decision-writer (no duplicated write/id/save logic). The searched path drives the
EXISTING ``LiteratureAcquirer`` (same contact-email policy as
``record_prior_work_searched`` incl. ``ConfigHalt``).

Covered:
  - ``record_novelty_searched`` -> a LITERATURE acquisition artifact + a
    NOVELTY_DECISION(outcome="searched") referencing it; bears_on=[].
  - ``record_novelty_searched`` honors the contact-email policy (ConfigHalt by default).
  - ``record_novelty_skip`` -> NOVELTY_DECISION(outcome="skipped") with a required reason.
  - ``record_contested`` with DOIs -> a LITERATURE artifact + a CONTESTED_RECORD.
  - REGRESSION: NOVELTY_DECISION / CONTESTED_RECORD do NOT close the Spec-creation
    prior_work checkpoint (separate kinds; the prior_work closing-kind set is unchanged).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.config import ConfigHalt
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
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _spec(spec_id: str, hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="a claim",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.QUALITATIVE, expression="clear and on-topic"
                ),
                novelty=True,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


class _FakeAdapter:
    """A paperforge stand-in that 'acquires' every DOI successfully (no network)."""

    def fetch(self, dois, out_dir, **opts):
        out_dir = Path(out_dir)
        return AcquisitionResult(
            returncode=0,
            output_dir=out_dir,
            manifest_path=out_dir / "manifest.csv",
            records=[
                AcquisitionRecord(doi=d, status="success", source="arxiv",
                                  license="cc-by", filename=f"{i}.pdf")
                for i, d in enumerate(dois)
            ],
            provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
        )


def _load_evidence(workspace: Path, spec_id: str) -> list[EvidenceItem]:
    ev_dir = workspace / "runs" / spec_id / "evidence"
    if not ev_dir.is_dir():
        return []
    return [
        EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(ev_dir.glob("*.json"))
    ]


# --------------------------------------------------------------------------- #
# novelty: searched
# --------------------------------------------------------------------------- #

def test_record_novelty_searched_writes_decision_referencing_literature(tmp_path):
    from sci_adk.loop.literature_triggers import record_novelty_searched

    spec = _spec("nov-searched")
    outcome = record_novelty_searched(
        spec, tmp_path, hypothesis_id="hyp-1", dois=["10.1/a", "10.1/b"],
        adapter=_FakeAdapter(), email="novelty-test@example.org",
    )
    # the acquisition artifact is a LITERATURE item ...
    assert outcome.evidence.kind is EvidenceKind.LITERATURE

    items = _load_evidence(tmp_path, spec.id)
    kinds = [i.kind for i in items]
    assert EvidenceKind.LITERATURE in kinds
    assert EvidenceKind.NOVELTY_DECISION in kinds

    decision = next(i for i in items if i.kind is EvidenceKind.NOVELTY_DECISION)
    assert decision.literature_decision is not None
    assert decision.literature_decision.outcome == "searched"
    assert decision.literature_decision.hypothesis_id == "hyp-1"
    # references the acquired LITERATURE item for traceability
    assert decision.literature_decision.literature_evidence_id == outcome.evidence.id
    assert decision.bears_on == []  # a recorded decision, not a belief


def test_record_novelty_searched_requires_email_by_default(tmp_path, monkeypatch):
    """Same contact-email policy as record_prior_work_searched: no email -> ConfigHalt
    BEFORE any acquisition (the spy adapter's fetch is never called)."""
    from sci_adk.loop.literature_triggers import record_novelty_searched

    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    cfg_root = tmp_path / "cfg"
    cfg_root.mkdir(parents=True, exist_ok=True)

    calls = {"n": 0}

    class _Spy(_FakeAdapter):
        def fetch(self, dois, out_dir, **opts):
            calls["n"] += 1
            return super().fetch(dois, out_dir, **opts)

    spec = _spec("nov-noemail")
    with pytest.raises(ConfigHalt):
        record_novelty_searched(
            spec, tmp_path, hypothesis_id="hyp-1", dois=["10.1/x"],
            adapter=_Spy(), config_root=cfg_root,
        )
    assert calls["n"] == 0  # no acquisition attempted


# --------------------------------------------------------------------------- #
# novelty: skip
# --------------------------------------------------------------------------- #

def test_record_novelty_skip_writes_decision_with_reason(tmp_path):
    from sci_adk.loop.literature_triggers import record_novelty_skip

    spec = _spec("nov-skip")
    item = record_novelty_skip(
        spec, tmp_path, hypothesis_id="hyp-1",
        reason="the priority framing was dropped in review",
    )
    assert item.kind is EvidenceKind.NOVELTY_DECISION
    assert item.literature_decision.outcome == "skipped"
    assert item.literature_decision.hypothesis_id == "hyp-1"
    assert "dropped in review" in (item.result.finding or "")
    assert item.bears_on == []


def test_record_novelty_skip_requires_reason(tmp_path):
    from sci_adk.loop.literature_triggers import record_novelty_skip

    spec = _spec("nov-skip-noreason")
    with pytest.raises(ValueError):
        record_novelty_skip(spec, tmp_path, hypothesis_id="hyp-1", reason="  ")


# --------------------------------------------------------------------------- #
# contested with DOIs -> acquire + reference
# --------------------------------------------------------------------------- #

def test_record_contested_with_dois_acquires_and_references(tmp_path):
    from sci_adk.loop.literature_triggers import record_contested

    spec = _spec("con-with-dois")
    item = record_contested(
        spec, tmp_path, hypothesis_id="hyp-1",
        reason_or_note="found conflicting prior work after the result",
        dois=["10.1/conflict"], adapter=_FakeAdapter(), email="con-test@example.org",
    )
    assert item.kind is EvidenceKind.CONTESTED_RECORD
    assert item.literature_decision.outcome == "recorded"
    # the acquired LITERATURE item is in the log and referenced by the record
    items = _load_evidence(tmp_path, spec.id)
    assert EvidenceKind.LITERATURE in [i.kind for i in items]
    assert item.literature_decision.literature_evidence_id is not None


# --------------------------------------------------------------------------- #
# REGRESSION: new decision kinds do NOT close the Spec-creation prior_work check
# --------------------------------------------------------------------------- #

def test_novelty_decision_does_not_close_prior_work(tmp_path):
    """A NOVELTY_DECISION must NOT spuriously satisfy the Spec-time prior-art check --
    that check closes ONLY on PRIOR_WORK_DECISION (separate kinds)."""
    from sci_adk.loop.literature_triggers import record_novelty_skip
    from sci_adk.loop.prior_work import prior_work_open

    spec = _spec("reg-nov")
    assert prior_work_open(spec, tmp_path) is True
    record_novelty_skip(spec, tmp_path, hypothesis_id="hyp-1", reason="r")
    # prior_work is STILL open: a novelty decision is a different kind.
    assert prior_work_open(spec, tmp_path) is True


def test_contested_record_does_not_close_prior_work(tmp_path):
    """A CONTESTED_RECORD must NOT close the Spec-creation prior-work checkpoint."""
    from sci_adk.loop.literature_triggers import record_contested
    from sci_adk.loop.prior_work import prior_work_open

    spec = _spec("reg-con")
    # a contested claim so record_contested has something to record against
    from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
    claims_dir = tmp_path / "runs" / spec.id / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim = Claim(
        id="claim-hyp-1", spec_id=spec.id, answers="hyp-1", statement="c",
        status=ClaimStatus.CONTESTED,
        confidence=Confidence(type=ConfidenceType.GRADED, level="moderate", basis="mixed"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (claims_dir / "claim-hyp-1.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8")

    assert prior_work_open(spec, tmp_path) is True
    record_contested(spec, tmp_path, hypothesis_id="hyp-1", reason_or_note="note")
    assert prior_work_open(spec, tmp_path) is True
