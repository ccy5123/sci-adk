"""
Lean 4 formal-proof capability (adapter-side, design/literature-acquisition.md's sibling
formal-verification seam; kernel dual = EvidenceKind.FORMAL_PROOF).

A capability that machine-checks a proof with an EXTERNAL checker (Lean 4 + Mathlib) and
emits the kernel's decisive evidence:

  * checker PASS (exit 0) -> a ``FORMAL_PROOF`` EvidenceItem bearing SUPPORTS on the
    hypothesis. The DecisionEngine's ``_eval_proof`` treats this as DECISIVE supports (the
    dual of a decisive counterexample) -- no LLM-judge, no §0 human spot-check, and
    ``verify`` re-derives it from the record (re-run the checker) with no LLM.
  * checker FAIL (exit != 0) -> a ``PROOF_STEP`` EvidenceItem bearing NEUTRAL (finding = the
    checker error). A failed compile is NOT a counterexample -- the theorem is not thereby
    false; the proof attempt merely did not verify -> the claim stays inconclusive/PROPOSED.

Seam direction (F4): this lives in ``sci_adk.adapter`` and imports the kernel's
``ExperimentFn`` / evidence TYPES only (adapter -> kernel is allowed). The kernel never
imports this; it only receives the resolved ``[EvidenceItem]``.

Environment: the real check runs Lean in a container (``environments/lean-base/`` recipe,
image ``sci-adk-lean``) via :meth:`DockerExecutor.execute_command`. The executor is
INJECTABLE (``executor=``) so this is unit-testable with a fake checker (no Docker, no Lean)
-- exactly as T-1 is tested with a fake experiment. Building/running the real Lean+Mathlib
image is the user's step (as with the chem image); end-to-end is not exercised in CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.loop.compiler import ExperimentFn
from sci_adk.runner.docker_executor import DockerExecutor

LEAN_CAPABILITY_ID = "lean-formal-proof"
DEFAULT_LEAN_IMAGE = "sci-adk-lean"


class _CommandRunner(Protocol):
    """The one method this capability needs from an executor (DockerExecutor satisfies it)."""

    def execute_command(
        self, command: List[str], capture_output: bool = True
    ) -> Dict[str, Any]:
        ...


@dataclass(frozen=True)
class LeanProofTask:
    """One theorem to machine-check: the target hypothesis + its Lean source.

    Attributes:
        hypothesis_id: the ``Hypothesis.id`` this proof bears on (a PROOF-rule hypothesis).
        lean_source: the complete Lean 4 file (imports + theorem + proof) to check.
        filename: co-located name written into the run/workspace; also the FORMAL_PROOF's
            ``code_ref`` (so the check is reproducible -- re-run the checker on this file).
    """

    hypothesis_id: str
    lean_source: str
    filename: str = "proof.lean"


def lean_experiment(
    tasks: Sequence[LeanProofTask],
    *,
    executor: Optional[_CommandRunner] = None,
    image: str = DEFAULT_LEAN_IMAGE,
) -> ExperimentFn:
    """Build an ``ExperimentFn`` that machine-checks each task's Lean proof.

    Args:
        tasks: the theorems to check (each -> one Evidence item).
        executor: a command runner (defaults to ``DockerExecutor(image)``). INJECT a fake in
            tests: any object with ``execute_command(cmd) -> {"returncode": int, "stderr":
            str, "provenance": dict}``.
        image: the Lean checker image (default ``sci-adk-lean``); ignored when ``executor``
            is injected.

    Returns:
        ``fn(spec, workspace_dir) -> [EvidenceItem]`` -- one FORMAL_PROOF (pass) or
        PROOF_STEP (fail) per task.
    """

    def experiment(spec: Any, workspace_dir: Any) -> List[EvidenceItem]:
        ws = Path(workspace_dir)
        ex = executor or DockerExecutor(image_name=image, workspace_dir=ws)
        items: List[EvidenceItem] = []
        for i, task in enumerate(tasks):
            # Co-locate the proof source so its code_ref resolves + the check is reproducible.
            (ws / task.filename).write_text(task.lean_source, encoding="utf-8")
            res = ex.execute_command(["lean", task.filename])
            rc = int(res.get("returncode", 1))
            out = ((res.get("stdout") or "") + "\n" + (res.get("stderr") or "")).strip()
            prov = res.get("provenance") or {}
            image_id = prov.get("image_id") or prov.get("image_name") or image

            # IMPORTANT: `lean <file>` exits 0 EVEN ON ERRORS (it prints an `error:`
            # diagnostic but does not fail the process), and a `sorry` hole compiles with
            # only a warning. So the exit code alone is NOT trustworthy -- a proof is
            # genuinely machine-verified iff the checker exited cleanly AND emitted no error
            # diagnostic AND no `sorry`. (Empirically a clean proof prints nothing.)
            verified = rc == 0 and "error:" not in out and "sorry" not in out

            if verified:
                items.append(
                    EvidenceItem(
                        id=f"ev-lean-{i}",
                        spec_id=spec.id,
                        kind=EvidenceKind.FORMAL_PROOF,
                        provenance=Provenance(
                            code_ref=task.filename,
                            data_source="generated",
                            environment=f"lean4 checker (image={image_id}); verified, no diagnostics",
                        ),
                        result=Result(
                            type="qualitative",
                            finding=f"lean4 verified {task.filename} (exit 0, no error/sorry diagnostics)",
                        ),
                        bears_on=[Bearing(target_id=task.hypothesis_id,
                                          direction=BearingDirection.SUPPORTS)],
                    )
                )
            else:
                if rc != 0:
                    reason = f"checker exit {rc}"
                elif "error:" in out:
                    reason = "error diagnostics (checker exits 0 on errors)"
                elif "sorry" in out:
                    reason = "the proof uses `sorry` (an admitted hole, not a proof)"
                else:
                    reason = "not verified"
                items.append(
                    EvidenceItem(
                        id=f"ev-lean-{i}",
                        spec_id=spec.id,
                        kind=EvidenceKind.PROOF_STEP,
                        provenance=Provenance(
                            code_ref=task.filename,
                            data_source="generated",
                            environment=f"lean4 checker (image={image_id}); {reason}",
                        ),
                        result=Result(
                            type="qualitative",
                            finding=(f"lean4 did NOT verify {task.filename} ({reason}); a "
                                     f"failed check is not a counterexample -- the proof "
                                     f"attempt did not verify. output: {out[:500]}"),
                        ),
                        # NEUTRAL: an un-verified attempt neither supports nor refutes -> the
                        # claim stays inconclusive/PROPOSED (only a COUNTEREXAMPLE refutes).
                        bears_on=[Bearing(target_id=task.hypothesis_id,
                                          direction=BearingDirection.NEUTRAL)],
                    )
                )
        return items

    return experiment


__all__ = ["LEAN_CAPABILITY_ID", "DEFAULT_LEAN_IMAGE", "LeanProofTask", "lean_experiment"]
