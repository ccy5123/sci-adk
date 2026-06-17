"""
Render a paper draft (Markdown) from a Spec + its Claims + Evidence.

This is the *deterministic* renderer: it lays out the proposal, the per-hypothesis
findings (the Claims the DecisionEngine produced), the evidence trail, and any
pending agent judgments -- as a structured draft, with NO LLM prose (so it runs
at zero cost, design/tool-policy.md). Prose polishing, when wanted, is a separate
in-session agent step over this draft (never an autonomous claude -p call).

Reference: design/directory-structure.md (render/), design/abstractions.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Hypothesis, Spec
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
# (\x00..\x01), which are assumed absent from paper content -- they never occur in
# rendered Spec/Evidence/prose text, so a literal collision is not a practical concern.
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
    for char, sentinel, _final in _LATEX_SENTINELS:
        s = s.replace(char, sentinel)
    for _char, sentinel, final in _LATEX_SENTINELS:
        s = s.replace(sentinel, final)
    return s


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
    suffix = f" --- {_latex_escape(qualifier)}" if qualifier else ""
    return (
        f"\\textit{{Evidence validity:}} referent={_latex_escape(referent)}; "
        f"data\\_source(s)={_latex_escape(sources_str)}{suffix}"
    )


def render_paper_latex(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    pending: Optional[Sequence[dict[str, Any]]] = None,
    prose: Optional[PaperProse] = None,
    cited_dois: Optional[Sequence[str]] = None,
    bib_path: Optional[str] = None,
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

    Returns:
        A LaTeX document string (``\\documentclass`` ... ``\\end{document}``).
    """
    evidence = list(evidence or [])
    pending = list(pending or [])
    rp = spec.raw_proposal
    claim_by_hyp = {c.answers: c for c in claims}

    lines: list[str] = []
    title = (rp.goal or "Untitled research").strip().splitlines()[0]

    # Preamble. hyperref+url so \url{} renders; nothing network-dependent.
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\usepackage{url}")
    lines.append(f"\\title{{{_latex_escape(title)}}}")
    lines.append(r"\author{sci-adk (deterministic render)}")
    lines.append(r"\date{\today}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")
    lines.append(
        f"\\noindent\\textit{{Draft compiled by sci-adk from Spec "
        f"\\texttt{{{_latex_escape(spec.id)}}} (v{spec.version}). "
        f"Belief state is revisable as Evidence accrues.}}"
    )
    lines.append("")

    # Abstract (after \maketitle), when supplied.
    if prose is not None and prose.abstract:
        lines.append(r"\begin{abstract}")
        lines.append(_latex_escape(prose.abstract.strip()))
        lines.append(r"\end{abstract}")
        lines.append("")

    # Introduction, when supplied.
    if prose is not None and prose.introduction:
        lines.append(r"\section{Introduction}")
        lines.append(_latex_escape(prose.introduction.strip()))
        lines.append("")

    lines.append(r"\section{Goal}")
    lines.append(_latex_escape(rp.goal.strip()) or r"\emph{(none)}")
    lines.append("")
    lines.append(r"\section{Background}")
    lines.append(_latex_escape(rp.background.strip()) or r"\emph{(none)}")
    lines.append("")
    lines.append(r"\section{Method}")
    lines.append(_latex_escape(rp.method.strip()) or r"\emph{(none)}")
    if spec.method and spec.method.approaches:
        lines.append("")
        lines.append("Planned approaches:")
        lines.append(r"\begin{itemize}")
        for a in spec.method.approaches:
            lines.append(f"  \\item {_latex_escape(a)}")
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
        lines.append(f"\\subsection{{{_latex_escape(h.statement)}}}")
        lines.append(r"\begin{itemize}")
        lines.append(
            f"  \\item Hypothesis id: \\texttt{{{_latex_escape(h.id)}}} "
            f"({_latex_escape(mode)})"
        )
        lines.append(
            f"  \\item Decision rule ({_latex_escape(rule_kind)}): "
            f"{_latex_escape(rule.expression)}"
        )
        if claim is not None:
            lines.append(
                f"  \\item \\textbf{{Status: {_latex_escape(_status_str(claim))}}} "
                f"--- confidence {_latex_escape(_confidence_str(claim))}"
            )
            lines.append(f"  \\item Basis: {_latex_escape(claim.confidence.basis)}")
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
                f"  \\item \\texttt{{{_latex_escape(ev.id)}}} "
                f"({_latex_escape(kind)}): {_latex_escape(summary)}"
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
            hyp_id = _latex_escape(str(p.get("hypothesis_id")))
            kind = _latex_escape(str(p.get("kind")))
            expr = _latex_escape(str(p.get("expression")))
            lines.append(f"  \\item \\texttt{{{hyp_id}}} ({kind}): {expr}")
            finding = (p.get("finding") or "").strip()
            if finding:
                lines.append(f"  \\item finding: {_latex_escape(finding)}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # Agent-authored discussion, when supplied (before References).
    if prose is not None and prose.discussion:
        lines.append(r"\section{Discussion}")
        lines.append(_latex_escape(prose.discussion.strip()))
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
