"""
Spec amendment with a human-approved *checkpoint receipt* (design/sci-adk-as-moai.md
§4.6, Invariant S5).

The kernel already owns the amendment *semantics*: :meth:`Spec.amend` bumps the version
(+1), requires a non-empty rationale, and links the prior version (S1/S5). What was
missing was the persisted, auditable *record* that a human-checkpointed amendment
happened. This module adds exactly that -- no new amendment semantics:

  1. read the recorded ``spec.json`` for a run;
  2. apply :meth:`Spec.amend(rationale=...)` (the existing S5 method);
  3. write the new ``spec.json`` (the new frozen version);
  4. record an :class:`AmendmentReceipt` to ``checkpoints/amendment-v<N>.json`` -- a small
     typed artifact stating prior version + rationale + new version + when.

The receipt is a *recording-type* checkpoint, the same family as the prior-work checkpoint
(loop/verdict.py): a typed JSON contract that documents a decision. It carries no verdict
trail (it is a decision record, not a belief) and lives in the run's ``checkpoints/`` dir
alongside ``prior_work.json`` -- distinguishable by its versioned filename and its own
schema. No LLM, no network: this is deterministic record-keeping.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from sci_adk.core.spec import Spec


class AmendmentReceipt(BaseModel):
    """Typed contract behind ``checkpoints/amendment-v<N>.json`` -- the amendment record.

    A recording-type receipt that an S5 human-checkpointed Spec amendment occurred. It
    documents the move from one frozen Spec version to the next together with the required
    rationale, so the amendment is auditable from the record alone (anti silent-edit). It
    carries no verdict trail (it records a decision, not a belief).

    Attributes:
        spec_id: the Spec this amendment is for (stable across versions).
        prior_version: the version that was amended (the ``from`` version).
        new_version: the version produced by the amendment (= ``prior_version + 1``).
        rationale: the required non-empty amendment rationale (S5).
        recorded_at: ISO-8601 UTC timestamp the receipt was written.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    spec_id: str = Field(..., min_length=1, description="Spec id this amendment is for")
    prior_version: int = Field(..., ge=1, description="Version that was amended")
    new_version: int = Field(..., ge=2, description="Version produced (prior + 1)")
    rationale: str = Field(..., min_length=1, description="Required amendment rationale (S5)")
    recorded_at: str = Field(..., min_length=1, description="ISO-8601 UTC receipt timestamp")


def amend_spec(
    run_dir: Path,
    *,
    rationale: str,
    spec: Optional[Spec] = None,
) -> tuple[Spec, AmendmentReceipt]:
    """Amend the run's recorded Spec and record a human-approved checkpoint receipt.

    Reads ``run_dir/spec.json`` (unless ``spec`` is supplied), applies the existing
    :meth:`Spec.amend` (version+1, S5 non-empty-rationale enforcement), overwrites
    ``spec.json`` with the new frozen version, and writes an :class:`AmendmentReceipt` to
    ``run_dir/checkpoints/amendment-v<new_version>.json``.

    No new amendment semantics are introduced -- the bump/link/freeze rules are entirely
    :meth:`Spec.amend`'s; this function only persists the result and the receipt. No LLM,
    no network.

    Args:
        run_dir: an existing ``runs/<spec.id>/`` directory holding ``spec.json``.
        rationale: the required amendment rationale (S5). An empty/blank rationale is
            refused by :meth:`Spec.amend` with a clear ``ValueError``.
        spec: optionally the in-memory Spec to amend (skips the ``spec.json`` read); the
            CLI verb omits it and reads from disk.

    Returns:
        ``(new_spec, receipt)`` -- the amended frozen Spec and the persisted receipt.

    Raises:
        FileNotFoundError: if ``spec`` is not supplied and ``spec.json`` is absent.
        ValueError: if ``rationale`` is empty/blank (re-raised from :meth:`Spec.amend`).
    """
    run_dir = Path(run_dir)
    if spec is None:
        spec_path = run_dir / "spec.json"
        if not spec_path.exists():
            raise FileNotFoundError(f"no spec.json found in run dir: {run_dir}")
        spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))

    prior_version = spec.version
    # The existing S5 method owns ALL amendment semantics (version+1, non-empty rationale,
    # prior-version link). A blank rationale raises ValueError here -- surfaced unchanged.
    new_spec = spec.amend(rationale=rationale)

    # Overwrite spec.json with the new frozen version (same id, version+1). The on-disk
    # spec is now the amended contract; the prior version is recoverable from the receipt
    # + the amended Spec's prior_version_id link.
    (run_dir / "spec.json").write_text(
        json.dumps(new_spec.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    receipt = AmendmentReceipt(
        spec_id=new_spec.id,
        prior_version=prior_version,
        new_version=new_spec.version,
        rationale=rationale.strip(),
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    cp_dir = run_dir / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    (cp_dir / f"amendment-v{new_spec.version}.json").write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return new_spec, receipt


__all__ = ["AmendmentReceipt", "amend_spec"]
