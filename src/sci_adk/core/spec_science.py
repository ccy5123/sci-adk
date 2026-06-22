"""
sci-adk spec-gate science lints (design/science-guards.md) -- the ALWAYS-ON surfacing
side of the science guards.

This is the (a) enforcement point of the two: at proposal->spec compile time
(``ResearchCompiler.stage_init_spec``), every Spec is audited for the weak-science
patterns G1/G2/G4/G5 (and a forward G3 reminder). Unlike the verdict-gate HALTS
(``core/validity.py``, gated by ``strict_science``), this audit NEVER halts and is ALWAYS
on -- so a weak Spec is never SILENTLY accepted (the guard's firing semantics): the
findings are surfaced as recording-type checkpoints the author resolves by a Spec
amendment, exactly like the prior-work / novelty / contested reminders.

It is KERNEL-side and holds NO LLM and NO domain knowledge: it reads frozen Spec fields
(referent, decision_rule.kind, mode, novelty flags, epistemic_kind, discriminating_cases,
cost_metrics) + the hypothesis/target-claim TEXT and produces structural findings --
nothing more. The deep judgments the guards rest on (is this case genuinely hard? is this
result actually a known theorem?) are the author's, recorded for audit; the lint only
checks that the DECLARATION the guard demands is present (the §5 honest-limit spirit).

Reference: design/science-guards.md (authoritative), design/evidence-validity.md (the
sibling referent-typed gate this composes with), design/abstractions.md (record vs belief).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from sci_adk.core.spec import DecisionRuleKind, Hypothesis, Spec

# The deterministic numeric rule kind the science guards reason about (mirrors
# core/validity._DETERMINISTIC). A single comparison of a recorded statistic -- no RNG.
_THRESHOLD = DecisionRuleKind.THRESHOLD

# G5 keyword -> required cost metric. A practical-property TERM in a claim commits the
# author to MEASURING that property; the lint demands the corresponding statistic so the
# cost is on the record (e.g. a Gödel "index" whose integers blow up super-polynomially must
# report its bit-length). Manual override: declaring the metric in ``Hypothesis.cost_metrics``
# (or already naming a size/time statistic) satisfies the lint. Lower-cased word-boundary
# matching; kept deliberately SMALL and explicit (no NLP) -- the same spirit as the
# deterministic ``\novelty`` markup, not a keyword classifier.
_COST_KEYWORDS: dict[str, str] = {
    "index": "the integer SIZE (bit-length) of the index -- a Gödel/prime-power index can "
    "grow super-polynomially, so its bit-length must be reported",
    "efficient": "a runtime / time-complexity measurement substantiating 'efficient'",
    "efficiency": "a runtime / time-complexity measurement substantiating 'efficiency'",
    "scalable": "a size-scaling measurement (how the cost grows with input size)",
    "scalability": "a size-scaling measurement (how the cost grows with input size)",
    "fast": "a runtime measurement substantiating 'fast'",
    "compact": "a space/size measurement (bytes or bit-length) substantiating 'compact'",
    "succinct": "a space/size measurement (bytes or bit-length) substantiating 'succinct'",
    "lightweight": "a space and/or time measurement substantiating 'lightweight'",
    "practical": "a concrete cost measurement (time and/or space) substantiating 'practical'",
    "optimal": "the cost measurement + the bound it is optimal against",
}

# Cost-metric statistic NAMES that, when present in cost_metrics or the rule's statistic,
# count as "the metric is declared" (so a claim that already reports size/time is not
# re-flagged). Substring match, lower-cased.
_COST_METRIC_HINTS: tuple[str, ...] = (
    "bit", "size", "length", "byte", "time", "runtime", "complexity", "memory", "space",
    "scaling", "cost",
)


class ScienceFinding(BaseModel):
    """A spec-gate science-guard finding -- a recording-type reminder, never a halt.

    Mirrors the other recording-type checkpoints (prior-work / novelty / contested): a
    typed record that a weak-science pattern was detected at spec-compile time, which the
    author resolves by supplying the missing artifact (a reclassification, a discriminating
    case, a cost metric) or a justification -- recorded as a Spec amendment. It carries no
    verdict trail (it is a decision prompt, not a belief).

    Attributes:
        guard: which guard fired (``G1``..``G5``).
        hypothesis_id: the hypothesis the finding is about (``None`` for a spec-wide note).
        message: the human-facing prompt -- what was detected and how to resolve it.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    guard: str = Field(..., min_length=1, description="Which guard fired (G1..G5)")
    hypothesis_id: Optional[str] = Field(
        default=None, description="Hypothesis the finding is about (None = spec-wide)"
    )
    message: str = Field(..., min_length=1, description="What was detected + how to resolve")


def _is_deterministic_formal(h: Hypothesis) -> bool:
    """A ``formal`` referent with a deterministic (``threshold``) rule -- the analytic
    claim class the science guards reason about (mirrors validity._is_deterministic_formal)."""
    return h.referent == "formal" and h.decision_rule.kind == _THRESHOLD


def _claim_text_for(spec: Spec, hypothesis: Hypothesis) -> str:
    """The text the cost lint scans for a hypothesis: its statement + the target claims that
    answer it (the practical-property word may live in either)."""
    parts = [hypothesis.statement]
    parts.extend(tc.statement for tc in spec.target_claims if tc.answers == hypothesis.id)
    return " ".join(parts).lower()


def _has_cost_metric(hypothesis: Hypothesis) -> bool:
    """True iff the hypothesis already DECLARES a cost metric (manual override): a non-empty
    ``cost_metrics`` list, OR a rule ``statistic`` param that names a size/time measurement."""
    if hypothesis.cost_metrics:
        return True
    params = hypothesis.decision_rule.params or {}
    statistic = str(params.get("statistic", "")).lower()
    return any(hint in statistic for hint in _COST_METRIC_HINTS)


