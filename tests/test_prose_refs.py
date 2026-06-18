"""
Prose-slot ref/cite passthrough: ``_latex_sanitize_prose`` and its end-to-end effect.

The gap this closes: the LaTeX renderer routes EVERY interpolated string -- including the
``PaperProse`` / ``SIProse`` narrative slots -- through ``_latex_sanitize``, which escapes
``\\ref{fig:x}`` to literal text. So the body-order figure numbering
(:func:`order_figures_by_reference`, which scans the rendered body for ``\\ref{fig:<id>}``)
NEVER saw a real ref authored in prose and silently fell back to supply order. The fix is
a PROSE-ONLY sanitizer that preserves an EXACT allowlist of reference/citation commands
(``\\ref`` ``\\eqref`` ``\\autoref`` ``\\cite`` ``\\citep`` ``\\citet``) verbatim while
escaping everything else.

Coverage here:
  - the sanitizer unit (allowlist preserved verbatim; specials around them still escaped;
    non-allowlisted commands escaped; underscore inside a key NOT escaped; unicode net
    still applies; deterministic);
  - the non-prose path is UNCHANGED (a no-prose draft is byte-identical to before);
  - END-TO-END (the payoff): a prose ``\\ref{fig:beta}`` before ``\\ref{fig:alpha}`` makes
    the body carry real refs, so numbering is driven by BODY reference order, not supply
    order -- proven both at the renderer (order_figures_by_reference) and through the
    compiler (the co-located ``paper/figures/fig1<ext>`` is beta's image);
  - the within-document consistency gate now SEES prose refs: a valid prose ref resolves,
    a dangling one is caught (so ``sci-adk verify`` would fail).

PURE: data in, string out -- no filesystem (except the compiler end-to-end test's tmp
images), no LLM, no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from sci_adk.render.consistency import check_latex_ref_consistency
from sci_adk.render.figures import (
    ImageFigureSpec,
    order_figures_by_reference,
    render_image_figure,
)
from sci_adk.render.paper import (
    _latex_sanitize,
    _latex_sanitize_prose,
    render_paper_latex,
)
from sci_adk.render.prose import PaperProse

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="point >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)


# ---------------------------------------------------------------------------
# _latex_sanitize_prose: the allowlist-preserving prose sanitizer.
# ---------------------------------------------------------------------------

class TestLatexSanitizeProse:
    def test_ref_preserved_verbatim(self):
        # A figure cross-reference passes through unchanged (NOT escaped to literal text).
        assert _latex_sanitize_prose(r"see \ref{fig:x}") == r"see \ref{fig:x}"

    def test_each_allowlisted_command_preserved(self):
        # Every member of the allowlist survives verbatim.
        for cmd, arg in [
            ("ref", "fig:x"),
            ("eqref", "eq:1"),
            ("autoref", "sec:intro"),
            ("cite", "Smith2020"),
            ("citep", "a,b"),
            ("citet", "Doe2019"),
        ]:
            span = f"\\{cmd}{{{arg}}}"
            assert _latex_sanitize_prose(f"x {span} y") == f"x {span} y"

    def test_citep_multikey_preserved(self):
        # A multi-key cite (comma-separated keys) is a single allowlisted span.
        assert _latex_sanitize_prose(r"prior work \citep{a,b}") == r"prior work \citep{a,b}"

    def test_eqref_preserved(self):
        assert _latex_sanitize_prose(r"by \eqref{eq:1}") == r"by \eqref{eq:1}"

    def test_underscore_inside_key_not_escaped(self):
        # The label/key inside the span is a reference KEY -- an underscore there must
        # survive as ``_`` for \ref to resolve, NOT become ``\_``.
        assert _latex_sanitize_prose(r"\ref{fig:a_b}") == r"\ref{fig:a_b}"
        assert _latex_sanitize_prose(r"\cite{Smith_2020}") == r"\cite{Smith_2020}"

    def test_stray_specials_around_refs_still_escaped(self):
        # Specials OUTSIDE a preserved span are still escaped (prose cannot break
        # compilation outside the allowlist).
        out = _latex_sanitize_prose(r"50% gain & \ref{fig:x} for $X$ with a_b")
        assert r"\ref{fig:x}" in out          # the ref survived
        assert r"\%" in out                    # % escaped
        assert r"\&" in out                    # & escaped
        assert r"\$" in out                    # $ escaped
        assert r"a\_b" in out                  # underscore OUTSIDE the span escaped
        # No raw special leaked (other than the preserved ref's own braces/backslash).
        leftover = out.replace(r"\ref{fig:x}", "")
        assert "%" not in leftover.replace(r"\%", "")
        assert "&" not in leftover.replace(r"\&", "")
        assert "$" not in leftover.replace(r"\$", "")

    def test_non_allowlisted_command_is_escaped(self):
        # A command NOT on the allowlist is the safety boundary: it becomes literal text.
        out = _latex_sanitize_prose(r"\textbf{x}")
        assert r"\ref" not in out  # sanity: it is not a ref
        assert out == r"\textbackslash{}textbf\{x\}"

    def test_input_command_escaped_not_passed_through(self):
        # \input is dangerous (file include) and NOT on the allowlist -> escaped.
        out = _latex_sanitize_prose(r"\input{secret.tex}")
        assert out == r"\textbackslash{}input\{secret.tex\}"

    def test_unicode_safety_net_still_applies_outside_spans(self):
        # A stray scientific unicode char in the surrounding text is still folded.
        out = _latex_sanitize_prose(r"gain \ref{fig:x} of ≥ 5")
        assert r"\ref{fig:x}" in out
        assert r"$\geq$" in out  # the unicode safety net mapped >=

    def test_deterministic(self):
        s = r"see \ref{fig:x} and \cite{a,b}; 50% of $X$ at a_b \autoref{sec:y}"
        assert _latex_sanitize_prose(s) == _latex_sanitize_prose(s)

    def test_no_passthrough_equals_plain_sanitize(self):
        # Prose with NO allowlisted command must sanitize identically to the plain path
        # (the prose variant only DIVERGES when a ref/cite is present).
        s = r"A 50% gain & a_b with $X$ and \textbf{bold}."
        assert _latex_sanitize_prose(s) == _latex_sanitize(s)

    def test_collision_proof_by_construction(self):
        # The split-and-stitch keeps preserved spans OUT of the escaper, so even a
        # (corrupted) NUL-bearing input cannot collide with anything; the gap is sanitized
        # (NUL bytes stripped by the inner _latex_sanitize) and the ref still survives.
        out = _latex_sanitize_prose("\x00\x01 see " + r"\ref{fig:x}")
        assert r"\ref{fig:x}" in out
        assert "\x00" not in out and "\x01" not in out


# ---------------------------------------------------------------------------
# Non-prose / no-prose: the renderer output is UNCHANGED.
# ---------------------------------------------------------------------------

def _basic_hyp() -> Hypothesis:
    return Hypothesis(
        id="hyp-1",
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent="formal",
        non_circularity="collisions could occur; the verifier checks for them",
    )


def _spec() -> Spec:
    hyp = _basic_hyp()
    return Spec(
        id="t-prose-refs",
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="An encoding", method="method", expected_output="out"
        ),
        hypotheses=[hyp],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp.id)],
    )


def _claim() -> Claim:
    hyp = _basic_hyp()
    return Claim(
        id="claim-1",
        spec_id="t-prose-refs",
        answers="hyp-1",
        statement=hyp.statement,
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(
            type=ConfidenceType.CREDENCE, value=0.9, basis="threshold rule: met"
        ),
        evidence_set=[EvidenceLink(evidence_id="ev-1", role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        id="ev-1",
        created_at=_T0,
        spec_id="t-prose-refs",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
    )


def test_no_prose_latex_is_byte_identical_regression():
    """The keystone regression lock: a draft with NO prose must be byte-identical to the
    pre-change skeleton. The prose-only sanitizer touches ONLY prose slots; every other
    interpolation (titles/ids/statements/findings/rules) stays on the fully-escaping
    ``_latex_sanitize``, so structural/data output cannot move."""
    spec, claim, ev = _spec(), _claim(), _evidence()
    old = render_paper_latex(spec, [claim], [ev])  # no prose, no figures
    new = render_paper_latex(spec, [claim], [ev], prose=None)
    assert new == old, "no-prose LaTeX output must not change"


def test_prose_ref_reaches_body_as_real_latex():
    # A \ref authored in a prose slot now appears as a REAL \ref in the rendered body
    # (no longer escaped to \textbackslash{}ref...).
    spec, claim, ev = _spec(), _claim(), _evidence()
    prose = PaperProse(discussion=r"As shown in \ref{fig:beta}, the trend holds.")
    tex = render_paper_latex(spec, [claim], [ev], prose=prose)
    assert r"\ref{fig:beta}" in tex
    assert r"\textbackslash{}ref" not in tex  # NOT escaped


# ---------------------------------------------------------------------------
# END-TO-END (renderer): prose \ref drives body-order figure numbering.
# ---------------------------------------------------------------------------

def _image(fig_id: str, path: str) -> ImageFigureSpec:
    return ImageFigureSpec(kind="image", id=fig_id, caption="A diagram.", image=path)


def test_prose_ref_order_drives_figure_numbering_at_renderer():
    """The payoff at the renderer boundary: prose discussion \\ref's fig:beta then
    fig:alpha; figures supplied [alpha, beta]. The rendered body now carries real refs, so
    order_figures_by_reference assigns beta=Figure 1, alpha=Figure 2 -- BODY reference
    order, NOT supply order -- and render_image_figure emits the matching fig<N> path."""
    spec, claim, ev = _spec(), _claim(), _evidence()
    figures = [_image("alpha", "alpha.png"), _image("beta", "beta.png")]
    prose = PaperProse(
        discussion=r"First \ref{fig:beta}, then \ref{fig:alpha}."
    )
    tex = render_paper_latex(spec, [claim], [ev], prose=prose, figures=figures)

    # The Figures section is emitted in body-reference order; the body up to that section
    # is the canonical ref text. Re-derive the SAME ordering the renderer used.
    body_before_figures = tex.split(r"\section{Figures}")[0]
    ordered = order_figures_by_reference(figures, body_before_figures)
    assert [(n, f.id) for n, f in ordered] == [(1, "beta"), (2, "alpha")]

    # The image renderer names each file by the body-reference number: beta -> fig1.
    assert "{figures/fig1.png}" in render_image_figure(ordered[0][1], ordered[0][0])
    assert "{figures/fig2.png}" in render_image_figure(ordered[1][1], ordered[1][0])
    # Both semantic labels survive so the body's \ref resolves.
    assert r"\label{fig:alpha}" in tex and r"\label{fig:beta}" in tex


# ---------------------------------------------------------------------------
# The within-document consistency gate now sees prose refs.
# ---------------------------------------------------------------------------

def test_consistency_gate_resolves_valid_prose_ref():
    # A prose \ref to a REAL figure id resolves: the figure's \label is in the same doc.
    spec, claim, ev = _spec(), _claim(), _evidence()
    figures = [_image("beta", "beta.png")]
    prose = PaperProse(discussion=r"See \ref{fig:beta}.")
    tex = render_paper_latex(spec, [claim], [ev], prose=prose, figures=figures)
    report = check_latex_ref_consistency(tex)
    assert "fig:beta" not in report.unresolved_refs
    assert report.ok is True


def test_consistency_gate_catches_dangling_prose_ref():
    # A prose \ref to a NON-existent figure is now caught (it used to be escaped, so the
    # gate never saw it). sci-adk verify would fail on this.
    spec, claim, ev = _spec(), _claim(), _evidence()
    figures = [_image("beta", "beta.png")]
    prose = PaperProse(discussion=r"See \ref{fig:typo}.")  # no fig:typo exists
    tex = render_paper_latex(spec, [claim], [ev], prose=prose, figures=figures)
    report = check_latex_ref_consistency(tex)
    assert "fig:typo" in report.unresolved_refs
    assert report.ok is False
