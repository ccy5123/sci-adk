"""
Unit tests for Evidence core type.

Tests cover invariants E1-E4 from design/abstractions.md:
    E1: Append-only - EvidenceItem is never mutated or deleted
    E2: Null results (refutes/inconclusive/neutral) are valid outcomes
    E3: Every EvidenceItem carries sufficient Provenance for reproduction
    E4: bears_on.target_id references an existing Hypothesis or Claim

Test Categories:
1. EvidenceItem creation and validation
2. Invariant E1: Append-only immutability
3. Invariant E2: Null result validity
4. Invariant E3: Provenance validation
5. Invariant E4: Bearing reference validity
6. Result types (quantitative vs qualitative)
7. Correction evidence items
8. JSON serialization
9. Edge cases and error conditions
"""

import pytest
from datetime import datetime, timezone

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    Cost,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.spec import Id

from tests.fixtures import (
    counterexample_evidence,
    inconclusive_bearing,
    literature_evidence,
    minimal_provenance,
    neutral_bearing,
    null_result,
    refuting_bearing,
    valid_bearing,
    valid_evidence_item,
    valid_provenance,
    valid_quantitative_result,
    valid_qualitative_result,
)


class TestEvidenceItemCreation:
    """Tests for EvidenceItem creation with valid data."""

    def test_create_minimal_evidence_item(self):
        """Test creating a valid EvidenceItem with minimal fields."""
        evidence = EvidenceItem(
            id="evi-minimal",
            spec_id="spec-001",
            kind=EvidenceKind.OBSERVATION,
            provenance=Provenance(code_ref="manual entry"),
            result=Result(type="qualitative", finding="Observation note"),
            bears_on=[],
        )

        assert evidence.id == "evi-minimal"
        assert evidence.spec_id == "spec-001"
        assert evidence.kind == EvidenceKind.OBSERVATION
        assert evidence.supersedes is None

    def test_create_experiment_run_evidence(self, valid_evidence_item):
        """Test creating experiment run evidence."""
        assert valid_evidence_item.kind == EvidenceKind.EXPERIMENT_RUN
        assert valid_evidence_item.provenance.code_ref is not None
        assert valid_evidence_item.provenance.seed is not None

    def test_create_literature_evidence(self, literature_evidence):
        """Test creating literature evidence."""
        assert literature_evidence.kind == EvidenceKind.LITERATURE
        assert literature_evidence.result.type == "qualitative"

    def test_create_counterexample_evidence(self, counterexample_evidence):
        """Test creating counterexample evidence."""
        assert counterexample_evidence.kind == EvidenceKind.COUNTEREXAMPLE
        assert any(
            b.direction == BearingDirection.REFUTES
            for b in counterexample_evidence.bears_on
        )

    def test_evidence_item_auto_generates_created_at(self):
        """Test that EvidenceItem auto-generates created_at."""
        before = datetime.now(timezone.utc)
        evidence = EvidenceItem(
            id="evi-timestamp",
            spec_id="spec-001",
            kind=EvidenceKind.OBSERVATION,
            provenance=Provenance(code_ref="test"),
            result=Result(type="qualitative", finding="test"),
            bears_on=[],
        )
        after = datetime.now(timezone.utc)

        assert before <= evidence.created_at <= after

    def test_evidence_item_with_supersedes(self, valid_evidence_item):
        """Test creating evidence that supersedes prior evidence."""
        correction = valid_evidence_item.with_correction(
            note="Fixing calculation error"
        )

        assert correction.supersedes == valid_evidence_item.id
        assert "corr" in correction.id


