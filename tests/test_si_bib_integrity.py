"""
SPEC-SI-AUTHORING-001 M6 hardening (RED-first): two defects/gaps in the M6 bib path.

Part A -- ``bib_subset`` must be BRACE-DEPTH AWARE. The naive "next @header = entry end"
slice truncates an entry whose field value contains a literal ``@word{...}``-shaped token
(e.g. ``note = {... @inbook{X, y} ...}``), emitting a brace-unbalanced, field-losing entry.

Part B -- the verify gate must validate the INTEGRITY of BOTH ``references.bib`` (main) AND
``references_SI.bib`` (SI): a PRESENT-but-brace-unbalanced bib must FAIL the gate (per-run +
package), naming the offending file. A MISSING bib is not a failure (thin/absent SI stays
clean). The user's requirement: "references는 _SI도 따로 있기에 둘 다 검정해야함".

Plus: the ``_colocate_si_bib`` empty-subset branch (all cited keys dangling / absent from the
pool -> empty subset -> NO ``references_SI.bib`` written) -- a previously-untested branch.

Design source: design/si-bibliography.md (§6 hardening). All tests PURE / deterministic /
no-LLM (no Docker, no real compile of the bib -- brace balance is the coarse compile signal).
"""

from __future__ import annotations

import json
from pathlib import Path

# Reuse the established M6 fixtures (same inputs the M6 tests use -- do not re-author them).
from tests.test_si_authoring_m6 import (
    _AUTHOR_SI_HEAD,
    _POOL_BIB,
    _compile,
    _pkg_si_bib,
    _pkg_si_tex,
    _pkgreqs_obj,
    _seed_pool,
    _seed_workspace,
    _si_citing,
    _freeze_pkgreqs,
)

from sci_adk.render.pkgreqs_checks import bib_keys, bib_subset, cite_resolution_problems


# ===========================================================================
# Part A -- bib_subset is brace-depth aware
# ===========================================================================

# A pool entry whose ``note`` field embeds a literal ``@inbook{...}``-shaped token: the naive
# "next @header = entry end" slice ends the Smith2020 entry at that fake header, dropping
# ``year = {2020}`` and the true closing brace.
_POISONED_POOL = (
    "@article{Smith2020,\n"
    "  author = {Smith, J.},\n"
    "  title = {A title},\n"
    "  note = {See also the @inbook{ShouldNotBeAKey, x=y} example},\n"
    "  year = {2020}\n"
    "}\n"
    "@article{Jones2019,\n"
    "  title = {Jones},\n"
    "  year = {2019}\n"
    "}\n"
)


def _balanced(bib: str) -> bool:
    return bib.count("{") == bib.count("}")


def test_bib_subset_keeps_full_entry_with_at_token_in_field():
    """RED: a pool entry whose note field carries a literal @word{...} token must be kept
    COMPLETE (brace-balanced, all fields incl. year = {2020}); the uncited Jones2019 out."""
    sub = bib_subset(_POISONED_POOL, ["Smith2020"])
    # kept entry is brace-balanced (no truncation at the fake @inbook header)
    assert _balanced(sub), f"kept entry must be brace-balanced, got: {sub!r}"
    # all original fields survived -- year = {2020} is the field the naive slice dropped
    assert "year = {2020}" in sub
    assert "author = {Smith, J.}" in sub
    assert "title = {A title}" in sub
    # the embedded @inbook{...} token stays INSIDE the note field (part of the kept entry),
    # it is not sliced off as its own chunk nor does it truncate the entry.
    assert "note = {See also the @inbook{ShouldNotBeAKey, x=y} example}" in sub
    # exactly ONE kept entry, and it is Smith2020 (Smith2020 is the only top-level @-header
    # that begins a kept chunk; the uncited Jones2019 is excluded).
    assert sub.count("@article{Smith2020,") == 1
    assert "Jones2019" not in sub


def test_bib_subset_at_token_entry_cite_gate_not_falsely_clean():
    """RED: with the truncation bug the SI cite gate FALSELY reports clean; a correct,
    complete subset resolves the cite cleanly (the entry is really there and balanced)."""
    sub = bib_subset(_POISONED_POOL, ["Smith2020"])
    # Smith2020 really resolves -- and the subset is not a mangled fragment.
    assert cite_resolution_problems(r"\citep{Smith2020}", sub) == []
    assert _balanced(sub)


