"""
Article-numbered journals: a cited article with a journal and a volume but no pages.

BibTeX from doi.org content negotiation (Crossref's registrar BibTeX, the store's source) has
no field for the article number a journal such as the Journal of Cheminformatics gives each
paper in place of a page range. The trial run (lit-search-trial-2, SPEC-BCFKOW-001) printed
Mansouri et al. (J Cheminform (2018) 10:10) as "Journal of Cheminformatics, 10 (1), March
2018": where in volume 10 the article is was lost. sci-adk's acquisition path never sees
Crossref's JSON metadata (the paperforge sidecar keeps only title, first author and year), so
the article number cannot be filled in automatically: verify names each such cited entry in a
non-gating advisory and says to add the number as ``pages = {<n>}`` to the store entry.

The entries come from tests/fixtures/bib_trial2/references.bib, a byte copy of the trial's
``literature/references.bib`` (Mansouri2018 is line 47 there and here).
"""

from __future__ import annotations

import pytest

from sci_adk.render.bib_latex import paper_bib
from sci_adk.render.pkgreqs_checks import bib_article_number_advisories
from tests.test_bib_latex_copy import _TRIAL_BIB, _compile_with_bib, needs_tex

_STORE = _TRIAL_BIB.read_text(encoding="utf-8")
_PREFIX = "bib article number:"


def _store_entry(key: str) -> str:
    """The trial store's entry ``key`` (one entry per line in the store)."""
    return next(line for line in _STORE.splitlines() if line.startswith("@") and f"{{{key}," in line)


_MANSOURI = _store_entry("Mansouri2018")


def test_the_trial_mansouri_entry_gets_one_advisory_line():
    lines = bib_article_number_advisories(r"\citep{Mansouri2018}", _MANSOURI + "\n")
    assert len(lines) == 1, lines
    line = lines[0]
    assert line.startswith(_PREFIX)
    assert "references.bib" in line and "'Mansouri2018'" in line
    assert "pages = {<n>}" in line  # the field to add, with the number left to the author
    assert "literature store" in line  # where the fix goes by default


def test_the_paper_copy_of_the_entry_is_flagged_too():
    # verify reads render's paper/ copy, which keeps journal and volume and adds no pages.
    lines = bib_article_number_advisories(r"\cite{Mansouri2018}", paper_bib(_MANSOURI + "\n"))
    assert len(lines) == 1 and "'Mansouri2018'" in lines[0], lines


def test_over_the_whole_trial_store_only_the_two_article_numbered_entries_are_named():
    # Measured on the trial store: 36 articles, 4 inbooks; only the two Journal of
    # Cheminformatics articles lack pages.
    from sci_adk.render.pkgreqs_checks import bib_keys

    every_key = r"\citep{" + ",".join(bib_keys(_STORE)) + "}"
    lines = bib_article_number_advisories(every_key, _STORE)
    named = sorted(line.split("'")[1] for line in lines)
    assert named == ["Krotko2020", "Mansouri2018"], lines


def test_an_uncited_entry_is_not_named():
    assert bib_article_number_advisories(r"\citep{Arnot2006}", _STORE) == []
    assert bib_article_number_advisories("no citations", _MANSOURI) == []


@pytest.mark.parametrize(
    "added",
    ["pages={10}", "pages = 10", "eid={10}", "Pages={10}"],
    ids=["pages", "bare-pages", "eid", "upper-case-name"],
)
def test_an_entry_with_pages_or_an_eid_is_not_named(added):
    # plainnat prints both after the volume and issue (measured below).
    entry = _MANSOURI.replace("number={1},", f"number={{1}}, {added},")
    assert added in entry
    assert bib_article_number_advisories(r"\cite{Mansouri2018}", entry) == []


def test_an_articleno_alone_is_still_named():
    # ACM's articleno field: plainnat does not print it (measured below), so the reference
    # list still lacks the number.
    entry = _MANSOURI.replace("number={1},", "number={1}, articleno={10},")
    lines = bib_article_number_advisories(r"\cite{Mansouri2018}", entry)
    assert len(lines) == 1 and "pages = {<n>}" in lines[0], lines


def test_an_empty_pages_field_counts_as_no_pages():
    entry = _MANSOURI.replace("number={1},", "number={1}, pages={ },")
    assert len(bib_article_number_advisories(r"\cite{Mansouri2018}", entry)) == 1


@pytest.mark.parametrize(
    "entry",
    [
        "@article{X2020, title={T}, journal={J}, year={2020}}",  # no volume
        "@article{X2020, title={T}, volume={3}, year={2020}}",  # no journal
        "@inbook{X2020, title={T}, journal={J}, volume={3}, year={2020}}",  # not an article
        "@article{X2020, title={T}, journal={}, volume={3}, year={2020}}",  # empty journal
    ],
    ids=["no-volume", "no-journal", "inbook", "empty-journal"],
)
def test_only_an_article_with_a_journal_and_a_volume_is_named(entry):
    assert bib_article_number_advisories(r"\cite{X2020}", entry) == []


