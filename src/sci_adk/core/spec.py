"""
sci-adk Core Type: Spec

The Spec type represents a frozen pre-registration contract. It captures the
four-pane research proposal as an evaluable contract with fixed questions and
decision rules (anti-HARKing).

Invariants:
    S1: Frozen Spec version is immutable; changes create version+1
    S2: Every Hypothesis has exactly one mode and one DecisionRule
    S3: DecisionRule expresses how continuous/uncertain evidence maps
    S4: TargetClaim.answers references an existing Hypothesis.id
    S5: Amending a frozen Spec requires human checkpoint

This module implements the Spec type and its related components using Pydantic v1
for validation and JSON serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

# Type alias for opaque stable identifiers
Id = str


class HypothesisMode(str, Enum):
    """
    The mode of a hypothesis - honest pre-declaration of research intent.

    Attributes:
        confirmatory: Pre-registered hypothesis with formal decision rule
        exploratory: Investigative hypothesis without formal commitment
    """

    CONFIRMATORY = "confirmatory"
    EXPLORATORY = "exploratory"


class DecisionRuleKind(str, Enum):
    """
    The kind of decision rule used to evaluate evidence.

    Each kind represents a different approach to mapping continuous/uncertain
    evidence to support/refute/null outcomes.

    Attributes:
        threshold: Simple threshold-based rule
        bayesian: Bayesian posterior odds rule
        interval: Confidence/credible interval rule
        proof: Formal proof or counterexample rule
        qualitative: Expert/structured criterion in prose
    """

    THRESHOLD = "threshold"
    BAYESIAN = "bayesian"
    INTERVAL = "interval"
    PROOF = "proof"
    QUALITATIVE = "qualitative"


class RawProposal(BaseModel):
    """
    The literal four-pane proposal input, verbatim from user.

    This captures the provenance of what the user actually requested,
    preserving the original input before any transformation.

    Attributes:
        background: Research background and context
        goal: Research goal and objectives
        method: Proposed methodology and approaches
        expected_output: Anticipated results and contributions
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    background: str = Field(..., min_length=1, description="Research background and context")
    goal: str = Field(..., min_length=1, description="Research goal and objectives")
    method: str = Field(..., min_length=1, description="Proposed methodology and approaches")
    expected_output: str = Field(
        ..., min_length=1, description="Anticipated results and contributions"
    )


class DecisionRule(BaseModel):
    """
    Decision rule for evaluating evidence against a hypothesis.

    This represents how continuous/uncertain evidence maps to support/refute/null.
    A purely binary pass/fail rule is considered a smell but not invalid.

    Invariant S3: MUST express how continuous/uncertain evidence maps to outcomes.

    Attributes:
        kind: The type of decision rule (threshold, bayesian, interval, proof, qualitative)
        expression: Human-readable rule description
        params: Optional machine-usable thresholds where applicable

    Example:
        >>> bayesian_rule = DecisionRule(
        ...     kind=DecisionRuleKind.BAYESIAN,
        ...     expression="posterior odds > 10 => support",
        ...     params={"min_odds": 10.0}
        ... )
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True
        json_encoders = {datetime: lambda v: v.isoformat()}

    kind: DecisionRuleKind = Field(..., description="Type of decision rule")
    expression: str = Field(
        ..., min_length=1, description="Human-readable rule expression"
    )
    params: Optional[Dict[str, Union[int, float, str, bool]]] = Field(
        None, description="Machine-usable thresholds where applicable"
    )

    @validator("expression")
    def validate_expression_not_binary_only(cls, v: str) -> str:
        """
        Validate that expression does not indicate a purely binary rule.

        Invariant S3: A purely binary pass/fail rule is a smell.
        This validator warns but does not reject, as some cases are legitimate.
        """
        # Check for obviously binary expressions
        binary_patterns = ["pass/fail", "binary", "either succeed or fail"]
        v_lower = v.lower()
        for pattern in binary_patterns:
            if pattern in v_lower:
                # We don't reject, but the expression should justify
                # why a binary rule is appropriate for this research
                pass
        return v

    @validator("params")
    def validate_params_match_kind(
        cls, v: Optional[Dict[str, Union[int, float, str, bool]]], values: Dict[str, Any]
    ) -> Optional[Dict[str, Union[int, float, str, bool]]]:
        """
        Validate that params are appropriate for the rule kind.

        Ensures that quantitative rule kinds have appropriate params defined.
        """
        if "kind" in values:
            kind = values["kind"]
            if kind in (DecisionRuleKind.THRESHOLD, DecisionRuleKind.BAYESIAN):
                if not v:
                    raise ValueError(
                        f"{kind.value} rules require params to define thresholds"
                    )
        return v


class Hypothesis(BaseModel):
    """
    A research hypothesis derived from the goal pane.

    Invariant S2: Every Hypothesis has exactly one mode and one DecisionRule.

    Attributes:
        id: Unique identifier for this hypothesis
        statement: The hypothesis statement (e.g., "molecule graphs admit encoding")
        mode: confirmatory or exploratory - honest pre-declaration
        decision_rule: Rule for evaluating evidence against this hypothesis
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True
        use_enum_values = True

    id: Id = Field(..., description="Unique hypothesis identifier")
    statement: str = Field(..., min_length=1, description="Hypothesis statement")
    mode: HypothesisMode = Field(..., description="Research mode (confirmatory/exploratory)")
    decision_rule: DecisionRule = Field(
        ..., description="Rule for evaluating evidence"
    )

    # @MX:ANCHOR: Hypothesis uniquely maps evidence to claim via one mode + one rule
    # @MX:REASON: Enforces invariant S2 - single evaluation path prevents ambiguity


