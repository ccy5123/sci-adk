"""
The novelty (High) and contested (Medium) discovery triggers
(design/literature-acquisition.md §"Discovery trigger model").

These are the two *incremental* triggers added beside the implemented Spec-creation
prior-art anchor (``loop/prior_work.py``). Both are HYPOTHESIS-bound (unlike the
Spec-bound prior-art check) and both record their decision into the single append-only
Evidence log via the SHARED writer ``loop/decision_record.write_decision_evidence`` --
no write/id/save logic is duplicated.

  - **Novelty (High)** underwrites the *validity* of a "first/new" claim, in TWO
    INDEPENDENT kinds -- ``result`` (no prior work established the hypothesis's RESULT)
    and ``method`` (no prior work used its METHOD) -- each separately pre-registered
    (its ``novelty_result`` / ``novelty_method`` Spec flag), searched, and derived
    (design/literature-acquisition.md §"Novelty -- definition (2-kind)"). Every
    novelty recorder is parameterised by ``kind``. Its decision is recorded as a
    ``NOVELTY_DECISION`` item carrying that ``kind``:
      * :func:`record_novelty_searched` drives the EXISTING ``LiteratureAcquirer``
        (a ``LITERATURE`` artifact) and records the searched decision (with its
        ``found="nothing"``/``found="something"`` outcome + ``kind``) referencing it;
      * :func:`record_novelty_skip` records a skipped decision (a recorded null + reason
        + ``kind``).
    B-replace: each kind is a 1st-class revisable Claim ``claim-novelty-{kind}-<hyp>``
    derived by rule (``derive_novelty_status(hyp, kind, ...)``): SUPPORTED iff a recorded
    *found_nothing* decision for THAT {hyp, kind}, else PROPOSED. There is NO run-HALT;
    while a kind's novelty claim is PROPOSED the compiler surfaces a NON-HALT
    :func:`novelty_checkpoint` (``novelty_open`` reports open-ness per {hyp, kind}).

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
from typing import Any, Literal, Optional, Sequence

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
from sci_adk.loop.verdict import ContestedCheckpoint, NoveltyCheckpoint
from sci_adk.search.paperforge_adapter import PaperforgeAdapter

# Default reminders shown on each surfaced checkpoint.
_CONTESTED_PROMPT = (
    "Contested check: this claim has conflicting evidence (support and refutation "
    "coexist). Record the post-conflict literature decision so papers found AFTER the "
    "conflict stay visible (anti post-hoc-rationalization). Run `sci-adk contested "
    "<run-dir> --hypothesis <id> --note \"...\"` (or --searched <dois...> to also "
    "acquire). This is recording, not a gate -- nothing halts."
)

# Reason-tailored novelty checkpoint prompts (B-replace), per kind. NON-HALT: the run
# proceeds while the kind's novelty claim is PROPOSED; this is a recording reminder, not
# a gate. ``{kind}`` is the novelty axis (result|method) -- naming it keeps the reminder
# and the CLI form unambiguous (each kind is searched/recorded independently).
#   - not_searched: no {hyp, kind} novelty decision (or a skipped one) -> the search has
#     not been done. Tell the agent to search prior art for THIS kind and record the
#     outcome, or amend the kind's novelty flag away (F7).
#   - found_something: a {hyp, kind} prior-art search was done and found prior art. Do NOT
#     tell the agent to go search (the search is done) -- the escape is the F7 amendment.
_NOVELTY_PROMPT_NOT_SEARCHED = (
    "Novelty check ({kind}-novelty): this hypothesis asserts {kind}-novelty (no prior "
    "published work established its {kind}) but no prior-art search returned nothing for "
    "the {kind} kind, so the {kind}-novelty claim stays PROPOSED. Search prior art for "
    "the {kind} and record the outcome (`sci-adk novelty <run-dir> --hypothesis <id> "
    "--kind {kind} --searched <dois...> --outcome found-nothing`), or drop the "
    "novelty_{kind} flag via a Spec amendment (F7, human-only -- never a silent edit). "
    "This is a recording reminder, not a gate -- nothing halts."
)
_NOVELTY_PROMPT_FOUND_SOMETHING = (
    "Novelty check ({kind}-novelty): prior art WAS found for the {kind} kind of this "
    "hypothesis (a recorded found_something search), so the {kind}-novelty claim cannot "
    "be supported and stays PROPOSED. The search is done -- do not search again. Drop the "
    "novelty_{kind} flag via a Spec amendment (F7, human-only -- never a silent edit). "
    "This is a recording reminder, not a gate -- nothing halts."
)


# -- novelty (High) --------------------------------------------------------- #

def record_novelty_searched(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    hypothesis_id: str,
    kind: Literal["result", "method"],
    dois: Sequence[str],
    found: Literal["nothing", "something"],
    adapter: Optional[PaperforgeAdapter] = None,
    email: Optional[str] = None,
    target_id: Optional[str] = None,
    allow_no_email: bool = False,
    config_root: Optional[Path] = None,
    **options: Any,
) -> AcquisitionOutcome:
    """Record the novelty *searched* decision for one {hypothesis, kind}: acquire via the
    EXISTING acquirer, then write a ``NOVELTY_DECISION`` (carrying ``kind``) referencing
    the acquired ``LITERATURE`` item.

    2-kind (design/literature-acquisition.md §"Novelty -- definition (2-kind)"): ``kind``
    selects which axis (``result`` | ``method``) this search serves; the recorded decision
    derives ONLY that kind's claim. The searched decision records its OUTCOME:
    ``found="nothing"`` -> ``found_nothing`` (the prior-art search returned nothing -> the
    {hyp, kind} novelty claim derives SUPPORTED via ``derive_novelty_status``);
    ``found="something"`` -> ``found_something`` (prior art exists -> it stays PROPOSED).
    Discovery (topic -> DOIs) is the agent's ``web_search`` upstream; given the DOI list
    this delegates to :class:`LiteratureAcquirer` (the ``LITERATURE`` item is the acquired
    artifact, reused not reinvented).

    Contact-email policy mirrors ``record_prior_work_searched`` exactly
    (design/evidence-validity.md E4): by DEFAULT a contact email is REQUIRED and resolved
    here (arg -> config -> ``$UNPAYWALL_EMAIL``); a missing email raises ``ConfigHalt``
    BEFORE any acquisition. ``allow_no_email=True`` proceeds degraded.

    Raises:
        ConfigHalt: when ``allow_no_email`` is False and no contact email resolves.
    """
    from sci_adk.config import require_contact_email

    outcome_str = "found_nothing" if found == "nothing" else "found_something"

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
        finding=f"{kind}-novelty {outcome_str}: DOIs={list(dois)}",
        provenance=Provenance(
            code_ref=f"novelty:{kind}:{outcome_str}",
            data_ref=f"literature_evidence={lit.id}; "
                     f"manifest={lit.result.artifact_ref or ''}",
            environment=f"novelty decision (High trigger, {kind}-novelty); "
                        "see referenced LITERATURE item for the acquired corpus",
        ),
        id_prefix="evi-nov-decision",
        literature_decision=LiteratureDecision(
            outcome=outcome_str,
            hypothesis_id=hypothesis_id,
            kind=kind,
            literature_evidence_id=lit.id,
        ),
    )
    return outcome


def record_novelty_skip(
    spec: Spec,
    workspace_dir: Optional[Path] = None,
    *,
    hypothesis_id: str,
    kind: Literal["result", "method"],
    reason: str,
) -> EvidenceItem:
    """Record the novelty *skipped* decision for one {hypothesis, kind} as a
    ``NOVELTY_DECISION`` (a recorded null carrying ``kind``).

    A skipped novelty decision does NOT satisfy the {hyp, kind} novelty gate (skipping the
    prior-art search guts that kind's claim's only evidentiary basis) -- but it is still
    recorded, with its reason and kind, so the decision is never invisible (Invariant E2).

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
        finding=f"{kind}-novelty skipped: {reason}",
        provenance=Provenance(
            code_ref=f"novelty:{kind}:skip",
            environment=f"novelty decision (High trigger, {kind}-novelty); "
                        "no search performed",
        ),
        id_prefix="evi-nov-decision",
        literature_decision=LiteratureDecision(
            outcome="skipped", hypothesis_id=hypothesis_id, kind=kind, reason=reason
        ),
    )


