"""
The novelty sentence in the submitted source is plain prose (FIX C).

On the BCF/Kow trial (run SPEC-BCFKOW-001) ``render`` wrote
``\\newcommand{\\novelty}[3]{#3}`` into the preamble of ``draft.tex`` and
``\\novelty{result}{H2}{A test of ... has not been reported (to our knowledge, as of
2026-10-08)}`` into its body. Two faults:

  (a) the submitted source carried sci-adk markup and the hypothesis label ``H2`` -- the
      manuscript must carry NO markup a reviewer would not recognize;
  (b) every supported novelty sentence got the stock softener "(to our knowledge, as of
      <date>)", while the record holds the search behind it (the ``found_nothing``
      decision's search log: which indexes answered, when).

The contract tested here:

  - the author still writes ``\\novelty{kind}{hyp}{text}`` in ``prose.json`` / ``si.json``;
    ``render`` writes ONLY the sentence plus a scope taken from the record -- "(no such
    report was found in searches of <indexes that answered> on <date>)", or "(as of
    <date>)" when no search log was recorded -- and no macro, no ``\\newcommand``;
  - the binding {document, kind, hypothesis, sentence} goes to a side file that is never
    submitted, ``runs/<id>/novelty_sentences.json``; ``verify`` re-derives every binding
    (an unbacked one FAILS, as the in-source markup did) and checks the sentence is still
    in its document;
  - drafts rendered before this change, whose ``.tex`` still carries ``\\novelty`` markup,
    are still checked from that markup (backward compatible).

Fixture text is taken from the trial: the H2 sentence of ``prose.json`` and the search
log of its two ``found_nothing`` decisions.
"""

from __future__ import annotations

import json
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
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.render.authored_si import render_authored_si_latex
from sci_adk.render.novelty import (
    NOVELTY_SENTENCES_FILE,
    NoveltySentence,
    find_unbacked_novelty_sentences,
    novelty_scope_suffix,
    parse_novelty_sentences,
)
from sci_adk.render.paper import (
    _latex_sanitize,
    check_paper_tool_vocabulary,
    render_paper_latex,
)
from sci_adk.render.prose import AuthoredSI, PaperProse, SIProse
from sci_adk.render.si import render_si_latex

_NC = "the verifier checks a property not baked into the generator"
_SPEC_ID = "SPEC-NOV-PLAIN"

# The H2 sentence as the trial's prose.json writes it, and the text it must render to.
_TRIAL_MARKUP = (
    r"\novelty{result}{H2}{A test of whether such a code ranks chemicals by measured "
    r"log Kow has not been reported}"
)
_TRIAL_TEXT = (
    "A test of whether such a code ranks chemicals by measured log Kow has not been "
    "reported"
)
_TRIAL_SCOPE = (
    " (no such report was found in searches of OpenAlex, arXiv, Crossref and the web "
    "on 2026-10-08)"
)
_INTRO = (
    "We define an integer code that uses prime factorisation but, unlike Matula numbers, "
    "does not encode the graph one-to-one. " + _TRIAL_MARKUP + ". Adding atoms or bonds "
    "raises the code."
)


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def _spec(*, novelty_method: bool = False) -> Spec:
    return Spec(
        id=_SPEC_ID,
        version=1,
        created_at=datetime(2026, 10, 8, 14, 5, 17, tzinfo=timezone.utc),
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id="H2",
                statement="the code's rank correlation with measured log Kow is at least 0.5",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="formal",
                non_circularity=_NC,
                novelty_result=True,
                novelty_method=novelty_method,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="H2")],
    )


def _q(index: str, status: str, query: str = "prime number molecular code log Kow") -> SearchQuery:
    return SearchQuery(index=index, query=query, status=status)


