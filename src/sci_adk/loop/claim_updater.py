"""
Claim updater for sci-adk research loop.

Evaluates Evidence against Spec DecisionRules and updates Claims.
Reference: design/directory-structure.md (loop/), design/decision-engine.md §4.

Phase D4 (design/decision-engine.md §4): ``ClaimUpdater`` no longer counts
``SUPPORTS``/``REFUTES`` bearings. It DELEGATES belief computation to the
``DecisionEngine`` -- the per-Spec ``DecisionRule`` is now the sole authority for
direction and confidence (D1) -- and only *assembles / persists* the resulting
``Claim``. It also supports non-monotone updates: re-running over an appended,
append-only record can demote a Claim, recording every move in the Claim's
append-only history (Decision 8, C1/C2).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    EvidenceLink,
    EvidenceLinkRole,
    StatusChange,
)
from sci_adk.core.evidence import EvidenceItem, BearingDirection
from sci_adk.core.spec import Spec
from sci_adk.core.validity import check_evidence_adequacy

from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
from sci_adk.loop.judge import Judge


# Decision 8 (design/decision-engine.md §3): how an engine ``Verdict.direction``
# maps to a ``ClaimStatus``. ``supports``->SUPPORTED, ``refutes``->REFUTED,
# ``neutral``/``inconclusive``->PROPOSED. CONTESTED is NOT in this table: the
# engine aggregates to ONE direction and cannot itself signal "mixed evidence",
# so CONTESTED is decided separately from the RAW bearings (see
# ``status_for_verdict``). ``retracted`` is reserved for provenance failure
# and is never emitted here.
#
# PUBLIC (Fix 1): this is the SINGLE source of truth for the verdict -> ClaimStatus
# derivation. Both the persister (``ClaimUpdater``) and the read-only audit
# (``loop/verify.py``) MUST use ``DIRECTION_TO_STATUS`` + ``status_for_verdict`` --
# never a private copy or a replayed contested rule -- so the two cannot drift.
DIRECTION_TO_STATUS: dict[BearingDirection, ClaimStatus] = {
    BearingDirection.SUPPORTS: ClaimStatus.SUPPORTED,
    BearingDirection.REFUTES: ClaimStatus.REFUTED,
    BearingDirection.NEUTRAL: ClaimStatus.PROPOSED,
    BearingDirection.INCONCLUSIVE: ClaimStatus.PROPOSED,
}


def status_for_verdict(verdict, raw_directions: set) -> ClaimStatus:
    """Map an engine ``Verdict`` to a ``ClaimStatus`` (Decision 8) -- the one public
    source of truth, mapping + the CONTESTED override.

    The engine aggregates the bearings to ONE direction, so it cannot by itself report
    "mixed evidence". The single judgment call (FLAGGED for orchestrator review in
    Phase D4) is the CONTESTED override: whenever the RAW bearings on this hypothesis
    contain BOTH a ``SUPPORTS`` and a ``REFUTES`` (support and refutation coexist --
    matching ``ClaimStatus.CONTESTED`` "mixed evidence; support and refutation
    coexist", C5), the status is CONTESTED regardless of the engine's single direction.
    Otherwise the direction maps via ``DIRECTION_TO_STATUS``. ``retracted`` is reserved
    for provenance failure and is never emitted here.

    Both the persister (``ClaimUpdater._apply_update`` / ``_create_claim``) and the
    read-only audit (``loop/verify.py``) call THIS function, so a faithful record
    re-derives exactly the status the updater persisted -- there is no second copy of
    this logic to drift out of sync.

    Args:
        verdict: the engine's ``Verdict`` (its ``direction`` drives the mapping).
        raw_directions: the set of RAW ``BearingDirection`` values across the bearings
            on this hypothesis (used only for the CONTESTED override).
    """
    # @MX:ANCHOR: [AUTO] the single public verdict->ClaimStatus derivation (Decision 8).
    # @MX:REASON: [AUTO] ClaimUpdater (persist) and loop/verify.py (audit) both call this;
    #   it is the one place the mapping + CONTESTED override live. A private copy in
    #   either caller would let the audit tool disagree with what was persisted -- the
    #   exact drift hazard Fix 1 removes. Changing the contested rule here moves both
    #   persisted belief AND its re-derivation in lockstep.
    if (
        BearingDirection.SUPPORTS in raw_directions
        and BearingDirection.REFUTES in raw_directions
    ):
        return ClaimStatus.CONTESTED
    return DIRECTION_TO_STATUS[verdict.direction]


class ClaimUpdater:
    """
    Update Claims based on Evidence by delegating belief to the DecisionEngine.

    The updater pre-filters the Evidence log to the bearings on each hypothesis,
    hands the hypothesis's frozen ``DecisionRule`` + those bearings to
    ``DecisionEngine.evaluate``, maps the returned ``Verdict`` to a Claim status
    (Decision 8), and persists the Claim. Belief computation lives entirely in the
    engine (D1); the updater owns only record-keeping and the non-monotone
    load-or-create + ``update_status`` mechanics.
    """

    def __init__(
        self,
        spec: Spec,
        workspace_dir: Optional[Path] = None,
        judge: Optional[Judge] = None,
    ):
        """
        Initialize claim updater.

        Args:
            spec: Spec instance with DecisionRules
            workspace_dir: Output directory for claims
            judge: optional LLM-judge forwarded to the DecisionEngine for
                proof/qualitative rules (Decision 4). When None (the default,
                zero-cost path), those rules return inconclusive and are surfaced
                as agent checkpoints rather than judged autonomously.
        """
        self.spec = spec
        self.workspace_dir = workspace_dir or Path.cwd()
        self.claims_dir = self.workspace_dir / "runs" / spec.id / "claims"
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        # The engine holds no state and no constants (D1); one instance suffices.
        self.engine = DecisionEngine(judge=judge)

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
        Evaluate a hypothesis by DELEGATING belief to the DecisionEngine, then
        assemble (or non-monotonically update) the Claim (design/decision-engine.md §4).

        The verdict is recomputed over the FULL append-only set of bearings on the
        hypothesis every time (record is monotone; belief is recomputed), so a
        previously ``SUPPORTED`` Claim can be demoted as refuting Evidence arrives
        (Decision 8). The engine supplies the kind-correct ``Confidence`` (with a
        required basis) directly -- no hardcoded ``credence``.

        Args:
            hypothesis: Hypothesis to evaluate (carries the frozen DecisionRule)
            evidence_items: EvidenceItems already pre-filtered to this hypothesis

        Returns:
            A freshly created Claim, or the loaded Claim mutated in place.
        """
        # Build the engine's pre-filtered view: every (EvidenceItem, Bearing) pair
        # whose bearing targets this hypothesis (the pre-filter from line 67-71 stays).
        results = EvidenceForHypothesis(
            pairs=[
                (ev, b)
                for ev in evidence_items
                for b in ev.bears_on
                if b.target_id == hypothesis.id
            ]
        )

        # Delegate: the per-Spec DecisionRule is the sole authority for direction
        # and confidence (D1). The vote-count is gone.
        verdict = self.engine.evaluate(hypothesis.decision_rule, results)

        # Evidence-validity adequacy gate (design/evidence-validity.md E3): refuse to
        # turn an inadequate record into a Claim. This runs AFTER the engine renders a
        # verdict (so the gate knows whether it is binding) but BEFORE any Claim is
        # assembled or persisted, so a halt means NO Claim is written -- an ungrounded
        # empirical result can never be self-certified. ``evidence_items`` is already
        # pre-filtered to the bearings on this hypothesis (line 146-149). A halt
        # propagates out of the updater; the CLI turns it into a friendly non-zero exit.
        check_evidence_adequacy(hypothesis, evidence_items, verdict.direction)

        raw_directions = {b.direction for _, b in results.pairs}
        status = self._status_for_verdict(verdict, raw_directions)
        confidence = verdict.confidence  # kind-correct type + required basis (Decision 5/C3)

        # The triggering evidence for any status move is the latest-arriving one.
        triggering_id = self._latest_evidence_id(evidence_items)

        # Record-keeping (C5): supporting vs refuting links per bearing direction.
        # This is the RECORD, not the belief -- it stays even though the status is
        # now decided by the engine verdict.
        evidence_links = [
            EvidenceLink(
                evidence_id=ev.id,
                role=EvidenceLinkRole.SUPPORTING
                if any(
                    b.target_id == hypothesis.id
                    and b.direction == BearingDirection.SUPPORTS
                    for b in ev.bears_on
                )
                else EvidenceLinkRole.REFUTING,
            )
            for ev in evidence_items
        ]

        existing = self._load_claim(hypothesis)
        if existing is not None:
            return self._apply_update(existing, status, confidence, evidence_links, triggering_id)
        return self._create_claim(hypothesis, status, confidence, evidence_links, triggering_id)

    @staticmethod
    def _status_for_verdict(verdict, raw_directions: set) -> ClaimStatus:
        """Thin delegate to the public :func:`status_for_verdict` (Fix 1).

        The verdict -> ClaimStatus derivation (mapping + CONTESTED override) now lives
        in ONE public place so the persister and the read-only audit share it. This
        method is retained for its existing internal call site and stays
        behavior-identical; the confidence still comes from the engine verdict (the
        caller passes ``verdict.confidence`` regardless of this status).
        """
        return status_for_verdict(verdict, raw_directions)

    @staticmethod
    def _latest_evidence_id(evidence_items: List[EvidenceItem]) -> str:
        """
        Return the id of the latest-arriving EvidenceItem (the one that triggers a
        status move, Decision 8). Latest is by ``created_at``, breaking ties toward
        the later position in the supplied (append/arrival) order so the choice is
        deterministic. Empty input yields ``""`` (parity with the prior behavior).
        """
        if not evidence_items:
            return ""
        latest = max(
            enumerate(evidence_items),
            key=lambda pair: (pair[1].created_at, pair[0]),
        )[1]
        return latest.id

    def _load_claim(self, hypothesis) -> Optional[Claim]:
        """
        Load the persisted Claim for this hypothesis if one exists (Decision 8
        load-or-create), else return ``None``.

        The Claim id is stable (``claim-<hyp.id>``), so the on-disk JSON is the
        record of prior belief; loading it lets ``update_status`` append to the
        existing append-only history rather than overwriting it (C2).
        """
        filepath = self.claims_dir / f"{self._generate_claim_id(hypothesis)}.json"
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return Claim.model_validate(json.load(f))

    def _apply_update(
        self,
        claim: Claim,
        status: ClaimStatus,
        confidence,
        evidence_links: List[EvidenceLink],
        triggering_id: str,
    ) -> Claim:
        """
        Non-monotonically update an existing Claim (Decision 8).

        Refreshes the evidence_set (record-keeping, C5), then -- only if the newly
        computed status DIFFERS from the current one -- threads the move through
        ``Claim.update_status`` (which appends a ``StatusChange``, satisfying C1
        non-monotone movement and C2 append-only history). Confidence is always
        refreshed from the engine verdict (basis remains required, C3). A
        ``SUPPORTED -> CONTESTED -> REFUTED`` path is legal and expected, not a
        regression. No spurious StatusChange is appended when the status is stable
        (D5: only NEW evidence that moves the verdict moves the history).
        """
        claim.evidence_set = self._merge_links(claim.evidence_set, evidence_links)

        if claim.status != status:
            claim.update_status(
                status,
                triggered_by=triggering_id,
                note=f"Re-evaluation moved status to {status.value}",
            )

        claim.update_confidence(
            confidence_type=confidence.type,
            value=confidence.value,
            level=confidence.level,
            basis=confidence.basis,
        )
        return claim

    def _create_claim(
        self,
        hypothesis,
        status: ClaimStatus,
        confidence,
        evidence_links: List[EvidenceLink],
        triggering_id: str,
    ) -> Claim:
        """
        Create a fresh Claim with one initial ``StatusChange`` (Milestone-1 parity
        with the prior first-evaluation behavior, Decision 8 / §4 item 3).
        """
        return Claim(
            id=self._generate_claim_id(hypothesis),
            spec_id=self.spec.id,
            answers=hypothesis.id,
            statement=hypothesis.statement,
            status=status,
            confidence=confidence,
            evidence_set=evidence_links,
            mode=hypothesis.mode,
            renders_to=None,
            history=[
                StatusChange(
                    at=datetime.now(timezone.utc),
                    from_status=ClaimStatus.PROPOSED,
                    to_status=status,
                    triggered_by=triggering_id,
                    note="Initial evaluation via DecisionEngine",
                )
            ],
        )

    @staticmethod
    def _merge_links(
        existing: List[EvidenceLink],
        new_links: List[EvidenceLink],
    ) -> List[EvidenceLink]:
        """
        Merge new evidence links into the existing set without duplicating
        (evidence_id, role) pairs. Order is preserved: existing links first, then
        any genuinely new ones (the Evidence log is append-only, so links only grow).
        """
        seen = {(link.evidence_id, link.role) for link in existing}
        merged = list(existing)
        for link in new_links:
            key = (link.evidence_id, link.role)
            if key not in seen:
                seen.add(key)
                merged.append(link)
        return merged

    def _generate_claim_id(self, hypothesis) -> str:
        """Generate Claim ID for hypothesis (stable per hypothesis)."""
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


__all__ = [
    "DIRECTION_TO_STATUS",
    "status_for_verdict",
    "ClaimUpdater",
    "update_claims",
]
