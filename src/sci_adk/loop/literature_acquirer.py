"""
Literature acquisition stage for the sci-adk research loop.

Bridges the paperforge adapter (``search/``) into the loop: given a list of
DOIs, it acquires the Open-Access PDFs into ``runs/<spec.id>/literature/`` and
records the acquisition as a ``LITERATURE`` EvidenceItem in the append-only
evidence log -- so a prior-work survey becomes part of the scientific record,
not an untracked side download.

Discovery vs acquisition (design/literature-acquisition.md):
    *Discovery* (topic -> key papers -> DOI list) is performed by Claude's
    native ``web_search`` at orchestration time -- an allowed tool
    (design/tool-policy.md), used on-demand the way a researcher checks prior
    work, not a code module. This stage is the *acquisition* half: DOIs in,
    PDFs + Evidence out. DOIs are passed in explicitly, exactly as
    ``ExperimentRunner`` takes its molecules explicitly (experiment_runner.py).

Halt gates (design/literature-acquisition.md):
    Acquisition can halt the loop and hand control back to the human (a
    structured ``AcquisitionHalt``, surfaced by the orchestrator -- code never
    prompts the user directly):
      1. **Unacquired papers** -- any DOI with no downloadable OA PDF halts the
         loop with the list of misses (detected here, automatically).
      2. **Supporting Information needed** -- after Claude reads a main text and
         judges that the paper's SI is required, it raises an
         ``AcquisitionHalt.for_supporting_info(...)`` (agent-judged, constructed
         by the orchestrator -- this module only provides the type).

Reference: design/directory-structure.md (loop/), design/abstractions.md (Evidence).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.spec import Spec
from sci_adk.search.paperforge_adapter import (
    AcquisitionRecord,
    AcquisitionResult,
    PaperforgeAdapter,
)


class HaltReason(str, Enum):
    """Why the literature loop is asking the human to step in."""

    UNACQUIRED_PAPERS = "unacquired_papers"        # condition 1 (mechanical)
    SUPPORTING_INFO_NEEDED = "supporting_info_needed"  # condition 2 (agent-judged)


@dataclass(frozen=True)
class HaltItem:
    """One paper the human is being asked about."""

    doi: str
    detail: str = ""   # the failure error (cond 1), or what SI is needed (cond 2)
    title: str = ""


@dataclass(frozen=True)
class AcquisitionHalt:
    """
    A structured request to stop the loop and feed back to the human.

    The orchestrator (Claude) -- not this module -- surfaces this via
    AskUserQuestion and halts; sci-adk code never prompts the user directly
    (agent-common-protocol: subagents/runtime do not prompt). This is the
    "structured halt result" the loop returns instead of pushing on.
    """

    reason: HaltReason
    items: list[HaltItem]
    message: str

    @classmethod
    def for_unacquired(cls, failed: Sequence[AcquisitionRecord]) -> "AcquisitionHalt":
        """Build the condition-1 halt from paperforge's failed records."""
        items = [HaltItem(doi=r.doi, detail=r.error) for r in failed]
        return cls(
            reason=HaltReason.UNACQUIRED_PAPERS,
            items=items,
            message=(
                f"{len(items)} paper(s) could not be acquired "
                f"(no downloadable Open-Access PDF). Human input needed before "
                f"the loop continues."
            ),
        )

    @classmethod
    def for_supporting_info(
        cls,
        items: Sequence[HaltItem],
        note: str = "",
    ) -> "AcquisitionHalt":
        """
        Build the condition-2 halt. Constructed by the orchestrator when Claude,
        having read a main text, judges the Supporting Information is required.
        """
        items = list(items)
        base = (f"Supporting Information (SI) is needed for {len(items)} "
                f"paper(s) after reading the main text.")
        return cls(
            reason=HaltReason.SUPPORTING_INFO_NEEDED,
            items=items,
            message=f"{base} {note}".strip(),
        )

    def feedback(self) -> str:
        """A human-readable feedback block (the orchestrator presents this)."""
        lines = [self.message]
        for it in self.items:
            label = it.doi or it.title or "?"
            suffix = f" -- {it.detail}" if it.detail else ""
            lines.append(f"  - {label}{suffix}")
        return "\n".join(lines)


@dataclass
class AcquisitionOutcome:
    """
    What :meth:`LiteratureAcquirer.acquire` returns.

    Bundles the persisted record (``evidence``), the raw per-DOI result
    (``result``), and -- when the loop should stop -- a structured ``halt``.
    """

    evidence: EvidenceItem
    result: AcquisitionResult
    halt: Optional[AcquisitionHalt] = None

    @property
    def should_halt(self) -> bool:
        return self.halt is not None


