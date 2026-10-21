"""
The novelty scope points to the record when queries failed; the record lists every query.

On the trial run (SPEC-BCFKOW-001) the two ``found_nothing`` decisions behind the paper's
result-novelty sentence carried the same search log: 115 queries, 31 of which failed (rate
limits on three indexes and one web search), the failed ones including those closest to the
claim. The rendered sentence read "(no such report was found in searches of OpenAlex, arXiv,
Crossref and the web on 2026-10-08)": the failures were invisible to the reader, and the
record held no query at all.

A first fix put the counts into the paper's sentence ("31 of 115 queries returned an error
or no response"). How many queries a tool sent and how many failed is record content, not
paper content (design/reader-facing-prose.md §16): the counts now live in the record and in
``verify``'s advisory, and the paper's sentence points to the record.

The contract tested here:

  - when the backing search logs hold failed queries, the scope ends with a pointer to the
    analysis record, which lists the queries and their outcomes; it states no count; with no
    failed query the scope is byte-identical to what render wrote before (no pointer);
  - index spellings that differ only in case, spaces, ``_`` or ``-`` are one index;
  - the scope holds no number but its date, so nothing in it is exempt from the number
    checks;
  - the record (``record.tex``) lists every recorded search: per decision with a log, its
    time(s) and each query with its index and status; identical logs once;
  - ``verify`` names each found_nothing decision behind a SUPPORTED novelty claim whose log
    has failed queries, with the counts, in an advisory line (never a failure); the counts
    are taken over DISTINCT logs (two decisions carrying the same log count once).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
    Provenance,
    Result,
)
from sci_adk.core.search_log import SearchLogRecord, SearchQuery
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.render import novelty
from sci_adk.render.figures import ImageFigureSpec
from sci_adk.render.novelty import failed_query_counts, novelty_scope_suffix
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import PaperProse
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import needs_tex
from tests.test_latex_sanitize_hardening import _build
from tests.test_latex_sanitize_round3 import _png
from tests.test_novelty_plain_sentence import (
    _INTRO,
    _TRIAL_TEXT,
    _found_nothing,
    _q,
    _spec,
    _trial_log,
)
from tests.test_novelty_render import _freeze_minimal_pubreqs

BS = chr(92)
_LISTED = (
    "the queries and their outcomes are listed in the analysis record distributed with "
    "the paper"
)
_NAMES = "OpenAlex, arXiv, Crossref and the web on 2026-10-08"


def _trial_shaped_log() -> SearchLogRecord:
    """The index/status mix of the trial's 115-query log: 31 failed."""
    plan = [
        ("openalex", 8, 9), ("arxiv", 24, 0), ("crossref", 32, 15), ("websearch", 20, 1),
        ("semantic_scholar", 0, 3), ("semanticscholar", 0, 3),
    ]
    queries = []
    for index, ok, failed in plan:
        queries += [_q(index, "ok", f"{index} query {i}") for i in range(ok)]
        queries += [_q(index, "failed", f"{index} failed query {i}") for i in range(failed)]
    return SearchLogRecord(
        searched_at=["2026-10-08T09:41:13Z", "2026-10-08T09:41:25Z"], queries=queries
    )


def _second(log: SearchLogRecord) -> EvidenceItem:
    return _found_nothing(
        ev_id="evi-nov-decision-20261008-100521-ce184c7a",
        created_at=datetime(2026, 10, 8, 10, 5, 21, tzinfo=timezone.utc),
        log=log,
    )


# =========================================================================== #
# the scope states the failed queries                                          #
# =========================================================================== #

