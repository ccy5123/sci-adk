"""
Search log on literature decisions (design/parallel-literature-search.md §4.2 / §4.4).

A ``found_nothing`` from one phrasing on one index used to be recorded identically to a
thorough search. The search log records HOW the search was done (which indexes, which
query strings, when, which failed) on the decision item's ``Provenance``, and ``verify``
checks it:

  - found_nothing + a log showing fewer than two distinct indexes that answered -> HARD fail
  - found_nothing + no log at all -> a non-blocking advisory line (old runs keep passing)
  - found_something -> the rule does not apply.

No network: acquisition goes through a fake paperforge adapter.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
    Provenance,
    Result,
)
from sci_adk.core.search_log import (
    SearchLogFile,
    SearchLogRecord,
    load_search_logs,
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
from sci_adk.loop.inquiry import record_inquiry_searched
from sci_adk.loop.literature_triggers import record_contested, record_novelty_searched
from sci_adk.loop.prior_work import record_prior_work_searched
from sci_adk.loop.verify import verify_run
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult


def _log_dict(**overrides) -> dict:
    base = {
        "hypothesis_id": "hyp-1",
        "kind": "result",
        "searched_at": "2026-10-08T05:12:44Z",
        "queries": [
            {"index": "openalex", "query": "first to show Z", "status": "ok",
             "n_results": 138},
            {"index": "arxiv", "query": "Z shown for the first time", "status": "ok",
             "n_results": 12},
            {"index": "semantic_scholar", "query": "first to show Z",
             "status": "failed", "detail": "HTTP 429"},
        ],
        "candidates": [
            {"doi": "10.1/x", "title": "A related paper", "relevance": "related",
             "basis": "shows Y, not Z"},
        ],
        "proposed_outcome": "found-nothing",
    }
    base.update(overrides)
    return base


def _write_log(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #

def test_search_log_file_accepts_a_well_formed_log():
    log = SearchLogFile.model_validate(_log_dict())
    assert log.hypothesis_id == "hyp-1"
    assert log.kind == "result"
    assert [q.index for q in log.queries] == ["openalex", "arxiv", "semantic_scholar"]
    assert log.queries[2].status == "failed"
    assert log.candidates[0].relevance == "related"


def test_search_log_file_hypothesis_and_kind_are_optional_for_prior_work():
    data = _log_dict()
    del data["hypothesis_id"]
    del data["kind"]
    del data["proposed_outcome"]
    log = SearchLogFile.model_validate(data)
    assert log.hypothesis_id is None and log.kind is None


def test_search_log_file_requires_searched_at():
    data = _log_dict()
    del data["searched_at"]
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(data)


def test_search_log_file_rejects_non_utc_or_malformed_searched_at():
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(_log_dict(searched_at="yesterday"))
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(_log_dict(searched_at="2026-10-08T05:12:44"))
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(_log_dict(searched_at="2026-10-08T05:12:44+09:00"))


def test_search_log_file_rejects_empty_queries():
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(_log_dict(queries=[]))


def test_search_log_file_rejects_bad_status():
    bad = _log_dict()
    bad["queries"][0]["status"] = "timeout"
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(bad)


def test_search_log_file_rejects_blank_query_and_negative_count():
    bad = _log_dict()
    bad["queries"][0]["query"] = "   "
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(bad)
    bad = _log_dict()
    bad["queries"][0]["n_results"] = -1
    with pytest.raises(ValidationError):
        SearchLogFile.model_validate(bad)


def test_search_log_file_is_frozen():
    log = SearchLogFile.model_validate(_log_dict())
    with pytest.raises(ValidationError):
        log.searched_at = "2026-01-01T00:00:00Z"


def test_load_search_logs_merges_queries_across_files(tmp_path):
    a = _write_log(tmp_path / "a.json", _log_dict())
    b = _write_log(tmp_path / "b.json", _log_dict(
        searched_at="2026-10-08T06:00:00Z",
        queries=[{"index": "crossref", "query": "Z first", "status": "ok"}],
        candidates=[],
    ))
    files, record = load_search_logs([a, b])
    assert len(files) == 2
    assert isinstance(record, SearchLogRecord)
    assert record.searched_at == ["2026-10-08T05:12:44Z", "2026-10-08T06:00:00Z"]
    assert [q.index for q in record.queries] == [
        "openalex", "arxiv", "semantic_scholar", "crossref"]
    assert [c.doi for c in record.candidates] == ["10.1/x"]
    assert record.ok_indexes() == {"openalex", "arxiv", "crossref"}


def test_load_search_logs_names_the_bad_file(tmp_path):
    good = _write_log(tmp_path / "good.json", _log_dict())
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.json"):
        load_search_logs([good, bad])
    invalid = _write_log(tmp_path / "invalid.json", _log_dict(queries=[]))
    with pytest.raises(ValueError, match="invalid.json"):
        load_search_logs([invalid])
    with pytest.raises(ValueError, match="missing.json"):
        load_search_logs([tmp_path / "missing.json"])


# --------------------------------------------------------------------------- #
# Provenance carries the log; old evidence still loads
# --------------------------------------------------------------------------- #

def test_old_evidence_json_without_search_log_still_loads():
    old = {
        "id": "evi-nov-old", "spec_id": "s", "kind": "novelty_decision",
        "provenance": {"code_ref": "novelty:result:found_nothing"},
        "result": {"type": "qualitative", "finding": "result found_nothing"},
        "bears_on": [],
        "literature_decision": {"outcome": "found_nothing", "hypothesis_id": "h",
                                "kind": "result"},
    }
    item = EvidenceItem.model_validate(old)
    assert item.provenance.search_log is None


def test_provenance_round_trips_a_search_log(tmp_path):
    _, record = load_search_logs([_write_log(tmp_path / "a.json", _log_dict())])
    prov = Provenance(code_ref="x", search_log=record)
    again = Provenance.model_validate(json.loads(json.dumps(prov.model_dump(mode="json"))))
    assert again.search_log == record


# --------------------------------------------------------------------------- #
# recorders thread the log onto the decision item
# --------------------------------------------------------------------------- #

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


def _spec(spec_id: str, hyp_id: str = "hyp-1") -> Spec:
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
                novelty_result=True,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _decisions(run_dir: Path, kind: EvidenceKind) -> list[EvidenceItem]:
    out = []
    for p in sorted((run_dir / "evidence").glob("*.json")):
        item = EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        if item.kind is kind:
            out.append(item)
    return out


def test_record_novelty_searched_stores_search_log_on_provenance(tmp_path):
    spec = _spec("sl-nov")
    _, record = load_search_logs([_write_log(tmp_path / "a.json", _log_dict())])
    record_novelty_searched(
        spec, tmp_path, hypothesis_id="hyp-1", kind="result", dois=["10.1/x"],
        found="nothing", adapter=_FakeAdapter(), email="x@y.z", search_log=record,
    )
    (decision,) = _decisions(tmp_path / "runs" / spec.id, EvidenceKind.NOVELTY_DECISION)
    assert decision.provenance.search_log is not None
    assert [q.index for q in decision.provenance.search_log.queries] == [
        "openalex", "arxiv", "semantic_scholar"]
    assert decision.provenance.search_log.searched_at == ["2026-10-08T05:12:44Z"]


def test_record_novelty_searched_without_log_leaves_field_none(tmp_path):
    spec = _spec("sl-nov-none")
    record_novelty_searched(
        spec, tmp_path, hypothesis_id="hyp-1", kind="result", dois=["10.1/x"],
        found="nothing", adapter=_FakeAdapter(), email="x@y.z",
    )
    (decision,) = _decisions(tmp_path / "runs" / spec.id, EvidenceKind.NOVELTY_DECISION)
    assert decision.provenance.search_log is None


def test_other_searched_recorders_store_search_log(tmp_path):
    _, record = load_search_logs([_write_log(tmp_path / "a.json", _log_dict())])

    spec = _spec("sl-pw")
    record_prior_work_searched(spec, tmp_path, dois=["10.1/x"], adapter=_FakeAdapter(),
                               email="x@y.z", search_log=record)
    (pw,) = _decisions(tmp_path / "runs" / spec.id, EvidenceKind.PRIOR_WORK_DECISION)
    assert pw.provenance.search_log == record

    spec = _spec("sl-inq")
    record_inquiry_searched(spec, tmp_path, question="has anyone measured Z?",
                            dois=["10.1/x"], adapter=_FakeAdapter(), email="x@y.z",
                            search_log=record)
    (inq,) = _decisions(tmp_path / "runs" / spec.id, EvidenceKind.INQUIRY_DECISION)
    assert inq.provenance.search_log == record

    spec = _spec("sl-con")
    item = record_contested(spec, tmp_path, hypothesis_id="hyp-1", dois=["10.1/x"],
                            adapter=_FakeAdapter(), email="x@y.z", search_log=record)
    assert item.provenance.search_log == record


# --------------------------------------------------------------------------- #
# verify: the two-index rule for found_nothing
# --------------------------------------------------------------------------- #

_NON_CIRC = "the verifier checks a property not baked into the generator"


def _verify_spec(spec_id: str, hyp_id: str = "hyp-n") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
                novelty_result=True,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _record(statuses: list[tuple[str, str]]) -> SearchLogRecord:
    return SearchLogRecord(
        searched_at=["2026-10-08T05:12:44Z"],
        queries=[{"index": idx, "query": "first to show Z", "status": st}
                 for idx, st in statuses],
    )


def _seed_run(tmp_path: Path, spec_id: str, outcome: str,
              search_log: SearchLogRecord | None) -> Path:
    spec = _verify_spec(spec_id)

    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-decision", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref=f"novelty:result:{outcome}",
                                      search_log=search_log),
                result=Result(type="qualitative", finding=f"result {outcome}"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome=outcome, hypothesis_id="hyp-n", kind="result",
                    literature_evidence_id="evi-lit-x"),
            ),
        ]

    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=tmp_path)
    # Drop the rendered paper so the publishing gates are vacuous: ``passed`` then turns
    # on the claim audit and the search-log rule alone (otherwise the failing-log test
    # would pass for an unrelated reason).
    shutil.rmtree(run_dir / "paper", ignore_errors=True)
    return run_dir


def test_seeded_run_with_a_sound_log_passes_verify(tmp_path):
    """Control: with a sound log the seeded run passes, so a failure below is the rule's."""
    run_dir = _seed_run(tmp_path, "sl-v-control", "found_nothing",
                        _record([("openalex", "ok"), ("crossref", "ok")]))
    assert verify_run(run_dir).passed is True


