"""
Test fixtures for sci-adk core types.

Provides pytest fixtures for creating valid test data across all three core types:
Spec, Evidence, and Claim.

Usage:
    from tests.fixtures import (
        valid_spec,
        valid_hypothesis,
        valid_decision_rule,
        # ... etc
    )
"""

import pytest
from datetime import datetime

# Import from submodules directly
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    Id,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
    ToolRef,
)

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    Cost,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceLevel,
    ConfidenceType,
    EvidenceLink,
    EvidenceLinkRole,
    StatusChange,
)


@pytest.fixture
def sample_hypothesis_id() -> Id:
    """Sample hypothesis ID."""
    return "hyp-test-encoding"


@pytest.fixture
def sample_claim_id() -> Id:
    """Sample claim ID."""
    return "claim-test-encoding"


@pytest.fixture
def sample_evidence_id() -> Id:
    """Sample evidence ID."""
    return "evi-test-001"


@pytest.fixture
def sample_spec_id() -> Id:
    """Sample spec ID."""
    return "spec-test-001"


@pytest.fixture
def valid_raw_proposal() -> RawProposal:
    """Valid raw proposal fixture."""
    return RawProposal(
        background="Molecule graphs represent chemical structures as graph objects.",
        goal="Determine if molecule graphs admit a bijective Gödel-style encoding.",
        method="Implement encoding algorithm and test on dataset of 1000 molecules.",
        expected_output="Proof of bijectivity or counterexample demonstrating failure.",
    )


@pytest.fixture
def valid_decision_rule(sample_hypothesis_id: Id) -> DecisionRule:
    """Valid decision rule fixture."""
    return DecisionRule(
        kind=DecisionRuleKind.BAYESIAN,
        expression="posterior odds > 10 => support",
        params={"min_odds": 10.0},
    )


@pytest.fixture
def valid_threshold_decision_rule() -> DecisionRule:
    """Valid threshold-based decision rule."""
    return DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression="accuracy >= 0.95 => support",
        params={"min_accuracy": 0.95},
    )


@pytest.fixture
def valid_interval_decision_rule() -> DecisionRule:
    """Valid interval-based decision rule."""
    return DecisionRule(
        kind=DecisionRuleKind.INTERVAL,
        expression="95% CI excludes 0 => support",
        params={"confidence_level": 0.95},
    )


@pytest.fixture
def valid_qualitative_decision_rule() -> DecisionRule:
    """Valid qualitative decision rule."""
    return DecisionRule(
        kind=DecisionRuleKind.QUALITATIVE,
        expression="Expert consensus on structural preservation",
    )


@pytest.fixture
def valid_proof_decision_rule() -> DecisionRule:
    """Valid proof-based decision rule."""
    return DecisionRule(
        kind=DecisionRuleKind.PROOF,
        expression="Verified derivation or counterexample exists",
    )


@pytest.fixture
def valid_hypothesis(
    sample_hypothesis_id: Id,
    valid_decision_rule: DecisionRule,
) -> Hypothesis:
    """Valid hypothesis fixture."""
    return Hypothesis(
        id=sample_hypothesis_id,
        statement="Molecule graphs admit a bijective Gödel-style encoding",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=valid_decision_rule,
    )


@pytest.fixture
def exploratory_hypothesis(sample_hypothesis_id: Id) -> Hypothesis:
    """Explatory hypothesis fixture."""
    return Hypothesis(
        id="hyp-exploratory-001",
        statement="Graph neural networks improve encoding efficiency",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE,
            expression="Qualitative assessment of improvement",
        ),
    )


@pytest.fixture
def valid_method_plan() -> MethodPlan:
    """Valid method plan fixture."""
    return MethodPlan(
        approaches=[
            "Implement Gödel encoding algorithm",
            "Test bijection property on random molecules",
            "Verify decoding correctness",
        ],
        tools=[
            ToolRef(name="RDKit", version="2023.9.1", kind="library"),
            ToolRef(name="NetworkX", version="3.2", kind="library"),
        ],
    )


