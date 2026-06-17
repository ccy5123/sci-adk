"""
Network-free unit tests for sci-adk's citation-key naming of acquired PDFs.

sci-adk OWNS the citation-key convention as a post-acquisition step (paperforge,
the external pinned tool, is never modified). A key is ``<NormalizedSurname><Year>``
with ``a/b/c…`` disambiguation -- ordered by DOI ascending -- when two acquired
papers map to the same base key. The key is applied consistently to ALL artifacts:
the PDF stem, its ``.json`` sidecar stem, the ``references.bib`` entry key, and the
``manifest.csv`` filename column.

These tests fake the acquired directory directly (PDFs + sidecars + manifest + bib)
-- no paperforge, no subprocess, no network. They pin the convention's contract:
deterministic keys, a/b-by-DOI on collision, ``Anon``/``nd`` fallbacks, surname
normalization, cross-artifact consistency, idempotency, and the overwrite-collision
detection (two DOIs resolving to one on-disk file is surfaced, never silently lost).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.search.citation_keys import (
    MAX_KEY_LEN,
    KeyingResult,
    apply_citation_keys,
    assign_and_apply_citation_keys,
    assign_citation_keys,
    normalize_surname,
)
from sci_adk.search.paperforge_adapter import AcquisitionRecord

# A minimal valid PDF body (magic bytes) -- content is irrelevant to keying,
# which is a pure rename/metadata step that never parses the PDF.
PDF_BYTES = b"%PDF-1.4\n%minimal\n"

_MANIFEST_HEADER = "index,doi,status,source,license,filename,origin,error"


def _sidecar(doi: str, author: str | None, year: str | None) -> dict:
    """A paperforge-shaped sidecar dict (author=first-author surname, year=str)."""
    d: dict = {"doi": doi, "title": f"Title for {doi}"}
    if author is not None:
        d["author"] = author
    if year is not None:
        d["year"] = year
    return d


def _bib_entry(key: str, doi: str, author_bibtex: str) -> str:
    """A BibTeX entry whose DOI field links it back to a record (key is paperforge's)."""
    return (
        f"@article{{{key},\n"
        f"  author  = {{{author_bibtex}}},\n"
        f"  title   = {{Title for {doi}}},\n"
        f"  year    = {{2020}},\n"
        f"  doi     = {{{doi}}}\n"
        f"}}\n"
    )


def _build_acquired_dir(
    tmp_path: Path,
    papers: list[dict],
    *,
    write_bib: bool = True,
    overwrite_filename: str | None = None,
) -> tuple[Path, list[AcquisitionRecord]]:
    """Lay out a fake acquired literature dir exactly as paperforge would.

    ``papers`` is a list of dicts: {doi, author, year, filename, bib_key, bib_author}.
    Returns (literature_dir, records). When ``overwrite_filename`` is set, every
    paper is written to that single on-disk file (simulating paperforge having
    overwritten a same-name collision before sci-adk saw it) -- but each paper
    keeps its own DISTINCT doi/record, so the loss is detectable.
    """
    lit = tmp_path / "literature"
    pdfs = lit / "pdfs"
    pdfs.mkdir(parents=True, exist_ok=True)

    records: list[AcquisitionRecord] = []
    manifest_rows = [_MANIFEST_HEADER]
    bib_chunks: list[str] = []

    for i, p in enumerate(papers, start=1):
        on_disk = overwrite_filename or p["filename"]
        stem = Path(on_disk).stem
        # PDF on disk
        (pdfs / on_disk).write_bytes(PDF_BYTES)
        # sidecar next to it (paperforge names it <stem>.json)
        (pdfs / f"{stem}.json").write_text(
            json.dumps(_sidecar(p["doi"], p.get("author"), p.get("year"))),
            encoding="utf-8",
        )
        records.append(
            AcquisitionRecord(
                doi=p["doi"], status="success", source="arxiv",
                license="", filename=on_disk,
            )
        )
        manifest_rows.append(
            f"{i},{p['doi']},success,arxiv,,{on_disk},cli,"
        )
        bib_chunks.append(
            _bib_entry(p.get("bib_key", f"pf{i}"), p["doi"],
                       p.get("bib_author", "Surname, Some"))
        )

    (lit / "manifest.csv").write_text("\n".join(manifest_rows) + "\n",
                                      encoding="utf-8")
    if write_bib:
        (lit / "references.bib").write_text("\n".join(bib_chunks), encoding="utf-8")
    return lit, records


def _read_manifest_filenames(lit: Path) -> dict[str, str]:
    """doi -> filename, parsed back from the manifest on disk."""
    import csv
    out: dict[str, str] = {}
    with open(lit / "manifest.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["doi"]] = row["filename"]
    return out


# === normalize_surname ======================================================

def test_normalize_surname_preserves_internal_casing():
    assert normalize_surname("McKay") == "McKay"


def test_normalize_surname_strips_spaces_and_punctuation():
    assert normalize_surname("van der Berg") == "vanderBerg"
    assert normalize_surname("O'Brien") == "OBrien"


def test_normalize_surname_strips_diacritics_to_ascii():
    assert normalize_surname("Jäger") == "Jager"
    assert normalize_surname("Krötkö") == "Krotko"
    assert normalize_surname("González") == "Gonzalez"


def test_normalize_surname_empty_is_anon():
    assert normalize_surname("") == "Anon"
    assert normalize_surname("   ") == "Anon"
    # a string that normalizes to nothing must not become "" -> Anon
    assert normalize_surname("---") == "Anon"


def test_normalize_surname_latin_extended_without_decomposition_keeps_letter():
    # Ł / Đ have no NFKD decomposition; a naive ascii-ignore drops the first
    # letter. The fallback map must keep a leading letter so a key is never
    # silently mutilated.
    assert normalize_surname("Łukasiewicz").startswith("L")
    assert normalize_surname("Đặng").startswith("D")


# === assign_citation_keys: base keys + fallbacks ============================

def test_single_paper_gets_surname_year_key(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026",
         "filename": "Joe2026.pdf", "bib_key": "joe2026", "bib_author": "Joe, A."},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert isinstance(res, KeyingResult)
    assert res.mapping == {"10.1/joe": "Joe2026"}
    assert res.collisions == []


def test_fallback_anon_for_missing_author(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/x", "author": None, "year": "2026", "filename": "x.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping == {"10.1/x": "Anon2026"}


def test_fallback_nd_for_missing_year(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/x", "author": "Jager", "year": None, "filename": "x.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping == {"10.1/x": "Jagernd"}


def test_fallback_both_missing_is_anon_nd(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/x", "author": None, "year": None, "filename": "x.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping == {"10.1/x": "Anonnd"}


def test_empty_string_author_year_use_fallbacks(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/x", "author": "", "year": "", "filename": "x.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping == {"10.1/x": "Anonnd"}


# === assign_citation_keys: a/b disambiguation by DOI ascending ==============

def test_collision_disambiguated_a_b_by_doi_ascending(tmp_path):
    # two Jager 1998 papers, different DOIs; lower DOI -> a, higher DOI -> b.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.9/zzz", "author": "Jager", "year": "1998", "filename": "p2.pdf"},
        {"doi": "10.1/aaa", "author": "Jager", "year": "1998", "filename": "p1.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping["10.1/aaa"] == "Jager1998a"   # lower DOI
    assert res.mapping["10.9/zzz"] == "Jager1998b"   # higher DOI


def test_collision_assignment_is_deterministic_across_runs(tmp_path):
    papers = [
        {"doi": "10.9/zzz", "author": "Jager", "year": "1998", "filename": "p2.pdf"},
        {"doi": "10.1/aaa", "author": "Jager", "year": "1998", "filename": "p1.pdf"},
    ]
    lit1, recs1 = _build_acquired_dir(tmp_path / "run1", papers)
    lit2, recs2 = _build_acquired_dir(tmp_path / "run2", list(reversed(papers)))
    res1 = assign_citation_keys(recs1, lit1 / "pdfs")
    # feed records in a DIFFERENT order: assignment must be identical (DOI-sorted)
    res2 = assign_citation_keys(recs2, lit2 / "pdfs")
    assert res1.mapping == res2.mapping
    assert res1.mapping["10.1/aaa"] == "Jager1998a"


def test_three_way_collision_gets_a_b_c(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.3/c", "author": "Smith", "year": "2000", "filename": "f3.pdf"},
        {"doi": "10.1/a", "author": "Smith", "year": "2000", "filename": "f1.pdf"},
        {"doi": "10.2/b", "author": "Smith", "year": "2000", "filename": "f2.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping["10.1/a"] == "Smith2000a"
    assert res.mapping["10.2/b"] == "Smith2000b"
    assert res.mapping["10.3/c"] == "Smith2000c"


def test_fallback_keys_also_disambiguate_by_doi(tmp_path):
    # two papers with no author/year both collapse to base "Anonnd" -> a/b by DOI.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.2/b", "author": None, "year": None, "filename": "f2.pdf"},
        {"doi": "10.1/a", "author": None, "year": None, "filename": "f1.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping["10.1/a"] == "Anonnda"
    assert res.mapping["10.2/b"] == "Anonndb"


def test_surname_normalization_collapses_to_same_base(tmp_path):
    # "Jäger" and "Jager" normalize to the same surname -> a real collision.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.2/b", "author": "Jäger", "year": "1998", "filename": "f2.pdf"},
        {"doi": "10.1/a", "author": "Jager", "year": "1998", "filename": "f1.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.mapping["10.1/a"] == "Jager1998a"
    assert res.mapping["10.2/b"] == "Jager1998b"


# === apply_citation_keys: rename + bib + manifest, consistency ==============

def test_apply_renames_pdf_and_sidecar(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "Joe2026.pdf"},
    ])
    # paperforge already happened to name it Joe2026 -- but pretend a different
    # on-disk name to prove the rename runs.
    lit2, records2 = _build_acquired_dir(tmp_path / "alt", [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "rawname.pdf"},
    ])
    res = assign_citation_keys(records2, lit2 / "pdfs")
    apply_citation_keys(lit2, records2, res.mapping)

    pdfs = lit2 / "pdfs"
    assert (pdfs / "Joe2026.pdf").exists()
    assert (pdfs / "Joe2026.json").exists()
    assert not (pdfs / "rawname.pdf").exists()
    assert not (pdfs / "rawname.json").exists()


def test_apply_rewrites_bib_key_matched_by_doi(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "raw.pdf",
         "bib_key": "joe2026orig", "bib_author": "Joe, Alice"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    apply_citation_keys(lit, records, res.mapping)
    bib = (lit / "references.bib").read_text(encoding="utf-8")
    assert "@article{Joe2026," in bib
    assert "joe2026orig" not in bib
    # the rest of the entry (author/doi) is preserved
    assert "Joe, Alice" in bib
    assert "10.1/joe" in bib


def test_apply_updates_manifest_filename_column(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "raw.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    apply_citation_keys(lit, records, res.mapping)
    assert _read_manifest_filenames(lit)["10.1/joe"] == "Joe2026.pdf"


def test_apply_full_consistency_pdf_sidecar_bib_manifest(tmp_path):
    # For each paper, PDF stem == sidecar stem == bib key == manifest filename stem.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.9/zzz", "author": "Jager", "year": "1998", "filename": "p2.pdf",
         "bib_key": "jagerB", "bib_author": "Jager, B."},
        {"doi": "10.1/aaa", "author": "Jager", "year": "1998", "filename": "p1.pdf",
         "bib_key": "jagerA", "bib_author": "Jager, A."},
        {"doi": "10.5/mmm", "author": "Joe", "year": "2026", "filename": "j.pdf",
         "bib_key": "joeX", "bib_author": "Joe, C."},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    apply_citation_keys(lit, records, res.mapping)

    pdfs = lit / "pdfs"
    bib = (lit / "references.bib").read_text(encoding="utf-8")
    manifest_fn = _read_manifest_filenames(lit)

    for doi, key in res.mapping.items():
        assert (pdfs / f"{key}.pdf").exists(), f"pdf for {key}"
        assert (pdfs / f"{key}.json").exists(), f"sidecar for {key}"
        assert f"@article{{{key}," in bib, f"bib key {key}"
        assert manifest_fn[doi] == f"{key}.pdf", f"manifest filename for {key}"


def test_apply_is_idempotent_noop_on_already_keyed(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "raw.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    apply_citation_keys(lit, records, res.mapping)
    bib_after_first = (lit / "references.bib").read_text(encoding="utf-8")

    # re-run on the already-keyed dir: records now carry the keyed filename
    keyed_records = [
        AcquisitionRecord(doi=r.doi, status=r.status, source=r.source,
                          license=r.license, filename=f"{res.mapping[r.doi]}.pdf")
        for r in records
    ]
    res2 = assign_citation_keys(keyed_records, lit / "pdfs")
    assert res2.mapping == res.mapping
    apply_citation_keys(lit, keyed_records, res2.mapping)  # must not raise / corrupt
    assert (lit / "pdfs" / "Joe2026.pdf").exists()
    assert (lit / "references.bib").read_text(encoding="utf-8") == bib_after_first


# === overwrite-collision detection ==========================================

def test_overwrite_collision_two_dois_one_file_is_surfaced(tmp_path):
    # Two DISTINCT DOIs, but paperforge overwrote both into ONE on-disk file
    # before sci-adk saw it. The keyer must DETECT this (never silently lose a
    # paper) and surface it via collisions.
    lit, records = _build_acquired_dir(
        tmp_path,
        [
            {"doi": "10.1/a", "author": "Jager", "year": "1998"},
            {"doi": "10.2/b", "author": "Jager", "year": "1998"},
        ],
        overwrite_filename="Jager1998.pdf",   # both written to the same file
    )
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.collisions, "an overwrite collision must be surfaced"
    # the surfaced collision names the shared on-disk file and the lost DOIs
    coll = res.collisions[0]
    assert coll.filename == "Jager1998.pdf"
    assert set(coll.dois) == {"10.1/a", "10.2/b"}


def test_no_overwrite_collision_when_filenames_distinct(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/a", "author": "Jager", "year": "1998", "filename": "p1.pdf"},
        {"doi": "10.2/b", "author": "Jager", "year": "1998", "filename": "p2.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    assert res.collisions == []


# === assign_and_apply convenience (one call) ================================

def test_assign_and_apply_returns_result_and_renames(tmp_path):
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "raw.pdf",
         "bib_key": "joeorig", "bib_author": "Joe, A."},
    ])
    res = assign_and_apply_citation_keys(lit, records)
    assert isinstance(res, KeyingResult)
    assert res.mapping == {"10.1/joe": "Joe2026"}
    assert (lit / "pdfs" / "Joe2026.pdf").exists()
    assert "@article{Joe2026," in (lit / "references.bib").read_text(encoding="utf-8")


def test_assign_and_apply_handles_missing_bib_gracefully(tmp_path):
    # a literature dir without references.bib must still rename PDF + sidecar +
    # manifest (bib rewrite is skipped, not an error).
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "raw.pdf"},
    ], write_bib=False)
    res = assign_and_apply_citation_keys(lit, records)
    assert (lit / "pdfs" / "Joe2026.pdf").exists()
    assert _read_manifest_filenames(lit)["10.1/joe"] == "Joe2026.pdf"


def test_failed_records_are_not_keyed(tmp_path):
    # only successful records (with a file) are keyed; a failed DOI is skipped.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/ok", "author": "Joe", "year": "2026", "filename": "raw.pdf"},
    ])
    records.append(AcquisitionRecord(doi="10.9/miss", status="failed",
                                     error="no OA PDF"))
    res = assign_citation_keys(records, lit / "pdfs")
    assert "10.9/miss" not in res.mapping
    assert res.mapping == {"10.1/ok": "Joe2026"}


# === swap/cycle-safe rename (paperforge's a/b order need not match sci-adk's) ==
#
# paperforge now emits its OWN <surname><year>a/b names, but in paperforge's
# acquisition order -- which need NOT match sci-adk's canonical DOI-ascending
# order. So the DOI -> key mapping can be a SWAP (A->B, B->A) or a longer CYCLE.
# A one-pass ``Path.replace`` would clobber a not-yet-moved source file -> silent
# DATA LOSS. apply_citation_keys MUST rename as a swap/cycle-safe batch.


def _no_temp_leftover(pdfs: Path) -> bool:
    """True when no temp/scratch file from the two-stage rename survives.

    Checks the flat ``pdfs/`` level only (non-recursive); the rename writes temps
    only there, so a flat scan covers every path ``_move_pair`` can touch.
    """
    return not any(p.name.startswith("__sciadk") for p in pdfs.iterdir())


def test_apply_is_swap_safe_no_data_loss_on_ab_reorder(tmp_path):
    # Two Jager 1998 papers. paperforge wrote the HIGHER-DOI paper as
    # ``Jager1998a.pdf`` and the LOWER-DOI paper as ``Jager1998b.pdf`` (paperforge
    # order). sci-adk keys by DOI ascending -> lower-DOI -> Jager1998a,
    # higher-DOI -> Jager1998b. That is a SWAP. A naive record-by-record
    # ``Path.replace`` renames Jager1998a.pdf -> Jager1998b.pdf, clobbering the
    # other paper BEFORE it is moved -> a lost PDF + sidecar.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.9/zzz", "author": "Jager", "year": "1998",
         "filename": "Jager1998a.pdf"},   # paperforge a/, but HIGHER doi
        {"doi": "10.1/aaa", "author": "Jager", "year": "1998",
         "filename": "Jager1998b.pdf"},   # paperforge b/, but LOWER doi
    ])
    pdfs = lit / "pdfs"
    # Give each on-disk PDF DISTINCT content so a lost paper is visible
    # (_build_acquired_dir writes the same PDF_BYTES to every PDF).
    lower_content = b"%PDF-1.4\nDOI-10.1-aaa\n"
    higher_content = b"%PDF-1.4\nDOI-10.9-zzz\n"
    (pdfs / "Jager1998b.pdf").write_bytes(lower_content)    # holds the LOWER-DOI paper
    (pdfs / "Jager1998a.pdf").write_bytes(higher_content)   # holds the HIGHER-DOI paper

    res = assign_citation_keys(records, pdfs)
    # the mapping is the swap: lower DOI -> a, higher DOI -> b
    assert res.mapping == {"10.1/aaa": "Jager1998a", "10.9/zzz": "Jager1998b"}

    apply_citation_keys(lit, records, res.mapping)

    # BOTH papers survive under the correct key (no clobber / no loss)
    assert (pdfs / "Jager1998a.pdf").read_bytes() == lower_content
    assert (pdfs / "Jager1998b.pdf").read_bytes() == higher_content
    # each sidecar follows its PDF (parse the doi field back)
    a_doi = json.loads((pdfs / "Jager1998a.json").read_text(encoding="utf-8"))["doi"]
    b_doi = json.loads((pdfs / "Jager1998b.json").read_text(encoding="utf-8"))["doi"]
    assert a_doi == "10.1/aaa"   # Jager1998a carries the lower-DOI paper
    assert b_doi == "10.9/zzz"   # Jager1998b carries the higher-DOI paper
    # no scratch file from the two-stage rename is left behind
    assert _no_temp_leftover(pdfs), "a temp rekey file leaked into pdfs/"


def test_apply_is_cycle_safe_three_way(tmp_path):
    # Three Smith 2000 papers forming a 3-CYCLE. paperforge order vs sci-adk's
    # DOI-ascending order:
    #   Smith2000b.pdf (doi 10.1/a)  -> key Smith2000a
    #   Smith2000c.pdf (doi 10.2/b)  -> key Smith2000b
    #   Smith2000a.pdf (doi 10.3/c)  -> key Smith2000c
    # i.e. b->a, c->b, a->c : a 3-cycle. A one-pass rename loses papers.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/a", "author": "Smith", "year": "2000", "filename": "Smith2000b.pdf"},
        {"doi": "10.2/b", "author": "Smith", "year": "2000", "filename": "Smith2000c.pdf"},
        {"doi": "10.3/c", "author": "Smith", "year": "2000", "filename": "Smith2000a.pdf"},
    ])
    pdfs = lit / "pdfs"
    content = {
        "Smith2000b.pdf": b"%PDF-1.4\nDOI-10.1-a\n",
        "Smith2000c.pdf": b"%PDF-1.4\nDOI-10.2-b\n",
        "Smith2000a.pdf": b"%PDF-1.4\nDOI-10.3-c\n",
    }
    for fn, body in content.items():
        (pdfs / fn).write_bytes(body)

    res = assign_citation_keys(records, pdfs)
    assert res.mapping == {
        "10.1/a": "Smith2000a", "10.2/b": "Smith2000b", "10.3/c": "Smith2000c",
    }

    apply_citation_keys(lit, records, res.mapping)

    # each final file holds the content of the record that maps to it
    assert (pdfs / "Smith2000a.pdf").read_bytes() == content["Smith2000b.pdf"]  # 10.1/a
    assert (pdfs / "Smith2000b.pdf").read_bytes() == content["Smith2000c.pdf"]  # 10.2/b
    assert (pdfs / "Smith2000c.pdf").read_bytes() == content["Smith2000a.pdf"]  # 10.3/c
    # sidecars follow their PDFs
    assert json.loads((pdfs / "Smith2000a.json").read_text(encoding="utf-8"))["doi"] == "10.1/a"
    assert json.loads((pdfs / "Smith2000b.json").read_text(encoding="utf-8"))["doi"] == "10.2/b"
    assert json.loads((pdfs / "Smith2000c.json").read_text(encoding="utf-8"))["doi"] == "10.3/c"
    assert _no_temp_leftover(pdfs), "a temp rekey file leaked into pdfs/"


