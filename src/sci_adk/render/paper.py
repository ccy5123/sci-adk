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

import unicodedata
from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Hypothesis, Spec
from sci_adk.render.figures import (
    AnyFigure,
    order_figures_by_reference,
    render_figure,
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
    Render a compilable LaTeX paper draft -- the deterministic, OFFLINE twin of
    :func:`render_paper`.

    Mirrors the Markdown renderer's structure (proposal panes, per-hypothesis
    findings, evidence trail, pending checkpoints) but emits valid LaTeX. EVERY
    interpolated string is routed through :func:`_latex_escape` so the .tex compiles
    and stays faithful. The same honest evidence-validity labels appear here as in the
    Markdown output (no honesty dropped). No LLM, no network: data in, string out.

    Args:
        spec: the compiled Spec (provenance of the proposal + hypotheses).
        claims: the Claims produced for the hypotheses (belief state).
        evidence: the Evidence log (the record); optional.
        pending: agent-judgment checkpoints; optional (same shape as
            :func:`render_paper`'s ``pending``).
        prose: optional agent-authored narrative; a present abstract becomes a LaTeX
            ``abstract`` environment after ``\\maketitle``, introduction/discussion
            become sections. ``None`` -> structural skeleton only.
        cited_dois: DOIs to list in the References section as
            ``\\url{https://doi.org/<doi>}`` entries; ``None``/empty -> a
            "No literature cited." line. DOI list only -- no BibTeX is generated.
        bib_path: if provided, MUST be a path to an EXISTING .bib file; the caller
            (compiler ``_locate_bib_path``) performs the existence check -- the
            renderer does no filesystem access. When provided, the already-existing
            ``.bib`` is wired with ``\\bibliographystyle{plain}`` +
            ``\\bibliography{<stem>}`` + ``\\nocite{*}`` (so its entries render).
            ``None`` emits no ``\\bibliography``. No BibTeX is generated or fetched here.
        figures: optional agent-authored figure list -- native (pgfplots) or image
            (``\\includegraphics``) specs (design/paper-figures-and-si.md, Phase 1/4).
            When non-empty a ``\\section{Figures}`` of ``figure`` envs is emitted before
            the References, IN BODY-REFERENCE ORDER (the standard academic convention:
            the first figure ``\\ref``'d in the body is Figure 1, the next distinct one
            Figure 2, ...; unreferenced figures are appended last) -- see
            :func:`order_figures_by_reference`. Emitting the environments in that order
            makes LaTeX's source-order auto-numbering print the right "Figure N", while
            each figure's SEMANTIC ``\\label{fig:<id>}`` is preserved so the body's
            existing ``\\ref{fig:<id>}`` still resolves (no ref rewriting). Image specs
            reference co-located ``figures/fig<N><ext>`` (the GENERIC figure-number
            filename, domain-free); native y values are pulled from ``evidence`` (record
            fidelity). The preamble pulls ``pgfplots`` ONLY when a NATIVE figure is
            present and ``graphicx`` ONLY when an IMAGE figure is present, so a
            native-only render stays byte-identical to the pre-image skeleton and an
            image-only render does not load pgfplots. ``None``/empty -> NOTHING new is
            emitted: the output stays byte-identical to the figure-less skeleton (a
            regression invariant, like ``prose=None``; no figures -> no ordering ->
            unchanged output).

    Returns:
        A LaTeX document string (``\\documentclass`` ... ``\\end{document}``).
    """
    evidence = list(evidence or [])
    pending = list(pending or [])
    figures = list(figures or [])
    rp = spec.raw_proposal
    claim_by_hyp = {c.answers: c for c in claims}

    lines: list[str] = []
    title = (rp.goal or "Untitled research").strip().splitlines()[0]

    # Preamble. hyperref+url so \url{} renders; nothing network-dependent.
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\usepackage{url}")
    # Figure packages are added PER KIND so each path stays minimal and regression-safe:
    # pgfplots ONLY when a NATIVE figure is present (a native-only render stays
    # byte-identical to the pre-figures skeleton; an image-only render does not load
    # pgfplots), graphicx ONLY when an IMAGE figure is present. Both ship with Overleaf
    # -- no Python/pip dependency.
    has_native = any(f.kind == "native" for f in figures)
    has_image = any(f.kind == "image" for f in figures)
    if has_native:
        lines.append(r"\usepackage{pgfplots}")
        lines.append(r"\pgfplotsset{compat=1.18}")
    if has_image:
        lines.append(r"\usepackage{graphicx}")
    lines.append(f"\\title{{{_latex_sanitize(title)}}}")
    lines.append(r"\author{sci-adk (deterministic render)}")
    lines.append(r"\date{\today}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")
    lines.append(
        f"\\noindent\\textit{{Draft compiled by sci-adk from Spec "
        f"\\texttt{{{_latex_sanitize(spec.id)}}} (v{spec.version}). "
        f"Belief state is revisable as Evidence accrues.}}"
    )
    lines.append("")

    # Abstract (after \maketitle), when supplied.
    if prose is not None and prose.abstract:
        lines.append(r"\begin{abstract}")
        lines.append(_latex_sanitize(prose.abstract.strip()))
        lines.append(r"\end{abstract}")
        lines.append("")

    # Introduction, when supplied.
    if prose is not None and prose.introduction:
        lines.append(r"\section{Introduction}")
        lines.append(_latex_sanitize(prose.introduction.strip()))
        lines.append("")

    lines.append(r"\section{Goal}")
    lines.append(_latex_sanitize(rp.goal.strip()) or r"\emph{(none)}")
    lines.append("")
    lines.append(r"\section{Background}")
    lines.append(_latex_sanitize(rp.background.strip()) or r"\emph{(none)}")
    lines.append("")
    lines.append(r"\section{Method}")
    lines.append(_latex_sanitize(rp.method.strip()) or r"\emph{(none)}")
    if spec.method and spec.method.approaches:
        lines.append("")
        lines.append("Planned approaches:")
        lines.append(r"\begin{itemize}")
        for a in spec.method.approaches:
            lines.append(f"  \\item {_latex_sanitize(a)}")
        lines.append(r"\end{itemize}")
    lines.append("")

    # Hypotheses & findings: each hypothesis with the Claim the DecisionEngine
    # produced (mirrors render_paper's "Hypotheses and findings" block).
    lines.append(r"\section{Hypotheses and findings}")
    lines.append("")
    for h in spec.hypotheses:
        claim = claim_by_hyp.get(h.id)
        rule = h.decision_rule
        rule_kind = rule.kind.value if hasattr(rule.kind, "value") else str(rule.kind)
        mode = h.mode.value if hasattr(h.mode, "value") else str(h.mode)
        lines.append(f"\\subsection{{{_latex_sanitize(h.statement)}}}")
        lines.append(r"\begin{itemize}")
        lines.append(
            f"  \\item Hypothesis id: \\texttt{{{_latex_sanitize(h.id)}}} "
            f"({_latex_sanitize(mode)})"
        )
        lines.append(
            f"  \\item Decision rule ({_latex_sanitize(rule_kind)}): "
            f"{_latex_sanitize(rule.expression)}"
        )
        if claim is not None:
            lines.append(
                f"  \\item \\textbf{{Status: {_latex_sanitize(_status_str(claim))}}} "
                f"--- confidence {_latex_sanitize(_confidence_str(claim))}"
            )
            lines.append(f"  \\item Basis: {_latex_sanitize(claim.confidence.basis)}")
        else:
            lines.append(
                r"  \item \textbf{Status: no claim} "
                r"(no evidence bore on this hypothesis)"
            )
        # Honest self-description: referent + bearing data_source(s), same as the
        # Markdown renderer (no honesty dropped).
        lines.append(
            f"  \\item {_latex_evidence_validity_label(h, claim, evidence)}"
        )
        lines.append(r"\end{itemize}")
        lines.append("")

    # Evidence trail (the append-only record).
    lines.append(r"\section{Evidence}")
    if not evidence:
        lines.append(r"\emph{No evidence recorded.}")
    else:
        lines.append(r"\begin{itemize}")
        for ev in evidence:
            kind = ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind)
            summary = _result_summary(ev)
            lines.append(
                f"  \\item \\texttt{{{_latex_sanitize(ev.id)}}} "
                f"({_latex_sanitize(kind)}): {_latex_sanitize(summary)}"
            )
        lines.append(r"\end{itemize}")
    lines.append("")

    # Pending agent judgments (proof/qualitative checkpoints -- filled in-session).
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

    # Agent-authored discussion, when supplied (before References).
    if prose is not None and prose.discussion:
        lines.append(r"\section{Discussion}")
        lines.append(_latex_sanitize(prose.discussion.strip()))
        lines.append("")

    # Figures (native pgfplots or image \includegraphics), when supplied -- before
    # References. They are emitted IN BODY-REFERENCE ORDER: the body built SO FAR (every
    # \ref{fig:...} appears in prose/hypotheses, which all precede this Figures section)
    # is the canonical reference text, so order_figures_by_reference assigns Figure 1 =
    # first-\ref'd, etc. Emitting in that order means LaTeX's source-order auto-numbering
    # prints the right number; render_figure keeps each figure's semantic
    # \label{fig:<id>} so the body's \ref still resolves, and passes the assigned NUMBER
    # so an image figure includes figures/fig<N><ext> (native y is pulled from `evidence`
    # for record fidelity). Absent -> nothing emitted (byte-identical skeleton, like
    # prose: no figures -> no ordering -> no Figures section).
    if figures:
        # The body up to here is the canonical reference text (all \ref's precede the
        # Figures section); the compiler re-derives the SAME numbering from the full
        # rendered draft (the Figures section adds only \label's, no \ref's) so the
        # co-located fig<N> files match these \includegraphics paths exactly.
        body_so_far = "\n".join(lines)
        ordered = order_figures_by_reference(figures, body_so_far)
        lines.append(r"\section{Figures}")
        lines.append("")
        for number, fig in ordered:
            lines.append(render_figure(fig, evidence, number))
            lines.append("")

    # References: a DOI list (no BibTeX generation). Always emitted.
    lines.append(r"\section{References}")
    dois = [d for d in (cited_dois or []) if d and d.strip()]
    if not dois:
        lines.append("No literature cited.")
    else:
        lines.append(r"\begin{itemize}")
        for doi in dois:
            # DOIs are inserted verbatim inside \url{} (NOT _latex_escape'd) -- \url
            # handles % and other specials; escaping would corrupt the URL.
            lines.append(f"  \\item \\url{{https://doi.org/{doi}}}")
        lines.append(r"\end{itemize}")

    # Wire an EXISTING .bib (never generate one). The renderer does NO filesystem
    # access: a non-None bib_path is the caller's guarantee that the file exists (the
    # compiler's _locate_bib_path performs the existence check and passes None
    # otherwise). Path is used only for .stem here -- no .exists() call.
    if bib_path is not None:
        stem = Path(bib_path).stem
        lines.append("")
        lines.append(r"\bibliographystyle{plain}")
        lines.append(f"\\bibliography{{{stem}}}")
        # \nocite{*} so every entry in the existing .bib renders even without \cite.
        lines.append(r"\nocite{*}")
    lines.append("")

    lines.append(r"\end{document}")
    return "\n".join(lines)


def _result_summary(ev: EvidenceItem) -> str:
    """One-line summary of an Evidence item's Result."""
    r = ev.result
    parts: list[str] = []
    if r.point is not None:
        parts.append(f"point={r.point:.6g}")
    if r.ci is not None:
        parts.append(f"ci={list(r.ci)}")
    if r.posterior is not None:
        parts.append(f"posterior={r.posterior:.6g}")
    if r.finding:
        text = r.finding.strip().replace("\n", " ")
        parts.append(f"finding={text[:120]}")
    return ", ".join(parts) if parts else "(no result fields)"
