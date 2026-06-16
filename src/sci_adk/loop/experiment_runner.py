"""
Experiment runner for sci-adk research loop.

Executes experiments and generates EvidenceItems with provenance.
Reference: design/directory-structure.md (loop/)
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Spec
from sci_adk.runner.docker_executor import DockerExecutor


class ExperimentRunner:
    """
    Run experiments and generate EvidenceItems.

    Milestone 1: T-1 molecular encoding experiments.
    Full loop controller deferred to milestone 2+.
    """

    def __init__(
        self,
        spec: Spec,
        workspace_dir: Optional[Path] = None,
    ):
        """
        Initialize experiment runner.

        Args:
            spec: Spec instance for this research run
            workspace_dir: Output directory for evidence
        """
        self.spec = spec
        self.workspace_dir = workspace_dir or Path.cwd()
        self.evidence_dir = self.workspace_dir / "runs" / spec.id / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _generate_evidence_id(self) -> str:
        """Generate a unique Evidence ID.

        The timestamp gives human-readable ordering; the short uuid suffix
        guarantees uniqueness even when several items are created within the same
        wall-clock second (a second-resolution timestamp alone collides).
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"evi-{timestamp}-{uuid.uuid4().hex[:8]}"

    def _capture_environment(self, provenance: Dict[str, Any]) -> str:
        """Capture environment description."""
        parts = [
            f"docker:{provenance.get('image_name', 'unknown')}",
            f"image_id:{provenance.get('image_id', 'unknown')}",
        ]
        return ", ".join(parts)

    def _save_evidence(self, evidence: EvidenceItem) -> None:
        """Save EvidenceItem to JSON file."""
        filename = f"{evidence.id}.json"
        filepath = self.evidence_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(evidence.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
