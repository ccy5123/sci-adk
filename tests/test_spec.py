"""
Unit tests for Spec core type.

Tests cover invariants S1-S5 from design/abstractions.md:
    S1: Frozen Spec version is immutable; changes create version+1
    S2: Every Hypothesis has exactly one mode and one DecisionRule
    S3: DecisionRule expresses how continuous/uncertain evidence maps
    S4: TargetClaim.answers references an existing Hypothesis.id
    S5: Amending a frozen Spec requires human checkpoint

Test Categories:
1. Spec creation and validation
2. Invariant S1: Immutability and versioning
3. Invariant S2: Single mode and DecisionRule
4. Invariant S3: DecisionRule validation
5. Invariant S4: TargetClaim reference validity
6. Invariant S5: Amendment requirements
7. JSON serialization
8. Edge cases and error conditions
"""

import pytest
from datetime import datetime, timezone

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

from tests.fixtures import (
    amended_spec,
    exploratory_hypothesis,
    multi_hypothesis_spec,
    valid_decision_rule,
    valid_hypothesis,
    valid_interval_decision_rule,
    valid_method_plan,
    valid_proof_decision_rule,
    valid_qualitative_decision_rule,
    valid_raw_proposal,
    valid_spec,
    valid_target_claim,
    valid_threshold_decision_rule,
)


class TestSpecCreation:
    """Tests for Spec creation with valid data."""

    def test_create_minimal_spec(self):
        """Test creating a valid Spec with minimal required fields."""
        spec = Spec(
            id="spec-minimal",
            raw_proposal=RawProposal(
                background="Test background",
                goal="Test goal",
                method="Test method",
                expected_output="Test output",
            ),
            hypotheses=[
                Hypothesis(
                    id="hyp-1",
                    statement="Test hypothesis",
                    mode=HypothesisMode.CONFIRMATORY,
                    decision_rule=DecisionRule(
                        kind=DecisionRuleKind.THRESHOLD,
                        expression="test >= 0.5",
                        params={"threshold": 0.5},
                    ),
                )
            ],
            method=MethodPlan(approaches=["test approach"]),
        )

        assert spec.id == "spec-minimal"
        assert spec.version == 1
        assert len(spec.hypotheses) == 1
        assert spec.amendment_rationale is None
        assert spec.prior_version_id is None

    def test_spec_auto_generates_created_at(self, valid_hypothesis):
        """Test that Spec auto-generates created_at timestamp."""
        before = datetime.now(timezone.utc)
        spec = Spec(
            id="spec-timestamp",
            raw_proposal=RawProposal(
                background="B", goal="G", method="M", expected_output="O"
            ),
            hypotheses=[valid_hypothesis],
            method=MethodPlan(),
        )
        after = datetime.now(timezone.utc)

        assert before <= spec.created_at <= after

    def test_spec_with_all_components(self, valid_spec):
        """Test creating a Spec with all optional components."""
        assert valid_spec.id == "spec-test-001"
        assert len(valid_spec.hypotheses) == 1
        assert len(valid_spec.method.approaches) == 3
        assert len(valid_spec.method.tools) == 2
        assert len(valid_spec.target_claims) == 1