class TestInvariantE1_AppendOnly:
    """Tests for Invariant E1: EvidenceItem is never mutated or deleted."""

    def test_evidence_item_is_frozen(self, valid_evidence_item):
        """Test that EvidenceItem instances are frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_evidence_item.id = "new-id"

    def test_result_is_frozen(self, valid_quantitative_result):
        """Test that Result is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_quantitative_result.point = 0.5

    def test_bearing_is_frozen(self, valid_bearing):
        """Test that Bearing is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_bearing.direction = BearingDirection.REFUTES

    def test_provenance_is_frozen(self, valid_provenance):
        """Test that Provenance is frozen."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            valid_provenance.seed = 123

    def test_cost_is_frozen(self):
        """Test that Cost is frozen."""
        from pydantic import ValidationError
        cost = Cost(tokens=1000, wallclock_seconds=10.0)
        with pytest.raises(ValidationError):
            cost.tokens = 2000

    def test_correction_creates_new_item(self, valid_evidence_item):
        """Test that corrections create new items, not mutations."""
        original_id = valid_evidence_item.id
        correction = valid_evidence_item.with_correction(note="Test correction")

        # Original should be unchanged
        assert valid_evidence_item.id == original_id
        # Correction should be new item
        assert correction.id != original_id
        assert correction.supersedes == original_id


class TestInvariantE2_NullResults:
    """Tests for Invariant E2: Null results are valid outcomes."""

    def test_refuting_direction_is_valid(self, refuting_bearing):
        """Test that refutes is a valid bearing direction."""
        assert refuting_bearing.direction == BearingDirection.REFUTES

    def test_inconclusive_direction_is_valid(self, inconclusive_bearing):
        """Test that inconclusive is a valid bearing direction."""
        assert inconclusive_bearing.direction == BearingDirection.INCONCLUSIVE

    def test_neutral_direction_is_valid(self, neutral_bearing):
        """Test that neutral is a valid bearing direction."""
        assert neutral_bearing.direction == BearingDirection.NEUTRAL

    def test_null_result_is_valid(self, null_result):
        """Test that null results (no significant effect) are valid."""
        assert null_result.p_value == 0.57  # Not significant
        assert null_result.point == 0.02  # Small effect

    def test_counterexample_evidence_is_valid(self, counterexample_evidence):
        """Test that counterexample evidence (strong refutation) is valid."""
        assert any(
            b.direction == BearingDirection.REFUTES
            for b in counterexample_evidence.bears_on
        )

    def test_all_bearing_directions_are_first_class(self):
        """Test that all bearing directions are equally valid."""
        directions = [
            BearingDirection.SUPPORTS,
            BearingDirection.REFUTES,
            BearingDirection.NEUTRAL,
            BearingDirection.INCONCLUSIVE,
        ]

        for direction in directions:
            bearing = Bearing(
                target_id="hyp-001",
                direction=direction,
            )
            assert bearing.direction == direction


class TestInvariantE3_ProvenanceValidation:
    """Tests for Invariant E3: EvidenceItem carries sufficient Provenance."""

    def test_full_provenance(self, valid_provenance):
        """Test creating Provenance with all fields."""
        assert valid_provenance.code_ref is not None
        assert valid_provenance.data_ref is not None
        assert valid_provenance.seed is not None
        assert valid_provenance.environment is not None
        assert valid_provenance.cost is not None

    def test_minimal_provenance(self, minimal_provenance):
        """Test that minimal provenance (only code_ref) is allowed."""
        assert minimal_provenance.code_ref is not None
        assert minimal_provenance.data_ref is None
        assert minimal_provenance.seed is None

    def test_provenance_with_cost_only(self):
        """Test Provenance with only cost telemetry."""
        provenance = Provenance(
            cost=Cost(tokens=5000, wallclock_seconds=30.0)
        )
        assert provenance.cost is not None
        assert provenance.cost.tokens == 5000

    def test_provenance_with_environment_only(self):
        """Test Provenance with only environment info."""
        provenance = Provenance(environment="python-3.13, pytest-8.0")
        assert provenance.environment == "python-3.13, pytest-8.0"

    def test_provenance_seed_must_be_non_negative(self):
        """Test that RNG seed cannot be negative."""
        with pytest.raises(Exception):
            Provenance(seed=-1)

    def test_cost_values_must_be_non_negative(self):
        """Test that cost values cannot be negative."""
        with pytest.raises(Exception):
            Cost(tokens=-100)

        with pytest.raises(Exception):
            Cost(wallclock_seconds=-5.0)


