"""
sci-adk's citation-key naming convention for acquired Open-Access PDFs.

paperforge (the external pinned acquisition tool) now emits its own
``<FirstAuthorSurname><Year>[a/b]`` filenames, but its a/b suffixes follow
*paperforge's acquisition order*, which need not match sci-adk's. sci-adk OWNS
the *canonical* convention and re-keys deterministically as a *post-acquisition*
step (paperforge is never modified):

  * key = ``<NormalizedSurname><Year>`` (e.g. ``McKay2013``, ``Joe2026``);
  * when >= 2 acquired papers share the same base key, an ``a/b/c…`` suffix is
    appended, ordered by **DOI ascending** -- so the assignment is deterministic
    and stable across runs, independent of acquisition order
    (``Jager1998a`` for the lower DOI, ``Jager1998b`` for the higher). Because
    paperforge's own a/b order may differ from this DOI order, the DOI -> key
    mapping can be a swap or cycle, so it is applied as a **swap/cycle-safe batch
    rename** (a one-pass rename would clobber a not-yet-moved file);
  * fallbacks: a missing/empty author -> ``Anon``; a missing/empty year -> ``nd``
    (``Anon2026``, ``McKaynd``, ``Anonnd``); fallback keys disambiguate the same
    way;
  * the key is applied **consistently to every artifact**: the PDF stem, its
    ``.json`` sidecar stem, the ``references.bib`` entry key, and the
    ``manifest.csv`` filename column. The citation key == PDF stem == .bib key.

Honest record (sci-adk records what happened): the DOI -> key mapping is returned
so the caller can record it in the LITERATURE EvidenceItem, and an
**overwrite collision** -- two distinct DOIs that resolved to the SAME on-disk
file (paperforge overwrote a same-name collision before sci-adk saw it) -- is
*detected and surfaced* (never silently dropped).

This module is acquisition/IO + naming only. It does NOT touch the PDF security
boundary (``pdf_normalize``), the evidence-validity gate (``core/validity.py``,
claim updating, data_source/referent), or the kernel core. It uses no LLM and adds
no third-party dependency: surname normalization is stdlib ``unicodedata``
(no ``unidecode``) and the ``.bib`` key rewrite is line-based (no ``bibtexparser``).

Reference: src/sci_adk/loop/literature_acquirer.py (caller),
src/sci_adk/search/paperforge_adapter.py (AcquisitionRecord), design/tool-policy.md.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional, Sequence

from pydantic import BaseModel, Field

from sci_adk.search.paperforge_adapter import AcquisitionRecord, _MANIFEST_FIELDS

# Fallback tokens (kept module-level so callers/tests share the exact strings).
ANON = "Anon"   # first-author surname missing/empty
NO_DATE = "nd"  # year missing/empty

# Upper bound on a NORMALIZED surname's length. A pathological author string
# (hundreds of chars) would otherwise become a filename component near/over the
# ~255-byte filesystem limit and make the PDF/sidecar ``rename`` raise
# ENAMETOOLONG. We deterministically slice the surname to this cap; the trailing
# ``<year>`` (and any ``a/b`` suffix) add only a few more chars, so the final key
# stays well under 255. 64 is comfortably long enough for any real surname.
MAX_KEY_LEN = 64

# A small transliteration fallback for Latin-extended letters that have NO
# Unicode NFKD decomposition -- an ``ascii`` "ignore" pass would silently DROP
# them, mutilating a key (e.g. "Łukasiewicz" -> "ukasiewicz"). We keep only the
# common cases needed so a key never loses its leading letter; everything with a
# canonical decomposition (the vast majority of accented Latin) is handled by
# NFKD and needs no entry here.
_TRANSLIT_FALLBACK = {
    "Ł": "L", "ł": "l",
    "Đ": "D", "đ": "d",
    "Ø": "O", "ø": "o",
    "Ð": "D", "ð": "d",
    "Þ": "Th", "þ": "th",
    "ß": "ss",
    "Æ": "AE", "æ": "ae",
    "Œ": "OE", "œ": "oe",
    "Ħ": "H", "ħ": "h",
    "Ŧ": "T", "ŧ": "t",
}


def normalize_surname(raw: Optional[str]) -> str:
    """Normalize a first-author surname to an ASCII-alphanumeric key fragment.

    Deterministic: strip diacritics to ASCII (NFKD + ascii-ignore, with a small
    fallback map for letters lacking a canonical decomposition), drop spaces and
    punctuation, and preserve the given casing (``McKay`` stays ``McKay``;
    ``"van der Berg"`` -> ``vanderBerg``). An empty/whitespace input -- or one that
    normalizes to nothing -- yields :data:`ANON`. A pathologically long surname is
    sliced to :data:`MAX_KEY_LEN` (deterministic prefix) so the assembled key
    stays a safe single filename component (no ``ENAMETOOLONG`` on rename).

    Args:
        raw: the surname as recorded in the sidecar (may be ``None``/empty).

    Returns:
        An ASCII-alphanumeric surname fragment (<= :data:`MAX_KEY_LEN` chars), or
        ``"Anon"`` when absent.
    """
    if not raw or not raw.strip():
        return ANON
    # Apply the explicit fallback first so no-decomposition letters survive.
    pre = "".join(_TRANSLIT_FALLBACK.get(ch, ch) for ch in raw)
    decomposed = unicodedata.normalize("NFKD", pre)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", ascii_only)
    # Cap the length so a 300-char author can't produce a 300-char filename
    # component (deterministic prefix slice; ASCII-only by construction above).
    return cleaned[:MAX_KEY_LEN] or ANON


def _base_key(author: Optional[str], year: Optional[str]) -> str:
    """``<NormalizedSurname><Year>`` with Anon/nd fallbacks (no suffix yet)."""
    surname = normalize_surname(author)
    yr = year.strip() if (year and year.strip()) else NO_DATE
    return f"{surname}{yr}"


def _suffix(index: int) -> str:
    """0 -> 'a', 1 -> 'b', ... 25 -> 'z', 26 -> 'aa' (bijective base-26)."""
    letters = ""
    n = index + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


class OverwriteCollision(BaseModel):
    """Two or more distinct DOIs that resolved to ONE on-disk file.

    Surfaced so a silently-overwritten paper (paperforge collapsed a same-name
    collision before sci-adk saw it) is never lost from the record.
    """

    model_config = {"frozen": True}

    filename: str = Field(..., description="The shared on-disk filename")
    dois: list[str] = Field(..., description="The distinct DOIs mapped to it")


class KeyingResult(BaseModel):
    """The outcome of assigning citation keys to an acquired set.

    Attributes:
        mapping: DOI -> citation key (the keyed PDF/sidecar/bib stem).
        collisions: any overwrite collisions detected (empty when clean).
    """

    model_config = {"frozen": True}

    mapping: dict[str, str] = Field(default_factory=dict)
    collisions: list[OverwriteCollision] = Field(default_factory=list)


def _sidecar_path(sidecar_dir: Path, filename: str) -> Path:
    """The sidecar paperforge writes next to a PDF: ``<stem>.json``."""
    return sidecar_dir / f"{Path(filename).stem}.json"


def _read_sidecar_author_year(
    sidecar_dir: Path, filename: str
) -> tuple[Optional[str], Optional[str]]:
    """Read (author, year) from ``<sidecar_dir>/<stem>.json``.

    The caller only invokes this for records whose sidecar exists (keying is
    gated on sidecar presence). An *unparseable* sidecar yields ``(None, None)``
    so the Anon/nd fallbacks apply rather than failing the keying.
    """
    sidecar = _sidecar_path(sidecar_dir, filename)
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    author = data.get("author")
    year = data.get("year")
    # year may be recorded as an int; normalize to str for the key.
    if year is not None and not isinstance(year, str):
        year = str(year)
    return author, year


def assign_citation_keys(
    records: Sequence[AcquisitionRecord],
    sidecar_dir: Path,
) -> KeyingResult:
    """Compute the DOI -> citation-key mapping for an acquired set.

    Only successful records that name a file are keyed (a failed DOI has no PDF).
    The base key comes from each record's sidecar (author/year, with Anon/nd
    fallbacks); records sharing a base key get ``a/b/c…`` suffixes ordered by DOI
    ascending (deterministic, acquisition-order-independent). Pure: no files are
    renamed here -- use :func:`apply_citation_keys` for that.

    Overwrite detection: when two or more DISTINCT DOIs name the SAME on-disk
    filename, that is paperforge having overwritten a same-name collision before
    sci-adk saw it -- it is surfaced in :attr:`KeyingResult.collisions` (the
    papers still receive distinct keys so the record stays honest about the loss).

    Keying is gated on **sidecar presence**: only a record whose paperforge
    ``<stem>.json`` sidecar exists is keyed. A PDF dropped without any sidecar has
    no author/year basis, so it is left at its paperforge filename rather than
    forced to an ``Anonnd`` key (the Anon/nd fallbacks apply to a sidecar that
    exists but has empty/missing fields, the real paperforge case).

    Args:
        records: the acquisition records (only successes with a filename count).
        sidecar_dir: the ``pdfs/`` directory holding ``<stem>.json`` sidecars.

    Returns:
        A :class:`KeyingResult` with the mapping and any overwrite collisions.
    """
    keyable = [
        r for r in records
        if r.ok and r.filename and _sidecar_path(sidecar_dir, r.filename).exists()
    ]

    # -- overwrite detection: distinct DOIs -> same on-disk filename -----------
    by_filename: dict[str, list[str]] = {}
    for r in keyable:
        by_filename.setdefault(r.filename, []).append(r.doi)
    collisions = [
        OverwriteCollision(filename=fn, dois=sorted(set(dois)))
        for fn, dois in by_filename.items()
        if len(set(dois)) > 1
    ]

    # -- base key per record, grouped --------------------------------------
    base_of: dict[str, str] = {}
    groups: dict[str, list[str]] = {}
    for r in keyable:
        author, year = _read_sidecar_author_year(sidecar_dir, r.filename)
        base = _base_key(author, year)
        base_of[r.doi] = base
        groups.setdefault(base, []).append(r.doi)

    # -- assign keys: suffix only when a base key is shared -----------------
    mapping: dict[str, str] = {}
    for base, dois in groups.items():
        if len(dois) == 1:
            mapping[dois[0]] = base
            continue
        # deterministic a/b/c… by DOI ascending
        for i, doi in enumerate(sorted(dois)):
            mapping[doi] = f"{base}{_suffix(i)}"

    return KeyingResult(mapping=mapping, collisions=collisions)


# Temp-name prefix used only during the two-stage rename. A real citation key is
# bare ASCII alphanumerics with a trailing a/b suffix, so it can never contain an
# underscore -- thus a temp stem (underscore + index) never collides with a key
# nor with any acquired source filename (also alphanumeric). A stale temp left by
# a run that crashed between the two stages is therefore an orphan scratch file,
# not a real paper -- the next run's stage 1 harmlessly overwrites it.
_REKEY_TMP_PREFIX = "__sciadk_rekey_"


def _move_pair(pdf_dir: Path, src_stem: str, dst_stem: str, suffix: str) -> None:
    """Move ``<src_stem><suffix>`` and ``<src_stem>.json`` to ``<dst_stem>``.

    The PDF and its ``.json`` sidecar are each moved only when present (a record
    whose file paperforge overwrote away has no source to move). Helper for the
    two-stage rename in :func:`apply_citation_keys`.
    """
    src_pdf = pdf_dir / f"{src_stem}{suffix}"
    if src_pdf.exists():
        src_pdf.replace(pdf_dir / f"{dst_stem}{suffix}")
    src_sidecar = pdf_dir / f"{src_stem}.json"
    if src_sidecar.exists():
        src_sidecar.replace(pdf_dir / f"{dst_stem}.json")


# Matches a BibTeX entry head and captures (@type{, oldkey, rest-of-entry-until-})
# in DOTALL so the body (which spans lines) is captured whole. Non-greedy body so
# adjacent entries are not merged. The end-anchor allows leading whitespace before
# the closing brace (``\n\s*\}``) so an entry whose ``}`` is indented still
# matches. The DOI field inside the body is matched separately to link an entry to
# a record.
_BIB_ENTRY_RE = re.compile(
    r"(@\w+\s*\{)\s*([^,\s]+)\s*,(.*?)(\n\s*\})",
    re.DOTALL,
)
_BIB_DOI_RE = re.compile(r"doi\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]", re.IGNORECASE)


def _rewrite_bib(bib_path: Path, doi_to_key: dict[str, str]) -> None:
    """Rewrite each ``references.bib`` entry's key to its DOI's citation key.

    Entries are matched to records by their ``doi = {...}`` field (case-folded),
    NOT by paperforge's original key. An entry whose DOI is not in the mapping is
    left untouched. A missing bib file is skipped (not an error).
    """
    if not bib_path.exists():
        return
    text = bib_path.read_text(encoding="utf-8")
    # Case-fold DOIs for matching (DOIs are case-insensitive).
    folded = {doi.lower(): key for doi, key in doi_to_key.items()}

    def _sub(m: re.Match) -> str:
        head, old_key, body, tail = m.groups()
        doi_match = _BIB_DOI_RE.search(body)
        if doi_match:
            key = folded.get(doi_match.group(1).strip().lower())
            if key:
                return f"{head}{key},{body}{tail}"
        return m.group(0)  # no DOI / unmapped -> leave untouched

    bib_path.write_text(_BIB_ENTRY_RE.sub(_sub, text), encoding="utf-8")


def _rewrite_manifest(manifest_path: Path, doi_to_key: dict[str, str]) -> None:
    """Update the ``filename`` column of each keyed DOI's manifest row.

    The new filename is ``<key>.pdf`` (preserving the original extension). Rows
    for unkeyed DOIs (failures, or DOIs absent from the mapping) are untouched.
    A missing manifest is skipped.
    """
    if not manifest_path.exists():
        return
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or list(_MANIFEST_FIELDS)
        rows = list(reader)

    for row in rows:
        key = doi_to_key.get(row.get("doi", ""))
        if not key:
            continue
        old = row.get("filename") or ""
        suffix = Path(old).suffix or ".pdf"
        row["filename"] = f"{key}{suffix}"

    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def apply_citation_keys(
    literature_dir: Path,
    records: Sequence[AcquisitionRecord],
    mapping: dict[str, str],
) -> None:
    """Apply a DOI -> key ``mapping`` to every artifact in ``literature_dir``.

    For each keyed record this renames ``pdfs/<old>.pdf`` -> ``pdfs/<key>.pdf``
    and its ``.json`` sidecar, rewrites the matching ``references.bib`` entry key,
    and updates the ``manifest.csv`` filename column -- so the citation key ==
    PDF stem == sidecar stem == .bib key == manifest filename. Idempotent:
    re-running on already-keyed files is a safe no-op.

    The PDF/sidecar rename is a **two-stage, swap/cycle-safe batch**: paperforge's
    own a/b filename order need not match sci-adk's DOI-ascending keys, so the
    mapping can be a swap (A->B, B->A) or a longer cycle. Every source is first
    moved to a unique temp name, then each temp to its final key -- so no source
    is ever clobbered by a not-yet-moved file (a one-pass rename would lose data).

    Args:
        literature_dir: the run's ``literature/`` dir (holds ``pdfs/``,
            ``manifest.csv``, ``references.bib``).
        records: the acquisition records (provides each DOI's on-disk filename).
        mapping: DOI -> citation key (from :func:`assign_citation_keys`).
    """
    literature_dir = Path(literature_dir)
    pdf_dir = literature_dir / "pdfs"

    # Plan the renames: a record that names a file, is mapped, and is not already
    # at its key (idempotent no-op when old stem == key).
    planned: list[tuple[str, str, str]] = []  # (old_stem, key, suffix)
    for r in records:
        key = mapping.get(r.doi)
        if not key or not r.filename:
            continue
        old_stem = Path(r.filename).stem
        if old_stem == key:
            continue
        suffix = Path(r.filename).suffix or ".pdf"
        planned.append((old_stem, key, suffix))

    # Two-stage swap/cycle-safe rename. paperforge now emits its OWN a/b names,
    # whose order need not match sci-adk's DOI-ascending keys -- so the mapping
    # can be a swap (A->B, B->A) or a longer cycle. A one-pass ``Path.replace``
    # would clobber a not-yet-moved source. Stage 1 moves every source to a unique
    # temp name; stage 2 moves each temp to its final key. No final name is ever
    # the live source of a pending move, so no artifact is overwritten/lost.
    for i, (old_stem, _key, suffix) in enumerate(planned):
        _move_pair(pdf_dir, old_stem, f"{_REKEY_TMP_PREFIX}{i}", suffix)
    for i, (_old_stem, key, suffix) in enumerate(planned):
        _move_pair(pdf_dir, f"{_REKEY_TMP_PREFIX}{i}", key, suffix)

    _rewrite_bib(literature_dir / "references.bib", mapping)
    _rewrite_manifest(literature_dir / "manifest.csv", mapping)


def assign_and_apply_citation_keys(
    literature_dir: Path,
    records: Sequence[AcquisitionRecord],
) -> KeyingResult:
    """Compute and apply citation keys for an acquired set in one call.

    A convenience wrapper combining :func:`assign_citation_keys` (read sidecars,
    compute deterministic keys, detect overwrite collisions) and
    :func:`apply_citation_keys` (rename PDFs/sidecars, rewrite bib + manifest).

    Args:
        literature_dir: the run's ``literature/`` dir.
        records: the acquisition records.

    Returns:
        The :class:`KeyingResult` (mapping + any overwrite collisions), for the
        caller to record in the LITERATURE EvidenceItem.
    """
    literature_dir = Path(literature_dir)
    result = assign_citation_keys(records, literature_dir / "pdfs")
    apply_citation_keys(literature_dir, records, result.mapping)
    return result