def _word_in(text: str, word: str) -> bool:
    """Whole-word, lower-cased containment (so 'indexing' does not match 'index' spuriously,
    but 'molecular index' does). Pure-stdlib word-boundary check without a regex import."""
    i = text.find(word)
    while i != -1:
        before = text[i - 1] if i > 0 else " "
        after = text[i + len(word)] if i + len(word) < len(text) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        i = text.find(word, i + 1)
    return False


def audit_spec_science(spec: Spec) -> List[ScienceFinding]:
    """Audit a frozen Spec for the weak-science patterns G1/G2/G4/G5 (+ a G3 reminder).

    PURE + structural + always-on (NEVER halts): returns one :class:`ScienceFinding` per
    detected pattern, which ``stage_init_spec`` persists and the CLI surfaces. The
    verdict-gate HALTS (``core/validity.py``) enforce the same concerns at SUPPORTED-stamp
    time under ``strict_science``; this is the spec-time surfacing that keeps a weak Spec
    from being SILENTLY accepted.

    Findings (per hypothesis unless noted):
      - G1 analyticity: a ``formal`` + ``threshold`` hypothesis asserting no novelty, still
        ``epistemic_kind=='finding'`` -> reclassify (capability_check/unit_test) or assert
        novelty (a known-result/constructively-true claim must not be framed as a discovery).
      - G2 test-power: a ``formal`` + ``threshold`` hypothesis with no ``discriminating_cases``
        -> declare the hard cases that make a pass informative.
      - G3 reminder (forward): a ``formal`` + ``threshold`` hypothesis -> a strict SUPPORTED
        will require a NEGATIVE_CONTROL failing on those discriminating cases.
      - G4 mode-coherence: a frozen ``threshold`` rule with ``mode=='exploratory'`` -> a
        pre-registered pass/fail threshold should be ``confirmatory`` (a guide-not-gate rule
        belongs to exploratory work).
      - G5 claim-cost: a practical-property term (index/efficient/scalable/...) in the
        hypothesis or its target claims with no declared cost metric -> declare the metric.
    """
    findings: List[ScienceFinding] = []
    for h in spec.hypotheses:
        det_formal = _is_deterministic_formal(h)

        # G1 -- analyticity (same trigger as validity.check_analyticity, minus the
        # evidence-side data_source check, which is unknown at spec time).
        if (
            det_formal
            and h.epistemic_kind == "finding"
            and not h.novelty_result
            and not h.novelty_method
        ):
            findings.append(ScienceFinding(
                guard="G1",
                hypothesis_id=h.id,
                message=(
                    "formal + deterministic (threshold) hypothesis asserting no novelty, still "
                    "epistemic_kind='finding': a constructively-true / already-known result "
                    "would be framed as an empirical discovery. Reclassify (epistemic_kind -> "
                    "'unit_test' if it is true by construction, 'capability_check' for a "
                    "capability assertion) or assert novelty (novelty_result/novelty_method "
                    "with a recorded found_nothing prior-art search). (G1)"
                ),
            ))

        # G2 -- test-power.
        if det_formal and not h.discriminating_cases:
            findings.append(ScienceFinding(
                guard="G2",
                hypothesis_id=h.id,
                message=(
                    "formal + deterministic (threshold) hypothesis declares no "
                    "discriminating_cases: a pass over an easy/undeclared test set is "
                    "non-discriminating (a plausibly-broken method would pass it too). Declare "
                    "the hard cases that make a pass informative, each with the reason it "
                    "separates a correct method from a broken one. (G2)"
                ),
            ))

        # G3 -- forward reminder (the verdict-gate HALT is evidence-dependent, so spec time
        # only reminds: a strict SUPPORTED will need a falsifying negative control).
        if det_formal:
            findings.append(ScienceFinding(
                guard="G3",
                hypothesis_id=h.id,
                message=(
                    "formal + deterministic (threshold) hypothesis: a strict SUPPORTED will "
                    "REQUIRE a NEGATIVE_CONTROL Evidence item -- a deliberately mutated method "
                    "(broken so the hypothesis must be violated) that was actually run and on "
                    "which the decision rule returned NOT-SUPPORTED, failing on the declared "
                    "discriminating cases. Plan to record one (e.g. remove a tie-breaking "
                    "invariant from the canonicalizer and confirm collisions appear). (G3)"
                ),
            ))

        # G4 -- mode-coherence (structural; independent of referent).
        if h.decision_rule.kind == _THRESHOLD and h.mode.value == "exploratory":
            findings.append(ScienceFinding(
                guard="G4",
                hypothesis_id=h.id,
                message=(
                    "mode-coherence: a frozen pre-registered threshold decision rule is "
                    "treated as binding pass/fail, but mode=='exploratory' (where a rule is a "
                    "guide, not a gate). Set mode='confirmatory' to honestly pre-register the "
                    "hard threshold, or use a non-threshold rule for exploratory work. (G4)"
                ),
            ))

        # G5 -- claim-cost.
        if not _has_cost_metric(h):
            text = _claim_text_for(spec, h)
            hit = next((kw for kw in _COST_KEYWORDS if _word_in(text, kw)), None)
            if hit is not None:
                findings.append(ScienceFinding(
                    guard="G5",
                    hypothesis_id=h.id,
                    message=(
                        f"claim-cost: the claim uses the practical-property term '{hit}' but "
                        f"declares no cost metric. Report {_COST_KEYWORDS[hit]} (declare it in "
                        "Hypothesis.cost_metrics, or name a size/time statistic in the rule). (G5)"
                    ),
                ))

    return findings


__all__ = ["ScienceFinding", "audit_spec_science", "_COST_KEYWORDS"]
