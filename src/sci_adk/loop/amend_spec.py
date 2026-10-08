"""
Spec amendment with a human-approved *checkpoint receipt* (design/sci-adk-as-moai.md
§4.6, Invariant S5).

The kernel already owns the amendment *semantics*: :meth:`Spec.amend` bumps the version
(+1), requires a non-empty rationale, and links the prior version (S1/S5). This module
persists an amendment -- no new amendment semantics:

  1. read the recorded ``spec.json`` for a run;
  2. apply :meth:`Spec.amend` -- rationale only, or with the new content
     (``raw_proposal`` / ``hypotheses`` / ``method`` / ``target_claims``) taken from a
     proposed Spec;
  3. save the current frozen ``spec.json`` byte-for-byte to
     ``spec_history/spec.v<version>.json`` (the pre-registration as originally committed
     is kept; a history file is never overwritten);
  4. write the new ``spec.json`` (the new frozen version);
  5. record an :class:`AmendmentReceipt` to ``checkpoints/amendment-v<N>.json`` -- a small
     typed artifact stating prior version + rationale + new version + when + the sha256 of
     the saved prior version.

The receipt is a *recording-type* checkpoint, the same family as the prior-work checkpoint
(loop/verdict.py): a typed JSON contract that documents a decision. It carries no verdict
trail (it is a decision record, not a belief) and lives in the run's ``checkpoints/`` dir
alongside ``prior_work.json`` -- distinguishable by its versioned filename and its own
schema. No LLM, no network: this is deterministic record-keeping.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from sci_adk.core.spec import Spec

#: The Spec fields an amendment may change; everything else is owned by Spec.amend.
CONTENT_FIELDS = ("raw_proposal", "hypotheses", "method", "target_claims")

#: Directory (inside ``runs/<id>/``) holding every superseded frozen Spec version.
HISTORY_DIR = "spec_history"


class AmendmentRefused(ValueError):
    """An amendment that cannot be recorded as asked; nothing has been written."""


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
        prior_spec_sha256: sha256 (hex) of ``spec_history/spec.v<prior_version>.json``,
            the prior frozen Spec's exact bytes. ``None`` on receipts written before the
            history was kept.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    spec_id: str = Field(..., min_length=1, description="Spec id this amendment is for")
    prior_version: int = Field(..., ge=1, description="Version that was amended")
    new_version: int = Field(..., ge=2, description="Version produced (prior + 1)")
    rationale: str = Field(..., min_length=1, description="Required amendment rationale (S5)")
    recorded_at: str = Field(..., min_length=1, description="ISO-8601 UTC receipt timestamp")
    prior_spec_sha256: Optional[str] = Field(
        default=None, description="sha256 of the saved prior frozen spec.json bytes"
    )


def history_path(run_dir: Path, version: int) -> Path:
    """Where frozen Spec ``version`` of the run is kept once it has been amended."""
    return Path(run_dir) / HISTORY_DIR / f"spec.v{version}.json"


def content_changes(old: Spec, new: Spec) -> List[str]:
    """JSON paths of the content fields that differ between two Spec versions.

    List elements carrying an ``id`` (hypotheses, target claims) are matched by id and
    shown as ``hypotheses[<id>]``; other lists by index. Added / removed elements are
    marked as such. An empty list means the content is identical.
    """
    out: List[str] = []
    for name in CONTENT_FIELDS:
        _diff(
            old.model_dump(mode="json")[name], new.model_dump(mode="json")[name], name, out
        )
    return out


def _diff(old: Any, new: Any, path: str, out: List[str]) -> None:
    if old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict):
        for key in list(old) + [k for k in new if k not in old]:
            sub = f"{path}.{key}"
            if key not in new:
                out.append(f"{sub}: removed")
            elif key not in old:
                out.append(f"{sub}: added")
            else:
                _diff(old[key], new[key], sub, out)
        return
    if isinstance(old, list) and isinstance(new, list):
        if _all_have_ids(old) and _all_have_ids(new):
            old_by = {e["id"]: e for e in old}
            new_by = {e["id"]: e for e in new}
            for key in list(old_by) + [k for k in new_by if k not in old_by]:
                sub = f"{path}[{key}]"
                if key not in new_by:
                    out.append(f"{sub}: removed")
                elif key not in old_by:
                    out.append(f"{sub}: added")
                else:
                    _diff(old_by[key], new_by[key], sub, out)
            if [e["id"] for e in old] != [e["id"] for e in new] and set(old_by) == set(new_by):
                out.append(f"{path}: reordered")
            return
        for i in range(max(len(old), len(new))):
            sub = f"{path}[{i}]"
            if i >= len(new):
                out.append(f"{sub}: removed")
            elif i >= len(old):
                out.append(f"{sub}: added")
            else:
                _diff(old[i], new[i], sub, out)
        return
    out.append(f"{path}: changed")


def _all_have_ids(items: list) -> bool:
    return bool(items) and all(isinstance(e, dict) and "id" in e for e in items)


def _check_proposed(current: Spec, proposed: Spec, rationale: str) -> None:
    """Refuse a proposed Spec that does not describe ``current``'s next version."""
    if proposed.id != current.id:
        raise AmendmentRefused(
            f"the proposed Spec's id '{proposed.id}' is not this run's Spec id "
            f"'{current.id}'"
        )
    given = proposed.model_fields_set
    if "version" in given and proposed.version != current.version + 1:
        raise AmendmentRefused(
            f"the proposed Spec says version {proposed.version}, but amending "
            f"v{current.version} produces version {current.version + 1}"
        )
    if (
        "amendment_rationale" in given
        and proposed.amendment_rationale is not None
        and proposed.amendment_rationale.strip() != rationale.strip()
    ):
        raise AmendmentRefused(
            "the proposed Spec's amendment_rationale differs from --rationale; they must "
            "be the same text"
        )
    if not content_changes(current, proposed):
        raise AmendmentRefused(
            f"nothing to amend: the proposed content is identical to frozen "
            f"v{current.version}"
        )


