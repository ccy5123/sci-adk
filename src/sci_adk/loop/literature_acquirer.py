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

Reference: design/directory-structure.md (loop/), design/abstractions.md (Evidence).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
from sci_adk.search.paperforge_adapter import AcquisitionResult, PaperforgeAdapter


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
    ) -> EvidenceItem:
        # @MX:NOTE: [AUTO] loop stage entry: turns a DOI list (from web_search
        #   discovery) into acquired PDFs + a LITERATURE EvidenceItem under
        #   runs/<spec.id>/. Discovery is upstream (Claude web_search); this is
        #   acquisition + record only -- no belief judgment here.
        """
        Acquire OA PDFs for ``dois`` and record a ``LITERATURE`` EvidenceItem.

        A non-zero paperforge exit (some DOIs had no OA PDF) is a valid outcome,
        recorded in the Evidence finding (E2: null results are results) -- it is
        not an error.

        Args:
            dois: DOIs to acquire (found upstream by web_search).
            target_id: optional Hypothesis/Claim id this survey relates to; when
                given, a single NEUTRAL bearing links the acquisition to it as
                context (acquisition asserts no direction on its own).
            **options: passthrough to ``PaperforgeAdapter.fetch`` (source_order,
                licenses, require_known_license, no_metadata, overwrite, verbose).

        Returns:
            The saved ``LITERATURE`` EvidenceItem.
        """
        self.literature_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        result = self.adapter.fetch(dois, self.literature_dir, **options)
        evidence = self._build_evidence(result, target_id)
        self._save_evidence(evidence)
        return evidence

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
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"evi-lit-{timestamp}"

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
) -> EvidenceItem:
    """
    Convenience wrapper: acquire ``dois`` for ``spec`` and return the Evidence.

    Mirrors ``run_t1_experiments`` -- a one-call entry for the common case.
    """
    acquirer = LiteratureAcquirer(
        spec, workspace_dir, adapter=adapter, email=email)
    return acquirer.acquire(dois, target_id=target_id, **options)
