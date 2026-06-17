"""
sci-adk loop package.

Research execution loop components.
"""

from sci_adk.loop.experiment_runner import ExperimentRunner
from sci_adk.loop.claim_updater import (
    ClaimUpdater,
    update_claims,
)
from sci_adk.loop.decision_engine import (
    DecisionEngine,
    EvidenceForHypothesis,
    Verdict,
)
from sci_adk.loop.judge import (
    ClaudeJudge,
    Judge,
    JudgeVerdict,
)
from sci_adk.loop.compiler import (
    Checkpoint,
    CompileResult,
    ResearchCompiler,
)
from sci_adk.loop.verdict import (
    CheckpointModel,
    ChiefVerdict,
    ContestedCheckpoint,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)
from sci_adk.loop.recorded_judge import RecordedJudge
from sci_adk.loop.checkpoint_loop import LoopResult, run_checkpoint_loop
from sci_adk.loop.literature_acquirer import (
    AcquisitionHalt,
    AcquisitionOutcome,
    HaltItem,
    HaltReason,
    LiteratureAcquirer,
    acquire_literature,
)
from sci_adk.loop.literature_triggers import (
    contested_checkpoint,
    contested_open,
    record_contested,
    record_novelty_searched,
    record_novelty_skip,
)

__all__ = [
    "ExperimentRunner",
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
    "Judge",
    "JudgeVerdict",
    "ClaudeJudge",
    "ResearchCompiler",
    "CompileResult",
    "Checkpoint",
    "CheckpointModel",
    "ChiefVerdict",
    "ContestedCheckpoint",
    "PanelVerdict",
    "VerdictProvenance",
    "VerdictTrail",
    "RecordedJudge",
    "LoopResult",
    "run_checkpoint_loop",
    "record_novelty_searched",
    "record_novelty_skip",
    "record_contested",
    "contested_checkpoint",
    "contested_open",
]
