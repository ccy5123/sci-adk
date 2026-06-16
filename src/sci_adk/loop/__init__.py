"""
sci-adk loop package.

Research execution loop components.
"""

from sci_adk.loop.experiment_runner import (
    ExperimentRunner,
    run_t1_experiments,
)
from sci_adk.loop.claim_updater import (
    ClaimUpdater,
    update_claims,
)
from sci_adk.loop.decision_engine import (
    DecisionEngine,
    EvidenceForHypothesis,
    Verdict,
)
from sci_adk.loop.literature_acquirer import (
    AcquisitionHalt,
    AcquisitionOutcome,
    HaltItem,
    HaltReason,
    LiteratureAcquirer,
    acquire_literature,
)

__all__ = [
    "ExperimentRunner",
    "run_t1_experiments",
    "ClaimUpdater",
    "update_claims",
    "DecisionEngine",
    "EvidenceForHypothesis",
    "Verdict",
    "LiteratureAcquirer",
    "acquire_literature",
    "AcquisitionOutcome",
    "AcquisitionHalt",
    "HaltItem",
    "HaltReason",
]
