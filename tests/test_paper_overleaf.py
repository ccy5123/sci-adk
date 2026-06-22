"""
Overleaf-hardening (RED-first): the LaTeX paper output must compile on Overleaf's
default pdflatex *as-is*.

pdflatex-safety proxy (no LaTeX engine locally):
    There is NO LaTeX engine in this environment, so we cannot compile. The
    machine-checkable proxy for "Overleaf pdflatex compiles" is:

        every codepoint in the emitted .tex is either ASCII (< U+0080) OR an
        inputenc-safe accent in U+00C0..U+017E (Latin-1 Supplement + Latin
        Extended-A, the range ``\\usepackage[utf8]{inputenc}`` defines under
        pdflatex on TeX Live / Overleaf).

    Any other non-ASCII codepoint (a curated scientific symbol left un-mapped, Latin
    Extended-B which inputenc does NOT define -- Romanian Ș/Ț, ƒ, ... -- CJK, emoji,
    or a stray combining mark) would break pdflatex -- so its absence is the proxy
    assertion. See ``assert_pdflatex_safe`` below.

These pin behavior before implementation. No LLM, no network: the renderer is pure
(data in, string out) and the compiler does no acquisition.
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
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import PaperProse

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="collision_count == 0 => support",
    params={"statistic": "collision_count", "op": "==", "value": 0.0},
)

# The inputenc-safe accent window: Latin-1 Supplement (U+00C0..U+00FF) + Latin
# Extended-A (U+0100..U+017E). ``utf8`` inputenc on TeX Live / Overleaf defines this
# range, so author names like Gödel / Erdős (and ł U+0142, ø) pass through unchanged.
# Latin Extended-B (U+0180+) is NOT defined by inputenc -- it must NOT be in this
# window, or the proxy would wrongly bless a char that aborts pdflatex.
_ACCENT_LO = 0x00C0
_ACCENT_HI = 0x017E


def assert_pdflatex_safe(tex: str) -> None:
    """Assert ``tex`` contains no codepoint that would break Overleaf's pdflatex.

    The proxy (documented at module top): every char is ASCII, or an inputenc-safe
    accent in U+00C0..U+017E. Any other non-ASCII codepoint is a compile hazard.
    """
    bad = [
        ch
        for ch in tex
        if ord(ch) >= 0x80 and not (_ACCENT_LO <= ord(ch) <= _ACCENT_HI)
    ]
    assert not bad, (
        "pdflatex-unsafe codepoints leaked into the .tex: "
        + ", ".join(f"U+{ord(ch):04X} {ch!r}" for ch in sorted(set(bad)))
    )


def _spec(hyp: Hypothesis, spec_id: str = "t-overleaf", goal: str = "An encoding") -> Spec:
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
    spec_id: str = "t-overleaf",
) -> Claim:
    return Claim(
        id=f"claim-{hyp.id}",
        spec_id=spec_id,
        answers=hyp.id,
        statement=hyp.statement,
        status=status,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis=basis),
        evidence_set=[EvidenceLink(evidence_id=ev_id, role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )


def _evidence(
    ev_id: str,
    hyp_id: str,
    data_source,
    direction,
    spec_id: str = "t-overleaf",
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


def _basic_hyp(referent: str = "formal", statement: str | None = None) -> Hypothesis:
    return Hypothesis(
        id="hyp-t1",
        statement=statement or "the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent=referent,
        non_circularity="collisions could occur; the verifier checks for them",
    )


# A stress set spanning every region the sanitizer must handle: relations, an
# operator, an arrow, Greek, micro, a subscript, a degree sign, an em-dash, curly
# quotes, an ellipsis, preserved accents, and two exotics (a CJK char + an
# astral-plane mathematical letter) that must NOT survive raw.
_STRESS = "x ≥ y × z ∏ w → v α μ ₂ 30° — “q” … ü ö ő 漢 \U0001d54f"


class TestPdflatexSafetyProxy:
    """The master assertion: arbitrary unicode in Spec/Claim/Evidence + prose ->
    a .tex with only ASCII or inputenc-safe accents."""

    def test_unicode_stress_spec_claim_evidence_is_pdflatex_safe(self):
        hyp = _basic_hyp(statement=f"injective when {_STRESS}")
        spec = _spec(hyp, goal=f"Encode {_STRESS}")
        claim = _claim(hyp, ClaimStatus.SUPPORTED, basis=f"rule met {_STRESS}")
        ev = _evidence(
            "ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS,
            finding=f"result {_STRESS}",
        )

        tex = render_paper_latex(spec, [claim], [ev])

        assert_pdflatex_safe(tex)

    def test_unicode_stress_in_prose_is_pdflatex_safe(self):
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        prose = PaperProse(
            abstract=f"Abstract {_STRESS}",
            introduction=f"Intro {_STRESS}",
            discussion=f"Discussion {_STRESS}",
        )

        tex = render_paper_latex(spec, [claim], [ev], prose=prose)

        assert_pdflatex_safe(tex)


class TestUnicodeMap:
    """Specific curated maps land on the documented LaTeX-safe forms."""

    def _tex_with(self, text: str) -> str:
        # The reframed paper renders the agent's PROSE (not the hypothesis statement);
        # inject the unicode via the abstract prose, which is sanitized identically
        # (the prose sanitizer routes non-ref/cite text through _latex_sanitize).
        hyp = _basic_hyp()
        spec = _spec(hyp)
        claim = _claim(hyp, ClaimStatus.SUPPORTED)
        ev = _evidence("ev-1", "hyp-t1", "generated", BearingDirection.SUPPORTS)
        return render_paper_latex(
            spec, [claim], [ev], prose=PaperProse(abstract=text)
        )

    def test_geq_maps_to_math(self):
        tex = self._tex_with("a ≥ b")  # >=
        assert r"$\geq$" in tex

    def test_leq_maps_to_math(self):
        tex = self._tex_with("a ≤ b")  # <=
        assert r"$\leq$" in tex

    def test_neq_maps_to_math(self):
        tex = self._tex_with("a ≠ b")  # !=
        assert r"$\neq$" in tex

    def test_times_maps_to_math(self):
        tex = self._tex_with("a × b")  # multiplication sign
        assert r"$\times$" in tex

    def test_pm_maps_to_math(self):
        tex = self._tex_with("a ± b")  # plus-minus
        assert r"$\pm$" in tex

    def test_subscript_digit_maps_to_math(self):
        tex = self._tex_with("H₂O")  # subscript 2
        assert "H$_2$O" in tex

    def test_superscript_digit_maps_to_math(self):
        tex = self._tex_with("x²")  # superscript 2
        assert "x$^2$" in tex

    def test_alpha_maps_to_math(self):
        tex = self._tex_with("rate α here")  # alpha
        assert r"$\alpha$" in tex

    def test_capital_omega_maps_to_math(self):
        tex = self._tex_with("Ω ohms")  # capital Omega
        assert r"$\Omega$" in tex

    def test_mu_maps_to_math(self):
        # Both MICRO SIGN (U+00B5) and GREEK SMALL LETTER MU (U+03BC) -> $\mu$.
        assert r"$\mu$" in self._tex_with("µg")
        assert r"$\mu$" in self._tex_with("μg")

    def test_degree_maps_to_textdegree(self):
        tex = self._tex_with("30°C")  # degree sign
        assert r"\textdegree" in tex
        # And no raw degree codepoint survives.
        assert "°" not in tex

    def test_arrow_maps_to_math(self):
        tex = self._tex_with("a → b")  # right arrow
        assert r"$\rightarrow$" in tex

    def test_cdot_maps_to_math(self):
        tex = self._tex_with("a · b")  # middle dot
        assert r"$\cdot$" in tex

    def test_infinity_and_sum_and_prod_and_sqrt(self):
        assert r"$\infty$" in self._tex_with("∞")  # infinity
        assert r"$\sum$" in self._tex_with("∑")  # n-ary sum
        assert r"$\prod$" in self._tex_with("∏")  # n-ary product
        # √ -> $\surd$ (standalone radical; \sqrt{} would render a bare radical with
        # no radicand).
        assert r"$\surd$" in self._tex_with("√")

    def test_endash_and_emdash(self):
        assert "--" in self._tex_with("a – b")  # en dash
        assert "---" in self._tex_with("a — b")  # em dash

    def test_curly_quotes(self):
        tex = self._tex_with("“quoted”")  # curly double quotes
        assert "``quoted''" in tex

    def test_ellipsis(self):
        tex = self._tex_with("and so on…")  # horizontal ellipsis
        assert r"\ldots" in tex


class TestAccentsPreserved:
    """Author names with common European accents must survive verbatim (inputenc
    handles them under pdflatex) -- never folded to ASCII or a placeholder."""

    def test_godel_preserved(self):
        tex = TestUnicodeMap()._tex_with("a result by Gödel")  # Gödel
        assert "Gödel" in tex

    def test_erdos_preserved(self):
        tex = TestUnicodeMap()._tex_with("after Erdős")  # Erdős (Latin Ext-A)
        assert "Erdős" in tex

    def test_accents_still_pdflatex_safe(self):
        # Accents are inputenc-safe, so they pass the proxy.
        tex = TestUnicodeMap()._tex_with("Gödel, Erdős, ü é ñ")
        assert_pdflatex_safe(tex)

    def test_latin_ext_a_polish_l_and_o_slash_preserved(self):
        # ł (U+0142, Latin Extended-A) and ø (U+00F8, Latin-1 Supplement) are
        # inputenc-defined -> pass through unchanged (regression guard for the
        # lowered _ACCENT_HI: the boundary must still include all of Latin Ext-A).
        tex = TestUnicodeMap()._tex_with("Wałęsa studies ø-rings")
        assert "Wałęsa" in tex
        assert "ø-rings" in tex
        assert_pdflatex_safe(tex)


class TestLatinExtendedBFolded:
    """Latin Extended-B (U+0180+) is NOT defined by inputenc utf8 -- passing it raw
    aborts pdflatex. The lowered _ACCENT_HI (U+017E) must route it through the
    NFKD-fold/placeholder path, never emit it raw. (Assertion-of-fix for the HIGH.)"""

    def test_romanian_s_comma_is_folded_not_raw(self):
        # Ș U+0218 / ș U+0219 NFKD-fold to S / s (base letter + dropped comma-below).
        tex = TestUnicodeMap()._tex_with("Mateescu, Știință și Țară")  # Ș, Ț
        assert "Ș" not in tex  # Ș
        assert "ș" not in tex  # ș
        assert "Ț" not in tex  # Ț
        assert "ț" not in tex  # ț
        assert_pdflatex_safe(tex)

    def test_florin_sign_is_not_raw(self):
        # ƒ U+0192 (LATIN SMALL LETTER F WITH HOOK) has NO ASCII NFKD fold (it
        # decomposes to itself), so it becomes the placeholder -- the key point is it
        # is never emitted raw (which would abort pdflatex).
        tex = TestUnicodeMap()._tex_with("the ƒ function")
        assert "ƒ" not in tex  # ƒ
        assert "?" in tex
        assert_pdflatex_safe(tex)

    def test_ezh_with_no_ascii_fold_becomes_placeholder(self):
        # Ʒ U+01B7 (LATIN CAPITAL LETTER EZH) has no ASCII NFKD fold -> placeholder.
        tex = TestUnicodeMap()._tex_with("symbol Ʒ here")
        assert "Ʒ" not in tex  # Ʒ
        assert "?" in tex
        assert_pdflatex_safe(tex)

    def test_accent_boundary_u017e_kept_u0180_folded(self):
        # U+017E (ž, last char this whitelist keeps == _ACCENT_HI) is inputenc-safe
        # and kept raw; U+0180 (ƀ, first Latin Ext-B) is NOT defined by inputenc and
        # must be folded/placeholdered, never emitted raw.
        tex_kept = TestUnicodeMap()._tex_with("Dvořák wrote ž")  # ž U+017E
        assert "ž" in tex_kept
        assert_pdflatex_safe(tex_kept)
        tex_folded = TestUnicodeMap()._tex_with("letter ƀ here")  # ƀ U+0180
        assert "ƀ" not in tex_folded
        assert_pdflatex_safe(tex_folded)


class TestExoticFoldedToPlaceholder:
    """A codepoint that is neither curated nor an inputenc-safe accent must be folded
    (NFKD) and, if still non-ASCII, replaced with a safe placeholder -- never left raw."""

    def test_cjk_becomes_placeholder(self):
        tex = TestUnicodeMap()._tex_with("the char 漢 here")  # CJK 'Han'
        assert "漢" not in tex
        assert "?" in tex
        assert_pdflatex_safe(tex)

    def test_astral_math_letter_becomes_placeholder(self):
        # U+1D54F MATHEMATICAL DOUBLE-STRUCK CAPITAL X: NFKD folds it to ASCII 'X'.
        tex = TestUnicodeMap()._tex_with("platform \U0001d54f rocks")
        assert "\U0001d54f" not in tex
        assert_pdflatex_safe(tex)

    def test_emoji_becomes_placeholder(self):
        tex = TestUnicodeMap()._tex_with("great \U0001f389 result")  # party popper
        assert "\U0001f389" not in tex
        assert "?" in tex
        assert_pdflatex_safe(tex)


class TestSanitizerComposesWithEscape:
    """The unicode net must compose with the existing LaTeX special-char escaping --
    a string mixing specials AND unicode stays both escaped and pdflatex-safe."""

    def test_specials_and_unicode_together(self):
        tex = TestUnicodeMap()._tex_with("cost_n ≥ 50% & α #1")
        # LaTeX specials still escaped ...
        assert r"cost\_n" in tex
        assert r"50\%" in tex
        assert r"\&" in tex
        assert r"\#1" in tex
        # ... unicode still mapped ...
        assert r"$\geq$" in tex
        assert r"$\alpha$" in tex
        # ... and no raw underscore / non-ASCII leaked.
        assert "_" not in tex.replace(r"\_", "")
        assert_pdflatex_safe(tex)