def novelty_open(
    spec: Spec,
    hypothesis_id: str,
    kind: Literal["result", "method"],
    workspace_dir: Optional[Path] = None,
) -> bool:
    """True iff ``hypothesis_id`` has the ``kind`` novelty flag set AND its
    ``claim-novelty-{kind}-<hyp>`` on disk is PROPOSED (read-only, no LLM, no capability).

    Mirrors :func:`contested_open`, per {hyp, kind} (2-kind). A novelty checkpoint is
    "open" only while the hypothesis IS a novelty claim of THAT kind AND the kind's claim
    has not yet derived SUPPORTED. A hypothesis with the kind's flag unset has nothing to
    surface for that kind; a SUPPORTED kind claim (a recorded found_nothing search of that
    {hyp, kind}) is closed. A flagged kind with no recorded claim yet is implicitly
    PROPOSED -> open. Reads the recorded claim only.
    """
    # @MX:ANCHOR: [AUTO] the open/closed predicate for the per-kind novelty checkpoint:
    #   open iff the hypothesis has the kind's novelty flag set AND its
    #   claim-novelty-{kind}-<hyp> on disk is PROPOSED (or absent, treated as PROPOSED).
    # @MX:REASON: [AUTO] the compiler surfaces open novelty checkpoints from this; it
    #   MUST stay record-only (no capability/LLM) so the headless verify re-read reaches
    #   the same verdict, and MUST close only when the kind's novelty claim is SUPPORTED (a
    #   recorded found_nothing search of THAT kind). It is a recording reminder -- it never
    #   gates/halts.
    if not _hypothesis_is_novelty(spec, hypothesis_id, kind):
        return False
    workspace = Path(workspace_dir) if workspace_dir else Path.cwd()
    run_dir = workspace / "runs" / spec.id
    return _novelty_claim_is_proposed(run_dir, hypothesis_id, kind)