# === Fix 1: bib regex tolerates an indented closing brace ===================

def test_apply_rewrites_bib_entry_with_indented_closing_brace(tmp_path):
    # A references.bib whose entry closes on an INDENTED brace ("  }") must still
    # have its key rewritten (the end-anchor allows leading whitespace), and a
    # second, unrelated entry must be left untouched.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/joe", "author": "Joe", "year": "2026", "filename": "raw.pdf"},
    ], write_bib=False)
    # hand-write a bib: entry 1 (ours) closes with an indented brace; entry 2
    # (unmapped DOI) is a normal entry we expect to survive verbatim.
    bib = (
        "@article{joeorig,\n"
        "  author  = {Joe, Alice},\n"
        "  title   = {Title for 10.1/joe},\n"
        "  year    = {2026},\n"
        "  doi     = {10.1/joe}\n"
        "  }\n"                              # <-- indented closing brace
        "\n"
        "@article{other2000,\n"
        "  author  = {Other, B.},\n"
        "  year    = {2000},\n"
        "  doi     = {10.9/other}\n"
        "}\n"
    )
    (lit / "references.bib").write_text(bib, encoding="utf-8")

    res = assign_citation_keys(records, lit / "pdfs")
    apply_citation_keys(lit, records, res.mapping)
    out = (lit / "references.bib").read_text(encoding="utf-8")

    # our entry got keyed despite the indented closing brace
    assert "@article{Joe2026," in out
    assert "joeorig" not in out
    # its body is preserved
    assert "Joe, Alice" in out and "10.1/joe" in out
    # the unrelated entry is untouched
    assert "@article{other2000," in out
    assert "10.9/other" in out


