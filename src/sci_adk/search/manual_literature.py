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

import re
from pathlib import Path
from typing import Optional

from sci_adk.search.citation_keys import _base_key

SI_SUFFIX = "_SI"


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
