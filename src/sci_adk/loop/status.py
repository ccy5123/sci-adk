"""
``sci-adk status <run>`` -- the terse, read-only session-state snapshot (D1).

design/research-session-enforcement.md §6 D1: a read-only verb that prints WHAT IS
RECORDED and WHAT IS PENDING for a run dir. It is consumed every turn by a future
``UserPromptSubmit`` re-anchor hook, so it MUST be cheap: NO recompile, NO experiment,
NO LLM, NO writes, NO re-derivation. (Re-derivation is ``sci-adk verify``'s job; this
verb reports the RECORDED claim statuses + the open *decisions* only.)

The state read is a pure composition over already-tested read-only loaders/predicates:

  - claims: the run's recorded ``claims/*.json`` (loaded with the same logic as
    ``verify._load_claims`` -- keyed by ``claim.id`` so an experiment claim
    ``claim-<hyp>`` and a novelty claim ``claim-novelty-<hyp>`` for the SAME hypothesis
    are both surfaced, never collapsed);
  - prior-work: ``prior_work.prior_work_open(spec, workspace_dir)``;
  - novelty: ``literature_triggers.novelty_open(spec, hyp_id, workspace_dir)`` per
    ``novelty=True`` hypothesis;
  - contested: ``literature_triggers.contested_open(spec, hyp_id, workspace_dir)`` per
    hypothesis;
  - open checkpoints: a ``checkpoints/<hyp>.json`` with no matching
    ``verdicts/<hyp>.json`` -- a proof/qualitative checkpoint still awaiting the
    in-session agent's verdict.

KERNEL-side (``sci_adk.loop``): stdlib + ``sci_adk.core`` + the loop predicates/loaders
only. It MUST NOT import the adapter (F4 seam, enforced by
``tests/test_kernel_adapter_seam.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.spec import Spec
from sci_adk.loop.literature_triggers import contested_open, novelty_open
from sci_adk.loop.prior_work import prior_work_open


class StatusReport(BaseModel):
    """A frozen, read-only snapshot of a run dir's recorded + pending state.

    Every field is derived from disk by :func:`session_status`. ``headline`` is the
    one-line summary the re-anchor hook echoes (it is also line 1 of
    :func:`render_status_text`).

    Attributes:
        spec_id: the recorded Spec id ("" when nothing is recorded yet).
        run_name: the run directory's own name (e.g. ``t1-godel``).
        n_hypotheses: number of hypotheses in the recorded Spec (0 when no spec).
        claim_counts: counts by ``ClaimStatus`` value (only non-zero statuses appear).
        unresolved_claim_ids: PROPOSED *experiment* claim ids (``claim-<hyp>``) needing
            attention. Novelty claims are surfaced via ``novelty_unresolved`` instead,
            so they are not double-listed here.
        contested_claim_ids: ids of claims whose status is CONTESTED.
        prior_work_open: True iff no PRIOR_WORK_DECISION is recorded for the Spec.
        novelty_unresolved: hypothesis ids whose novelty checkpoint is still open
            (``novelty=True`` AND its ``claim-novelty-<hyp>`` is PROPOSED/absent).
        contested_pending: hypothesis ids whose Claim is CONTESTED with no recorded
            CONTESTED_RECORD decision yet.
        checkpoints_awaiting_verdict: hypothesis ids with a ``checkpoints/<hyp>.json``
            but no matching ``verdicts/<hyp>.json``.
        headline: the one-line summary (line 1 of the rendered text).
    """

    model_config = {"frozen": True}

    spec_id: str = Field(default="")
    run_name: str = Field(default="")
    n_hypotheses: int = Field(default=0)
    claim_counts: Dict[str, int] = Field(default_factory=dict)
    unresolved_claim_ids: List[str] = Field(default_factory=list)
    contested_claim_ids: List[str] = Field(default_factory=list)
    prior_work_open: bool = Field(default=False)
    novelty_unresolved: List[str] = Field(default_factory=list)
    contested_pending: List[str] = Field(default_factory=list)
    checkpoints_awaiting_verdict: List[str] = Field(default_factory=list)
    headline: str = Field(default="")


_NOTHING_RECORDED = "nothing recorded yet"


def session_status(run_dir: Path) -> StatusReport:
    """Compose a read-only :class:`StatusReport` over a run dir.

    PURE + READ-ONLY: reads ``spec.json`` + ``claims/`` + ``evidence/`` +
    ``checkpoints/`` + ``verdicts/`` only, via the already-tested loaders/predicates.
    No recompile, no experiment, no LLM, no write, no re-derivation.

    A missing/empty run dir (no ``spec.json`` OR no recorded claims) yields a
    "nothing recorded yet" report with empty lists -- the D2 "no run+Claim -> the
    Stop gate passes" signal. The caller never needs to special-case absence.

    Precondition (caller contract): ``run_dir`` MUST follow the
    ``<workspace>/runs/<spec.id>/`` layout. The workspace root is derived as
    ``run_dir.parent.parent`` and passed to ``prior_work_open`` / ``novelty_open`` /
    ``contested_open``, which each RE-APPEND ``runs/<spec.id>`` internally. A ``run_dir``
    NOT nested under a ``runs/`` directory therefore yields silently-incorrect
    prior-work / novelty / contested results (no error is raised). The CLI only ever
    passes a real ``runs/<id>`` path, so this is a caller contract, not a runtime bug.

    Args:
        run_dir: a ``<workspace>/runs/<spec.id>/`` directory (may not exist).

    Returns:
        A :class:`StatusReport`. Never raises for a missing/empty run dir.
    """
    run_dir = Path(run_dir)
    run_name = run_dir.name

    spec = _load_spec(run_dir)
    if spec is None:
        return StatusReport(
            run_name=run_name,
            headline=_headline(run_name, spec_id=None, n_unresolved=0,
                               prior_work_open=False, n_novelty=0,
                               n_awaiting=0, has_record=False),
        )

    # The three *_open predicates take the WORKSPACE root (the parent of runs/) and
    # internally append runs/<spec.id>; run_dir IS workspace/runs/<spec.id>, so the
    # workspace is run_dir.parent.parent.
    workspace_dir = run_dir.parent.parent

    # Checkpoints awaiting a verdict exist independently of recorded claims: a
    # proof/qualitative hypothesis surfaces a checkpoint BEFORE any Claim is derived, so
    # it must be reported even on the no-claims path (it is pending work).
    awaiting = _checkpoints_awaiting_verdict(run_dir)

    claims = _load_claims(run_dir)
    if not claims:
        # No recorded claims: there is no recorded *belief* to protect (the D2 signal),
        # but an open checkpoint is still pending work the agent owes a verdict for.
        return StatusReport(
            spec_id=spec.id,
            run_name=run_name,
            n_hypotheses=len(spec.hypotheses),
            checkpoints_awaiting_verdict=awaiting,
            headline=_headline(run_name, spec_id=spec.id, n_unresolved=0,
                               prior_work_open=False, n_novelty=0,
                               n_awaiting=len(awaiting), has_record=bool(awaiting)),
        )

    claim_counts = _count_by_status(claims.values())

    unresolved_claim_ids = sorted(
        c.id for c in claims.values()
        if c.status == ClaimStatus.PROPOSED and not _is_novelty_claim(c)
    )
    contested_claim_ids = sorted(
        c.id for c in claims.values() if c.status == ClaimStatus.CONTESTED
    )

    pw_open = prior_work_open(spec, workspace_dir)

    novelty_unresolved = sorted(
        h.id for h in spec.hypotheses
        if novelty_open(spec, h.id, workspace_dir)
    )
    contested_pending = sorted(
        h.id for h in spec.hypotheses
        if contested_open(spec, h.id, workspace_dir)
    )

    headline = _headline(
        run_name, spec_id=spec.id, n_unresolved=len(unresolved_claim_ids),
        prior_work_open=pw_open, n_novelty=len(novelty_unresolved),
        n_awaiting=len(awaiting), has_record=True,
    )

    return StatusReport(
        spec_id=spec.id,
        run_name=run_name,
        n_hypotheses=len(spec.hypotheses),
        claim_counts=claim_counts,
        unresolved_claim_ids=unresolved_claim_ids,
        contested_claim_ids=contested_claim_ids,
        prior_work_open=pw_open,
        novelty_unresolved=novelty_unresolved,
        contested_pending=contested_pending,
        checkpoints_awaiting_verdict=awaiting,
        headline=headline,
    )


def render_status_text(report: StatusReport) -> str:
    """The terse multi-line human view of a :class:`StatusReport` (headline first).

    Line 1 is ``report.headline`` verbatim (the re-anchor hook echoes it). The body
    lists, when non-empty, the ids needing attention. Always non-empty.
    """
    lines: List[str] = [report.headline]

    if not report.spec_id:
        return "\n".join(lines)

    counts = ", ".join(
        f"{status}={n}" for status, n in sorted(report.claim_counts.items())
    )
    lines.append(
        f"  spec: {report.spec_id}  ({report.n_hypotheses} hypothesis"
        f"{'es' if report.n_hypotheses != 1 else ''}, run '{report.run_name}')"
    )
    lines.append(f"  claims: {counts if counts else 'none recorded'}")

    if report.unresolved_claim_ids:
        lines.append(
            "  unresolved (proposed): " + ", ".join(report.unresolved_claim_ids)
        )
    if report.contested_claim_ids:
        lines.append("  contested: " + ", ".join(report.contested_claim_ids))
    if report.prior_work_open:
        lines.append("  prior-work decision: OPEN (not yet recorded)")
    if report.novelty_unresolved:
        lines.append("  novelty unresolved: " + ", ".join(report.novelty_unresolved))
    if report.contested_pending:
        lines.append(
            "  contested decision pending: " + ", ".join(report.contested_pending)
        )
    if report.checkpoints_awaiting_verdict:
        lines.append(
            "  checkpoints awaiting verdict: "
            + ", ".join(report.checkpoints_awaiting_verdict)
        )

    return "\n".join(lines)


# -- read-only loaders / helpers --------------------------------------------- #

def _load_spec(run_dir: Path) -> "Spec | None":
    """Load ``spec.json`` if present; ``None`` when absent (no run recorded).

    Unlike ``verify._load_spec`` this returns ``None`` rather than raising on a missing
    spec -- ``status`` is a never-failing read-only report, so absence is a valid state
    to report, not an error.
    """
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        return None
    return Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))


def _load_claims(run_dir: Path) -> Dict[str, Claim]:
    """Load recorded Claims keyed by their unique ``id`` (read-only).

    Same logic as ``verify._load_claims``: keyed by ``claim.id`` (not ``claim.answers``)
    so a hypothesis's experiment claim ``claim-<hyp>`` and novelty claim
    ``claim-novelty-<hyp>`` are both surfaced.
    """
    claims_dir = run_dir / "claims"
    if not claims_dir.is_dir():
        return {}
    claims: Dict[str, Claim] = {}
    for path in sorted(claims_dir.glob("*.json")):
        claim = Claim.model_validate(json.loads(path.read_text(encoding="utf-8")))
        claims[claim.id] = claim
    return claims


def _is_novelty_claim(claim: Claim) -> bool:
    """True iff ``claim`` is a novelty claim (id ``claim-novelty-<hyp>``).

    Mirrors ``verify._is_novelty_claim`` -- novelty claims are tracked via the
    ``novelty_open`` predicate (rule-derived), not as generic unresolved claims.
    """
    return claim.id.startswith("claim-novelty-")


def _count_by_status(claims) -> Dict[str, int]:
    """Counts keyed by ``ClaimStatus`` value; only non-zero statuses appear."""
    counts: Dict[str, int] = {}
    for c in claims:
        counts[c.status.value] = counts.get(c.status.value, 0) + 1
    return counts


def _checkpoints_awaiting_verdict(run_dir: Path) -> List[str]:
    """Hypothesis ids with a ``checkpoints/<hyp>.json`` but no matching
    ``verdicts/<hyp>.json`` -- a proof/qualitative checkpoint still awaiting the
    in-session agent's verdict. Read-only directory listing only.
    """
    ckpt_dir = run_dir / "checkpoints"
    if not ckpt_dir.is_dir():
        return []
    verdicts_dir = run_dir / "verdicts"
    awaiting: List[str] = []
    for path in sorted(ckpt_dir.glob("*.json")):
        hyp_id = path.stem
        # the prior-work recording checkpoint (checkpoints/prior_work.json) is not a
        # proof/qualitative verdict checkpoint -- its open/closed state is the
        # prior_work_open predicate, not a verdicts/<id>.json file. Skip it here.
        if hyp_id == "prior_work":
            continue
        if not (verdicts_dir / f"{hyp_id}.json").exists():
            awaiting.append(hyp_id)
    return awaiting


def _headline(
    run_name: str,
    *,
    spec_id: "str | None",
    n_unresolved: int,
    prior_work_open: bool,
    n_novelty: int,
    n_awaiting: int,
    has_record: bool,
) -> str:
    """Build the one-line headline (line 1 of the rendered text, echoed by the hook)."""
    prefix = f"sci-adk status [{run_name}]:"
    if not has_record:
        if spec_id is None:
            return f"{prefix} {_NOTHING_RECORDED} (no run dir / no spec)"
        return f"{prefix} {_NOTHING_RECORDED} (spec recorded, no claims)"

    parts: List[str] = []
    parts.append(
        f"{n_unresolved} unresolved claim{'s' if n_unresolved != 1 else ''}"
    )
    if prior_work_open:
        parts.append("prior-work open")
    if n_novelty:
        parts.append(f"{n_novelty} novelty unresolved")
    if n_awaiting:
        parts.append(
            f"{n_awaiting} checkpoint{'s' if n_awaiting != 1 else ''} awaiting verdict"
        )

    pending = n_unresolved or prior_work_open or n_novelty or n_awaiting
    if not pending:
        return f"{prefix} all recorded claims resolved; nothing pending"
    return f"{prefix} " + ", ".join(parts)


__all__ = [
    "StatusReport",
    "session_status",
    "render_status_text",
]
