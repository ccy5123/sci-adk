"""
Unit tests for Claim core type.

Tests cover invariants C1-C6 from design/abstractions.md:
    C1: status may move in any direction (supported -> contested -> refuted)
    C2: history is append-only - every change appends a StatusChange
    C3: confidence.basis is the load-bearing field and always required
    C4: Null results are expressible (e.g., "no evidence for effect X")
    C5: evidence_set includes refuting links, not only supporting
    C6: exploratory claims cannot be presented as confirmatory

Test Categories:
1. Claim creation and validation
2. Invariant C1: Status transitions in any direction
3. Invariant C2: Append-only history
4. Invariant C3: confidence.basis requirement
5. Invariant C4: Null result expressibility
6. Invariant C5: Refuting evidence inclusion
7. Invariant C6: Exploratory mode labeling
8. Confidence type validations
9. Evidence link management
10. JSON serialization
11. Edge cases and error conditions
"""

import pytest
from datetime import datetime

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
from sci_adk.core.spec import HypothesisMode, Id

from tests.fixtures import (
    contested_claim,
    exploratory_claim,
    exploratory_hypothesis,
    graded_confidence,
    null_result_claim,
    posterior_confidence,
    supported_claim,
    valid_claim,
    valid_confidence,
    sample_claim_id,
    sample_evidence_id,
    sample_hypothesis_id,
    sample_spec_id,
)


class TestClaimCreation:
    """Tests for Claim creation with valid data."""

    def test_create_minimal_claim(self):
        """Test creating a valid Claim with minimal required fields."""
        claim = Claim(
            id="claim-minimal",
            spec_id="spec-001",
            answers="hyp-001",
            statement="Test claim statement",
            confidence=Confidence(
                type=ConfidenceType.CREDENCE,
                value=0.8,
                basis="Test basis",
            ),
            mode=HypothesisMode.CONFIRMATORY,
        )

        assert claim.id == "claim-minimal"
        assert claim.status == ClaimStatus.PROPOSED  # Default status
        assert len(claim.evidence_set) == 0
        assert len(claim.history) == 0

    def test_create_claim_with_all_fields(self, valid_claim):
        """Test creating a Claim with all fields."""
        assert valid_claim.id == "claim-test-encoding"
        assert valid_claim.spec_id == "spec-test-001"
        assert valid_claim.statement.startswith("Molecule graphs")
        assert valid_claim.status == ClaimStatus.PROPOSED
        assert len(valid_claim.scope_limitations) > 0

    def test_claim_default_status(self):
        """Test that Claim defaults to PROPOSED status."""
        claim = Claim(
            id="claim-default",
            spec_id="spec-001",
            answers="hyp-001",
            statement="Test",
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.WEAK,
                basis="Test",
            ),
            mode=HypothesisMode.EXPLORATORY,
        )

        assert claim.status == ClaimStatus.PROPOSED

    def test_claim_revisable_not_frozen(self, valid_claim):
        """Test that Claim is not frozen (revisable belief state)."""
        # Unlike Spec/Evidence, Claim allows mutation
        valid_claim.status = ClaimStatus.SUPPORTED
        assert valid_claim.status == ClaimStatus.SUPPORTED


