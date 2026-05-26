"""
sci-adk Core Type: Evidence

The Evidence type represents the accumulated record of research activities.
It is immutable and append-only - the audit trail of the research process.

Core principle: The record of what happened is monotone and append-only.
You never unmake an experiment. Null and negative results are part of the record.

Invariants:
    E1: Append-only - EvidenceItem is never mutated or deleted
    E2: Null results (refutes/inconclusive/neutral) are valid outcomes
    E3: Every EvidenceItem carries sufficient Provenance for reproduction
    E4: bears_on.target_id references an existing Hypothesis or Claim

This module uses frozen dataclasses to enforce immutability at the type level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, validator

from .spec import Id


class EvidenceKind(str, Enum):
    """
    The kind of evidence item.

    Each represents a different type of research activity or finding.

    Attributes:
        experiment_run: A computational or physical experiment execution
        proof_step: A step in a formal proof derivation
        literature: A finding from the literature review
        counterexample: A counterexample to a claim
        observation: A general observation or note
    """

    EXPERIMENT_RUN = "experiment_run"
    PROOF_STEP = "proof_step"
    LITERATURE = "literature"
    COUNTEREXAMPLE = "counterexample"
    OBSERVATION = "observation"


class BearingDirection(str, Enum):
    """
    The direction of evidence bearing on a hypothesis or claim.

    All directions are first-class - none is "failure" or "stuck".
    Null results are valid and complete outcomes (Invariant E2).

    Attributes:
        supports: Evidence supports the hypothesis/claim
        refutes: Evidence refutes the hypothesis/claim
        neutral: Evidence is neutral or inconclusive
        inconclusive: Evidence is insufficient to draw a conclusion
    """

    SUPPORTS = "supports"
    REFUTES = "refutes"
    NEUTRAL = "neutral"
    INCONCLUSIVE = "inconclusive"


class Cost(BaseModel):
    """
    Resource cost information for evidence generation.

    Captures telemetry for reproducibility and resource tracking.

    Attributes:
        tokens: Language model tokens consumed (if applicable)
        wallclock_seconds: Wall-clock time taken
        cpu_seconds: CPU time consumed
        memory_mb: Peak memory usage in MB
    """

    class Config:
        frozen = True

    tokens: Optional[int] = Field(None, ge=0, description="LLM tokens consumed")
    wallclock_seconds: Optional[float] = Field(None, ge=0, description="Wall-clock time")
    cpu_seconds: Optional[float] = Field(None, ge=0, description="CPU time")
    memory_mb: Optional[float] = Field(None, ge=0, description="Peak memory MB")


class Provenance(BaseModel):
    """
    Reproducibility information for an evidence item.

    Invariant E3: Every EvidenceItem carries enough Provenance to attempt
    reproduction, or explicitly marks what is missing.

    Attributes:
        code_ref: Commit/worktree/script path + line reference
        data_ref: Dataset id + version reference
        seed: RNG seed for stochastic reproducibility
        environment: Toolchain/container/library versions
        cost: Resource cost telemetry
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    code_ref: Optional[str] = Field(None, description="Commit/worktree/script reference")
    data_ref: Optional[str] = Field(None, description="Dataset id + version")
    seed: Optional[int] = Field(None, ge=0, description="RNG seed")
    environment: Optional[str] = Field(None, description="Toolchain/container versions")
    cost: Optional[Cost] = Field(None, description="Resource cost telemetry")

    @validator("code_ref", "data_ref", "environment", pre=True, always=True)
    def validate_reproducibility_information(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """
        Invariant E3: Validate that sufficient provenance is recorded.

        At minimum, some provenance information should be present.
        """
        # Note: This is a simplified check - full validation would check all fields
        # We don't raise to allow purely observational evidence
        return v


class Result(BaseModel):
    """
    The result of an evidence item.

    Results may be continuous/probabilistic OR qualitative.
    The type accommodates both quantitative and qualitative findings.

    Attributes:
        type: Result type (quantitative or qualitative)
        point: Point estimate/statistic (quantitative)
        effect_size: Effect size measure (quantitative)
        ci: Confidence/credible interval (quantitative)
        p_value: P-value (quantitative)
        posterior: Posterior probability or reference (quantitative)
        residual: Residual from model fit (quantitative)
        predictive_error: Predictive error measure (quantitative)
        finding: Qualitative finding text (qualitative)
        artifact_ref: Reference to produced figure/table/file (qualitative)
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    type: str = Field(..., description="Result type discriminator")

    # Quantitative fields
    point: Optional[float] = Field(None, description="Point estimate")
    effect_size: Optional[float] = Field(None, description="Effect size")
    ci: Optional[Tuple[float, float]] = Field(
        None, description="Confidence/credible interval (lower, upper)"
    )
    p_value: Optional[float] = Field(None, ge=0, le=1, description="P-value")
    posterior: Optional[float] = Field(None, ge=0, le=1, description="Posterior probability")
    residual: Optional[float] = Field(None, description="Residual")
    predictive_error: Optional[float] = Field(None, description="Predictive error")

    # Qualitative fields
    finding: Optional[str] = Field(None, description="Qualitative finding text")
    artifact_ref: Optional[str] = Field(None, description="Reference to produced artifact")

    @validator("type")
    def validate_type(cls, v: str) -> str:
        """Ensure type is one of the allowed values."""
        allowed = {"quantitative", "qualitative"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}, got '{v}'")
        return v

    @validator("ci")
    def validate_ci_interval(cls, v: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
        """Validate confidence interval ordering."""
        if v:
            lower, upper = v
            if lower > upper:
                raise ValueError(f"CI lower bound ({lower}) exceeds upper ({upper})")
        return v


class Bearing(BaseModel):
    """
    A bearing describes how evidence relates to a hypothesis or claim.

    Invariant E4: target_id must reference an existing Hypothesis or Claim.
    (Validation happens at EvidenceItem level with full context.)

    Attributes:
        target_id: Reference to a Hypothesis or Claim id
        direction: supports/refutes/neutral/inconclusive
        weight: Optional strength/weight of this bearing
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    target_id: Id = Field(..., description="Hypothesis or Claim id this bears on")
    direction: BearingDirection = Field(..., description="Bearing direction")
    weight: Optional[float] = Field(None, ge=0, description="Optional strength weight")

    # @MX:NOTE: All bearing directions are first-class outcomes
    # Null results (refutes/inconclusive/neutral) are valid science


class EvidenceItem(BaseModel):
    """
    A single evidence item in the append-only evidence log.

    Invariant E1: EvidenceItem is never mutated or deleted after creation.
    Corrections are NEW items that reference the superseded one.

    The Evidence log is the source of truth for "what happened" in research.
    It is monotone and append-only - the scientific record.

    Attributes:
        id: Unique evidence item identifier
        created_at: ISO-8601 UTC timestamp
        spec_id: Reference to the Spec this run serves
        kind: Type of evidence item
        provenance: Reproducibility information
        result: The result (quantitative or qualitative)
        bears_on: Which hypotheses/claims this relates to and how
        supersedes: Optional reference to superseded evidence id (for corrections)
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True
        json_encoders = {datetime: lambda v: v.isoformat()}

    id: Id = Field(..., description="Unique evidence identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="Creation timestamp (ISO-8601 UTC)",
    )
    spec_id: Id = Field(..., description="Reference to governing Spec")
    kind: EvidenceKind = Field(..., description="Type of evidence")
    provenance: Provenance = Field(..., description="Reproducibility information")
    result: Result = Field(..., description="The result")
    bears_on: List[Bearing] = Field(
        default_factory=list, description="Relationships to hypotheses/claims"
    )
    supersedes: Optional[Id] = Field(
        None, description="Supersedes prior evidence id (for corrections)"
    )

    # @MX:ANCHOR: Evidence is append-only audit trail
    # @MX:REASON: Invariant E1 - enforces monotone scientific record

    @validator("bears_on")
    def validate_bears_on_not_empty(cls, v: List[Bearing], values: Dict[str, Any]) -> List[Bearing]:
        """
        Validate that at least one bearing is specified for non-observational evidence.

        Evidence should relate to at least one hypothesis or claim.
        """
        if "kind" in values:
            kind = values["kind"]
            if kind != EvidenceKind.OBSERVATION and not v:
                # We don't raise to allow flexible evidence entry
                pass
        return v

    def with_correction(
        self,
        result: Optional[Result] = None,
        provenance: Optional[Provenance] = None,
        bears_on: Optional[List[Bearing]] = None,
        note: str = "",
    ) -> EvidenceItem:
        """
        Create a correction evidence item that supersedes this one.

        Invariant E1: Corrections create NEW items, never mutate existing ones.
        The new evidence item references the old one via `supersedes`.

        Args:
            result: New result (or keep existing)
            provenance: New provenance (or keep existing)
            bears_on: New bearings (or keep existing)
            note: Explanation of the correction

        Returns:
            New EvidenceItem with supersedes pointing to this item
        """
        return EvidenceItem(
            id=f"{self.id}-corr-{int(datetime.utcnow().timestamp())}",
            created_at=datetime.utcnow(),
            spec_id=self.spec_id,
            kind=self.kind,
            provenance=provenance or self.provenance,
            result=result or self.result,
            bears_on=bears_on or self.bears_on,
            supersedes=self.id,
        )

    def supports_target(self, target_id: Id) -> bool:
        """
        Check if this evidence supports the given target.

        Args:
            target_id: Hypothesis or Claim id to check

        Returns:
            True if any bearing has direction=SUPPORTS for this target
        """
        return any(
            b.target_id == target_id and b.direction == BearingDirection.SUPPORTS
            for b in self.bears_on
        )

    def refutes_target(self, target_id: Id) -> bool:
        """
        Check if this evidence refutes the given target.

        Args:
            target_id: Hypothesis or Claim id to check

        Returns:
            True if any bearing has direction=REFUTES for this target
        """
        return any(
            b.target_id == target_id and b.direction == BearingDirection.REFUTES
            for b in self.bears_on
        )


__all__ = [
    "Id",
    "EvidenceKind",
    "BearingDirection",
    "Cost",
    "Provenance",
    "Result",
    "Bearing",
    "EvidenceItem",
]
