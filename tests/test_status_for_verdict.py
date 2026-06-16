"""
RED-first (Fix 1): a SINGLE PUBLIC source of truth for verdict -> ClaimStatus.

design/decision-engine.md §3 (Decision 8): how an engine ``Verdict.direction`` maps
to a ``ClaimStatus``, plus the one judgment call -- the CONTESTED override (RAW
bearings contain BOTH a SUPPORTS and a REFUTES -> CONTESTED). This derivation must
live in ONE public place so the persister (``ClaimUpdater``) and the read-only audit
(``verify``) cannot drift: a private import + a replayed contested rule in two modules
is a correctness hazard for the audit tool.

These tests pin the public surface:
  - ``DIRECTION_TO_STATUS`` (public mapping constant), and
  - ``status_for_verdict(verdict, raw_directions)`` (public function, mapping + override).
"""

from __future__ import annotations

from sci_adk.core.claim import ClaimStatus, Confidence, ConfidenceLevel, ConfidenceType
from sci_adk.core.evidence import BearingDirection
from sci_adk.loop import claim_updater as cu
from sci_adk.loop.claim_updater import DIRECTION_TO_STATUS, status_for_verdict
from sci_adk.loop.decision_engine import Verdict


def _verdict(direction: BearingDirection) -> Verdict:
    return Verdict(
        direction=direction,
        confidence=Confidence(
            type=ConfidenceType.GRADED, level=ConfidenceLevel.NONE, basis="b"
        ),
    )


def test_direction_to_status_is_public_and_in_all():
    assert "DIRECTION_TO_STATUS" in cu.__all__
    assert "status_for_verdict" in cu.__all__
    assert DIRECTION_TO_STATUS[BearingDirection.SUPPORTS] == ClaimStatus.SUPPORTED
    assert DIRECTION_TO_STATUS[BearingDirection.REFUTES] == ClaimStatus.REFUTED
    assert DIRECTION_TO_STATUS[BearingDirection.NEUTRAL] == ClaimStatus.PROPOSED
    assert DIRECTION_TO_STATUS[BearingDirection.INCONCLUSIVE] == ClaimStatus.PROPOSED


def test_status_for_verdict_maps_each_direction():
    assert status_for_verdict(_verdict(BearingDirection.SUPPORTS), set()) == ClaimStatus.SUPPORTED
    assert status_for_verdict(_verdict(BearingDirection.REFUTES), set()) == ClaimStatus.REFUTED
    assert status_for_verdict(_verdict(BearingDirection.NEUTRAL), set()) == ClaimStatus.PROPOSED
    assert status_for_verdict(_verdict(BearingDirection.INCONCLUSIVE), set()) == ClaimStatus.PROPOSED


def test_status_for_verdict_contested_override():
    # Both SUPPORTS and REFUTES among the raw bearings -> CONTESTED, regardless of the
    # engine's single aggregated direction.
    raw = {BearingDirection.SUPPORTS, BearingDirection.REFUTES}
    assert status_for_verdict(_verdict(BearingDirection.SUPPORTS), raw) == ClaimStatus.CONTESTED
    assert status_for_verdict(_verdict(BearingDirection.REFUTES), raw) == ClaimStatus.CONTESTED
    assert status_for_verdict(_verdict(BearingDirection.NEUTRAL), raw) == ClaimStatus.CONTESTED


def test_status_for_verdict_no_contested_without_both():
    # Only SUPPORTS present (e.g. one supporting + one neutral bearing) -> not contested.
    raw = {BearingDirection.SUPPORTS, BearingDirection.NEUTRAL}
    assert status_for_verdict(_verdict(BearingDirection.SUPPORTS), raw) == ClaimStatus.SUPPORTED


def test_claim_updater_private_status_method_delegates_to_public():
    # The historical private method must remain behavior-compatible (it now delegates
    # to the public function) so existing call sites/tests are unaffected.
    raw = {BearingDirection.SUPPORTS, BearingDirection.REFUTES}
    assert cu.ClaimUpdater._status_for_verdict(_verdict(BearingDirection.SUPPORTS), raw) == (
        ClaimStatus.CONTESTED
    )
