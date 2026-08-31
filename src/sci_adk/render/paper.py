"""
Render a paper draft (Markdown) from a Spec + its Claims + Evidence.

This is the *deterministic* renderer: it lays out the proposal, the per-hypothesis
findings (the Claims the DecisionEngine produced), the evidence trail, and any
pending agent judgments -- as a structured draft, with NO LLM prose (so it runs
at zero cost, design/tool-policy.md). Prose polishing, when wanted, is a separate
in-session agent step over this draft (never an autonomous claude -p call).

LaTeX-authoring convention (the ``.tex`` is the source of truth): the Spec proposal
panes, the hypothesis statements, and ``PaperProse`` (abstract/introduction/
discussion) should be authored in **LaTeX-safe form** -- e.g. ``$\\geq$``,
``H$_2$O``, ``30\\textdegree{}C`` -- NOT unicode, because the emitted document is
what the author uploads to Overleaf (default pdflatex). A lightweight unicode
sanitizer (:func:`_latex_sanitize`) is a *safety net*, not a license to rely on
unicode: a stray ``≥`` or ``α`` is mapped to a pdflatex-safe LaTeX command, common
European accents (Gödel, Erdős) pass through unchanged under ``utf8`` inputenc, and
any other non-ASCII codepoint (CJK, emoji) is folded/placeheld so it cannot break
compilation. Author LaTeX-safe; the net only guards against accidents.

Reference: design/directory-structure.md (render/), design/abstractions.md.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.claim import Claim, ClaimStatus, ConfidenceType
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import Hypothesis, Spec
from sci_adk.render.factref import substitute_factrefs
from sci_adk.render.figures import (
    AnyFigure,
    order_figures_by_reference,
    render_figure,
)
from sci_adk.render.novelty import (
    NOVELTY_NEWCOMMAND,
    NOVELTY_RENDER_RE,
    has_novelty_markup,
    novelty_scope_suffix,
)
from sci_adk.render.prose import PaperProse

# LaTeX special characters and their escaped forms. Several replacements (the
# backslash and the tilde/caret commands) themselves contain ``{}`` -- so a naive
# left-to-right ``str.replace`` per char corrupts them (escaping ``\`` first injects
# ``{}`` that the later ``{``/``}`` passes then re-escape). ``_latex_escape`` avoids
# this with a placeholder phase: each special maps to a brace-free sentinel first,
# then every sentinel is expanded to its final form in one last pass.
_LATEX_SPECIALS: list[tuple[str, str]] = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]

# A sentinel per special whose characters are NONE of the LaTeX specials, so it
# survives every replacement pass untouched. The sentinels use NUL-range bytes
# (\x00..\x01); ``_latex_escape`` STRIPS those bytes from its input before the
# sentinel phase (see below), making their absence a hard invariant rather than an
# assumption -- a corrupted NUL-bearing string can never collide with a sentinel and
# inject a spurious ``\textbackslash``.
_LATEX_SENTINELS: list[tuple[str, str, str]] = [
    (char, f"\x00{i}\x01", replacement)
    for i, (char, replacement) in enumerate(_LATEX_SPECIALS)
]


def _latex_escape(s: str) -> str:
    """Escape LaTeX special characters in ``s`` so interpolated content is faithful.

    Routes ``& % $ # _ { } ~ ^ \\`` to their LaTeX-safe forms via a two-phase
    placeholder substitution: each special is first mapped to a brace-free sentinel
    (so the braces inside ``\\textbackslash{}`` / ``\\textasciitilde{}`` etc. are not
    themselves re-escaped), then every sentinel is expanded to its final command in
    one pass. Plain text with no specials is returned unchanged, and a literal
    backslash followed by another special escapes faithfully
    (``\\&`` -> ``\\textbackslash{}\\&``, never a corrupted ``\\textbackslash\\{\\}``).

    Call exactly once per string at interpolation time; NOT idempotent -- never
    pre-escape (a second pass would turn ``\\&`` into ``\\textbackslash{}\\&``).

    This is load-bearing: EVERY interpolated string in the LaTeX output (titles,
    statements, rule expressions, findings, basis text, ids) MUST pass through here
    or the emitted .tex will not compile (or will silently corrupt content).
    """
    # Strip the sentinel bytes from the input first, so a (corrupted) NUL-bearing
    # string cannot collide with a sentinel and inject a spurious command. This turns
    # the sentinels' "absent from content" assumption into a hard invariant.
    s = s.replace("\x00", "").replace("\x01", "")
    for char, sentinel, _final in _LATEX_SENTINELS:
        s = s.replace(char, sentinel)
    for _char, sentinel, final in _LATEX_SENTINELS:
        s = s.replace(sentinel, final)
    return s


# Curated unicode -> pdflatex-safe LaTeX. The primary strategy is "author LaTeX-safe"
# (the .tex is the source of truth); this map is the SAFETY NET so a stray scientific
# unicode char does not break Overleaf's default pdflatex. Math symbols use
# ``$...$`` (base LaTeX -- no amssymb needed for any entry here). Applied AFTER
# :func:`_latex_escape`, so the values here are final LaTeX and the ASCII keys are
# disjoint from the LaTeX specials the escaper handles.
_UNICODE_MAP: dict[str, str] = {
    # Subscripts 0-9 -> $_n$.
    "₀": "$_0$", "₁": "$_1$", "₂": "$_2$", "₃": "$_3$",
    "₄": "$_4$", "₅": "$_5$", "₆": "$_6$", "₇": "$_7$",
    "₈": "$_8$", "₉": "$_9$",
    # Superscripts -> $^n$ (the common digits/sign; 1/2/3 have legacy codepoints).
    "⁰": "$^0$", "¹": "$^1$", "²": "$^2$", "³": "$^3$",
    "⁴": "$^4$", "⁵": "$^5$", "⁶": "$^6$", "⁷": "$^7$",
    "⁸": "$^8$", "⁹": "$^9$", "⁺": "$^+$", "⁻": "$^-$",
    "ⁿ": "$^n$",
    # Relations / operators.
    "≥": r"$\geq$", "≤": r"$\leq$", "≠": r"$\neq$",
    "±": r"$\pm$", "×": r"$\times$", "÷": r"$\div$",
    "≈": r"$\approx$", "≡": r"$\equiv$", "∝": r"$\propto$",
    "·": r"$\cdot$", "∙": r"$\cdot$",
    # Big operators / analysis.
    "∞": r"$\infty$", "∑": r"$\sum$", "∏": r"$\prod$",
    "∫": r"$\int$", "√": r"$\surd$", "∂": r"$\partial$",
    "∇": r"$\nabla$",
    # Set relations.
    "∈": r"$\in$", "∉": r"$\notin$", "⊂": r"$\subset$",
    "⊆": r"$\subseteq$", "∪": r"$\cup$", "∩": r"$\cap$",
    # Arrows.
    "→": r"$\rightarrow$", "←": r"$\leftarrow$",
    "↔": r"$\leftrightarrow$", "⇒": r"$\Rightarrow$",
    "⇐": r"$\Leftarrow$",
    # Greek lowercase alpha..omega.
    "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$",
    "δ": r"$\delta$", "ε": r"$\epsilon$", "ζ": r"$\zeta$",
    "η": r"$\eta$", "θ": r"$\theta$", "ι": r"$\iota$",
    "κ": r"$\kappa$", "λ": r"$\lambda$", "μ": r"$\mu$",
    "ν": r"$\nu$", "ξ": r"$\xi$", "ο": "o",
    "π": r"$\pi$", "ρ": r"$\rho$", "σ": r"$\sigma$",
    "ς": r"$\varsigma$", "τ": r"$\tau$", "υ": r"$\upsilon$",
    "φ": r"$\phi$", "χ": r"$\chi$", "ψ": r"$\psi$",
    "ω": r"$\omega$",
    # Greek uppercase Alpha..Omega (the ones with distinct LaTeX commands; the rest
    # look like Latin capitals and fold cleanly via NFKD if they ever appear).
    "Γ": r"$\Gamma$", "Δ": r"$\Delta$", "Θ": r"$\Theta$",
    "Λ": r"$\Lambda$", "Ξ": r"$\Xi$", "Π": r"$\Pi$",
    "Σ": r"$\Sigma$", "Φ": r"$\Phi$", "Ψ": r"$\Psi$",
    "Ω": r"$\Omega$",
    # Micro sign + degree.
    "µ": r"$\mu$", "°": r"\textdegree{}",
    # Dashes, quotes, ellipsis.
    "–": "--", "—": "---",
    "‘": "`", "’": "'", "“": "``", "”": "''",
    "…": r"\ldots{}",
}

# The inputenc-safe accent window. ``\usepackage[utf8]{inputenc}`` (TeX Live /
# Overleaf) only defines codepoints up to ~U+017E -- the end of Latin Extended-A --
# so this window covers Latin-1 Supplement (U+00C0..U+00FF) + Latin Extended-A
# (U+0100..U+017E). These pass through unchanged under pdflatex, so common European
# accents stay correct (Gödel, Erdős, ł U+0142, ø). Latin Extended-B and above
# (U+0180..U+024F: Romanian Ș U+0218 / Ț U+021A, ƒ U+0192, etc.) are NOT defined by
# inputenc and would abort pdflatex if passed raw, so they fall through to the
# NFKD-fold/placeholder path instead (Ș->S, Ț->T; ƒ and Ʒ have no ASCII fold -> ?).
_ACCENT_LO = 0x00C0
_ACCENT_HI = 0x017E

# Replacement for a non-ASCII codepoint that is neither curated nor an inputenc-safe
# accent and does not NFKD-fold to ASCII (e.g. CJK, emoji): a safe placeholder so the
# document still compiles. ``?`` is ASCII and not a LaTeX special.
_UNICODE_PLACEHOLDER = "?"


def _latex_sanitize(s: str) -> str:
    """Escape LaTeX specials AND fold unicode to pdflatex-safe LaTeX (the safety net).

    Two-phase, order-critical:

    1. :func:`_latex_escape` first -- neutralizes the ASCII specials
       ``& % $ # _ { } ~ ^ \\`` while ``s`` is still raw (no LaTeX commands of ours
       present yet, so nothing we emit later gets double-escaped).
    2. Then, per remaining character: a curated scientific symbol maps to its LaTeX
       form via :data:`_UNICODE_MAP` (e.g. ``≥`` -> ``$\\geq$``, ``₂`` -> ``$_2$``,
       ``α`` -> ``$\\alpha$``); an inputenc-safe accent (U+00C0..U+017E, e.g. ``ö``)
       passes through unchanged; any other non-ASCII codepoint -- including Latin
       Extended-B (U+0180+, e.g. Romanian ``Ș``/``Ț``) which inputenc does NOT define
       -- is NFKD-normalized with combining marks stripped, and if STILL non-ASCII
       (CJK, emoji) is replaced with :data:`_UNICODE_PLACEHOLDER`. ASCII passes
       through (it survived phase 1 as-is).

    Result: every codepoint is ASCII or an inputenc-safe accent, so the emitted .tex
    compiles under Overleaf's default pdflatex. This is a fallback -- author LaTeX-safe
    (the module docstring's convention); do not rely on the net for correctness.

    Replaces :func:`_latex_escape` at EVERY interpolation point in the LaTeX renderer.
    Like ``_latex_escape`` it is NOT idempotent -- call exactly once per string.
    """
    escaped = _latex_escape(s)
    out: list[str] = []
    for ch in escaped:
        cp = ord(ch)
        if cp < 0x80:
            out.append(ch)
            continue
        mapped = _UNICODE_MAP.get(ch)
        if mapped is not None:
            out.append(mapped)
            continue
        if _ACCENT_LO <= cp <= _ACCENT_HI:
            # Common European accent: inputenc renders it under pdflatex. Keep it.
            out.append(ch)
            continue
        # Fold via NFKD (drops combining marks); keep ASCII fallout (e.g. an
        # astral-plane math letter folds to its base Latin letter), placehold the rest.
        folded = unicodedata.normalize("NFKD", ch)
        for f in folded:
            if ord(f) < 0x80:
                out.append(f)
            elif unicodedata.combining(f):
                continue  # drop combining marks
            else:
                out.append(_UNICODE_PLACEHOLDER)
    return "".join(out)


# The EXACT allowlist of LaTeX cross-reference / citation commands that
# :func:`_latex_sanitize_prose` lets through verbatim. Each is of the form
# ``\cmd{...}`` where ``{...}`` is a SINGLE label/key argument with NO nested braces
# (``fig:water``, ``Smith2020``, ``a,b``) -- exactly what an author writes to reference
# a figure or cite a paper. The allowlist is closed and deliberately tiny: it is the
# ONLY LaTeX that survives a prose slot. A non-allowlisted command (``\textbf{...}``,
# ``\input{...}``) and every stray special (``&`` ``%`` ``_`` ``$``) stay escaped, so
# prose can never inject arbitrary LaTeX or break compilation outside this set.
#
# The regex matches the command name then a brace group with no inner ``{`` / ``}``
# (``[^{}]*`` -- a key never contains braces; an empty arg ``\ref{}`` is matched too so
# it is preserved rather than half-escaped). ``\b``-free by construction: the command
# names are immediately followed by ``{`` so ``\reference{}`` is NOT matched (the name
# alternation requires the literal ``{`` next).
_PROSE_PASSTHROUGH_RE = re.compile(
    r"\\(?:ref|eqref|autoref|cite|citep|citet)\{[^{}]*\}"
)


def _latex_sanitize_prose(s: str) -> str:
    """Sanitize an agent-authored PROSE slot, PRESERVING ref/cite commands verbatim.

    The prose-only variant of :func:`_latex_sanitize`. Every prose slot
    (``PaperProse`` abstract/introduction/discussion, ``SIProse`` overview/notes) is the
    one place an author legitimately writes real LaTeX: ``\\ref{fig:<id>}`` to point at a
    figure and ``\\cite{<key>}`` to cite literature. The plain ``_latex_sanitize`` would
    escape those to literal text (``\\ref{fig:x}`` -> ``\\textbackslash{}ref\\{fig:x\\}``),
    which is why the body-order figure numbering (:func:`figures.order_figures_by_reference`,
    which scans the body for ``\\ref{fig:<id>}``) silently fell back to supply order --
    it never saw a real ref. This function closes that gap by letting EXACTLY the six
    allowlisted commands (:data:`_PROSE_PASSTHROUGH_RE`) through unchanged while still
    fully sanitizing everything else.

    Implementation: a SPLIT-and-stitch (collision-proof BY CONSTRUCTION -- no placeholder
    that could collide with content, and nothing of ours is routed back through the
    escaper). :func:`re.Match`/:func:`re.split`-style alternation walks ``s`` and carves it
    into segments separated by the allowlisted spans; only the SEGMENTS between/around the
    spans pass through the EXISTING :func:`_latex_sanitize` (specials escaped + unicode
    folded exactly as the non-prose path), while each allowlisted span is concatenated back
    VERBATIM. The label/key INSIDE ``{...}`` is therefore never escaped: it is a reference
    key (``fig:a_b``, ``Smith2020``), so an underscore there survives as ``_`` for the
    ``\\ref`` to resolve, not become ``\\_``.

    Why split rather than the sentinel trick :func:`_latex_escape` uses: ``_latex_escape``
    (called inside ``_latex_sanitize``) STRIPS the ``\\x00``/``\\x01`` sentinel bytes from
    its input as a hard collision-proofing invariant, so a placeholder routed THROUGH it
    would be destroyed. Splitting keeps the preserved spans entirely OUT of the escaper's
    path -- the same collision-proofing goal, reached without fighting that invariant.

    Safety boundary: ONLY the allowlist passes. A non-allowlisted command stays escaped
    (``\\textbf{x}`` -> literal ``\\textbackslash{}textbf\\{x\\}``) and a stray ``&`` / ``%``
    outside a preserved span is still escaped -- so prose cannot smuggle arbitrary LaTeX
    or unbalanced specials past the renderer.

    PURE + deterministic. Like ``_latex_sanitize`` it is NOT idempotent -- a second pass
    would re-escape the (now bare) preserved commands. Call exactly once, on prose only.
    """
    out: list[str] = []
    pos = 0
    # Walk every allowlisted span in order; sanitize the gap BEFORE it, then append the
    # span itself verbatim. The trailing gap (after the last span) is handled below. A
    # string with no allowlisted span never enters the loop -> falls straight to the final
    # _latex_sanitize, i.e. identical to the non-prose path.
    for match in _PROSE_PASSTHROUGH_RE.finditer(s):
        out.append(_latex_sanitize(s[pos : match.start()]))  # gap -> fully sanitized
        out.append(match.group(0))                            # \cmd{key} -> verbatim
        pos = match.end()
    out.append(_latex_sanitize(s[pos:]))  # trailing gap (or the whole string if no spans)
    return "".join(out)


def _novelty_prose(
    text: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
) -> str:
    """Sanitize a prose slot AND render its ``\\novelty{kind}{hyp}{text}`` markup (N2 gate).

    The novelty member of the prose pipeline (alongside :func:`_latex_sanitize_prose` and
    :func:`factref.substitute_factrefs`). It SPLIT-and-stitches on
    :data:`novelty.NOVELTY_RENDER_RE` exactly as ``_latex_sanitize_prose`` walks the ref/cite
    allowlist: each GAP between/around the ``\\novelty`` spans is fully prose-sanitized, and
    each SPAN ``\\novelty{kind}{hyp}{inner}`` is re-emitted SURVIVING into the ``.tex`` (the
    preamble ``\\newcommand`` makes LaTeX render only the text) with:

      - ``kind`` / ``hyp`` -- slugs, emitted VERBATIM (verify re-scans them; a sanitized
        underscore would break the re-derivation, like a ref key);
      - the inner text -- prose-sanitized (FLAT: specials escaped, no nested ref/cite -- the
        documented honest limit), then immediately followed by the record-derived honest
        scope from :func:`novelty.novelty_scope_suffix` (also sanitized -- it is plain ASCII
        ``(to our knowledge, as of <date>)`` so the escape is a no-op, but routing it through
        keeps the boundary uniform). The scope is INSIDE the ``\\novelty`` text arg so the
        ``\\newcommand`` renders it.

    A string with NO ``\\novelty`` markup never enters the loop -> falls straight to
    ``_latex_sanitize_prose(text)`` (BYTE-IDENTICAL to the pre-N2 path). PURE + FAIL-LOUD:
    an unsupported / unknown / bad-kind assertion raises ``ValueError`` via
    ``novelty_scope_suffix`` (the HARD gate at render time).
    """
    out: list[str] = []
    pos = 0
    for match in NOVELTY_RENDER_RE.finditer(text):
        out.append(_latex_sanitize_prose(text[pos : match.start()]))  # gap -> sanitized
        kind, hyp, inner = match.group(1), match.group(2), match.group(3)
        suffix = novelty_scope_suffix(kind, hyp, spec, novelty_decisions)  # fail-loud
        out.append(
            "\\novelty{" + kind + "}{" + hyp + "}{"
            + _latex_sanitize_prose(inner)
            + _latex_sanitize(suffix)
            + "}"
        )
        pos = match.end()
    out.append(_latex_sanitize_prose(text[pos:]))  # trailing gap / whole string if no spans
    return "".join(out)


def _confidence_str(claim: Claim) -> str:
    """Human-readable confidence: numeric value or graded level, + type."""
    c = claim.confidence
    type_name = c.type.value if hasattr(c.type, "value") else str(c.type)
    if c.value is not None:
        return f"{c.value:.3g} ({type_name})"
    if c.level is not None:
        level = c.level.value if hasattr(c.level, "value") else str(c.level)
        return f"{level} ({type_name})"
    return type_name


def _confidence_display(claim: Claim) -> Optional[str]:
    """The confidence string to SHOW, or ``None`` to suppress it (render decision).

    A deterministic threshold verdict produces a ``credence``/``posterior`` confidence
    whose numeric ``value`` is the uninformative ``0.0`` default (the real judgment lives
    in ``basis``, C3). Rendering "confidence 0 (credence)" next to a SUPPORTED status reads
    as incoherent, so that uninformative zero is SUPPRESSED (the basis carries the
    judgment). A genuine graded level, or a non-zero numeric value, is shown via
    :func:`_confidence_str`. Render-only -- it never changes belief, only what is printed.
    """
    c = claim.confidence
    if (
        c.value is not None
        and c.value == 0.0
        and c.type in (ConfidenceType.CREDENCE, ConfidenceType.POSTERIOR)
    ):
        return None
    return _confidence_str(claim)


def _status_str(claim: Claim) -> str:
    return claim.status.value if hasattr(claim.status, "value") else str(claim.status)


def _bearing_data_sources(
    hyp_id: str, evidence: Sequence[EvidenceItem]
) -> list[str]:
    """The distinct ``data_source`` values of the Evidence bearing on ``hyp_id``.

    ``None`` (unstated) is surfaced as the literal ``"none"`` so the label is honest
    about unmarked provenance. Order is first-seen for a stable, readable line.
    """
    seen: list[str] = []
    for ev in evidence:
        if not any(b.target_id == hyp_id for b in ev.bears_on):
            continue
        src = ev.provenance.data_source or "none"
        if src not in seen:
            seen.append(src)
    return seen


def _evidence_validity_fields(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> tuple[str, str, str]:
    """The honest evidence-validity facts for one hypothesis as ``(referent,
    data_sources, qualifier)`` (design/evidence-validity.md §4).

    Single source of truth for the honesty labeling shared by the Markdown and LaTeX
    renderers: referent (a frozen Spec field), the bearing data_source(s), and a short
    qualifier (in-silico/computational, or awaiting measured data) when warranted.
    Reporting only -- it never changes belief; it labels what the gate already let
    through, and never overclaims.
    """
    referent = hyp.referent  # "formal" | "empirical" (a frozen Spec field)
    sources = _bearing_data_sources(hyp.id, evidence)
    sources_str = ", ".join(sources) if sources else "none"

    qualifier = ""
    is_supported = claim is not None and claim.status == ClaimStatus.SUPPORTED
    has_measured = "measured" in sources
    if referent == "formal" and is_supported and "generated" in sources:
        # A formal claim supported on generated instances: a real computational
        # result, not a bare empirical "supported".
        qualifier = "in-silico/computational result"
    elif referent == "empirical" and not has_measured:
        # An empirical claim with no measured Evidence yet: belief is not grounded in
        # real data, so say so plainly (the gate already blocks a binding empirical
        # verdict here; a proposed/awaiting claim is the legitimate state).
        qualifier = "awaiting measured data"

    return referent, sources_str, qualifier


def _evidence_validity_label(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> str:
    """The Markdown evidence-validity label line for one hypothesis (§4).

    A concise, factual single line built from :func:`_evidence_validity_fields`:
    referent + bearing data_source(s) + an honest qualifier when warranted, so a
    reader can tell apart an in-silico/computational result, a real measured result,
    and an empirical claim still awaiting measured data.
    """
    referent, sources_str, qualifier = _evidence_validity_fields(hyp, claim, evidence)
    suffix = f" — {qualifier}" if qualifier else ""
    return (
        f"- Evidence validity: referent={referent}; "
        f"data_source(s)={sources_str}{suffix}"
    )


def render_paper(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    pending: Optional[Sequence[dict[str, Any]]] = None,
    prose: Optional[PaperProse] = None,
    cited_dois: Optional[Sequence[str]] = None,
) -> str:
    """
    Render a Markdown paper draft.

    Args:
        spec: the compiled Spec (provenance of the proposal + hypotheses).
        claims: the Claims produced for the hypotheses (belief state).
        evidence: the Evidence log (the record); optional.
        pending: agent-judgment checkpoints (proof/qualitative awaiting an
            in-session verdict); optional. Each item: {hypothesis_id, kind,
            expression, finding}.
        prose: optional agent-authored narrative (abstract/introduction/discussion).
            A present slot is injected as its section; ``None`` (or a ``None`` slot)
            falls back to the structural skeleton -- with ``prose=None`` the output is
            byte-identical to the pre-prose skeleton (a regression invariant).
        cited_dois: optional DOIs to list in a References section. ``None``/empty
            renders a "No literature cited." line. DOI list only -- no BibTeX is
            generated (design decision).

    Returns:
        A Markdown document string.
    """
    evidence = list(evidence or [])
    pending = list(pending or [])
    rp = spec.raw_proposal
    claim_by_hyp = {c.answers: c for c in claims}

    lines: list[str] = []
    title = (rp.goal or "Untitled research").strip().splitlines()[0]
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> Draft compiled by sci-adk from Spec `{spec.id}` "
                 f"(v{spec.version}). Belief state is revisable as Evidence accrues.")
    lines.append("")

    # Agent-authored abstract (after the title), when supplied. Absent -> nothing,
    # preserving the byte-identical skeleton.
    if prose is not None and prose.abstract:
        lines.append("## Abstract")
        lines.append(prose.abstract.strip())
        lines.append("")

    # Agent-authored introduction, when supplied.
    if prose is not None and prose.introduction:
        lines.append("## Introduction")
        lines.append(prose.introduction.strip())
        lines.append("")

    lines.append("## Goal")
    lines.append(rp.goal.strip() or "_(none)_")
    lines.append("")
    lines.append("## Background")
    lines.append(rp.background.strip() or "_(none)_")
    lines.append("")
    lines.append("## Method")
    lines.append(rp.method.strip() or "_(none)_")
    if spec.method and spec.method.approaches:
        lines.append("")
        lines.append("Planned approaches:")
        for a in spec.method.approaches:
            lines.append(f"- {a}")
    lines.append("")

    # Hypotheses & findings: the heart of the draft -- each hypothesis with the
    # Claim the DecisionEngine produced from the per-Spec DecisionRule.
    lines.append("## Hypotheses and findings")
    lines.append("")
    for h in spec.hypotheses:
        claim = claim_by_hyp.get(h.id)
        rule = h.decision_rule
        rule_kind = rule.kind.value if hasattr(rule.kind, "value") else str(rule.kind)
        mode = h.mode.value if hasattr(h.mode, "value") else str(h.mode)
        lines.append(f"### {h.statement}")
        lines.append(f"- Hypothesis id: `{h.id}` ({mode})")
        lines.append(f"- Decision rule ({rule_kind}): {rule.expression}")
        if claim is not None:
            lines.append(f"- **Status: {_status_str(claim)}** — "
                         f"confidence {_confidence_str(claim)}")
            lines.append(f"- Basis: {claim.confidence.basis}")
        else:
            lines.append("- **Status: no claim** (no evidence bore on this hypothesis)")
        # Honest self-description: referent + bearing data_source(s) (evidence-validity
        # §4), so the draft never reads as a bare "supported" for a formal/generated
        # result, nor hides that an empirical claim lacks measured data.
        lines.append(_evidence_validity_label(h, claim, evidence))
        lines.append("")

    # Evidence trail (the append-only record).
    lines.append("## Evidence")
    if not evidence:
        lines.append("_No evidence recorded._")
    else:
        for ev in evidence:
            kind = ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind)
            summary = _result_summary(ev)
            lines.append(f"- `{ev.id}` ({kind}): {summary}")
    lines.append("")

    # Pending agent judgments (proof/qualitative checkpoints -- filled in-session).
    if pending:
        lines.append("## Pending agent judgments")
        lines.append("")
        lines.append("These hypotheses use a non-numeric rule and await an "
                     "in-session agent verdict (no autonomous LLM call):")
        for p in pending:
            lines.append(f"- `{p.get('hypothesis_id')}` "
                         f"({p.get('kind')}): {p.get('expression')}")
            finding = (p.get("finding") or "").strip()
            if finding:
                lines.append(f"  - finding: {finding}")
        lines.append("")

    # Agent-authored discussion, when supplied (before References).
    if prose is not None and prose.discussion:
        lines.append("## Discussion")
        lines.append(prose.discussion.strip())
        lines.append("")

    # References: a DOI list only (no BibTeX generation). Emitted only when the
    # caller passes the kwarg -- when cited_dois is omitted entirely (the legacy
    # call), nothing is appended, keeping the prose=None output byte-identical.
    if cited_dois is not None:
        lines.append("## References")
        dois = [d for d in cited_dois if d and d.strip()]
        if not dois:
            lines.append("No literature cited.")
        else:
            for doi in dois:
                lines.append(f"- https://doi.org/{doi}")
        lines.append("")

    return "\n".join(lines)


def _latex_evidence_validity_label(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> str:
    """The LaTeX evidence-validity label line for one hypothesis (§4).

    The LaTeX twin of :func:`_evidence_validity_label`: built from the same
    single-source :func:`_evidence_validity_fields`, so the honest in-silico /
    awaiting-measured-data qualifiers appear in the .tex exactly as in the .md. The
    referent and data_source(s) are escaped (they originate in the Spec/Evidence).
    """
    referent, sources_str, qualifier = _evidence_validity_fields(hyp, claim, evidence)
    suffix = f" --- {_latex_sanitize(qualifier)}" if qualifier else ""
    return (
        f"\\textit{{Evidence validity:}} referent={_latex_sanitize(referent)}; "
        f"data\\_source(s)={_latex_sanitize(sources_str)}{suffix}"
    )


def render_paper_latex(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    pending: Optional[Sequence[dict[str, Any]]] = None,
    prose: Optional[PaperProse] = None,
    cited_dois: Optional[Sequence[str]] = None,
    bib_path: Optional[str] = None,
    figures: Optional[Sequence[AnyFigure]] = None,
) -> str:
    """
    Render the BELIEF-NARRATIVE paper (``draft.tex``) -- agent prose + a record-fidelity
    spine (the "moved line", design/render-architecture-reframe.md).

    The reframe shrinks this renderer to its record-fidelity job and hands the paper's
    narrative + structure to the in-session agent (rigor-shell-architecture.md §2.4:
    "Writing paper prose" is OUT of the kernel). So the engine emits NO stage-dump
    sections (no Goal/Background/Evidence/Figures heading, no per-hypothesis verdict
    bullets) -- those record facts live in the deterministic SI (``render_si_latex``).
    What it DOES emit deterministically: the IMRaD skeleton an agent fills (Abstract /
    Introduction / Methods / Results / Discussion), the figures (drawn FROM the record),
    the bibliography wiring, and -- the fidelity gate -- the substitution of every
    ``\\evval``/``\\status`` macro in the agent prose with its TRUE recorded value
    (:func:`sci_adk.render.factref.substitute_factrefs`, FAIL-LOUD). So the narrative is
    the agent's, but every measured number / verdict it states is the record's.

    PURE: no LLM, no network. The agent prose arrives as ``prose`` (input, never
    generated here). Deterministic: same inputs -> byte-identical output.

    Args:
        spec: the compiled Spec (id + version for the title fallback + the header note).
        claims: the Claims (their statuses back ``\\status{<hyp>}`` in the prose).
        evidence: the Evidence record (figure y-values + ``\\evval`` values come from
            here); optional.
        pending: agent-judgment checkpoints; a NON-empty list emits a working-draft
            "Pending agent judgments" section (a finished paper has none). Optional.
        prose: the agent-authored narrative (``title``/``abstract``/``introduction``/
            ``methods``/``results``/``discussion``). Each present slot is emitted as its
            IMRaD section, after ``\\evval``/``\\status`` substitution + the prose
            sanitizer (``\\ref``/``\\cite`` preserved). ``title`` is the paper title; absent
            -> ``spec.id`` (NEVER the goal/hypothesis wall). ``None`` -> a near-empty paper
            (an unwritten narrative -- the record still lives in the SI).
        cited_dois: used ONLY as the no-bibtex fallback -- when ``bib_path`` is ``None`` and
            these are present, a ``\\url`` DOI list is emitted as the References. Ignored
            when ``bib_path`` is given (BibTeX is the single source then).
        bib_path: path to an EXISTING ``.bib`` (the compiler checks existence; the renderer
            does no fs access). Present -> ``\\usepackage{natbib}`` is wired with
            ``\\bibliographystyle{plainnat}`` + ``\\bibliography{<stem>}`` (author-year, so
            the prose's ``\\citep``/``\\citet`` resolve). NO ``\\nocite{*}`` and NO manual
            DOI list (one reference source, never both). ``None`` -> the DOI-list fallback
            (or nothing).
        figures: agent-authored MAIN figures (native pgfplots / image) -- the ONLY place
            main figures appear (the SI carries only supplementary figures). Placed as
            floats inside Results, numbered by body-reference order across the WHOLE
            narrative (a ``\\ref{fig:<id>}`` may be in Results or Discussion), so the order
            is computed against all prose then the floats are emitted; the compiler
            re-derives the SAME order from the rendered draft for co-located ``fig<N>``
            filenames. ``None``/empty -> no figures.

    Returns:
        A LaTeX document string (``\\documentclass`` ... ``\\end{document}``).
    """
    evidence = list(evidence or [])
    pending = list(pending or [])
    figures = list(figures or [])
    claims = list(claims)
    # Novelty decisions (bears_on=[]) back the \novelty{} markup re-derivation (N2 gate).
    novelty_decisions = [
        ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
    ]

    def _slot(text: str) -> str:
        # Agent prose -> substitute record-fidelity facts (\evval/\status, fail-loud), THEN
        # render \novelty{} markup (scope baked / HARD fail) + the prose sanitizer (specials
        # escaped; \ref/\cite preserved). Substitute factrefs before, so a substituted string
        # value is escaped as ordinary text; _novelty_prose owns the prose sanitize.
        return _novelty_prose(
            substitute_factrefs(text.strip(), evidence, claims),
            spec,
            novelty_decisions,
        )

    # Title: the agent's short title, else spec.id -- NEVER the goal/hypothesis wall.
    title = (prose.title.strip() if prose is not None and prose.title else "") or spec.id

    lines: list[str] = []
    # Preamble. natbib (author-year \citep/\citet); figure packages PER KIND.
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\usepackage{url}")
    lines.append(r"\usepackage{natbib}")
    has_native = any(f.kind == "native" for f in figures)
    has_image = any(f.kind == "image" for f in figures)
    # Figure font policy (design/paper-publishing-requirements.md F2): equations in a
    # Times-compatible serif (newtxmath -- MATH only, so the body TEXT font is unchanged),
    # other figure text in an Arial-compatible sans (helvet, scaled). pdflatex
    # metric-compatible -- no font files, no engine change. Emitted ONLY for a
    # figure-bearing paper, so a figure-less paper stays byte-identical (regression
    # invariant). The per-figure sans scoping is applied in figures.render_figure.
    if has_native or has_image:
        lines.append(r"\usepackage{amsmath}")
        lines.append(r"\usepackage{newtxmath}")
        lines.append(r"\usepackage[scaled]{helvet}")
    if has_native:
        lines.append(r"\usepackage{pgfplots}")
        lines.append(r"\pgfplotsset{compat=1.18}")
    if has_image:
        lines.append(r"\usepackage{graphicx}")
    # \novelty{kind}{hyp}{text} survives into the .tex; this \newcommand makes LaTeX render
    # only the text (kind/hyp are verify metadata). Emitted ONLY when novelty markup is
    # present in a prose slot, so a no-novelty paper is byte-identical (regression invariant).
    has_nov = prose is not None and any(
        has_novelty_markup(s)
        for s in (
            prose.abstract,
            prose.introduction,
            prose.methods,
            prose.results,
            prose.discussion,
        )
        if s
    )
    if has_nov:
        lines.append(NOVELTY_NEWCOMMAND)
    lines.append(f"\\title{{{_latex_sanitize(title)}}}")
    # Author is agent-supplied; absent -> empty \author{} (the paper is tool-agnostic and
    # never names the rendering toolchain -- design feedback §10, tool-vocabulary leakage).
    author = (prose.author.strip() if prose is not None and prose.author else "")
    lines.append(f"\\author{{{_latex_sanitize(author)}}}")
    lines.append(r"\date{\today}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")
    # NO engine-emitted "compiled by sci-adk from Spec ... Belief state ... Evidence"
    # note here: that is tool self-reference, which the belief-narrative paper must not
    # carry (§10). The provenance note lives in the SI (the record), which is exempt; a
    # data/code-availability pointer, if wanted, is agent prose.

    # Abstract.
    if prose is not None and prose.abstract:
        lines.append(r"\begin{abstract}")
        lines.append(_slot(prose.abstract))
        lines.append(r"\end{abstract}")
        lines.append("")

    # IMRaD body -- agent-authored narrative; a section is emitted ONLY when its prose
    # slot is present. The engine adds no stage-dump section of its own.
    if prose is not None and prose.introduction:
        lines.append(r"\section{Introduction}")
        lines.append(_slot(prose.introduction))
        lines.append("")
    if prose is not None and prose.methods:
        lines.append(r"\section{Methods}")
        lines.append(_slot(prose.methods))
        lines.append("")

    # Results: the agent's findings prose + the MAIN figures as floats (the only place
    # they appear). Figures are numbered by body-reference order across the WHOLE
    # narrative (a \ref may be in Results or Discussion), so the order is computed against
    # ALL prose -- the canonical \ref text (figures add only \label, no \ref) -- then the
    # floats are emitted here. Emitted when there is results prose OR at least one figure.
    if (prose is not None and prose.results) or figures:
        lines.append(r"\section{Results}")
        if prose is not None and prose.results:
            lines.append(_slot(prose.results))
            lines.append("")
        if figures:
            ref_body = "\n".join(
                s.strip()
                for s in (
                    (prose.abstract if prose else None),
                    (prose.introduction if prose else None),
                    (prose.methods if prose else None),
                    (prose.results if prose else None),
                    (prose.discussion if prose else None),
                )
                if s
            )
            for number, fig in order_figures_by_reference(figures, ref_body):
                lines.append(render_figure(fig, evidence, number))
                lines.append("")

    if prose is not None and prose.discussion:
        lines.append(r"\section{Discussion}")
        lines.append(_slot(prose.discussion))
        lines.append("")

    # Pending agent judgments -- only when present (an unresolved proof/qualitative
    # hypothesis). A finished paper has none; this is the working-draft signal.
    if pending:
        lines.append(r"\section{Pending agent judgments}")
        lines.append(
            "These hypotheses use a non-numeric rule and await an in-session agent "
            "verdict (no autonomous LLM call):"
        )
        lines.append(r"\begin{itemize}")
        for p in pending:
            hyp_id = _latex_sanitize(str(p.get("hypothesis_id")))
            kind = _latex_sanitize(str(p.get("kind")))
            expr = _latex_sanitize(str(p.get("expression")))
            lines.append(f"  \\item \\texttt{{{hyp_id}}} ({kind}): {expr}")
            finding = (p.get("finding") or "").strip()
            if finding:
                lines.append(f"  \\item finding: {_latex_sanitize(finding)}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # References: ONE source, never both. An existing .bib -> natbib + plainnat +
    # \bibliography (citations come from the prose's \citep/\citet; NO \nocite{*}, NO
    # manual list). No .bib but cited DOIs -> a \url DOI list (the no-bibtex fallback).
    if bib_path is not None:
        stem = Path(bib_path).stem
        lines.append(r"\bibliographystyle{plainnat}")
        lines.append(f"\\bibliography{{{stem}}}")
    else:
        dois = [d for d in (cited_dois or []) if d and d.strip()]
        if dois:
            lines.append(r"\section{References}")
            lines.append(r"\begin{itemize}")
            for doi in dois:
                # DOIs go verbatim inside \url{} (NOT escaped -- \url handles specials).
                lines.append(f"  \\item \\url{{https://doi.org/{doi}}}")
            lines.append(r"\end{itemize}")
    lines.append("")
    lines.append(r"\end{document}")
    return "\n".join(lines)


def _truncate_words(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars at a WORD boundary, ellipsis OUTSIDE.

    Never cuts mid-token (the bug behind the malformed JSON dumps was a fixed char cap
    slicing through a value). The ellipsis is appended after the boundary, so it is never
    inside a quoted string / number.
    """
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0]
    return (head or text[:limit]) + " ..."


def _summarize_value(value: object) -> str:
    """A short, STRUCTURED rendering of one finding value (never a raw mid-token cut).

    A scalar -> its text (capped at a word boundary). A list of dicts -> the salient
    fields (``doi``/``source``/``license``/``filename``) of the first entry + a ``(+N
    more)`` count -- so a literature finding renders as a structured citation summary, not
    a truncated JSON blob. A list of scalars -> a count. A nested dict -> ``{...}`` (the
    SI's per-item record carries the full structure; this is the one-line summary).
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return _truncate_words(str(value), 80)
    if isinstance(value, list):
        if not value:
            return "[]"
        head = value[0]
        if isinstance(head, dict):
            keys = [k for k in ("doi", "source", "license", "filename") if k in head]
            shown = ", ".join(f"{k}={_truncate_words(str(head[k]), 60)}" for k in keys)
            more = f" (+{len(value) - 1} more)" if len(value) > 1 else ""
            return f"[{{{shown or '...'}}}{more}]"
        return f"[{len(value)} item(s)]"
    if isinstance(value, dict):
        return "{...}"
    return _truncate_words(str(value), 80)


def _summarize_finding(finding: str) -> str:
    """Render a finding as a STRUCTURED, escaped-downstream summary -- never raw JSON.

    A JSON object -> ``key=value; ...`` of structured per-field summaries (so the DOI /
    source / license / filename of a literature finding read cleanly, design feedback
    3.1). A JSON array -> a count. Non-JSON prose -> the text, truncated at a word
    boundary with the ellipsis OUTSIDE (never mid-token). The caller escapes the result.
    """
    text = finding.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return f"finding={_truncate_words(text, 200)}"
    if isinstance(data, dict):
        bits = "; ".join(f"{k}={_summarize_value(v)}" for k, v in data.items())
        return f"finding=({bits})" if bits else "finding=()"
    if isinstance(data, list):
        return f"finding=[{len(data)} item(s)]"
    return f"finding={_summarize_value(data)}"


# -- §10 tool-vocabulary leakage check (paper narrative only; SI is exempt) ----------
#
# A belief-narrative paper must read as legitimate science to a reader who does not know
# sci-adk (the "tool-agnostic reader test"): no sentence may require knowing a sci-adk
# internal object to make sense. These phrases/words name the MACHINERY, not the science,
# so they must not appear in draft.tex. The SI (si.tex) is openly the record dump and is
# EXEMPT -- this checker is for the PAPER only. (design feedback §10.)
_PAPER_TOOL_PHRASES: tuple[str, ...] = (
    "sci-adk",
    "frozen spec",
    "engine-derived",
    "the engine",
    "verify audit",
    "append-only",
    "evidence record",
    "belief state",
    "anti-harking",
    "result.point",
    "result.finding",
    "decision rule",
)
# Bare jargon words (word-boundary, case-insensitive): a paper states a "result", not a
# "verdict".
_PAPER_TOOL_WORD_RE = re.compile(r"\b(?:verdict|verdicts)\b", re.IGNORECASE)
# "Spec" as a sci-adk proper noun (case-sensitive). The generic word -- "specification",
# "specifically", lowercase "spec" -- is fine; the capitalized object "Spec" is not.
_PAPER_TOOL_PROPER_RE = re.compile(r"\bSpec\b")


def check_paper_tool_vocabulary(paper_tex: str) -> list[str]:
    """Return the tool-vocabulary leaks found in a rendered PAPER (``draft.tex``).

    PURE. The §10 tool-agnostic check: returns the distinct forbidden phrases/words that
    name the sci-adk machinery (``sci-adk``, ``frozen Spec``, ``engine-derived``,
    ``verdict``, ``Evidence record``, ``result.point``, ...) found in ``paper_tex``. An
    EMPTY list means the paper reads as tool-agnostic science. The SI is the record dump
    and is intentionally NOT passed here (it is exempt). De-duplicated, first-seen order;
    a verify gate and the render regression tests both consume it.
    """
    low = paper_tex.lower()
    found: list[str] = []
    for phrase in _PAPER_TOOL_PHRASES:
        if phrase in low and phrase not in found:
            found.append(phrase)
    for match in _PAPER_TOOL_WORD_RE.finditer(paper_tex):
        word = match.group(0).lower()
        if word not in found:
            found.append(word)
    if _PAPER_TOOL_PROPER_RE.search(paper_tex) and "Spec" not in found:
        found.append("Spec")
    return found


def _result_summary(ev: EvidenceItem) -> str:
    """One-line, STRUCTURED summary of an Evidence item's Result.

    The numeric scalars (point/ci/posterior) plus a structured rendering of the qualitative
    finding (:func:`_summarize_finding`) -- NO raw JSON dumped, NO mid-token truncation. The
    SI carries the full per-item record; this is the readable one-line summary.
    """
    r = ev.result
    parts: list[str] = []
    if r.point is not None:
        parts.append(f"point={r.point:.6g}")
    if r.ci is not None:
        parts.append(f"ci={list(r.ci)}")
    if r.posterior is not None:
        parts.append(f"posterior={r.posterior:.6g}")
    if r.finding:
        parts.append(_summarize_finding(r.finding))
    return ", ".join(parts) if parts else "(no result fields)"
