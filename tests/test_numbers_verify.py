"""
`sci-adk verify` and the declared number list (design/declared-numbers.md §5).

Opt-in per run, like the declaration list:

  - a run WITH ``runs/<id>/numbers.json`` is checked by the declared-number checks INSTEAD
    of the pattern-based number audit (render/number_audit.py);
  - a run WITHOUT it keeps today's audit, byte for byte, and gets one advisory line
    recommending the list. No existing run changes verdict.

The blind conclusions reviewer may also note an identifier that reads as a reported
quantity; that note reaches the per-run advisory channel and can never fail a run.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sci_adk.cli import main
from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
from sci_adk.core.declarations import ConclusionReview
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
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
from sci_adk.loop.verify import verify_run
from sci_adk.render.number_audit import number_audit_problems, pool_from_record

_NON_CIRC = "the verifier checks a property not baked into the generator"
_DRAFT = (r"\section{Results}The value is 0.61 over 341 items, against a threshold of 0.5;"
          " the baseline 0.42 is not recorded anywhere.")


def _spec() -> Spec:
    return Spec(
        id="spec-n", version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id="hyp-a", statement="a recorded statement", mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="point >= threshold => support",
                params={"statistic": "point", "op": ">=", "value": 0.5},
            ),
            referent="formal", non_circularity=_NON_CIRC,
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-a")],
    )


def _run(tmp_path: Path, draft: str | None = _DRAFT, *, pubreqs: bool = True) -> Path:
    spec = _spec()
    run_dir = tmp_path / "runs" / spec.id
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "claims").mkdir()
    (run_dir / "spec.json").write_text(spec.model_dump_json(), encoding="utf-8")
    ev = EvidenceItem(
        id="ev-1", spec_id=spec.id, kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=0.61,
                      finding=json.dumps({"summary": "the run", "n_items": 341,
                                          "baseline": 0.42})),
        bears_on=[Bearing(target_id="hyp-a", direction=BearingDirection.SUPPORTS)],
    )
    (run_dir / "evidence" / "ev-1.json").write_text(ev.model_dump_json(), encoding="utf-8")
    claim = Claim(
        id="claim-hyp-a", spec_id=spec.id, answers="hyp-a", statement="s",
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(type=ConfidenceType.RULE, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (run_dir / "claims" / "claim-hyp-a.json").write_text(
        claim.model_dump_json(), encoding="utf-8")
    if draft is not None:
        (run_dir / "paper").mkdir()
        (run_dir / "paper" / "draft.tex").write_text(draft, encoding="utf-8")
    if pubreqs:
        (run_dir / "pubreqs.json").write_text(PubReqs(
            spec_id=spec.id, digest="fixture", required_sections=[],
            figure_font_policy=False, image_min_dpi=None, reproduction_bundle=False,
        ).model_dump_json(), encoding="utf-8")
        from sci_adk.loop.prior_work import record_prior_work_skip
        record_prior_work_skip(spec, tmp_path, reason="fixture: another gate under test")
    return run_dir


def _numbers(run_dir: Path, *entries: dict) -> None:
    (run_dir / "numbers.json").write_text(
        json.dumps({"spec_id": "spec-n", "numbers": list(entries)}), encoding="utf-8")


FULL = (
    {"text": "0.61", "source": {"evidence": "ev-1", "field": "point"}},
    {"text": "341", "source": {"evidence": "ev-1", "field": "finding.n_items"}},
    {"text": "0.5", "source": {"spec": "hypotheses[0].decision_rule.params.value"}},
    {"text": "0.42", "source": {"evidence": "ev-1", "field": "finding.baseline"}},
)


def _audit_lines(report) -> list[str]:
    return [p for p in report.paper_requirements_problems if p.startswith("number audit:")]


# --------------------------------------------------------------------------- #
# opt-in: a run without the list is unchanged
# --------------------------------------------------------------------------- #

def test_without_a_list_the_pattern_audit_runs_unchanged(tmp_path):
    run_dir = _run(tmp_path, r"\section{Results}The value is 0.61; 0.123456 is unrecorded.")
    report = verify_run(run_dir)
    spec = _spec()
    evidence = [EvidenceItem.model_validate_json(
        (run_dir / "evidence" / "ev-1.json").read_text(encoding="utf-8"))]
    claims = [Claim.model_validate_json(
        (run_dir / "claims" / "claim-hyp-a.json").read_text(encoding="utf-8"))]
    expected = number_audit_problems(
        (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8"),
        pool_from_record(claims, evidence, spec), source="draft.tex")
    assert expected  # the fixture does exercise the audit
    assert _audit_lines(report) == expected
    assert report.numbers_clean is True and report.number_problems == []
    assert report.passed is False


def test_without_a_list_one_advisory_recommends_it(tmp_path):
    report = verify_run(_run(tmp_path))
    lines = [n for n in report.paper_advisory if "numbers.json" in n]
    assert len(lines) == 1
    assert "numbers draft" in lines[0]


def test_a_run_without_a_paper_gets_no_recommendation(tmp_path):
    report = verify_run(_run(tmp_path, draft=None, pubreqs=False))
    assert not any("numbers.json" in n for n in report.paper_advisory)
    assert report.passed is True


# --------------------------------------------------------------------------- #
# with the list: the declared checks replace the audit
# --------------------------------------------------------------------------- #

def test_a_complete_list_replaces_the_audit_and_passes(tmp_path):
    run_dir = _run(tmp_path)
    _numbers(run_dir, *FULL)
    report = verify_run(run_dir)
    assert _audit_lines(report) == []
    assert report.numbers_clean is True, report.number_problems
    assert not any("numbers.json" in n and "numbers draft" in n for n in report.paper_advisory)
    assert report.passed is True, (report.paper_requirements_problems, report.number_problems)


def test_an_undeclared_literal_fails_verify(tmp_path):
    run_dir = _run(tmp_path)
    _numbers(run_dir, *FULL[:3])
    report = verify_run(run_dir)
    assert report.numbers_clean is False
    assert report.passed is False
    assert any("0.42" in p for p in report.number_problems)
    assert _audit_lines(report) == []


def test_a_wrong_source_fails_verify(tmp_path):
    run_dir = _run(tmp_path)
    _numbers(run_dir, *FULL[:3],
             {"text": "0.42", "source": {"evidence": "ev-1", "field": "point"}})
    report = verify_run(run_dir)
    assert report.numbers_clean is False
    assert any("numbers[3]" in p for p in report.number_problems)


def test_a_malformed_list_fails_loudly_and_still_replaces_the_audit(tmp_path):
    run_dir = _run(tmp_path)
    (run_dir / "numbers.json").write_text("{ not json", encoding="utf-8")
    report = verify_run(run_dir)
    assert report.numbers_clean is False
    assert any("numbers.json" in p for p in report.number_problems)
    assert _audit_lines(report) == []


def test_identifiers_and_stale_entries_reach_the_advisory_channel(tmp_path):
    run_dir = _run(tmp_path, _DRAFT + " Registry number 17109-49-8.")
    _numbers(run_dir, *FULL, {"text": "17109-49-8", "role": "identifier"},
             {"text": "7.77", "role": "identifier"})
    report = verify_run(run_dir)
    assert report.passed is True, report.number_problems
    assert any("17109-49-8" in n for n in report.paper_advisory)
    assert any("7.77" in n for n in report.paper_advisory)


def test_the_list_is_checked_even_before_the_paper_is_rendered(tmp_path):
    run_dir = _run(tmp_path, draft=None, pubreqs=False)
    _numbers(run_dir, {"text": "0.62", "source": {"evidence": "ev-1", "field": "point"}})
    report = verify_run(run_dir)
    assert report.numbers_clean is False      # 0.62 is not the recorded 0.61
    assert any("draft.tex" in n for n in report.paper_advisory)  # stale: no document yet


def test_verify_is_read_only_for_the_number_list(tmp_path):
    run_dir = _run(tmp_path)
    _numbers(run_dir, *FULL)
    before = {p: p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()}
    verify_run(run_dir)
    after = {p: p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()}
    assert before == after


def test_the_cli_prints_number_failures(tmp_path):
    run_dir = _run(tmp_path)
    _numbers(run_dir, *FULL[:3])
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(["verify", str(run_dir)])
    assert rc == 1
    assert "numbers FAILED" in err.getvalue()
    assert "0.42" in err.getvalue()


# --------------------------------------------------------------------------- #
# the blind reviewer's identifier notes (decision 4)
# --------------------------------------------------------------------------- #

def test_an_old_review_without_notes_loads_unchanged():
    review = ConclusionReview.model_validate(
        {"spec_id": "s", "reviewer": "r", "readings": []})
    assert review.notes == []


def test_a_reviewer_note_on_an_identifier_is_advisory_only(tmp_path):
    run_dir = _run(tmp_path, _DRAFT + " Criterion-5 records were kept.")
    _numbers(run_dir, *FULL, {"text": "5", "role": "identifier", "context": "Criterion-5"})
    before = verify_run(run_dir)
    (run_dir / "review.json").write_text(json.dumps({
        "spec_id": "spec-n", "reviewer": "evaluator-conclusions", "readings": [],
        "notes": [{"text": "5", "document": "draft.tex",
                   "note": "reads as a count of criteria"}],
    }), encoding="utf-8")
    after = verify_run(run_dir)
    lines = [n for n in after.paper_advisory if "reads as a count of criteria" in n]
    assert len(lines) == 1 and "'5'" in lines[0]
    assert after.passed == before.passed
    assert after.numbers_clean == before.numbers_clean
