"""Tests for manual literature ingest key naming (src/sci_adk/search/manual_literature.py).

Covers the manual (DOI-less) naming scheme: base key, arrival-order UPPERCASE
disambiguation (bare, A, B, …), _SI as a same-key variant that disambiguates only
among SI files, institutional authors, and Anon/nd fallbacks.
"""

from __future__ import annotations

from pathlib import Path

from sci_adk.search.manual_literature import (
    SI_SUFFIX,
    _upper_suffix,
    assign_manual_key,
)


def _touch(pdfs_dir: Path, *stems: str) -> None:
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    for s in stems:
        (pdfs_dir / f"{s}.pdf").write_bytes(b"%PDF-1.4\n")


# -- base key ---------------------------------------------------------------


def test_single_paper_is_bare(tmp_path: Path) -> None:
    assert assign_manual_key(tmp_path / "pdfs", "Niimi", "1986") == "Niimi1986"


def test_institutional_author(tmp_path: Path) -> None:
    assert assign_manual_key(tmp_path / "pdfs", "OECD", "2012") == "OECD2012"


def test_anon_and_nd_fallbacks(tmp_path: Path) -> None:
    assert assign_manual_key(tmp_path / "pdfs", None, "2012") == "Anon2012"
    assert assign_manual_key(tmp_path / "pdfs", "Oliver", None) == "Olivernd"
    assert assign_manual_key(tmp_path / "pdfs", "  ", "  ") == "Anonnd"


# -- arrival-order UPPERCASE disambiguation ---------------------------------


def test_collision_arrival_order_uppercase(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    _touch(pdfs, "Niimi1986")               # first already saved (bare)
    assert assign_manual_key(pdfs, "Niimi", "1986") == "Niimi1986A"
    _touch(pdfs, "Niimi1986A")
    assert assign_manual_key(pdfs, "Niimi", "1986") == "Niimi1986B"


def test_existing_files_are_not_rekeyed(tmp_path: Path) -> None:
    # assign is pure/read-only: it never touches the bare first file.
    pdfs = tmp_path / "pdfs"
    _touch(pdfs, "Oliver1985")
    assign_manual_key(pdfs, "Oliver", "1985")
    assert (pdfs / "Oliver1985.pdf").exists()


# -- _SI as a same-key variant ----------------------------------------------


def test_si_is_bare_and_coexists_with_paper(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    _touch(pdfs, "Niimi1986")  # the paper already exists (non-SI)
    # the SI does NOT get an A suffix just because the non-SI base exists
    assert assign_manual_key(pdfs, "Niimi", "1986", is_si=True) == "Niimi1986_SI"


def test_si_disambiguates_among_si_only(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    _touch(pdfs, "Niimi1986", "Niimi1986_SI")
    assert assign_manual_key(pdfs, "Niimi", "1986", is_si=True) == "Niimi1986A_SI"


def test_paper_after_si_still_ignores_si_count(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    _touch(pdfs, "Niimi1986_SI")  # only an SI on disk, no paper yet
    # a non-SI paper ignores the SI file when counting -> bare
    assert assign_manual_key(pdfs, "Niimi", "1986") == "Niimi1986"


# -- suffix boundaries ------------------------------------------------------


def test_upper_suffix_bijective_base26() -> None:
    assert _upper_suffix(0) == "A"
    assert _upper_suffix(25) == "Z"
    assert _upper_suffix(26) == "AA"


def test_si_suffix_constant() -> None:
    assert SI_SUFFIX == "_SI"


# -- the `add-literature` CLI verb (integration) ----------------------------


def _make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "t-demo"
    run_dir.mkdir(parents=True)
    return run_dir


def _src_pdf(tmp_path: Path, name: str = "incoming.pdf") -> Path:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4\nmanual\n")
    return p


def test_cli_saves_under_bibkey(tmp_path: Path) -> None:
    from sci_adk.cli import main

    run_dir = _make_run(tmp_path)
    src = _src_pdf(tmp_path)
    rc = main(["add-literature", str(run_dir), "--pdf", str(src),
               "--author", "Niimi", "--year", "1986"])
    assert rc == 0
    assert (run_dir / "literature" / "pdfs" / "Niimi1986.pdf").exists()


def test_cli_collision_gets_uppercase(tmp_path: Path) -> None:
    from sci_adk.cli import main

    run_dir = _make_run(tmp_path)
    for _ in range(2):
        main(["add-literature", str(run_dir), "--pdf", str(_src_pdf(tmp_path)),
              "--author", "Niimi", "--year", "1986"])
    pdfs = run_dir / "literature" / "pdfs"
    assert (pdfs / "Niimi1986.pdf").exists()
    assert (pdfs / "Niimi1986A.pdf").exists()


def test_cli_si_flag(tmp_path: Path) -> None:
    from sci_adk.cli import main

    run_dir = _make_run(tmp_path)
    rc = main(["add-literature", str(run_dir), "--pdf", str(_src_pdf(tmp_path)),
               "--author", "Niimi", "--year", "1986", "--si"])
    assert rc == 0
    assert (run_dir / "literature" / "pdfs" / "Niimi1986_SI.pdf").exists()


def test_cli_missing_file_exits_2(tmp_path: Path) -> None:
    from sci_adk.cli import main

    run_dir = _make_run(tmp_path)
    rc = main(["add-literature", str(run_dir), "--pdf", str(tmp_path / "nope.pdf"),
               "--author", "Niimi", "--year", "1986"])
    assert rc == 2
