"""
Novelty render gate (N2) + verify gate (N3): the ``\\novelty{kind}{hyp}{text}`` markup.

design/literature-acquisition.md §"Render-time novelty gate". A novelty/priority claim is
asserted in the paper ONLY via explicit markup; the engine re-derives the {hyp, kind} status
via the SINGLE source of truth ``derive_novelty_status`` (NEVER the recorded claim) and:

  - SUPPORTED  -> the markup SURVIVES into the .tex (a preamble ``\\newcommand{\\novelty}[3]
                  {#3}`` renders only the text) with an honest record-derived scope baked in:
                  ``<text> (to our knowledge, as of <YYYY-MM-DD>)``;
  - NOT SUPPORTED / unknown hyp / bad kind -> HARD fail: ``ValueError`` at render time and a
                  non-zero ``sci-adk verify``.

Architecture (locked): SURVIVE + preamble newcommand (not substitute-away). The gate runs on
BOTH ``draft.tex`` (PaperProse) and ``si.tex`` (SIProse). The byte-identical invariant: a
no-novelty render carries no ``\\newcommand{\\novelty}`` and is unchanged from before N2.

PURE for the render tests (data in, string out); N3 tests seed a real run dir + write a
``paper/draft.tex`` and read the verify report.
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
from sci_adk.loop.verify import verify_run
from sci_adk.render.novelty import (
    NOVELTY_NEWCOMMAND,
    NOVELTY_RENDER_RE,
    NOVELTY_SCAN_RE,
    find_unsupported_novelty,
    has_novelty_markup,
    novelty_scope_suffix,
)
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import PaperProse, SIProse
from sci_adk.render.si import render_si_latex

_NON_CIRC = "the verifier checks a property not baked into the generator"
_T0 = datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def _spec(
    *,
    hyp_id: str = "hyp-n",
    novelty_result: bool = True,
    novelty_method: bool = False,
) -> Spec:
    return Spec(
        id="sp-nov",
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
                novelty_result=novelty_result,
                novelty_method=novelty_method,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _found_nothing(
    *,
    hyp_id: str = "hyp-n",
    kind: str = "result",
    ev_id: str = "evi-nov-fn",
    created_at: datetime = _T0,
) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id="sp-nov",
        kind=EvidenceKind.NOVELTY_DECISION,
        provenance=Provenance(code_ref=f"novelty:{kind}:found_nothing"),
        result=Result(type="qualitative", finding=f"{kind} found_nothing"),
        bears_on=[],
        literature_decision=LiteratureDecision(
            outcome="found_nothing", hypothesis_id=hyp_id, kind=kind
        ),
    )


# =========================================================================== #
# (N2) novelty_scope_suffix -- the pure record re-derivation                  #
# =========================================================================== #

class TestNoveltyScopeSuffix:
    def test_supported_bakes_record_date(self):
        spec = _spec()
        suffix = novelty_scope_suffix("result", "hyp-n", spec, [_found_nothing()])
        assert suffix == " (to our knowledge, as of 2026-06-18)"

    def test_supported_uses_latest_found_nothing_date(self):
        # Two found_nothing decisions -> the LATEST created_at wins (most recent confirmation).
        spec = _spec()
        older = _found_nothing(ev_id="evi-old", created_at=_T0)
        newer = _found_nothing(
            ev_id="evi-new", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc)
        )
        suffix = novelty_scope_suffix("result", "hyp-n", spec, [newer, older])
        assert suffix == " (to our knowledge, as of 2026-07-01)"

    def test_unsupported_no_found_nothing_raises(self):
        spec = _spec()
        with pytest.raises(ValueError) as exc:
            novelty_scope_suffix("result", "hyp-n", spec, [])  # no decision
        msg = str(exc.value)
        assert "result-novelty" in msg and "hyp-n" in msg
        assert "found-nothing" in msg or "found_nothing" in msg  # the remedy

    def test_unknown_hypothesis_raises(self):
        spec = _spec()
        with pytest.raises(ValueError) as exc:
            novelty_scope_suffix("result", "no-such-hyp", spec, [_found_nothing()])
        assert "unknown hypothesis" in str(exc.value)

    def test_bad_kind_raises(self):
        spec = _spec()
        with pytest.raises(ValueError) as exc:
            novelty_scope_suffix("resul", "hyp-n", spec, [_found_nothing()])
        assert "invalid kind" in str(exc.value)

    def test_non_emit_safe_hyp_id_raises(self):
        # Finding B: a Spec hyp id with a LaTeX tokenization-special (%) is emitted RAW into
        # the surviving markup and would comment out the line -- the gate must REFUSE it
        # (fail loud) rather than escape it (escaping would break the emit==scan round-trip).
        spec = _spec(hyp_id="hyp%x")
        with pytest.raises(ValueError) as exc:
            novelty_scope_suffix("result", "hyp%x", spec, [_found_nothing(hyp_id="hyp%x")])
        msg = str(exc.value)
        assert "hyp%x" in msg and "emit-safe" in msg

    def test_emit_safe_hyp_ids_accepted(self):
        # Real ids use letters/digits and ._:- -> all emit-safe, gate passes (returns scope).
        for hid in ("hyp-001", "h1", "hyp_t1", "hyp.a", "hyp:b"):
            spec = _spec(hyp_id=hid)
            suffix = novelty_scope_suffix(
                "result", hid, spec, [_found_nothing(hyp_id=hid)]
            )
            assert suffix.startswith(" (to our knowledge, as of ")

    def test_other_kind_found_nothing_does_not_support(self):
        # A METHOD found_nothing must NOT support a RESULT novelty assertion (independence).
        spec = _spec(novelty_result=True, novelty_method=False)
        with pytest.raises(ValueError):
            novelty_scope_suffix(
                "result", "hyp-n", spec, [_found_nothing(kind="method")]
            )


# =========================================================================== #
# (N2) render_paper_latex -- the paper render gate                            #
# =========================================================================== #

class TestPaperNoveltyRender:
    def test_supported_survives_with_scope_and_newcommand(self):
        spec = _spec()
        prose = PaperProse(
            introduction=r"This is the \novelty{result}{hyp-n}{first encoding of Z}.",
        )
        tex = render_paper_latex(spec, [], evidence=[_found_nothing()], prose=prose)
        # The markup SURVIVES (not substituted away).
        assert r"\novelty{result}{hyp-n}{" in tex
        # The record-derived scope is baked into the text arg.
        assert "first encoding of Z (to our knowledge, as of 2026-06-18)" in tex
        # The preamble newcommand is emitted.
        assert NOVELTY_NEWCOMMAND in tex

    def test_unsupported_raises_at_render(self):
        spec = _spec()
        prose = PaperProse(
            introduction=r"We are \novelty{result}{hyp-n}{first}.",
        )
        with pytest.raises(ValueError) as exc:
            render_paper_latex(spec, [], evidence=[], prose=prose)  # no found_nothing
        assert "result-novelty for 'hyp-n'" in str(exc.value)

    def test_unknown_hypothesis_raises_at_render(self):
        spec = _spec()
        prose = PaperProse(introduction=r"\novelty{result}{ghost}{first}")
        with pytest.raises(ValueError) as exc:
            render_paper_latex(spec, [], evidence=[_found_nothing()], prose=prose)
        assert "unknown hypothesis" in str(exc.value)

    def test_bad_kind_raises_at_render(self):
        spec = _spec()
        prose = PaperProse(introduction=r"\novelty{methdo}{hyp-n}{first}")
        with pytest.raises(ValueError) as exc:
            render_paper_latex(spec, [], evidence=[_found_nothing()], prose=prose)
        assert "invalid kind" in str(exc.value)

    def test_inner_text_specials_escaped(self):
        # The inner text is FLAT prose -> a special (50%) is escaped; no nested \ref/\cite.
        spec = _spec()
        prose = PaperProse(
            introduction=r"\novelty{result}{hyp-n}{first with 50% gain}",
        )
        tex = render_paper_latex(spec, [], evidence=[_found_nothing()], prose=prose)
        assert r"50\% gain" in tex  # the % was escaped inside the novelty text

    def test_no_novelty_markup_no_newcommand(self):
        # The byte-identical invariant guard: a paper with NO novelty markup carries no
        # \newcommand{\novelty} (and a prose-with-ref path is otherwise unchanged).
        spec = _spec()
        prose = PaperProse(introduction=r"Plain prose, see \cite{Smith2020}.")
        tex = render_paper_latex(spec, [], evidence=[_found_nothing()], prose=prose)
        assert "novelty" not in tex
        assert r"\cite{Smith2020}" in tex  # the ref passthrough still works

    def test_prose_none_byte_identical(self):
        # prose=None must be byte-identical with and without the N2 wiring -- compare the
        # two renders (no novelty path can change a prose-less paper).
        spec = _spec()
        a = render_paper_latex(spec, [], evidence=[_found_nothing()], prose=None)
        b = render_paper_latex(spec, [], evidence=[], prose=None)
        assert a == b
        assert "novelty" not in a


# =========================================================================== #
# (N2) render_si_latex -- the SI render gate (same survive+scope+newcommand)   #
# =========================================================================== #

class TestSINoveltyRender:
    def test_si_supported_overview_survives_with_scope(self):
        spec = _spec()
        prose = SIProse(overview=r"As \novelty{result}{hyp-n}{first} shows.")
        tex = render_si_latex(spec, [], [_found_nothing()], prose=prose)
        assert r"\novelty{result}{hyp-n}{" in tex
        assert "first (to our knowledge, as of 2026-06-18)" in tex
        assert NOVELTY_NEWCOMMAND in tex

    def test_si_supported_notes_survives(self):
        spec = _spec()
        prose = SIProse(notes=r"Note: \novelty{result}{hyp-n}{first}.")
        tex = render_si_latex(spec, [], [_found_nothing()], prose=prose)
        assert "first (to our knowledge, as of 2026-06-18)" in tex
        assert NOVELTY_NEWCOMMAND in tex

    def test_si_unsupported_raises(self):
        spec = _spec()
        prose = SIProse(overview=r"\novelty{result}{hyp-n}{first}")
        with pytest.raises(ValueError):
            render_si_latex(spec, [], [], prose=prose)  # no found_nothing

    def test_si_no_novelty_byte_identical(self):
        # No novelty markup in SI prose -> byte-identical to the no-prose dump (invariant),
        # and no \newcommand{\novelty} is emitted. (The record dump legitimately prints the
        # NOVELTY_DECISION item's kind/provenance -- that is record content, not the macro.)
        spec = _spec()
        a = render_si_latex(spec, [], [_found_nothing()], prose=None)
        b = render_si_latex(spec, [], [_found_nothing()], prose=SIProse())
        assert a == b
        assert NOVELTY_NEWCOMMAND not in a


# =========================================================================== #
# helpers / unit: has_novelty_markup + SCAN regex vs the newcommand           #
# =========================================================================== #

class TestNoveltyMarkupDetection:
    def test_has_markup_true_false(self):
        assert has_novelty_markup(r"x \novelty{result}{h}{t} y") is True
        assert has_novelty_markup(r"plain prose \ref{fig:x}") is False

    def test_scan_does_not_match_newcommand(self):
        # The verify-side scan must NOT mistake the preamble \newcommand for an assertion.
        assert NOVELTY_SCAN_RE.search(NOVELTY_NEWCOMMAND) is None

    def test_find_unsupported_pure_scan(self):
        spec = _spec()
        # One supported + one unsupported assertion in raw tex.
        tex = (
            r"\novelty{result}{hyp-n}{a (to our knowledge, as of 2026-06-18)}"
            r" and \novelty{method}{hyp-n}{b}"
        )
        problems = find_unsupported_novelty(tex, spec, [_found_nothing(kind="result")])
        # result is supported (silent); method has no found_nothing -> one problem.
        assert len(problems) == 1
        assert "method-novelty for 'hyp-n'" in problems[0]

    def test_non_emit_safe_hyp_id_caught_by_verify_scan(self):
        # Finding B (verify side): a Spec hyp id with a tokenization-special (%) -- even with a
        # found_nothing on record (so it WOULD be SUPPORTED) -- is reported as a problem, so a
        # corrupting markup never passes sci-adk verify silently. (The render side raises;
        # this is the same re-derivation headless.)
        spec = _spec(hyp_id="hyp%x")
        tex = r"\novelty{result}{hyp%x}{first}"
        problems = find_unsupported_novelty(
            tex, spec, [_found_nothing(hyp_id="hyp%x")]
        )
        assert problems and "emit-safe" in problems[0]

    def test_non_emit_safe_hyp_id_raises_at_render(self):
        # Finding B (render side): the same id HARD-fails the paper render gate.
        spec = _spec(hyp_id="hyp%x")
        prose = PaperProse(introduction=r"\novelty{result}{hyp%x}{first}")
        with pytest.raises(ValueError) as exc:
            render_paper_latex(
                spec, [], evidence=[_found_nothing(hyp_id="hyp%x")], prose=prose
            )
        assert "emit-safe" in str(exc.value)


# =========================================================================== #
# (Finding C) whitespace-tolerant \novelty -- the tamper-boundary closure     #
# =========================================================================== #

class TestNoveltyWhitespaceTolerance:
    # LaTeX skips whitespace after the control word and between brace args, so each of these
    # expands via \newcommand{\novelty}[3]{#3} and PRINTS -- so the gate MUST see them too.
    # (Build the newline form with an explicit "\n" join so it is unambiguous in-source.)
    _SPACED_FORMS = [
        r"\novelty {result}{hyp-n}{first to show Z}",          # space after command
        "\\novelty\n{result}{hyp-n}{first to show Z}",          # newline after command
        r"\novelty{result} {hyp-n}{first to show Z}",           # space between args 1->2
        r"\novelty{result}{hyp-n} {first to show Z}",           # space between args 2->3
        r"\novelty  {result}  {hyp-n}  {first to show Z}",      # multiple spaces throughout
    ]

    def test_scan_catches_every_spaced_form(self):
        # The verify scan must capture (kind, hyp) from every whitespace-spaced form...
        for form in self._SPACED_FORMS:
            m = NOVELTY_SCAN_RE.search(form)
            assert m is not None, f"scan missed: {form!r}"
            assert (m.group(1), m.group(2)) == ("result", "hyp-n")

    def test_scan_still_rejects_newcommand_after_ws_tolerance(self):
        # The \s* must NOT let the preamble \newcommand{\novelty}[3]{#3} match (regression
        # guard for the tolerance change): after \novelty comes '}', and \s*\{ needs a '{'.
        assert NOVELTY_SCAN_RE.search(NOVELTY_NEWCOMMAND) is None

    def test_spaced_groups_do_not_leak_whitespace(self):
        # The \s* sit OUTSIDE the captured groups -> the id never gains stray whitespace
        # (which would make the verify re-scan's hyp_id mismatch the recorded id).
        m = NOVELTY_RENDER_RE.search(r"\novelty {result} {hyp-n} {first}")
        assert (m.group(1), m.group(2), m.group(3)) == ("result", "hyp-n", "first")

    def test_unsupported_spaced_form_caught_by_verify_scan(self):
        # The HOLE the finding describes: an unbacked spaced \novelty must be a PROBLEM (it
        # previously slipped past find_unsupported_novelty and verify went green).
        spec = _spec()
        for form in self._SPACED_FORMS:
            problems = find_unsupported_novelty(form, spec, [])  # no found_nothing
            assert problems, f"verify scan missed an unbacked spaced form: {form!r}"
            assert "result-novelty for 'hyp-n'" in problems[0]

    def test_unsupported_spaced_form_raises_at_render(self):
        # And the render gate (NOVELTY_RENDER_RE) HARD-fails on the unbacked spaced form too.
        spec = _spec()
        for form in self._SPACED_FORMS:
            prose = PaperProse(introduction=form)
            with pytest.raises(ValueError):
                render_paper_latex(spec, [], evidence=[], prose=prose)

    def test_supported_spaced_form_renders_with_scope(self):
        # A BACKED spaced \novelty renders fine -- the tolerance does not break the happy path.
        spec = _spec()
        prose = PaperProse(introduction=r"This is \novelty {result} {hyp-n} {first}.")
        tex = render_paper_latex(spec, [], evidence=[_found_nothing()], prose=prose)
        assert "first (to our knowledge, as of 2026-06-18)" in tex
        assert NOVELTY_NEWCOMMAND in tex


# =========================================================================== #
# (N3) verify gate -- end to end over a seeded run dir                        #
# =========================================================================== #

def _experiment_found_nothing(point: float, hyp_id: str = "hyp-n"):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-fn", spec_id=s.id, kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:result:found_nothing"),
                result=Result(type="qualitative", finding="result found_nothing"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id=hyp_id, kind="result"),
            ),
        ]
    return experiment


def _experiment_plain(point: float, hyp_id: str = "hyp-n"):
    """A supporting experiment WITHOUT any novelty decision -> the novelty claim stays
    PROPOSED (no prior-art search on record), which re-derives faithfully on verify."""
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
        ]
    return experiment


def _seed(workspace: Path, spec: Spec, experiment) -> Path:
    run_dir = workspace / "runs" / spec.id
    run_checkpoint_loop(
        run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=workspace
    )
    return run_dir


def _write_draft(run_dir: Path, body: str) -> None:
    """Render a real draft.tex with the given Introduction prose and write it to paper/."""
    spec = Spec.model_validate(
        json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    )
    evidence = [
        EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((run_dir / "evidence").glob("*.json"))
    ]
    tex = render_paper_latex(
        spec, [], evidence=evidence, prose=PaperProse(introduction=body)
    )
    paper_dir = run_dir / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "draft.tex").write_text(tex, encoding="utf-8")


def _freeze_minimal_pubreqs(run_dir: Path) -> None:
    """Freeze a minimal compliant pubreqs.json so the SPEC-PAPER-GATE-001 P1 refusal is
    silenced for a conclusion-bearing draft.tex (M1, OD-1 strict + OD-8 immediate)."""
    from sci_adk.core.pubreqs import PubReqs as _PubReqs
    from sci_adk.provenance import pubreqs_digest as _pubreqs_digest

    pr = _PubReqs(
        spec_id=run_dir.name, required_sections=[], figure_font_policy=False,
        image_min_dpi=None, reference_style=None, max_words=None,
        reproduction_bundle=False,
    )
    pr = pr.model_copy(update={"digest": _pubreqs_digest(pr)})
    (run_dir / "pubreqs.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")


class TestVerifyNoveltyGate:
    def test_supported_novelty_in_draft_passes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            spec = _spec()
            run_dir = _seed(ws, spec, _experiment_found_nothing(0.95))
            _write_draft(run_dir, r"This is \novelty{result}{hyp-n}{first}.")
            # M1 (SPEC-PAPER-GATE-001 P1): a draft.tex is conclusion-bearing -> freeze a minimal
            # publishing contract so the P1 refusal is silenced; this test targets the novelty
            # gate, and the draft prose carries no quantitative literal (number-audit clean).
            _freeze_minimal_pubreqs(run_dir)

            report = verify_run(run_dir)
            assert report.paper_novelty_clean is True
            assert report.paper_novelty_problems == {}
            assert report.passed is True

    def test_unsupported_novelty_in_draft_fails_even_when_claims_reproduce(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            spec = _spec()
            # Seed WITHOUT a found_nothing decision: the experiment supports hyp-n, but the
            # novelty claim is honestly PROPOSED (no prior-art search). Both the experiment
            # claim and the PROPOSED novelty claim re-derive faithfully -> all_reproduced True.
            run_dir = _seed(ws, spec, _experiment_plain(0.95))
            # Now hand-write a draft.tex that ASSERTS \novelty{result}{hyp-n} anyway -- the
            # exact tamper N3 guards (a render would have refused this; a hand-edited .tex must
            # not slip past verify). The assertion does NOT re-derive SUPPORTED (no
            # found_nothing on record), so the novelty gate must fail -- an independent
            # firewall: a paper asserting an unbacked priority FAILS even when claims reproduce.
            paper_dir = run_dir / "paper"
            paper_dir.mkdir(parents=True, exist_ok=True)
            (paper_dir / "draft.tex").write_text(
                "\\documentclass{article}\n"
                "\\newcommand{\\novelty}[3]{#3}\n"
                "\\begin{document}\n"
                "This is \\novelty{result}{hyp-n}{first}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )

            report = verify_run(run_dir)
            assert report.all_reproduced is True  # every recorded claim reproduces
            assert report.paper_novelty_clean is False  # the novelty gate fails...
            assert "draft.tex" in report.paper_novelty_problems
            assert report.passed is False  # ...and that alone fails the combined gate