class TestInvariantE4_BearingReferences:
    """Tests for Invariant E4: bears_on.target_id references existing Hypothesis or Claim."""

    def test_bearing_with_valid_target_id(self, valid_bearing):
        """Test creating Bearing with valid target_id."""
        assert valid_bearing.target_id == "hyp-test-encoding"

    def test_bearing_target_id_is_required(self):
        """Test that target_id is required for Bearing."""
        with pytest.raises(Exception):
            Bearing(
                # target_id missing
                direction=BearingDirection.SUPPORTS,
            )

    def test_bearing_direction_is_required(self):
        """Test that direction is required for Bearing."""
        with pytest.raises(Exception):
            Bearing(
                target_id="hyp-001",
                # direction missing
            )

    def test_bearing_weight_is_optional(self):
        """Test that weight is optional."""
        bearing = Bearing(
            target_id="hyp-001",
            direction=BearingDirection.SUPPORTS,
            # weight not provided
        )
        assert bearing.weight is None

    def test_bearing_weight_must_be_non_negative(self):
        """Test that weight cannot be negative."""
        with pytest.raises(Exception):
            Bearing(
                target_id="hyp-001",
                direction=BearingDirection.SUPPORTS,
                weight=-1.0,
            )

    def test_multiple_bearings_on_same_target(self):
        """Test multiple bearings on the same target."""
        bearings = [
            Bearing(
                target_id="hyp-001",
                direction=BearingDirection.SUPPORTS,
                weight=1.0,
            ),
            Bearing(
                target_id="hyp-001",
                direction=BearingDirection.REFUTES,
                weight=0.5,
            ),
        ]

        assert len(bearings) == 2
        assert all(b.target_id == "hyp-001" for b in bearings)

    def test_evidence_with_multiple_bearings(self):
        """Test EvidenceItem with bearings on multiple targets."""
        evidence = EvidenceItem(
            id="evi-multi-001",
            spec_id="spec-001",
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="test"),
            result=Result(type="qualitative", finding="test"),
            bears_on=[
                Bearing(target_id="hyp-001", direction=BearingDirection.SUPPORTS),
                Bearing(target_id="claim-001", direction=BearingDirection.REFUTES),
            ],
        )

        assert len(evidence.bears_on) == 2
        target_ids = {b.target_id for b in evidence.bears_on}
        assert target_ids == {"hyp-001", "claim-001"}


class TestResultTypes:
    """Tests for Result types (quantitative vs qualitative)."""

    def test_quantitative_result(self, valid_quantitative_result):
        """Test creating quantitative result."""
        assert valid_quantitative_result.type == "quantitative"
        assert valid_quantitative_result.point is not None
        assert valid_quantitative_result.effect_size is not None
        assert valid_quantitative_result.ci is not None
        assert valid_quantitative_result.p_value is not None
        assert valid_quantitative_result.posterior is not None

    def test_qualitative_result(self, valid_qualitative_result):
        """Test creating qualitative result."""
        assert valid_qualitative_result.type == "qualitative"
        assert valid_qualitative_result.finding is not None
        assert valid_qualitative_result.artifact_ref is not None

    def test_result_type_must_be_valid(self):
        """Test that result type must be 'quantitative' or 'qualitative'."""
        with pytest.raises(ValueError, match="type must be one of"):
            Result(type="invalid_type")

    def test_result_ci_ordering(self):
        """Test that confidence interval has valid ordering."""
        # Valid CI
        result = Result(
            type="quantitative",
            ci=(0.0, 1.0),
        )
        assert result.ci == [0.0, 1.0]

        # Invalid CI (lower > upper)
        with pytest.raises(ValueError, match="lower bound.*exceeds upper"):
            Result(
                type="quantitative",
                ci=(1.0, 0.0),
            )

    def test_p_value_bounds(self):
        """Test that p_value is within [0, 1]."""
        # Valid p-values
        Result(type="quantitative", p_value=0.0)
        Result(type="quantitative", p_value=0.5)
        Result(type="quantitative", p_value=1.0)

        # Invalid p-values
        with pytest.raises(Exception):
            Result(type="quantitative", p_value=-0.1)

        with pytest.raises(Exception):
            Result(type="quantitative", p_value=1.5)

    def test_posterior_bounds(self):
        """Test that posterior is within [0, 1]."""
        # Valid posterior
        Result(type="quantitative", posterior=0.95)

        # Invalid posterior
        with pytest.raises(Exception):
            Result(type="quantitative", posterior=1.5)

    def test_mixed_result_fields_allowed(self):
        """Test that mixing quantitative and qualitative fields is allowed."""
        # Both quantitative point and qualitative finding
        result = Result(
            type="quantitative",
            point=0.95,
            finding="Strong correlation observed",
        )
        assert result.point == 0.95
        assert result.finding == "Strong correlation observed"


