"""
Sequential acquisition calls into ONE run's ``literature/`` dir must accumulate.

paperforge (the external acquisition tool) keeps ``manifest.csv`` across calls but
REWRITES ``references.bib`` from scratch with only the current call's DOIs. Every
recorder (prior-work, novelty, contested, inquiry) acquires into the same
``runs/<id>/literature/``, so without a merge a later call silently drops every
earlier citation. These tests drive :class:`LiteratureAcquirer` with a network-free
simulator of paperforge's real file behaviour (``PaperforgeSim``) and pin:

  * the bib after each call is the union (earlier entries kept verbatim);
  * a key, once assigned, never changes (a re-requested DOI keeps key + text);
  * a newcomer whose base key is already used gets the next free suffix, and no
    earlier PDF/sidecar is renamed or overwritten;
  * entries/PDFs with no DOI (manual ingest) survive;
  * the LITERATURE evidence and the halt cover only the DOIs of THIS call;
  * the merged bib passes the repo's brace-integrity rule with no duplicate keys.
"""

from __future__ import annotations

import csv
import io
import json
import re
import types
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from sci_adk.loop.literature_acquirer import LiteratureAcquirer
from sci_adk.loop.verify import _braces_balanced
from sci_adk.render.pkgreqs_checks import bib_keys
from sci_adk.search.literature_merge import parse_bib_entries
from sci_adk.search.manual_literature import normalize_doi
from sci_adk.search.paperforge_adapter import AcquisitionResult, PaperforgeAdapter

PIN = "60fefedacb7349c755c29b2c2f26873464158c12"
_MANIFEST_FIELDS = ["index", "doi", "status", "source", "license",
                    "filename", "origin", "bib", "error"]


