"""
Experiment runner for sci-adk research loop.

Executes experiments and generates EvidenceItems with provenance.
Reference: design/directory-structure.md (loop/)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sci_adk.core.evidence import (
    EvidenceItem,
    Provenance,
    Result,
    Bearing,
    EvidenceKind,
    BearingDirection,
)
from sci_adk.core.spec import Spec
from sci_adk.runner.docker_executor import DockerExecutor, execute_t1_molecule_encoding


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

    def run_t1_molecular_encoding(
        self,
        molecules: List[str],
    ) -> EvidenceItem:
        """
        Run T-1 molecular encoding experiment.

        Args:
            molecules: List of molecular formulas to encode

        Returns:
            EvidenceItem with encoding results
        """
        # Execute experiment
        executor = DockerExecutor()
        result = execute_t1_molecule_encoding(molecules, executor)

        # Create EvidenceItem
        evidence = EvidenceItem(
            id=self._generate_evidence_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            spec_id=self.spec.id,
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(
                code_ref=result["provenance"].get("commit_hash"),
                data_ref=None,  # No dataset for milestone 1
                seed=None,  # Deterministic encoding
                environment=self._capture_environment(result["provenance"]),
                cost=None,  # Milestone 1: no cost tracking
            ),
            result=self._create_encoding_result(result),
            bears_on=self._create_bearings(result),
        )

        # Save to file
        self._save_evidence(evidence)

        return evidence

    def _generate_evidence_id(self) -> str:
        """Generate unique Evidence ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"evi-{timestamp}"

    def _capture_environment(self, provenance: Dict[str, Any]) -> str:
        """Capture environment description."""
        parts = [
            f"docker:{provenance.get('image_name', 'unknown')}",
            f"image_id:{provenance.get('image_id', 'unknown')}",
        ]
        return ", ".join(parts)

    def _create_encoding_result(self, execution_result: Dict[str, Any]) -> Result:
        """Create Result from T-1 encoding execution."""
        encodings = execution_result.get("encodings", {})

        # Count successful encodings
        successful = sum(1 for v in encodings.values() if v.get("status") == "success")
        total = len(encodings)

        # Create quantitative result
        return Result(
            type="quantitative",
            point=float(successful),
            effect_size=float(successful),  # Encoded molecules count
            ci=None,  # Milestone 1: no CI calculation
            p_value=None,
            posterior=None,
            residual=None,
            predictive_error=None,
            finding=json.dumps(encodings, ensure_ascii=False),
            artifact_ref=None,  # Milestone 1: no separate artifact
        )

    def _create_bearings(self, execution_result: Dict[str, Any]) -> List[Bearing]:
        """Create Bearings for T-1 experiment."""
        bearings = []

        # Reference first hypothesis
        if self.spec.hypotheses:
            target_id = self.spec.hypotheses[0].id

            # Determine direction based on success
            encodings = execution_result.get("encodings", {})
            successful = sum(1 for v in encodings.values() if v.get("status") == "success")

            if successful > 0:
                direction = BearingDirection.SUPPORTS
                weight = float(successful) / len(encodings) if encodings else 0.0
            else:
                direction = BearingDirection.REFUTES
                weight = 0.0

            bearings.append(
                Bearing(
                    target_id=target_id,
                    direction=direction,
                    weight=weight,
                )
            )

        return bearings

    def _save_evidence(self, evidence: EvidenceItem) -> None:
        """Save EvidenceItem to JSON file."""
        filename = f"{evidence.id}.json"
        filepath = self.evidence_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(evidence.model_dump(mode="json"), f, indent=2, ensure_ascii=False)


def run_t1_experiments(
    spec: Spec,
    molecules: List[str],
    workspace_dir: Optional[Path] = None,
) -> List[EvidenceItem]:
    """
    Convenience function to run T-1 experiments.

    Args:
        spec: Spec instance
        molecules: List of molecular formulas
        workspace_dir: Output directory

    Returns:
        List of EvidenceItems
    """
    runner = ExperimentRunner(spec, workspace_dir)
    evidence = runner.run_t1_molecular_encoding(molecules)
    return [evidence]