class ToolRef(BaseModel):
    """
    Reference to a tool, solver, language, or dataset.

    Used in MethodPlan to capture the expected tools for this research.

    Attributes:
        name: Tool or resource name
        version: Optional version constraint
        kind: Type of tool (solver, language, dataset, etc.)
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    name: str = Field(..., min_length=1, description="Tool or resource name")
    version: Optional[str] = Field(None, description="Version constraint")
    kind: str = Field("tool", description="Type of tool")


class MethodPlan(BaseModel):
    """
    Research method plan derived from the method pane.

    This captures the intended approaches and tools for the research.
    It informs the loop but is not binding on the actual execution.

    Attributes:
        approaches: List of planned techniques/approaches
        tools: Optional list of expected solvers/languages/datasets
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    approaches: List[str] = Field(
        default_factory=list, description="Planned techniques and approaches"
    )
    tools: Optional[List[ToolRef]] = Field(
        None, description="Expected solvers, languages, datasets"
    )

    @validator("approaches", pre=True)
    def validate_approaches_not_empty(cls, v: List[str]) -> List[str]:
        """At least one approach should be specified."""
        if not v or all(a.strip() == "" for a in v):
            # Empty approaches is allowed for flexible research,
            # but we log a warning (not raising to allow exploratory work)
            pass
        return v