class TestEvidenceKinds:
    """Tests for all EvidenceKind values."""

    def test_all_evidence_kinds(self):
        """Test creating evidence with all valid kinds."""
        kinds = [
            EvidenceKind.EXPERIMENT_RUN,
            EvidenceKind.PROOF_STEP,
            EvidenceKind.LITERATURE,
            EvidenceKind.COUNTEREXAMPLE,
            EvidenceKind.OBSERVATION,
        ]

        for kind in kinds:
            evidence = EvidenceItem(
                id=f"evi-{kind.value}",
                spec_id="spec-001",
                kind=kind,
                provenance=Provenance(code_ref="test"),
                result=Result(type="qualitative", finding="test"),
                bears_on=[],
            )
            assert evidence.kind == kind


class TestCorrectionEvidence:
    """Tests for creating correction evidence items."""

    def test_with_correction_creates_new_evidence(self, valid_evidence_item):
        """Test that with_correction() creates a new EvidenceItem."""
        correction = valid_evidence_item.with_correction(
            note="Corrected calculation error"
        )

        assert correction.id != valid_evidence_item.id
        assert correction.supersedes == valid_evidence_item.id
        assert correction.spec_id == valid_evidence_item.spec_id
        assert correction.kind == valid_evidence_item.kind

    def test_with_correction_new_result(self, valid_evidence_item):
        """Test correction with new result."""
        new_result = Result(
            type="quantitative",
            point=0.999,  # Corrected value
            p_value=0.0001,
        )

        correction = valid_evidence_item.with_correction(
            result=new_result,
            note="Fixed calculation",
        )

        assert correction.result.point == 0.999
        assert correction.result != valid_evidence_item.result

    def test_with_correction_new_provenance(self, valid_evidence_item):
        """Test correction with new provenance."""
        new_provenance = Provenance(
            code_ref="fix-branch:src/calc.py:50",
            seed=43,  # Different seed
        )

        correction = valid_evidence_item.with_correction(
            provenance=new_provenance,
            note="Reproducibility fix",
        )

        assert correction.provenance.seed == 43

    def test_with_correction_preserves_unspecified_fields(self, valid_evidence_item):
        """Test that correction preserves unspecified fields."""
        original_bears_on = valid_evidence_item.bears_on

        correction = valid_evidence_item.with_correction(
            note="Minor note correction"
        )

        assert correction.bears_on == original_bears_on
        assert correction.result == valid_evidence_item.result
        assert correction.provenance == valid_evidence_item.provenance


class TestEvidenceHelperMethods:
    """Tests for EvidenceItem helper methods."""

    def test_supports_target(self, valid_evidence_item):
        """Test checking if evidence supports a target."""
        assert valid_evidence_item.supports_target("hyp-test-encoding")
        assert not valid_evidence_item.supports_target("other-hyp")

    def test_refutes_target(self, valid_evidence_item):
        """Test checking if evidence refutes a target."""
        # Default evidence has SUPPORTS direction
        assert not valid_evidence_item.refutes_target("hyp-test-encoding")

    def test_refutes_target_with_refuting_bearing(self, counterexample_evidence):
        """Test refutes_target with actual refuting bearing."""
        assert counterexample_evidence.refutes_target("hyp-test-encoding")


