"""
Unit 2 (RED-first): the engine F2 trail gate for non-numeric verdicts.

design/rigor-shell-architecture.md §2.3 (F2): a BINDING (SUPPORTS/REFUTES) verdict
from the judge on a ``proof``/``qualitative`` rule is accepted only if it carries a
well-formed ``VerdictTrail``. The check is *structural* -- panel non-empty,
``rubric_expression``/``rubric_params`` present, ``chief.basis`` non-empty, and
``trail.rubric_expression == rule.expression`` (the verdict judged THIS rule). A
missing or malformed trail -> ``inconclusive`` with a basis naming the problem.

This is a contract STRENGTHENING: a confident judgment can no longer move a Claim on
the judge's say-so alone -- it must arrive with the auditable chief-over-N trail
("agents propose; the engine judges"). The engine never inspects N or the
combination policy, so the kernel stays unaware of how the chief aggregates.

Counterexample REFUTES is exempt (a decisive safety refutation needs no trail):
that path is covered in tests/test_decision_engine_proof_qualitative.py.
"""

from __future__ import annotations

from sci_adk.core.claim import ConfidenceLevel, ConfidenceType
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.spec import DecisionRule, DecisionRuleKind
from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
from sci_adk.loop.judge import JudgeVerdict
from sci_adk.loop.verdict import (
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)

QUAL_RULE = DecisionRule(
    kind=DecisionRuleKind.QUALITATIVE,
    expression="the finding is clear, well-organized, and on-topic",
)
PROOF_RULE = DecisionRule(
    kind=DecisionRuleKind.PROOF,
    expression="verified derivation => support; counterexample => refute",
)


class FakeJudge:
    def __init__(self, qualitative=None, proof=None):
        self._qualitative = qualitative
        self._proof = proof

    def judge_qualitative(self, criterion, finding, params):
        return self._qualitative

    def judge_proof(self, criterion, finding, artifact_ref, evidence_kinds, params):
        return self._proof


def _ev(kind=EvidenceKind.PROOF_STEP, finding="finding text"):
    return EvidenceItem(
        id="evi-1",
        spec_id="s",
        kind=kind,
        provenance=Provenance(),
        result=Result(type="qualitative", finding=finding),
        bears_on=[],
    )


def _results(*items):
    pairs = [
        (it, Bearing(target_id="hyp-1", direction=BearingDirection.NEUTRAL))
        for it in items
    ]
    return EvidenceForHypothesis(pairs=pairs)


def _well_formed_trail(rule_expression: str, direction=BearingDirection.SUPPORTS,
                       level=ConfidenceLevel.STRONG, rubric_params=None):
    return VerdictTrail(
        hypothesis_id="hyp-1",
        rule_kind="qualitative" if "clear" in rule_expression else "proof",
        rubric_expression=rule_expression,
        rubric_params=rubric_params,
        panel=[
            PanelVerdict(direction=direction, level=level, basis="panelist A reasoning"),
            PanelVerdict(
                direction=direction, level=ConfidenceLevel.MODERATE, basis="panelist B"
            ),
        ],
        chief=ChiefVerdict(
            direction=direction, level=level, basis="panelist A is decisive under R"
        ),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )


# -- qualitative binding gate ------------------------------------------------

def test_qualitative_binding_with_well_formed_trail_is_accepted():
    trail = _well_formed_trail(QUAL_RULE.expression)
    jv = JudgeVerdict(
        BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "criterion met", trail=trail
    )
    v = DecisionEngine(judge=FakeJudge(qualitative=jv)).evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.SUPPORTS
    assert v.confidence.type == ConfidenceType.GRADED
    assert v.confidence.level == ConfidenceLevel.STRONG


def test_qualitative_binding_without_trail_is_refused():
    # A confident SUPPORTS with NO trail must NOT move the Claim (F2 gate).
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "criterion met")
    v = DecisionEngine(judge=FakeJudge(qualitative=jv)).evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "trail" in v.confidence.basis.lower()


def test_qualitative_binding_with_rubric_mismatch_is_refused():
    # The trail must have judged THIS rule: rubric_expression == rule.expression.
    trail = _well_formed_trail("a DIFFERENT criterion the trail actually judged")
    jv = JudgeVerdict(
        BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "criterion met", trail=trail
    )
    v = DecisionEngine(judge=FakeJudge(qualitative=jv)).evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    basis = v.confidence.basis.lower()
    assert "rubric" in basis or "mismatch" in basis


def test_qualitative_refutes_binding_also_requires_a_trail():
    # The gate is on BOTH binding directions, not only SUPPORTS.
    jv = JudgeVerdict(BearingDirection.REFUTES, ConfidenceLevel.STRONG, "criterion failed")
    v = DecisionEngine(judge=FakeJudge(qualitative=jv)).evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "trail" in v.confidence.basis.lower()


def test_qualitative_refutes_binding_with_trail_is_accepted():
    trail = _well_formed_trail(QUAL_RULE.expression, direction=BearingDirection.REFUTES)
    jv = JudgeVerdict(
        BearingDirection.REFUTES, ConfidenceLevel.STRONG, "criterion failed", trail=trail
    )
    v = DecisionEngine(judge=FakeJudge(qualitative=jv)).evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.REFUTES


# -- proof binding gate ------------------------------------------------------

def test_proof_confident_verified_with_trail_still_pends_spotcheck():
    # Even WITH a well-formed trail, a confident proof "verified" does not become
    # supports -- the D8 human-spot-check override is preserved (no self-cert).
    trail = _well_formed_trail(PROOF_RULE.expression)
    jv = JudgeVerdict(
        BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "derivation verified",
        trail=trail,
    )
    v = DecisionEngine(judge=FakeJudge(proof=jv)).evaluate(PROOF_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "spot-check" in v.confidence.basis.lower()


def test_proof_confident_verified_without_trail_is_refused_for_trail():
    # A confident "verified" with no trail is refused at the gate (before the
    # spot-check override even applies): still inconclusive, but for the trail.
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "verified")
    v = DecisionEngine(judge=FakeJudge(proof=jv)).evaluate(PROOF_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "trail" in v.confidence.basis.lower()


def test_proof_judge_counterexample_refutes_without_a_trail():
    # COUNTEREXAMPLE is the decisive safety refutation -- exempt from the trail gate.
    jv = JudgeVerdict(
        BearingDirection.REFUTES, ConfidenceLevel.STRONG, "found counterexample",
        counterexample=True,
    )
    v = DecisionEngine(judge=FakeJudge(proof=jv)).evaluate(PROOF_RULE, _results(_ev()))
    assert v.direction == BearingDirection.REFUTES