class TestInvariantS1_Immutability:
    """Tests for Invariant S1: Frozen Spec version is immutable."""

    def test_spec_is_frozen(self, valid_spec):
        """Test that Spec instances are frozen (immutable)."""
        # Pydantic v2 models with frozen=True raise ValidationError on mutation
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_spec.id = "new-id"

    def test_raw_proposal_is_frozen(self, valid_raw_proposal):
        """Test that RawProposal is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_raw_proposal.background = "new background"

    def test_hypothesis_is_frozen(self, valid_hypothesis):
        """Test that Hypothesis is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_hypothesis.statement = "new statement"

    def test_decision_rule_is_frozen(self, valid_decision_rule):
        """Test that DecisionRule is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_decision_rule.expression = "new expression"

    def test_target_claim_is_frozen(self, valid_target_claim):
        """Test that TargetClaim is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_target_claim.statement = "new statement"

    def test_method_plan_is_frozen(self, valid_method_plan):
        """Test that MethodPlan is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_method_plan.approaches = ["new"]


class TestInvariantS2_SingleModeAndRule:
    """Tests for Invariant S2: Every Hypothesis has exactly one mode and one DecisionRule."""

    def test_hypothesis_has_single_mode(self, valid_hypothesis):
        """Test that Hypothesis has exactly one mode."""
        assert isinstance(valid_hypothesis.mode, HypothesisMode)
        assert valid_hypothesis.mode in (HypothesisMode.CONFIRMATORY, HypothesisMode.EXPLORATORY)

    def test_hypothesis_has_single_decision_rule(self, valid_hypothesis):
        """Test that Hypothesis has exactly one DecisionRule."""
        assert isinstance(valid_hypothesis.decision_rule, DecisionRule)
        assert valid_hypothesis.decision_rule.kind in DecisionRuleKind

    def test_confirmatory_mode(self, valid_hypothesis):
        """Test confirmatory mode hypothesis."""
        assert valid_hypothesis.mode == HypothesisMode.CONFIRMATORY

    def test_exploratory_mode(self, exploratory_hypothesis):
        """Test exploratory mode hypothesis."""
        assert exploratory_hypothesis.mode == HypothesisMode.EXPLORATORY

    def test_mode_is_required_field(self):
        """Test that mode is required for Hypothesis creation."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Hypothesis(
                id="hyp-no-mode",
                statement="Test",
                # mode missing
                decision_rule=valid_decision_rule,
            )


class TestInvariantS3_DecisionRuleValidation:
    """Tests for Invariant S3: DecisionRule expresses continuous/uncertain evidence mapping."""

    def test_bayesian_rule_with_params(self, valid_decision_rule):
        """Test Bayesian rule with required params."""
        assert valid_decision_rule.kind == DecisionRuleKind.BAYESIAN
        assert valid_decision_rule.params is not None
        assert "min_odds" in valid_decision_rule.params

    def test_threshold_rule_requires_params(self):
        """Test that threshold rules require params."""
        with pytest.raises(ValueError, match="require params"):
            DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="accuracy >= 0.95",
                # params missing - should raise
            )

    def test_bayesian_rule_requires_params(self):
        """Test that Bayesian rules require params."""
        with pytest.raises(ValueError, match="require params"):
            DecisionRule(
                kind=DecisionRuleKind.BAYESIAN,
                expression="posterior > 0.9",
                # params missing - should raise
            )

    def test_interval_rule_valid(self, valid_interval_decision_rule):
        """Test interval decision rule is valid."""
        assert valid_interval_decision_rule.kind == DecisionRuleKind.INTERVAL
        assert valid_interval_decision_rule.params is not None

    def test_proof_rule_valid(self, valid_proof_decision_rule):
        """Test proof decision rule is valid."""
        assert valid_proof_decision_rule.kind == DecisionRuleKind.PROOF

    def test_qualitative_rule_valid(self, valid_qualitative_decision_rule):
        """Test qualitative decision rule is valid."""
        assert valid_qualitative_decision_rule.kind == DecisionRuleKind.QUALITATIVE

    def test_expression_not_empty(self):
        """Test that expression cannot be empty."""
        with pytest.raises(Exception):
            DecisionRule(
                kind=DecisionRuleKind.QUALITATIVE,
                expression="",  # Empty expression
            )

    def test_expression_is_stripped(self):
        """Test that expression whitespace is stripped."""
        rule = DecisionRule(
            kind=DecisionRuleKind.QUALITATIVE,
            expression="  test expression  ",
        )
        assert rule.expression == "test expression"


