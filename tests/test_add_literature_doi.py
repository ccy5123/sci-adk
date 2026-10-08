"""Tests for ``sci-adk add-literature --doi`` (bind a user-supplied PDF to a recorded DOI).

When acquisition could not fetch a DOI's PDF, the run's ``literature/references.bib``
still holds that DOI's entry under its citation key (paperforge writes BibTeX for every
DOI; sci-adk only re-keys entries whose PDF arrived). ``--doi`` makes the PDF <-> bib
binding deterministic: the PDF is saved under the EXISTING key of the bib entry whose
DOI matches, instead of a fresh author/year key whose arrival-order suffix may not line
up with the bib's DOI-order suffix.

Fixtures reproduce the on-disk format the acquirer leaves behind: a multi-line
``references.bib`` (``DOI = {...}`` fields, as content negotiation returns them) and a
``manifest.csv`` with paperforge's column order.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.search.manual_literature import find_recorded_key, normalize_doi

_MANIFEST_HEADER = "index,doi,status,source,license,filename,origin,bib,error"

_ENTRIES = [
    # (key, doi) -- BOYD1982's odd casing is what the bib really carries.
    ("BOYD1982", "10.1111/j.2042-7158.1982.tb04730.x"),
    ("Smith2001", "10.1000/aaa.001"),
    ("Smith2001a", "10.1000/bbb.002"),
    ("Jones1999", "10.1000/ccc.003"),
]


def _bib_entry(key: str, doi: str) -> str:
    return (
        f"@article{{{key},\n"
        f"\ttitle = {{Title for {doi}}},\n"
        f"\turl = {{http://dx.doi.org/{doi}}},\n"
        f"\tDOI = {{{doi}}},\n"
        f"\tauthor = {{Someone, A}},\n"
        f"\tyear = {{2001}}\n"
        f"}}\n"
    )


def _make_run(tmp_path: Path) -> Path:
    """A run whose acquisition fetched Jones1999 and failed the other three DOIs."""
    run_dir = tmp_path / "runs" / "t-demo"
    lit = run_dir / "literature"
    pdfs = lit / "pdfs"
    pdfs.mkdir(parents=True)
    (pdfs / "Jones1999.pdf").write_bytes(b"%PDF-1.4\njones\n")
    (lit / "references.bib").write_text(
        "\n".join(_bib_entry(k, d) for k, d in _ENTRIES), encoding="utf-8"
    )
    rows = [
        _MANIFEST_HEADER,
        f"1,{_ENTRIES[0][1]},failed,,,,cli,ok,no OA PDF",
        f"2,{_ENTRIES[1][1]},failed,,,,cli,ok,no OA PDF",
        f"3,{_ENTRIES[2][1]},failed,,,,cli,ok,no OA PDF",
        f"4,{_ENTRIES[3][1]},success,unpaywall,cc-by,Jones1999.pdf,cli,ok,",
    ]
    (lit / "manifest.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return run_dir


def _pdf(tmp_path: Path, name: str, body: bytes = b"content") -> Path:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.7\n" + body)
    return p


def _manifest(run_dir: Path) -> tuple[list[str], list[dict]]:
    with open(run_dir / "literature" / "manifest.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# -- DOI normalisation + lookup (unit) -----------------------------------------


@pytest.mark.parametrize("raw", [
    "10.1000/AAA.001",
    "https://doi.org/10.1000/aaa.001",
    "http://dx.doi.org/10.1000/aaa.001",
    "doi:10.1000/aaa.001",
    "  DOI:10.1000/aaa.001 ",
])
def test_normalize_doi_strips_prefix_and_casefolds(raw: str) -> None:
    assert normalize_doi(raw) == "10.1000/aaa.001"


def test_find_recorded_key_reads_the_bib_entry_key(tmp_path: Path) -> None:
    lit = _make_run(tmp_path) / "literature"
    assert find_recorded_key(lit, "10.1111/J.2042-7158.1982.TB04730.X") == "BOYD1982"
    assert find_recorded_key(lit, "10.9999/not.recorded") is None


def test_find_recorded_key_without_bib_is_none(tmp_path: Path) -> None:
    assert find_recorded_key(tmp_path / "nope", "10.1000/aaa.001") is None


def test_find_recorded_key_ambiguous_doi_raises(tmp_path: Path) -> None:
    lit = tmp_path / "literature"
    lit.mkdir()
    (lit / "references.bib").write_text(
        _bib_entry("Smith2001", "10.1000/aaa.001") + "\n"
        + _bib_entry("Smith2001x", "10.1000/AAA.001"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        find_recorded_key(lit, "10.1000/aaa.001")


# -- the CLI verb: recorded DOI ------------------------------------------------


def test_known_doi_reuses_existing_key_with_odd_casing(tmp_path, capsys) -> None:
    run_dir = _make_run(tmp_path)
    src = _pdf(tmp_path, "boyd.pdf")
    rc = main(["add-literature", str(run_dir), "--pdf", str(src),
               "--doi", "10.1111/j.2042-7158.1982.tb04730.x"])
    assert rc == 0
    pdfs = run_dir / "literature" / "pdfs"
    assert (pdfs / "BOYD1982.pdf").exists()
    assert not (pdfs / "Boyd1982.pdf").exists()
    assert "BOYD1982" in capsys.readouterr().out


@pytest.mark.parametrize("order", [("bbb", "aaa"), ("aaa", "bbb")])
def test_same_base_entries_bound_by_doi_regardless_of_call_order(tmp_path, order) -> None:
    run_dir = _make_run(tmp_path)
    doi_of = {"aaa": "10.1000/aaa.001", "bbb": "10.1000/bbb.002"}
    for tag in order:
        src = _pdf(tmp_path, f"{tag}.pdf", body=tag.encode())
        rc = main(["add-literature", str(run_dir), "--pdf", str(src),
                   "--doi", doi_of[tag], "--author", "Smith", "--year", "2001"])
        assert rc == 0
    pdfs = run_dir / "literature" / "pdfs"
    assert (pdfs / "Smith2001.pdf").read_bytes().endswith(b"aaa")
    assert (pdfs / "Smith2001a.pdf").read_bytes().endswith(b"bbb")
    assert not (pdfs / "Smith2001A.pdf").exists()


def test_author_year_ignored_with_note_when_doi_recorded(tmp_path, capsys) -> None:
    run_dir = _make_run(tmp_path)
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "s.pdf")),
               "--doi", "10.1000/aaa.001", "--author", "Wrong", "--year", "1900"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ignored" in out
    assert not (run_dir / "literature" / "pdfs" / "Wrong1900.pdf").exists()


def test_si_flag_saves_key_si(tmp_path) -> None:
    run_dir = _make_run(tmp_path)
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "si.pdf")),
               "--doi", "10.1000/aaa.001", "--si"])
    assert rc == 0
    pdfs = run_dir / "literature" / "pdfs"
    assert (pdfs / "Smith2001_SI.pdf").exists()
    assert not (pdfs / "Smith2001.pdf").exists()
    # the manifest row describes the paper, not its SI -> untouched
    _fields, rows = _manifest(run_dir)
    assert rows[1]["status"] == "failed" and rows[1]["filename"] == ""


def test_manifest_row_updated_others_and_column_order_untouched(tmp_path) -> None:
    run_dir = _make_run(tmp_path)
    before_fields, before = _manifest(run_dir)
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "b.pdf")),
               "--doi", "10.1111/j.2042-7158.1982.tb04730.x"])
    assert rc == 0
    after_fields, after = _manifest(run_dir)
    assert after_fields == before_fields
    assert len(after) == len(before)
    row = after[0]
    assert row["filename"] == "BOYD1982.pdf"
    assert row["status"] == "success"
    assert row["source"] == "manual"
    assert row["error"] == ""
    # fields that describe the original input / bib outcome stay as recorded
    for col in ("index", "doi", "license", "origin", "bib"):
        assert row[col] == before[0][col]
    assert after[1:] == before[1:]


def test_doi_in_url_form_and_other_case_still_matches(tmp_path) -> None:
    run_dir = _make_run(tmp_path)
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "b.pdf")),
               "--doi", "https://doi.org/10.1000/BBB.002"])
    assert rc == 0
    assert (run_dir / "literature" / "pdfs" / "Smith2001a.pdf").exists()
    _f, rows = _manifest(run_dir)
    assert rows[2]["filename"] == "Smith2001a.pdf"


def test_existing_same_content_is_noop_success(tmp_path, capsys) -> None:
    run_dir = _make_run(tmp_path)
    src = _pdf(tmp_path, "b.pdf", body=b"same")
    args = ["add-literature", str(run_dir), "--pdf", str(src), "--doi", "10.1000/aaa.001"]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 0
    assert "already present" in capsys.readouterr().out
    assert len(list((run_dir / "literature" / "pdfs").glob("Smith2001*.pdf"))) == 1


def test_existing_different_content_exits_2_and_writes_nothing(tmp_path) -> None:
    run_dir = _make_run(tmp_path)
    lit = run_dir / "literature"
    (lit / "pdfs" / "Smith2001.pdf").write_bytes(b"%PDF-1.4\nolder\n")
    manifest_before = (lit / "manifest.csv").read_bytes()
    sha_before = _sha(lit / "pdfs" / "Smith2001.pdf")
    files_before = sorted(p.name for p in (lit / "pdfs").iterdir())

    rc = main(["add-literature", str(run_dir), "--pdf",
               str(_pdf(tmp_path, "new.pdf", body=b"different")),
               "--doi", "10.1000/aaa.001"])
    assert rc == 2
    assert _sha(lit / "pdfs" / "Smith2001.pdf") == sha_before
    assert (lit / "manifest.csv").read_bytes() == manifest_before
    assert sorted(p.name for p in (lit / "pdfs").iterdir()) == files_before


def test_non_pdf_file_rejected_on_doi_path(tmp_path) -> None:
    run_dir = _make_run(tmp_path)
    src = tmp_path / "page.pdf"
    src.write_bytes(b"<html>paywall</html>")
    rc = main(["add-literature", str(run_dir), "--pdf", str(src),
               "--doi", "10.1000/aaa.001"])
    assert rc == 2
    assert not (run_dir / "literature" / "pdfs" / "Smith2001.pdf").exists()


# -- the CLI verb: DOI not in the record -----------------------------------------


def test_unknown_doi_falls_back_to_provisional_key_with_note(tmp_path, capsys) -> None:
    run_dir = _make_run(tmp_path)
    manifest_before = (run_dir / "literature" / "manifest.csv").read_bytes()
    bib_before = (run_dir / "literature" / "references.bib").read_bytes()
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "n.pdf")),
               "--doi", "10.9999/not.recorded", "--author", "Niimi", "--year", "1986"])
    assert rc == 0
    assert (run_dir / "literature" / "pdfs" / "Niimi1986.pdf").exists()
    out = capsys.readouterr().out
    assert "not found" in out and "provisional" in out
    # no bib entry invented, manifest untouched
    assert (run_dir / "literature" / "references.bib").read_bytes() == bib_before
    assert (run_dir / "literature" / "manifest.csv").read_bytes() == manifest_before


def test_doi_with_no_literature_record_at_all_is_provisional(tmp_path, capsys) -> None:
    run_dir = tmp_path / "runs" / "empty"
    run_dir.mkdir(parents=True)
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "n.pdf")),
               "--doi", "10.9999/x", "--author", "Niimi", "--year", "1986"])
    assert rc == 0
    assert (run_dir / "literature" / "pdfs" / "Niimi1986.pdf").exists()
    assert "not found" in capsys.readouterr().out


# -- without --doi: unchanged ---------------------------------------------------


def test_without_doi_behaviour_unchanged_even_with_a_record(tmp_path, capsys) -> None:
    run_dir = _make_run(tmp_path)
    manifest_before = (run_dir / "literature" / "manifest.csv").read_bytes()
    rc = main(["add-literature", str(run_dir), "--pdf", str(_pdf(tmp_path, "b.pdf")),
               "--author", "Boyd", "--year", "1982"])
    assert rc == 0
    assert (run_dir / "literature" / "pdfs" / "Boyd1982.pdf").exists()
    assert (run_dir / "literature" / "manifest.csv").read_bytes() == manifest_before
    assert "not found" not in capsys.readouterr().out