def _trial_log(searched_at=("2026-10-08T09:41:13Z", "2026-10-08T09:41:25Z")) -> SearchLogRecord:
    """The indexes and statuses of the trial's H2 result-novelty search (one query each)."""
    return SearchLogRecord(
        searched_at=list(searched_at),
        queries=[
            _q("openalex", "ok", 'filter=title_and_abstract.search:"Gödel number" molecule'),
            _q("openalex", "failed",
               'filter=title_and_abstract.search:"prime number" octanol water partition'),
            _q("arxiv", "ok", 'abs:"prime numbers" AND abs:molecular AND abs:descriptor'),
            _q("crossref", "ok", "query.bibliographic=prime number molecular graph code "
                                 "octanol-water partition coefficient"),
            _q("crossref", "failed", "query.bibliographic=Matula numbers prime numbers "
                                     "alkanes rooted trees chemical"),
            _q("semantic_scholar", "failed", "prime number molecular code octanol-water "
                                             "partition coefficient"),
            _q("websearch", "ok", "prime number molecular graph code octanol-water "
                                  "partition coefficient log P correlation"),
            _q("semanticscholar", "failed", "multiplicative topological index "
                                            "octanol-water partition coefficient"),
        ],
    )


def _found_nothing(
    *,
    ev_id: str = "evi-nov-decision-20261008-100441-315c71ca",
    created_at: datetime = datetime(2026, 10, 8, 10, 4, 41, tzinfo=timezone.utc),
    log: SearchLogRecord | None = None,
    kind: str = "result",
    hyp_id: str = "H2",
) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref=f"novelty:{kind}:found_nothing", search_log=log),
        result=Result(type="qualitative", finding=f"{kind} found_nothing"),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="found_nothing", hypothesis_id=hyp_id, kind=kind
        ),
    )


# =========================================================================== #
# (2) the scope comes from the search behind the found_nothing decision        #
# =========================================================================== #

class TestScopeFromSearchLog:
    def test_trial_search_names_the_indexes_that_answered_and_the_date(self):
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=_trial_log())])
        assert suffix == _TRIAL_SCOPE
        assert "to our knowledge" not in suffix

    def test_trial_two_decisions_name_each_index_once(self):
        # The trial recorded two found_nothing decisions for {H2, result} carrying the same
        # log: an index is named once, the date once.
        first = _found_nothing(log=_trial_log())
        second = _found_nothing(
            ev_id="evi-nov-decision-20261008-100521-ce184c7a",
            created_at=datetime(2026, 10, 8, 10, 5, 21, tzinfo=timezone.utc),
            log=_trial_log(),
        )
        assert novelty_scope_suffix("result", "H2", _spec(), [second, first]) == _TRIAL_SCOPE

    def test_failed_only_index_is_not_named(self):
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=_trial_log())])
        assert "Semantic Scholar" not in suffix  # every Semantic Scholar query failed

    def test_searches_on_different_days_give_the_span(self):
        early = _found_nothing(
            created_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
            log=SearchLogRecord(
                searched_at=["2026-10-01T08:00:00Z"],
                queries=[_q("openalex", "ok"), _q("arxiv", "ok")],
            ),
        )
        late = _found_nothing(
            ev_id="evi-nov-late",
            created_at=datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc),
            log=SearchLogRecord(
                searched_at=["2026-10-08T09:00:00Z"],
                queries=[_q("crossref", "ok"), _q("pubmed", "ok")],
            ),
        )
        assert novelty_scope_suffix("result", "H2", _spec(), [late, early]) == (
            " (no such report was found in searches of OpenAlex, arXiv, Crossref and "
            "PubMed between 2026-10-01 and 2026-10-08)"
        )

    def test_unknown_index_name_is_kept_as_recorded(self):
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"],
            queries=[_q("openalex", "ok"), _q("inspirehep", "ok")],
        )
        assert novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)]) == (
            " (no such report was found in searches of OpenAlex and inspirehep on 2026-10-08)"
        )

    def test_no_search_log_falls_back_to_the_decision_date_without_a_softener(self):
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=None)])
        assert suffix == " (as of 2026-10-08)"

    def test_log_where_no_index_answered_falls_back_to_the_decision_date(self):
        log = SearchLogRecord(
            searched_at=["2026-10-07T09:00:00Z"],
            queries=[_q("openalex", "failed"), _q("semantic_scholar", "failed")],
        )
        suffix = novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)])
        assert suffix == " (as of 2026-10-08)"

    def test_search_of_the_other_kind_is_not_used(self):
        spec = _spec(novelty_method=True)
        result = _found_nothing(log=None)
        method = _found_nothing(ev_id="evi-nov-method", kind="method", log=_trial_log())
        assert novelty_scope_suffix("result", "H2", spec, [result, method]) == " (as of 2026-10-08)"

    def test_unbacked_assertion_still_raises(self):
        with pytest.raises(ValueError) as exc:
            novelty_scope_suffix("result", "H2", _spec(), [])
        assert "result-novelty for 'H2'" in str(exc.value)


