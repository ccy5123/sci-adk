"""
Claim updater for sci-adk research loop.

Evaluates Evidence against Spec DecisionRules and updates Claims.
Reference: design/directory-structure.md (loop/)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    EvidenceLink,
    EvidenceRole,
    StatusChange,
)
from src.sci_adk.core.evidence import EvidenceItem, BearingDirection
from src.sci_adk.core.spec import Spec


class ClaimUpdater:
    """
    Update Claims based on Evidence.

    Evaluates Evidence against Spec DecisionRules and updates Claim confidence.
    Milestone 1: Basic evaluation without full DecisionRule engine.
    """

    def __init__(
        self,
        spec: Spec,
        workspace_dir: Optional[Path] = None,
    ):
        """
        Initialize claim updater.

        Args:
            spec: Spec instance with DecisionRules
            workspace_dir: Output directory for claims
        """
        self.spec = spec
        self.workspace_dir = workspace_dir or Path.cwd()
        self.claims_dir = self.workspace_dir / "runs" / spec.id / "claims"
        self.claims_dir.mkdir(parents=True, exist_ok=True)

    def update_claims_from_evidence(
        self,
        evidence_items: List[EvidenceItem],
    ) -> List[Claim]:
        """
        Update Claims based on new Evidence.

        Args:
            evidence_items: List of EvidenceItems to evaluate

        Returns:
            Updated/created Claims
        """
        claims = []

        # Process each hypothesis
        for hypothesis in self.spec.hypotheses:
            # Find evidence bearing on this hypothesis
            relevant_evidence = [
                ev for ev in evidence_items
                if any(b.target_id == hypothesis.id for b in ev.bears_on)
            ]

            if not relevant_evidence:
                continue

            # Create or update claim
            claim = self._evaluate_hypothesis(hypothesis, relevant_evidence)
            claims.append(claim)
            self._save_claim(claim)

        return claims

    def _evaluate_hypothesis(
        self,
        hypothesis,
        evidence_items: List[EvidenceItem],
    ) -> Claim:
        """
        Evaluate hypothesis against evidence.

        Milestone 1: Simple support/refute counting.
        Full DecisionRule evaluation deferred to milestone 2+.

        Args:
            hypothesis: Hypothesis to evaluate
            evidence_items: Relevant EvidenceItems

        Returns:
            Claim with updated confidence
        """
        # Count supporting vs refuting evidence
        support_count = 0
        refute_count = 0
        total_weight = 0.0

        for evidence in evidence_items:
            for bearing in evidence.bears_on:
                if bearing.target_id == hypothesis.id:
                    total_weight += bearing.weight or 1.0
                    if bearing.direction == BearingDirection.SUPPORTS:
                        support_count += 1
                    elif bearing.direction == BearingDirection.REFUTES:
                        refute_count += 1

        # Determine status
        if support_count > 0 and refute_count == 0:
            status = ClaimStatus.SUPPORTED
        elif refute_count > 0 and support_count == 0:
            status = ClaimStatus.REFUTED
        elif support_count > 0 and refute_count > 0:
            status = ClaimStatus.CONTESTED
        else:
            status = ClaimStatus.PROPOSED

        # Calculate confidence (simple heuristic)
        if support_count + refute_count > 0:
            confidence_value = support_count / (support_count + refute_count)
        else:
            confidence_value = 0.0

        # Create basis text
        basis = (
            f"Based on {len(evidence_items)} evidence items: "
            f"{support_count} supporting, {refute_count} refuting."
        )

        # Create claim
        claim = Claim(
            id=self._generate_claim_id(hypothesis),
            spec_id=self.spec.id,
            answers=hypothesis.id,
            statement=hypothesis.statement,
            status=status,
            confidence=Confidence(
                type="credence",
                value=confidence_value,
                basis=basis,
            ),
            evidence_set=[
                EvidenceLink(
                    evidence_id=ev.id,
                    role=EvidenceRole.SUPPORTING
                    if any(
                        b.target_id == hypothesis.id
                        and b.direction == BearingDirection.SUPPORTS
                        for b in ev.bears_on
                    )
                    else EvidenceRole.REFUTING,
                )
                for ev in evidence_items
            ],
            scope_limitations="Milestone 1: Limited to T-1 test molecules. Small sample size.",
            mode=hypothesis.mode,
            renders_to=None,  # Milestone 1: no paper rendering
            history=[
                StatusChange(
                    at=datetime.now(timezone.utc).isoformat(),
                    from_status=ClaimStatus.PROPOSED,
                    to_status=status,
                    triggered_by=evidence_items[0].id if evidence_items else "",
                    note=f"Initial evaluation based on {len(evidence_items)} evidence items",
                )
            ],
        )

        return claim

    def _generate_claim_id(self, hypothesis) -> str:
        """Generate Claim ID for hypothesis."""
        return f"claim-{hypothesis.id}"

    def _save_claim(self, claim: Claim) -> None:
        """Save Claim to JSON file."""
        filename = f"{claim.id}.json"
        filepath = self.claims_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(claim.model_dump(mode="json"), f, indent=2, ensure_ascii=False)


def update_claims(
    spec: Spec,
    evidence_items: List[EvidenceItem],
    workspace_dir: Optional[Path] = None,
) -> List[Claim]:
    """
    Convenience function to update Claims from Evidence.

    Args:
        spec: Spec instance
        evidence_items: List of EvidenceItems
        workspace_dir: Output directory

    Returns:
        Updated Claims
    """
    updater = ClaimUpdater(spec, workspace_dir)
    return updater.update_claims_from_evidence(evidence_items)
