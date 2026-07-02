"""
Mid-research emergent-question trigger (design/literature-acquisition.md, field-report
concern 2): ``sci-adk inquiry`` records an INQUIRY_DECISION when a new question arises
DURING research -- searched (-> LITERATURE) or skipped-with-reason (a recorded null).
Like the other decision kinds it is a record, not a belief (bears_on=[]), and its
code_ref is a decision pointer, not generating code (excluded from the reproduction gate).
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
from sci_adk.loop.inquiry import record_inquiry_searched, record_inquiry_skip


def _spec(spec_id: str = "inq") -> Spec:
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id="hyp-n", statement="s", mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= t => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-n")],
    )


def test_record_inquiry_skip_writes_decision_with_question_and_reason(tmp_path):
    spec = _spec("inq-skip")
    question = "does an independent method already measure this endpoint?"
    reason = "out of scope for the frozen MethodPlan; noted for future work"
    item = record_inquiry_skip(spec, tmp_path, question=question, reason=reason)

    assert item.kind is EvidenceKind.INQUIRY_DECISION
    assert question in (item.result.finding or "")
    assert reason in (item.result.finding or "")
    assert item.bears_on == []  # a recorded decision, not a belief
    assert item.provenance.code_ref == "inquiry:skip"
    ev_path = tmp_path / "runs" / spec.id / "evidence" / f"{item.id}.json"
    assert ev_path.exists()


def test_record_inquiry_requires_non_blank_question(tmp_path):
    spec = _spec("inq-noq")
    with pytest.raises(ValueError):
        record_inquiry_skip(spec, tmp_path, question="   ", reason="r")


def test_record_inquiry_skip_requires_reason(tmp_path):
    spec = _spec("inq-noreason")
    with pytest.raises(ValueError):
        record_inquiry_skip(spec, tmp_path, question="a real question?", reason="  ")


def test_record_inquiry_searched_records_decision_and_literature(tmp_path):
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
                returncode=0, output_dir=out_dir,
                manifest_path=out_dir / "manifest.csv", records=records,
                provenance={"pinned_sha": "deadbeef", "installed_version": "0.1"},
            )

    spec = _spec("inq-searched")
    outcome = record_inquiry_searched(
        spec, tmp_path, question="has anyone measured X mid-study?",
        dois=["10.1/x"], adapter=_FakeAdapter(), email="inq-test@example.org",
    )
    # The acquisition artifact is the LITERATURE item ...
    assert outcome.evidence.kind is EvidenceKind.LITERATURE
    # ... and an explicit INQUIRY_DECISION was also recorded in the log.
    ev_dir = tmp_path / "runs" / spec.id / "evidence"
    kinds = {
        EvidenceItem.model_validate_json(p.read_text(encoding="utf-8")).kind
        for p in ev_dir.glob("*.json")
    }
    assert EvidenceKind.INQUIRY_DECISION in kinds
    assert EvidenceKind.LITERATURE in kinds


def test_inquiry_decision_excluded_from_reproduction_gate(tmp_path):
    # An INQUIRY_DECISION carries a decision pointer (inquiry:skip), NOT generating code.
    # The reproduction-bundle gate must not require it in the already-rendered reproduce.py
    # (same class as prior-work / novelty / contested; the field-report P3 trap).
    from sci_adk.loop.verify import _reproduction_bundle_problems

    run_dir = tmp_path / "runs" / "inq-repro"
    (run_dir / "paper").mkdir(parents=True, exist_ok=True)
    (run_dir / "paper" / "reproduce.py").write_text(
        'SCRIPTS = []\nPOINTERS = [("ev-gen", "gen-commit")]\n', encoding="utf-8"
    )
    evidence = [
        EvidenceItem(
            id="ev-gen", spec_id="inq-repro", kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="gen-commit", data_source="generated"),
            result=Result(type="quantitative", point=0.95),
            bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
        ),
        EvidenceItem(
            id="evi-inquiry-1", spec_id="inq-repro",
            kind=EvidenceKind.INQUIRY_DECISION,
            provenance=Provenance(code_ref="inquiry:skip"),
            result=Result(type="qualitative", finding="inquiry skipped: q | reason: r"),
            bears_on=[],
        ),
    ]
    # The generating ref is still required and present; the inquiry pointer is excluded.
    assert _reproduction_bundle_problems(run_dir, evidence) == []


def test_cli_inquiry_skip_records_decision(tmp_path):
    from sci_adk.cli import main
    from sci_adk.loop.compiler import ResearchCompiler

    spec = _spec("inq-cli")
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    run_dir = tmp_path / "runs" / spec.id
    rc = main([
        "inquiry", str(run_dir),
        "--question", "does prior art already answer this sub-question?",
        "--skip", "--reason", "tangential to the frozen hypotheses",
    ])
    assert rc == 0
    kinds = {
        EvidenceItem.model_validate_json(p.read_text(encoding="utf-8")).kind
        for p in (run_dir / "evidence").glob("*.json")
    }
    assert EvidenceKind.INQUIRY_DECISION in kinds