class TestScopePointsToTheRecord:
    def test_failed_queries_add_a_pointer_to_the_record(self):
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=_trial_log())])
        assert suffix == f" (no such report was found in searches of {_NAMES}; {_LISTED})"

    def test_the_trial_scope_states_no_count(self):
        log = _trial_shaped_log()
        suffix = novelty_scope_suffix(
            "result", "H2", _spec(), [_found_nothing(log=log), _second(log)]
        )
        assert suffix == f" (no such report was found in searches of {_NAMES}; {_LISTED})"
        assert "31" not in suffix and "115" not in suffix
        assert novelty.FAILED_QUERY_TERM not in suffix

    def test_the_scope_holds_no_number_but_its_date(self):
        suffix = novelty_scope_suffix(
            "result", "H2", _spec(), [_found_nothing(log=_trial_shaped_log())]
        )
        assert re.findall(r"\d+", suffix.replace("2026-10-08", "")) == []

    def test_two_decisions_with_the_same_log_count_it_once(self):
        log = _trial_log()
        counts = failed_query_counts([_found_nothing(log=log), _second(log)])
        assert (counts.failed, counts.total) == (4, 8)

    def test_two_decisions_with_different_logs_add_up(self):
        other = SearchLogRecord(
            searched_at=["2026-10-08T11:00:00Z"],
            queries=[_q("pubmed", "ok"), _q("pubmed", "failed", "another query")],
        )
        counts = failed_query_counts([_found_nothing(log=_trial_log()), _second(other)])
        assert (counts.failed, counts.total) == (5, 10)

    def test_a_decision_without_a_log_adds_nothing(self):
        counts = failed_query_counts([_found_nothing(log=None), _second(_trial_log())])
        assert (counts.failed, counts.total) == (4, 8)

    def test_failed_counts_per_index_merge_spellings(self):
        counts = failed_query_counts([_found_nothing(log=_trial_shaped_log())])
        assert counts.failed_by_index == {
            "Crossref": 15, "OpenAlex": 9, "Semantic Scholar": 6, "the web": 1,
        }

    def test_no_failed_query_leaves_the_scope_as_before(self):
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"],
            queries=[_q("openalex", "ok"), _q("arxiv", "ok"), _q("websearch", "ok")],
        )
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)])
        assert suffix == " (no such report was found in searches of OpenAlex, arXiv and the web on 2026-10-08)"

    def test_index_spellings_are_one_index_in_the_names(self):
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"],
            queries=[
                _q("semantic_scholar", "ok"), _q("SemanticScholar", "ok", "q2"),
                _q("Inspire_HEP", "ok", "q3"), _q("inspire-hep", "ok", "q4"),
                _q("inspirehep", "ok", "q5"),
            ],
        )
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)])
        assert suffix == (
            " (no such report was found in searches of Semantic Scholar and Inspire_HEP "
            "on 2026-10-08)"
        )

    def test_all_queries_failed_falls_back_to_the_date_with_the_pointer(self):
        log = SearchLogRecord(
            searched_at=["2026-10-07T09:00:00Z"],
            queries=[_q("openalex", "failed"), _q("semantic_scholar", "failed", "q2")],
        )
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)])
        assert suffix == f" (as of 2026-10-08; {_LISTED})"

    def test_one_failed_query_gets_the_same_pointer(self):
        log = SearchLogRecord(
            searched_at=["2026-10-07T09:00:00Z"], queries=[_q("openalex", "failed")],
        )
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)])
        assert suffix == f" (as of 2026-10-08; {_LISTED})"

    def test_the_sentence_in_the_draft_carries_the_pointer(self):
        tex = render_paper_latex(
            _spec(), [], evidence=[_found_nothing(log=_trial_log())],
            prose=PaperProse(introduction=_INTRO),
        )
        flat = " ".join(tex.split())
        assert _TRIAL_TEXT + f" (no such report was found in searches of {_NAMES}; {_LISTED})" in flat
        assert novelty.FAILED_QUERY_TERM not in flat


# =========================================================================== #
# the scope holds no count, so nothing in it is exempt from the number checks  #
# =========================================================================== #

def test_no_scope_count_exemption_is_left():
    # The counts were blanked before the number checks read a paper; with no count in the
    # scope there is nothing to blank, and the exemption is gone with it.
    assert not hasattr(novelty, "mask_novelty_scope_counts")


def _decision(spec_id: str, ev_id: str, log: SearchLogRecord) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id, spec_id=spec_id, kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref="novelty:result:found_nothing", search_log=log),
        result=Result(type="qualitative", finding="result found_nothing"),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="found_nothing", hypothesis_id="H2", kind="result"),
    )


def _experiment(log: SearchLogRecord, second: SearchLogRecord | None = None):
    def experiment(s, w):
        extra = ([_decision(s.id, "evi-nov-decision-20261008-100521-ce184c7a", second)]
                 if second is not None else [])
        return extra + [
            EvidenceItem(
                id="ev-h2-rho", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.618),
                bears_on=[Bearing(target_id="H2", direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-decision-20261008-100441-315c71ca", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:result:found_nothing",
                                      search_log=log),
                result=Result(type="qualitative", finding="result found_nothing"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id="H2", kind="result"),
            ),
        ]
    return experiment


def _seeded_run(
    tmp_path: Path, log: SearchLogRecord, second: SearchLogRecord | None = None
) -> Path:
    spec = _spec()
    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(
        run_dir=run_dir, spec=spec, experiment=_experiment(log, second),
        workspace_dir=tmp_path,
    )
    ResearchCompiler(workspace_dir=tmp_path).stage_render(
        spec, prose=PaperProse(introduction=_INTRO)
    )
    return run_dir


def _failed_three_of_seven() -> SearchLogRecord:
    return SearchLogRecord(
        searched_at=["2026-10-08T09:41:13Z"],
        queries=[
            _q("openalex", "ok", "a"), _q("arxiv", "ok", "b"), _q("crossref", "ok", "c"),
            _q("websearch", "ok", "d"), _q("crossref", "failed", "e"),
            _q("semantic_scholar", "failed", "f"), _q("semanticscholar", "failed", "g"),
        ],
    )