class TestInvariantC1_StatusTransitions:
    """Tests for Invariant C1: status may move in any direction."""

    def test_proposed_to_supported(self, valid_claim, sample_evidence_id):
        """Test transition from PROPOSED to SUPPORTED."""
        valid_claim.update_status(
            new_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
            note="Strong evidence found",
        )

        assert valid_claim.status == ClaimStatus.SUPPORTED
        assert len(valid_claim.history) == 1

    def test_supported_to_contested(self, supported_claim, sample_evidence_id):
        """Test transition from SUPPORTED to CONTESTED (regression allowed)."""
        supported_claim.update_status(
            new_status=ClaimStatus.CONTESTED,
            triggered_by=sample_evidence_id,
            note="Conflicting evidence found",
        )

        assert supported_claim.status == ClaimStatus.CONTESTED

    def test_contested_to_refuted(self, contested_claim, sample_evidence_id):
        """Test transition from CONTESTED to REFUTED."""
        contested_claim.update_status(
            new_status=ClaimStatus.REFUTED,
            triggered_by=sample_evidence_id,
            note="Counterexample confirmed",
        )

        assert contested_claim.status == ClaimStatus.REFUTED

    def test_refuted_to_supported(self, sample_claim_id, sample_spec_id, sample_hypothesis_id, sample_evidence_id):
        """Test transition from REFUTED back to SUPPORTED (full reversal)."""
        claim = Claim(
            id=sample_claim_id,
            spec_id=sample_spec_id,
            answers=sample_hypothesis_id,
            statement="Test claim",
            status=ClaimStatus.REFUTED,
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.NONE,
                basis="Previously refuted",
            ),
            mode=HypothesisMode.CONFIRMATORY,
        )

        claim.update_status(
            new_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
            note="Original refutation was based on faulty data",
        )

        assert claim.status == ClaimStatus.SUPPORTED

    def test_supported_to_retracted(self, supported_claim, sample_evidence_id):
        """Test transition from SUPPORTED to RETRACTED."""
        supported_claim.update_status(
            new_status=ClaimStatus.RETRACTED,
            triggered_by=sample_evidence_id,
            note="Reproducibility failure - unable to replicate",
        )

        assert supported_claim.status == ClaimStatus.RETRACTED

    def test_all_status_values_are_valid(self):
        """Test that all ClaimStatus enum values are valid."""
        statuses = [
            ClaimStatus.PROPOSED,
            ClaimStatus.SUPPORTED,
            ClaimStatus.CONTESTED,
            ClaimStatus.REFUTED,
            ClaimStatus.RETRACTED,
        ]

        for status in statuses:
            claim = Claim(
                id=f"claim-{status.value}",
                spec_id="spec-001",
                answers="hyp-001",
                statement="Test",
                confidence=Confidence(
                    type=ConfidenceType.GRADED,
                    level=ConfidenceLevel.WEAK,
                    basis="Test",
                ),
                status=status,
                mode=HypothesisMode.CONFIRMATORY,
            )
            assert claim.status == status


class TestInvariantC2_AppendOnlyHistory:
    """Tests for Invariant C2: history is append-only."""

    def test_update_status_appends_to_history(self, valid_claim, sample_evidence_id):
        """Test that status change appends to history."""
        initial_history_len = len(valid_claim.history)

        valid_claim.update_status(
            new_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
            note="Evidence supports claim",
        )

        assert len(valid_claim.history) == initial_history_len + 1

    def test_history_records_status_change(self, valid_claim, sample_evidence_id):
        """Test that history records all status change details."""
        valid_claim.update_status(
            new_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
            note="Test note",
        )

        change = valid_claim.history[-1]
        assert change.from_status == ClaimStatus.PROPOSED
        assert change.to_status == ClaimStatus.SUPPORTED
        assert change.triggered_by == sample_evidence_id
        assert change.note == "Test note"

    def test_history_preserves_all_changes(self, sample_claim_id, sample_spec_id, sample_hypothesis_id, sample_evidence_id):
        """Test that history preserves entire status journey."""
        claim = Claim(
            id=sample_claim_id,
            spec_id=sample_spec_id,
            answers=sample_hypothesis_id,
            statement="Test",
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.WEAK,
                basis="Test",
            ),
            mode=HypothesisMode.CONFIRMATORY,
        )

        # Multiple status changes
        claim.update_status(ClaimStatus.SUPPORTED, f"{sample_evidence_id}-1", "Initial support")
        claim.update_status(ClaimStatus.CONTESTED, f"{sample_evidence_id}-2", "Counterexample")
        claim.update_status(ClaimStatus.REFUTED, f"{sample_evidence_id}-3", "Confirmed refutation")

        assert len(claim.history) == 3
        assert claim.history[0].to_status == ClaimStatus.SUPPORTED
        assert claim.history[1].to_status == ClaimStatus.CONTESTED
        assert claim.history[2].to_status == ClaimStatus.REFUTED

    def test_history_is_not_cleared_on_status_update(self, supported_claim, sample_evidence_id):
        """Test that history is preserved when status updates."""
        original_history = list(supported_claim.history)  # Copy
        original_len = len(original_history)

        supported_claim.update_status(
            new_status=ClaimStatus.CONTESTED,
            triggered_by=sample_evidence_id,
        )

        # Original history entries should be preserved
        for i, change in enumerate(original_history):
            assert supported_claim.history[i].at == change.at
            assert supported_claim.history[i].from_status == change.from_status
            assert supported_claim.history[i].to_status == change.to_status

        # New entry added
        assert len(supported_claim.history) == original_len + 1

    def test_status_change_has_timestamp(self, valid_claim, sample_evidence_id):
        """Test that status change records timestamp."""
        before = datetime.utcnow()
        valid_claim.update_status(
            new_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
        )
        after = datetime.utcnow()

        change = valid_claim.history[-1]
        assert before <= change.at <= after