class TestJSONSerialization:
    """Tests for JSON serialization/deserialization."""

    def test_evidence_item_model_dump(self, valid_evidence_item):
        """Test EvidenceItem serialization to dict."""
        data = valid_evidence_item.model_dump()

        assert data["id"] == "evi-test-001"
        assert data["kind"] == "experiment_run"
        assert "provenance" in data
        assert "result" in data
        assert "bears_on" in data

    def test_evidence_item_model_dump_json(self, valid_evidence_item):
        """Test EvidenceItem serialization to JSON string."""
        json_str = valid_evidence_item.model_dump_json()

        assert isinstance(json_str, str)
        assert "evi-test-001" in json_str

    def test_result_serialization(self, valid_quantitative_result):
        """Test Result serialization."""
        data = valid_quantitative_result.model_dump()

        assert data["type"] == "quantitative"
        assert data["point"] == 0.987
        assert data["ci"] == [0.95, 1.02]

    def test_bearing_serialization(self, valid_bearing):
        """Test Bearing serialization."""
        data = valid_bearing.model_dump()

        assert data["target_id"] == "hyp-test-encoding"
        assert data["direction"] == "supports"
        assert data["weight"] == 1.0

    def test_provenance_serialization(self, valid_provenance):
        """Test Provenance serialization."""
        data = valid_provenance.model_dump()

        assert data["code_ref"] is not None
        assert data["data_ref"] is not None
        assert data["seed"] == 42
        assert "cost" in data


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_evidence_with_empty_bears_on(self):
        """Test evidence with empty bears_on list."""
        evidence = EvidenceItem(
            id="evi-no-bearings",
            spec_id="spec-001",
            kind=EvidenceKind.OBSERVATION,
            provenance=Provenance(code_ref="manual"),
            result=Result(type="qualitative", finding="General note"),
            bears_on=[],
        )
        assert len(evidence.bears_on) == 0

    def test_result_with_all_optional_fields(self):
        """Test result with minimal fields."""
        result = Result(type="quantitative")
        assert result.point is None
        assert result.p_value is None
        assert result.finding is None

    def test_provenance_with_all_none_fields(self):
        """Test provenance with all fields None."""
        provenance = Provenance()
        assert provenance.code_ref is None
        assert provenance.data_ref is None
        assert provenance.seed is None
        assert provenance.environment is None
        assert provenance.cost is None

    def test_cost_with_all_none_fields(self):
        """Test Cost with all fields None."""
        cost = Cost()
        assert cost.tokens is None
        assert cost.wallclock_seconds is None
        assert cost.cpu_seconds is None
        assert cost.memory_mb is None

    def test_multiple_evidence_items_same_spec(self):
        """Test multiple evidence items for the same spec."""
        spec_id = "spec-001"

        ev1 = EvidenceItem(
            id="evi-001",
            spec_id=spec_id,
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="test1"),
            result=Result(type="qualitative", finding="test1"),
            bears_on=[],
        )

        ev2 = EvidenceItem(
            id="evi-002",
            spec_id=spec_id,
            kind=EvidenceKind.LITERATURE,
            provenance=Provenance(code_ref="test2"),
            result=Result(type="qualitative", finding="test2"),
            bears_on=[],
        )

        assert ev1.spec_id == ev2.spec_id == spec_id

    def test_evidence_chain_corrections(self, valid_evidence_item):
        """Test chain of corrections."""
        # First correction
        v2 = valid_evidence_item.with_correction(note="First correction")
        assert v2.supersedes == valid_evidence_item.id

        # Second correction
        v3 = v2.with_correction(note="Second correction")
        assert v3.supersedes == v2.id

    def test_bearing_with_large_weight(self):
        """Test bearing with large weight value."""
        bearing = Bearing(
            target_id="hyp-001",
            direction=BearingDirection.SUPPORTS,
            weight=1000.0,
        )
        assert bearing.weight == 1000.0

    def test_evidence_with_all_result_fields(self):
        """Test evidence with all quantitative result fields."""
        result = Result(
            type="quantitative",
            point=0.5,
            effect_size=1.2,
            ci=(0.3, 0.7),
            p_value=0.01,
            posterior=0.99,
            residual=0.05,
            predictive_error=0.02,
        )

        evidence = EvidenceItem(
            id="evi-full-result",
            spec_id="spec-001",
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="test"),
            result=result,
            bears_on=[],
        )

        assert evidence.result.point == 0.5
        assert evidence.result.effect_size == 1.2
        assert evidence.result.residual == 0.05