class TestInvariantS4_TargetClaimReferences:
    """Tests for Invariant S4: TargetClaim.answers references existing Hypothesis.id."""

    def test_valid_target_claim_reference(self, valid_spec):
        """Test that valid TargetClaim reference is accepted."""
        target_claim = valid_spec.target_claims[0]
        hypothesis_ids = {h.id for h in valid_spec.hypotheses}
        assert target_claim.answers in hypothesis_ids

    def test_invalid_target_claim_reference_raises(self, valid_threshold_decision_rule):
        """Test that invalid TargetClaim reference raises ValueError."""
        with pytest.raises(ValueError, match="unknown hypothesis"):
            Spec(
                id="spec-invalid-ref",
                raw_proposal=RawProposal(
                    background="B", goal="G", method="M", expected_output="O"
                ),
                hypotheses=[
                    Hypothesis(
                        id="hyp-1",
                        statement="H1",
                        mode=HypothesisMode.CONFIRMATORY,
                        decision_rule=valid_threshold_decision_rule,
                    )
                ],
                method=MethodPlan(),
                target_claims=[
                    TargetClaim(
                        id="claim-1",
                        statement="C1",
                        answers="nonexistent-hyp",  # Invalid reference
                    )
                ],
            )

    def test_multiple_claims_reference_same_hypothesis(self, multi_hypothesis_spec):
        """Test that multiple claims can reference the same hypothesis."""
        # Find claims referencing the first hypothesis
        hyp_id = multi_hypothesis_spec.hypotheses[0].id
        matching_claims = [
            c for c in multi_hypothesis_spec.target_claims if c.answers == hyp_id
        ]
        assert len(matching_claims) >= 1

    def test_multiple_claims_different_hypotheses(self, multi_hypothesis_spec):
        """Test that claims can reference different hypotheses."""
        hypothesis_ids = {h.id for h in multi_hypothesis_spec.hypotheses}
        claim_answers = {c.answers for c in multi_hypothesis_spec.target_claims}

        assert claim_answers.issubset(hypothesis_ids)


class TestInvariantS5_AmendmentRequirements:
    """Tests for Invariant S5: Amending Spec requires human checkpoint."""

    def test_amend_creates_new_version(self, valid_spec, valid_threshold_decision_rule):
        """Test that amend() creates a new Spec with incremented version."""
        amended = valid_spec.amend(
            hypotheses=[
                Hypothesis(
                    id="hyp-new",
                    statement="New hypothesis",
                    mode=HypothesisMode.CONFIRMATORY,
                    decision_rule=valid_threshold_decision_rule,
                )
            ],
            target_claims=[],  # Clear existing claims that reference old hypotheses
            rationale="Test amendment",
        )

        assert amended.version == valid_spec.version + 1
        assert amended.id == valid_spec.id  # Same spec id
        assert amended.amendment_rationale == "Test amendment"

    def test_amend_requires_rationale(self, valid_spec):
        """Test that amend() requires non-empty rationale."""
        with pytest.raises(ValueError, match="Amendment requires non-empty rationale"):
            valid_spec.amend(
                rationale="",  # Empty rationale
            )

        with pytest.raises(ValueError, match="Amendment requires non-empty rationale"):
            valid_spec.amend(
                rationale="   ",  # Whitespace only
            )

    def test_amend_preserves_prior_version_id(self, valid_spec):
        """Test that amend() records prior version reference."""
        amended = valid_spec.amend(rationale="Test")

        assert amended.prior_version_id is not None
        assert amended.prior_version_id == str(valid_spec.created_at.timestamp())

    def test_amend_keeps_existing_components(self, valid_spec):
        """Test that amend() keeps unchanged components."""
        original_hyp_count = len(valid_spec.hypotheses)

        amended = valid_spec.amend(
            rationale="Updated method only",
            method=MethodPlan(approaches=["new approach"]),
        )

        # Hypotheses should be unchanged
        assert len(amended.hypotheses) == original_hyp_count
        # Method should be new
        assert amended.method.approaches == ["new approach"]

    def test_amend_all_components(self, valid_spec, valid_threshold_decision_rule):
        """Test amending all components at once."""
        new_proposal = RawProposal(
            background="Updated background",
            goal="Updated goal",
            method="Updated method",
            expected_output="Updated output",
        )

        amended = valid_spec.amend(
            raw_proposal=new_proposal,
            hypotheses=[
                Hypothesis(
                    id="hyp-revised",
                    statement="Revised",
                    mode=HypothesisMode.CONFIRMATORY,
                    decision_rule=valid_threshold_decision_rule,
                )
            ],
            method=MethodPlan(approaches=["revised"]),
            target_claims=[
                TargetClaim(
                    id="claim-revised",
                    statement="Revised claim",
                    answers="hyp-revised",
                )
            ],
            rationale="Complete revision",
        )

        assert amended.raw_proposal.background == "Updated background"
        assert len(amended.hypotheses) == 1
        assert amended.hypotheses[0].id == "hyp-revised"
        assert amended.method.approaches == ["revised"]
        assert len(amended.target_claims) == 1
        assert amended.target_claims[0].id == "claim-revised"

    def test_amend_multiple_times(self, valid_spec):
        """Test amending a spec multiple times."""
        # First amendment
        v2 = valid_spec.amend(rationale="First amendment")
        assert v2.version == 2

        # Second amendment
        v3 = v2.amend(rationale="Second amendment")
        assert v3.version == 3

        # Chain should be preserved
        assert v3.prior_version_id == str(v2.created_at.timestamp())