def test_verify_found_nothing_with_two_ok_indexes_passes(tmp_path):
    run_dir = _seed_run(tmp_path, "sl-v-two", "found_nothing",
                        _record([("openalex", "ok"), ("arxiv", "ok")]))
    report = verify_run(run_dir)
    assert report.search_log_problems == []
    assert report.search_log_clean is True
    assert report.passed is True
    assert not any("search log" in line for line in report.paper_advisory)


def test_verify_found_nothing_with_one_ok_index_fails(tmp_path):
    run_dir = _seed_run(tmp_path, "sl-v-one", "found_nothing",
                        _record([("openalex", "ok"), ("semantic_scholar", "failed"),
                                 ("OpenAlex", "ok")]))
    report = verify_run(run_dir)
    assert report.all_reproduced is True  # the claim audit is unaffected
    assert report.search_log_clean is False
    assert report.passed is False
    (problem,) = report.search_log_problems
    assert "hyp-n" in problem and "result" in problem
    assert "openalex" in problem


def test_verify_found_nothing_without_log_passes_with_advisory(tmp_path):
    run_dir = _seed_run(tmp_path, "sl-v-none", "found_nothing", None)
    report = verify_run(run_dir)
    assert report.search_log_clean is True
    assert report.passed is True
    lines = [line for line in report.paper_advisory if "search log" in line]
    assert len(lines) == 1
    assert "hyp-n" in lines[0] and "result" in lines[0]