class TestInvariantC3_ConfidenceBasis:
    """Tests for Invariant C3: confidence.basis is always required."""

    def test_confidence_requires_basis(self):
        """Test that Confidence requires non-empty basis."""
        with pytest.raises(ValueError, match="basis is required"):
            Confidence(
                type=ConfidenceType.CREDENCE,
                value=0.9,
                basis="",  # Empty basis
            )

        with pytest.raises(ValueError, match="must not be empty"):
            Confidence(
                type=ConfidenceType.CREDENCE,
                value=0.9,
                basis="   ",  # Whitespace only
            )

    def test_credence_requires_value(self):
        """Test that credence type requires value field."""
        with pytest.raises(ValueError, match="requires value field"):
            Confidence(
                type=ConfidenceType.CREDENCE,
                value=None,  # Missing value
                basis="Test basis",
            )

    def test_posterior_requires_value(self):
        """Test that posterior type requires value field."""
        with pytest.raises(ValueError, match="requires value field"):
            Confidence(
                type=ConfidenceType.POSTERIOR,
                value=None,  # Missing value
                basis="Test basis",
            )

    def test_graded_requires_level(self):
        """Test that graded type requires level field."""
        with pytest.raises(ValueError, match="requires level field"):
            Confidence(
                type=ConfidenceType.GRADED,
                level=None,  # Missing level
                basis="Test basis",
            )

    def test_confidence_value_bounds(self):
        """Test that confidence value is within [0, 1]."""
        # Valid values
        Confidence(
            type=ConfidenceType.CREDENCE,
            value=0.0,
            basis="Test",
        )
        Confidence(
            type=ConfidenceType.CREDENCE,
            value=0.5,
            basis="Test",
        )
        Confidence(
            type=ConfidenceType.CREDENCE,
            value=1.0,
            basis="Test",
        )

        # Invalid values
        with pytest.raises(Exception):
            Confidence(
                type=ConfidenceType.CREDENCE,
                value=-0.1,
                basis="Test",
            )

        with pytest.raises(Exception):
            Confidence(
                type=ConfidenceType.CREDENCE,
                value=1.5,
                basis="Test",
            )

    def test_update_confidence_requires_basis(self, valid_claim):
        """Test that updating confidence requires basis."""
        with pytest.raises(ValueError, match="basis is required"):
            valid_claim.update_confidence(basis="")  # Empty basis

    def test_update_confidence_preserves_basis_if_not_provided(self, valid_claim):
        """Test that update_confidence preserves existing basis if not provided."""
        original_basis = valid_claim.confidence.basis
        valid_claim.update_confidence(value=0.99)

        assert valid_claim.confidence.basis == original_basis

    def test_all_confidence_levels(self):
        """Test all valid confidence levels."""
        levels = [
            ConfidenceLevel.STRONG,
            ConfidenceLevel.MODERATE,
            ConfidenceLevel.WEAK,
            ConfidenceLevel.NONE,
        ]

        for level in levels:
            conf = Confidence(
                type=ConfidenceType.GRADED,
                level=level,
                basis=f"Test for {level.value}",
            )
            assert conf.level == level


