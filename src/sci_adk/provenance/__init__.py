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

This module also carries the **spec digest** (design/sci-adk-as-moai.md §6.1) -- a
sha256 over the canonical Spec serialization ALONE (not the whole record). It backs the
spec-digest boundary guard: a worker's ``[FROZEN SPEC REFERENCE]`` block carries the
frozen Spec's digest, and a record-advancing verb (``append-evidence`` / ``derive-claim``)
compares the passed digest against ``spec.json`` on disk; a mismatch raises
:class:`SpecDigestMismatch` so the worker cannot silently advance past a Spec it
tampered with. It reuses the same canonicalization as ``record_digest`` (typed model,
sorted keys); the boundary check + flag wiring live in the CLI. (Per this module's
"resist a broad subsystem" note: just these two functions + the exception, nothing more.)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.pkgreqs import PackageReqs
from sci_adk.core.pubreqs import PubReqs
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


def spec_digest(spec: Spec) -> str:
    """Return a deterministic sha256 (hex) over the canonical serialization of ``spec``.

    Unlike :func:`record_digest` (which covers the whole audited surface), this hashes
    the **Spec alone** -- the frozen contract a worker carries in its
    ``[FROZEN SPEC REFERENCE]`` block (design/sci-adk-as-moai.md §6.1). It reuses the
    same canonicalization (the typed ``Spec`` model dumped with sorted keys) so the
    digest is invariant to cosmetic JSON differences (whitespace, key order) but changes
    on ANY Spec content edit -- including an amendment (version+1).

    Domain-general: it hashes only Spec fields; it knows nothing of any capability.

    Relationship to :func:`record_digest`: on a run with no evidence/verdicts yet,
    ``spec_digest(spec)`` equals ``record_digest(run_dir)`` (both fold only the Spec);
    they diverge the moment any Evidence is appended. The §6.1 boundary deliberately uses
    ``spec_digest`` -- it is STABLE under evidence appends (the frozen contract does not
    change when the record grows), whereas ``record_digest`` would shift on every append.
    Do NOT substitute one for the other.

    Args:
        spec: the frozen Spec to digest.

    Returns:
        The 64-char hex sha256 of the canonical Spec serialization.
    """
    hasher = hashlib.sha256()
    _absorb(hasher, "spec", spec.model_dump(mode="json"))
    return hasher.hexdigest()


def pubreqs_digest(pubreqs: PubReqs) -> str:
    """Return a deterministic sha256 (hex) over the canonical serialization of ``pubreqs``.

    The F1 publishing-requirements digest (design/paper-publishing-requirements.md §1.1):
    tamper-evidence over the FROZEN publishing contract, mirroring :func:`spec_digest`'s
    canonicalization (the typed ``PubReqs`` model dumped with sorted keys, so the digest is
    invariant to cosmetic JSON differences but changes on ANY gate-bearing edit -- a relaxed
    ``image_min_dpi`` or a dropped ``required_sections`` entry shifts it). Unlike the Spec
    (whose digest is computed on demand), the design STORES this digest in ``pubreqs.json``,
    so the freeze step records it once and the gate trusts the recorded contract.

    The ``digest`` field itself is EXCLUDED from the hash: a digest cannot cover the slot it
    is written into (that would be circular -- you could never store a stable value). The
    ``frozen_at`` timestamp is likewise excluded, so the digest is a function of the
    GATE-BEARING contract only (two freezes of the same requirements at different times share
    a digest, and a re-freeze that only bumps the timestamp does not falsely look "tampered").
    Every other field -- the ones that actually gate the paper -- is folded in.

    Domain-general: it hashes only PubReqs fields; it knows nothing of any capability.

    Args:
        pubreqs: the publishing-requirements contract to digest.

    Returns:
        The 64-char hex sha256 of the canonical gate-bearing PubReqs serialization.
    """
    hasher = hashlib.sha256()
    payload = pubreqs.model_dump(mode="json", exclude={"digest", "frozen_at"})
    _absorb(hasher, "pubreqs", payload)
    return hasher.hexdigest()


def pkgreqs_digest(pkgreqs: PackageReqs) -> str:
    """Return a deterministic sha256 (hex) over the canonical serialization of ``pkgreqs``.

    The workspace-level package digest (design/near-submission-package.md §2): tamper-evidence
    over the FROZEN package contract, mirroring :func:`pubreqs_digest`'s canonicalization (the
    typed ``PackageReqs`` model dumped with sorted keys, so the digest is invariant to cosmetic
    JSON differences but changes on ANY gate-bearing edit -- a relaxed ``abstract_max_words`` or
    a dropped ``required_sections`` entry shifts it). The design STORES this digest in
    ``pkgreqs.json``, so the freeze step records it once and the gate trusts the recorded
    contract.

    The ``digest`` field itself is EXCLUDED from the hash (a digest cannot cover the slot it is
    written into -- that would be circular). The ``frozen_at`` timestamp is likewise excluded,
    so the digest is a function of the GATE-BEARING contract only (two freezes of the same
    requirements at different times share a digest, and a re-freeze that only bumps the
    timestamp does not falsely look "tampered"). Every other field -- the ones that actually
    gate the package -- is folded in (``body_word_range`` and ``advisory`` included: though they
    are ADVISORY at gate time, they are still part of the frozen contract the digest attests).

    Domain-general: it hashes only PackageReqs fields; it knows nothing of any capability.

    Args:
        pkgreqs: the package-requirements contract to digest.

    Returns:
        The 64-char hex sha256 of the canonical gate-bearing PackageReqs serialization.
    """
    hasher = hashlib.sha256()
    payload = pkgreqs.model_dump(mode="json", exclude={"digest", "frozen_at"})
    _absorb(hasher, "pkgreqs", payload)
    return hasher.hexdigest()