# =========================================================================== #
# (1) the rendered documents carry the plain sentence, never the macro          #
# =========================================================================== #

class TestPlainSentenceInRenderedSource:
    def test_trial_draft_carries_the_plain_sentence_and_no_markup(self):
        tex = render_paper_latex(
            _spec(), [], evidence=[_found_nothing(log=_trial_log())],
            prose=PaperProse(introduction=_INTRO),
        )
        assert _TRIAL_TEXT + _TRIAL_SCOPE + ". Adding atoms" in tex
        assert r"\novelty" not in tex
        assert r"\newcommand" not in tex
        assert "{H2}" not in tex

    def test_draft_binding_is_collected_exactly_as_rendered(self):
        found: list[NoveltySentence] = []
        tex = render_paper_latex(
            _spec(), [], evidence=[_found_nothing(log=_trial_log())],
            prose=PaperProse(introduction=_INTRO), novelty_sentences=found,
        )
        assert found == [NoveltySentence(
            document="draft.tex", kind="result", hypothesis_id="H2",
            sentence=_TRIAL_TEXT + _TRIAL_SCOPE,
        )]
        assert found[0].sentence in tex

    def test_inner_specials_are_still_escaped(self):
        found: list[NoveltySentence] = []
        tex = render_paper_latex(
            _spec(), [], evidence=[_found_nothing(log=None)],
            prose=PaperProse(introduction=r"\novelty{result}{H2}{a 50% gain}"),
            novelty_sentences=found,
        )
        assert r"a 50\% gain (as of 2026-10-08)" in tex
        assert found[0].sentence == r"a 50\% gain (as of 2026-10-08)"

    def test_unbacked_markup_still_fails_the_render(self):
        with pytest.raises(ValueError) as exc:
            render_paper_latex(_spec(), [], evidence=[], prose=PaperProse(introduction=_INTRO))
        assert "result-novelty for 'H2'" in str(exc.value)

    def test_authored_si_carries_the_plain_sentence_and_its_binding(self):
        found: list[NoveltySentence] = []
        si = AuthoredSI(sections=[{"title": "Descriptor", "body": _INTRO}])
        tex = render_authored_si_latex(
            si, _spec(), [], evidence=[_found_nothing(log=_trial_log())],
            novelty_sentences=found,
        )
        assert _TRIAL_TEXT + _TRIAL_SCOPE in tex
        assert r"\novelty" not in tex and r"\newcommand{\novelty}" not in tex
        assert found == [NoveltySentence(
            document="si.tex", kind="result", hypothesis_id="H2",
            sentence=_TRIAL_TEXT + _TRIAL_SCOPE,
        )]

    def test_authored_si_escapes_a_recorded_index_name(self):
        # The SI body is authored LaTeX (not escaped), but the scope comes from the record:
        # an index recorded as "web_search" must not reach the source as a bare underscore.
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"],
            queries=[_q("openalex", "ok"), _q("my_index", "ok")],
        )
        si = AuthoredSI(sections=[{"title": "S", "body": r"\novelty{result}{H2}{none}"}])
        tex = render_authored_si_latex(si, _spec(), [], evidence=[_found_nothing(log=log)])
        assert r"OpenAlex and my\_index on 2026-10-08" in tex

    def test_record_dump_carries_the_plain_sentence(self):
        tex = render_si_latex(
            _spec(), [], [_found_nothing(log=_trial_log())],
            prose=SIProse(overview=_TRIAL_MARKUP),
        )
        assert _TRIAL_TEXT + _TRIAL_SCOPE in tex
        assert r"\novelty{" not in tex and r"\newcommand{\novelty}" not in tex


