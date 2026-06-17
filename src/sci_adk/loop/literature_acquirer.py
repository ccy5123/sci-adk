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
from sci_adk.search.citation_keys import (
    KeyingResult,
    assign_and_apply_citation_keys,
)
from sci_adk.search.paperforge_adapter import (
    AcquisitionRecord,
    AcquisitionResult,
    PaperforgeAdapter,
)
from sci_adk.search.pdf_normalize import (
    NormalizeResult,
    NormalizeStatus,
    normalize_pdf,
)

# How many EXTRA re-download attempts to spend on an acquired PDF that cannot be
# parsed (corrupt/truncated/HTML-saved-as-pdf) before giving up and marking it
# ``error``. Total attempts = 1 original + PDF_REDOWNLOAD_RETRIES. A user-password
# lock is NOT retried (a re-download yields the same lock) -- only parse errors.
PDF_REDOWNLOAD_RETRIES = 2


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

    ``normalizations`` holds the per-PDF normalization outcomes (one
    :class:`~sci_adk.search.pdf_normalize.NormalizeResult` per acquired PDF).
    ``locked_pdfs`` lists the filenames of any acquired PDFs that turned out to be
    real user-password locks -- surfaced (never silently treated as readable) so
    the orchestrator can ask the human for the password or another source.
    ``unreadable_pdfs`` lists the filenames of any acquired PDFs that could not be
    parsed even after re-download retries (corrupt/truncated/HTML-as-pdf) --
    surfaced the same way; the batch was not aborted for them.
    ``citation_keys`` maps each acquired DOI to its sci-adk citation key
    (``<Surname><Year>`` with ``a/b`` on collision); the PDF/sidecar/bib/manifest
    were renamed to match. ``key_collisions`` lists any overwrite collisions
    detected (distinct DOIs that resolved to one on-disk file) -- surfaced so a
    silently-overwritten paper is never lost.
    """

    evidence: EvidenceItem
    result: AcquisitionResult
    halt: Optional[AcquisitionHalt] = None
    normalizations: list[NormalizeResult] = field(default_factory=list)
    locked_pdfs: list[str] = field(default_factory=list)
    unreadable_pdfs: list[str] = field(default_factory=list)
    citation_keys: dict[str, str] = field(default_factory=dict)
    key_collisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def should_halt(self) -> bool:
        return self.halt is not None

    @property
    def has_locked_pdfs(self) -> bool:
        """True when at least one acquired PDF is a user-password lock to surface."""
        return bool(self.locked_pdfs)

    @property
    def has_unreadable_pdfs(self) -> bool:
        """True when at least one acquired PDF stayed unreadable after retries."""
        return bool(self.unreadable_pdfs)

    @property
    def has_key_collisions(self) -> bool:
        """True when an overwrite collision (two DOIs -> one file) was detected."""
        return bool(self.key_collisions)


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

        # Auto-normalize each acquired PDF: owner/permission-restricted-but-
        # openable PDFs are re-written extractable; a real user-password lock is
        # left untouched and surfaced (never bypassed); a corrupt/unparseable PDF
        # is re-downloaded up to PDF_REDOWNLOAD_RETRIES times and, if still
        # unreadable, surfaced (the batch is not aborted). IO only -- no belief.
        normalizations, retries_spent = self._normalize_acquired(result, options)
        locked_pdfs = [
            n.path.name
            for n in normalizations
            if n.status == NormalizeStatus.LOCKED
        ]
        unreadable_pdfs = [
            n.path.name
            for n in normalizations
            if n.status == NormalizeStatus.ERROR
        ]

        # Apply sci-adk's own citation-key convention to the acquired files
        # (after fetch + normalize, before the record is built): rename each
        # PDF/sidecar to <Surname><Year> (a/b-by-DOI on collision) and update
        # references.bib + manifest.csv to match. Naming/IO only -- no belief.
        # An overwrite collision (two DOIs -> one on-disk file) is detected and
        # surfaced, never silently dropped.
        keying = assign_and_apply_citation_keys(self.literature_dir, result.records)

        evidence = self._build_evidence(
            result, target_id, normalizations, retries_spent, keying
        )
        self._save_evidence(evidence)

        halt = (
            AcquisitionHalt.for_unacquired(result.failed)
            if result.failed
            else None
        )
        return AcquisitionOutcome(
            evidence=evidence,
            result=result,
            halt=halt,
            normalizations=normalizations,
            locked_pdfs=locked_pdfs,
            unreadable_pdfs=unreadable_pdfs,
            citation_keys=dict(keying.mapping),
            key_collisions=[c.model_dump(mode="json") for c in keying.collisions],
        )

    # -- normalization -----------------------------------------------------

    def _normalize_acquired(
        self,
        result: AcquisitionResult,
        options: dict[str, Any],
    ) -> tuple[list[NormalizeResult], dict[str, int]]:
        """Normalize each successfully-acquired PDF on disk, retrying corrupt ones.

        paperforge writes acquired PDFs into ``<literature_dir>/pdfs/<filename>``.
        Only successful records have a file; failed DOIs are skipped (a missing
        OA PDF is recorded by the existing halt, not normalized). A file that is
        named in the manifest but missing on disk is skipped defensively.

        When ``normalize_pdf`` returns ``error`` (the file could not be parsed --
        truncated download, HTML error page saved as .pdf, corrupt bytes), the
        single owning DOI is re-downloaded (overwrite) up to
        ``PDF_REDOWNLOAD_RETRIES`` more times and re-normalized each time; the
        first readable result wins. A ``locked`` result is NOT retried (a
        re-download yields the same user-password lock).

        Returns the final per-PDF results and a ``retries_spent`` map
        (filename -> number of re-download retries actually used).
        """
        pdf_dir = self.literature_dir / "pdfs"
        normalizations: list[NormalizeResult] = []
        retries_spent: dict[str, int] = {}
        for record in result.succeeded:
            if not record.filename:
                continue
            pdf_path = pdf_dir / record.filename
            if not pdf_path.exists():
                continue

            outcome = normalize_pdf(pdf_path)
            used = 0
            # Only a parse error is retryable; locked/normalized/already are final.
            while (
                outcome.status == NormalizeStatus.ERROR
                and used < PDF_REDOWNLOAD_RETRIES
            ):
                used += 1
                self._redownload(record.doi, options)
                outcome = normalize_pdf(pdf_path)

            normalizations.append(outcome)
            if used:
                retries_spent[record.filename] = used
        return normalizations, retries_spent

    def _redownload(self, doi: str, options: dict[str, Any]) -> None:
        """Re-fetch a single DOI into the literature dir, overwriting the file.

        Used to retry a corrupt acquired PDF. ``overwrite=True`` is forced so the
        fresh download replaces the unparseable file in place; other options carry
        through unchanged.
        """
        retry_options = {**options, "overwrite": True}
        self.adapter.fetch([doi], self.literature_dir, **retry_options)

    # -- evidence assembly -------------------------------------------------

    def _build_evidence(
        self,
        result: AcquisitionResult,
        target_id: Optional[str],
        normalizations: Optional[Sequence[NormalizeResult]] = None,
        retries_spent: Optional[dict[str, int]] = None,
        keying: Optional[KeyingResult] = None,
    ) -> EvidenceItem:
        """Assemble a LITERATURE EvidenceItem from a paperforge result.

        The ``normalization`` block honestly records the PDF transformation
        (sci-adk records what happened): which acquired PDFs were ``normalized``
        (owner-restriction stripped), ``already_extractable`` (no-op), ``locked``
        (a user-password lock left untouched), or ``error`` (unreadable even after
        re-download retries), whether an original was preserved, and how many
        re-download retries were spent on each.

        The ``citation_keys`` block records the DOI -> citation-key mapping sci-adk
        applied to the acquired files (the renaming is an honest part of the
        record), and ``citation_key_collisions`` records any overwrite collision
        (distinct DOIs that resolved to one on-disk file) so a silently-overwritten
        paper is never lost from the log.
        """
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
            "normalization": self._normalization_summary(
                normalizations or [], retries_spent or {}
            ),
            "citation_keys": dict(keying.mapping) if keying else {},
            "citation_key_collisions": (
                [c.model_dump(mode="json") for c in keying.collisions]
                if keying else []
            ),
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
    def _normalization_summary(
        normalizations: Sequence[NormalizeResult],
        retries_spent: dict[str, int],
    ) -> dict[str, Any]:
        """Build the JSON-able ``normalization`` block for the evidence finding."""
        pdfs = [
            {
                "filename": n.path.name,
                "status": n.status.value,
                "original_preserved": n.original_path is not None,
                "retries_spent": retries_spent.get(n.path.name, 0),
                "note": n.note,
            }
            for n in normalizations
        ]
        counts = {
            "normalized": 0,
            "already_extractable": 0,
            "locked": 0,
            "error": 0,
        }
        for n in normalizations:
            counts[n.status.value] += 1
        return {"pdfs": pdfs, "counts": counts}

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

    A one-call entry for the common case.
    Inspect ``outcome.should_halt`` / ``outcome.halt`` to decide whether to feed
    back to the human and stop the loop.
    """
    acquirer = LiteratureAcquirer(
        spec, workspace_dir, adapter=adapter, email=email)
    return acquirer.acquire(dois, target_id=target_id, **options)
