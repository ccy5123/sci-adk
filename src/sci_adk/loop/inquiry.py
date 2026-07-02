"""
Mid-research emergent-question trigger: record an ad-hoc discovery decision when a NEW
question arises DURING research (design/literature-acquisition.md, field-report concern 2).

The Spec-anchor prior-work trigger (``prior_work.py``) covers "before any result exists,
has this been done?". But a real researcher also stops mid-stream -- "wait, has anyone
measured X?" -- and searches. That emergent moment had no recording rail: if the agent
searched, only a bare ``LITERATURE`` item landed (no *decision*); if it skipped, nothing at
all. In a system whose spine is record != belief and "null results are results" (E2), the
emergent discovery **decision** must be in the record too.

So this module records an ``INQUIRY_DECISION`` -- a *recording-type* item capturing the
emergent question + the decision:

  - **searched** -> :func:`record_inquiry_searched` drives the EXISTING
    :class:`LiteratureAcquirer` (a ``LITERATURE`` EvidenceItem = the acquired artifact,
    reused not reinvented) AND records the ``INQUIRY_DECISION`` referencing it;
  - **not searched** -> :func:`record_inquiry_skip` records the ``INQUIRY_DECISION`` with
    the reason (a recorded null).

Unlike the Spec-anchor prior-work trigger there is NO "open" checkpoint to close: an inquiry
is raised ad-hoc by the agent's judgment (the design deliberately rejects a periodic
"check literature?" prompt), so it is only ever a recorded decision, never a pending gate.
Kernel-side, no LLM: discovery (topic -> DOIs) is the agent's ``web_search`` upstream; this
module only records the decision and (searched path) acquires.

An inquiry is a *decision*, not a belief -- ``bears_on=[]`` (via the shared
:func:`write_decision_evidence`), so it never enters the DecisionEngine. Its ``code_ref``
is a decision pointer, not generating code, so ``verify`` excludes ``INQUIRY_DECISION`` from
the reproduction-bundle requirement (the P3 class). F7 seam preserved: this records evidence
and never mutates the Spec, so a finding that touches a frozen element still routes through
the human-only amendment path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.evidence import EvidenceItem, EvidenceKind, Provenance
from sci_adk.core.spec import Spec
from sci_adk.loop.decision_record import write_decision_evidence
from sci_adk.loop.literature_acquirer import AcquisitionOutcome, LiteratureAcquirer
from sci_adk.search.paperforge_adapter import PaperforgeAdapter

_ID_PREFIX = "evi-inquiry-decision"


def _require_question(question: str) -> str:
    question = question.strip()
    if not question:
        raise ValueError(
            "an inquiry requires a non-empty question: the emergent question is the "
            "record of WHAT prompted the mid-research search, and must not be blank."
        )
    return question


def record_inquiry_skip(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    question: str,
    reason: str,
) -> EvidenceItem:
    """Record a *not-searched* emergent-question decision as an ``INQUIRY_DECISION``.

    A recorded null (E2): the emergent ``question`` AND the ``reason`` it was not pursued
    are captured, so the decision is never invisible. ``bears_on`` is empty (a decision,
    not a belief).

    Args:
        spec: the governing Spec (its ``id`` selects the run directory).
        workspace_dir: workspace root holding ``runs/`` (default: cwd).
        question: the emergent question that arose mid-research (required, non-blank).
        reason: why it was not searched (required -- a null is still a *recorded* result).

    Raises:
        ValueError: if ``question`` or ``reason`` is empty/blank.
    """
    question = _require_question(question)
    reason = reason.strip()
    if not reason:
        raise ValueError(
            "record_inquiry_skip requires a non-empty reason: a skipped emergent search "
            "is a recorded null, and the record must say why."
        )
    return write_decision_evidence(
        spec,
        workspace_dir,
        kind=EvidenceKind.INQUIRY_DECISION,
        finding=f"inquiry skipped: {question} | reason: {reason}",
        provenance=Provenance(
            code_ref="inquiry:skip",
            environment="emergent-question decision (mid-research trigger); no search performed",
        ),
        id_prefix=_ID_PREFIX,
    )


def record_inquiry_searched(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    question: str,
    dois: Sequence[str],
    adapter: Optional[PaperforgeAdapter] = None,
    email: Optional[str] = None,
    target_id: Optional[str] = None,
    allow_no_email: bool = False,
    config_root: Optional[Path] = None,
    **options: Any,
) -> AcquisitionOutcome:
    """Record a *searched* emergent-question decision: acquire via the EXISTING acquirer,
    then write an ``INQUIRY_DECISION`` referencing the acquired ``LITERATURE`` artifact.

    Discovery (question -> DOIs) is the agent's ``web_search`` upstream; given the DOI list
    this delegates to :class:`LiteratureAcquirer` (the ``LITERATURE`` EvidenceItem is the
    acquired artifact, full paperforge provenance, reused not reinvented), then records the
    dedicated ``INQUIRY_DECISION`` -- the *decision* that this emergent question was searched
    -- referencing the LITERATURE item for traceability.

    The decision is recorded even when acquisition halts (some DOIs had no OA PDF): a search
    *was performed* regardless of acquisition success. The returned :class:`AcquisitionOutcome`
    still carries any ``halt`` for the orchestrator.

    Contact-email policy (E4): the searched path uses the polite pool, so by DEFAULT it
    REQUIRES a contact email (resolved from ``email`` arg -> config -> ``$UNPAYWALL_EMAIL``);
    when none is configured it raises ``ConfigHalt`` before any acquisition. Pass
    ``allow_no_email=True`` to proceed degraded. Resolution happens here (not only in the
    acquirer) so the requirement holds even when a fake ``adapter`` is injected for tests.

    Raises:
        ConfigHalt: when ``allow_no_email`` is False and no contact email resolves.
        ValueError: if ``question`` is empty/blank.
    """
    question = _require_question(question)

    from sci_adk.config import require_contact_email

    email = require_contact_email(
        email, allow_no_email=allow_no_email, config_root=config_root
    )

    acquirer = LiteratureAcquirer(spec, workspace_dir, adapter=adapter, email=email)
    outcome = acquirer.acquire(dois, target_id=target_id, **options)

    lit = outcome.evidence
    write_decision_evidence(
        spec,
        workspace_dir,
        kind=EvidenceKind.INQUIRY_DECISION,
        finding=f"inquiry searched: {question} | DOIs={list(dois)}",
        provenance=Provenance(
            code_ref="inquiry:searched",
            data_ref=f"literature_evidence={lit.id}; "
                     f"manifest={lit.result.artifact_ref or ''}",
            environment="emergent-question decision (mid-research trigger); "
                        "see referenced LITERATURE item for the acquired corpus",
        ),
        id_prefix=_ID_PREFIX,
    )
    return outcome


__all__ = ["record_inquiry_searched", "record_inquiry_skip"]
