"""
Phase D3 tests: proof / qualitative routing to an injected LLM-judge (Decision 4).

A ``FakeJudge`` stands in for the real Claude-backed judge (the live adapter is
deferred), so these are deterministic and network-free. They lock the §0
override rails:
  - a counterexample (in the record OR found by the judge) refutes decisively;
  - a confident proof "verified" verdict does NOT become ``supports`` -- it
    routes to a human spot-check (inconclusive) before a Claim can be supported;
  - low-confidence judgments escalate to a human;
  - with no judge, proof/qualitative return inconclusive (never fabricated).

Updated for the F2 trail gate (design/rigor-shell-architecture.md §2.3): a BINDING
(SUPPORTS/REFUTES) non-numeric verdict now must arrive with a well-formed
``VerdictTrail``. Tests that exercise a confident binding outcome therefore attach a
trail (see ``_trail``); the trail-absent / rubric-mismatch refusals are covered in
tests/test_decision_engine_trail_gate.py.
"""

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

PROOF_RULE = DecisionRule(
    kind=DecisionRuleKind.PROOF,
    expression="verified derivation => support; counterexample => refute",
)
QUAL_RULE = DecisionRule(
    kind=DecisionRuleKind.QUALITATIVE,
    expression="the finding is clear, well-organized, and on-topic",
)


def _trail(rule: DecisionRule, direction=BearingDirection.SUPPORTS,
           level=ConfidenceLevel.STRONG):
    """A well-formed chief-over-N trail that judged ``rule`` (F2 gate input)."""
    return VerdictTrail(
        hypothesis_id="hyp-1",
        rule_kind=rule.kind.value,
        rubric_expression=rule.expression,
        rubric_params=rule.params,
        panel=[
            PanelVerdict(direction=direction, level=level, basis="panelist A"),
            PanelVerdict(direction=direction, level=ConfidenceLevel.MODERATE,
                         basis="panelist B"),
        ],
        chief=ChiefVerdict(direction=direction, level=level,
                           basis="panelist A reasoning is decisive under R"),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )


class FakeJudge:
    """A scripted judge; records its calls for argument assertions."""

    def __init__(self, qualitative=None, proof=None):
        self._qualitative = qualitative
        self._proof = proof
        self.calls = []

    def judge_qualitative(self, criterion, finding, params):
        self.calls.append(("qualitative", criterion, finding, params))
        return self._qualitative

    def judge_proof(self, criterion, finding, artifact_ref, evidence_kinds, params):
        self.calls.append(
            ("proof", criterion, finding, artifact_ref, evidence_kinds, params))
        return self._proof


def _ev(kind=EvidenceKind.PROOF_STEP, finding="finding text", artifact_ref=None):
    return EvidenceItem(
        id="evi-1",
        spec_id="s",
        kind=kind,
        provenance=Provenance(),
        result=Result(type="qualitative", finding=finding, artifact_ref=artifact_ref),
        bears_on=[],
    )


def _results(*items):
    pairs = [
        (it, Bearing(target_id="hyp-1", direction=BearingDirection.NEUTRAL))
        for it in items
    ]
    return EvidenceForHypothesis(pairs=pairs)


# -- qualitative -------------------------------------------------------------

def test_qualitative_confident_judgment_maps_to_direction_and_level():
    # A confident BINDING judgment now requires a well-formed trail (F2 gate).
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.STRONG,
                      "criterion clearly met", trail=_trail(QUAL_RULE))
    engine = DecisionEngine(judge=FakeJudge(qualitative=jv))
    v = engine.evaluate(QUAL_RULE, _results(_ev(finding="clear and organized")))
    assert v.direction == BearingDirection.SUPPORTS
    assert v.confidence.type == ConfidenceType.GRADED
    assert v.confidence.level == ConfidenceLevel.STRONG
    assert "criterion clearly met" in v.confidence.basis


def test_qualitative_low_confidence_escalates_to_human():
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.WEAK, "unsure")
    engine = DecisionEngine(judge=FakeJudge(qualitative=jv))
    v = engine.evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "escalate to human" in v.confidence.basis.lower()