def amend_spec(
    run_dir: Path,
    *,
    rationale: str,
    spec: Optional[Spec] = None,
    proposed: Optional[Spec] = None,
) -> tuple[Spec, AmendmentReceipt]:
    """Amend the run's recorded Spec and record a human-approved checkpoint receipt.

    Reads ``run_dir/spec.json`` (unless ``spec`` is supplied) and applies the existing
    :meth:`Spec.amend` (version+1, S5 non-empty-rationale enforcement). With ``proposed``
    the content fields (``raw_proposal`` / ``hypotheses`` / ``method`` /
    ``target_claims``) are taken from it; without it the content is kept and only the
    version and rationale change. The current ``spec.json`` is saved byte-for-byte to
    ``spec_history/spec.v<version>.json`` before the new version is written, and an
    :class:`AmendmentReceipt` (with that file's sha256) goes to
    ``checkpoints/amendment-v<new_version>.json``.

    Every check runs before anything is written. No LLM, no network.

    Args:
        run_dir: an existing ``runs/<spec.id>/`` directory holding ``spec.json``.
        rationale: the required amendment rationale (S5).
        spec: optionally the in-memory Spec to amend (skips the ``spec.json`` read).
        proposed: optionally the full Spec of the new version. Its ``id`` must equal the
            current id; a ``version`` it sets explicitly must be current+1; an
            ``amendment_rationale`` it sets must equal ``rationale`` (after strip); its
            content must differ from the current content. Its ``created_at`` and
            ``prior_version_id`` are not used (``Spec.amend`` sets them).

    Returns:
        ``(new_spec, receipt)`` -- the amended frozen Spec and the persisted receipt.

    Raises:
        FileNotFoundError: if ``spec`` is not supplied and ``spec.json`` is absent.
        AmendmentRefused: a ``proposed`` Spec that fails a check above, or a history file
            for the current version that already exists with different bytes.
        ValueError: if ``rationale`` is empty/blank (re-raised from :meth:`Spec.amend`).
    """
    run_dir = Path(run_dir)
    spec_path = run_dir / "spec.json"
    if spec is None:
        if not spec_path.exists():
            raise FileNotFoundError(f"no spec.json found in run dir: {run_dir}")
        spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))

    if not rationale or not rationale.strip():
        raise ValueError("Amendment requires non-empty rationale")
    if proposed is not None:
        _check_proposed(spec, proposed, rationale)

    prior_version = spec.version
    # The existing S5 method owns ALL amendment semantics (version+1, non-empty rationale,
    # prior-version link, created_at).
    content = (
        {name: getattr(proposed, name) for name in CONTENT_FIELDS}
        if proposed is not None else {}
    )
    new_spec = spec.amend(rationale=rationale, **content)

    # The frozen bytes being superseded. When the caller supplied the Spec in memory and
    # nothing is on disk yet, its serialization is what was frozen.
    prior_bytes = (
        spec_path.read_bytes() if spec_path.exists()
        else json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False)
        .encode("utf-8")
    )
    hist = history_path(run_dir, prior_version)
    if hist.exists() and hist.read_bytes() != prior_bytes:
        raise AmendmentRefused(
            f"{hist} already exists with different content than the current spec.json "
            f"(v{prior_version}); a saved frozen version is never overwritten"
        )

    # @MX:WARN: [AUTO] Writes the superseded frozen Spec into spec_history/ before
    #   spec.json is replaced; this file is the only copy of what was pre-registered.
    # @MX:REASON: Pre-registration must keep what was originally committed to -- never
    #   overwrite an existing history file, and never write spec.json before this succeeds.
    hist.parent.mkdir(parents=True, exist_ok=True)
    if not hist.exists():
        hist.write_bytes(prior_bytes)

    # The on-disk spec is now the amended contract; every prior version is in
    # spec_history/, its sha256 in the receipt.
    spec_path.write_text(
        json.dumps(new_spec.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    receipt = AmendmentReceipt(
        spec_id=new_spec.id,
        prior_version=prior_version,
        new_version=new_spec.version,
        rationale=rationale.strip(),
        recorded_at=datetime.now(timezone.utc).isoformat(),
        prior_spec_sha256=hashlib.sha256(prior_bytes).hexdigest(),
    )
    cp_dir = run_dir / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    (cp_dir / f"amendment-v{new_spec.version}.json").write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return new_spec, receipt


__all__ = [
    "AmendmentReceipt",
    "AmendmentRefused",
    "CONTENT_FIELDS",
    "HISTORY_DIR",
    "amend_spec",
    "content_changes",
    "history_path",
]
