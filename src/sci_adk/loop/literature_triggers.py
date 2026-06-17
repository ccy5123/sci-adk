"""
The novelty (High) and contested (Medium) discovery triggers
(design/literature-acquisition.md §"Discovery trigger model").

These are the two *incremental* triggers added beside the implemented Spec-creation
prior-art anchor (``loop/prior_work.py``). Both are HYPOTHESIS-bound (unlike the
Spec-bound prior-art check) and both record their decision into the single append-only
Evidence log via the SHARED writer ``loop/decision_record.write_decision_evidence`` --
no write/id/save logic is duplicated.

  - **Novelty (High)** underwrites the *validity* of a "first/new" claim. Its decision
    is recorded as a ``NOVELTY_DECISION`` item:
      * :func:`record_novelty_searched` drives the EXISTING ``LiteratureAcquirer``
        (a ``LITERATURE`` artifact) and records the searched decision referencing it;
      * :func:`record_novelty_skip` records a skipped decision (a recorded null + reason).
    A SUPPORTED novelty claim is gated by ``check_novelty_adequacy`` (claim_updater):
    only a *searched* decision un-blocks it -- a skip does not.

  - **Contested (Medium)** is RECORDING, not searching: after a claim becomes CONTESTED,
    :func:`record_contested` writes a ``CONTESTED_RECORD`` (a timestamp via the
    append-only ``created_at``) so literature that arrived after the conflict stays
    visible (anti post-hoc-rationalization). It NEVER gates/halts.
    :func:`contested_open` reports whether a contested hypothesis still lacks its record;
    :func:`contested_checkpoint` builds the surfacing checkpoint.

F7 seam: a finding here that implies a *frozen* Spec element must change goes through the
human-only amendment path (F7) -- never a silent mutation. These functions record
evidence and do not touch the Spec, so that seam holds by construction.

No LLM anywhere: discovery (topic -> DOIs) is the in-session agent's ``web_search``
upstream; this module only records the decision and (searched paths) acquires.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import (
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
    Provenance,
)
from sci_adk.core.spec import Spec
from sci_adk.loop.decision_record import write_decision_evidence
from sci_adk.loop.literature_acquirer import AcquisitionOutcome, LiteratureAcquirer
from sci_adk.loop.verdict import ContestedCheckpoint
from sci_adk.search.paperforge_adapter import PaperforgeAdapter

# Default reminders shown on each surfaced checkpoint.
_CONTESTED_PROMPT = (
    "Contested check: this claim has conflicting evidence (support and refutation "
    "coexist). Record the post-conflict literature decision so papers found AFTER the "
    "conflict stay visible (anti post-hoc-rationalization). Run `sci-adk contested "
    "<run-dir> --hypothesis <id> --note \"...\"` (or --searched <dois...> to also "
    "acquire). This is recording, not a gate -- nothing halts."
)


# -- novelty (High) --------------------------------------------------------- #

def record_novelty_searched(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    hypothesis_id: str,
    dois: Sequence[str],
    adapter: Optional[PaperforgeAdapter] = None,
    email: Optional[str] = None,
    target_id: Optional[str] = None,
    allow_no_email: bool = False,
    config_root: Optional[Path] = None,
    **options: Any,
) -> AcquisitionOutcome:
    """Record the novelty *searched* decision: acquire via the EXISTING acquirer, then
    write a ``NOVELTY_DECISION`` referencing the acquired ``LITERATURE`` item.

    Discovery (topic -> DOIs) is the agent's ``web_search`` upstream; given the DOI list
    this delegates to :class:`LiteratureAcquirer` (the ``LITERATURE`` item is the
    acquired artifact, reused not reinvented), then records the decision that satisfies
    the novelty gate (``check_novelty_adequacy``).

    Contact-email policy mirrors ``record_prior_work_searched`` exactly
    (design/evidence-validity.md E4): by DEFAULT a contact email is REQUIRED and resolved
    here (arg -> config -> ``$UNPAYWALL_EMAIL``); a missing email raises ``ConfigHalt``
    BEFORE any acquisition. ``allow_no_email=True`` proceeds degraded.

    Raises:
        ConfigHalt: when ``allow_no_email`` is False and no contact email resolves.
    """
    from sci_adk.config import require_contact_email

    email = require_contact_email(
        email, allow_no_email=allow_no_email, config_root=config_root
    )
    outcome = LiteratureAcquirer(
        spec, workspace_dir, adapter=adapter, email=email
    ).acquire(dois, target_id=target_id, **options)

    lit = outcome.evidence
    write_decision_evidence(
        spec,
        workspace_dir,
        kind=EvidenceKind.NOVELTY_DECISION,
        finding=f"searched: DOIs={list(dois)}",
        provenance=Provenance(
            code_ref="novelty:searched",
            data_ref=f"literature_evidence={lit.id}; "
                     f"manifest={lit.result.artifact_ref or ''}",
            environment="novelty decision (High trigger); "
                        "see referenced LITERATURE item for the acquired corpus",
        ),
        id_prefix="evi-nov-decision",
        literature_decision=LiteratureDecision(
            outcome="searched",
            hypothesis_id=hypothesis_id,
            literature_evidence_id=lit.id,
        ),
    )
    return outcome


def record_novelty_skip(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    hypothesis_id: str,
    reason: str,
) -> EvidenceItem:
    """Record the novelty *skipped* decision as a ``NOVELTY_DECISION`` (a recorded null).

    A skipped novelty decision does NOT satisfy the novelty gate (skipping the prior-art
    search guts a 'first/new' claim's only evidentiary basis) -- but it is still recorded,
    with its reason, so the decision is never invisible (Invariant E2).

    Raises:
        ValueError: if ``reason`` is empty/blank.
    """
    reason = reason.strip()
    if not reason:
        raise ValueError(
            "record_novelty_skip requires a non-empty reason: a skipped novelty search "
            "is a recorded null, and the record must say why."
        )
    return write_decision_evidence(
        spec,
        workspace_dir,
        kind=EvidenceKind.NOVELTY_DECISION,
        finding=f"skipped: {reason}",
        provenance=Provenance(
            code_ref="novelty:skip",
            environment="novelty decision (High trigger); no search performed",
        ),
        id_prefix="evi-nov-decision",
        literature_decision=LiteratureDecision(
            outcome="skipped", hypothesis_id=hypothesis_id, reason=reason
        ),
    )


# -- contested (Medium) ----------------------------------------------------- #

def record_contested(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    hypothesis_id: str,
    reason_or_note: str = "",
    dois: Optional[Sequence[str]] = None,
    adapter: Optional[PaperforgeAdapter] = None,
    email: Optional[str] = None,
    allow_no_email: bool = False,
    config_root: Optional[Path] = None,
    **options: Any,
) -> EvidenceItem:
    """Record the post-conflict literature decision as a ``CONTESTED_RECORD``.

    The Medium trigger's rigor is *recording, not searching*: the append-only
    ``created_at`` is the anti-post-hoc timestamp, and this record makes the decision
    explicit. It NEVER gates/halts.

    When ``dois`` are given, the searched path is taken first (acquire via the existing
    acquirer, same contact-email policy as the novelty/prior-work searched paths), and
    the record references the acquired ``LITERATURE`` item. With no DOIs it is a pure
    note (a recorded decision with no acquisition).

    Args:
        hypothesis_id: the contested hypothesis this record is bound to.
        reason_or_note: a free-text note about the conflict / what was found.
        dois: optional DOIs to acquire and reference (the searched-contested path).

    Raises:
        ConfigHalt: only on the searched path when ``allow_no_email`` is False and no
            contact email resolves (a pure note never touches the email policy).
    """
    literature_evidence_id: Optional[str] = None
    data_ref: Optional[str] = None
    if dois:
        from sci_adk.config import require_contact_email

        email = require_contact_email(
            email, allow_no_email=allow_no_email, config_root=config_root
        )
        outcome = LiteratureAcquirer(
            spec, workspace_dir, adapter=adapter, email=email
        ).acquire(dois, target_id=None, **options)
        lit = outcome.evidence
        literature_evidence_id = lit.id
        data_ref = (f"literature_evidence={lit.id}; "
                    f"manifest={lit.result.artifact_ref or ''}")

    note = reason_or_note.strip()
    finding = f"recorded: {note}" if note else "recorded: post-conflict literature decision"
    return write_decision_evidence(
        spec,
        workspace_dir,
        kind=EvidenceKind.CONTESTED_RECORD,
        finding=finding,
        provenance=Provenance(
            code_ref="contested:record",
            data_ref=data_ref,
            environment="contested record (Medium trigger); recording, not searching",
        ),
        id_prefix="evi-con-record",
        literature_decision=LiteratureDecision(
            outcome="recorded",
            hypothesis_id=hypothesis_id,
            reason=note or None,
            literature_evidence_id=literature_evidence_id,
        ),
    )


def contested_checkpoint(
    spec: Spec, hypothesis_id: str, spec_version: int, prompt: str = _CONTESTED_PROMPT
) -> ContestedCheckpoint:
    """Build the recording-type contested checkpoint for ``hypothesis_id`` (Medium trigger).

    Recording-type: it carries no verdict trail. It is hypothesis-bound -- a reminder
    that the post-conflict literature *decision* has not yet been recorded.
    """
    return ContestedCheckpoint(
        hypothesis_id=hypothesis_id,
        spec_id=spec.id,
        spec_version=spec_version,
        prompt=prompt,
    )


def contested_open(
    spec: Spec, hypothesis_id: str, workspace_dir: Optional[Path] = None
) -> bool:
    """True iff the Claim for ``hypothesis_id`` is CONTESTED but no ``CONTESTED_RECORD``
    decision exists for it yet (read-only, no LLM, no capability).

    A contested checkpoint is "open" only while there IS a conflict to record AND it has
    not been recorded. A non-contested (or absent) Claim has nothing to surface; a
    contested Claim whose record already exists is closed. Reads the record only -- so it
    works during the record-only re-read too.
    """
    # @MX:ANCHOR: [AUTO] the open/closed predicate for the contested checkpoint: open iff
    #   the hypothesis's Claim is CONTESTED AND no hypothesis-bound CONTESTED_RECORD is
    #   on disk for it.
    # @MX:REASON: [AUTO] the compiler surfaces open contested checkpoints from this; it
    #   MUST stay record-only (no capability/LLM) so the headless verify re-read reaches
    #   the same verdict, and MUST close only on a hypothesis-bound CONTESTED_RECORD (never
    #   a bare LITERATURE acquisition). It is a recording reminder -- it never gates/halts.
    workspace = Path(workspace_dir) if workspace_dir else Path.cwd()
    run_dir = workspace / "runs" / spec.id

    if not _claim_is_contested(run_dir, hypothesis_id):
        return False
    return not _contested_record_exists(run_dir, hypothesis_id)


# -- helpers ---------------------------------------------------------------- #

def _claim_is_contested(run_dir: Path, hypothesis_id: str) -> bool:
    """True iff a recorded Claim for ``hypothesis_id`` is in CONTESTED status."""
    import json

    claims_dir = run_dir / "claims"
    if not claims_dir.is_dir():
        return False
    for path in sorted(claims_dir.glob("*.json")):
        claim = Claim.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if claim.answers == hypothesis_id:
            return claim.status == ClaimStatus.CONTESTED
    return False


def _contested_record_exists(run_dir: Path, hypothesis_id: str) -> bool:
    """True iff a ``CONTESTED_RECORD`` bound to ``hypothesis_id`` is in the log."""
    import json

    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return False
    for path in sorted(evidence_dir.glob("*.json")):
        item = EvidenceItem.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if (
            item.kind == EvidenceKind.CONTESTED_RECORD
            and item.literature_decision is not None
            and item.literature_decision.hypothesis_id == hypothesis_id
        ):
            return True
    return False


__all__ = [
    "record_novelty_searched",
    "record_novelty_skip",
    "record_contested",
    "contested_checkpoint",
    "contested_open",
]