class TestInvariantC4_NullResultExpressibility:
    """Tests for Invariant C4: Null results are expressible."""

    def test_create_null_result_claim(self, null_result_claim):
        """Test creating a claim representing null result."""
        assert null_result_claim.status == ClaimStatus.SUPPORTED
        assert null_result_claim.statement.startswith("No evidence")
        assert null_result_claim.confidence.type == ConfidenceType.GRADED
        assert null_result_claim.confidence.level == ConfidenceLevel.MODERATE

    def test_null_result_has_confidence_on_absence(self, null_result_claim):
        """Test that null result claim has confidence over the ABSENCE."""
        assert "absence" in null_result_claim.confidence.basis.lower() or "no evidence" in null_result_claim.confidence.basis.lower()

    def test_null_result_with_custom_basis(self):
        """Test null result with custom basis."""
        claim = Claim.create_null_result_claim(
            id="claim-null-custom",
            spec_id="spec-001",
            answers="hyp-001",
            statement="No significant effect found",
            mode=HypothesisMode.CONFIRMATORY,
            basis="Multiple independent trials with p > 0.5 consistently",
        )

        assert "p > 0.5" in claim.confidence.basis

    def test_exploratory_null_result(self):
        """Test null result claim with exploratory mode."""
        claim = Claim.create_null_result_claim(
            id="claim-null-exp",
            spec_id="spec-001",
            answers="hyp-001",
            statement="No improvement found",
            mode=HypothesisMode.EXPLORATORY,
        )

        assert claim.mode == HypothesisMode.EXPLORATORY


class TestInvariantC5_RefutingEvidenceInclusion:
    """Tests for Invariant C5: evidence_set includes refuting links."""

    def test_evidence_set_includes_supporting(self, supported_claim):
        """Test that evidence_set can include supporting evidence."""
        supporting = supported_claim.get_supporting_evidence()
        assert len(supporting) > 0
        assert all(link.role == EvidenceLinkRole.SUPPORTING for link in supporting)

    def test_evidence_set_includes_refuting(self, contested_claim):
        """Test that evidence_set can include refuting evidence."""
        refuting = contested_claim.get_refuting_evidence()
        assert len(refuting) > 0
        assert all(link.role == EvidenceLinkRole.REFUTING for link in refuting)

    def test_has_conflicting_evidence(self, contested_claim):
        """Test detecting conflicting evidence."""
        assert contested_claim.has_conflicting_evidence()

    def test_no_conflicting_evidence_when_only_supporting(self, supported_claim):
        """Test that only supporting evidence is not conflicting."""
        assert not supported_claim.has_conflicting_evidence()

    def test_add_evidence_supporting(self, valid_claim):
        """Test adding supporting evidence."""
        valid_claim.add_evidence(
            evidence_id="evi-support-001",
            role=EvidenceLinkRole.SUPPORTING,
        )

        supporting = valid_claim.get_supporting_evidence()
        assert any(link.evidence_id == "evi-support-001" for link in supporting)

    def test_add_evidence_refuting(self, valid_claim):
        """Test adding refuting evidence."""
        valid_claim.add_evidence(
            evidence_id="evi-refute-001",
            role=EvidenceLinkRole.REFUTING,
        )

        refuting = valid_claim.get_refuting_evidence()
        assert any(link.evidence_id == "evi-refute-001" for link in refuting)

    def test_add_evidence_prevents_duplicates(self, valid_claim, sample_evidence_id):
        """Test that adding same evidence twice doesn't duplicate."""
        valid_claim.add_evidence(
            evidence_id=sample_evidence_id,
            role=EvidenceLinkRole.SUPPORTING,
        )

        initial_count = len(valid_claim.evidence_set)

        # Try adding same evidence again
        valid_claim.add_evidence(
            evidence_id=sample_evidence_id,
            role=EvidenceLinkRole.SUPPORTING,
        )

        assert len(valid_claim.evidence_set) == initial_count

    def test_add_both_supporting_and_refuting(self, valid_claim):
        """Test adding both supporting and refuting evidence."""
        valid_claim.add_evidence(
            evidence_id="evi-001",
            role=EvidenceLinkRole.SUPPORTING,
        )
        valid_claim.add_evidence(
            evidence_id="evi-002",
            role=EvidenceLinkRole.REFUTING,
        )

        assert valid_claim.has_conflicting_evidence()