def test_verify_found_something_with_one_index_log_passes(tmp_path):
    run_dir = _seed_run(tmp_path, "sl-v-fs", "found_something",
                        _record([("openalex", "ok")]))
    report = verify_run(run_dir)
    assert report.search_log_clean is True
    assert report.search_log_problems == []
    assert not any("search log" in line for line in report.paper_advisory)


def _seed_two_decisions(tmp_path: Path, spec_id: str,
                        logs: list[SearchLogRecord | None]) -> Path:
    """Seed one run with several found_nothing decisions for the SAME {hyp-n, result}."""
    spec = _verify_spec(spec_id)

    def experiment(s, w):
        items = [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
            )
        ]
        for i, log in enumerate(logs):
            items.append(EvidenceItem(
                id=f"evi-nov-decision-{i}", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:result:found_nothing",
                                      search_log=log),
                result=Result(type="qualitative", finding="result found_nothing"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id="hyp-n", kind="result",
                    literature_evidence_id=f"evi-lit-{i}"),
            ))
        return items

    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=tmp_path)
    shutil.rmtree(run_dir / "paper", ignore_errors=True)
    return run_dir


def test_verify_weak_null_is_cured_by_a_later_sound_null_for_the_same_kind(tmp_path):
    """The record is append-only, so a weak found_nothing can never be removed. The
    novelty claim derives SUPPORTED from ANY found_nothing of its {hyp, kind}, so the
    gate asks the same question: does at least one of them rest on a sound search?
    Re-searching properly must therefore clear the failure."""
    run_dir = _seed_two_decisions(tmp_path, "sl-v-cured", [
        _record([("openalex", "ok")]),
        _record([("openalex", "ok"), ("arxiv", "ok")]),
    ])
    report = verify_run(run_dir)
    assert report.search_log_problems == []
    assert report.passed is True