def test_bib_subset_multiline_nested_braces_slice_correctly():
    """RED: multi-line entries with nested braces in field values are sliced at the TRUE
    matching close brace, not at the first inner ``}``."""
    pool = (
        "@article{Nested2020,\n"
        "  title = {A {deeply {nested}} title},\n"
        "  abstract = {We use {\\LaTeX} and {math $x^2$} here},\n"
        "  year = {2020}\n"
        "}\n"
        "@book{After2021,\n"
        "  title = {After},\n"
        "  year = {2021}\n"
        "}\n"
    )
    sub = bib_subset(pool, ["Nested2020"])
    assert _balanced(sub)
    assert set(bib_keys(sub)) == {"Nested2020"}
    assert "year = {2020}" in sub
    assert "abstract = {We use {\\LaTeX} and {math $x^2$} here}" in sub
    # the following entry is not bled into the kept slice
    assert "After2021" not in sub


def test_bib_subset_preserves_contract_and_order():
    """The existing contract must still hold: bib_keys(bib_subset(bib, keep)) ==
    sorted(set(keep) & set(bib_keys(bib))), empty -> "", and source order preserved."""
    pool = (
        "@article{A2020, title={A}, year={2020}}\n"
        "@article{B2021, title={B}, year={2021}}\n"
        "@article{C2022, title={C}, year={2022}}\n"
    )
    # contract: kept keys are the intersection, sorted
    sub = bib_subset(pool, ["C2022", "A2020", "Z9999"])
    assert bib_keys(sub) == sorted({"A2020", "C2022"})
    # source order preserved: A2020 appears before C2022 in the emitted text
    assert sub.index("A2020") < sub.index("C2022")
    # empty result -> "" (not "\n")
    assert bib_subset(pool, ["Z9999"]) == ""
    assert bib_subset(pool, []) == ""


# ===========================================================================
# Part B -- bib-integrity gate over BOTH bib files (per-run + package)
# ===========================================================================

# A malformed (brace-unbalanced) bib -- one extra unclosed brace in a field value.
_MALFORMED_BIB = "@article{Bad2020, title = {Unclosed brace, year = {2020}}\n"


def _perrun_paper_problems(run_dir: Path):
    """Run the per-run paper-requirements gate over an already-compiled run."""
    from sci_adk.core.pubreqs import PubReqs
    from sci_adk.loop.verify import (
        _check_paper_requirements,
        _load_claims,
        _load_evidence,
        _load_spec,
    )

    (run_dir / "pubreqs.json").write_text(
        PubReqs(spec_id=run_dir.name, digest="fixture-digest").model_dump_json(),
        encoding="utf-8",
    )
    spec = _load_spec(run_dir)
    claims = list(_load_claims(run_dir).values())
    evidence = _load_evidence(run_dir)
    problems, _warnings = _check_paper_requirements(run_dir, evidence, claims, spec)
    return problems


# --- per-run: malformed references.bib (main) fails, naming the file ---

def test_per_run_malformed_main_bib_fails(tmp_path):
    """RED (Part B): a PRESENT-but-brace-unbalanced paper/references.bib FAILS the per-run
    gate, naming references.bib."""
    run_dir, _ = _compile(tmp_path, "t-bibint-main", _si_citing("A2020"))
    (run_dir / "paper" / "references.bib").write_text(_MALFORMED_BIB, encoding="utf-8")
    problems = _perrun_paper_problems(run_dir)
    assert any(
        "references.bib" in p and "references_SI.bib" not in p and "brace" in p.lower()
        for p in problems
    ), f"a malformed references.bib must fail naming the file; got {problems}"


# --- per-run: malformed references_SI.bib (SI) fails, naming the file ---

def test_per_run_malformed_si_bib_fails(tmp_path):
    """RED (Part B): a PRESENT-but-brace-unbalanced paper/references_SI.bib FAILS the
    per-run gate, naming references_SI.bib (the user's "둘 다 검정" requirement)."""
    run_dir, _ = _compile(tmp_path, "t-bibint-si", _si_citing("A2020"))
    assert (run_dir / "paper" / "references_SI.bib").is_file()
    (run_dir / "paper" / "references_SI.bib").write_text(_MALFORMED_BIB, encoding="utf-8")
    problems = _perrun_paper_problems(run_dir)
    assert any(
        "references_SI.bib" in p and "brace" in p.lower() for p in problems
    ), f"a malformed references_SI.bib must fail naming the file; got {problems}"


# --- per-run: clean bibs pass the integrity gate ---

def test_per_run_clean_bibs_pass_integrity(tmp_path):
    """RED (Part B): a clean pool (balanced references.bib + references_SI.bib) raises NO
    bib-integrity problem."""
    run_dir, _ = _compile(tmp_path, "t-bibint-clean", _si_citing("A2020"))
    problems = _perrun_paper_problems(run_dir)
    assert not any(
        "bib integrity" in p.lower() or "unbalanced brace" in p.lower() for p in problems
    ), f"clean bibs must not raise a bib-integrity problem; got {problems}"


# --- per-run: a MISSING bib is not a failure ---

