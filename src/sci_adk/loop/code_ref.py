"""
How a recorded ``provenance.code_ref`` resolves to generating code (F3 reproduction bundle).

A ``code_ref`` is text written by whoever recorded the Evidence. The reproduction bundle
(design/paper-publishing-requirements.md §3) can only re-run code it holds, so the compiler
(which ships scripts into ``paper/code/`` and drives them from ``paper/reproduce.py``) and
``verify`` (which gates that bundle) must read a ``code_ref`` the SAME way. This module is
that one reading:

  1. The WHOLE ``code_ref``, taken as a path, names an existing file -> that file is the
     script. (The original rule; it keeps a path that contains spaces working.)
  2. Otherwise the LEADING whitespace-delimited token (one trailing ``;`` or ``,`` dropped)
     is the path, optionally followed by ``sha256=<64 hex>``. Everything after that is free
     text and is ignored -- a second script named in it is NOT followed.
       - the token names no existing file -> a POINTER (a bare commit hash, a decision ref
         such as ``prior_work:searched``, an unresolvable name), exactly as before;
       - it names a file and no hash follows -> the script;
       - a hash follows and the file's sha256 matches it -> the script;
       - a hash follows and does NOT match -> a POINTER, with the mismatch reported: the
         file on disk is not the code the record names, so it is never shipped as if it
         were.

A relative path is looked up under the run dir first, then the workspace; an absolute path
is taken as-is. Read-only and deterministic: it stats and hashes files, never writes, runs
nothing, and calls no LLM.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ``sha256=`` + exactly 64 hex digits, not followed by another hex digit (so a longer run
# is not mistaken for a hash). Matched only at the START of the text after the path token.
_SHA256_AFTER_PATH = re.compile(r"sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])")


@dataclass(frozen=True)
class CodeRefResolution:
    """What one ``code_ref`` resolves to.

    Attributes:
        script: the file to ship and drive as the recorded generating code, or ``None``
            (the ``code_ref`` is a POINTER).
        named_path: the path token as recorded, when it names an existing file.
        expected_sha256: the hash the ``code_ref`` records for that file, if any.
        actual_sha256: the sha256 of that file on disk now (set when a hash was recorded).
    """

    script: Optional[Path] = None
    named_path: Optional[str] = None
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None

    @property
    def hash_mismatch(self) -> bool:
        """True when the named file exists but does not hash to the recorded sha256."""
        return (
            self.expected_sha256 is not None
            and self.actual_sha256 is not None
            and self.expected_sha256 != self.actual_sha256
        )


def parse_code_ref(code_ref: str) -> tuple[str, Optional[str]]:
    """Split ``code_ref`` into ``(leading path token, sha256 or None)``. PURE.

    The token is the first whitespace-delimited word with one trailing ``;`` or ``,``
    removed. The hash is taken only when ``sha256=<64 hex>`` is the very next word (also
    when the token ended in ``;``); it is returned lower-cased. Anything else -- a hash of a
    different length, a hash further along the text -- is free text, so ``(token, None)``.
    """
    parts = code_ref.strip().split(None, 1)
    if not parts:
        return "", None
    token = parts[0]
    if token[-1] in ";,":
        token = token[:-1]
    rest = parts[1] if len(parts) > 1 else ""
    match = _SHA256_AFTER_PATH.match(rest)
    return token, (match.group(1).lower() if match else None)


# @MX:ANCHOR: [AUTO] the single reading of a code_ref: the compiler ships/drives what this
#   returns as a script, and verify's F3 gate + pointer-only advisory judge the same answer.
# @MX:REASON: [AUTO] fan_in 3 (compiler._resolve_repro_listings, verify
#   _reproduction_bundle_problems, verify _reproduction_advisory). If the compiler and verify
#   read a code_ref differently, the gate would judge a bundle the render never produced.
def resolve_code_ref(code_ref: str, run_dir: Path, workspace_dir: Path) -> CodeRefResolution:
    """Resolve ``code_ref`` to the recorded script, or to a POINTER (see the module docs).

    Never raises for an odd ``code_ref``: free text that cannot be a path (a NUL byte, a
    name longer than the filesystem allows) is simply not a file, and an unreadable file
    cannot be hashed, so both are POINTERS.
    """
    ref = code_ref.strip()
    if not ref:
        return CodeRefResolution()
    whole = _existing_file(ref, run_dir, workspace_dir)
    if whole is not None:
        return CodeRefResolution(script=whole)

    token, expected = parse_code_ref(ref)
    named = _existing_file(token, run_dir, workspace_dir) if token else None
    if named is None:
        return CodeRefResolution()
    if expected is None:
        return CodeRefResolution(script=named, named_path=token)
    actual = _sha256_of(named)
    if actual is None:
        return CodeRefResolution()
    return CodeRefResolution(
        script=named if actual == expected else None,
        named_path=token,
        expected_sha256=expected,
        actual_sha256=actual,
    )


def describe_mismatch(evidence_id: str, resolution: CodeRefResolution) -> str:
    """One line naming a hash mismatch: the Evidence id, the file, and both hashes."""
    return (
        f"{evidence_id}: code_ref names {resolution.named_path} with "
        f"sha256={resolution.expected_sha256}, but that file now hashes to "
        f"{resolution.actual_sha256}"
    )


def _existing_file(ref: str, run_dir: Path, workspace_dir: Path) -> Optional[Path]:
    candidate = Path(ref)
    roots = (
        [candidate]
        if candidate.is_absolute()
        else [Path(run_dir) / candidate, Path(workspace_dir) / candidate]
    )
    for path in roots:
        # os.path.isfile, not Path.is_file: it answers False instead of raising for a name
        # the OS rejects (ENAMETOOLONG, an embedded NUL), which free text can produce.
        if os.path.isfile(path):
            return path
    return None


def _sha256_of(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


__all__ = [
    "CodeRefResolution",
    "describe_mismatch",
    "parse_code_ref",
    "resolve_code_ref",
]
