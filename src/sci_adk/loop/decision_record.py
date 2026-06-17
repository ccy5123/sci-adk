"""
Shared writer for discovery-trigger *decision* EvidenceItems (one implementation).

design/literature-acquisition.md §"Discovery trigger model": the Spec-creation
prior-art trigger and the novelty / contested triggers each record a *decision* into
the single append-only Evidence log. They differ only in the EvidenceKind, the id
prefix, and (for the hypothesis-bound triggers) a ``LiteratureDecision`` payload --
NOT in the write/id/save mechanics. This module is the single home for those
mechanics so no caller duplicates them (``prior_work.py`` and
``literature_triggers.py`` both call :func:`write_decision_evidence`).

A decision is a record, not a belief: every item written here carries ``bears_on=[]``
(it asserts no support/refute direction on any hypothesis and never enters the
DecisionEngine). Kernel-side, no LLM.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sci_adk.core.evidence import (
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
    Provenance,
    Result,
)
from sci_adk.core.spec import Spec


def write_decision_evidence(
    spec: Spec,
    workspace_dir: Optional[Path],
    *,
    kind: EvidenceKind,
    finding: str,
    provenance: Provenance,
    id_prefix: str,
    literature_decision: Optional[LiteratureDecision] = None,
) -> EvidenceItem:
    """Persist a decision EvidenceItem of ``kind`` into ``runs/<spec.id>/evidence/``.

    The ONE writer shared by every discovery-trigger decision recorder. The item is a
    recorded decision, not a belief -- ``bears_on`` is always empty.

    Args:
        spec: the governing Spec (its ``id`` selects the run directory).
        workspace_dir: workspace root holding ``runs/`` (default: cwd).
        kind: the decision EvidenceKind (PRIOR_WORK_DECISION / NOVELTY_DECISION /
            CONTESTED_RECORD).
        finding: the qualitative finding text recorded on the item.
        provenance: the item's provenance block.
        id_prefix: the id stem (e.g. ``"evi-nov-decision"``) -- a timestamp + short uuid
            suffix make it unique within a run.
        literature_decision: the hypothesis-bound payload (None for the Spec-bound
            prior-art decision, which is per Spec, not per hypothesis).

    Returns:
        The persisted EvidenceItem.
    """
    workspace = Path(workspace_dir) if workspace_dir else Path.cwd()
    evidence_dir = workspace / "runs" / spec.id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    item = EvidenceItem(
        id=_generate_id(id_prefix),
        spec_id=spec.id,
        kind=kind,
        provenance=provenance,
        result=Result(type="qualitative", finding=finding),
        bears_on=[],  # a recorded decision, not a belief -> no bearing
        literature_decision=literature_decision,
    )
    (evidence_dir / f"{item.id}.json").write_text(
        json.dumps(item.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return item


def _generate_id(prefix: str) -> str:
    """``<prefix>-<UTC timestamp>-<short uuid>`` -- human-ordered and unique."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


__all__ = ["write_decision_evidence"]