def test_per_run_missing_bibs_stay_clean(tmp_path):
    """RED (Part B): NO references.bib and NO references_SI.bib (no-pool run) -> the
    integrity gate is silent (a missing bib is not malformed)."""
    run_dir, _ = _compile(
        tmp_path, "t-bibint-nobib", _si_citing("A2020"), seed_pool=False
    )
    assert not (run_dir / "paper" / "references.bib").exists()
    assert not (run_dir / "paper" / "references_SI.bib").exists()
    problems = _perrun_paper_problems(run_dir)
    assert not any(
        "bib integrity" in p.lower() or "unbalanced brace" in p.lower() for p in problems
    ), f"missing bibs must not raise a bib-integrity problem; got {problems}"


# --- package: malformed main / SI bib fails, naming the file ---

def _assemble_pkg_with_bibs(tmp_path, *, main_bib: str, si_bib: str):
    """Assemble a package whose 01_manuscript carries the given references.bib +
    references_SI.bib (via an author package_src)."""
    from sci_adk.render.package import assemble_package

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    authored_si = (
        _AUTHOR_SI_HEAD
        + r"Discussion \citep{A2020}."
        + r"\bibliography{references_SI}\end{document}"
    )
    (src / "si.tex").write_text(authored_si, encoding="utf-8")
    (src / "references.bib").write_text(main_bib, encoding="utf-8")
    (src / "references_SI.bib").write_text(si_bib, encoding="utf-8")
    pkgreqs = _pkgreqs_obj(ws)
    assemble_package(ws, pkgreqs)
    return ws, pkgreqs


def _pkg_problems(ws, pkgreqs):
    from sci_adk.loop.verify import _check_package_requirements

    problems, _warnings, _runs, _repro = _check_package_requirements(
        ws, ws / "package", pkgreqs
    )
    return problems


_CLEAN_SI_BIB = "@article{A2020, title={Alpha}, doi={10.1/a}}\n"


def test_package_malformed_main_bib_fails(tmp_path):
    """RED (Part B): a PRESENT-but-brace-unbalanced 01_manuscript/references.bib FAILS the
    package gate, naming references.bib."""
    ws, pkgreqs = _assemble_pkg_with_bibs(
        tmp_path, main_bib=_MALFORMED_BIB, si_bib=_CLEAN_SI_BIB
    )
    problems = _pkg_problems(ws, pkgreqs)
    assert any(
        "references.bib" in p and "references_SI.bib" not in p and "brace" in p.lower()
        for p in problems
    ), f"a malformed package references.bib must fail naming the file; got {problems}"


def test_package_malformed_si_bib_fails(tmp_path):
    """RED (Part B): a PRESENT-but-brace-unbalanced 01_manuscript/references_SI.bib FAILS
    the package gate, naming references_SI.bib (둘 다 검정)."""
    ws, pkgreqs = _assemble_pkg_with_bibs(
        tmp_path, main_bib=_POOL_BIB, si_bib=_MALFORMED_BIB
    )
    problems = _pkg_problems(ws, pkgreqs)
    assert any(
        "references_SI.bib" in p and "brace" in p.lower() for p in problems
    ), f"a malformed package references_SI.bib must fail naming the file; got {problems}"


def test_package_clean_bibs_pass_integrity(tmp_path):
    """RED (Part B): clean package bibs raise NO bib-integrity problem."""
    ws, pkgreqs = _assemble_pkg_with_bibs(
        tmp_path, main_bib=_POOL_BIB, si_bib=_CLEAN_SI_BIB
    )
    problems = _pkg_problems(ws, pkgreqs)
    assert not any(
        "bib integrity" in p.lower() or "unbalanced brace" in p.lower() for p in problems
    ), f"clean package bibs must not raise a bib-integrity problem; got {problems}"


# ===========================================================================
# _colocate_si_bib empty-subset branch (Minor coverage gap)
# ===========================================================================

def test_colocate_si_bib_all_cited_keys_dangling_writes_no_file(tmp_path):
    """RED (coverage): ALL cited keys absent from the pool -> empty subset -> NO
    references_SI.bib written and si.tex emits no \\bibliography (the `if not subset:
    return None` branch of _colocate_si_bib)."""
    # Pool has {A,B,C}; the SI cites only Z9999 + Y8888 -> the subset is empty.
    run_dir, _ = _compile(
        tmp_path, "t-m6-all-dangle", _si_citing("Z9999", "Y8888")
    )
    si_bib = run_dir / "paper" / "references_SI.bib"
    assert not si_bib.exists(), "an empty subset must write NO references_SI.bib"
    si_tex = (run_dir / "paper" / "si.tex").read_text(encoding="utf-8")
    assert r"\bibliography{" not in si_tex