class TestInvariantC6_ExploratoryMode:
    """Tests for Invariant C6: exploratory claims cannot be presented as confirmatory."""

    def test_exploratory_mode_claim(self, exploratory_claim):
        """Test creating exploratory mode claim."""
        assert exploratory_claim.mode == HypothesisMode.EXPLORATORY

    def test_confirmatory_mode_claim(self, valid_claim):
        """Test creating confirmatory mode claim."""
        assert valid_claim.mode == HypothesisMode.CONFIRMATORY

    def test_mode_is_required_field(self):
        """Test that mode is required."""
        with pytest.raises(Exception):
            Claim(
                id="claim-no-mode",
                spec_id="spec-001",
                answers="hyp-001",
                statement="Test",
                confidence=Confidence(
                    type=ConfidenceType.GRADED,
                    level=ConfidenceLevel.WEAK,
                    basis="Test",
                ),
                # mode missing
            )

    def test_exploratory_claim_labeled_correctly(self, exploratory_claim):
        """Test that exploratory claims are explicitly labeled."""
        # The mode field prevents misrepresentation
        assert exploratory_claim.mode == HypothesisMode.EXPLORATORY
        # This label should be preserved when presenting results


class TestClaimHelperMethods:
    """Tests for Claim helper methods."""

    def test_is_supported(self, supported_claim):
        """Test is_supported helper method."""
        assert supported_claim.is_supported()

    def test_is_contested(self, contested_claim):
        """Test is_contested helper method."""
        assert contested_claim.is_contested()

    def test_is_refuted(self, sample_claim_id, sample_spec_id, sample_hypothesis_id):
        """Test is_refuted helper method."""
        claim = Claim(
            id=sample_claim_id,
            spec_id=sample_spec_id,
            answers=sample_hypothesis_id,
            statement="Test",
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.NONE,
                basis="Test",
            ),
            status=ClaimStatus.REFUTED,
            mode=HypothesisMode.CONFIRMATORY,
        )
        assert claim.is_refuted()

    def test_is_retracted(self, sample_claim_id, sample_spec_id, sample_hypothesis_id):
        """Test is_retracted helper method."""
        claim = Claim(
            id=sample_claim_id,
            spec_id=sample_spec_id,
            answers=sample_hypothesis_id,
            statement="Test",
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.NONE,
                basis="Test",
            ),
            status=ClaimStatus.RETRACTED,
            mode=HypothesisMode.CONFIRMATORY,
        )
        assert claim.is_retracted()

    def test_get_supporting_evidence(self, contested_claim):
        """Test getting supporting evidence links."""
        supporting = contested_claim.get_supporting_evidence()
        assert len(supporting) == 1
        assert supporting[0].role == EvidenceLinkRole.SUPPORTING

    def test_get_refuting_evidence(self, contested_claim):
        """Test getting refuting evidence links."""
        refuting = contested_claim.get_refuting_evidence()
        assert len(refuting) == 1
        assert refuting[0].role == EvidenceLinkRole.REFUTING


class TestStatusChange:
    """Tests for StatusChange component."""

    def test_status_change_creation(self, sample_evidence_id):
        """Test creating StatusChange."""
        change = StatusChange(
            at=datetime(2026, 5, 26, 12, 0, 0),
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
            note="Status changed",
        )

        assert change.from_status == ClaimStatus.PROPOSED
        assert change.to_status == ClaimStatus.SUPPORTED
        assert change.triggered_by == sample_evidence_id

    def test_status_change_note_is_optional(self, sample_evidence_id):
        """Test that note is optional for StatusChange."""
        change = StatusChange(
            at=datetime.utcnow(),
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
        )
        assert change.note is None

    def test_status_change_is_frozen(self, sample_evidence_id):
        """Test that StatusChange is frozen."""
        change = StatusChange(
            at=datetime.utcnow(),
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            triggered_by=sample_evidence_id,
        )

        with pytest.raises(TypeError):
            change.note = "New note"


class TestEvidenceLink:
    """Tests for EvidenceLink component."""

    def test_evidence_link_creation_supporting(self):
        """Test creating supporting EvidenceLink."""
        link = EvidenceLink(
            evidence_id="evi-001",
            role=EvidenceLinkRole.SUPPORTING,
        )
        assert link.role == EvidenceLinkRole.SUPPORTING

    def test_evidence_link_creation_refuting(self):
        """Test creating refuting EvidenceLink."""
        link = EvidenceLink(
            evidence_id="evi-001",
            role=EvidenceLinkRole.REFUTING,
        )
        assert link.role == EvidenceLinkRole.REFUTING

    def test_evidence_link_is_frozen(self):
        """Test that EvidenceLink is frozen."""
        link = EvidenceLink(
            evidence_id="evi-001",
            role=EvidenceLinkRole.SUPPORTING,
        )

        with pytest.raises(TypeError):
            link.role = EvidenceLinkRole.REFUTING


