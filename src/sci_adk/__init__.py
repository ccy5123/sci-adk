"""sci-adk — a rigor / verification ADK (Agentic Discovery Kit).

This package root is the **curated public Python API** that semver 1.0 promises
to keep stable (the CLI in ``sci_adk.cli`` is the other half of the contract).
The surface is fixed in ``design/surface-freeze-analysis.md`` §4 and is exactly
the record/belief core plus the sole verdict path:

  - Spec   (frozen compiler input — the pre-registration contract)
  - Evidence (the append-only record: ``EvidenceItem`` + its components)
  - Claim  (the revisable belief derived from Evidence)
  - the verdict engine + the read-only ``verify`` entry points

Everything NOT re-exported here is **internal and unstable** — free to change
within a major version. In particular ``sci_adk.adapter`` (the T-1 capability +
registry; A1b is scoped out of the 1.0 claim, ``design/g-a-a3-decision.md``),
``sci_adk.render`` internals, ``sci_adk.search``, ``sci_adk.provenance``, and the
non-verdict ``sci_adk.loop`` modules are deliberately NOT part of the promise.

Importing a name from here is the supported way for a Python embedder to reach
the kernel; reaching into submodules directly is allowed but unversioned.
"""

from __future__ import annotations

# -- Spec: the frozen compiler input (record) ------------------------------------
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    DiscriminatingCase,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)

# -- Evidence: the append-only record --------------------------------------------
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    Cost,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)

# -- Claim: the revisable belief -------------------------------------------------
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

# -- the verdict engine + the sole read-only verdict path ------------------------
from sci_adk.loop.decision_engine import DecisionEngine
from sci_adk.loop.verify import (
    PackageVerifyReport,
    VerifyReport,
    verify_package,
    verify_run,
)

__all__ = [
    # Spec
    "Spec",
    "Hypothesis",
    "RawProposal",
    "MethodPlan",
    "DecisionRule",
    "TargetClaim",
    "DiscriminatingCase",
    "HypothesisMode",
    "DecisionRuleKind",
    # Evidence
    "EvidenceItem",
    "Provenance",
    "Result",
    "Bearing",
    "Cost",
    "EvidenceKind",
    "BearingDirection",
    # Claim
    "Claim",
    "Confidence",
    "EvidenceLink",
    "StatusChange",
    "ClaimStatus",
    "ConfidenceType",
    "ConfidenceLevel",
    "EvidenceLinkRole",
    # verdict path
    "DecisionEngine",
    "verify_run",
    "verify_package",
    "VerifyReport",
    "PackageVerifyReport",
]