def spec_digest_of_run(run_dir: Path) -> str:
    """Load ``run_dir/spec.json`` and return its :func:`spec_digest`.

    The on-disk side of the spec-digest boundary check: the verb recomputes this from
    the recorded Spec and compares it to the digest the worker passed.

    Args:
        run_dir: a ``runs/<spec.id>/`` directory.

    Returns:
        The 64-char hex sha256 of the recorded Spec.

    Raises:
        FileNotFoundError: if ``spec.json`` is absent (mirrors :func:`record_digest`).
        ValueError: if ``spec.json`` is malformed (named in the message).
    """
    run_dir = Path(run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"no spec.json to digest in run dir: {run_dir}")
    spec = Spec.model_validate(_load_json(spec_path))
    return spec_digest(spec)


class SpecDigestMismatch(Exception):
    """The passed Spec digest does not match the recorded ``spec.json`` (§6.1 boundary).

    Raised at a record-advancing verb (``append-evidence`` / ``derive-claim``) when the
    worker-supplied ``--spec-digest`` differs from the on-disk Spec's digest. The CLI
    catches it, prints a friendly stderr message, and exits 2, so the worker cannot
    advance past a Spec other than the one it was given.

    The message says what the passed value IS, as far as the caller could establish it,
    and claims a revision only when it applies:

      - ``passed_file_hash``: the value is the sha256 of the spec.json bytes (the obvious
        wrong value -- a 64-char sha256 too). The Spec is unchanged.
      - ``earlier_version``: the value is the Spec digest of a version saved in
        ``spec_history/`` -- the Spec WAS amended since that reference.
      - neither: the value is not the digest of any recorded version of this Spec. Nothing
        shows the Spec changed, so the message does not say it did.

    Which digest the flag takes, and where to read the current one (``sci-adk status``,
    as init-spec and amend-spec print it), is stated once.

    Attributes:
        spec_id: the run's Spec id.
        expected: the digest the worker passed (its frozen reference).
        actual: the digest recomputed from ``spec.json`` on disk.
        run_dir: the run dir named in the "where to get it" hint (``None`` -> a
            ``<run-dir>`` placeholder).
        passed_file_hash: True iff ``expected`` is the sha256 of the spec.json bytes.
        earlier_version: the ``spec_history/`` version whose Spec digest ``expected`` is,
            or ``None``.
        current_version: the version of the Spec on disk, or ``None`` when unknown.
    """

    def __init__(self, *, spec_id: str, expected: str, actual: str,
                 run_dir: "Path | str | None" = None,
                 passed_file_hash: bool = False,
                 earlier_version: Optional[int] = None,
                 current_version: Optional[int] = None) -> None:
        self.spec_id = spec_id
        self.expected = expected
        self.actual = actual
        self.run_dir = run_dir
        self.passed_file_hash = passed_file_hash
        self.earlier_version = earlier_version
        self.current_version = current_version
        status = f"`sci-adk status {run_dir if run_dir is not None else '<run-dir>'}`"
        current = f"v{current_version}" if current_version is not None else ""
        takes = "--spec-digest takes the Spec digest (sha256 over the canonical Spec content)"
        if passed_file_hash:
            what = ("the value passed is the sha256 of the spec.json file; the Spec itself "
                    f"is unchanged. {takes}")
        elif earlier_version is not None:
            what = ("the value passed is the digest of an earlier Spec version "
                    f"(v{earlier_version}, kept as spec_history/spec.v{earlier_version}.json); "
                    f"the Spec has been amended since and is now {current or 'a later version'}. "
                    "Read the amended Spec before recording under it")
        else:
            if current_version is not None and current_version > 1:
                versions = f" ({current}) nor of an earlier version kept in spec_history/"
            else:
                versions = f" ({current})" if current else ""
            what = (f"the value passed is not the digest of this Spec{versions}. {takes}, "
                    "not the sha256 of the spec.json file")
        # Truncate the 64-char hashes for a readable one-line message; the full values
        # stay on the attributes for callers that need them.
        super().__init__(
            f"spec-digest mismatch for '{spec_id}': "
            f"passed {expected[:12]}... != recorded {actual[:12]}...: {what}; "
            f"{status} prints the current Spec digest on its spec_digest: line, as "
            "init-spec and amend-spec do at freeze"
        )


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


__all__ = [
    "record_digest",
    "spec_digest",
    "pubreqs_digest",
    "pkgreqs_digest",
    "spec_digest_of_run",
    "SpecDigestMismatch",
]
