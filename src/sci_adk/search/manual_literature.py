"""Manual literature ingest -- bibkey naming for user-provided PDFs.

When paperforge cannot fetch a paper (no Open-Access copy, or the user simply has
the PDF in hand), the user provides it directly. This module assigns sci-adk's
canonical citation-key STEM to such a manually-provided PDF, so the caller can save
it as ``<literature_dir>/pdfs/<stem>.pdf``.

Naming (design/literature-acquisition.md, manual path):
  * base key = ``<NormalizedSurname><Year>`` -- reuses citation_keys' surname
    normalization + Anon/nd fallbacks (an institutional author like "OECD" keys as
    ``OECD2012``);
  * a manually-ingested PDF has no DOI yet, so same-base collisions are
    disambiguated by ARRIVAL ORDER with an UPPERCASE suffix -- the first is bare
    (``Niimi1986``), the next ``Niimi1986A``, then ``Niimi1986B`` (provisional).
    Render-time normalization (Part B, elsewhere) later re-sorts these to the
    canonical lowercase ``a/b/c`` by DOI order;
  * supplementary information is a variant of its paper's key with a ``_SI`` suffix
    (``Niimi1986_SI``); SI files disambiguate among SI files ONLY, so a paper and
    its SI coexist without forcing a suffix on either.

Deterministic, no LLM, no new dependency (reuses citation_keys). The caller (the
``add-literature`` CLI verb, driven by the agent) supplies author + year + is_si,
having read the document.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

from sci_adk.search.citation_keys import _BIB_DOI_RE, _BIB_ENTRY_RE, _base_key

SI_SUFFIX = "_SI"

# Prefixes stripped from a DOI before comparison (the same set paperforge's
# ``normalize_doi`` strips when it writes manifest.csv / references.bib).
_DOI_PREFIXES = (
    "https://doi.org/", "http://doi.org/",
    "https://dx.doi.org/", "http://dx.doi.org/",
    "doi:", "doi ",
)
_DOI_TRAILING = ".,;)]}>\"' \t\r\n"

# manifest.csv ``source`` value marking a PDF the user supplied (not an OA source).
MANUAL_SOURCE = "manual"


def normalize_doi(raw: Optional[str]) -> str:
    """Return the comparison form of a DOI: prefix-free, trimmed, case-folded.

    DOIs are case-insensitive; ``https://doi.org/``, ``dx.doi.org`` and ``doi:``
    prefixes are dropped, as are trailing punctuation and whitespace.
    """
    doi = (raw or "").strip()
    low = doi.lower()
    for prefix in _DOI_PREFIXES:
        if low.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi.strip().strip(_DOI_TRAILING).lower()


# @MX:NOTE: [AUTO] DOI -> citation key comes from references.bib, not manifest.csv:
# the acquirer writes a bib entry for EVERY DOI, but manifest ``filename`` is empty
# for a DOI whose PDF was not fetched, and sci-adk never re-keys such an entry. The
# bib key is therefore the only record of that DOI's key; reuse it verbatim.
def find_recorded_key(literature_dir: Path, doi: str) -> Optional[str]:
    """Return the citation key of the ``references.bib`` entry whose DOI is ``doi``.

    Matching uses :func:`normalize_doi` on both sides. Returns ``None`` when the bib
    file is absent or no entry carries the DOI. Raises ``ValueError`` when two
    entries with DIFFERENT keys carry the same DOI (the binding would be a guess).
    """
    bib = Path(literature_dir) / "references.bib"
    if not bib.exists():
        return None
    target = normalize_doi(doi)
    keys: list[str] = []
    for m in _BIB_ENTRY_RE.finditer(bib.read_text(encoding="utf-8")):
        _head, key, body, _tail = m.groups()
        doi_match = _BIB_DOI_RE.search(body)
        if doi_match and normalize_doi(doi_match.group(1)) == target and key not in keys:
            keys.append(key)
    if len(keys) > 1:
        raise ValueError(
            f"DOI {doi} appears under more than one references.bib key: {', '.join(keys)}"
        )
    return keys[0] if keys else None


def mark_manifest_pdf_present(literature_dir: Path, doi: str, filename: str) -> bool:
    """Record in manifest.csv that ``doi``'s PDF is now on disk as ``filename``.

    Sets ``status=success`` (so a resumed acquisition skips the DOI instead of
    re-fetching it), ``source=manual``, ``filename``, and clears ``error``. Every
    other column and every other row is preserved, in the original column order.
    Returns False (nothing written) when the manifest or the DOI's row is absent.
    """
    manifest = Path(literature_dir) / "manifest.csv"
    if not manifest.exists():
        return False
    with open(manifest, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    target = normalize_doi(doi)
    hit = False
    for row in rows:
        if normalize_doi(row.get("doi")) == target:
            row.update(status="success", source=MANUAL_SOURCE, filename=filename, error="")
            hit = True
    if not hit:
        return False
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return True


def _upper_suffix(index: int) -> str:
    """0 -> 'A', 1 -> 'B', ... 25 -> 'Z', 26 -> 'AA' (bijective base-26, uppercase).

    The uppercase twin of ``citation_keys._suffix``: uppercase marks a *provisional*
    arrival-order key (DOI unknown), visibly distinct from the canonical lowercase
    ``a/b`` that render-time normalization assigns by DOI order.
    """
    letters = ""
    n = index + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def assign_manual_key(
    pdfs_dir: Path,
    author: Optional[str],
    year: Optional[str],
    *,
    is_si: bool = False,
) -> str:
    """Return the citation-key STEM for a manually-provided PDF.

    Disambiguates by arrival order against the PDFs already in ``pdfs_dir`` that
    share this base key AND SI-ness: the first is bare, later ones get ``A``, ``B``,
    … The ``_SI`` marker (supplementary information) is appended after any
    disambiguation suffix and is counted separately from non-SI files, so a paper
    and its SI never force a suffix on each other.

    Args:
        pdfs_dir: the run's ``literature/pdfs/`` directory (may not exist yet).
        author: first-author surname or institutional name; None/empty -> ``Anon``.
        year: publication year; None/empty -> ``nd``.
        is_si: True if this file is supplementary information.

    Returns:
        The on-disk stem WITHOUT extension (e.g. ``Niimi1986``, ``Niimi1986A``,
        ``Niimi1986_SI``).
    """
    base = _base_key(author, year)
    # Count existing files of the SAME class (SI vs non-SI) sharing this base.
    #   non-SI stem: <base>[A-Z]*        (year ends in a digit/nd, suffix is letters)
    #   SI stem:     <base>[A-Z]*_SI
    if is_si:
        pat = re.compile(rf"^{re.escape(base)}[A-Z]*{re.escape(SI_SUFFIX)}$")
    else:
        pat = re.compile(rf"^{re.escape(base)}[A-Z]*$")

    existing = 0
    if pdfs_dir.exists():
        for p in pdfs_dir.glob("*.pdf"):
            if pat.match(p.stem):
                existing += 1

    suffix = "" if existing == 0 else _upper_suffix(existing - 1)
    stem = f"{base}{suffix}"
    return f"{stem}{SI_SUFFIX}" if is_si else stem
