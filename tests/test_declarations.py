"""
The conclusion DECLARATION list (design/reader-facing-prose.md §11.3).

The contract: the submitted manuscript is plain LaTeX carrying no opaque shorthand a
reviewer would not recognize (the OD-7 constraint) -- so the binding between a conclusion
and the record lives in a side file that is never submitted:

    hypothesis id | the status the author wrote to | the exact sentence that states it

``sci-adk verify`` runs three deterministic checks over it, none of which reads meaning:

  1. the declared status is still what the record derives (belief is NON-MONOTONE, so a
     revision must cost a rewrite of the passage, not a silent re-wording);
  2. the declared sentence still appears in the manuscript (an edit detaches the
     declaration from its subject);
  3. every hypothesis the record DECIDED has a declared conclusion (the floor).

Whether a sentence OVERSTATES its declared status is semantic and is NOT decided here --
that is escalated to an advisory reviewer (design §11.4); no LLM sits on the verdict path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
from sci_adk.core.declarations import (
    ConclusionReview,
    Declaration,
    Declarations,
    ReadConclusion,
    load_declarations,
)
from sci_adk.core.evidence import (
    Bearing, BearingDirection, EvidenceItem, EvidenceKind, Provenance, Result,
)
from sci_adk.core.spec import (
    DecisionRule, DecisionRuleKind, Hypothesis, HypothesisMode, MethodPlan,
    RawProposal, Spec, TargetClaim,
)
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verify import verify_run
from sci_adk.render.declaration_checks import (
    declaration_disagreements,
    declaration_problems,
    opening_note_lines,
    status_mismatches,
    unanchored_sentences,
    undeclared_hypotheses,
)

_T0 = datetime(2026, 8, 31, 9, 0, 0, tzinfo=timezone.utc)
_NC = "the verifier checks a property not baked into the generator"
_SENTENCE = "The model reproduces the held-out measurements to within a factor of two."


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def _spec(*hyp_ids: str) -> Spec:
    ids = hyp_ids or ("hyp-001",)
    return Spec(
        id="sp-decl", version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=h, statement="s", mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="empirical", non_circularity=_NC,
            ) for h in ids
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id=f"tc-{h}", statement="t", answers=h) for h in ids],
    )


def _claim(hyp_id: str, status: ClaimStatus, *, claim_id: str | None = None) -> Claim:
    return Claim(
        id=claim_id or f"claim-{hyp_id}", spec_id="sp-decl", answers=hyp_id,
        statement="s", status=status,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.5, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )


def _decls(*rows: tuple[str, ClaimStatus, str]) -> Declarations:
    return Declarations(
        spec_id="sp-decl",
        declarations=[
            Declaration(hypothesis_id=h, status=s, sentence=t) for h, s, t in rows
        ],
    )


# --------------------------------------------------------------------------- #
# check 1 -- the declared status still matches the record
# --------------------------------------------------------------------------- #

def test_matching_declaration_is_clean():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    assert status_mismatches(decls, [_claim("hyp-001", ClaimStatus.SUPPORTED)]) == []


def test_belief_revision_makes_the_declaration_fail():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    problems = status_mismatches(decls, [_claim("hyp-001", ClaimStatus.CONTESTED)])
    assert len(problems) == 1
    assert "supported" in problems[0] and "contested" in problems[0]
    assert "rewrite" in problems[0].lower()  # the remedy, not just the fact


def test_declaring_a_conclusion_the_record_never_decided_fails():
    decls = _decls(("hyp-999", ClaimStatus.SUPPORTED, _SENTENCE))
    problems = status_mismatches(decls, [_claim("hyp-001", ClaimStatus.SUPPORTED)])
    assert len(problems) == 1 and "hyp-999" in problems[0]


def test_a_novelty_subclaim_is_not_the_headline_verdict():
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED,
                     claim_id="claim-novelty-result-hyp-001")]
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    assert len(status_mismatches(decls, claims)) == 1


# --------------------------------------------------------------------------- #
# check 2 -- the declared sentence is still in the manuscript
# --------------------------------------------------------------------------- #

def test_sentence_present_is_clean():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    tex = f"\\section{{Results}}\n{_SENTENCE}\nMore prose follows.\n"
    assert unanchored_sentences(decls, tex) == []


def test_latex_line_wrapping_does_not_break_the_match():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    wrapped = "The model reproduces the held-out\n  measurements to within\na factor of two."
    assert unanchored_sentences(decls, f"\\section{{Results}}\n{wrapped}\n") == []


def test_an_edited_sentence_detaches_the_declaration():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    edited = "The model accurately predicts the held-out measurements."
    problems = unanchored_sentences(decls, f"\\section{{Results}}\n{edited}\n")
    assert len(problems) == 1
    assert "hyp-001" in problems[0] and "no longer" in problems[0]


def test_a_sentence_surviving_only_in_a_comment_does_not_count():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    tex = f"\\section{{Results}}\n% {_SENTENCE}\nThe model does something else.\n"
    assert len(unanchored_sentences(decls, tex)) == 1


def test_an_escaped_percent_is_not_treated_as_a_comment():
    sentence = r"Accuracy improved by 40\% across the range."
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, sentence))
    assert unanchored_sentences(decls, f"\\section{{Results}}\n{sentence}\n") == []


# --------------------------------------------------------------------------- #
# check 3 -- the floor
# --------------------------------------------------------------------------- #

def test_floor_flags_a_decided_hypothesis_with_no_declaration():
    spec = _spec("hyp-001", "hyp-002")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED),
              _claim("hyp-002", ClaimStatus.REFUTED)]
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    problems = undeclared_hypotheses(decls, spec, claims)
    assert len(problems) == 1 and "hyp-002" in problems[0]
    assert "refuted" in problems[0]  # tells the author what it must say


def test_floor_is_clean_when_every_decided_hypothesis_is_declared():
    spec = _spec("hyp-001", "hyp-002")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED),
              _claim("hyp-002", ClaimStatus.REFUTED)]
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE),
                   ("hyp-002", ClaimStatus.REFUTED, "The scaling relation does not hold."))
    assert undeclared_hypotheses(decls, spec, claims) == []


def test_floor_skips_a_hypothesis_the_record_never_decided():
    spec = _spec("hyp-001", "hyp-undecided")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED)]
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    assert undeclared_hypotheses(decls, spec, claims) == []


# --------------------------------------------------------------------------- #
# the type + loader
# --------------------------------------------------------------------------- #

def test_absent_file_means_the_run_declares_nothing(tmp_path):
    assert load_declarations(tmp_path) is None


def test_a_malformed_list_is_loud_not_silently_skipped(tmp_path):
    (tmp_path / "declarations.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_declarations(tmp_path)


def test_unknown_fields_are_rejected(tmp_path):
    (tmp_path / "declarations.json").write_text(
        json.dumps({"spec_id": "s", "declarations": [], "surprise": 1}), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_declarations(tmp_path)


def test_roundtrip(tmp_path):
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    (tmp_path / "declarations.json").write_text(
        decls.model_dump_json(), encoding="utf-8"
    )
    loaded = load_declarations(tmp_path)
    assert loaded is not None
    assert loaded.declared_hypotheses == {"hyp-001"}
    assert loaded.document == "draft.tex"


# --------------------------------------------------------------------------- #
# verify integration
# --------------------------------------------------------------------------- #

def _seeded_run(tmp_path, *, hyp_ids=("hyp-001",), point=0.95):
    spec = _spec(*hyp_ids)

    def experiment(s, w):
        return [
            EvidenceItem(
                id=f"ev-{h}", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="measured"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=h, direction=BearingDirection.SUPPORTS)],
            ) for h in hyp_ids
        ]

    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=tmp_path)
    return run_dir


def _write(run_dir, tex: str, decls: Declarations | None):
    paper = run_dir / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "draft.tex").write_text(tex, encoding="utf-8")
    if decls is not None:
        (run_dir / "declarations.json").write_text(
            decls.model_dump_json(), encoding="utf-8"
        )


def test_verify_is_clean_for_a_faithful_declaration(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    report = verify_run(run_dir)
    assert report.declarations_clean is True
    assert report.declaration_problems_found == []


def test_verify_catches_the_stale_declaration_after_a_belief_revision(tmp_path):
    """The crown case: the record moved, the argument did not."""
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    assert verify_run(run_dir).declarations_clean is True

    claim_path = next(p for p in (run_dir / "claims").glob("*.json")
                      if "novelty" not in p.name)
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["status"] = "contested"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")

    report = verify_run(run_dir)
    assert report.declarations_clean is False
    assert report.passed is False
    assert any("contested" in p for p in report.declaration_problems_found)


def test_verify_catches_a_silently_edited_conclusion(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    assert verify_run(run_dir).declarations_clean is True

    # The author strengthens the sentence without touching the record or the list.
    (run_dir / "paper" / "draft.tex").write_text(
        "\\section{Results}\nThe model accurately predicts every measurement.\n",
        encoding="utf-8",
    )
    report = verify_run(run_dir)
    assert report.declarations_clean is False
    assert any("no longer" in p for p in report.declaration_problems_found)


def test_verify_is_vacuously_clean_without_a_declaration_list(tmp_path):
    run_dir = _seeded_run(tmp_path, hyp_ids=("hyp-001", "hyp-002"))
    _write(run_dir, "\\section{Results}\nOrdinary prose.\n", None)
    assert verify_run(run_dir).declarations_clean is True


def test_verify_floor_fires_once_the_list_exists(tmp_path):
    run_dir = _seeded_run(tmp_path, hyp_ids=("hyp-001", "hyp-002"))
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    report = verify_run(run_dir)
    assert report.declarations_clean is False
    assert any("hyp-002" in p for p in report.declaration_problems_found)


def test_verify_reports_a_manuscript_that_does_not_exist(tmp_path):
    # The list may name the document its sentences live in (design §11.1 moves the paper
    # to its own artifact); naming one that is not there is a loud failure, not a pass.
    run_dir = _seeded_run(tmp_path)
    decls = Declarations(
        spec_id="sp-decl", document="paper.tex",
        declarations=[Declaration(hypothesis_id="hyp-001",
                                  status=ClaimStatus.SUPPORTED, sentence=_SENTENCE)],
    )
    (run_dir / "declarations.json").write_text(decls.model_dump_json(), encoding="utf-8")
    report = verify_run(run_dir)
    assert report.declarations_clean is False
    assert any("does not exist" in p for p in report.declaration_problems_found)


def test_a_conclusion_absent_from_the_rendered_draft_is_caught(tmp_path):
    # The seeded run renders its own draft.tex; a sentence never written into it cannot be
    # declared. This is check 2 doing its job against a real rendered manuscript.
    run_dir = _seeded_run(tmp_path)
    (run_dir / "declarations.json").write_text(
        _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)).model_dump_json(),
        encoding="utf-8",
    )
    report = verify_run(run_dir)
    assert report.declarations_clean is False
    assert any("no longer" in p for p in report.declaration_problems_found)


def test_verify_is_read_only_for_declarations(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    before = {p: p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()}
    verify_run(run_dir)
    after = {p: p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()}
    assert before == after


# --------------------------------------------------------------------------- #
# the manuscript stays clean -- the point of the whole design
# --------------------------------------------------------------------------- #

def test_the_manuscript_carries_no_declaration_markup():
    """No opaque shorthand reaches the submitted source (the OD-7 constraint)."""
    from sci_adk.render.paper import check_paper_tool_vocabulary

    tex = f"\\section{{Results}}\n{_SENTENCE}\n"
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    assert declaration_problems(
        decls, _spec("hyp-001"), [_claim("hyp-001", ClaimStatus.SUPPORTED)], tex
    ) == []
    # Nothing was added to the document to achieve that.
    assert "\\finding" not in tex and "\\status" not in tex
    assert check_paper_tool_vocabulary(tex) == []


# --------------------------------------------------------------------------- #
# the advisory reviewer (design §11.4) -- a label comparison, never a gate
# --------------------------------------------------------------------------- #

def _review(*rows) -> ConclusionReview:
    return ConclusionReview(
        spec_id="sp-decl",
        reviewer="test",
        readings=[
            ReadConclusion(hypothesis_id=h, reads_as=s, basis=b)
            for h, s, b in rows
        ],
    )


def test_an_agreeing_reading_is_silent():
    """A faithful paper produces nothing -- the point of reading instead of hunting."""
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    review = _review(("hyp-001", ClaimStatus.SUPPORTED, "states it plainly"))
    assert declaration_disagreements(decls, review) == []


def test_overstatement_surfaces():
    decls = _decls(("hyp-001", ClaimStatus.CONTESTED, _SENTENCE))
    review = _review(("hyp-001", ClaimStatus.SUPPORTED, "reads as established"))
    lines = declaration_disagreements(decls, review)
    assert len(lines) == 1
    assert "contested" in lines[0] and "supported" in lines[0]


def test_understatement_surfaces_too():
    """A reviewer that flags only overclaims would reward hedging (design §4)."""
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    review = _review(("hyp-001", ClaimStatus.PROPOSED, "hedged to the point of no claim"))
    lines = declaration_disagreements(decls, review)
    assert len(lines) == 1 and "proposed" in lines[0]


def test_cannot_tell_gets_its_own_line():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    review = _review(("hyp-001", None, "the sentence is ambiguous"))
    lines = declaration_disagreements(decls, review)
    assert len(lines) == 1 and "could not tell" in lines[0]


def test_a_reading_for_an_undeclared_hypothesis_is_reported():
    decls = _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE))
    review = _review(("hyp-002", ClaimStatus.REFUTED, "x"))
    lines = declaration_disagreements(decls, review)
    assert len(lines) == 1 and "hyp-002" in lines[0]


def test_verify_routes_a_disagreement_to_the_advisory_channel_and_never_gates(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    before = verify_run(run_dir)
    (run_dir / "review.json").write_text(
        _review(("hyp-001", ClaimStatus.PROPOSED, "hedged")).model_dump_json(),
        encoding="utf-8",
    )
    after = verify_run(run_dir)
    assert any("conclusion review" in n for n in after.paper_advisory)
    # The model's disagreement changed NOTHING about the verdict.
    assert after.passed == before.passed
    assert after.declarations_clean is True
    assert after.declaration_problems_found == before.declaration_problems_found


def test_a_malformed_review_cannot_stop_a_run(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    before = verify_run(run_dir)
    (run_dir / "review.json").write_text("{ not json", encoding="utf-8")
    after = verify_run(run_dir)
    assert after.passed == before.passed   # a broken advisory cannot stop a run
    assert any("review" in n for n in after.paper_advisory)


def test_no_review_is_silent(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    report = verify_run(run_dir)
    assert not any("conclusion review" in n for n in report.paper_advisory)


# --------------------------------------------------------------------------- #
# the reviewer's cold reading of the opening -- its own list, its own wording
# --------------------------------------------------------------------------- #
#
# The reviewer's second duty (read the title, abstract and opening as a reader of the
# frozen venue, and name terms that reader would not know unaided) had no field: `notes`
# holds only identifiers read as quantities, so a vocabulary finding was dropped or shown
# under the identifier wording. `opening_notes` is its own list. Advisory, never gated.

_TERM = "criterion-5 tissue score"
_OPENING = "Records failing the criterion-5 tissue score were excluded."


def _opening_review(*notes: dict, readings=()) -> ConclusionReview:
    return ConclusionReview.model_validate({
        "spec_id": "sp-decl", "reviewer": "evaluator-conclusions",
        "readings": list(readings), "opening_notes": list(notes),
    })


def test_a_review_written_before_opening_notes_existed_loads_unchanged():
    # The shape the trial run's review.json has today: readings plus an empty notes list.
    review = ConclusionReview.model_validate({
        "spec_id": "s", "reviewer": "evaluator-conclusions",
        "readings": [{"hypothesis_id": "H1", "reads_as": "supported", "basis": "b"}],
        "notes": [],
    })
    assert review.opening_notes == []


def test_an_opening_note_names_the_term_its_sentence_and_the_reason():
    review = _opening_review({
        "term": _TERM, "document": "draft.tex", "sentence": _OPENING,
        "reason": "a label from another paper's scoring scheme, never explained",
    })
    lines = opening_note_lines(review)
    assert len(lines) == 1
    line = lines[0]
    assert f"'{_TERM}'" in line and _OPENING in line and "draft.tex" in line
    assert "never explained" in line
    assert "advisory" in line.lower()
    # Not the identifier wording: a term is not "a reported quantity".
    assert "reported quantity" not in line and "numbers.json" not in line


def test_an_opening_note_needs_only_the_term():
    review = _opening_review({"term": "PHYSPROP"})
    lines = opening_note_lines(review)
    assert len(lines) == 1 and "'PHYSPROP'" in lines[0] and "draft.tex" in lines[0]


def test_an_opening_note_without_a_term_is_not_a_note():
    with pytest.raises(ValueError, match=r"opening_notes\.0\.term"):
        _opening_review({"term": "", "reason": "x"})


def test_a_sentence_wrapped_across_lines_surfaces_on_one_line():
    review = _opening_review({"term": _TERM,
                              "sentence": "Records failing the\n  criterion-5 tissue score."})
    (line,) = opening_note_lines(review)
    assert "\n" not in line and "Records failing the criterion-5 tissue score." in line


def test_no_opening_notes_is_silent():
    assert opening_note_lines(_review(("hyp-001", ClaimStatus.SUPPORTED, "b"))) == []


def test_verify_surfaces_an_opening_note_and_never_gates(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n",
           _decls(("hyp-001", ClaimStatus.SUPPORTED, _SENTENCE)))
    before = verify_run(run_dir)
    (run_dir / "review.json").write_text(json.dumps({
        "spec_id": "sp-decl", "reviewer": "evaluator-conclusions",
        "readings": [{"hypothesis_id": "hyp-001", "reads_as": "supported", "basis": "b"}],
        "opening_notes": [{"term": _TERM, "sentence": _OPENING,
                           "reason": "a label the venue's reader cannot decode"}],
    }), encoding="utf-8")
    after = verify_run(run_dir)
    lines = [n for n in after.paper_advisory if _TERM in n]
    assert len(lines) == 1
    # The reading agreed with the declaration, so the opening note is the only line.
    assert not any("declared" in n for n in after.paper_advisory if "conclusion review" in n)
    assert after.passed == before.passed
    assert after.declarations_clean is True
    assert after.declaration_problems_found == before.declaration_problems_found


def test_opening_notes_surface_when_the_run_declares_no_conclusions(tmp_path):
    """A cold reading of the opening needs no declaration list to be worth reading."""
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n", None)
    (run_dir / "review.json").write_text(
        _opening_review({"term": _TERM}).model_dump_json(), encoding="utf-8")
    review_lines = [n for n in verify_run(run_dir).paper_advisory
                    if n.startswith("conclusion review")]
    assert len(review_lines) == 1 and _TERM in review_lines[0]


def test_identifier_and_opening_notes_keep_their_own_wording(tmp_path):
    run_dir = _seeded_run(tmp_path)
    _write(run_dir, f"\\section{{Results}}\n{_SENTENCE}\n", None)
    (run_dir / "review.json").write_text(json.dumps({
        "spec_id": "sp-decl", "reviewer": "evaluator-conclusions", "readings": [],
        "notes": [{"text": "5", "note": "reads as a count of criteria"}],
        "opening_notes": [{"term": _TERM}],
    }), encoding="utf-8")
    advisory = verify_run(run_dir).paper_advisory
    identifier = [n for n in advisory if "'5'" in n]
    opening = [n for n in advisory if _TERM in n]
    assert len(identifier) == 1 and "reported quantity" in identifier[0]
    assert len(opening) == 1 and "reported quantity" not in opening[0]


def test_the_agent_output_contract_loads_and_routes_each_duty_to_its_own_list():
    """The reviewer writes what its template shows; that example must load, and must put
    the second duty (the opening) and the third (identifiers) in different lists."""
    import re as _re
    from pathlib import Path as _Path

    import sci_adk

    template = (_Path(sci_adk.__file__).parent / "templates" / "research-workspace"
                / ".claude" / "agents" / "evaluator-conclusions.md").read_text(encoding="utf-8")
    contract = template.split("## Output Contract", 1)[1]
    example = _re.search(r"```json\n(.*?)\n```", contract, _re.DOTALL).group(1)
    review = ConclusionReview.model_validate(json.loads(example))
    assert review.opening_notes and review.notes
    assert "`opening_notes`" in contract and "`notes`" in contract
    second = template.split("## Second Duty", 1)[1].split("## Third Duty", 1)[0]
    third = template.split("## Third Duty", 1)[1].split("## How To Read", 1)[0]
    assert "`opening_notes`" in second
    assert "`notes`" in third and "`opening_notes`" not in third
