"""
The turnkey checkpoint loop -- a thin, no-LLM kernel-side orchestrator.

design/rigor-shell-architecture.md §5: ``run_checkpoint_loop`` drives
``ResearchCompiler`` across the agent boundary. It does NOT replace the compiler --
it sequences:

  1. compile (numeric kinds resolve autonomously and free);
  2. surface typed ``checkpoints/<hyp-id>.json`` + the ``checkpoints.md`` view
     (the compiler writes these);
  3. when ``verdicts/<hyp-id>.json`` exist, re-enter with ``RecordedJudge(run_dir)``
     injected so the engine applies the frozen rule to the recorded chief verdict;
  4. FIXPOINT -- recompile until the unresolved set stops changing. A confident
     PROOF does NOT auto-support: the engine keeps it inconclusive (a pending human
     spot-check), so it remains an open checkpoint, handled here as a stable
     fixpoint rather than a single pass;
  5. idempotency (F5) -- the experiment is NOT re-run when Evidence for this Spec
     version already exists on disk; the recorded Evidence is reused (so a re-run
     reproduces the same Claim and appends no spurious StatusChange).

No LLM is invoked anywhere in this module (the verdicts were authored by the
in-session agent, off to the side, and merely read back by ``RecordedJudge``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Spec
from sci_adk.loop.compiler import Checkpoint, ExperimentFn, ResearchCompiler
from sci_adk.loop.recorded_judge import RecordedJudge

# A Claim in one of these states has been moved by a binding verdict -> resolved.
# PROPOSED means neutral/inconclusive (incl. a proof pending its human spot-check),
# so it is still an OPEN checkpoint.
_RESOLVED_STATES = {
    ClaimStatus.SUPPORTED,
    ClaimStatus.REFUTED,
    ClaimStatus.CONTESTED,
}

# Fixpoint guard: the compile is deterministic, so the unresolved set converges in a
# couple of passes; this bound prevents any pathological non-convergence loop.
_MAX_ITERATIONS = 10


@dataclass
class LoopResult:
    """The outcome of a checkpoint-loop run."""

    spec: Spec
    claims: List[Claim]
    checkpoints: List[Checkpoint]
    unresolved: List[str]            # hypothesis ids still awaiting a binding verdict
    run_dir: Path
    iterations: int = field(default=0)


def run_checkpoint_loop(
    *,
    run_dir: Path,
    spec: Spec,
    experiment: Optional[ExperimentFn] = None,
    workspace_dir: Optional[Path] = None,
    proposal_text: str = "",
    force: bool = False,
) -> LoopResult:
    """Drive the compile -> surface -> re-enter -> fixpoint loop over a run dir.

    Args:
        run_dir: the run directory (``<workspace>/runs/<spec.id>``). Used to locate
            ``verdicts/`` and existing ``evidence/`` for re-entry and idempotency.
        spec: the frozen Spec to compile (supplied directly; the loop is
            capability-agnostic -- the adapter builds the Spec + experiment).
        experiment: the ``ExperimentFn`` producing Evidence. Skipped when Evidence
            for this Spec version already exists on disk (F5 reuse) unless ``force``.
        workspace_dir: the workspace root holding ``runs/`` (default: ``run_dir``'s
            grandparent, i.e. ``run_dir/../..``).
        proposal_text: unused when ``spec`` is supplied (kept for symmetry with the
            compiler signature).
        force: re-run the experiment even if Evidence already exists (F5: appends a
            new EvidenceItem, never overwrites -- the compiler/adapter own that).

    Returns:
        A :class:`LoopResult` -- inspect ``unresolved`` for the open checkpoints.
    """
    # @MX:ANCHOR: [AUTO] the single turnkey entry that drives compile -> surface ->
    #   re-enter -> fixpoint across the agent boundary (no LLM here).
    # @MX:REASON: [AUTO] the CLI `resolve` verb and the loop/recorded-judge/T-1-proof
    #   test suites all call this; it owns the fixpoint termination AND the F5 reuse
    #   contract (do not re-run the experiment when Evidence exists). Breaking the
    #   reuse/fixpoint contract would re-execute experiments (violating E1 append-only
    #   honesty) or loop forever on an engine-raised spot-check checkpoint.
    run_dir = Path(run_dir)
    workspace = Path(workspace_dir) if workspace_dir else run_dir.parent.parent

    effective_experiment = _resolve_experiment(run_dir, experiment, force=force)

    last: Optional[LoopResult] = None
    prev_unresolved: Optional[List[str]] = None
    for iteration in range(1, _MAX_ITERATIONS + 1):
        judge = RecordedJudge(run_dir) if _has_verdicts(run_dir) else None
        result = ResearchCompiler(workspace_dir=workspace, judge=judge).compile(
            proposal_text, spec=spec, experiment=effective_experiment
        )
        # Persist produced Evidence so a re-run/re-entry can replay it (F5). Writing
        # is idempotent: a replay shim returns the same items, and the on-disk file
        # is keyed by the stable EvidenceItem.id.
        _persist_evidence(result.run_dir, result.evidence)
        unresolved = _unresolved(result.checkpoints, result.claims)
        last = LoopResult(
            spec=result.spec,
            claims=result.claims,
            checkpoints=result.checkpoints,
            unresolved=unresolved,
            run_dir=result.run_dir,
            iterations=iteration,
        )
        # Done in one pass when there is nothing for an agent (numeric-only path,
        # §5.2 step 1) or everything is already resolved.
        if not result.checkpoints or not unresolved:
            break
        # Fixpoint: the unresolved set stopped changing (the engine-raised spot-check
        # for a confident proof is a STABLE open checkpoint, not a growing one).
        if prev_unresolved is not None and unresolved == prev_unresolved:
            break
        prev_unresolved = unresolved
        # After the first pass, reuse the now-on-disk Evidence (never re-run).
        effective_experiment = _resolve_experiment(run_dir, experiment, force=False)

    # The loop runs at least once; guard explicitly so it holds under `python -O`
    # (where `assert` is stripped) rather than returning None.
    if last is None:
        raise RuntimeError(
            "checkpoint_loop ran 0 iterations -- _MAX_ITERATIONS must be >= 1"
        )
    return last


# -- helpers -----------------------------------------------------------------

def _unresolved(checkpoints: List[Checkpoint], claims: List[Claim]) -> List[str]:
    """Hypothesis ids whose Claim has NOT been moved by a binding verdict.

    A checkpoint is resolved iff a Claim exists for it in a resolved state
    (supported/refuted/contested). A missing Claim or a PROPOSED (neutral /
    inconclusive / pending-spot-check) Claim leaves it open.
    """
    status_by_hyp = {c.answers: c.status for c in claims}
    return [
        cp.hypothesis_id
        for cp in checkpoints
        if status_by_hyp.get(cp.hypothesis_id) not in _RESOLVED_STATES
    ]


def _has_verdicts(run_dir: Path) -> bool:
    vdir = run_dir / "verdicts"
    return vdir.is_dir() and any(vdir.glob("*.json"))


def _resolve_experiment(
    run_dir: Path,
    experiment: Optional[ExperimentFn],
    *,
    force: bool,
) -> Optional[ExperimentFn]:
    """Return the experiment to use this pass, honoring F5 reuse.

    If Evidence already exists on disk for this run and ``force`` is False, return a
    shim that REPLAYS the recorded Evidence instead of re-executing -- so the loop is
    idempotent and the append-only log is not duplicated. This replay path also
    serves ``sci-adk resolve`` over an existing run dir, where no ``experiment`` is
    supplied: the recorded Evidence is reused as-is. When no Evidence exists yet,
    return the supplied ``experiment`` (or ``None``).
    """
    if not force:
        existing = _load_existing_evidence(run_dir)
        if existing:
            def _replay(_spec: Spec, _workspace: Path) -> List[EvidenceItem]:
                return existing
            return _replay
    return experiment


def _load_existing_evidence(run_dir: Path) -> List[EvidenceItem]:
    """Load recorded Evidence from ``runs/<id>/evidence/*.json`` (F5 reuse)."""
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return []
    items: List[EvidenceItem] = []
    for path in sorted(evidence_dir.glob("*.json")):
        items.append(
            EvidenceItem.model_validate(json.loads(path.read_text(encoding="utf-8")))
        )
    return items


def _persist_evidence(run_dir: Path, evidence: List[EvidenceItem]) -> None:
    """Write Evidence to ``runs/<id>/evidence/<id>.json`` (the loop owns F5 reuse).

    Idempotent: each item is keyed by its stable id, so re-writing the same Evidence
    overwrites byte-identical content. This is how a capability whose experiment does
    not self-persist (e.g. a fixture) still gets a replayable record on disk.
    """
    if not evidence:
        return
    evidence_dir = Path(run_dir) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for item in evidence:
        (evidence_dir / f"{item.id}.json").write_text(
            json.dumps(item.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


__all__ = ["LoopResult", "run_checkpoint_loop"]