# =========================================================================== #
# the binding: written by render, checked by verify                            #
# =========================================================================== #

def _experiment(*, with_novelty: bool = True, log: SearchLogRecord | None = None):
    def experiment(s, w):
        items = [
            EvidenceItem(
                id="ev-h2-rho", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.618),
                bears_on=[Bearing(target_id="H2", direction=BearingDirection.SUPPORTS)],
            ),
        ]
        if with_novelty:
            items.append(EvidenceItem(
                id="evi-nov-decision-20261008-100441-315c71ca", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:result:found_nothing",
                                      search_log=log),
                result=Result(type="qualitative", finding="result found_nothing"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id="H2", kind="result"),
            ))
        return items
    return experiment


def _seeded(tmp_path: Path, **kw) -> tuple[Path, Spec]:
    spec = _spec()
    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(
        run_dir=run_dir, spec=spec, experiment=_experiment(**kw), workspace_dir=tmp_path
    )
    return run_dir, spec


def _render(tmp_path: Path, spec: Spec, prose: PaperProse, si: AuthoredSI | None = None):
    return ResearchCompiler(workspace_dir=tmp_path).stage_render(spec, prose=prose, si=si)


class TestBindingSideFile:
    def test_render_writes_the_binding_beside_the_paper_not_in_it(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        side = json.loads((run_dir / NOVELTY_SENTENCES_FILE).read_text(encoding="utf-8"))
        assert side == {
            "spec_id": _SPEC_ID,
            "sentences": [{
                "document": "draft.tex", "kind": "result", "hypothesis_id": "H2",
                "sentence": _TRIAL_TEXT + _TRIAL_SCOPE,
            }],
        }
        assert not (run_dir / "paper" / NOVELTY_SENTENCES_FILE).exists()
        draft = (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8")
        assert r"\novelty" not in draft

    def test_render_without_novelty_writes_no_side_file(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."))
        assert not (run_dir / NOVELTY_SENTENCES_FILE).exists()

    def test_rerender_without_novelty_empties_a_stale_side_file(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."))
        side = json.loads((run_dir / NOVELTY_SENTENCES_FILE).read_text(encoding="utf-8"))
        assert side["sentences"] == []
        assert verify_run(run_dir).paper_novelty_problems == {}

    def test_si_binding_is_written_too(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        si = AuthoredSI(sections=[{"title": "Descriptor", "body": _INTRO}])
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."), si=si)
        side = json.loads((run_dir / NOVELTY_SENTENCES_FILE).read_text(encoding="utf-8"))
        assert [s["document"] for s in side["sentences"]] == ["si.tex"]


class TestVerifyChecksTheBinding:
    def test_backed_sentence_verifies_clean(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        report = verify_run(run_dir)
        assert report.paper_novelty_problems == {}
        assert report.paper_novelty_clean is True

    def test_binding_to_an_unsearched_kind_fails(self, tmp_path):
        # The tamper the in-source markup guarded against, moved to the side file: a
        # sentence bound to a {hyp, kind} with no found_nothing search on record.
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        path = run_dir / NOVELTY_SENTENCES_FILE
        side = json.loads(path.read_text(encoding="utf-8"))
        side["sentences"][0]["kind"] = "method"
        path.write_text(json.dumps(side), encoding="utf-8")
        report = verify_run(run_dir)
        assert report.paper_novelty_clean is False
        assert any("method-novelty for 'H2'" in p
                   for p in report.paper_novelty_problems["draft.tex"])

    def test_sentence_unbacked_after_its_decision_is_gone_fails(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        for p in (run_dir / "evidence").glob("evi-nov-decision-*.json"):
            p.rename(tmp_path / p.name)  # moved out of the record, kept on disk
        report = verify_run(run_dir)
        assert report.paper_novelty_clean is False
        assert any("result-novelty for 'H2'" in p
                   for p in report.paper_novelty_problems["draft.tex"])

    def test_edited_sentence_no_longer_matches_its_binding(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        draft = run_dir / "paper" / "draft.tex"
        draft.write_text(
            draft.read_text(encoding="utf-8").replace("has not been reported",
                                                      "is reported here for the first time"),
            encoding="utf-8",
        )
        report = verify_run(run_dir)
        assert report.paper_novelty_clean is False
        assert any("no longer in draft.tex" in p
                   for p in report.paper_novelty_problems["draft.tex"])

    def test_rewrapped_sentence_still_matches(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        draft = run_dir / "paper" / "draft.tex"
        draft.write_text(
            draft.read_text(encoding="utf-8").replace("ranks chemicals by", "ranks\nchemicals by"),
            encoding="utf-8",
        )
        assert verify_run(run_dir).paper_novelty_problems == {}

    def test_malformed_side_file_fails(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        (run_dir / NOVELTY_SENTENCES_FILE).write_text("{not json", encoding="utf-8")
        report = verify_run(run_dir)
        assert report.paper_novelty_clean is False
        assert NOVELTY_SENTENCES_FILE in report.paper_novelty_problems

    def test_side_file_for_another_spec_fails(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        path = run_dir / NOVELTY_SENTENCES_FILE
        side = json.loads(path.read_text(encoding="utf-8"))
        side["spec_id"] = "SPEC-OTHER"
        path.write_text(json.dumps(side), encoding="utf-8")
        report = verify_run(run_dir)
        assert NOVELTY_SENTENCES_FILE in report.paper_novelty_problems

    def test_draft_rendered_before_the_change_still_verifies(self, tmp_path):
        # Backward compatibility: an older draft.tex carries the surviving markup and the
        # preamble macro, and no side file. It is still checked from the markup.
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        paper = run_dir / "paper"
        paper.mkdir(parents=True, exist_ok=True)
        old = (
            "\\documentclass{article}\n\\newcommand{\\novelty}[3]{#3}\n\\begin{document}\n"
            "\\novelty{result}{H2}{" + _TRIAL_TEXT
            + " (to our knowledge, as of 2026-10-08)}.\n\\end{document}\n"
        )
        (paper / "draft.tex").write_text(old, encoding="utf-8")
        assert verify_run(run_dir).paper_novelty_problems == {}
        (paper / "draft.tex").write_text(old.replace("{result}", "{method}"), encoding="utf-8")
        assert "draft.tex" in verify_run(run_dir).paper_novelty_problems


class TestCliSurfacesNoveltyProblems:
    def test_verify_cli_names_the_failed_novelty_binding(self, tmp_path):
        # A novelty failure used to make `sci-adk verify` exit 1 with no line saying why.
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from sci_adk.cli import main

        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        draft = run_dir / "paper" / "draft.tex"
        draft.write_text(
            draft.read_text(encoding="utf-8").replace("has not been reported", "is new"),
            encoding="utf-8",
        )
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(["verify", str(run_dir)])
        assert rc == 1
        assert "novelty FAILED" in err.getvalue()
        assert "result-novelty for 'H2'" in err.getvalue()


class TestPureBindingCheck:
    def test_pure_check_reports_missing_document(self):
        entry = NoveltySentence(document="si.tex", kind="result", hypothesis_id="H2",
                                sentence=_TRIAL_TEXT + _TRIAL_SCOPE)
        problems = find_unbacked_novelty_sentences(
            [entry], {"draft.tex": "x"}, _spec(), [_found_nothing(log=_trial_log())],
            escape=_latex_sanitize,
        )
        assert list(problems) == ["si.tex"]
        assert "si.tex" in problems["si.tex"][0]

    def test_pure_check_ignores_a_commented_out_copy(self):
        entry = NoveltySentence(document="draft.tex", kind="result", hypothesis_id="H2",
                                sentence=_TRIAL_TEXT + _TRIAL_SCOPE)
        tex = "% " + _TRIAL_TEXT + _TRIAL_SCOPE + "\n"
        problems = find_unbacked_novelty_sentences(
            [entry], {"draft.tex": tex}, _spec(), [_found_nothing(log=_trial_log())],
            escape=_latex_sanitize,
        )
        assert "draft.tex" in problems


# =========================================================================== #
# a render without the SI keeps the bindings of the si.tex it leaves in place  #
# =========================================================================== #

def _si_with_novelty() -> AuthoredSI:
    return AuthoredSI(sections=[{"title": "Descriptor", "body": _INTRO}])


def _side(run_dir: Path) -> dict:
    return json.loads((run_dir / NOVELTY_SENTENCES_FILE).read_text(encoding="utf-8"))


class TestRenderWithoutSiKeepsTheSiBindings:
    """``render`` without ``--si`` leaves an earlier ``paper/si.tex`` where it is.

    It used to rewrite ``novelty_sentences.json`` from the draft alone, so the novelty
    sentence still printed in that si.tex lost its binding and no gate checked it.
    """

    def test_left_si_tex_keeps_its_binding(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."), si=_si_with_novelty())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))  # no --si this time
        assert (run_dir / "paper" / "si.tex").is_file()
        assert sorted(s["document"] for s in _side(run_dir)["sentences"]) == [
            "draft.tex", "si.tex",
        ]
        assert verify_run(run_dir).paper_novelty_problems == {}

    def test_kept_si_sentence_is_still_checked(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."), si=_si_with_novelty())
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."))
        si_tex = run_dir / "paper" / "si.tex"
        si_tex.write_text(
            si_tex.read_text(encoding="utf-8").replace("has not been reported", "is new"),
            encoding="utf-8",
        )
        problems = verify_run(run_dir).paper_novelty_problems
        assert any("no longer in si.tex" in p for p in problems["si.tex"])

    def test_render_with_si_replaces_the_si_bindings(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."), si=_si_with_novelty())
        plain_si = AuthoredSI(sections=[{"title": "Descriptor", "body": "Plain prose."}])
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."), si=plain_si)
        assert _side(run_dir)["sentences"] == []

    def test_unreadable_bindings_beside_a_left_si_tex_stop_the_render(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction="Plain prose."), si=_si_with_novelty())
        (run_dir / NOVELTY_SENTENCES_FILE).write_text("{not json", encoding="utf-8")
        draft = run_dir / "paper" / "draft.tex"
        before = draft.read_bytes()
        with pytest.raises(ValueError) as exc:
            _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        assert "si.tex" in str(exc.value) and NOVELTY_SENTENCES_FILE in str(exc.value)
        assert draft.read_bytes() == before  # stopped before writing anything

    def test_unreadable_bindings_without_an_si_tex_are_rewritten(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        (run_dir / NOVELTY_SENTENCES_FILE).write_text("{not json", encoding="utf-8")
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        assert [s["document"] for s in _side(run_dir)["sentences"]] == ["draft.tex"]


# =========================================================================== #
# verify re-derives the scope from the record, not just the sentence's presence #
# =========================================================================== #

def _write_evidence(run_dir: Path, item: EvidenceItem) -> None:
    (run_dir / "evidence" / f"{item.id}.json").write_text(
        item.model_dump_json(), encoding="utf-8"
    )


def _remove_novelty_decisions(run_dir: Path, keep_dir: Path) -> None:
    for p in (run_dir / "evidence").glob("evi-nov-decision-*.json"):
        p.rename(keep_dir / p.name)  # moved out of the record, kept on disk


class TestVerifyRederivesTheScope:
    def test_surviving_decision_with_other_indexes_fails(self, tmp_path):
        # The sentence names OpenAlex, arXiv, Crossref and the web; the only found_nothing
        # search now on record queried PubMed and Europe PMC. Still SUPPORTED, still in the
        # draft -- but the printed scope is not the search behind it.
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        _remove_novelty_decisions(run_dir, tmp_path)
        _write_evidence(run_dir, _found_nothing(
            ev_id="evi-nov-decision-other",
            log=SearchLogRecord(
                searched_at=["2026-10-08T09:00:00Z"],
                queries=[_q("pubmed", "ok"), _q("europepmc", "ok")],
            ),
        ))
        report = verify_run(run_dir)
        assert report.paper_novelty_clean is False
        assert any("PubMed and Europe PMC on 2026-10-08" in p
                   for p in report.paper_novelty_problems["draft.tex"])

    def test_later_search_fails_until_the_paper_is_rerendered(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        _write_evidence(run_dir, _found_nothing(
            ev_id="evi-nov-decision-later",
            created_at=datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc),
            log=SearchLogRecord(
                searched_at=["2026-10-08T11:30:00Z"], queries=[_q("pubmed", "ok")],
            ),
        ))
        assert "draft.tex" in verify_run(run_dir).paper_novelty_problems
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        assert verify_run(run_dir).paper_novelty_problems == {}

    def test_index_name_with_a_latex_special_verifies_clean(self, tmp_path):
        # The scope is compared in its escaped form: "my_index" is "my\_index" in the source.
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"],
            queries=[_q("openalex", "ok"), _q("my_index", "ok")],
        )
        run_dir, spec = _seeded(tmp_path, log=log)
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        assert r"my\_index on 2026-10-08)" in _side(run_dir)["sentences"][0]["sentence"]
        assert verify_run(run_dir).paper_novelty_problems == {}

    def test_binding_without_the_scope_fails(self, tmp_path):
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        side = _side(run_dir)
        side["sentences"][0]["sentence"] = _TRIAL_TEXT  # still in the draft, scope dropped
        (run_dir / NOVELTY_SENTENCES_FILE).write_text(json.dumps(side), encoding="utf-8")
        problems = verify_run(run_dir).paper_novelty_problems
        assert any("scope" in p for p in problems["draft.tex"])


class TestPureScopeCheck:
    def _check(self, sentence: str, log: SearchLogRecord | None = None):
        entry = NoveltySentence("draft.tex", "result", "H2", sentence)
        return find_unbacked_novelty_sentences(
            [entry], {"draft.tex": "x " + sentence + " y"}, _spec(),
            [_found_nothing(log=log or _trial_log())], escape=_latex_sanitize,
        )

    def test_matching_scope_is_clean(self):
        assert self._check(_TRIAL_TEXT + _TRIAL_SCOPE) == {}

    def test_other_scope_names_the_scope_on_record(self):
        problems = self._check(
            _TRIAL_TEXT + " (no such report was found in searches of PubMed on 2026-10-08)"
        )
        assert any(
            "OpenAlex, arXiv, Crossref and the web on 2026-10-08" in p
            for p in problems["draft.tex"]
        )

    def test_scope_alone_is_not_a_claim(self):
        problems = self._check(_TRIAL_SCOPE.strip())
        assert any("no claim" in p for p in problems["draft.tex"])

    def test_scope_is_compared_escaped(self):
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"], queries=[_q("my_index", "ok")],
        )
        escaped = _TRIAL_TEXT + r" (no such report was found in searches of my\_index on 2026-10-08)"
        assert self._check(escaped, log) == {}
        raw = _TRIAL_TEXT + " (no such report was found in searches of my_index on 2026-10-08)"
        assert "draft.tex" in self._check(raw, log)


# =========================================================================== #
# a bound sentence cannot be empty or near-empty                                #
# =========================================================================== #

def _raw_side(sentence: str) -> dict:
    return {"spec_id": _SPEC_ID, "sentences": [{
        "document": "draft.tex", "kind": "result", "hypothesis_id": "H2",
        "sentence": sentence,
    }]}


class TestHollowSentences:
    @pytest.mark.parametrize("sentence", ["", "   \n ", "new", "(as of 2026-10-08)"])
    def test_parse_rejects_an_empty_or_very_short_sentence(self, sentence):
        with pytest.raises(ValueError, match=r"sentences\[0\]"):
            parse_novelty_sentences(_raw_side(sentence), _SPEC_ID)

    def test_parse_accepts_the_shortest_sentence_render_writes(self):
        parsed = parse_novelty_sentences(_raw_side("x (as of 2026-10-08)"), _SPEC_ID)
        assert parsed[0].sentence == "x (as of 2026-10-08)"

    def test_empty_bound_sentence_fails_verify(self, tmp_path):
        # An empty needle used to be skipped: the binding verified clean against any draft.
        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        side = _side(run_dir)
        side["sentences"][0]["sentence"] = ""
        (run_dir / NOVELTY_SENTENCES_FILE).write_text(json.dumps(side), encoding="utf-8")
        assert NOVELTY_SENTENCES_FILE in verify_run(run_dir).paper_novelty_problems

    @pytest.mark.parametrize("text", ["", "   "])
    def test_draft_render_refuses_an_empty_novelty_text(self, text):
        with pytest.raises(ValueError, match="no text"):
            render_paper_latex(
                _spec(), [], evidence=[_found_nothing(log=None)],
                prose=PaperProse(introduction=r"We report X\novelty{result}{H2}{" + text + "}."),
            )

    @pytest.mark.parametrize("text", ["", "   "])
    def test_si_render_refuses_an_empty_novelty_text(self, text):
        si = AuthoredSI(sections=[{"title": "S", "body": r"X\novelty{result}{H2}{" + text + "}."}])
        with pytest.raises(ValueError, match="no text"):
            render_authored_si_latex(si, _spec(), [], evidence=[_found_nothing(log=None)])


# =========================================================================== #
# smaller fixes: one file-name prefix, the artifact pattern, index dedupe       #
# =========================================================================== #

class TestSmallerFixes:
    def test_malformed_side_file_line_names_the_file_once(self, tmp_path):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from sci_adk.cli import main

        run_dir, spec = _seeded(tmp_path, log=_trial_log())
        _render(tmp_path, spec, PaperProse(introduction=_INTRO))
        (run_dir / NOVELTY_SENTENCES_FILE).write_text("{not json", encoding="utf-8")
        report = verify_run(run_dir)
        assert not report.paper_novelty_problems[NOVELTY_SENTENCES_FILE][0].startswith(
            NOVELTY_SENTENCES_FILE
        )
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            main(["verify", str(run_dir)])
        lines = [ln for ln in err.getvalue().splitlines() if NOVELTY_SENTENCES_FILE in ln]
        assert lines and all(ln.count(NOVELTY_SENTENCES_FILE) == 1 for ln in lines)

    def test_tool_vocabulary_names_the_binding_file(self):
        assert check_paper_tool_vocabulary(
            "The bindings are kept in novelty_sentences.json."
        ) == ["novelty_sentences.json"]
        # the draft's prose sanitizer writes the underscore escaped
        assert check_paper_tool_vocabulary(
            r"The bindings are kept in novelty\_sentences.json."
        ) == [r"novelty\_sentences.json"]

    def test_index_recorded_in_two_cases_is_named_once(self):
        log = SearchLogRecord(
            searched_at=["2026-10-08T09:00:00Z"],
            queries=[_q("inspirehep", "ok"), _q("InspireHEP", "ok"), _q("openalex", "ok")],
        )
        assert novelty_scope_suffix("result", "H2", _spec(), [_found_nothing(log=log)]) == (
            " (no such report was found in searches of inspirehep and OpenAlex on 2026-10-08)"
        )