class LiteratureAcquirer:
    """
    Acquire Open-Access PDFs for a set of DOIs and record the run as Evidence.

    Mirrors ``ExperimentRunner``: constructed with a ``Spec`` and a workspace,
    writes under ``runs/<spec.id>/``, and emits an ``EvidenceItem``. The DOIs to
    acquire are supplied to :meth:`acquire` (discovery is Claude's web_search,
    upstream of this stage). The acquisition itself holds no judgment: a
    ``LITERATURE`` item records *what was acquired*, not whether a paper supports
    or refutes a hypothesis -- so ``bears_on`` is empty unless the caller asserts
    a contextual link.

    If any DOI fails to resolve to an OA PDF, :meth:`acquire` returns an
    ``AcquisitionOutcome`` whose ``halt`` lists the misses (condition 1); the
    orchestrator surfaces it and stops the loop.
    """

    def __init__(
        self,
        spec: Spec,
        workspace_dir: Optional[Path] = None,
        adapter: Optional[PaperforgeAdapter] = None,
        email: Optional[str] = None,
    ) -> None:
        """
        Args:
            spec: the governing Spec (its ``id`` selects the run directory).
            workspace_dir: repo/working root holding ``runs/`` (default: cwd).
            adapter: a PaperforgeAdapter (injectable for tests); built with
                ``email`` when not provided.
            email: contact email for the Unpaywall/OpenAlex polite pool, passed
                to a default adapter.
        """
        self.spec = spec
        self.workspace_dir = workspace_dir or Path.cwd()
        self.adapter = adapter or PaperforgeAdapter(email=email)
        self.run_dir = self.workspace_dir / "runs" / spec.id
        self.literature_dir = self.run_dir / "literature"
        self.evidence_dir = self.run_dir / "evidence"

    def acquire(
        self,
        dois: Sequence[str],
        *,
        target_id: Optional[str] = None,
        **options: Any,
    ) -> AcquisitionOutcome:
        # @MX:NOTE: [AUTO] loop stage entry: turns a DOI list (from web_search
        #   discovery) into acquired PDFs + a LITERATURE EvidenceItem under
        #   runs/<spec.id>/. Discovery is upstream (Claude web_search); this is
        #   acquisition + record only -- no belief judgment here. A non-empty
        #   failure set returns a halt (condition 1) for the orchestrator.
        """
        Acquire OA PDFs for ``dois``, record a ``LITERATURE`` EvidenceItem, and
        report whether the loop should halt.

        Every DOI is still attempted and recorded (E2: a missing OA PDF is a
        valid, recorded outcome, not an exception). The *whole batch* runs; then
        if any DOI failed, the returned ``AcquisitionOutcome.halt`` carries the
        list of misses so the orchestrator can feed it back and stop.

        Args:
            dois: DOIs to acquire (found upstream by web_search).
            target_id: optional Hypothesis/Claim id this survey relates to; when
                given, a single NEUTRAL bearing links the acquisition to it as
                context (acquisition asserts no direction on its own).
            **options: passthrough to ``PaperforgeAdapter.fetch`` (source_order,
                licenses, require_known_license, no_metadata, overwrite, verbose).

        Returns:
            An ``AcquisitionOutcome`` (evidence + result + optional halt).
        """
        self.literature_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        result = self.adapter.fetch(dois, self.literature_dir, **options)
        evidence = self._build_evidence(result, target_id)
        self._save_evidence(evidence)

        halt = (
            AcquisitionHalt.for_unacquired(result.failed)
            if result.failed
            else None
        )
        return AcquisitionOutcome(evidence=evidence, result=result, halt=halt)

    # -- evidence assembly -------------------------------------------------

    def _build_evidence(
        self,
        result: AcquisitionResult,
        target_id: Optional[str],
    ) -> EvidenceItem:
        """Assemble a LITERATURE EvidenceItem from a paperforge result."""
        summary = {
            "acquired": [
                {"doi": r.doi, "source": r.source,
                 "license": r.license, "filename": r.filename}
                for r in result.succeeded
            ],
            "failed": [
                {"doi": r.doi, "error": r.error} for r in result.failed
            ],
            "counts": {
                "succeeded": len(result.succeeded),
                "failed": len(result.failed),
            },
        }

        bears_on: list[Bearing] = []
        if target_id is not None:
            # Acquired-but-unjudged literature relates to the hypothesis as
            # context; NEUTRAL is the honest direction (E2) until a later step
            # reads the paper and asserts support/refute.
            bears_on = [Bearing(target_id=target_id,
                                direction=BearingDirection.NEUTRAL)]

        sha = str(result.provenance.get("pinned_sha", ""))[:7]
        version = result.provenance.get("installed_version")

        return EvidenceItem(
            id=self._generate_evidence_id(),
            spec_id=self.spec.id,
            kind=EvidenceKind.LITERATURE,
            provenance=Provenance(
                data_ref=str(result.manifest_path),
                environment=f"paperforge@{sha} version={version} "
                            f"returncode={result.returncode}",
            ),
            result=Result(
                type="qualitative",
                finding=json.dumps(summary, ensure_ascii=False),
                artifact_ref=str(self.literature_dir),
            ),
            bears_on=bears_on,
        )

    @staticmethod
    def _generate_evidence_id() -> str:
        # Timestamp for human-readable ordering + a short uuid suffix so IDs are
        # unique even when several are created within the same second.
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"evi-lit-{timestamp}-{uuid.uuid4().hex[:8]}"

    def _save_evidence(self, evidence: EvidenceItem) -> None:
        """Persist the EvidenceItem as JSON in the run's evidence log."""
        filepath = self.evidence_dir / f"{evidence.id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(evidence.model_dump(mode="json"), f,
                      indent=2, ensure_ascii=False)


def acquire_literature(
    spec: Spec,
    dois: Sequence[str],
    workspace_dir: Optional[Path] = None,
    *,
    adapter: Optional[PaperforgeAdapter] = None,
    email: Optional[str] = None,
    target_id: Optional[str] = None,
    **options: Any,
) -> AcquisitionOutcome:
    """
    Convenience wrapper: acquire ``dois`` for ``spec`` and return the outcome.

    Mirrors ``run_t1_experiments`` -- a one-call entry for the common case.
    Inspect ``outcome.should_halt`` / ``outcome.halt`` to decide whether to feed
    back to the human and stop the loop.
    """
    acquirer = LiteratureAcquirer(
        spec, workspace_dir, adapter=adapter, email=email)
    return acquirer.acquire(dois, target_id=target_id, **options)
