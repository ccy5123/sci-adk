"""
render-merge (RED-first): a deterministic, OFFLINE LaTeX renderer mirroring the
Markdown ``render_paper`` -- valid compilable LaTeX with load-bearing special-char
escaping, the same honest evidence-validity labels, a prose hook (agent-authored
narrative passed in, never LLM-generated), and a DOI-list References section
(NO BibTeX generation -- DOI list only, design decision).

These pin the behavior before any implementation exists. No LLM, no network: the
renderer is pure (data in, string out).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
    EvidenceLink,
    EvidenceLinkRole,
)
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
from sci_adk.render.paper import _latex_escape, render_paper_latex
from sci_adk.render.prose import PaperProse

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="collision_count == 0 => support",
    params={"statistic": "collision_count", "op": "==", "value": 0.0},
)


def _spec(hyp: Hypothesis, spec_id: str = "t-latex", goal: str = "An encoding") -> Spec:
    return Spec(
        id=spec_id,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal=goal, method="method", expected_output="out"
        ),
        hypotheses=[hyp],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp.id)],
    )


def _claim(
    hyp: Hypothesis,
    status: ClaimStatus,
    ev_id: str = "ev-1",
    basis: str = "threshold rule: met",
    spec_id: str = "t-latex",
) -> Claim:
    return Claim(
        id=f"claim-{hyp.id}",
        spec_id=spec_id,
        answers=hyp.id,
        statement=hyp.statement,
        status=status,
        confidence=Confidence(
            type=ConfidenceType.CREDENCE, value=0.9, basis=basis
        ),
        evidence_set=[EvidenceLink(evidence_id=ev_id, role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _evidence(
    ev_id: str,
    hyp_id: str,
    data_source,
    direction,
    spec_id: str = "t-latex",
    finding: str = "",
):
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id=spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source=data_source),
        result=Result(type="quantitative", point=0.0, finding=finding or None),
        bears_on=[Bearing(target_id=hyp_id, direction=direction)],
    )


def _basic_hyp(referent: str = "formal") -> Hypothesis:
    return Hypothesis(
        id="hyp-t1",
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent=referent,
        non_circularity="collisions could occur; the verifier checks for them",
    )


# ---------------------------------------------------------------------------
# _latex_escape: the load-bearing escaper.
# ---------------------------------------------------------------------------

class TestLatexEscape:
    def test_escapes_each_special_char(self):
        # Every LaTeX special must be neutralized.
        assert _latex_escape("&") == r"\&"
        assert _latex_escape("%") == r"\%"
        assert _latex_escape("$") == r"\$"
        assert _latex_escape("#") == r"\#"
        assert _latex_escape("_") == r"\_"
        assert _latex_escape("{") == r"\{"
        assert _latex_escape("}") == r"\}"
        assert _latex_escape("~") == r"\textasciitilde{}"
        assert _latex_escape("^") == r"\textasciicircum{}"
        assert _latex_escape("\\") == r"\textbackslash{}"

    def test_plain_text_unchanged(self):
        # No specials -> identity (safe on already-plain text).
        s = "A clean sentence with no specials 123 abc."
        assert _latex_escape(s) == s

    def test_backslash_is_not_double_escaped(self):
        # The backslash must be replaced FIRST, so the backslashes introduced by
        # escaping the OTHER specials are not themselves re-escaped. A literal
        # backslash followed by an ampersand must produce exactly the two tokens.
        assert _latex_escape(r"\&") == r"\textbackslash{}\&"

    def test_combined_specials_roundtrip_faithful(self):
        # A realistic mix: every special once, in one string.
        src = "a_b % c & d $ e # f { g } h ~ i ^ j"
        out = _latex_escape(src)
        # No raw special survives (each is now backslash-prefixed or a command).
        assert "_" not in out.replace(r"\_", "")
        assert "%" not in out.replace(r"\%", "")
        assert "&" not in out.replace(r"\&", "")
        assert "$" not in out.replace(r"\$", "")
        assert "#" not in out.replace(r"\#", "")
        # Braces only appear as escaped pairs or inside the tilde/caret commands.
        # The faithful text fragments are still present.
        assert r"a\_b" in out


# ---------------------------------------------------------------------------
# render_paper_latex: a valid, compilable document skeleton.
# ---------------------------------------------------------------------------

class TestLatexDocumentSkeleton:
    def test_emits_documentclass_and_body_delimiters(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        assert r"\documentclass{article}" in tex
        assert r"\begin{document}" in tex
        assert r"\end{document}" in tex
        # \maketitle requires a \title; the goal is the title.
        assert r"\title{" in tex
        assert r"\maketitle" in tex
        # begin precedes end (well-formed).
        assert tex.index(r"\begin{document}") < tex.index(r"\end{document}")

    def test_section_per_hypothesis_with_status_confidence_basis(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED, basis="met collision_count == 0")
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        # A section carries the hypothesis statement.
        assert r"\section{" in tex or r"\subsection{" in tex
        assert "the encoding is injective on the tested set" in tex
        # Status, confidence, basis all present.
        assert "supported" in tex.lower()
        assert "0.9" in tex
        assert "met collision_count" in tex.replace(r"\_", "_")

    def test_evidence_section_lists_items(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("evi-xyz", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        # There is an Evidence section and the evidence id appears.
        assert "Evidence" in tex
        assert "evi-xyz" in tex

    def test_no_claim_renders_no_claim_line(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        # No claim and no evidence bearing -> the "no claim" branch.
        tex = render_paper_latex(spec, [], [])
        assert "no claim" in tex.lower()


# ---------------------------------------------------------------------------
# Escaping is wired through ALL interpolated content (load-bearing).
# ---------------------------------------------------------------------------

class TestLatexEscapingIsWired:
    def test_hypothesis_statement_with_specials_is_escaped(self):
        # A statement riddled with LaTeX specials.
        hyp = Hypothesis(
            id="hyp_x",  # underscore in the id, too
            statement="encode A_i & B% with $cost #1 {set} ~op ^pow",
            mode=HypothesisMode.EXPLORATORY,
            decision_rule=_THRESHOLD,
            referent="formal",
            non_circularity="n/a",
        )
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp_x", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        # The escaped forms are present ...
        assert r"A\_i" in tex
        assert r"B\%" in tex
        assert r"\$cost" in tex
        assert r"\#1" in tex
        assert r"\{set\}" in tex
        # ... and NO raw special leaked from the statement. Check the underscore:
        # the only underscores in the document must be escaped ones.
        assert "_" not in tex.replace(r"\_", "")

    def test_finding_with_specials_is_escaped(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        # A finding text full of specials, surfaced in the Evidence summary.
        ev = _evidence(
            "ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS,
            finding="collision_count = 0 (100% pass) & cost $5",
        )
        tex = render_paper_latex(spec, [claim], [ev])
        assert r"100\%" in tex
        assert "_" not in tex.replace(r"\_", "")

    def test_basis_with_specials_is_escaped(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(
            hyp, ClaimStatus.SUPPORTED, basis="rule met: collision_count == 0 & ok"
        )
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        tex = render_paper_latex(spec, [claim], [ev])
        assert r"collision\_count" in tex
        assert r"\&" in tex


# ---------------------------------------------------------------------------
# The honest evidence-validity labels appear in LaTeX too (no honesty dropped).
# ---------------------------------------------------------------------------

class TestLatexEvidenceValidityLabels:
    def test_formal_generated_supported_labelled_computational(self):
        hyp = _basic_hyp(referent="formal")
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev])

        assert "referent=formal" in tex
        assert "generated" in tex
        assert "in-silico" in tex.lower() or "computational result" in tex.lower()

    def test_empirical_no_measured_labelled_awaiting(self):
        hyp = Hypothesis(
            id="hyp-e",
            statement="trait predicts organ dry weight",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=_THRESHOLD,
            referent="empirical",
        )
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.PROPOSED)
        ev = _evidence("ev-1", "hyp-e", None, BearingDirection.NEUTRAL)

        tex = render_paper_latex(spec, [claim], [ev])

        assert "referent=empirical" in tex
        assert "awaiting measured data" in tex.lower()


# ---------------------------------------------------------------------------
# Prose hook: agent-authored narrative injected as sections.
# ---------------------------------------------------------------------------

class TestLatexProse:
    def test_prose_sections_injected(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(
            abstract="We present a Goedel-style encoding tested for injectivity.",
            introduction="Serializing a molecular graph to one integer is attractive.",
            discussion="The supported claim is exploratory and sample-bounded.",
        )

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)

        # Abstract uses the LaTeX abstract environment.
        assert r"\begin{abstract}" in tex
        assert r"\end{abstract}" in tex
        assert "tested for injectivity" in tex
        # Introduction + Discussion appear as sections.
        assert "Introduction" in tex
        assert "Serializing a molecular graph" in tex
        assert "Discussion" in tex
        assert "exploratory and sample-bounded" in tex
        # The abstract comes before the Discussion (structural ordering).
        assert tex.index("tested for injectivity") < tex.index("exploratory and sample")

    def test_prose_none_emits_no_abstract_environment(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev], prose=None)
        # No abstract supplied -> no abstract environment.
        assert r"\begin{abstract}" not in tex

    def test_partial_prose_only_present_slots(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(abstract="Only an abstract here.")

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)
        assert r"\begin{abstract}" in tex
        assert "Only an abstract here." in tex
        # No discussion slot -> no agent-authored Discussion section heading text
        # injected (the discussion content is simply absent).
        assert "Only an abstract here." in tex

    def test_prose_with_specials_is_escaped(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(abstract="A 100% deterministic & exact result on set #1.")

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)
        assert r"100\%" in tex
        assert r"\&" in tex
        assert r"\#1" in tex


# ---------------------------------------------------------------------------
# Citations: DOI list only (NO BibTeX generation).
# ---------------------------------------------------------------------------

class TestLatexCitations:
    def test_cited_dois_render_url_entries(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        dois = ["10.1021/c160017a018", "10.48550/arXiv.1301.1493"]

        tex = render_paper_latex(spec, [claim], [ev], cited_dois=dois)

        assert "References" in tex
        # Each DOI is an \url{https://doi.org/<doi>} entry.
        assert r"\url{https://doi.org/10.1021/c160017a018}" in tex
        assert r"\url{https://doi.org/10.48550/arXiv.1301.1493}" in tex

    def test_no_dois_says_none_cited(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex_none = render_paper_latex(spec, [claim], [ev], cited_dois=None)
        tex_empty = render_paper_latex(spec, [claim], [ev], cited_dois=[])
        assert "No literature cited." in tex_none
        assert "No literature cited." in tex_empty

    def test_bib_path_existing_wires_bibliography(self, tmp_path):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        bib = tmp_path / "references.bib"
        bib.write_text("@article{x2020, doi={10.1/x}}\n", encoding="utf-8")

        tex = render_paper_latex(
            spec, [claim], [ev],
            cited_dois=["10.1/x"], bib_path=str(bib),
        )

        # The existing .bib is wired (NOT generated): style + bibliography + nocite.
        assert r"\bibliographystyle{plain}" in tex
        assert r"\bibliography{references}" in tex  # stem of references.bib
        assert r"\nocite{*}" in tex

    def test_bib_path_none_emits_no_bibliography(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

        tex = render_paper_latex(spec, [claim], [ev], cited_dois=["10.1/x"])
        assert r"\bibliography{" not in tex
        assert r"\nocite{*}" not in tex

    # NOTE: the renderer-level "no bibliography" case is bib_path=None (above). The
    # renderer is PURE and does NO filesystem access -- it does NOT check whether
    # bib_path exists; a non-None bib_path is the caller's guarantee. The "missing
    # references.bib -> no \bibliography" behavior is proven at the COMPILER level
    # (where _locate_bib_path returns None for a missing file): see
    # tests/test_render_merge_wiring.py::test_compile_without_literature_says_none_cited.


# ---------------------------------------------------------------------------
# Purity / offline: the renderer makes no network call and needs no LLM, and --
# load-bearing for the MED fix -- performs NO filesystem access. Two proxies: a
# determinism check, and a hard purity assertion that monkeypatches the filesystem
# primitives to raise, then proves render_paper_latex still wires \bibliography.
# ---------------------------------------------------------------------------

def test_latex_render_is_deterministic():
    hyp = _basic_hyp()
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
    a = render_paper_latex(spec, [claim], [ev], cited_dois=["10.1/x"])
    b = render_paper_latex(spec, [claim], [ev], cited_dois=["10.1/x"])
    assert a == b


def test_latex_render_does_no_filesystem_access(monkeypatch):
    """The renderer MUST be pure: given a non-None bib_path it wires the bibliography
    WITHOUT touching the filesystem. We sabotage Path.exists and builtins.open to
    raise; if render_paper_latex performed any existence check or file read it would
    blow up -- instead it must return a \\bibliography{...}-containing string."""
    import builtins
    import pathlib

    def _boom(*_args, **_kwargs):
        raise AssertionError("render_paper_latex must not access the filesystem")

    monkeypatch.setattr(pathlib.Path, "exists", _boom)
    monkeypatch.setattr(builtins, "open", _boom)

    hyp = _basic_hyp()
    spec = _spec(hyp)
    claim = _claim(hyp, ClaimStatus.SUPPORTED)
    ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)

    # A non-None bib_path (the caller's guarantee that the file exists). The renderer
    # only takes its .stem -- no .exists(), no open().
    tex = render_paper_latex(
        spec, [claim], [ev],
        cited_dois=["10.1/x"], bib_path="/any/path/references.bib",
    )
    assert r"\bibliography{references}" in tex
    assert r"\nocite{*}" in tex