def novelty_checkpoint(
    spec: Spec,
    hypothesis_id: str,
    kind: Literal["result", "method"],
    spec_version: int,
    *,
    reason: Literal["not_searched", "found_something"],
) -> NoveltyCheckpoint:
    """Build the recording-type novelty checkpoint for one {hypothesis, kind} (High
    trigger).

    NON-HALT (B-replace): a reminder that the kind's novelty claim is still PROPOSED. The
    prompt names the ``kind`` and is tailored by ``reason``:
      - ``not_searched`` (no {hyp, kind} novelty decision, or a ``skipped`` one): tell the
        agent to search prior art for this kind and record the outcome, or drop the kind's
        novelty flag via F7;
      - ``found_something`` (a {hyp, kind} prior-art search found prior art): the search is
        done -- do NOT tell the agent to search again; the escape is the F7 amendment.
    """
    template = (
        _NOVELTY_PROMPT_FOUND_SOMETHING
        if reason == "found_something"
        else _NOVELTY_PROMPT_NOT_SEARCHED
    )
    return NoveltyCheckpoint(
        hypothesis_id=hypothesis_id,
        spec_id=spec.id,
        spec_version=spec_version,
        prompt=template.format(kind=kind),
    )


def novelty_reason_from_decisions(
    hypothesis_id: str,
    kind: Literal["result", "method"],
    novelty_decisions: Sequence[EvidenceItem],
) -> Literal["not_searched", "found_something"]:
    """PURE in-memory novelty-checkpoint reason for one {hypothesis, kind}:
    ``found_something`` iff a ``found_something`` NOVELTY_DECISION bound to
    ``hypothesis_id`` AND ``kind`` is present in ``novelty_decisions``, else
    ``not_searched`` (no decision for this kind, or a ``skipped`` one).

    This is the SINGLE home for the reason logic. It operates on the SAME decisions the
    kind's novelty CLAIM is derived from (``derive_novelty_status(hyp, kind, ...)``), so
    the checkpoint message and the claim status agree even in a single-pass ``compile()``
    where an in-memory ``found_something`` decision is not yet persisted on disk. A
    ``found_nothing`` decision means the kind's claim is SUPPORTED (the checkpoint is
    closed), so it never reaches this reason path -- it returns ``not_searched``
    defensively.
    """
    found_something = any(
        ev.kind == EvidenceKind.NOVELTY_DECISION
        and ev.literature_decision is not None
        and ev.literature_decision.hypothesis_id == hypothesis_id
        and ev.literature_decision.kind == kind
        and ev.literature_decision.outcome == "found_something"
        for ev in novelty_decisions
    )
    return "found_something" if found_something else "not_searched"


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

def _hypothesis_is_novelty(
    spec: Spec, hypothesis_id: str, kind: Literal["result", "method"]
) -> bool:
    """True iff the Spec's hypothesis ``hypothesis_id`` has the ``kind`` novelty flag set
    (``novelty_result`` for ``result``, ``novelty_method`` for ``method``)."""
    for h in spec.hypotheses:
        if h.id == hypothesis_id:
            return bool(h.novelty_result if kind == "result" else h.novelty_method)
    return False


def _novelty_claim_is_proposed(
    run_dir: Path, hypothesis_id: str, kind: Literal["result", "method"]
) -> bool:
    """True iff the recorded ``claim-novelty-{kind}-<hyp>`` is PROPOSED, OR no such claim
    exists yet (an unrecorded kind novelty claim is implicitly PROPOSED). False iff it is
    SUPPORTED (or any non-PROPOSED status)."""
    import json

    claim_path = (
        run_dir / "claims" / f"claim-novelty-{kind}-{hypothesis_id}.json"
    )
    if not claim_path.exists():
        return True
    claim = Claim.model_validate(json.loads(claim_path.read_text(encoding="utf-8")))
    return claim.status == ClaimStatus.PROPOSED


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
    "novelty_open",
    "novelty_checkpoint",
    "novelty_reason_from_decisions",
    "record_contested",
    "contested_checkpoint",
    "contested_open",
]