@pytest.fixture
def valid_target_claim(sample_hypothesis_id: Id) -> TargetClaim:
    """Valid target claim fixture."""
    return TargetClaim(
        id="claim-target-001",
        statement="We prove bijection exists between molecule graphs and natural numbers",
        answers=sample_hypothesis_id,
    )


@pytest.fixture
def valid_spec(
    sample_spec_id: Id,
    valid_raw_proposal: RawProposal,
    valid_hypothesis: Hypothesis,
    valid_method_plan: MethodPlan,
    valid_target_claim: TargetClaim,
) -> Spec:
    """Valid spec fixture with all components."""
    return Spec(
        id=sample_spec_id,
        created_at=datetime(2026, 5, 26, 12, 0, 0),
        version=1,
        raw_proposal=valid_raw_proposal,
        hypotheses=[valid_hypothesis],
        method=valid_method_plan,
        target_claims=[valid_target_claim],
    )


@pytest.fixture
def multi_hypothesis_spec(
    sample_spec_id: Id,
    valid_raw_proposal: RawProposal,
    valid_hypothesis: Hypothesis,
    exploratory_hypothesis: Hypothesis,
    valid_method_plan: MethodPlan,
    valid_target_claim: TargetClaim,
) -> Spec:
    """Spec with multiple hypotheses."""
    return Spec(
        id=f"{sample_spec_id}-multi",
        created_at=datetime(2026, 5, 26, 12, 0, 0),
        version=1,
        raw_proposal=valid_raw_proposal,
        hypotheses=[valid_hypothesis, exploratory_hypothesis],
        method=valid_method_plan,
        target_claims=[
            valid_target_claim,
            TargetClaim(
                id="claim-target-002",
                statement="GNNs improve encoding by >20%",
                answers="hyp-exploratory-001",
            ),
        ],
    )


@pytest.fixture
def amended_spec(
    valid_spec: Spec,
    valid_hypothesis: Hypothesis,
) -> Spec:
    """Amended spec fixture (version 2)."""
    return valid_spec.amend(
        hypotheses=[
            Hypothesis(
                id="hyp-amended",
                statement="Revised hypothesis statement",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=valid_hypothesis.decision_rule,
            )
        ],
        rationale="Original hypothesis was too broad",
    )


@pytest.fixture
def valid_provenance() -> Provenance:
    """Valid provenance fixture."""
    return Provenance(
        code_ref="commit:abc123@main:src/encoding.py:45-67",
        data_ref="molecules-dataset-v1.2",
        seed=42,
        environment="python3.13, rdkit-2023.9.1, networkx-3.2",
        cost=Cost(tokens=1500, wallclock_seconds=12.5, cpu_seconds=10.2, memory_mb=512),
    )


@pytest.fixture
def minimal_provenance() -> Provenance:
    """Minimal provenance with only code reference."""
    return Provenance(code_ref="src/test.py:10")


@pytest.fixture
def valid_quantitative_result() -> Result:
    """Valid quantitative result fixture."""
    return Result(
        type="quantitative",
        point=0.987,
        effect_size=2.3,
        ci=(0.95, 1.02),
        p_value=0.001,
        posterior=0.999,
    )


@pytest.fixture
def valid_qualitative_result() -> Result:
    """Valid qualitative result fixture."""
    return Result(
        type="qualitative",
        finding="Successfully encoded all 1000 test molecules with unique IDs",
        artifact_ref="results/encoding_table.csv",
    )


@pytest.fixture
def null_result() -> Result:
    """Null result fixture (no significant effect)."""
    return Result(
        type="quantitative",
        point=0.02,
        ci=(-0.05, 0.09),
        p_value=0.57,
    )


