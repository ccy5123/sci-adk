"""
The reproduction bundle, third pass: what review of the second pass found.

  1. Since only source files ship, a hashed non-source path in a ``code_ref``
     (``analysis/data.csv sha256=...``) is a data reference -- and nothing checked its hash.
     Appending a row to the data file left ``verify`` silent, where before the second pass
     the same change was a hash-mismatch failure. A data reference the workspace holds is
     now hashed and a mismatch FAILS the reproduction-bundle requirement; a data file the
     workspace does not hold is an advisory line.
  2. The source extension set missed common languages (Stan, JAGS, Cython, CUDA, JSX/TSX,
     PHP, OCaml, ...), and an extensionless script (``bin/run_all`` starting ``#!``) was
     read as data.
  3. A script moved out of the workspace after render: ``verify`` said reproduce.py
     "lists X, which no recorded code_ref names" and advised a re-render -- which would
     prune the copy, the last one the reader has. It now names the code_ref and asks for
     the file to be restored first.
  4. Reader summaries cut a clause at the preposition before a removed record id even when
     the clause went on after it, or the word before the preposition needed it, leaving
     fragments ("... relative.", "... and not, which was wrong.", "Value differs."). Such a
     sentence now goes whole (a summary then falls back to the output name), and internal
     approach numbers are stripped wherever they label a step, including the bare
     "Spec method approach 4" form.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sci_adk.core.evidence import Provenance
from sci_adk.loop.code_ref import (
    SOURCE_EXTENSIONS,
    code_ref_data_files,
    is_source_path,
    resolve_code_ref_data_files,
    resolve_code_ref_scripts,
)
from sci_adk.loop.verify import verify_run
from sci_adk.render.reproduction import reader_summary, reader_text
from tests.test_reproduction_bundle import (
    _ANALYSIS,
    _freeze_bundle_contract,
    _render,
    _run_reproduce,
    _seed,
    _sha,
    _trial,
    _trial_evidence,
)
from tests.test_reproduction_sources import _CSV, _data_ref_code_ref, _data_run, _h, _manifest


def _bundle_problems(report) -> list[str]:
    return [p for p in report.paper_requirements_problems if p.startswith("reproduction bundle")]


# -- 1. a data reference the workspace holds is hash-checked ------------------------------


def test_resolving_data_references_hashes_the_files_the_workspace_holds(tmp_path):
    _data_run(tmp_path)
    run_dir = tmp_path / "runs" / "rs-data"
    named = resolve_code_ref_data_files(_data_ref_code_ref(), run_dir, tmp_path)
    assert [(n.path, n.recorded_sha256) for n in named] == code_ref_data_files(
        _data_ref_code_ref()
    )
    csv = named[0]
    assert csv.file == tmp_path / "analysis" / "data.csv"
    assert csv.actual_sha256 == _h(_CSV.encode())
    assert not csv.hash_mismatch and not csv.missing


def test_verify_fails_when_a_data_file_a_code_ref_names_has_changed(tmp_path):
    run_dir = _data_run(tmp_path)
    _freeze_bundle_contract(run_dir)
    data = tmp_path / "analysis" / "data.csv"
    data.write_text(_CSV + "71-43-2,2.13\n", encoding="utf-8")  # a row appended

    report = verify_run(run_dir)

    assert report.passed is False
    lines = [p for p in _bundle_problems(report) if "analysis/data.csv" in p]
    assert len(lines) == 1, report.paper_requirements_problems
    line = lines[0]
    assert _h(_CSV.encode()) in line                      # the recorded hash
    assert _h(data.read_bytes()) in line                  # the hash on disk now
    assert "evi-run-20261008-h1-primary-fit" in line      # the Evidence that names it
    assert "data" in line and "restore" in line


def test_a_data_file_the_workspace_does_not_hold_is_advisory(tmp_path):
    run_dir = _data_run(tmp_path)
    _freeze_bundle_contract(run_dir)
    data = tmp_path / "analysis" / "data.csv"
    data.rename(tmp_path / "data.csv.elsewhere")

    report = verify_run(run_dir)

    assert report.passed is True, report.paper_requirements_problems
    notes = [n for n in report.paper_advisory if "analysis/data.csv" in n]
    assert len(notes) == 1, report.paper_advisory
    assert _h(_CSV.encode()) in notes[0]
    assert "does not hold" in notes[0]


def test_an_unchanged_data_file_passes_and_says_nothing(tmp_path):
    run_dir = _data_run(tmp_path)
    _freeze_bundle_contract(run_dir)
    report = verify_run(run_dir)
    assert report.passed is True
    assert not any("data.csv" in n for n in report.paper_advisory)


def test_render_warns_about_a_changed_data_file(tmp_path):
    run_dir = _data_run(tmp_path)
    (tmp_path / "analysis" / "data.csv").write_text(_CSV + "x\n", encoding="utf-8")
    compiler = _render(tmp_path, run_dir)
    assert any("analysis/data.csv" in w for w in compiler.code_ref_warnings), (
        compiler.code_ref_warnings
    )


# -- 2. more source languages, and extensionless scripts with a shebang -------------------


@pytest.mark.parametrize("path", [
    "model.stan", "model.jags", "model.bug", "fast.pyx", "fast.pxd", "kernel.cu",
    "kernel.cuh", "App.jsx", "App.tsx", "mod.mts", "mod.cts", "index.php", "fit.ml",
    "fit.mli", "fit.fs", "fit.fsx", "build.groovy", "build.gradle.kts", "app.dart",
    "x.zig", "x.nim", "x.ex", "x.exs", "x.erl", "x.clj", "x.vb", "model.gms",
])
def test_more_source_languages_are_recognised(path):
    assert is_source_path(path)
    assert path.rsplit(".", 1)[1].lower() in {e.lstrip(".") for e in SOURCE_EXTENSIONS}


def _shebang_run(tmp_path: Path, body: bytes) -> tuple[Path, str]:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "run_all").write_bytes(body)
    code_ref = f"bin/run_all sha256={hashlib.sha256(body).hexdigest()}; no git commit"
    fit = _trial_evidence()[5].model_copy(
        update={"provenance": Provenance(code_ref=code_ref, data_source="generated")}
    )
    run_dir = _seed(tmp_path, "rs-shebang", [fit])
    _render(tmp_path, run_dir)
    return run_dir, code_ref


_SHEBANG = b"#!/usr/bin/env bash\nset -e\npython fit.py\n"


def test_an_extensionless_file_starting_with_a_shebang_is_a_script(tmp_path):
    run_dir, code_ref = _shebang_run(tmp_path, _SHEBANG)
    (named,) = resolve_code_ref_scripts(code_ref, run_dir, tmp_path)
    assert named.path == "bin/run_all"
    assert named.resolution.script == tmp_path / "bin" / "run_all"
    assert code_ref_data_files(code_ref, run_dir, tmp_path) == []
    assert resolve_code_ref_data_files(code_ref, run_dir, tmp_path) == []


def test_a_shebang_script_ships_and_verify_passes(tmp_path):
    run_dir, _code_ref = _shebang_run(tmp_path, _SHEBANG)
    assert (run_dir / "paper" / "code" / "run_all").read_bytes() == _SHEBANG
    assert [entry[0] for entry in _manifest(run_dir)] == ["run_all"]
    assert _run_reproduce(run_dir).returncode == 0
    _freeze_bundle_contract(run_dir)
    assert verify_run(run_dir).passed is True


def test_an_extensionless_file_without_a_shebang_stays_data(tmp_path):
    run_dir, code_ref = _shebang_run(tmp_path, b"chemical,logkow\n50-29-3,6.91\n")
    assert resolve_code_ref_scripts(code_ref, run_dir, tmp_path) == []
    assert [p for p, _digest in code_ref_data_files(code_ref, run_dir, tmp_path)] == [
        "bin/run_all"]
    assert not (run_dir / "paper" / "code").exists()


def test_a_whole_code_ref_naming_a_shebang_script_is_that_script(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "run_all").write_bytes(_SHEBANG)
    (named,) = resolve_code_ref_scripts("bin/run_all", tmp_path / "runs" / "r", tmp_path)
    assert named.resolution.script == tmp_path / "bin" / "run_all"


# -- 3. a script moved out of the workspace after render ---------------------------------


def test_a_script_gone_from_the_workspace_is_named_and_no_re_render_is_advised(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    script = tmp_path / _ANALYSIS / "s0_kow_columns.py"
    script.rename(tmp_path / "s0_kow_columns.py.moved")

    report = verify_run(run_dir)

    assert report.passed is False
    lines = [p for p in _bundle_problems(report) if "s0_kow_columns.py" in p]
    assert len(lines) == 1, report.paper_requirements_problems
    line = lines[0]
    assert f"code_ref names {_ANALYSIS}/s0_kow_columns.py (sha256={_sha('s0_kow_columns.py')})" \
        in line
    assert "the workspace no longer holds it; restore the file before re-rendering" in line
    assert "which no recorded code_ref names" not in line
    assert "re-run sci-adk render" not in line


def test_a_listed_script_no_code_ref_names_still_advises_a_re_render(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    path = run_dir / "paper" / "reproduce.py"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("SCRIPTS = [\n", f"SCRIPTS = [\n    ('extra.py', "
                                 f"{'f' * 64!r}, True),\n", 1), encoding="utf-8")
    report = verify_run(run_dir)
    (line,) = [p for p in _bundle_problems(report) if "extra.py" in p]
    assert "which no recorded code_ref names" in line
    assert line.endswith("re-run sci-adk render to refresh paper/")


# -- 4. reader summaries: no fragment where a reference stood ------------------------------

_A = "evi-obs-20261008-filter-approach1-records"
_FIT = "evi-run-20261008-h1-primary-fit"
_IDS = [_A, _FIT]
_OUTPUT = "s4_h1_fit.json"


@pytest.mark.parametrize("finding", [
    # The second pass cut each of these at the preposition before the id and printed
    # "The slope was lower relative.", "... and not, which was wrong.", "Value differs.".
    f"The slope was lower relative to {_FIT} because the set was smaller.",
    f"Counts were taken from s1_counts.json and not from {_A}, which was wrong.",
    f"Value differs from {_FIT} by 0.02 log units.",
    f"Value differs from {_FIT}.",
    f"The slope is lower relative to {_FIT}.",
    # The reference mid-clause, with the clause going on after it.
    f"The sample {_A} was drawn before any statistic was computed.",
    f"The fit used {_FIT}, which was wrong.",
])
def test_a_reference_that_cannot_leave_cleanly_takes_its_sentence(finding):
    assert reader_summary(finding, _IDS, fallback=_OUTPUT) == _OUTPUT


def test_only_the_sentence_holding_such_a_reference_goes():
    text = f"Value differs from {_FIT} by 0.02 log units. The fit used 341 chemicals."
    assert reader_text(text, _IDS) == "The fit used 341 chemicals."


@pytest.mark.parametrize(("finding", "expected"), [
    # The trial's h1-multi-record-chemicals summary: the clause after the main one goes on
    # after its reference, so that clause goes -- not the sentence.
    ("Named values for the third pre-registered H1 discriminating case, "
     "h1-multi-record-chemicals (chemicals with 5 or more retained BCF records), reported "
     f"in {_A} but not yet as named values. s8 was re-run.",
     "Named values for the third pre-registered H1 discriminating case, "
     "h1-multi-record-chemicals (chemicals with 5 or more retained BCF records)."),
    (f"The slope was 0.77, lower relative to {_FIT}.", "The slope was 0.77."),
])
def test_a_later_clause_that_cannot_lose_its_reference_goes_alone(finding, expected):
    assert reader_summary(finding, _IDS, fallback=_OUTPUT) == expected


@pytest.mark.parametrize(("finding", "expected"), [
    # clean cuts are unchanged
    (f"Named values for {_A}, read from s1_counts.json: database input.",
     "Named values, read from s1_counts.json: database input."),
    (f"Correction of {_A}: the earlier text gave 102 fish taxa.",
     "Correction: the earlier text gave 102 fish taxa."),
    (f"H2 primary correlation over the 50 chemicals recorded in {_A}.",
     "H2 primary correlation over the 50 chemicals."),
])
def test_a_reference_ending_its_clause_is_still_cut_cleanly(finding, expected):
    assert reader_summary(finding, _IDS, fallback=_OUTPUT) == expected


@pytest.mark.parametrize(("text", "expected"), [
    # the trial's leak: a bare approach number after "Spec method"
    ("Named value for the acidic-phenol rule (Spec method approach 4: exclude a hydroxyl "
     "on an aromatic ring).",
     "Named value for the acidic-phenol rule (exclude a hydroxyl on an aromatic ring)."),
    ("Spec method approach [4] neutral filter.", "Neutral filter."),
    ("Approach [6]: chemical identifier = CAS RN.", "Chemical identifier = CAS RN."),
    ("Records kept after approach [1] filtering: 2363.", "Records kept after filtering: 2363."),
    ("Log Kow from the approach [5] sources.", "Log Kow from the sources."),
    ("H1 negative control (approach [13]), executed.", "H1 negative control, executed."),
    # an English verb "approach(es)" followed by a number is not an approach number
    ("The slope approaches 1 at high log Kow.", "The slope approaches 1 at high log Kow."),
    ("Values approach 0 as n grows.", "Values approach 0 as n grows."),
])
def test_approach_numbers_are_stripped_wherever_they_label_a_step(text, expected):
    assert reader_text(text) == expected


@pytest.mark.parametrize("finding", [
    # a range of approaches used as a noun mid-clause: stripping it would leave
    # "Chemicals passing restricted to ...", so the sentence goes
    "Chemicals passing approaches [1]-[6] restricted to log Kow 1 to 6.",
    "Retained after approach [1]: 2363 records.",
])
def test_an_approach_number_used_as_a_noun_takes_its_sentence(finding):
    assert reader_summary(finding, fallback=_OUTPUT) == _OUTPUT
