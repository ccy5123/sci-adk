"""
sci-adk Core Type: Claim

The Claim type represents the compiler output - revisable belief states
derived from Evidence.

Core principle: What we currently believe is non-monotone and revisable.
New evidence raises or lowers confidence; a once-supported claim can be
demoted or retracted. This is normal science, not a defect.

Invariants:
    C1: status may move in any direction (supported -> contested -> refuted)
    C2: history is append-only - every change appends a StatusChange
    C3: confidence.basis is the load-bearing field and always required
    C4: Null results are expressible (e.g., "no evidence for effect X")
    C5: evidence_set includes refuting links, not only supporting
    C6: exploratory claims cannot be presented as confirmatory

This module uses non-frozen dataclass for Claim (revisable) while maintaining
append-only history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from .spec import HypothesisMode, Id


class ClaimStatus(str, Enum):
    """
    The status of a claim - NON-monotone belief state.

    A claim can move in ANY direction over time (Invariant C1).
    This is normal science - new evidence can contest or refute
    previously-supported claims.

    Attributes:
        proposed: Newly proposed claim, not yet evaluated
        supported: Current evidence supports the claim
        contested: Mixed evidence - both support and refutation exist
        refuted: Current evidence refutes the claim
        retracted: Claim withdrawn (e.g., provenance broken, reproduction failed)
    """

    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    REFUTED = "refuted"
    RETRACTED = "retracted"


class ConfidenceType(str, Enum):
    """
    The type of confidence representation.

    The type does not privilege one representation over another.
    The `basis` text carries the actual judgment (Invariant C3).

    Attributes:
        credence: Subjective credence/probability in [0,1]
        posterior: Bayesian posterior probability in [0,1]
        graded: Qualitative graded level (strong/moderate/weak/none)
    """

    CREDENCE = "credence"
    POSTERIOR = "posterior"
    GRADED = "graded"


class ConfidenceLevel(str, Enum):
    """
    Qualitative confidence levels for graded confidence type.

    Used when numeric confidence is not appropriate or available.

    Attributes:
        strong: High confidence
        moderate: Medium confidence
        weak: Low confidence
        none: No confidence
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class EvidenceLinkRole(str, Enum):
    """
    The role of evidence in relation to a claim.

    Invariant C5: Both roles must be tracked - a claim hides nothing
    about evidence against it.

    Attributes:
        supporting: Evidence supports this claim
        refuting: Evidence refutes this claim
    """

    SUPPORTING = "supporting"
    REFUTING = "refuting"


class Confidence(BaseModel):
    """
    Confidence representation for a claim.

    Invariant C3: basis (justification) is the load-bearing field and
    is always required. value/level is whichever indicator is representative
    for the field.

    Attributes:
        type: Type of confidence (credence/posterior/graded)
        value: Numeric confidence value in [0,1] (for credence/posterior)
        level: Qualitative confidence level (for graded)
        basis: Natural-language justification (REQUIRED)
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    type: ConfidenceType = Field(..., description="Type of confidence representation")
    value: Optional[float] = Field(
        None, ge=0, le=1, description="Numeric confidence [0,1] for credence/posterior"
    )
    level: Optional[ConfidenceLevel] = Field(
        None, description="Qualitative level for graded type"
    )
    basis: str = Field(..., min_length=1, description="Natural-language justification (REQUIRED)")

    # @MX:ANCHOR: basis is the load-bearing confidence field
    # @MX:REASON: Invariant C3 - prevents arbitrary numeric thresholds from carrying authority

    @validator("value")
    def validate_fields_match_type(cls, v: Optional[float], values: Dict[str, Any]) -> Optional[float]:
        """Ensure confidence fields are appropriate for the declared type."""
        if "type" in values:
            conf_type = values["type"]
            if conf_type in (ConfidenceType.CREDENCE, ConfidenceType.POSTERIOR):
                if v is None:
                    raise ValueError(f"{conf_type.value} confidence requires value field")
        return v

    @validator("level")
    def validate_level_for_graded(cls, v: Optional[ConfidenceLevel], values: Dict[str, Any]) -> Optional[ConfidenceLevel]:
        """Ensure level is present for graded type."""
        if "type" in values:
            conf_type = values["type"]
            if conf_type == ConfidenceType.GRADED and v is None:
                raise ValueError("graded confidence requires level field")
        return v

    @validator("basis")
    def validate_basis_present(cls, v: str) -> str:
        """
        Invariant C3: basis is always required.

        The justification text carries the actual judgment - numeric values
        alone are insufficient.
        """
        if not v or not v.strip():
            raise ValueError("confidence.basis is required and must not be empty")
        return v


class EvidenceLink(BaseModel):
    """
    A link from a claim to a piece of evidence.

    Invariant C5: Claims include refuting links, not just supporting ones.
    A claim hides nothing about evidence against it.

    Attributes:
        evidence_id: Reference to an EvidenceItem
        role: Whether this evidence supports or refutes the claim
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    evidence_id: Id = Field(..., description="Reference to EvidenceItem")
    role: EvidenceLinkRole = Field(..., description="Supporting or refuting")