def test_qualitative_without_judge_is_inconclusive():
    v = DecisionEngine().evaluate(QUAL_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "judge" in v.confidence.basis.lower()
    assert v.confidence.value is None  # no fabricated number (D8)


def test_qualitative_judge_applies_the_specs_own_criterion():
    jv = JudgeVerdict(BearingDirection.NEUTRAL, ConfidenceLevel.MODERATE, "ok")
    fake = FakeJudge(qualitative=jv)
    DecisionEngine(judge=fake).evaluate(QUAL_RULE, _results(_ev(finding="some finding")))
    _, criterion, finding, _ = fake.calls[0]
    assert criterion == QUAL_RULE.expression   # the rule's own prose, not a global rubric (D1)
    assert "some finding" in finding


# -- proof -------------------------------------------------------------------

def test_proof_counterexample_in_record_is_decisive_without_a_judge():
    # A COUNTEREXAMPLE item refutes decisively -- no judge consulted.
    engine = DecisionEngine()  # no judge on purpose
    v = engine.evaluate(
        PROOF_RULE, _results(_ev(kind=EvidenceKind.COUNTEREXAMPLE, finding="cx")))
    assert v.direction == BearingDirection.REFUTES
    assert v.confidence.level == ConfidenceLevel.STRONG
    assert "counterexample" in v.confidence.basis.lower()


def test_proof_formal_proof_in_record_is_decisive_supports_without_a_judge():
    # The dual of the counterexample: a machine-checked FORMAL_PROOF supports decisively --
    # no judge, no human spot-check (the §0 override guards an LLM "verified", not a
    # mechanical proof from a trusted checker like Lean).
    engine = DecisionEngine()  # no judge on purpose
    v = engine.evaluate(
        PROOF_RULE, _results(_ev(kind=EvidenceKind.FORMAL_PROOF, finding="lean: ok")))
    assert v.direction == BearingDirection.SUPPORTS
    assert v.confidence.level == ConfidenceLevel.STRONG
    assert "formal_proof" in v.confidence.basis.lower() or "checker" in v.confidence.basis.lower()


def test_proof_counterexample_beats_formal_proof_when_both_present():
    # A contradictory record (both a machine proof AND a counterexample) safety-refutes:
    # the counterexample is checked first.
    engine = DecisionEngine()
    v = engine.evaluate(PROOF_RULE, _results(
        _ev(kind=EvidenceKind.FORMAL_PROOF, finding="lean: ok"),
        _ev(kind=EvidenceKind.COUNTEREXAMPLE, finding="cx"),
    ))
    assert v.direction == BearingDirection.REFUTES


def test_proof_judge_found_counterexample_refutes():
    jv = JudgeVerdict(BearingDirection.REFUTES, ConfidenceLevel.STRONG,
                      "found a counterexample", counterexample=True)
    engine = DecisionEngine(judge=FakeJudge(proof=jv))
    v = engine.evaluate(PROOF_RULE, _results(_ev(kind=EvidenceKind.PROOF_STEP)))
    assert v.direction == BearingDirection.REFUTES


def test_proof_confident_verified_pends_human_spotcheck_not_supports():
    # OVERRIDE: even WITH a well-formed trail, a confident "verified" still needs a
    # human spot-check before a Claim can be supported -- the engine must NOT emit
    # supports. (Trail-absent confident verified is refused for the trail instead;
    # see tests/test_decision_engine_trail_gate.py.)
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.STRONG,
                      "derivation verified", trail=_trail(PROOF_RULE))
    engine = DecisionEngine(judge=FakeJudge(proof=jv))
    v = engine.evaluate(PROOF_RULE, _results(_ev(finding="proof body")))
    assert v.direction == BearingDirection.INCONCLUSIVE
    basis = v.confidence.basis.lower()
    assert "spot-check" in basis and "supported" in basis


def test_proof_low_confidence_escalates_to_human():
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.WEAK, "maybe")
    engine = DecisionEngine(judge=FakeJudge(proof=jv))
    v = engine.evaluate(PROOF_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "escalate to human" in v.confidence.basis.lower()


def test_proof_without_judge_or_counterexample_is_inconclusive():
    v = DecisionEngine().evaluate(PROOF_RULE, _results(_ev()))
    assert v.direction == BearingDirection.INCONCLUSIVE
    assert "judge" in v.confidence.basis.lower()


def test_proof_engine_never_emits_supports():
    # The engine emits refutes (counterexample) or inconclusive (pending/escalate)
    # for proofs -- never supports. Promotion to supported is the human's step.
    jv = JudgeVerdict(BearingDirection.SUPPORTS, ConfidenceLevel.STRONG, "verified")
    v = DecisionEngine(judge=FakeJudge(proof=jv)).evaluate(
        PROOF_RULE, _results(_ev()))
    assert v.direction != BearingDirection.SUPPORTS