class TestVerifyReadsTheScope:
    def test_number_list_needs_only_the_date(self, tmp_path):
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven())
        draft = " ".join((run_dir / "paper" / "draft.tex").read_text(encoding="utf-8").split())
        assert f"on 2026-10-08; {_LISTED})" in draft
        assert "3 of 7" not in draft
        (run_dir / "numbers.json").write_text(json.dumps({
            "spec_id": run_dir.name,
            "numbers": [{"text": "2026-10-08", "role": "identifier"}],
        }), encoding="utf-8")
        report = verify_run(run_dir)
        assert report.number_problems == [], report.number_problems

    def test_pattern_audit_does_not_flag_the_counts(self, tmp_path):
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven())
        _freeze_minimal_pubreqs(run_dir)
        report = verify_run(run_dir)
        flagged = [p for p in report.paper_requirements_problems
                   if p.startswith("number audit:") and (" states 3," in p or " states 7," in p)]
        assert flagged == []

    def test_the_bound_sentence_verifies_clean(self, tmp_path):
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven())
        assert verify_run(run_dir).paper_novelty_problems == {}

    def test_a_scope_rendered_with_the_old_counts_fails_until_rendered_again(self, tmp_path):
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven())
        old = ("3 of 7 queries returned an error or no response; all queries are listed in "
               "the analysis record distributed with the paper")
        pointer = r"\s+".join(re.escape(w) for w in _LISTED.split())
        for path in (run_dir / "paper" / "draft.tex", run_dir / "novelty_sentences.json"):
            text = path.read_text(encoding="utf-8")
            changed = re.sub(pointer, old, text)
            assert changed != text, path.name
            path.write_text(changed, encoding="utf-8")
        assert verify_run(run_dir).paper_novelty_problems != {}


# =========================================================================== #
# verify names the failed queries behind a supported novelty claim (advisory)  #
# =========================================================================== #

class TestVerifyAdvisory:
    def test_failed_queries_behind_a_supported_claim_are_named(self, tmp_path):
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven())
        report = verify_run(run_dir)
        lines = [a for a in report.paper_advisory if "queries returned an error or no response" in a]
        assert len(lines) == 1, report.paper_advisory
        line = lines[0]
        assert "result-novelty" in line and "'H2'" in line
        assert "evi-nov-decision-20261008-100441-315c71ca" in line
        assert "3 of 7 queries returned an error or no response" in line
        assert "Semantic Scholar 2, Crossref 1" in line
        # The paper's sentence no longer states the count: the line says where it is.
        assert "states the count" not in line
        assert "the paper's novelty scope points to the record, which lists every query" in line
        assert not any("queries returned an error or no response" in p for p in report.search_log_problems)
        assert report.search_log_clean

    def test_two_decisions_sharing_one_log_give_one_line_naming_both(self, tmp_path):
        # The same rule as the sentence: a log two decisions record counts once.
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven(), _failed_three_of_seven())
        lines = [a for a in verify_run(run_dir).paper_advisory
                 if "returned an error or no response" in a]
        assert len(lines) == 1, lines
        assert "evi-nov-decision-20261008-100441-315c71ca" in lines[0]
        assert "evi-nov-decision-20261008-100521-ce184c7a" in lines[0]
        assert "3 of 7 queries returned an error or no response" in lines[0]

    def test_two_decisions_with_different_logs_give_a_line_each(self, tmp_path):
        other = SearchLogRecord(
            searched_at=["2026-10-08T11:00:00Z"],
            queries=[_q("openalex", "ok", "x"), _q("arxiv", "ok", "y"),
                     _q("crossref", "failed", "z")],
        )
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven(), other)
        lines = [a for a in verify_run(run_dir).paper_advisory
                 if "returned an error or no response" in a]
        assert len(lines) == 2, lines
        assert any("1 of 3 queries returned" in a and "ce184c7a" in a for a in lines)

    def test_claims_only_report_carries_it_too(self, tmp_path):
        run_dir = _seeded_run(tmp_path, _failed_three_of_seven())
        report = verify_run(run_dir, claims_only=True)
        assert any("3 of 7 queries returned an error or no response" in a for a in report.paper_advisory)

    def test_no_failed_query_no_advisory(self, tmp_path):
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:41:13Z"],
            queries=[_q("openalex", "ok", "a"), _q("arxiv", "ok", "b")],
        )
        run_dir = _seeded_run(tmp_path, log)
        assert not any("queries returned an error or no response" in a for a in verify_run(run_dir).paper_advisory)


# =========================================================================== #
# the record lists every recorded search                                       #
# =========================================================================== #