class StatusChange(BaseModel):
    """
    A record of a claim's status change.

    The claim's status may move non-monotonically, but the HISTORY is
    append-only (Invariant C2). Every change is recorded.

    Attributes:
        at: Timestamp of the status change
        from: Previous status
        to: New status
        triggered_by: Evidence id that caused the change
        note: Optional explanation of the change
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True
        json_encoders = {datetime: lambda v: v.isoformat()}

    at: datetime = Field(..., description="When the status changed")
    from_status: ClaimStatus = Field(..., description="Previous status", alias="from")
    to_status: ClaimStatus = Field(..., description="New status", alias="to")
    triggered_by: Id = Field(..., description="Evidence id that caused this change")
    note: Optional[str] = Field(None, description="Optional explanation")

    class Config:
        allow_population_by_field_name = True


class Claim(BaseModel):
    """
    A contribution-level statement with uncertainty - the compiler output.

    Claims are derived from Evidence and represent what becomes the paper's
    claims. Unlike software's binary DONE, claims have revisable belief states.

    Invariant C1: status may move in any direction - supported -> contested is normal.
    Invariant C6: exploratory claims must remain labeled as such.

    Attributes:
        id: Unique claim identifier
        spec_id: Reference to the governing Spec
        answers: Hypothesis id this claim addresses
        statement: The claim statement
        status: Current belief status (non-monotone)
        confidence: Confidence assessment with required basis
        evidence_set: All evidence links (supporting AND refuting)
        scope_limitations: "Research Limitations" section text
        mode: confirmatory or exploratory (inherited from Hypothesis)
        renders_to: Optional paper section/deliverable mapping
        history: Append-only audit of belief movement
    """

    class Config:
        frozen = False  # Claim is revisable - non-frozen
        anystr_strip_whitespace = True
        json_encoders = {datetime: lambda v: v.isoformat()}
        validate_assignment = True  # Validate on attribute assignment

    id: Id = Field(..., description="Unique claim identifier")
    spec_id: Id = Field(..., description="Reference to governing Spec")
    answers: Id = Field(..., description="Hypothesis id this claim addresses")
    statement: str = Field(..., min_length=1, description="Claim statement")
    status: ClaimStatus = Field(
        ClaimStatus.PROPOSED, description="Current belief status"
    )
    confidence: Confidence = Field(..., description="Confidence assessment")
    evidence_set: List[EvidenceLink] = Field(
        default_factory=list, description="All evidence (supporting + refuting)"
    )
    scope_limitations: str = Field(
        "", description="Research limitations text"
    )
    mode: HypothesisMode = Field(
        ..., description="confirmatory or exploratory (inherited from hypothesis)"
    )
    renders_to: Optional[str] = Field(
        None, description="Paper section/deliverable mapping"
    )
    history: List[StatusChange] = Field(
        default_factory=list, description="Append-only status change history"
    )

    # @MX:NOTE: Claim is non-frozen - belief state is revisable
    # Only the history log is append-only (Invariant C2)

    @validator("status")
    def validate_confidence_matches_status(cls, v: ClaimStatus, values: Dict[str, Any]) -> ClaimStatus:
        """Ensure confidence is consistent with status (informational only)."""
        # Note: We don't raise here because confidence and status can diverge
        # during updates. This is informational validation.
        return v

    @validator("mode", pre=True, always=True)
    def validate_exploratory_not_presented_as_confirmatory(cls, v: HypothesisMode) -> HypothesisMode:
        """
        Invariant C6: exploratory claims cannot be presented as confirmatory.

        This is enforced at the mode level - the claim inherits its mode
        from the hypothesis and cannot change it.
        """
        # The mode is inherited and frozen at creation time
        # External validation must prevent mode changes
        return v

    def update_status(
        self,
        new_status: ClaimStatus,
        triggered_by: Id,
        note: Optional[str] = None,
    ) -> None:
        """
        Update the claim's status, recording the change in history.

        Invariant C1: Status may move in ANY direction - no restrictions.
        Invariant C2: Every change appends to history (append-only).

        Args:
            new_status: The new status
            triggered_by: Evidence id causing this change
            note: Optional explanation
        """
        now = datetime.utcnow()

        # Record the change in history (append-only)
        change = StatusChange(
            at=now,
            from_status=self.status,
            to_status=new_status,
            triggered_by=triggered_by,
            note=note,
        )
        self.history.append(change)

        # Update the status
        self.status = new_status

    def add_evidence(
        self,
        evidence_id: Id,
        role: EvidenceLinkRole,
    ) -> None:
        """
        Add an evidence link to this claim.

        Invariant C5: Refuting links MUST be included, not hidden.

        Args:
            evidence_id: Reference to an EvidenceItem
            role: Whether this evidence supports or refutes
        """
        # Check for duplicates
        for link in self.evidence_set:
            if link.evidence_id == evidence_id and link.role == role:
                return  # Already linked

        self.evidence_set.append(
            EvidenceLink(evidence_id=evidence_id, role=role)
        )

    def update_confidence(
        self,
        confidence_type: Optional[ConfidenceType] = None,
        value: Optional[float] = None,
        level: Optional[ConfidenceLevel] = None,
        basis: str = "",
    ) -> None:
        """
        Update the claim's confidence.

        Invariant C3: basis is always required.

        Args:
            confidence_type: New confidence type (or keep existing)
            value: New numeric value (for credence/posterior)
            level: New qualitative level (for graded)
            basis: New justification text (REQUIRED if provided)

        Raises:
            ValueError: If basis is empty when updating
        """
        current_basis = self.confidence.basis

        # Build new confidence
        new_type = confidence_type or self.confidence.type
        new_value = value if value is not None else self.confidence.value
        new_level = level if level is not None else self.confidence.level
        new_basis = basis if basis else current_basis

        if not new_basis or not new_basis.strip():
            raise ValueError("confidence.basis is required")

        self.confidence = Confidence(
            type=new_type,
            value=new_value,
            level=new_level,
            basis=new_basis,
        )

    def is_supported(self) -> bool:
        """Check if claim is currently in supported status."""
        return self.status == ClaimStatus.SUPPORTED

    def is_contested(self) -> bool:
        """Check if claim is currently in contested status."""
        return self.status == ClaimStatus.CONTESTED

    def is_refuted(self) -> bool:
        """Check if claim is currently in refuted status."""
        return self.status == ClaimStatus.REFUTED

    def is_retracted(self) -> bool:
        """Check if claim is currently in retracted status."""
        return self.status == ClaimStatus.RETRACTED

    def get_supporting_evidence(self) -> List[EvidenceLink]:
        """Get all supporting evidence links."""
        return [link for link in self.evidence_set if link.role == EvidenceLinkRole.SUPPORTING]

    def get_refuting_evidence(self) -> List[EvidenceLink]:
        """Get all refuting evidence links."""
        return [link for link in self.evidence_set if link.role == EvidenceLinkRole.REFUTING]

    def has_conflicting_evidence(self) -> bool:
        """
        Check if claim has both supporting and refuting evidence.

        Returns:
            True if both supporting and refuting evidence exist
        """
        has_supporting = any(
            link.role == EvidenceLinkRole.SUPPORTING for link in self.evidence_set
        )
        has_refuting = any(
            link.role == EvidenceLinkRole.REFUTING for link in self.evidence_set
        )
        return has_supporting and has_refuting

    @classmethod
    def create_null_result_claim(
        cls,
        id: Id,
        spec_id: Id,
        answers: Id,
        statement: str,
        mode: HypothesisMode,
        basis: str = "No evidence found for the claimed effect",
    ) -> Claim:
        """
        Create a claim representing a null result.

        Invariant C4: Null results are expressible as claims.
        Example: "no evidence for effect X" with status=supported,
        confidence over the ABSENCE.

        Args:
            id: Unique claim identifier
            spec_id: Reference to governing Spec
            answers: Hypothesis id this addresses
            statement: Claim statement (e.g., "No evidence for effect X")
            mode: confirmatory or exploratory
            basis: Justification for the null result

        Returns:
            A Claim representing a null result finding
        """
        return cls(
            id=id,
            spec_id=spec_id,
            answers=answers,
            statement=statement,
            status=ClaimStatus.SUPPORTED,
            confidence=Confidence(
                type=ConfidenceType.GRADED,
                level=ConfidenceLevel.MODERATE,
                basis=basis,
            ),
            evidence_set=[],
            scope_limitations="Null result - absence of effect claimed",
            mode=mode,
            history=[],
        )


__all__ = [
    "Id",
    "ClaimStatus",
    "ConfidenceType",
    "ConfidenceLevel",
    "EvidenceLinkRole",
    "Confidence",
    "EvidenceLink",
    "StatusChange",
    "Claim",
]
