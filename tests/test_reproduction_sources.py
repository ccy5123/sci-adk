"""
The reproduction bundle, second pass: what a real run and a review of the first fix found.

  1. Every word followed by ``sha256=<hex>`` in a ``code_ref`` was read as a script, so a
     ``code_ref`` naming the data its script reads (``analysis/data.csv sha256=...``)
     shipped the data into ``paper/code/``, listed it in ``reproduce.py`` as a script and
     inlined the CSV in the record. Only source files ship now (a fixed extension set,
     :data:`sci_adk.loop.code_ref.SOURCE_EXTENSIONS`); other hashed paths are data
     references, listed in ``reproduce.py`` with their hash and never copied.
  2. ``reproduce.py`` crashed under a console encoding that cannot show a character of a
     summary (``PYTHONIOENCODING=ascii``).
  3. The reader summaries replaced record ids with the words "another recorded result"
     (17 times on the real run; "Named values for another recorded result and its
     correction another recorded result, ..."), kept internal approach numbers
     ("approach [13]"), and cut at abbreviations ("... database, Environ."). A reference
     the reader cannot resolve is now removed with the clause around it.
  4. ``verify`` checked the shipped copies but not the script list inside ``reproduce.py``,
     which is what a reader's ``python reproduce.py`` checks against.
  5. A render with nothing to list returned before removing the files the previous render
     had written.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sci_adk.core.evidence import Provenance
from sci_adk.loop.code_ref import (
    code_ref_data_files,
    is_source_path,
    resolve_code_ref_scripts,
)
from sci_adk.loop.compiler import deposit_record_path
from sci_adk.loop.verify import verify_run
from sci_adk.render.reproduction import (
    MACHINE_SECTION_MARKER,
    reader_summary,
    reader_text,
)
from tests.test_reproduction_bundle import (
    _ANALYSIS,
    _BODIES,
    _freeze_bundle_contract,
    _obs,
    _render,
    _run_reproduce,
    _seed,
    _sha,
    _trial,
    _trial_evidence,
)

_CSV = "chemical,logkow\n50-29-3,6.91\n"
# The first bytes of an OLE2 (legacy Excel) file, then bytes that are not text.
_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(range(256)) * 4
_SCRIPT = "import csv\nprint('fit from data.csv and table.xls')\n"


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _data_ref_code_ref() -> str:
    return (
        f"analysis/a.py sha256={_h(_SCRIPT.encode())} (reads analysis/data.csv "
        f"sha256={_h(_CSV.encode())} and analysis/table.xls sha256={_h(_XLS)}); "
        "no git commit"
    )


def _data_run(tmp_path: Path, spec_id: str = "rs-data") -> Path:
    d = tmp_path / "analysis"
    d.mkdir(parents=True, exist_ok=True)
    (d / "a.py").write_text(_SCRIPT, encoding="utf-8")
    (d / "data.csv").write_text(_CSV, encoding="utf-8")
    (d / "table.xls").write_bytes(_XLS)
    fit = _trial_evidence()[5].model_copy(
        update={"provenance": Provenance(code_ref=_data_ref_code_ref(),
                                         data_source="generated")}
    )
    run_dir = _seed(tmp_path, spec_id, [fit])
    _render(tmp_path, run_dir)
    return run_dir


def _manifest(run_dir: Path) -> list:
    tree = ast.parse((run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "SCRIPTS":
            return ast.literal_eval(node.value)
    raise AssertionError("no SCRIPTS list")


# -- 1. only source files ship; other hashed paths are data references -------------------


@pytest.mark.parametrize("path", [
    "analysis/a.py", "fit.R", "fit.r", "model.jl", "run.sh", "fit.m", "nb.ipynb",
    "clean.do", "proc.sas", "x.pl", "x.rb", "x.js", "x.ts", "x.c", "x.cpp", "x.f90",
    "proof.lean", "ANALYSIS/FIT.PY", "Makefile", "Snakefile",
])
def test_source_files_are_recognised_by_extension(path):
    assert is_source_path(path)


@pytest.mark.parametrize("path", [
    "analysis/data.csv", "table.xls", "table.xlsx", "out.json", "fig.png", "notes.txt",
    "data.parquet", "archive.zip", "README", "prior_work:searched",
])
def test_data_and_other_files_are_not_source(path):
    assert not is_source_path(path)


def test_a_code_ref_naming_its_data_resolves_only_the_script(tmp_path):
    _data_run(tmp_path)
    named = resolve_code_ref_scripts(_data_ref_code_ref(), tmp_path / "runs" / "r", tmp_path)
    assert [n.path for n in named] == ["analysis/a.py"]
    assert named[0].resolution.script == tmp_path / "analysis" / "a.py"


def test_the_hashed_data_paths_are_data_references():
    assert code_ref_data_files(_data_ref_code_ref()) == [
        ("analysis/data.csv", _h(_CSV.encode())),
        ("analysis/table.xls", _h(_XLS)),
    ]
    # A hashed word that is not a file path is free text, not a data reference.
    assert code_ref_data_files(f"run.py sha256={'a' * 64} outputs sha256={'b' * 64}") == []


def test_data_files_are_not_copied_into_paper_code(tmp_path):
    run_dir = _data_run(tmp_path)
    assert sorted(p.name for p in (run_dir / "paper" / "code").iterdir()) == ["a.py"]


def test_reproduce_lists_data_files_with_their_hash_not_as_scripts(tmp_path):
    run_dir = _data_run(tmp_path)
    assert [entry[0] for entry in _manifest(run_dir)] == ["a.py"]
    proc = _run_reproduce(run_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    assert "code/data.csv" not in out and "code/table.xls" not in out
    for path, digest in (("analysis/data.csv", _h(_CSV.encode())),
                         ("analysis/table.xls", _h(_XLS))):
        line = next(ln for ln in out.splitlines() if path in ln)
        assert digest in line, line
    assert "1 of 1 scripts match" in out


def test_record_does_not_inline_a_data_file(tmp_path):
    run_dir = _data_run(tmp_path)
    record = deposit_record_path(run_dir).read_text(encoding="utf-8")
    assert "50-29-3,6.91" not in record
    assert record.count(r"\begin{lstlisting}") == 1


def test_verify_passes_a_bundle_whose_code_ref_names_data(tmp_path):
    run_dir = _data_run(tmp_path)
    _freeze_bundle_contract(run_dir)
    report = verify_run(run_dir)
    assert report.paper_requirements_problems == []
    assert report.passed is True


# -- 2. reproduce.py survives a console that cannot show a character ---------------------


def test_reproduce_runs_under_an_ascii_console(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "fit.py").write_text("print('fit')\n", encoding="utf-8")
    fit = _trial_evidence()[5].model_copy(
        update={
            "provenance": Provenance(
                code_ref="code/fit.py", data_ref="5 µg/L stock — lot 7",
                data_source="generated",
            ),
            "result": _trial_evidence()[5].result.model_copy(
                update={"finding": "Fit over 5 µg/L – 10 µg/L samples (Rana catesbeiana)."}
            ),
        }
    )
    run_dir = _seed(tmp_path, "rs-ascii", [fit])
    _render(tmp_path, run_dir)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "ascii"
    paper = run_dir / "paper"
    proc = subprocess.run(
        [sys.executable, str(paper / "reproduce.py")],
        cwd=str(paper), capture_output=True, timeout=60, env=env,
    )
    stdout = proc.stdout.decode("ascii")
    assert proc.returncode == 0, stdout + proc.stderr.decode("ascii", "replace")
    assert b"UnicodeEncodeError" not in proc.stderr
    assert "Fit over 5 ?g/L" in stdout


# -- 3. reader summaries: unresolvable references leave with their clause ------------------

_A = "evi-obs-20261008-filter-approach1-records"
_B = "evi-obs-20261008-filter-approach1-records-corr1"
_S = "evi-obs-20261008-h2-sample"
_FIT = "evi-run-20261008-h1-primary-fit"
_IDS = [_A, _B, _S, _FIT]


@pytest.mark.parametrize(("finding", "expected"), [
    (f"Named values for {_A}, read from s1_counts.json: database input, and records kept.",
     "Named values, read from s1_counts.json: database input, and records kept."),
    (f"Named values for {_A} and its correction {_B}, read from s1_counts.json: database "
     "input.",
     "Named values, read from s1_counts.json: database input."),
    (f"Correction of {_A}: the earlier text gave 102 fish taxa; all counts are unchanged.",
     "Correction: the earlier text gave 102 fish taxa; all counts are unchanged."),
    (f"H2 primary correlation (approaches [9]-[10]) over the 50 chemicals recorded in {_S}. "
     "Encoding on the graph.",
     "H2 primary correlation over the 50 chemicals."),
    ("Exploratory analysis added after the results were seen; it does not change the frozen "
     f"decision rule (H1: 0.7 <= b <= 1.0, {_FIT}) and bears on no hypothesis.",
     "Exploratory analysis added after the results were seen; it does not change the frozen "
     "decision rule (H1: 0.7 <= b <= 1.0) and bears on no hypothesis."),
    (f"Residual from the H1 fit (a = -0.81, n = 341; {_FIT}).",
     "Residual from the H1 fit (a = -0.81, n = 341)."),
    (f"Over the 50 sampled chemicals ({_S}), unordered pairs.",
     "Over the 50 sampled chemicals, unordered pairs."),
])
def test_a_record_id_is_removed_with_its_clause_never_replaced(finding, expected):
    summary = reader_summary(finding, _IDS)
    assert summary == expected
    assert "another recorded result" not in summary


def test_a_sentence_that_is_only_a_reference_falls_back():
    assert reader_summary(f"{_A}.", _IDS, fallback="s1_counts.json") == "s1_counts.json"


@pytest.mark.parametrize(("finding", "expected"), [
    ("H1 negative control (approach [13]), executed. Mutation: permuted.",
     "H1 negative control, executed."),
    ("H1 primary fit (approach [7]). H1 analysis set: 404 chemicals.", "H1 primary fit."),
    ("Approach [2] chemical structure. The data set provides no SMILES.",
     "Chemical structure."),
    ("Approach [5] measured log Kow and approach [6] aggregation. Which columns.",
     "Measured log Kow and aggregation."),
    ("Data source (approach [0], option (a)): the curated database.",
     "Data source (option (a)): the curated database."),
    ("H2 sample record (approach [8]), written before any statistic was computed.",
     "H2 sample record, written before any statistic was computed."),
    ("Exploratory size baseline (approach [11]); bears on no hypothesis.",
     "Exploratory size baseline; bears on no hypothesis."),
])
def test_internal_approach_numbers_are_dropped(finding, expected):
    assert reader_summary(finding) == expected


@pytest.mark.parametrize(("finding", "expected"), [
    ("Data source: the Arnot & Gobas (2006) database, Environ. Rev. 14:257-297, DOI x. "
     "File y.",
     "Data source: the Arnot & Gobas (2006) database, Environ. Rev. 14:257-297, DOI x."),
    ("Values from Smith et al. Table 2 of the review. Next sentence.",
     "Values from Smith et al. Table 2 of the review."),
    ("Measured by J. Smith in 2001. Next sentence.", "Measured by J. Smith in 2001."),
    ("Read from the SI, e.g. Table S2 and Fig. S3. Next sentence.",
     "Read from the SI, e.g. Table S2 and Fig. S3."),
    ("Kept as given (the paper gives a URL as its location). File data/raw/x.xls.",
     "Kept as given (the paper gives a URL as its location)."),
])
def test_the_first_sentence_does_not_end_at_an_abbreviation(finding, expected):
    assert reader_summary(finding) == expected


def test_reader_text_removes_a_see_reference_from_a_data_ref():
    data_ref = (
        "input data/raw/a06-005.decrypted.xls sha256=1081 (decrypted from a06-005.xls "
        f"sha256 d5f6; see {_A})"
    )
    assert reader_text(data_ref, _IDS) == (
        "input data/raw/a06-005.decrypted.xls sha256=1081 (decrypted from a06-005.xls "
        "sha256 d5f6)"
    )


def test_the_bundle_never_prints_a_placeholder_for_a_record_id(tmp_path):
    run_dir = _trial(tmp_path)
    out = _run_reproduce(run_dir).stdout
    assert "another recorded result" not in out
    assert "Named values, read from s3_counts.json" in out


def test_a_summary_that_is_only_a_reference_falls_back_to_the_output_name(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "fit.py").write_text("print('fit')\n", encoding="utf-8")
    first = _obs("evi-obs-first", "code/fit.py", "The first result.")
    second = _obs("evi-obs-second", "code/fit.py", "evi-obs-first. Details follow.")
    run_dir = _seed(tmp_path, "rs-fallback", [first, second])
    _render(tmp_path, run_dir)
    out = _run_reproduce(run_dir).stdout
    assert "    - s3_counts.json" in out.splitlines()


# -- 4. verify compares reproduce.py's script list with the record ------------------------


def _tamper(run_dir: Path, old: str, new: str) -> None:
    path = run_dir / "paper" / "reproduce.py"
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def _entry(name: str) -> str:
    return f"    ({name!r}, {_sha(name)!r}, True),\n"


def test_verify_fails_when_reproduce_lists_another_hash_for_a_script(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    forged = "0" * 64
    _tamper(run_dir, _entry("s0_kow_columns.py"), f"    ('s0_kow_columns.py', {forged!r}, True),\n")
    report = verify_run(run_dir)
    assert report.passed is False
    lines = [p for p in report.paper_requirements_problems
             if "reproduce.py" in p and "s0_kow_columns.py" in p]
    assert len(lines) == 1, report.paper_requirements_problems
    assert forged in lines[0] and _sha("s0_kow_columns.py") in lines[0]
    assert lines[0].endswith("re-run sci-adk render to refresh paper/")


def test_verify_fails_when_reproduce_drops_a_script_from_its_list(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    _tamper(run_dir, _entry("s2_fetch_comptox.py"), "")
    report = verify_run(run_dir)
    assert report.passed is False
    assert any("reproduce.py" in p and "s2_fetch_comptox.py" in p and "does not list" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems


def test_verify_fails_when_reproduce_lists_a_script_no_code_ref_names(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    _tamper(run_dir, "SCRIPTS = [\n", f"SCRIPTS = [\n    ('extra.py', {'f' * 64!r}, True),\n")
    report = verify_run(run_dir)
    assert report.passed is False
    assert any("reproduce.py" in p and "extra.py" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems


def test_verify_fails_when_reproduce_has_no_readable_script_list(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    _tamper(run_dir, "SCRIPTS = [\n", "SCRIPTS = list([\n")
    path = run_dir / "paper" / "reproduce.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "\n]\n\n# One entry per recorded result", "\n])\n\n# One entry per recorded result", 1
    ), encoding="utf-8")
    report = verify_run(run_dir)
    assert report.passed is False
    assert any("reproduce.py" in p and "script list" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems


# -- 5. a render with nothing to list still removes what the previous render wrote ---------


def _no_code_run(tmp_path: Path, spec_id: str) -> Path:
    item = _obs("evi-obs-plain", None, "A plain observation.")
    run_dir = _seed(tmp_path, spec_id, [item])
    _render(tmp_path, run_dir)
    assert not (run_dir / "paper" / "reproduce.py").exists()
    return run_dir


def _previous_driver(names: list[str]) -> str:
    entries = "".join(f"    ({n!r}, {'e' * 64!r}, True),\n" for n in names)
    return (
        '"""reproduce.py -- an earlier render."""\n'
        f"{MACHINE_SECTION_MARKER}\nBUNDLE_FORMAT = 2\nSCRIPTS = [\n{entries}]\nRESULTS = []\n"
    )


def test_a_render_with_no_listing_removes_the_previous_bundle(tmp_path):
    run_dir = _no_code_run(tmp_path, "rs-prune")
    code = run_dir / "paper" / "code"
    code.mkdir()
    (code / "old.py").write_text("print('old')\n", encoding="utf-8")
    (run_dir / "paper" / "reproduce.py").write_text(_previous_driver(["old.py"]),
                                                   encoding="utf-8")
    _render(tmp_path, run_dir)
    assert not (code / "old.py").exists()
    assert not code.exists()
    assert not (run_dir / "paper" / "reproduce.py").exists()


def test_a_render_with_no_listing_keeps_the_authors_files(tmp_path):
    run_dir = _no_code_run(tmp_path, "rs-prune-keep")
    code = run_dir / "paper" / "code"
    code.mkdir()
    (code / "old.py").write_text("print('old')\n", encoding="utf-8")
    (code / "notes.txt").write_text("mine\n", encoding="utf-8")
    (run_dir / "paper" / "reproduce.py").write_text(_previous_driver(["old.py"]),
                                                   encoding="utf-8")
    _render(tmp_path, run_dir)
    assert sorted(p.name for p in code.iterdir()) == ["notes.txt"]


def test_files_a_hand_written_reproduce_lists_are_not_render_owned(tmp_path):
    # Only a reproduce.py a sci-adk render wrote tells the render which paper/code/ files
    # it owns; a hand-written one with a SCRIPTS list does not.
    run_dir = _no_code_run(tmp_path, "rs-prune-handlist")
    code = run_dir / "paper" / "code"
    code.mkdir()
    (code / "mine.py").write_text("print('mine')\n", encoding="utf-8")
    (run_dir / "paper" / "reproduce.py").write_text(
        "BUNDLE_FORMAT = 2\nSCRIPTS = [('mine.py', '" + "a" * 64 + "', True)]\n",
        encoding="utf-8",
    )
    _render(tmp_path, run_dir)
    assert (code / "mine.py").is_file()


def test_a_render_with_no_listing_leaves_a_hand_written_reproduce_alone(tmp_path):
    run_dir = _no_code_run(tmp_path, "rs-prune-hand")
    hand = "print('my own driver')\n"
    (run_dir / "paper" / "reproduce.py").write_text(hand, encoding="utf-8")
    _render(tmp_path, run_dir)
    assert (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8") == hand


# -- 6. the documents no longer describe reproduce.py as a re-runner ---------------------

_REPO = Path(__file__).resolve().parents[1]
_TEMPLATE = _REPO / "src" / "sci_adk" / "templates" / "research-workspace" / ".claude"


@pytest.mark.parametrize("doc", [
    _REPO / "README.md",
    _TEMPLATE / "skills" / "science-workflow-experiment" / "SKILL.md",
    _TEMPLATE / "agents" / "expert-experimentalist.md",
])
def test_documents_say_the_bundle_checks_hashes_and_does_not_re_run(doc):
    text = " ".join(doc.read_text(encoding="utf-8").split())
    assert "re-runs the file" not in text
    assert "reproduce.py` re-runner" not in text
    assert "does not re-run" in text


@pytest.mark.parametrize("doc", [
    _TEMPLATE / "skills" / "science-workflow-experiment" / "SKILL.md",
    _TEMPLATE / "agents" / "expert-experimentalist.md",
])
def test_recording_advice_names_input_scripts_with_their_hash(doc):
    text = " ".join(doc.read_text(encoding="utf-8").split())
    # The advice from before every hashed script shipped: input-building scripts "go in
    # the finding" and the bundle "reads only the leading path".
    assert "the scripts that built its inputs" not in text
    assert "reads only the leading path" not in text
    assert "never shipped" in text


def test_trial_fixture_still_ships_every_source_script(tmp_path):
    # Regression guard for the first fix: the trial's scripts are all .py and all ship.
    run_dir = _trial(tmp_path)
    assert sorted(entry[0] for entry in _manifest(run_dir)) == sorted(_BODIES)
    assert all(entry[0].endswith(".py") for entry in _manifest(run_dir))
    assert _ANALYSIS  # fixture paths unchanged