@pytest.fixture
def valid_bearing(sample_hypothesis_id: Id) -> Bearing:
    """Valid supporting bearing fixture."""
    return Bearing(
        target_id=sample_hypothesis_id,
        direction=BearingDirection.SUPPORTS,
        weight=1.0,
    )


@pytest.fixture
def refuting_bearing(sample_hypothesis_id: Id) -> Bearing:
    """Refuting bearing fixture."""
    return Bearing(
        target_id=sample_hypothesis_id,
        direction=BearingDirection.REFUTES,
        weight=0.8,
    )


@pytest.fixture
def neutral_bearing(sample_hypothesis_id: Id) -> Bearing:
    """Neutral bearing fixture."""
    return Bearing(
        target_id=sample_hypothesis_id,
        direction=BearingDirection.NEUTRAL,
    )


@pytest.fixture
def inconclusive_bearing(sample_hypothesis_id: Id) -> Bearing:
    """Inconclusive bearing fixture."""
    return Bearing(
        target_id=sample_hypothesis_id,
        direction=BearingDirection.INCONCLUSIVE,
    )


@pytest.fixture
def valid_evidence_item(
    sample_evidence_id: Id,
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
    valid_provenance: Provenance,
    valid_quantitative_result: Result,
    valid_bearing: Bearing,
) -> EvidenceItem:
    """Valid evidence item fixture."""
    return EvidenceItem(
        id=sample_evidence_id,
        created_at=datetime(2026, 5, 26, 12, 30, 0),
        spec_id=sample_spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=valid_provenance,
        result=valid_quantitative_result,
        bears_on=[valid_bearing],
    )


@pytest.fixture
def literature_evidence(
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
    valid_provenance: Provenance,
    valid_qualitative_result: Result,
    valid_bearing: Bearing,
) -> EvidenceItem:
    """Literature evidence fixture."""
    return EvidenceItem(
        id="evi-literature-001",
        created_at=datetime(2026, 5, 26, 13, 0, 0),
        spec_id=sample_spec_id,
        kind=EvidenceKind.LITERATURE,
        provenance=valid_provenance,
        result=valid_qualitative_result,
        bears_on=[valid_bearing],
    )


@pytest.fixture
def counterexample_evidence(
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
    valid_provenance: Provenance,
    refuting_bearing: Bearing,
) -> EvidenceItem:
    """Counterexample evidence fixture."""
    return EvidenceItem(
        id="evi-counter-001",
        created_at=datetime(2026, 5, 26, 14, 0, 0),
        spec_id=sample_spec_id,
        kind=EvidenceKind.COUNTEREXAMPLE,
        provenance=valid_provenance,
        result=Result(
            type="qualitative",
            finding="Found molecule graph with no valid encoding",
        ),
        bears_on=[refuting_bearing],
    )


@pytest.fixture
def valid_confidence() -> Confidence:
    """Valid credence-based confidence fixture."""
    return Confidence(
        type=ConfidenceType.CREDENCE,
        value=0.95,
        basis="Strong experimental support",
    )


@pytest.fixture
def posterior_confidence() -> Confidence:
    """Valid posterior-based confidence fixture."""
    return Confidence(
        type=ConfidenceType.POSTERIOR,
        value=0.99,
        basis="Bayesian update with strong prior and conclusive evidence",
    )


@pytest.fixture
def graded_confidence() -> Confidence:
    """Valid graded confidence fixture."""
    return Confidence(
        type=ConfidenceType.GRADED,
        level=ConfidenceLevel.STRONG,
        basis="Multiple independent confirmations across diverse test cases",
    )


@pytest.fixture
def valid_claim(
    sample_claim_id: Id,
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
    valid_confidence: Confidence,
) -> Claim:
    """Valid claim fixture."""
    return Claim(
        id=sample_claim_id,
        spec_id=sample_spec_id,
        answers=sample_hypothesis_id,
        statement="Molecule graphs admit a bijective Gödel-style encoding",
        status=ClaimStatus.PROPOSED,
        confidence=valid_confidence,
        evidence_set=[],
        scope_limitations="Tested on molecules up to 50 atoms",
        mode=HypothesisMode.CONFIRMATORY,
        history=[],
    )