# === Fix 2: over-long keys are capped (filename-length guard) ================

def test_normalize_surname_truncates_over_long_input():
    # A pathological 300-char author must not produce a 300-char filename
    # component (ENAMETOOLONG risk on rename). The surname is sliced to the cap;
    # deterministic and ASCII-safe.
    long_author = "A" * 300
    surname = normalize_surname(long_author)
    assert len(surname) <= MAX_KEY_LEN
    assert surname == "A" * MAX_KEY_LEN          # deterministic prefix slice
    assert surname.isascii()


def test_over_long_author_yields_safe_single_filename_component(tmp_path):
    # The assembled <surname><year> key stays a safe single path component well
    # under the ~255-byte filesystem limit.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.1/x", "author": "B" * 300, "year": "2026", "filename": "raw.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    key = res.mapping["10.1/x"]
    # surname capped + short year (+ no suffix here)
    assert len(key) <= MAX_KEY_LEN + len("2026")
    assert len(f"{key}.pdf") < 255
    assert "/" not in key and "\\" not in key and key.isascii()
    assert key.startswith("B" * MAX_KEY_LEN) and key.endswith("2026")


def test_truncated_keys_still_disambiguate_by_doi(tmp_path):
    # Two distinct papers whose 300-char authors share the same capped prefix
    # collapse to the same base key -> must still get a/b by DOI ascending.
    lit, records = _build_acquired_dir(tmp_path, [
        {"doi": "10.9/zzz", "author": "C" * 300, "year": "2026", "filename": "p2.pdf"},
        {"doi": "10.1/aaa", "author": "C" * 290 + "different",
         "year": "2026", "filename": "p1.pdf"},
    ])
    res = assign_citation_keys(records, lit / "pdfs")
    base = "C" * MAX_KEY_LEN + "2026"
    assert res.mapping["10.1/aaa"] == f"{base}a"   # lower DOI
    assert res.mapping["10.9/zzz"] == f"{base}b"   # higher DOI
    # each remains a safe filename component
    for key in res.mapping.values():
        assert len(f"{key}.pdf") < 255