def test_a_bare_volume_and_an_upper_case_entry_type_count():
    entry = "@Article{X2020, title={T}, journal={J}, volume=3, year={2020}}"
    assert len(bib_article_number_advisories(r"\cite{X2020}", entry)) == 1


def test_a_field_name_inside_another_value_is_not_a_field():
    # 'pages = 5' inside the title is text, not the entry's pages field.
    entry = "@article{X2020, title={On pages = 5 of it}, journal={J}, volume={3}, year={2020}}"
    assert len(bib_article_number_advisories(r"\cite{X2020}", entry)) == 1


def test_the_fix_location_and_source_name_are_the_callers():
    lines = bib_article_number_advisories(
        r"\cite{Mansouri2018}",
        _MANSOURI,
        source="references_SI.bib",
        fix_in="package_src/references_SI.bib, which the package copies unchanged",
    )
    assert len(lines) == 1, lines
    assert "references_SI.bib entry 'Mansouri2018'" in lines[0]
    assert "package_src/references_SI.bib, which the package copies unchanged" in lines[0]


@needs_tex
def test_without_pages_the_reference_list_loses_the_article_number(tmp_path):
    # The premise, measured with bibtex + plainnat: no number after the issue without pages,
    # "(1):\penalty0 10" once the store entry carries pages = {10} or eid = {10}, still none
    # with ACM's articleno = {10}.
    (tmp_path / "a").mkdir()
    errors, bbl, dropped = _compile_with_bib(tmp_path / "a", paper_bib(_MANSOURI + "\n"), False)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    assert "10\\penalty0 (1), March 2018" in bbl, bbl

    for name, printed in (("pages", True), ("eid", True), ("articleno", False)):
        fixed = _MANSOURI.replace("number={1},", f"number={{1}}, {name}={{10}},")
        (tmp_path / name).mkdir()
        errors, bbl, dropped = _compile_with_bib(tmp_path / name, paper_bib(fixed + "\n"), False)
        assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
        assert ("10\\penalty0 (1):\\penalty0 10" in bbl) is printed, (name, bbl)


# -- verify: per-run paper_advisory and the package gate's warnings ----------------------------


def test_per_run_verify_carries_the_advisory_and_names_the_literature_store(tmp_path):
    from sci_adk.loop.verify import verify_run
    from tests.test_paper_gate_enforcement import _draft, _freeze_pubreqs, _write_run

    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    _draft(run_dir, r"\section{Results}As shown \citep{Mansouri2018}, the value is 0.61.")
    store = run_dir / "literature" / "references.bib"
    store.parent.mkdir(parents=True)
    store.write_text(_MANSOURI + "\n", encoding="utf-8")
    (run_dir / "paper" / "references.bib").write_text(paper_bib(_MANSOURI + "\n"), encoding="utf-8")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)

    report = verify_run(run_dir)
    lines = [n for n in report.paper_advisory if n.startswith(_PREFIX)]
    assert len(lines) == 1, report.paper_advisory
    assert "'Mansouri2018'" in lines[0] and "literature/references.bib" in lines[0]
    assert "re-render" in lines[0]
    assert not any(_PREFIX in p for p in report.paper_requirements_problems)


def test_per_run_verify_checks_the_si_bibliography_against_si_tex(tmp_path):
    from sci_adk.loop.verify import verify_run
    from tests.test_paper_gate_enforcement import _draft, _freeze_pubreqs, _write_run

    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    _draft(run_dir, r"\section{Results}The value is 0.61.")
    (run_dir / "paper" / "si.tex").write_text(r"Methods follow \citet{Mansouri2018}.", encoding="utf-8")
    (run_dir / "paper" / "references_SI.bib").write_text(
        paper_bib(_MANSOURI + "\n"), encoding="utf-8"
    )
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)

    report = verify_run(run_dir)
    lines = [n for n in report.paper_advisory if n.startswith(_PREFIX)]
    assert len(lines) == 1, report.paper_advisory
    assert "references_SI.bib entry 'Mansouri2018'" in lines[0]


def test_package_verify_carries_the_advisory_as_a_warning(tmp_path):
    from sci_adk.loop.verify import _check_package_requirements
    from tests.test_si_authoring_m6 import _POOL_BIB
    from tests.test_si_bib_integrity import _assemble_pkg_with_bibs

    si_bib = "@article{A2020, title={Alpha}, journal={J}, volume={3}, doi={10.1/a}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(tmp_path, main_bib=_POOL_BIB, si_bib=si_bib)
    problems, warnings, _runs, _repro = _check_package_requirements(ws, ws / "package", pkgreqs)
    lines = [w for w in warnings if w.startswith(_PREFIX)]
    assert len(lines) == 1, warnings
    assert "references_SI.bib entry 'A2020'" in lines[0]
    assert "package_src/references_SI.bib" in lines[0]
    assert not any(_PREFIX in p for p in problems)
