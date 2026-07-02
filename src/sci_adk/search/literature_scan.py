"""
Watch-folder scan for user-provided PDFs (design/literature-acquisition.md).

The manual-ingest verb (``add-literature``) handles ONE known PDF. This module closes
the discovery half: point sci-adk at a folder the user drops papers into (default
``~/Downloads``, configurable), and it reports which PDFs are NOT yet in the run's
literature store -- the *new candidates* the agent then reads and ingests.

Design constraints (why a SCAN, not a watcher):
  * sci-adk's tool policy forbids a long-running background service, so this is a
    stateless SCAN run on demand (a CLI verb + skill wiring), never a daemon.
  * De-duplication is by CONTENT HASH, not filename: ``add-literature`` renames each PDF
    to its bibkey, so a filename match is impossible; but ``shutil.copy2`` preserves the
    bytes, so the stored copy's sha256 equals the source's. A watch-folder PDF whose
    sha256 already appears in ``literature/pdfs/`` is already ingested -> skipped. No
    ledger file is needed (the store IS the ledger).

Pure + deterministic + no LLM: it reads bytes and returns paths. The judgement of WHICH
candidates are real papers (and their author/year/SI) stays with the agent, exactly as
for ``add-literature`` -- this module only surfaces the un-ingested files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Sequence

# Read in chunks so a large PDF does not load wholesale into memory.
_CHUNK = 1 << 20  # 1 MiB


def file_sha256(path: Path) -> str:
    """The sha256 hex digest of a file's bytes (streamed)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_new_pdfs(
    pdfs_dir: Path,
    watch_dirs: Sequence[Path],
) -> List[Path]:
    """Return the watch-folder ``*.pdf`` files NOT already in ``pdfs_dir`` (by content).

    Args:
        pdfs_dir: the run's ``literature/pdfs/`` store (may not exist yet).
        watch_dirs: folders to scan for dropped PDFs (top-level ``*.pdf``, non-recursive;
            ``~`` is expanded). A missing dir is skipped gracefully.

    Returns:
        The un-ingested candidate PDFs, absolute, deterministically ordered (by watch-dir
        order then filename), each content deduplicated ONCE -- so the same paper dropped
        twice (or already in the store) is never reported as a duplicate candidate.
    """
    seen: set[str] = set()
    if pdfs_dir.is_dir():
        for p in sorted(pdfs_dir.glob("*.pdf")):
            seen.add(file_sha256(p))

    new: List[Path] = []
    for raw in watch_dirs:
        d = Path(raw).expanduser()
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.pdf")):
            if not p.is_file():
                continue
            digest = file_sha256(p)
            if digest in seen:
                continue
            seen.add(digest)  # dedup within + across watch dirs too
            new.append(p.resolve())
    return new


__all__ = ["file_sha256", "scan_new_pdfs"]
