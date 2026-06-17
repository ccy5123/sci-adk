"""
Spec-time prior-work trigger: the recording-type discovery checkpoint + the two
decision recorders (design/literature-acquisition.md §"Discovery trigger model").

The gap this closes: acquisition is fully recorded (a ``LITERATURE`` EvidenceItem),
but the *decision* to check prior work leaves no trace -- if the agent never
searches, nothing in the record shows whether prior work was even considered. In a
system whose spine is record != belief and "null results are results" (Invariant
E2), **not searching is itself a recorded null**.

So at Spec creation the compiler emits a :class:`PriorWorkCheckpoint` -- a
*recording-type* reminder (no verdict trail, not hypothesis-bound). It stays "open"
until an explicit prior-work **decision** is recorded in the single append-only
Evidence log. BOTH outcomes write a dedicated ``PRIOR_WORK_DECISION`` item so the
decision is unambiguous and never conflated with an incidental acquisition:

  - **searched** -> :func:`record_prior_work_searched` drives the EXISTING
    :class:`LiteratureAcquirer` (a ``LITERATURE`` EvidenceItem = the acquired
    artifact, reused not reinvented) AND records a ``PRIOR_WORK_DECISION`` item that
    references it (finding ``"searched: DOIs=[...]"``);
  - **not searched** -> :func:`record_prior_work_skip` writes a
    ``PRIOR_WORK_DECISION`` EvidenceItem carrying the reason (a recorded null).

The checkpoint closes **only** on a ``PRIOR_WORK_DECISION`` item -- never on a bare
``LITERATURE`` item (a future trigger may acquire literature for other reasons, and
that must not spuriously satisfy the Spec-time prior-art check).

No LLM anywhere: discovery (topic -> DOIs) is the in-session agent's ``web_search``
upstream; this module only records the decision and (searched path) acquires.

Only the **Spec-creation** trigger is implemented. The contested / novelty /
paper-render triggers are deferred (graded as incremental in the design; never
pegged at the Spec anchor's priority). A prior-work finding that would force a
**frozen** Spec element to change must route through the human-only Spec amendment
path (F7) -- never a silent mutation; this module does not mutate the Spec, so that
seam is preserved by construction (see :func:`record_prior_work_searched`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.evidence import EvidenceItem, EvidenceKind, Provenance
from sci_adk.core.spec import Spec
from sci_adk.loop.decision_record import write_decision_evidence
from sci_adk.loop.literature_acquirer import AcquisitionOutcome, LiteratureAcquirer
from sci_adk.loop.verdict import PriorWorkCheckpoint
from sci_adk.search.paperforge_adapter import PaperforgeAdapter

# The default reminder shown on the Spec-time checkpoint. Phrased as the cleanest,
# most important check ("has this been done?") -- pre-registration canonical, zero
# post-hoc risk (the Spec anchor in the graded trigger table).
_PROMPT = (
    "Prior-work check (Spec creation): before any result exists, has this been "
    "done? Search prior work (agent web_search), then record the decision -- "
    "searched (-> LITERATURE evidence) or skipped with a reason (-> a recorded "
    "null). Run `sci-adk prior-work <run-dir> --searched <dois...>` or "
    "`--skip --reason \"...\"`."
)

# The EvidenceKind that, when present for a Spec, closes the prior-work checkpoint:
# ONLY an explicit PRIOR_WORK_DECISION record (searched-decision or skipped-decision).
# A bare LITERATURE item does NOT close it -- literature may be acquired for other
# reasons (later triggers), and that must not silently satisfy the prior-art check.
_CLOSING_KINDS = (EvidenceKind.PRIOR_WORK_DECISION,)


def prior_work_checkpoint(spec: Spec, prompt: str = _PROMPT) -> PriorWorkCheckpoint:
    """Build the Spec-time recording-type checkpoint for ``spec``.

    Recording-type: it carries no verdict trail and is not hypothesis-bound -- it is
    a reminder that the prior-work *decision* has not yet been recorded.
    """
    return PriorWorkCheckpoint(
        spec_id=spec.id,
        spec_version=spec.version,
        prompt=prompt,
    )


def prior_work_open(spec: Spec, workspace_dir: Optional[Path] = None) -> bool:
    """True when no prior-work decision has been recorded for ``spec`` yet.

    The checkpoint closes once a ``PRIOR_WORK_DECISION`` EvidenceItem for this Spec
    exists in the single append-only log under ``runs/<spec.id>/evidence/`` -- the
    explicit decision record, written by BOTH the searched and skipped paths. A bare
    ``LITERATURE`` item does NOT close it. This reads the record only -- no
    capability, no LLM -- so it works during the record-only re-read too.
    """
    # @MX:ANCHOR: [AUTO] the open/closed predicate for the Spec-time prior-work
    #   checkpoint: closed iff an explicit PRIOR_WORK_DECISION item is on disk.
    # @MX:REASON: [AUTO] this is the single point that decides whether the discovery
    #   decision has been recorded; it MUST close only on the dedicated decision kind
    #   (never a bare LITERATURE acquisition, which a later trigger may produce for
    #   unrelated reasons) and MUST stay record-only (no capability/LLM) so the future
    #   `sci-adk verify` re-read reaches the same verdict. Either change would break
    #   the record != belief invariant at exactly the trigger.
    workspace = Path(workspace_dir) if workspace_dir else Path.cwd()
    evidence_dir = workspace / "runs" / spec.id / "evidence"
    if not evidence_dir.is_dir():
        return True
    for path in sorted(evidence_dir.glob("*.json")):
        item = EvidenceItem.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if item.kind in _CLOSING_KINDS:
            return False
    return True


def record_prior_work_skip(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    reason: str,
) -> EvidenceItem:
    """Record the *not-searched* decision as a ``PRIOR_WORK_DECISION`` EvidenceItem.

    A recorded null (Invariant E2): the reason WHY prior-art search was skipped is
    captured in the record so the decision is never invisible. The item is a
    decision, not a belief -- ``bears_on`` is empty (it asserts no support/refute
    direction on any hypothesis).

    Args:
        spec: the governing Spec (its ``id`` selects the run directory).
        workspace_dir: workspace root holding ``runs/`` (default: cwd).
        reason: why prior-art search was skipped (required -- a null result is still
            a *recorded* result; an empty reason is refused).

    Returns:
        The persisted ``PRIOR_WORK_DECISION`` EvidenceItem.

    Raises:
        ValueError: if ``reason`` is empty/blank.
    """
    reason = reason.strip()
    if not reason:
        raise ValueError(
            "record_prior_work_skip requires a non-empty reason: a skipped "
            "prior-work search is a recorded null, and the record must say why."
        )

    return _write_prior_work_decision(
        spec,
        workspace_dir,
        finding=f"skipped: {reason}",
        provenance=Provenance(
            code_ref="prior_work:skip",
            environment="prior-work decision (Spec-time trigger); no search performed",
        ),
    )


def record_prior_work_searched(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    dois: Sequence[str],
    adapter: Optional[PaperforgeAdapter] = None,
    email: Optional[str] = None,
    target_id: Optional[str] = None,
    allow_no_email: bool = False,
    config_root: Optional[Path] = None,
    **options: Any,
) -> AcquisitionOutcome:
    """Record the *searched* decision: acquire via the EXISTING acquirer, then write
    an explicit ``PRIOR_WORK_DECISION``.

    Discovery (topic -> DOIs) is the agent's ``web_search`` upstream; given the DOI
    list, this delegates to :class:`LiteratureAcquirer` -- the ``LITERATURE``
    EvidenceItem is the acquired *artifact* (full paperforge provenance, reused not
    reinvented). It then records a dedicated ``PRIOR_WORK_DECISION`` item -- the
    *decision* that prior work was searched -- which references the LITERATURE item
    (its id + manifest) for traceability. Only that decision closes the checkpoint
    (a bare LITERATURE item does not).

    The decision is recorded even when acquisition halts (some DOIs had no OA PDF):
    a search *was performed* regardless of acquisition success. The returned
    :class:`AcquisitionOutcome` still carries any ``halt`` for the orchestrator.

    Contact-email policy (design/evidence-validity.md E4): the searched path uses the
    Unpaywall/OpenAlex polite pool, so by DEFAULT it REQUIRES a contact email,
    resolved from (``email`` arg -> ``~/.config/sci-adk/config.toml`` ->
    ``$UNPAYWALL_EMAIL``). When none is configured it raises ``ConfigHalt`` BEFORE any
    acquisition is attempted -- silent degradation is refused (it is how the rice run
    rode past the literature gate). Pass ``allow_no_email=True`` to proceed in the
    degraded mode (no ``--email``). The resolution happens here (not only in the
    acquirer/adapter) so the requirement holds even when a fake ``adapter`` is injected
    for tests.

    F7 seam: a finding here that implies a *frozen* Spec element must change goes
    through the human-only amendment path -- never a silent mutation. This function
    records evidence and does not touch the Spec, so that seam holds by construction.

    Raises:
        ConfigHalt: when ``allow_no_email`` is False and no contact email resolves.
    """
    # Resolve+require the contact email FIRST, so a missing email halts before any
    # acquisition is attempted (E4). The require-or-degrade policy is single-sourced in
    # config.require_contact_email (shared by every OA searched trigger).
    from sci_adk.config import require_contact_email

    email = require_contact_email(
        email, allow_no_email=allow_no_email, config_root=config_root
    )

    acquirer = LiteratureAcquirer(
        spec, workspace_dir, adapter=adapter, email=email
    )
    outcome = acquirer.acquire(dois, target_id=target_id, **options)

    # Record the explicit prior-art DECISION, referencing the LITERATURE artifact.
    lit = outcome.evidence
    _write_prior_work_decision(
        spec,
        workspace_dir,
        finding=f"searched: DOIs={list(dois)}",
        provenance=Provenance(
            code_ref="prior_work:searched",
            data_ref=f"literature_evidence={lit.id}; "
                     f"manifest={lit.result.artifact_ref or ''}",
            environment="prior-work decision (Spec-time trigger); "
                        "see referenced LITERATURE item for the acquired corpus",
        ),
    )
    return outcome


# -- helpers ---------------------------------------------------------------- #

def _write_prior_work_decision(
    spec: Spec,
    workspace_dir: Optional[Path],
    *,
    finding: str,
    provenance: Provenance,
) -> EvidenceItem:
    """Persist a ``PRIOR_WORK_DECISION`` EvidenceItem into the single log.

    Shared by both decision paths. The item is a recorded decision, not a belief --
    ``bears_on`` is empty (it asserts no support/refute direction on any hypothesis).
    Delegates the id/build/save mechanics to the shared
    :func:`sci_adk.loop.decision_record.write_decision_evidence` so there is ONE
    implementation of "write a decision EvidenceItem" across the discovery triggers
    (the novelty / contested recorders reuse the same writer).

    The Spec-creation prior-art decision is Spec-bound (not hypothesis-bound), so it
    carries NO ``literature_decision`` payload -- preserving its load-bearing
    closing-kind anchor (``prior_work_open`` keys solely on ``PRIOR_WORK_DECISION``).
    """
    return write_decision_evidence(
        spec,
        workspace_dir,
        kind=EvidenceKind.PRIOR_WORK_DECISION,
        finding=finding,
        provenance=provenance,
        id_prefix="evi-pw-decision",
    )


__all__ = [
    "prior_work_checkpoint",
    "prior_work_open",
    "record_prior_work_skip",
    "record_prior_work_searched",
]
