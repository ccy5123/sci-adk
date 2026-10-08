"""
Accumulate one run's literature store across acquisition calls.

Every recorder (prior-work, novelty, contested, inquiry) acquires into the SAME
``runs/<id>/literature/``. paperforge keeps ``manifest.csv`` across calls, but
REWRITES ``references.bib`` from scratch with only the current call's DOIs, and
its key/filename suffixes are unique only within one call. Left alone, each call
would drop every earlier citation, and re-keying the whole manifest would rename
papers a manuscript already cites.

This module makes the store append-only for keys:

  1. :func:`snapshot_literature` -- taken BEFORE paperforge runs -- records the
     existing bib text, every key/PDF stem already in use, and the DOI -> key
     bindings already made (from the bib, else from a manifest row whose PDF is on
     disk -- a run whose bib was already lost to this bug keeps its file keys).
  2. :func:`key_and_merge` -- after paperforge -- keys THIS call's DOIs, renames
     only this call's new PDFs, and rewrites ``references.bib`` as
     ``<previous bib verbatim> + <entries for DOIs not seen before>``.

Key rule (extends ``citation_keys``'s ``<Surname><Year>`` + ``a/b`` convention):

  * a DOI that already has a key keeps it, with its bib entry text, unchanged;
  * a newcomer's base is ``<Surname><Year>`` from its OWN bib entry (first
    author's family name + year) -- falling back to the sidecar author/year
    (Anon/nd fallbacks) when the entry has no usable author/year, then to
    paperforge's bib key minus its trailing ``a/b`` suffix -- so the PDF, sidecar,
    manifest filename and bib key all carry the one key;
  * the base's *family* is every key or PDF stem already taken that is the base
    plus an optional letter suffix (lower or UPPERCASE provisional, from
    ``add-literature``) and an optional ``_SI``;
  * when the family is empty and only one newcomer of this call has the base,
    it is bare (``Smith2001``);
  * otherwise this call's newcomers of that base, in DOI-ascending order, take
    the first free suffixes ``a, b, c, …`` -- skipping any taken key. "Taken" is
    compared case-insensitively (BibTeX keys and Windows/macOS filenames are
    case-insensitive), so ``Smith2001A`` blocks ``Smith2001a``. An existing bare
    ``Smith2001`` stays bare; the newcomer becomes ``Smith2001a``. On a first call
    with nothing taken, this equals ``assign_citation_keys`` (bare, or a/b by DOI).

Entries without a DOI already in the bib (manual / synthetic) are kept verbatim,
and PDFs/sidecars present before the call are never renamed or overwritten. No
LLM, no new dependency; bib entries are split brace-depth-aware via
``render.pkgreqs_checks._entry_close_index`` (the helper ``bib_subset`` uses).
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from sci_adk.search.citation_keys import (
    ANON,
    KeyingResult,
    OverwriteCollision,
    _BIB_DOI_RE,
    _base_key,
    _read_sidecar_author_year,
    _sidecar_path,
    _suffix,
    apply_citation_keys,
    bib_first_author_family,
    normalize_surname,
)
from sci_adk.search.manual_literature import normalize_doi
from sci_adk.search.paperforge_adapter import AcquisitionRecord

# An entry header ``@type{KEY,`` (``@comment``/``@string``/``@preamble`` have no key
# and are matched by nothing that needs keying -- they stay in the verbatim prefix).
_ENTRY_HEAD_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s{}]+)\s*,")
_PAPERFORGE_SUFFIX_RE = re.compile(r"(?<=\d)[a-z]+$")


@dataclass(frozen=True)
class BibEntry:
    """One BibTeX entry: its key, normalised DOI (``""`` when absent), full text."""

    key: str
    doi: str
    text: str


def _entry_spans(bib: str) -> list[tuple[int, int, BibEntry]]:
    """``(start, end, entry)`` for each entry of ``bib``, brace-depth aware.

    An entry runs from its ``@`` to the brace that closes its opening ``{`` -- not to
    the next ``@`` and not to a newline -- so a one-line entry, a field value holding
    ``{nested}`` braces, or an ``@word{...}`` token inside a value all stay whole.
    """
    # Lazy import: importing sci_adk.render at module load pulls in the loop
    # package, which imports this module (circular).
    from sci_adk.render.pkgreqs_checks import _entry_close_index

    spans: list[tuple[int, int, BibEntry]] = []
    pos = 0
    while True:
        m = _ENTRY_HEAD_RE.search(bib, pos)
        if m is None:
            break
        open_brace = bib.index("{", m.start())
        end = _entry_close_index(bib, open_brace)
        text = bib[m.start():end]
        doi_match = _BIB_DOI_RE.search(text)
        spans.append((m.start(), end, BibEntry(
            key=m.group(2),
            doi=normalize_doi(doi_match.group(1)) if doi_match else "",
            text=text,
        )))
        pos = end
    return spans


def parse_bib_entries(bib: str) -> list[BibEntry]:
    """Split ``bib`` into entries, brace-depth aware, in source order."""
    return [entry for _start, _end, entry in _entry_spans(bib)]


def rekey_bib_text(bib: str, doi_to_key: dict[str, str]) -> str:
    """``bib`` with each entry whose DOI is mapped re-keyed; all other text verbatim.

    DOIs are compared after :func:`normalize_doi` (case-insensitive, prefix-free).
    Only the key inside ``@type{KEY,`` changes, whatever the entry's line layout.
    """
    wanted = {normalize_doi(d): k for d, k in doi_to_key.items()}
    out: list[str] = []
    pos = 0
    for start, end, entry in _entry_spans(bib):
        key = wanted.get(entry.doi) if entry.doi else None
        if key and key != entry.key:
            out.append(bib[pos:start])
            out.append(_rekey_entry(entry.text, key))
            pos = end
    out.append(bib[pos:])
    return "".join(out)


_FIELD_NAME_RE = re.compile(r"[\s,]*([A-Za-z][\w-]*)\s*=\s*")
_BARE_VALUE_RE = re.compile(r"[^,}\s]*")


def bib_field(entry_text: str, name: str) -> Optional[str]:
    """The raw value of field ``name`` (case-insensitive) in one entry, or ``None``.

    Walks the entry's ``name = value`` pairs at the top level -- ``{...}`` values by
    brace depth, ``"..."`` values to the closing quote, bare values (``month=Apr``,
    ``year=2012``) to the next ``,`` or ``}`` -- so a field name that only appears
    inside another field's text is never mistaken for that field.
    """
    from sci_adk.render.pkgreqs_checks import _entry_close_index  # lazy: circular

    head = _ENTRY_HEAD_RE.match(entry_text)
    if head is None:
        return None
    wanted = name.lower()
    i, n = head.end(), len(entry_text)
    while i < n:
        fm = _FIELD_NAME_RE.match(entry_text, i)
        if fm is None or fm.end() >= n:
            return None
        field_name, i = fm.group(1).lower(), fm.end()
        if entry_text[i] == "{":
            end = _entry_close_index(entry_text, i)
            value, i = entry_text[i + 1:end - 1], end
        elif entry_text[i] == '"':
            j, depth = i + 1, 0
            while j < n and not (entry_text[j] == '"' and depth == 0):
                depth += {"{": 1, "}": -1}.get(entry_text[j], 0)
                j += 1
            value, i = entry_text[i + 1:j], j + 1
        else:
            vm = _BARE_VALUE_RE.match(entry_text, i)
            value, i = vm.group(0), vm.end()
        if field_name == wanted:
            return value
    return None


# @MX:NOTE: [AUTO] Key-source rule for a DOI keyed for the FIRST time: the base
#   <Surname><Year> comes from that DOI's own bib entry (first author's family name
#   from the BibTeX `author` field, 4-digit `year`) -- the bib entry is the single
#   source of a key, so the PDF, sidecar, manifest filename and bib key all carry
#   it. Fallbacks, in order: the sidecar (OpenAlex) author/year when the entry has
#   no usable author or year, then paperforge's own bib key minus its a/b suffix.
#   The sidecar is NOT preferred because OpenAlex and Crossref can disagree on the
#   first author (10.5772/31647: Taherpour vs Arman) or the year (10.1002/jps.21494:
#   2008 online vs 2009 issue), and the bib key is what a manuscript \cite{}s.
#   Keys assigned before the call never change (see key_and_merge).
def bib_entry_base(entry_text: str) -> Optional[str]:
    """``<Surname><Year>`` from an entry's own author/year, or ``None`` if unusable.

    Unusable: no ``author`` field, a first author whose family name normalizes to
    nothing, or a ``year`` with no 4-digit run.
    """
    author = bib_field(entry_text, "author")
    year = re.search(r"\d{4}", bib_field(entry_text, "year") or "")
    if not author or year is None:
        return None
    family = bib_first_author_family(author)
    surname = normalize_surname(family)
    if not family.strip() or surname == ANON:
        return None
    return f"{surname}{year.group(0)}"


@dataclass(frozen=True)
class LiteratureSnapshot:
    """The literature store as it was before an acquisition call.

    Attributes:
        bib_text: ``references.bib`` before the call (``None`` when absent).
        bib_dois: normalised DOIs that already have a bib entry.
        doi_keys: normalised DOI -> its already-assigned key.
        taken: every key and ``pdfs/`` file stem in use, case-folded.
        stems: the ``pdfs/`` file stems present (exact case).
    """

    bib_text: Optional[str]
    bib_dois: frozenset[str] = field(default_factory=frozenset)
    doi_keys: dict[str, str] = field(default_factory=dict)
    taken: frozenset[str] = field(default_factory=frozenset)
    stems: frozenset[str] = field(default_factory=frozenset)


def snapshot_literature(literature_dir: Path) -> LiteratureSnapshot:
    """Record the store's keys, stems and bib text; call BEFORE paperforge runs."""
    literature_dir = Path(literature_dir)
    bib_path = literature_dir / "references.bib"
    bib_text = bib_path.read_text(encoding="utf-8") if bib_path.exists() else None

    pdf_dir = literature_dir / "pdfs"
    stems = (
        frozenset(p.stem for p in pdf_dir.iterdir()
                  if p.suffix.lower() in (".pdf", ".json"))
        if pdf_dir.is_dir() else frozenset()
    )

    entries = parse_bib_entries(bib_text or "")
    doi_keys: dict[str, str] = {}
    for e in entries:
        if e.doi and e.doi not in doi_keys:
            doi_keys[e.doi] = e.key
    bib_dois = frozenset(doi_keys)
    bib_keys_cf = {e.key.casefold() for e in entries}

    # A DOI recorded in the manifest with its PDF on disk but no bib entry (a bib
    # lost before this fix) keeps the key its file already carries.
    manifest = literature_dir / "manifest.csv"
    if manifest.exists():
        with open(manifest, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                doi = normalize_doi(row.get("doi"))
                stem = Path(row.get("filename") or "").stem
                if (doi and doi not in doi_keys and row.get("status") == "success"
                        and stem in stems and stem.casefold() not in bib_keys_cf):
                    doi_keys[doi] = stem

    taken = frozenset(
        {e.key.casefold() for e in entries} | {s.casefold() for s in stems})
    return LiteratureSnapshot(bib_text=bib_text, bib_dois=bib_dois,
                              doi_keys=doi_keys, taken=taken, stems=stems)


def _family_taken(base: str, taken: set[str]) -> bool:
    """True when any taken key is ``base`` + optional letters + optional ``_SI``."""
    pat = re.compile(rf"{re.escape(base.casefold())}[a-z]*(_si)?")
    return any(pat.fullmatch(t) for t in taken)


def _assign_newcomers(bases: dict[str, str], taken: set[str]) -> dict[str, str]:
    """DOI -> key for newcomers (``bases``: DOI -> base key). Mutates ``taken``."""
    groups: dict[str, list[str]] = {}
    for doi, base in bases.items():
        groups.setdefault(base, []).append(doi)
    keys: dict[str, str] = {}
    for base in sorted(groups):
        dois = sorted(groups[base])
        if len(dois) == 1 and not _family_taken(base, taken):
            keys[dois[0]] = base
            taken.add(base.casefold())
            continue
        index = 0
        for doi in dois:
            while f"{base}{_suffix(index)}".casefold() in taken:
                index += 1
            key = f"{base}{_suffix(index)}"
            keys[doi] = key
            taken.add(key.casefold())
    return keys


def _sidecar_doi(pdf_dir: Path, stem: str) -> str:
    """Normalised DOI recorded in ``<stem>.json`` (``""`` when absent/unreadable)."""
    try:
        data = json.loads(_sidecar_path(pdf_dir, f"{stem}.pdf").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return normalize_doi(data.get("doi") if isinstance(data, dict) else None)


def _rekey_entry(text: str, key: str) -> str:
    """``text`` with its entry key replaced by ``key`` (type and body untouched)."""
    return _ENTRY_HEAD_RE.sub(lambda m: f"@{m.group(1)}{{{key},", text, count=1)


def merge_bib(prior_text: Optional[str], new_entries: Sequence[BibEntry],
              doi_keys: dict[str, str], prior_dois: frozenset[str]) -> str:
    """``prior_text`` verbatim plus the new entries whose DOI it lacks, re-keyed.

    A new entry without a DOI, or whose DOI is already in ``prior_dois`` or was
    already appended, is dropped (the earlier text wins).
    """
    out = (prior_text or "").rstrip()
    seen = set(prior_dois)
    for e in new_entries:
        if not e.doi or e.doi in seen or e.doi not in doi_keys:
            continue
        seen.add(e.doi)
        block = _rekey_entry(e.text.strip(), doi_keys[e.doi])
        out = f"{out}\n\n{block}" if out else block
    return f"{out}\n" if out else ""


# @MX:WARN: [AUTO] rewrites references.bib and renames PDFs in a run's shared
#   literature store on every acquisition call.
# @MX:REASON: [AUTO] authored manuscripts cite these keys and PDF filenames carry
#   them; dropping an entry or changing a key silently breaks every \cite that uses
#   it. Keys present in the snapshot must never change, earlier bib text must be
#   kept verbatim, and earlier PDFs/sidecars must never be renamed or overwritten.
def key_and_merge(
    literature_dir: Path,
    call_records: Sequence[AcquisitionRecord],
    call_bib_text: Optional[str],
    snapshot: LiteratureSnapshot,
) -> KeyingResult:
    """Key this call's DOIs against ``snapshot`` and write the merged bib.

    Args:
        literature_dir: the run's ``literature/`` dir.
        call_records: manifest records for the DOIs requested in THIS call.
        call_bib_text: ``references.bib`` as paperforge wrote it for this call
            (read right after the fetch, before any re-download rewrites it).
        snapshot: :func:`snapshot_literature` taken before the fetch.

    Returns:
        A :class:`KeyingResult`: DOI -> key for this call's acquired PDFs, plus
        overwrite collisions (distinct DOIs sharing one file, or a PDF whose key
        is held on disk by another paper's file -- left unrenamed).
    """
    literature_dir = Path(literature_dir)
    pdf_dir = literature_dir / "pdfs"
    new_entries = parse_bib_entries(call_bib_text or "")

    keyable = [r for r in call_records
               if r.ok and r.filename and _sidecar_path(pdf_dir, r.filename).exists()]
    by_filename: dict[str, set[str]] = {}
    for r in keyable:
        by_filename.setdefault(r.filename, set()).add(r.doi)
    collisions = [OverwriteCollision(filename=fn, dois=sorted(d))
                  for fn, d in by_filename.items() if len(d) > 1]

    # Bases for DOIs with no key yet: the DOI's own bib entry first (author/year),
    # else its sidecar, else paperforge's bib key minus its a/b suffix.
    entry_of: dict[str, BibEntry] = {}
    for e in new_entries:
        if e.doi:
            entry_of.setdefault(e.doi, e)
    bases: dict[str, str] = {}
    for r in keyable:
        doi = normalize_doi(r.doi)
        if doi and doi not in snapshot.doi_keys and doi not in bases:
            entry = entry_of.get(doi)
            bases[doi] = ((bib_entry_base(entry.text) if entry else None)
                          or _base_key(*_read_sidecar_author_year(pdf_dir, r.filename)))
    for doi, e in entry_of.items():
        if doi not in snapshot.doi_keys and doi not in bases:
            bases[doi] = (bib_entry_base(e.text)
                          or _PAPERFORGE_SUFFIX_RE.sub("", e.key) or e.key)

    taken = set(snapshot.taken)
    doi_keys = {**snapshot.doi_keys, **_assign_newcomers(bases, taken)}

    pdf_mapping: dict[str, str] = {}
    for r in keyable:
        key = doi_keys.get(normalize_doi(r.doi))
        if key is None:
            continue
        source = Path(r.filename).stem
        if (key != source and key in snapshot.stems
                and _sidecar_doi(pdf_dir, key) != normalize_doi(r.doi)):
            # The key's file belongs to another paper (or a manual PDF): never
            # overwrite it; leave this PDF under paperforge's name and surface it.
            collisions.append(OverwriteCollision(filename=f"{key}.pdf", dois=[r.doi]))
            continue
        pdf_mapping[r.doi] = key

    apply_citation_keys(literature_dir, keyable, pdf_mapping)

    if snapshot.bib_text is not None or call_bib_text is not None:
        (literature_dir / "references.bib").write_text(
            merge_bib(snapshot.bib_text, new_entries, doi_keys, snapshot.bib_dois),
            encoding="utf-8")
    return KeyingResult(mapping=pdf_mapping, collisions=collisions)