class TestSpecRetrievalMethods:
    """Tests for Spec helper methods."""

    def test_get_hypothesis_by_id(self, valid_spec):
        """Test retrieving hypothesis by id."""
        hypothesis = valid_spec.get_hypothesis("hyp-test-encoding")
        assert hypothesis is not None
        assert hypothesis.id == "hyp-test-encoding"

    def test_get_hypothesis_not_found(self, valid_spec):
        """Test retrieving non-existent hypothesis returns None."""
        hypothesis = valid_spec.get_hypothesis("nonexistent")
        assert hypothesis is None

    def test_get_target_claim_by_id(self, valid_spec):
        """Test retrieving target claim by id."""
        claim = valid_spec.get_target_claim("claim-target-001")
        assert claim is not None
        assert claim.id == "claim-target-001"

    def test_get_target_claim_not_found(self, valid_spec):
        """Test retrieving non-existent target claim returns None."""
        claim = valid_spec.get_target_claim("nonexistent")
        assert claim is None

    def test_get_hypothesis_from_multi_hypothesis_spec(self, multi_hypothesis_spec):
        """Test retrieval from spec with multiple hypotheses."""
        hyp1 = multi_hypothesis_spec.get_hypothesis("hyp-test-encoding")
        hyp2 = multi_hypothesis_spec.get_hypothesis("hyp-exploratory-001")

        assert hyp1 is not None
        assert hyp2 is not None
        assert hyp1.id != hyp2.id


