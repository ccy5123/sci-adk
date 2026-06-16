"""
Minimal provenance primitive for the headless audit (``sci-adk verify``).

design/rigor-shell-architecture.md §8 F6: ``verify`` re-derives belief from the
*recorded* run so a third party can audit it without Claude Code. This module adds
the one companion primitive that audit needs -- a deterministic **record digest** --
and nothing more (a broad provenance subsystem is out of scope; resist it).

``record_digest(run_dir)`` is a sha256 (hex) over a CANONICAL serialization of the
three recorded artifacts the verifier trusts as given:

    spec.json  +  sorted evidence/*.json  +  sorted verdicts/*.json

The verdict trails are included on purpose: ``verify`` re-reads them as the record of
the non-numeric judgment (it does not re-judge), so trail tampering must change the
digest. The digest is the tamper-evidence companion to ``verify`` -- a third party
compares it to a trusted/published baseline; equal digest + an all-reproduced verify
report == the published belief follows from the published record.

Canonicalization goes THROUGH the typed core/loop models (``Spec`` / ``EvidenceItem``
/ ``VerdictTrail``), not the raw bytes on disk: re-serializing each artifact with
sorted keys makes the digest invariant to cosmetic JSON differences (whitespace, key
order) while still sensitive to any content change. Files are folded in a fixed order
(spec, then evidence by filename, then verdicts by filename) so the digest is
deterministic.

``claims/*.json`` is DELIBERATELY EXCLUDED: Claims are derived OUTPUTS that ``verify``
re-derives from the record (spec + evidence + verdict trails). Digesting them would be
circular -- it would pin the very belief the audit independently reconstructs, so a
tampered claim could pass by also matching a tampered digest. The digest covers only
the INPUTS to belief; ``verify`` then checks that the recorded Claims follow from
those inputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List

from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Spec
from sci_adk.loop.verdict import VerdictTrail


def record_digest(run_dir: Path) -> str:
    """Return a deterministic sha256 (hex) over the recorded run's audited surface.

    Covers ``spec.json`` + every ``evidence/*.json`` + every ``verdicts/*.json``,
    canonicalized via their typed models (sorted keys) so the digest is invariant to
    cosmetic JSON formatting but changes on any content edit -- including a tampered
    verdict trail (which ``verify`` trusts as the record of judgment).

    Args:
        run_dir: a ``runs/<spec.id>/`` directory.

    Returns:
        The 64-char hex sha256 of the canonical record.

    Raises:
        FileNotFoundError: if ``spec.json`` is absent (no record to digest).
        ValueError: if a recorded artifact is malformed (named in the message).
    """
    run_dir = Path(run_dir)
    hasher = hashlib.sha256()

    # spec.json -- required: a run with no Spec has no record to digest.
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"no spec.json to digest in run dir: {run_dir}")
    spec = Spec.model_validate(_load_json(spec_path))
    _absorb(hasher, "spec", spec.model_dump(mode="json"))

    # evidence/*.json and verdicts/*.json, each sorted by filename for determinism.
    # NOTE: claims/*.json is intentionally NOT digested -- Claims are derived outputs
    # verify re-derives, so including them would be circular (see module docstring).
    for path in _sorted_json(run_dir / "evidence"):
        item = _validate(EvidenceItem, path)
        _absorb(hasher, f"evidence:{path.name}", item.model_dump(mode="json"))
    for path in _sorted_json(run_dir / "verdicts"):
        trail = _validate(VerdictTrail, path)
        _absorb(hasher, f"verdict:{path.name}", trail.model_dump(mode="json"))

    return hasher.hexdigest()


# -- internals ---------------------------------------------------------------

def _sorted_json(directory: Path) -> List[Path]:
    """Every ``*.json`` in ``directory`` (if it exists), sorted by filename."""
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON in {path}: {e}") from e


def _validate(model, path: Path):
    """Parse + validate a recorded artifact, re-raising as a file-naming ValueError."""
    from pydantic import ValidationError

    try:
        return model.model_validate(_load_json(path))
    except ValidationError as e:
        raise ValueError(f"malformed record file {path}: {e}") from e


def _absorb(hasher, label: str, payload: dict) -> None:
    """Fold a labelled, canonically-serialized payload into the running digest.

    ``hasher`` is a live ``hashlib`` object (updated in place). The label keeps
    artifacts of different kinds (or same-named files in different dirs) from
    colliding; ``sort_keys=True`` makes the serialization canonical so the digest
    ignores on-disk key order / whitespace. The ``\\0`` separators keep field
    boundaries unambiguous (no concatenation collision).
    """
    hasher.update(label.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    hasher.update(b"\0")


__all__ = ["record_digest"]
