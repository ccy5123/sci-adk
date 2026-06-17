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

from typing import Any, Optional, Sequence

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Hypothesis, Spec


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


def _evidence_validity_label(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> str:
    """A concise, factual evidence-validity label line for one hypothesis
    (design/evidence-validity.md §4): referent + bearing data_source(s), plus a short
    honest qualifier so a reader can tell apart an in-silico/computational result, a
    real measured result, and an empirical claim still awaiting measured data.

    Reporting only -- this never changes belief; it labels what the gate already let
    through. Never overclaims: it just states referent + data_source factually and
    adds one qualifier when warranted.
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
        qualifier = " — in-silico/computational result"
    elif referent == "empirical" and not has_measured:
        # An empirical claim with no measured Evidence yet: belief is not grounded in
        # real data, so say so plainly (the gate already blocks a binding empirical
        # verdict here; a proposed/awaiting claim is the legitimate state).
        qualifier = " — awaiting measured data"

    return f"- Evidence validity: referent={referent}; data_source(s)={sources_str}{qualifier}"


def render_paper(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    pending: Optional[Sequence[dict[str, Any]]] = None,
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