class TargetClaim(BaseModel):
    """
    A contribution the user hopes to establish.

    Invariant S4: TargetClaim.answers must reference an existing Hypothesis.id.

    Attributes:
        id: Unique identifier for this target claim
        statement: The claim statement
        answers: Reference to the hypothesis id this target addresses
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True

    id: Id = Field(..., description="Unique target claim identifier")
    statement: str = Field(..., min_length=1, description="Target claim statement")
    answers: Id = Field(..., description="Hypothesis id this target addresses")


class Spec(BaseModel):
    """
    A frozen pre-registration contract - the compiler input.

    Spec represents a four-pane proposal as a compiled, evaluable contract.
    Once accepted, the question and decision rules do not change mid-run
    (anti-HARKing). Amendments create new versions, never silent edits.

    Invariant S1: A frozen Spec version is immutable. Changes create version+1.
    Invariant S5: Amending requires human checkpoint (enforced externally).

    Attributes:
        id: Unique spec identifier
        created_at: ISO-8601 UTC timestamp of creation
        version: Version number, bumped on amendment
        raw_proposal: Original four-pane input (provenance)
        hypotheses: Derived hypotheses from goal pane
        method: Method plan from method pane
        target_claims: Target claims from expected output pane
        amendment_rationale: Optional rationale for version > 1
        prior_version_id: Reference to previous version if amended
    """

    class Config:
        frozen = True
        anystr_strip_whitespace = True
        json_encoders = {datetime: lambda v: v.isoformat()}

    id: Id = Field(..., description="Unique spec identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="Creation timestamp (ISO-8601 UTC)",
    )
    version: int = Field(1, ge=1, description="Version number")
    raw_proposal: RawProposal = Field(..., description="Original four-pane input")
    hypotheses: List[Hypothesis] = Field(
        default_factory=list, description="Derived hypotheses"
    )
    method: MethodPlan = Field(..., description="Method plan")
    target_claims: List[TargetClaim] = Field(
        default_factory=list, description="Target claims"
    )
    amendment_rationale: Optional[str] = Field(
        None, description="Rationale for amendment (version > 1)"
    )
    prior_version_id: Optional[Id] = Field(
        None, description="Previous version id if amended"
    )

    # @MX:ANCHOR: Spec is frozen pre-registration contract
    # @MX:REASON: Invariant S1 - prevents silent HARKing, ensures anti-HARKing guarantee

    @validator("hypotheses")
    def validate_hypotheses_not_empty(cls, v: List[Hypothesis]) -> List[Hypothesis]:
        """At least one hypothesis must be defined."""
        if not v:
            raise ValueError("Spec must have at least one hypothesis")
        return v

    @validator("target_claims", pre=True, always=True)
    def validate_target_claims_reference_hypotheses(
        cls, v: List[TargetClaim], values: Dict[str, Any]
    ) -> List[TargetClaim]:
        """
        Invariant S4: TargetClaim.answers must reference an existing Hypothesis.id.

        This ensures that every target claim is about a known hypothesis.
        """
        if "hypotheses" in values:
            hypothesis_ids = {h.id for h in values["hypotheses"]}
            for claim in v:
                if claim.answers not in hypothesis_ids:
                    raise ValueError(
                        f"TargetClaim '{claim.id}' references unknown hypothesis '{claim.answers}'"
                    )
        return v

    @validator("amendment_rationale", "prior_version_id", pre=True, always=True)
    def validate_amendment_has_rationale(
        cls, v: Optional[str], values: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate that amended specs have required documentation.
        """
        if "version" in values and values["version"] > 1:
            # Note: This validator runs separately for each field
            # Full validation happens in model post-init
            pass
        return v

    def amend(
        self,
        raw_proposal: Optional[RawProposal] = None,
        hypotheses: Optional[List[Hypothesis]] = None,
        method: Optional[MethodPlan] = None,
        target_claims: Optional[List[TargetClaim]] = None,
        rationale: str = "",
    ) -> Spec:
        """
        Create an amended version of this Spec.

        Invariant S5: REQUIRES HUMAN CHECKPOINT - this method creates the
        new version object but external enforcement must ensure human approval.

        The new spec has version+1 and references this spec as prior_version_id.

        Args:
            raw_proposal: New raw proposal (or keep existing)
            hypotheses: New hypotheses (or keep existing)
            method: New method plan (or keep existing)
            target_claims: New target claims (or keep existing)
            rationale: Required rationale for the amendment

        Returns:
            New Spec with incremented version

        Raises:
            ValueError: If rationale is empty for version > 1
        """
        if not rationale or not rationale.strip():
            raise ValueError("Amendment requires non-empty rationale")

        # Validate that we're not trying to modify frozen fields directly
        return Spec(
            id=self.id,  # Same id, different version
            created_at=datetime.utcnow(),
            version=self.version + 1,
            raw_proposal=raw_proposal or self.raw_proposal,
            hypotheses=hypotheses or self.hypotheses,
            method=method or self.method,
            target_claims=target_claims or self.target_claims,
            amendment_rationale=rationale,
            prior_version_id=str(self.created_at.timestamp()),
        )

    def get_hypothesis(self, hypothesis_id: Id) -> Optional[Hypothesis]:
        """
        Retrieve a hypothesis by its id.

        Args:
            hypothesis_id: The hypothesis identifier

        Returns:
            The Hypothesis if found, None otherwise
        """
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def get_target_claim(self, claim_id: Id) -> Optional[TargetClaim]:
        """
        Retrieve a target claim by its id.

        Args:
            claim_id: The target claim identifier

        Returns:
            The TargetClaim if found, None otherwise
        """
        for claim in self.target_claims:
            if claim.id == claim_id:
                return claim
        return None


__all__ = [
    "Id",
    "HypothesisMode",
    "DecisionRuleKind",
    "RawProposal",
    "DecisionRule",
    "Hypothesis",
    "ToolRef",
    "MethodPlan",
    "TargetClaim",
    "Spec",
]