def test_verify_weak_null_with_only_unlogged_company_still_fails(tmp_path):
    """No sound search for the kind: the weak logged null fails even beside an
    unlogged one -- an unlogged null is not evidence of a sound search."""
    run_dir = _seed_two_decisions(tmp_path, "sl-v-weak-unlogged", [
        _record([("openalex", "ok")]),
        None,
    ])
    report = verify_run(run_dir)
    assert report.passed is False
    assert len(report.search_log_problems) == 1


def test_verify_unlogged_null_beside_a_sound_one_raises_no_advisory(tmp_path):
    """A sound search on record for the kind: the older unlogged null adds nothing to
    report."""
    run_dir = _seed_two_decisions(tmp_path, "sl-v-sound-unlogged", [
        None,
        _record([("openalex", "ok"), ("crossref", "ok")]),
    ])
    report = verify_run(run_dir)
    assert report.passed is True
    assert not any("search log" in line for line in report.paper_advisory)


def _late_record(statuses: list[tuple[str, str]]) -> SearchLogRecord:
    """A log whose search ran long after any Spec in these tests was frozen."""
    return SearchLogRecord(
        searched_at=["2099-01-01T00:00:00Z"],
        queries=[{"index": idx, "query": "first to show Z", "status": st}
                 for idx, st in statuses],
    )


def test_verify_found_nothing_searched_after_the_freeze_fails(tmp_path):
    """The search must precede the freeze, or the null could be fitted to the plan.
    Recording happens after the freeze (the verbs need spec.json); searched_at is the
    evidence that the SEARCH did not."""
    run_dir = _seed_run(tmp_path, "sl-v-late", "found_nothing",
                        _late_record([("openalex", "ok"), ("arxiv", "ok")]))
    report = verify_run(run_dir)
    assert report.passed is False
    (problem,) = report.search_log_problems
    assert "after the Spec was frozen" in problem
    assert "hyp-n" in problem


def test_verify_late_null_is_cured_by_a_timely_sound_one(tmp_path):
    run_dir = _seed_two_decisions(tmp_path, "sl-v-late-cured", [
        _late_record([("openalex", "ok"), ("arxiv", "ok")]),
        _record([("openalex", "ok"), ("crossref", "ok")]),
    ])
    assert verify_run(run_dir).passed is True


def test_verify_flagged_novelty_without_a_found_nothing_record_is_advisory(tmp_path):
    """novelty_result is set at the freeze from the search logs, then recorded. A flag
    with no matching found_nothing on record is surfaced, never gated: between the
    freeze and the recording the gap is legitimate, and a PROPOSED novelty claim is an
    allowed state."""
    run_dir = _seed_two_decisions(tmp_path, "sl-v-flag-unrecorded", [])
    report = verify_run(run_dir)
    assert report.passed is True
    lines = [line for line in report.paper_advisory if line.startswith("novelty flag:")]
    assert len(lines) == 1
    assert "hyp-n" in lines[0] and "novelty_result" in lines[0]


def test_verify_flagged_novelty_with_its_record_raises_no_flag_advisory(tmp_path):
    run_dir = _seed_two_decisions(tmp_path, "sl-v-flag-recorded", [
        _record([("openalex", "ok"), ("crossref", "ok")]),
    ])
    report = verify_run(run_dir)
    assert not any(line.startswith("novelty flag:") for line in report.paper_advisory)


def test_cli_verify_surfaces_search_log_failure_and_advisory(tmp_path, capsys):
    from sci_adk.cli import main

    bad = _seed_run(tmp_path, "sl-cli-bad", "found_nothing", _record([("openalex", "ok")]))
    assert main(["verify", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "search log FAILED" in err and "hyp-n" in err

    bare = _seed_run(tmp_path, "sl-cli-bare", "found_nothing", None)
    assert main(["verify", str(bare)]) == 0
    out = capsys.readouterr().out
    assert "advisory: search log:" in out
