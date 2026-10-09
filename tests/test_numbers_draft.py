"""
`sci-adk numbers draft` (design/declared-numbers.md §4.4).

A helper that proposes a source for each literal of the paper by exact printed-precision
match against every recorded field, and marks the rest. Deterministic, no model, no
network. It saves effort; the author's choices in ``numbers.json`` are what verify checks.

  - one match      -> ``source`` filled;
  - several        -> ``candidates`` listed, no source chosen;
  - none           -> ``unresolved``.

It reads the paper the way verify will: the rendered ``paper/draft.tex`` / ``si.tex``, or,
before render, the prose JSON sanitized by the same render path.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.numbers import NumberEntry
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
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.render.number_checks import NumberRecord
from sci_adk.render.number_draft import propose_numbers
from sci_adk.render.prose import AuthoredSI, PaperProse, SISection

_NON_CIRC = "the verifier checks a property not baked into the generator"


def _ev(ev_id: str, **result) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id, spec_id="sp-x", kind=EvidenceKind.OBSERVATION,
        provenance=Provenance(code_ref="x"), result=Result(type="quantitative", **result),
        bears_on=[],
    )


SPEC_JSON = {
    "id": "sp-x",
    "hypotheses": [{"id": "H1", "decision_rule": {
        "expression": "the 95% interval is reported", "params": {"value": 0.5}}}],
}
RECORD = NumberRecord(
    spec_json=SPEC_JSON,
    evidence=[
        _ev("evi-fit", effect_size=0.768932,
            finding=json.dumps({"summary": "fit", "n_chemicals": 341})),
        _ev("evi-b", point=0.1, finding=json.dumps({"summary": "count", "n": 341})),
    ],
    bib_years={"Arnot2006": "2006", "Veith1979": "1979"},
)


def _by_text(draft: dict) -> dict[str, dict]:
    return {e["text"]: e for e in draft["numbers"]}


# --------------------------------------------------------------------------- #
# the proposal (pure)
# --------------------------------------------------------------------------- #

def test_single_ambiguous_and_unresolved_proposals():
    docs = {"draft.tex": ("Slope 0.769 over 341 chemicals from 6973 records (CAS RN "
                          "17109-49-8), as in 2006; the 95 percent interval.")}
    draft, summary = propose_numbers(docs, RECORD, "sp-x")
    by = _by_text(draft)
    assert by["0.769"]["source"] == {"evidence": "evi-fit", "field": "effect_size"}
    assert by["2006"]["source"] == {"bib": "Arnot2006", "field": "year"}
    assert by["95"]["source"] == {"spec_text": "hypotheses[0].decision_rule.expression"}
    assert by["341"]["candidates"] == [
        {"evidence": "evi-fit", "field": "finding.n_chemicals"},
        {"evidence": "evi-b", "field": "finding.n"},
    ]
    assert "source" not in by["341"]
    assert by["6973"]["unresolved"] is True
    assert by["17109-49-8"]["unresolved"] is True
    assert summary == {"resolved": 3, "ambiguous": 1, "unresolved": 2}
    assert draft["spec_id"] == "sp-x"


def test_a_resolved_proposal_is_a_valid_entry_and_the_rest_are_not():
    docs = {"draft.tex": "Slope 0.769 over 341 chemicals from 6973 records."}
    draft, _ = propose_numbers(docs, RECORD, "sp-x")
    by = _by_text(draft)
    NumberEntry.model_validate(by["0.769"])
    for text in ("341", "6973"):
        assert "where" in by[text]           # a snippet for the author to decide on
        try:
            NumberEntry.model_validate(by[text])
        except ValueError:
            continue
        raise AssertionError(f"{text}: an undecided proposal must not load as an entry")


def test_each_text_is_proposed_once_per_document_in_source_order():
    docs = {"draft.tex": "0.769, then 341, then 0.769 again.", "si.tex": "SI: 0.769."}
    draft, _ = propose_numbers(docs, RECORD, "sp-x")
    assert [(e["text"], e["document"]) for e in draft["numbers"]] == [
        ("0.769", "draft.tex"), ("341", "draft.tex"), ("0.769", "si.tex")]


def test_a_spec_numeric_field_is_a_candidate():
    draft, _ = propose_numbers({"draft.tex": "threshold 0.5"}, RECORD, "sp-x")
    assert _by_text(draft)["0.5"]["source"] == {
        "spec": "hypotheses[0].decision_rule.params.value"}


# --------------------------------------------------------------------------- #
# the verb
# --------------------------------------------------------------------------- #

def _spec() -> Spec:
    return Spec(
        id="spec-d", version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id="hyp-a", statement="a recorded statement", mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD, expression="point >= threshold => support",
                params={"statistic": "point", "op": ">=", "value": 0.5},
            ),
            referent="formal", non_circularity=_NON_CIRC,
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-a")],
    )


def _run(tmp_path: Path, draft: str | None = None) -> Path:
    spec = _spec()
    run_dir = tmp_path / "runs" / spec.id
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "claims").mkdir()
    (run_dir / "spec.json").write_text(spec.model_dump_json(), encoding="utf-8")
    ev = EvidenceItem(
        id="ev-1", spec_id=spec.id, kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=0.61, ci=[0.55, 0.66],
                      finding=json.dumps({"summary": "s", "n_items": 341})),
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
    return run_dir


def _cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def test_the_verb_reads_the_rendered_paper_and_never_touches_numbers_json(tmp_path):
    run_dir = _run(tmp_path, r"\section{Results}The value is 0.61 over 341 items; 6973.")
    (run_dir / "numbers.json").write_text("KEEP", encoding="utf-8")
    rc, out, _ = _cli("numbers", "draft", str(run_dir))
    assert rc == 0
    assert (run_dir / "numbers.json").read_text(encoding="utf-8") == "KEEP"
    draft = json.loads((run_dir / "numbers.draft.json").read_text(encoding="utf-8"))
    by = _by_text(draft)
    assert by["0.61"]["source"] == {"evidence": "ev-1", "field": "point"}
    assert by["341"]["source"] == {"evidence": "ev-1", "field": "finding.n_items"}
    assert by["6973"]["unresolved"] is True
    assert "2 resolved" in out and "0 ambiguous" in out and "1 unresolved" in out
    assert "6973" in out   # the unresolved literals are named


def test_the_verb_names_resolved_literals_stated_more_than_once(tmp_path):
    # One entry covers every occurrence of its text, so a repeated text is where a second
    # role can hide behind the single match the helper found.
    run_dir = _run(tmp_path, "The value is 0.61 here, and 0.61 there; 341 once.")
    rc, out, _ = _cli("numbers", "draft", str(run_dir))
    assert rc == 0
    assert "0.61 x2" in out
    assert "341 x" not in out


def test_the_verb_reads_the_prose_the_way_render_will(tmp_path):
    run_dir = _run(tmp_path)
    prose = tmp_path / "prose.json"
    prose.write_text(json.dumps({
        "abstract": "The value was 0.61 (95% CI 0.55–0.66), and R² = 0.678.",
    }), encoding="utf-8")
    rc, _, err = _cli("numbers", "draft", str(run_dir), "--prose", str(prose))
    assert rc == 0, err
    draft = json.loads((run_dir / "numbers.draft.json").read_text(encoding="utf-8"))
    assert [e["text"] for e in draft["numbers"]] == ["0.61", "95", "0.55", "0.66", "0.678"]
    assert not (run_dir / "paper").exists()   # nothing was rendered to disk


def test_the_verb_reads_an_authored_si(tmp_path):
    run_dir = _run(tmp_path)
    si = tmp_path / "si.json"
    si.write_text(json.dumps({"sections": [{"title": "Counts", "body": "341 items."}]}),
                  encoding="utf-8")
    rc, _, err = _cli("numbers", "draft", str(run_dir), "--si", str(si))
    assert rc == 0, err
    draft = json.loads((run_dir / "numbers.draft.json").read_text(encoding="utf-8"))
    assert [(e["text"], e["document"]) for e in draft["numbers"]] == [("341", "si.tex")]


def test_the_verb_needs_a_paper_or_prose(tmp_path):
    rc, _, err = _cli("numbers", "draft", str(_run(tmp_path)))
    assert rc == 2
    assert "--prose" in err


def test_figures_without_prose_is_a_usage_error(tmp_path):
    run_dir = _run(tmp_path, "Values 0.61.")
    figures = tmp_path / "figures.json"
    figures.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _cli("numbers", "draft", str(run_dir), "--figures", str(figures))
    assert exc.value.code == 2
    assert not (run_dir / "numbers.draft.json").exists()


def test_the_verb_is_deterministic(tmp_path):
    run_dir = _run(tmp_path, "Values 0.61, 341, 0.55 and 6973.")
    _cli("numbers", "draft", str(run_dir))
    first = (run_dir / "numbers.draft.json").read_bytes()
    _cli("numbers", "draft", str(run_dir))
    assert (run_dir / "numbers.draft.json").read_bytes() == first


def test_render_texts_is_what_render_writes(tmp_path):
    run_dir = _run(tmp_path)
    spec = _spec()
    prose = PaperProse(abstract="The value was 0.61 (95% CI 0.55–0.66).",
                       results="Over 341 items.")
    si = AuthoredSI(sections=[SISection(title="Counts", body="341 items.")])
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    draft_tex, si_tex = compiler.render_texts(spec, prose=prose, si=si)
    paper_path, si_path, _, _ = compiler.stage_render(spec, prose=prose, si=si)
    assert paper_path.read_text(encoding="utf-8") == draft_tex
    assert si_path.read_text(encoding="utf-8") == si_tex
    assert run_dir.is_dir()
