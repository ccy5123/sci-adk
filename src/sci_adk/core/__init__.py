"""
sci-adk Core Types

The three core types of the sci-adk research compiler:

1. Spec - Frozen pre-registration contract (compiler input)
2. Evidence - Immutable, append-only record (what happened)
3. Claim - Revisable belief state (what we believe, compiler output)

Core principle: Record (Evidence, append-only) vs Belief (Claim, revisable) separation.

These types implement the invariants specified in design/abstractions.md v0.1.
"""

from .spec import (
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

from .evidence import (
    Bearing,
    BearingDirection,
    Cost,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)

from .claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceLevel,
    ConfidenceType,
    EvidenceLink,
    EvidenceLinkRole,
    StatusChange,
)

__all__ = [
    # Spec types
    "DecisionRule",
    "DecisionRuleKind",
    "Hypothesis",
    "HypothesisMode",
    "Id",
    "MethodPlan",
    "RawProposal",
    "Spec",
    "TargetClaim",
    "ToolRef",
    # Evidence types
    "Bearing",
    "BearingDirection",
    "Cost",
    "EvidenceItem",
    "EvidenceKind",
    "Provenance",
    "Result",
    # Claim types
    "Claim",
    "ClaimStatus",
    "Confidence",
    "ConfidenceLevel",
    "ConfidenceType",
    "EvidenceLink",
    "EvidenceLinkRole",
    "StatusChange",
]