_HARD_QUERIES = [
    ("openalex", "ok", 'filter=title_and_abstract.search:"na' + chr(239) + 've estimator" sample'),
    ("crossref", "failed", "query.bibliographic=prime (number) & code: 50% #1 x_y ~z ^w {b} " + BS + "x"),
    ("arxiv", "ok", "abs:" + "a" * 260 + " AND cat:physics.chem-ph"),
    ("websearch", "ok", "site:example.org " + "very-long-hyphenated-token-" * 12),
]


def _hard_log() -> SearchLogRecord:
    return SearchLogRecord(
        searched_at=["2026-10-08T09:41:13Z", "2026-10-08T09:41:25Z"],
        queries=[
            SearchQuery(index=i, query=q, status=s, n_results=(3 if s == "ok" else None))
            for i, s, q in _HARD_QUERIES
        ],
        candidates=[],
    )


def _prior_work(log: SearchLogRecord) -> EvidenceItem:
    return EvidenceItem(
        id="evi-pw-decision-20261008-100739-df0f7348",
        created_at=datetime(2026, 10, 8, 10, 7, 39, tzinfo=timezone.utc),
        spec_id="SPEC-NOV-PLAIN",
        kind=EvidenceKind.PRIOR_WORK_DECISION,
        provenance=Provenance(code_ref="prior_work:searched", search_log=log),
        result=Result(type="qualitative", finding="prior-work search"),
        bears_on=[],
    )


class TestRecordListsTheSearches:
    def _record(self, evidence, **kw) -> str:
        return render_si_latex(_spec(), [], evidence, **kw)

    def test_no_search_log_no_section(self):
        assert "Literature searches" not in self._record([_found_nothing(log=None)])

    def test_each_query_is_listed_with_index_and_status(self):
        tex = self._record([_found_nothing(log=_trial_log())])
        assert BS + "section{Literature searches}" in tex
        section = tex.split(BS + "section{Literature searches}", 1)[1]
        assert section.count(BS + "item ") == 8
        assert "8 queries, 4 returned an error or no response" in section
        assert BS + "mbox{2026-10-08T09:41:13Z}" in section
        assert "semantic" + BS + "_scholar" in section

    def test_identical_logs_are_listed_once_with_both_decisions(self):
        log = _trial_log()
        tex = self._record([_found_nothing(log=log), _second(log)])
        section = tex.split(BS + "section{Literature searches}", 1)[1]
        assert section.count(BS + "item ") == 8
        joined = section.replace(BS + "allowbreak{}", "")  # long ids carry break points
        assert "315c71ca" in joined and "ce184c7a" in joined

    def test_a_prior_work_search_is_listed_too(self):
        tex = self._record([_found_nothing(log=_trial_log()), _prior_work(_hard_log())])
        section = tex.split(BS + "section{Literature searches}", 1)[1]
        assert section.count(BS + "item ") == 8 + len(_HARD_QUERIES)
        assert "Prior-work decision" in section

    def test_result_counts_are_printed_when_recorded(self):
        tex = self._record([_prior_work(_hard_log())])
        assert "3 results" in tex

    def test_specials_are_escaped(self):
        tex = self._record([_prior_work(_hard_log())])
        assert "50" + BS + "%" in tex and BS + "&" in tex and "x" + BS + "_y" in tex
        assert BS + "textbackslash{}x" in tex

    def test_long_queries_get_break_points(self):
        tex = self._record([_prior_work(_hard_log())])
        assert BS + "allowbreak{}" in tex.split("Literature searches", 1)[1]
        assert max(len(line) for line in tex.split("\n")) < 2000


@needs_tex
@pytest.mark.parametrize("with_figure", [False, True], ids=["latin-modern", "times"])
def test_the_record_with_hard_queries_compiles(tmp_path, with_figure):
    figures = []
    if with_figure:
        _png(tmp_path / "figures" / "fig1.png")
        figures = [ImageFigureSpec(kind="image", id="fig-a", caption="A.", image="a.png")]
    tex = render_si_latex(
        _spec(), [], [_found_nothing(log=_trial_log()), _prior_work(_hard_log())],
        figures=figures,
    )
    assert _build(tmp_path, tex, "record") == []
    # The query lines break inside the margin: no overfull line in the section.
    source = (tmp_path / "record.tex").read_text(encoding="utf-8").split("\n")
    start = next(i for i, line in enumerate(source, 1) if "section{Literature searches}" in line)
    end = next(i for i, line in enumerate(source, 1) if "section{Record integrity}" in line)
    log = (tmp_path / "record.log").read_text(encoding="utf-8", errors="replace")
    overfull = [int(m.group(1)) for m in re.finditer(
        r"Overfull \\hbox \([0-9.]+pt too wide\) in paragraph at lines (\d+)--", log)]
    assert [n for n in overfull if start <= n <= end] == []