class TestJSONSerialization:
    """Tests for JSON serialization/deserialization."""

    def test_claim_model_dump(self, valid_claim):
        """Test Claim serialization to dict."""
        data = valid_claim.model_dump()

        assert data["id"] == "claim-test-encoding"
        assert data["status"] == "proposed"
        assert data["mode"] == "confirmatory"

    def test_claim_model_dump_json(self, valid_claim):
        """Test Claim serialization to JSON string."""
        json_str = valid_claim.model_dump_json()

        assert isinstance(json_str, str)
        assert "claim-test-encoding" in json_str

    def test_confidence_serialization(self, valid_confidence):
        """Test Confidence serialization."""
        data = valid_confidence.model_dump()

        assert data["type"] == "credence"
        assert data["value"] == 0.95
        assert data["basis"] == "Strong experimental support"

    def test_status_change_serialization(self, supported_claim):
        """Test StatusChange serialization."""
        change = supported_claim.history[0]
        data = change.model_dump()

        assert data["from_status"] == "proposed"
        assert data["to_status"] == "supported"

    def test_evidence_link_serialization(self, contested_claim):
        """Test EvidenceLink serialization."""
        link = contested_claim.evidence_set[0]
        data = link.model_dump()

        assert "evidence_id" in data
        assert "role" in data


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_claim_with_empty_evidence_set(self, valid_claim):
        """Test claim with empty evidence set."""
        assert len(valid_claim.evidence_set) == 0

    def test_claim_with_empty_scope_limitations(self):
        """Test claim with empty scope limitations."""
        claim = Claim(
            id="claim-no-scope",
            spec_id="spec-001",
            answers="hyp-001",
            statement="Test",
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.WEAK,
                basis="Test",
            ),
            scope_limitations="",  # Empty
            mode=HypothesisMode.CONFIRMATORY,
        )
        assert claim.scope_limitations == ""

    def test_claim_with_renders_to(self, valid_claim):
        """Test claim with renders_to field."""
        valid_claim.renders_to = "Section 4: Main Results"
        assert valid_claim.renders_to == "Section 4: Main Results"

    def test_multiple_status_changes_same_claim(self, sample_claim_id, sample_spec_id, sample_hypothesis_id):
        """Test claim with multiple status changes."""
        claim = Claim(
            id=sample_claim_id,
            spec_id=sample_spec_id,
            answers=sample_hypothesis_id,
            statement="Test",
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.WEAK,
                basis="Test",
            ),
            mode=HypothesisMode.CONFIRMATORY,
        )

        # Add multiple changes
        for i, evidence_id in enumerate(["evi-001", "evi-002", "evi-003"]):
            claim.update_status(
                ClaimStatus.SUPPORTED if i % 2 == 0 else ClaimStatus.CONTESTED,
                evidence_id,
            )

        assert len(claim.history) == 3

    def test_confidence_without_value_for_graded(self, graded_confidence):
        """Test graded confidence without value field."""
        assert graded_confidence.value is None
        assert graded_confidence.level is not None

    def test_confidence_with_both_value_and_level(self):
        """Test confidence can have both value and level."""
        # This is allowed for flexibility
        conf = Confidence(
            type=ConfidenceType.GRADED,
            value=0.75,
            level=ConfidenceLevel.MODERATE,
            basis="Both numeric and qualitative",
        )
        assert conf.value == 0.75
        assert conf.level == ConfidenceLevel.MODERATE

    def test_all_confidence_types(self):
        """Test all valid confidence types."""
        types = [
            ConfidenceType.CREDENCE,
            ConfidenceType.POSTERIOR,
            ConfidenceType.GRADED,
        ]

        for conf_type in types:
            if conf_type == ConfidenceType.GRADED:
                conf = Confidence(
                    type=conf_type,
                    level=ConfidenceLevel.MODERATE,
                    basis=f"Test for {conf_type.value}",
                )
            else:
                conf = Confidence(
                    type=conf_type,
                    value=0.7,
                    basis=f"Test for {conf_type.value}",
                )
            assert conf.type == conf_type