def _pdf(text: str) -> bytes:
    """A one-page, text-extractable PDF drawing ``text`` (distinct bytes per paper)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class PaperforgeSim:
    """Network-free stand-in reproducing paperforge's on-disk behaviour.

    Mirrors ``paperforge/orchestrator.py`` + ``downloader.py``:
      * ``manifest.csv`` is loaded and ACCUMULATED (prior rows kept; a prior
        ``success`` row is skipped, not re-downloaded, unless ``overwrite``);
      * PDFs are saved as ``<Author><Year>[a/b].pdf`` + ``.json`` sidecar, never
        clobbering a file that belongs to a different DOI (sidecar DOI check);
      * ``references.bib`` is REWRITTEN from scratch with one entry per DOI of
        THIS call only, keys unique within the call only.

    ``catalog`` maps DOI -> dict(author, year, available, title).
    """

    def __init__(self, catalog: dict[str, dict]):
        self.catalog = catalog
        self.calls: list[list[str]] = []

    @staticmethod
    def _unique_pdf(pdfs: Path, base: str, doi: str) -> Path:
        for suffix in ["", *"abcdefghijklmnopqrstuvwxyz"]:
            path = pdfs / f"{base}{suffix}.pdf"
            if not path.exists():
                return path
            sidecar = path.with_suffix(".json")
            if sidecar.exists():
                prev = json.loads(sidecar.read_text(encoding="utf-8"))
                if (prev.get("doi") or "").lower() == doi.lower():
                    return path
        raise AssertionError("suffixes exhausted")

    def fetch(self, dois, output_dir, overwrite=False, **_options):
        self.calls.append(list(dois))
        out = Path(output_dir)
        pdfs = out / "pdfs"
        pdfs.mkdir(parents=True, exist_ok=True)
        manifest = out / "manifest.csv"
        rows: dict[str, dict] = {}
        if manifest.exists():
            with open(manifest, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    rows[row["doi"].lower()] = row

        bib_keys_used: set[str] = set()
        entries: list[str] = []
        this_call: list[str] = []
        for index, raw in enumerate(dois, start=1):
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", raw.strip())
            this_call.append(doi.lower())
            meta = self.catalog[doi.lower()]
            prev = rows.get(doi.lower())
            base = f"{meta['author']}{meta['year']}"
            if prev and prev["status"] == "success" and not overwrite:
                row = dict(prev)
            elif meta.get("available", True):
                path = self._unique_pdf(pdfs, base, doi)
                path.write_bytes(_pdf(doi))
                path.with_suffix(".json").write_text(json.dumps(
                    {"doi": doi, "author": meta["author"], "year": meta["year"]}),
                    encoding="utf-8")
                row = {"index": index, "doi": doi, "status": "success",
                       "source": "unpaywall", "license": "cc-by",
                       "filename": path.name, "origin": "cli", "error": ""}
            else:
                row = {"index": index, "doi": doi, "status": "failed",
                       "source": "", "license": "", "filename": "",
                       "origin": "cli", "error": "no OA PDF"}
            key = base
            for suffix in "abcdefghijklmnopqrstuvwxyz":
                if key not in bib_keys_used:
                    break
                key = f"{base}{suffix}"
            bib_keys_used.add(key)
            entries.append(
                f"@article{{{key},\n"
                f"  author = {{{meta['author']}, A.}},\n"
                f"  title = {{{meta.get('title', 'A study of {X}')}}},\n"
                f"  year = {{{meta['year']}}},\n"
                f"  doi = {{{doi}}}\n}}\n")
            row["bib"] = "ok"
            rows[doi.lower()] = row

        (out / "references.bib").write_text("\n".join(entries), encoding="utf-8")
        with open(manifest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_MANIFEST_FIELDS)
            w.writeheader()
            for row in rows.values():
                w.writerow({k: row.get(k, "") for k in _MANIFEST_FIELDS})

        rc = 0 if all(rows[d]["status"] == "success" for d in this_call) else 1
        return AcquisitionResult(
            returncode=rc,
            output_dir=out,
            manifest_path=manifest,
            # like the real adapter: the WHOLE accumulated manifest
            records=PaperforgeAdapter.parse_manifest(manifest),
            provenance={"tool": "paperforge", "pinned_sha": PIN,
                        "installed_version": "0.1.0", "returncode": rc},
        )


def _spec():
    return types.SimpleNamespace(id="acc-spec")


def _lit(tmp_path: Path) -> Path:
    return tmp_path / "runs" / "acc-spec" / "literature"


def _bib(tmp_path: Path) -> str:
    return (_lit(tmp_path) / "references.bib").read_text(encoding="utf-8")


def _entry_count(bib: str) -> int:
    return bib.count("\n@") + (1 if bib.lstrip().startswith("@") else 0)


def _acquirer(tmp_path: Path, sim: PaperforgeSim) -> LiteratureAcquirer:
    return LiteratureAcquirer(_spec(), workspace_dir=tmp_path, adapter=sim)


def _manifest_filenames(tmp_path: Path) -> dict[str, str]:
    with open(_lit(tmp_path) / "manifest.csv", newline="", encoding="utf-8") as f:
        return {r["doi"]: r["filename"] for r in csv.DictReader(f)}


# -- the data-loss bug -------------------------------------------------------


def test_second_call_with_disjoint_dois_keeps_every_earlier_entry(tmp_path):
    sim = PaperforgeSim({
        "10.1/a": {"author": "Smith", "year": "2001"},
        "10.1/b": {"author": "Jones", "year": "1999"},
        "10.1/c": {"author": "Brown", "year": "2010"},
    })
    acq = _acquirer(tmp_path, sim)
    acq.acquire(["10.1/a", "10.1/b"])
    after_first = _bib(tmp_path)

    acq.acquire(["10.1/c"])

    bib = _bib(tmp_path)
    assert bib_keys(bib) == ["Brown2010", "Jones1999", "Smith2001"]
    assert after_first.strip() in bib  # earlier entries kept verbatim
    pdfs = _lit(tmp_path) / "pdfs"
    for stem in ("Smith2001", "Jones1999", "Brown2010"):
        assert (pdfs / f"{stem}.pdf").exists()
        assert (pdfs / f"{stem}.json").exists()


def test_rerequested_doi_keeps_its_key_and_entry_text(tmp_path):
    sim = PaperforgeSim({
        "10.1/a": {"author": "Smith", "year": "2001", "title": "Original title"},
        "10.1/b": {"author": "Jones", "year": "1999"},
    })
    acq = _acquirer(tmp_path, sim)
    acq.acquire(["10.1/a", "10.1/b"])
    first = _bib(tmp_path)

    # the metadata service now returns different text for the same DOI
    sim.catalog["10.1/a"]["title"] = "Re-fetched title"
    acq.acquire(["10.1/a"])

    bib = _bib(tmp_path)
    assert bib_keys(bib) == ["Jones1999", "Smith2001"]
    assert bib.count("10.1/a") == 1
    assert "Original title" in bib and "Re-fetched title" not in bib
    assert first.strip() in bib


# -- cross-call key collisions ------------------------------------------------


def test_same_author_year_in_a_later_call_gets_a_fresh_key(tmp_path):
    # the newcomer's DOI sorts LOWER, so a whole-set a/b-by-DOI re-key would
    # rename the earlier paper; its key must not move.
    sim = PaperforgeSim({
        "10.5/early": {"author": "Smith", "year": "2001"},
        "10.1/late": {"author": "Smith", "year": "2001"},
    })
    acq = _acquirer(tmp_path, sim)
    acq.acquire(["10.5/early"])
    pdfs = _lit(tmp_path) / "pdfs"
    early_bytes = (pdfs / "Smith2001.pdf").read_bytes()

    outcome = acq.acquire(["10.1/late"])

    assert outcome.citation_keys == {"10.1/late": "Smith2001a"}
    assert (pdfs / "Smith2001.pdf").read_bytes() == early_bytes
    assert json.loads((pdfs / "Smith2001.json").read_text())["doi"] == "10.5/early"
    assert json.loads((pdfs / "Smith2001a.json").read_text())["doi"] == "10.1/late"
    assert (pdfs / "Smith2001a.pdf").read_bytes() != early_bytes
    bib = _bib(tmp_path)
    assert bib_keys(bib) == ["Smith2001", "Smith2001a"]
    assert _entry_count(bib) == 2
    names = _manifest_filenames(tmp_path)
    assert names == {"10.5/early": "Smith2001.pdf", "10.1/late": "Smith2001a.pdf"}


def test_failed_newcomer_bib_key_does_not_duplicate_an_existing_key(tmp_path):
    # a DOI with no OA PDF still gets a bib entry; paperforge keys it per call,
    # so its key would duplicate the earlier Smith2001.
    sim = PaperforgeSim({
        "10.1/a": {"author": "Smith", "year": "2001"},
        "10.1/miss": {"author": "Smith", "year": "2001", "available": False},
    })
    acq = _acquirer(tmp_path, sim)
    acq.acquire(["10.1/a"])
    acq.acquire(["10.1/miss"])

    bib = _bib(tmp_path)
    assert bib_keys(bib) == ["Smith2001", "Smith2001a"]
    assert _entry_count(bib) == 2


def test_manual_pdfs_and_no_doi_entries_survive_and_block_their_keys(tmp_path):
    lit = _lit(tmp_path)
    pdfs = lit / "pdfs"
    pdfs.mkdir(parents=True)
    # add-literature (no DOI) leaves bare + provisional UPPERCASE stems, no sidecar
    (pdfs / "Smith2001.pdf").write_bytes(b"%PDF-1.4 manual one")
    (pdfs / "Smith2001A.pdf").write_bytes(b"%PDF-1.4 manual two")
    oecd = "@techreport{OECD2012,\n  title = {Test No. 305},\n  year = {2012}\n}"
    (lit / "references.bib").write_text(oecd + "\n", encoding="utf-8")

    sim = PaperforgeSim({"10.1/new": {"author": "Smith", "year": "2001"}})
    outcome = _acquirer(tmp_path, sim).acquire(["10.1/new"])

    # BibTeX keys and some filesystems are case-insensitive: Smith2001a would
    # clash with Smith2001A, so the newcomer takes the next free suffix.
    assert outcome.citation_keys == {"10.1/new": "Smith2001b"}
    assert (pdfs / "Smith2001.pdf").read_bytes() == b"%PDF-1.4 manual one"
    assert (pdfs / "Smith2001A.pdf").read_bytes() == b"%PDF-1.4 manual two"
    assert (pdfs / "Smith2001b.pdf").exists()
    bib = _bib(tmp_path)
    assert oecd in bib
    assert bib_keys(bib) == ["OECD2012", "Smith2001b"]


def test_doi_recorded_before_the_fix_without_a_bib_entry_keeps_its_file_key(tmp_path):
    # a run already hit by the bug: manifest + PDF for 10.1/a under Smith2001,
    # but its bib entry was lost. Re-requesting it restores the entry under the
    # key the PDF (and any manuscript) already uses.
    sim = PaperforgeSim({
        "10.1/a": {"author": "Smith", "year": "2001"},
        "10.1/b": {"author": "Jones", "year": "1999"},
    })
    acq = _acquirer(tmp_path, sim)
    acq.acquire(["10.1/a", "10.1/b"])
    (_lit(tmp_path) / "references.bib").write_text("", encoding="utf-8")

    acq.acquire(["10.1/a"])

    assert bib_keys(_bib(tmp_path)) == ["Smith2001"]


# -- call scope of the record and the halt -----------------------------------


def test_evidence_and_halt_cover_only_this_calls_dois(tmp_path):
    catalog = {f"10.1/old{i}": {"author": f"Old{i}", "year": "2000",
                                "available": i % 2 == 0} for i in range(6)}
    catalog["10.1/new"] = {"author": "New", "year": "2020"}
    catalog["10.1/gone"] = {"author": "Gone", "year": "2021", "available": False}
    sim = PaperforgeSim(catalog)
    acq = _acquirer(tmp_path, sim)
    acq.acquire([f"10.1/old{i}" for i in range(6)])

    outcome = acq.acquire(["10.1/new"])
    summary = json.loads(outcome.evidence.result.finding)
    assert [a["doi"] for a in summary["acquired"]] == ["10.1/new"]
    assert summary["failed"] == []
    assert summary["counts"] == {"succeeded": 1, "failed": 0}
    assert outcome.halt is None
    assert [r.doi for r in outcome.result.records] == ["10.1/new"]
    assert [n.path.name for n in outcome.normalizations] == ["New2020.pdf"]

    outcome = acq.acquire(["https://doi.org/10.1/GONE"])
    assert outcome.halt is not None
    assert [normalize_doi(it.doi) for it in outcome.halt.items] == ["10.1/gone"]
    assert json.loads(outcome.evidence.result.finding)["counts"] == {
        "succeeded": 0, "failed": 1}


# -- validity of the merged file ---------------------------------------------


def test_merged_bib_is_brace_balanced_with_unique_keys(tmp_path):
    lit = _lit(tmp_path)
    lit.mkdir(parents=True)
    tricky = ("@article{Prior1990,\n  title = {The {DNA} of {\\em E. coli}},\n"
              "  note = {see @inbook{X, y} here},\n  doi = {10.9/prior}\n}\n")
    (lit / "references.bib").write_text(tricky, encoding="utf-8")
    sim = PaperforgeSim({
        "10.9/prior": {"author": "Prior", "year": "1990"},
        "10.1/a": {"author": "Lee", "year": "2005", "title": "Nested {B}races"},
        "10.1/b": {"author": "Lee", "year": "2005"},
    })
    acq = _acquirer(tmp_path, sim)
    acq.acquire(["10.1/a", "10.9/prior"])
    acq.acquire(["10.1/b", "10.1/a"])

    bib = _bib(tmp_path)
    assert _braces_balanced(bib)
    assert tricky.strip() in bib
    # entry-level split (brace-depth aware): the "@inbook{X," inside the note is
    # field text, not an entry -- pkgreqs_checks.bib_keys would count it.
    keys = [e.key for e in parse_bib_entries(bib)]
    headers = [line for line in bib.splitlines() if line.startswith("@")]
    assert len(keys) == len(set(keys)) == len(headers) == 3
    assert sorted(keys) == ["Lee2005", "Lee2005a", "Prior1990"]