class TestJSONSerialization:
    """Tests for JSON serialization/deserialization."""

    def test_spec_model_dump(self, valid_spec):
        """Test Spec serialization to dict."""
        data = valid_spec.model_dump()

        assert data["id"] == "spec-test-001"
        assert data["version"] == 1
        assert "raw_proposal" in data
        assert "hypotheses" in data
        assert len(data["hypotheses"]) == 1

    def test_spec_model_dump_json(self, valid_spec):
        """Test Spec serialization to JSON string."""
        json_str = valid_spec.model_dump_json()

        assert isinstance(json_str, str)
        assert "spec-test-001" in json_str
        assert "version" in json_str

    def test_hypothesis_serialization(self, valid_hypothesis):
        """Test Hypothesis serialization."""
        data = valid_hypothesis.model_dump()

        assert data["id"] == "hyp-test-encoding"
        assert data["mode"] == "confirmatory"
        assert "decision_rule" in data

    def test_decision_rule_serialization(self, valid_decision_rule):
        """Test DecisionRule serialization."""
        data = valid_decision_rule.model_dump()

        assert data["kind"] == "bayesian"
        assert data["expression"] == "posterior odds > 10 => support"
        assert data["params"]["min_odds"] == 10.0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_hypotheses_raises(self):
        """Test that Spec with empty hypotheses list raises ValueError."""
        with pytest.raises(ValueError, match="at least one hypothesis"):
            Spec(
                id="spec-no-hyp",
                raw_proposal=RawProposal(
                    background="B", goal="G", method="M", expected_output="O"
                ),
                hypotheses=[],  # Empty list
                method=MethodPlan(),
            )

    def test_empty_target_claims_allowed(self, valid_hypothesis):
        """Test that empty target_claims list is allowed."""
        spec = Spec(
            id="spec-no-claims",
            raw_proposal=RawProposal(
                background="B", goal="G", method="M", expected_output="O"
            ),
            hypotheses=[valid_hypothesis],
            method=MethodPlan(),
            target_claims=[],  # Empty list should be OK
        )
        assert len(spec.target_claims) == 0

    def test_empty_method_approaches_allowed(self, valid_hypothesis):
        """Test that empty method approaches is allowed."""
        spec = Spec(
            id="spec-no-approaches",
            raw_proposal=RawProposal(
                background="B", goal="G", method="M", expected_output="O"
            ),
            hypotheses=[valid_hypothesis],
            method=MethodPlan(approaches=[]),
        )
        assert len(spec.method.approaches) == 0

    def test_method_without_tools(self):
        """Test MethodPlan without tools."""
        method = MethodPlan(approaches=["test"])
        assert method.tools is None

    def test_version_ge_1(self):
        """Test that version must be >= 1."""
        with pytest.raises(Exception):
            Spec(
                id="spec-bad-version",
                version=0,  # Invalid
                raw_proposal=RawProposal(
                    background="B", goal="G", method="M", expected_output="O"
                ),
                hypotheses=[valid_hypothesis],
                method=MethodPlan(),
            )

    def test_all_decision_rule_kinds(self):
        """Test creating rules with all valid kinds."""
        kinds = [
            DecisionRuleKind.THRESHOLD,
            DecisionRuleKind.BAYESIAN,
            DecisionRuleKind.INTERVAL,
            DecisionRuleKind.PROOF,
            DecisionRuleKind.QUALITATIVE,
        ]

        # Decision 3 (design/decision-engine.md): INTERVAL now requires params
        # too (null_value + support side), alongside THRESHOLD and BAYESIAN.
        params_required = (
            DecisionRuleKind.THRESHOLD,
            DecisionRuleKind.BAYESIAN,
            DecisionRuleKind.INTERVAL,
        )
        for kind in kinds:
            rule = DecisionRule(
                kind=kind,
                expression=f"Expression for {kind}",
                params={"test": 1.0} if kind in params_required else None,
            )
            assert rule.kind == kind


class TestRawProposal:
    """Tests for RawProposal component."""

    def test_raw_proposal_creation(self, valid_raw_proposal):
        """Test creating a valid RawProposal."""
        assert valid_raw_proposal.background == "Molecule graphs represent chemical structures as graph objects."
        assert valid_raw_proposal.goal.startswith("Determine if")
        assert valid_raw_proposal.method.startswith("Implement")
        assert valid_raw_proposal.expected_output.startswith("Proof")

    def test_raw_proposal_required_fields(self):
        """Test that all RawProposal fields are required."""
        with pytest.raises(Exception):
            RawProposal(
                background="B",
                goal="G",
                # method missing
                expected_output="O",
            )

    def test_raw_proposal_whitespace_stripping(self):
        """Test that RawProposal fields strip whitespace."""
        proposal = RawProposal(
            background="  test background  ",
            goal="\ttest goal\t",
            method="  test method  ",
            expected_output="\ntest output\n",
        )

        assert proposal.background == "test background"
        assert proposal.goal == "test goal"
        assert proposal.method == "test method"
        assert proposal.expected_output == "test output"


class TestMethodPlan:
    """Tests for MethodPlan component."""

    def test_method_plan_creation(self, valid_method_plan):
        """Test creating a valid MethodPlan."""
        assert len(valid_method_plan.approaches) == 3
        assert len(valid_method_plan.tools) == 2

    def test_tool_ref_creation(self):
        """Test creating ToolRef."""
        tool = ToolRef(name="pytest", version="8.0.0", kind="testing")
        assert tool.name == "pytest"
        assert tool.version == "8.0.0"
        assert tool.kind == "testing"

    def test_tool_ref_without_version(self):
        """Test ToolRef without version."""
        tool = ToolRef(name="python", kind="language")
        assert tool.version is None

    def test_tool_ref_default_kind(self):
        """Test ToolRef default kind is 'tool'."""
        tool = ToolRef(name="test-tool")
        assert tool.kind == "tool"
