"""
The ``\\finding{hyp}{status}{text}`` markup -- OD-R1 (design/reader-facing-prose.md §8).

The contract: a paper ARGUES its conclusions in the author's own sentences while the
recorded verdict stays binding. The author DECLARES the status they are writing to; the
engine CHECKS that declaration against the record and renders only the author's text.

Architecture (mirrors the LOCKED ``\\novelty`` architecture, render/novelty.py): SURVIVE +
preamble ``\\newcommand{\\finding}[3]{#3}`` -- NOT substitute-away. So:

  - the reader sees the author's sentence, never the belief-state enum
    (``proposed``/``supported``/``contested``/``refuted``);
  - the declared status SURVIVES as metadata that ``sci-adk verify`` re-scans, so a
    belief revision (the record is non-monotone) makes the stale sentence FAIL LOUD
    instead of being silently rewritten under an unchanged argument.

Two gates:
  - MISMATCH (hard): declared status != the recorded experiment Claim status.
  - FLOOR (hard, opt-in per document): a document that argues ANY hypothesis via
    ``\\finding`` must argue EVERY hypothesis that has a derived experiment Claim -- the
    dual of the ceiling rule ("never overstate"), which alone selects for silent omission.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
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
from sci_adk.render.finding import (
    FINDING_NEWCOMMAND,
    FINDING_RENDER_RE,
    FINDING_SCAN_RE,
    check_finding,
    find_mismatched_findings,
    find_unargued_hypotheses,
    has_finding_markup,
)
from sci_adk.render.paper import check_paper_tool_vocabulary, render_paper_latex
from sci_adk.render.prose import PaperProse

_T0 = datetime(2026, 8, 31, 9, 0, 0, tzinfo=timezone.utc)
_NON_CIRC = "the verifier checks a property not baked into the generator"


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def _hyp(hyp_id: str) -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement="s",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=DecisionRule(
            kind=DecisionRuleKind.THRESHOLD,
            expression="point >= threshold => support",
            params={"statistic": "point", "op": ">=", "value": 0.9},
        ),
        referent="formal",
        non_circularity=_NON_CIRC,
    )


def _spec(*hyp_ids: str) -> Spec:
    ids = hyp_ids or ("hyp-001",)
    return Spec(
        id="sp-find",
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[_hyp(h) for h in ids],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id=f"tc-{h}", statement="t", answers=h) for h in ids],
    )


def _claim(hyp_id: str, status: ClaimStatus, *, claim_id: str | None = None) -> Claim:
    return Claim(
        id=claim_id or f"claim-{hyp_id}",
        spec_id="sp-find",
        answers=hyp_id,
        statement="s",
        status=status,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.0, basis="b"),
        mode=HypothesisMode.EXPLORATORY,
    )


# --------------------------------------------------------------------------- #
# the macro surface
# --------------------------------------------------------------------------- #

def test_render_regex_captures_three_args():
    m = FINDING_RENDER_RE.search(r"\finding{hyp-001}{supported}{The model reproduces it.}")
    assert m is not None
    assert m.group(1) == "hyp-001"
    assert m.group(2) == "supported"
    assert m.group(3) == "The model reproduces it."


def test_scan_regex_does_not_match_the_preamble_newcommand():
    # Same trap the novelty scan avoids: \finding} in \newcommand must not read as markup.
    assert FINDING_SCAN_RE.search(FINDING_NEWCOMMAND) is None


def test_newcommand_renders_only_the_author_text():
    assert FINDING_NEWCOMMAND == r"\newcommand{\finding}[3]{#3}"


def test_has_finding_markup():
    assert has_finding_markup(r"a \finding{h}{supported}{t} b") is True
    assert has_finding_markup("plain prose") is False


# --------------------------------------------------------------------------- #
# the MISMATCH gate
# --------------------------------------------------------------------------- #

def test_declared_status_matching_the_record_passes():
    check_finding("hyp-001", "supported", [_claim("hyp-001", ClaimStatus.SUPPORTED)])


def test_declared_status_contradicting_the_record_fails_loud():
    with pytest.raises(ValueError) as exc:
        check_finding("hyp-001", "supported", [_claim("hyp-001", ClaimStatus.REFUTED)])
    msg = str(exc.value)
    assert "hyp-001" in msg
    assert "supported" in msg and "refuted" in msg  # names BOTH -- actionable


def test_unknown_status_word_fails_loud():
    with pytest.raises(ValueError) as exc:
        check_finding("hyp-001", "confirmed", [_claim("hyp-001", ClaimStatus.SUPPORTED)])
    assert "confirmed" in str(exc.value)


def test_hypothesis_with_no_experiment_claim_fails_loud():
    with pytest.raises(ValueError) as exc:
        check_finding("hyp-999", "supported", [_claim("hyp-001", ClaimStatus.SUPPORTED)])
    assert "hyp-999" in str(exc.value)


def test_novelty_claims_are_not_the_headline_verdict():
    # claim-novelty-* must never answer a \finding -- the headline is the experiment Claim.
    claims = [
        _claim("hyp-001", ClaimStatus.SUPPORTED, claim_id="claim-novelty-result-hyp-001"),
    ]
    with pytest.raises(ValueError):
        check_finding("hyp-001", "supported", claims)


def test_non_emit_safe_hypothesis_id_is_refused_not_escaped():
    with pytest.raises(ValueError):
        check_finding("hyp%001", "supported", [_claim("hyp%001", ClaimStatus.SUPPORTED)])


# --------------------------------------------------------------------------- #
# the verify re-scan (belief revision must break the build)
# --------------------------------------------------------------------------- #

def test_rescan_clean_when_declaration_matches():
    tex = r"\finding{hyp-001}{supported}{The model reproduces the observed values.}"
    assert find_mismatched_findings(tex, [_claim("hyp-001", ClaimStatus.SUPPORTED)]) == []


def test_rescan_catches_a_belief_revision_after_render():
    # The paper was rendered when the record said supported; new evidence made it contested.
    tex = r"\finding{hyp-001}{supported}{The model reproduces the observed values.}"
    problems = find_mismatched_findings(tex, [_claim("hyp-001", ClaimStatus.CONTESTED)])
    assert len(problems) == 1
    assert "hyp-001" in problems[0] and "contested" in problems[0]


def test_rescan_is_deduplicated_and_sorted():
    tex = (
        r"\finding{hyp-001}{supported}{one} "
        r"\finding{hyp-001}{supported}{two} "
        r"\finding{hyp-002}{supported}{three}"
    )
    problems = find_mismatched_findings(
        tex,
        [
            _claim("hyp-001", ClaimStatus.REFUTED),
            _claim("hyp-002", ClaimStatus.REFUTED),
        ],
    )
    assert len(problems) == 2
    assert problems == sorted(problems)


# --------------------------------------------------------------------------- #
# the FLOOR gate (the missing dual of the ceiling)
# --------------------------------------------------------------------------- #

def test_floor_is_vacuous_for_a_document_that_uses_no_finding_markup():
    # Opt-in per document: a paper that never argues via \finding is not retro-broken.
    spec = _spec("hyp-001", "hyp-002")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED), _claim("hyp-002", ClaimStatus.REFUTED)]
    assert find_unargued_hypotheses("plain prose, no markup", spec, claims) == []


def test_floor_flags_a_hypothesis_argued_nowhere():
    spec = _spec("hyp-001", "hyp-002")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED), _claim("hyp-002", ClaimStatus.REFUTED)]
    tex = r"\finding{hyp-001}{supported}{The model reproduces the observed values.}"
    problems = find_unargued_hypotheses(tex, spec, claims)
    assert len(problems) == 1
    assert "hyp-002" in problems[0]


def test_floor_is_clean_when_every_hypothesis_is_argued():
    spec = _spec("hyp-001", "hyp-002")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED), _claim("hyp-002", ClaimStatus.REFUTED)]
    tex = (
        r"\finding{hyp-001}{supported}{The model reproduces the observed values.} "
        r"\finding{hyp-002}{refuted}{The elasticity relation does not hold here.}"
    )
    assert find_unargued_hypotheses(tex, spec, claims) == []


def test_floor_ignores_a_hypothesis_with_no_derived_claim():
    # Nothing can be argued about a hypothesis the record never decided.
    spec = _spec("hyp-001", "hyp-undecided")
    claims = [_claim("hyp-001", ClaimStatus.SUPPORTED)]
    tex = r"\finding{hyp-001}{supported}{The model reproduces the observed values.}"
    assert find_unargued_hypotheses(tex, spec, claims) == []


# --------------------------------------------------------------------------- #
# render integration
# --------------------------------------------------------------------------- #

def _render(prose: PaperProse, claims):
    return render_paper_latex(spec=_spec("hyp-001"), claims=claims, prose=prose)


def test_render_survives_the_markup_and_emits_the_newcommand():
    tex = _render(
        PaperProse(results=r"\finding{hyp-001}{supported}{The model reproduces it.}"),
        [_claim("hyp-001", ClaimStatus.SUPPORTED)],
    )
    assert FINDING_NEWCOMMAND in tex
    assert r"\finding{hyp-001}{supported}{The model reproduces it.}" in tex


def test_render_fails_loud_on_a_contradicted_declaration():
    with pytest.raises(ValueError):
        _render(
            PaperProse(results=r"\finding{hyp-001}{supported}{The model reproduces it.}"),
            [_claim("hyp-001", ClaimStatus.REFUTED)],
        )


def test_a_finding_free_paper_carries_no_newcommand():
    # Byte-identical invariant, same as the novelty gate.
    tex = _render(
        PaperProse(results="Ordinary prose with no markup."),
        [_claim("hyp-001", ClaimStatus.SUPPORTED)],
    )
    assert FINDING_NEWCOMMAND not in tex


def test_author_text_is_prose_sanitized_inside_the_span():
    tex = _render(
        PaperProse(results=r"\finding{hyp-001}{supported}{A 50% drop in run_time.}"),
        [_claim("hyp-001", ClaimStatus.SUPPORTED)],
    )
    assert r"50\%" in tex and r"run\_time" in tex


def test_the_enum_word_never_reaches_the_reader_but_survives_for_verify():
    # arg 2 stays in the source as verify metadata; \newcommand renders only arg 3.
    tex = _render(
        PaperProse(results=r"\finding{hyp-001}{supported}{The model reproduces it.}"),
        [_claim("hyp-001", ClaimStatus.SUPPORTED)],
    )
    assert r"{supported}{" in tex  # metadata present
    assert FINDING_SCAN_RE.search(tex) is not None  # verify can re-scan it


def test_the_markup_does_not_trip_the_tool_vocabulary_gate():
    # Why the macro is \finding and not \verdict: paper.py bans the word "verdict".
    tex = _render(
        PaperProse(results=r"\finding{hyp-001}{supported}{The model reproduces it.}"),
        [_claim("hyp-001", ClaimStatus.SUPPORTED)],
    )
    assert check_paper_tool_vocabulary(tex) == []


# --------------------------------------------------------------------------- #
# verify integration -- the belief-revision catch, end to end
# --------------------------------------------------------------------------- #

def _seeded_run(tmp_path, *, hyp_ids=("hyp-001",), point=0.95):
    """Seed a real run whose hypotheses each get a SUPPORTED experiment Claim."""
    from sci_adk.core.evidence import (
        Bearing,
        BearingDirection,
        EvidenceItem,
        EvidenceKind,
        Provenance,
        Result,
    )
    from sci_adk.loop.checkpoint_loop import run_checkpoint_loop

    spec = _spec(*hyp_ids)

    def experiment(s, w):
        return [
            EvidenceItem(
                id=f"ev-{h}",
                spec_id=s.id,
                kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=h, direction=BearingDirection.SUPPORTS)],
            )
            for h in hyp_ids
        ]

    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(
        run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=tmp_path
    )
    return run_dir


def _write_draft(run_dir, body: str):
    paper = run_dir / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "draft.tex").write_text(body, encoding="utf-8")


def test_verify_is_clean_when_the_declaration_still_matches(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _seeded_run(tmp_path)
    _write_draft(
        run_dir,
        r"\finding{hyp-001}{supported}{The model reproduces the observed values.}",
    )
    report = verify_run(run_dir)
    assert report.paper_finding_clean is True
    assert report.paper_finding_problems == {}


def test_verify_catches_the_stale_declaration_after_a_belief_revision(tmp_path):
    """The crown case: the record moved, the argument did not.

    Under substitution the next render would silently swap the word and leave the
    surrounding argument written for the old verdict. Here verify REFUSES.
    """
    import json

    from sci_adk.loop.verify import verify_run

    run_dir = _seeded_run(tmp_path)
    _write_draft(
        run_dir,
        r"\finding{hyp-001}{supported}{The model reproduces the observed values.}",
    )
    assert verify_run(run_dir).paper_finding_clean is True

    # The record revises: supported -> contested (new evidence conflicts).
    claim_path = next(
        p for p in (run_dir / "claims").glob("*.json") if "novelty" not in p.name
    )
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["status"] = "contested"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")

    report = verify_run(run_dir)
    assert report.paper_finding_clean is False
    assert report.passed is False
    problems = report.paper_finding_problems["draft.tex"]
    assert any("hyp-001" in p and "contested" in p for p in problems)


def test_verify_floor_flags_a_decided_hypothesis_argued_nowhere(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _seeded_run(tmp_path, hyp_ids=("hyp-001", "hyp-002"))
    _write_draft(
        run_dir,
        r"\finding{hyp-001}{supported}{The model reproduces the observed values.}",
    )
    report = verify_run(run_dir)
    assert report.paper_finding_clean is False
    assert any(
        "hyp-002" in p for p in report.paper_finding_problems["draft.tex"]
    )


def test_verify_is_vacuously_clean_for_a_draft_with_no_markup(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _seeded_run(tmp_path, hyp_ids=("hyp-001", "hyp-002"))
    _write_draft(run_dir, "Ordinary prose that uses no markup at all.")
    report = verify_run(run_dir)
    assert report.paper_finding_clean is True


def test_verify_is_read_only_for_findings(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _seeded_run(tmp_path)
    _write_draft(
        run_dir,
        r"\finding{hyp-001}{supported}{The model reproduces the observed values.}",
    )
    before = {
        p: p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()
    }
    verify_run(run_dir)
    after = {p: p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()}
    assert before == after