@pytest.fixture
def supported_claim(
    sample_claim_id: Id,
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
    valid_confidence: Confidence,
    sample_evidence_id: Id,
) -> Claim:
    """Claim in supported status with evidence."""
    claim = Claim(
        id=sample_claim_id,
        spec_id=sample_spec_id,
        answers=sample_hypothesis_id,
        statement="Molecule graphs admit a bijective Gödel-style encoding",
        status=ClaimStatus.SUPPORTED,
        confidence=valid_confidence,
        evidence_set=[
            EvidenceLink(evidence_id=sample_evidence_id, role=EvidenceLinkRole.SUPPORTING)
        ],
        scope_limitations="Tested on molecules up to 50 atoms",
        mode=HypothesisMode.CONFIRMATORY,
        history=[
            StatusChange(
                at=datetime(2026, 5, 26, 13, 0, 0),
                from_status=ClaimStatus.PROPOSED,
                to_status=ClaimStatus.SUPPORTED,
                triggered_by=sample_evidence_id,
                note="Initial evidence supports hypothesis",
            )
        ],
    )
    return claim


@pytest.fixture
def contested_claim(
    sample_claim_id: Id,
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
    sample_evidence_id: Id,
) -> Claim:
    """Claim with conflicting evidence (contested status)."""
    return Claim(
        id=sample_claim_id,
        spec_id=sample_spec_id,
        answers=sample_hypothesis_id,
        statement="Molecule graphs admit a bijective Gödel-style encoding",
        status=ClaimStatus.CONTESTED,
        confidence=Confidence(
            type=ConfidenceType.GRADED,
            level=ConfidenceLevel.MODERATE,
            basis="Conflicting evidence: strong support but counterexamples exist",
        ),
        evidence_set=[
            EvidenceLink(evidence_id="evi-support-001", role=EvidenceLinkRole.SUPPORTING),
            EvidenceLink(evidence_id="evi-refute-001", role=EvidenceLinkRole.REFUTING),
        ],
        scope_limitations="Counterexamples found in complex molecular structures",
        mode=HypothesisMode.CONFIRMATORY,
        history=[
            StatusChange(
                at=datetime(2026, 5, 26, 14, 0, 0),
                from_status=ClaimStatus.SUPPORTED,
                to_status=ClaimStatus.CONTESTED,
                triggered_by="evi-refute-001",
                note="Counterexample evidence found",
            )
        ],
    )


@pytest.fixture
def exploratory_claim(
    sample_claim_id: Id,
    sample_spec_id: Id,
    graded_confidence: Confidence,
) -> Claim:
    """Exploratory mode claim fixture."""
    return Claim(
        id=f"{sample_claim_id}-exp",
        spec_id=sample_spec_id,
        answers="hyp-exploratory-001",
        statement="Graph neural networks improve encoding efficiency",
        status=ClaimStatus.PROPOSED,
        confidence=graded_confidence,
        evidence_set=[],
        scope_limitations="",
        mode=HypothesisMode.EXPLORATORY,
        history=[],
    )


@pytest.fixture
def null_result_claim(
    sample_claim_id: Id,
    sample_spec_id: Id,
    sample_hypothesis_id: Id,
) -> Claim:
    """Claim representing null result."""
    return Claim.create_null_result_claim(
        id=sample_claim_id,
        spec_id=sample_spec_id,
        answers=sample_hypothesis_id,
        statement="No evidence for encoding performance improvement with GNNs",
        mode=HypothesisMode.CONFIRMATORY,
        basis="No evidence found for encoding performance improvement after testing 1000 variants (p=0.67)",
    )
