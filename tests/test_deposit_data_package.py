"""
Deposit files, Phase 2 -- declared data in the package (design/deposit-files.md D7, D8;
test plan item 15 and the package part of 17).

The package owns ``02_data/<id>/`` and ``05_inputs/<id>/`` for every workspace run: each
assembly clears them and copies in what the run ships now, from the per-run copies under
``runs/<id>/paper/deposit/``. ``06_provenance/deposit.csv`` lists every declared file with the
run and the Evidence id; ``05_inputs/README.md`` is generated from the rows; the package gate
checks the inventory, the rows, the Evidence binding and the paths ``main.tex`` / ``si.tex``
name.

Runs: the trial fixture with the synthetic data of ``tests/test_deposit_data.py``, and an
unamended numeric run from the real loop.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.pkgreqs import PackageReqs
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verify import verify_package
from sci_adk.render.number_audit import RecordedValuePool
from sci_adk.render.package import assemble_package
from sci_adk.render.paper import check_paper_tool_vocabulary
from tests.test_deposit_data import (
    _BIB,
    _C,
    _COPY,
    _COPY_ENTRY,
    _N,
    _NOTES,
    _NOTES_ENTRY,
    _T,
    _TABLE,
    _TABLE_ENTRY,
    _TERMS,
    _W,
    _WORKBOOK,
    _WORKBOOK_ENTRY,
    _data_run,
    _declare,
)
from tests.test_deposit_protocol import (
    _REASON,
    _TRIAL_ID,
    _manifest_rows,
    _render,
    _withhold,
)
from tests.test_package_smoke import _numeric_experiment, _numeric_spec

_NUM_ID = "run-num"
_DATA = f"02_data/{_TRIAL_ID}"
_INPUTS = f"05_inputs/{_TRIAL_ID}"
_TODAY_README = (
    "# Inputs\n\n"
    "Pointers to the model inputs and any primary-literature sources used by the runs. "
    "Nothing copyrighted is redistributed here; curated values live in each run's "
    "official scripts (`04_scripts/runs/<id>/`).\n"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _ws(tmp_path: Path, *, numeric: bool = False) -> Path:
    run_dir = _data_run(tmp_path)
    ws = run_dir.parent.parent
    (ws / "package_src").mkdir()
    (ws / "package_src" / "references.bib").write_text(_BIB, encoding="utf-8")
    if numeric:
        run_checkpoint_loop(
            run_dir=ws / "runs" / _NUM_ID, spec=_numeric_spec(_NUM_ID),
            experiment=_numeric_experiment(0.95), workspace_dir=ws,
        )
    return ws


def _trial(ws: Path) -> Path:
    return ws / "runs" / _TRIAL_ID


def _pkg(ws: Path) -> Path:
    return ws / "package"


def _deposit_csv(ws: Path) -> list[dict]:
    text = (_pkg(ws) / "06_provenance" / "deposit.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _gate(ws: Path):
    report = verify_package(ws)
    fails = [p for p in report.package_requirements_problems if p.startswith("deposit files")]
    return fails, report.advisory


def _files_under(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _ship_all(ws: Path) -> None:
    """Declare and render: the table and the notes ship to data/, the workbook to inputs/,
    its decrypted copy is cited only."""
    _declare(_trial(ws), {**_TABLE_ENTRY, **_TERMS}, _NOTES_ENTRY,
             {**_WORKBOOK_ENTRY, "name": "workbook.xls", **_TERMS}, _COPY_ENTRY,
             license="CC0-1.0")
    _render(_trial(ws))


def _set_main(ws: Path, body: str) -> None:
    main_tex = _pkg(ws) / "01_manuscript" / "main.tex"
    main_tex.write_text(main_tex.read_text(encoding="utf-8").replace(
        r"\end{document}", body + "\n\\end{document}"), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 15 -- placement, rows, gate
# --------------------------------------------------------------------------- #

def test_the_package_ships_declared_files_at_the_d8_paths(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    assert (_pkg(ws) / _DATA / "table.csv").read_bytes() == _TABLE
    assert (_pkg(ws) / _DATA / "notes.csv").read_bytes() == _NOTES
    assert (_pkg(ws) / _INPUTS / "workbook.xls").read_bytes() == _WORKBOOK
    assert sorted(p.name for p in (_pkg(ws) / _DATA).iterdir()) == ["notes.csv", "table.csv"]

    rows = {r["sha256"]: r for r in _deposit_csv(ws)}
    assert rows[_T]["file"] == f"{_DATA}/table.csv"
    assert rows[_T]["evidence"] == "evi-obs-sample"
    assert rows[_T]["license"] == "CC-BY-4.0; redistribution asserted by the authors"
    assert rows[_N]["file"] == f"{_DATA}/notes.csv" and rows[_N]["evidence"] == ""
    assert rows[_N]["license"] == "CC0-1.0"
    assert rows[_W]["file"] == f"{_INPUTS}/workbook.xls"
    assert rows[_W]["evidence"] == "evi-obs-datasource"
    assert rows[_C]["file"] == "" and rows[_C]["license"] == "not redistributed"
    assert rows[_C]["evidence"] == "evi-obs-datasource"
    assert {r["run"] for r in rows.values()} == {_TRIAL_ID}
    files = [r["file"] for r in _deposit_csv(ws)]
    assert files[-1] == ""                                   # the unshipped row comes last
    assert files[:-1] == sorted(files[:-1])

    assert _gate(ws)[0] == []


def test_package_rows_match_the_per_run_rows_but_for_paths(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    per_run = [r[1:4] + r[5:] for r in _manifest_rows(_trial(ws))[1:]]
    package = [[r["sha256"], r["bytes"], r["kind"], r["cite"], r["license"], r["description"]]
               for r in _deposit_csv(ws)]
    assert sorted(per_run) == sorted(package)


def test_deposit_csv_without_run_and_evidence_passes_the_vocabulary_check(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    cells = "\n".join(",".join(v for k, v in r.items() if k not in ("run", "evidence"))
                      for r in _deposit_csv(ws))
    assert check_paper_tool_vocabulary(cells) == []


def test_a_cited_table_as_declared_is_a_row_without_a_file_and_nothing_lands_in_02_data(
        tmp_path):
    ws = _ws(tmp_path)
    _declare(_trial(ws), _TABLE_ENTRY)
    _render(_trial(ws))
    assemble_package(ws)
    assert not (_pkg(ws) / _DATA).exists()
    row = next(r for r in _deposit_csv(ws) if r["sha256"] == _T)
    assert row["file"] == "" and row["license"] == "not redistributed"
    assert row["evidence"] == "evi-obs-sample"
    assert _gate(ws)[0] == []


def test_the_number_audit_pool_is_unchanged_by_a_deposited_table(tmp_path):
    ws = _ws(tmp_path)
    _render(_trial(ws))
    assemble_package(ws)
    before = RecordedValuePool.from_package(_pkg(ws)).values
    _declare(_trial(ws), {**_TABLE_ENTRY, **_TERMS})
    _render(_trial(ws))
    assemble_package(ws)
    assert (_pkg(ws) / _DATA / "table.csv").is_file()
    assert RecordedValuePool.from_package(_pkg(ws)).values == before


def test_a_shipped_file_missing_from_the_per_run_bundle_stops_the_assembly(tmp_path, capsys):
    ws = _ws(tmp_path)
    _declare(_trial(ws), _NOTES_ENTRY)                       # declared, never rendered
    with pytest.raises(ValueError, match=f"re-render run {_TRIAL_ID}"):
        assemble_package(ws)
    assert not _pkg(ws).exists()
    assert main(["package", str(ws)]) == 2
    assert "re-render" in capsys.readouterr().err


def test_a_per_run_copy_that_differs_from_its_source_stops_the_assembly(tmp_path):
    ws = _ws(tmp_path)
    _declare(_trial(ws), _NOTES_ENTRY)
    _render(_trial(ws))
    (ws / "analysis" / "out" / "notes.csv").write_bytes(_NOTES + b"later,1\n")
    with pytest.raises(ValueError, match="re-render"):
        assemble_package(ws)


def test_the_rebuild_with_data_is_byte_identical_and_the_manifest_lists_everything(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    first = _files_under(_pkg(ws))
    assemble_package(ws)
    assert _files_under(_pkg(ws)) == first
    manifest = (_pkg(ws) / "MANIFEST.md").read_text(encoding="utf-8")
    for rel in (f"{_DATA}/table.csv", f"{_DATA}/notes.csv", f"{_INPUTS}/workbook.xls",
                "06_provenance/deposit.csv", "05_inputs/README.md"):
        assert f"`{rel}`" in manifest
    assert "rebuilt on every assembly" in manifest


# --------------------------------------------------------------------------- #
# 15 -- 05_inputs/README.md (D7)
# --------------------------------------------------------------------------- #

def test_the_inputs_readme_keeps_todays_text_with_no_declared_data(tmp_path):
    ws = _ws(tmp_path)
    assemble_package(ws)
    assert (_pkg(ws) / "05_inputs" / "README.md").read_text(encoding="utf-8") == _TODAY_README


def test_the_inputs_readme_lists_third_party_then_cited_study_rows(tmp_path):
    ws = _ws(tmp_path)
    _declare(_trial(ws), _TABLE_ENTRY, _WORKBOOK_ENTRY, _COPY_ENTRY)
    _render(_trial(ws))
    assemble_package(ws)
    readme = (_pkg(ws) / "05_inputs" / "README.md").read_text(encoding="utf-8")
    assert "Nothing copyrighted is redistributed here" in readme
    for sha in (_W, _C, _T):
        assert sha in readme
    assert readme.index(_W) < readme.index(_T) and readme.index(_C) < readme.index(_T)
    assert readme.count("not redistributed") == 3
    assert "Arnot2006" in readme


def test_the_inputs_readme_drops_the_sentence_when_a_cited_file_ships(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    readme = (_pkg(ws) / "05_inputs" / "README.md").read_text(encoding="utf-8")
    assert "Nothing copyrighted is redistributed here" not in readme
    assert f"`{_DATA}/table.csv`" in readme and f"`{_INPUTS}/workbook.xls`" in readme
    assert "CC-BY-4.0; redistribution asserted by the authors" in readme


# --------------------------------------------------------------------------- #
# 15 -- shrink then rebuild; owned namespaces
# --------------------------------------------------------------------------- #

def test_shrink_then_rebuild_leaves_no_stale_data_file(tmp_path):
    ws = _ws(tmp_path, numeric=True)
    _declare(_trial(ws), _NOTES_ENTRY, {**_TABLE_ENTRY, **_TERMS})
    _render(_trial(ws))
    assemble_package(ws)
    rows_before = len(_deposit_csv(ws))
    assert sorted(p.name for p in (_pkg(ws) / _DATA).iterdir()) == ["notes.csv", "table.csv"]

    _declare(_trial(ws), _NOTES_ENTRY)
    _render(_trial(ws))
    assemble_package(ws)
    assert sorted(p.name for p in (_pkg(ws) / _DATA).iterdir()) == ["notes.csv"]
    assert len(_deposit_csv(ws)) == rows_before - 1
    assert _gate(ws)[0] == []

    _declare(_trial(ws))                                     # files: []
    _render(_trial(ws))
    assemble_package(ws)
    assert not (_pkg(ws) / _DATA).exists()
    assert _gate(ws)[0] == []


def test_deselecting_a_run_clears_its_namespaces(tmp_path):
    ws = _ws(tmp_path, numeric=True)
    _ship_all(ws)
    assemble_package(ws)
    assert (_pkg(ws) / _DATA).is_dir() and (_pkg(ws) / _INPUTS).is_dir()
    assemble_package(ws, PackageReqs(runs=[_NUM_ID]))
    assert not (_pkg(ws) / _DATA).exists()
    assert not (_pkg(ws) / _INPUTS).exists()
    assert not (_pkg(ws) / "06_provenance" / "protocol" / _TRIAL_ID).exists()
    assert {r["run"] for r in _deposit_csv(ws)} == {_NUM_ID}


def test_an_author_file_in_a_run_data_folder_fails_the_gate_and_is_gone_after_a_rebuild(
        tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    mine = _pkg(ws) / _DATA / "mine.csv"
    mine.write_bytes(b"a,b\n")
    assert any(f"{_DATA}/mine.csv" in f for f in _gate(ws)[0])
    assemble_package(ws)
    assert not mine.exists()


def test_an_unknown_subfolder_of_02_data_gets_an_advisory_and_is_left_alone(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    other = _pkg(ws) / "02_data" / "shared"
    other.mkdir()
    (other / "x.csv").write_bytes(b"1\n")
    fails, advisory = _gate(ws)
    assert fails == []
    assert sum("02_data/shared" in a and "unchecked" in a for a in advisory) == 1
    assemble_package(ws)
    assert (other / "x.csv").is_file()


def test_a_subfolder_named_after_an_unpackaged_workspace_run_fails(tmp_path):
    ws = _ws(tmp_path, numeric=True)
    _ship_all(ws)
    assemble_package(ws, PackageReqs(runs=[_NUM_ID]))
    stray = _pkg(ws) / _DATA
    stray.mkdir(parents=True)
    (stray / "table.csv").write_bytes(_TABLE)
    assert any(_DATA in f for f in _gate(ws)[0])


@pytest.mark.parametrize("tamper", ["edit", "delete"])
def test_the_package_inventory_rechecks_data_files(tmp_path, tamper):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    copy = _pkg(ws) / _DATA / "table.csv"
    if tamper == "edit":
        copy.write_bytes(_TABLE + b"C,3.5\n")
    else:
        copy.unlink()
    assert any(f"{_DATA}/table.csv" in f for f in _gate(ws)[0])


def test_a_deposit_csv_data_cell_the_package_could_not_have_written_fails(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    manifest = _pkg(ws) / "06_provenance" / "deposit.csv"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        f"{_DATA}/notes.csv", "02_data/../README.md"), encoding="utf-8")
    assert any("row file '02_data/../README.md'" in f for f in _gate(ws)[0])


def test_an_entry_declared_against_an_item_without_its_hash_fails_the_package_gate(tmp_path):
    ws = _ws(tmp_path)
    _declare(_trial(ws), {**_TABLE_ENTRY, "evidence": "evi-obs-step-a"})
    _render(_trial(ws))
    assemble_package(ws)
    assert any("evi-obs-step-a" in f and _TRIAL_ID in f for f in _gate(ws)[0])


def test_a_declared_file_also_under_artifacts_gets_an_advisory(tmp_path):
    ws = _ws(tmp_path)
    artifacts = _trial(ws) / "artifacts"
    artifacts.mkdir()
    (artifacts / "copy-of-table.csv").write_bytes(_TABLE)
    (artifacts / "copy-of-workbook.xls").write_bytes(_COPY)
    _declare(_trial(ws), {**_TABLE_ENTRY, **_TERMS}, _COPY_ENTRY)
    _render(_trial(ws))
    assemble_package(ws)
    advisory = _gate(ws)[1]
    twice = [a for a in advisory if "copy-of-table.csv" in a]
    assert len(twice) == 1 and f"{_DATA}/table.csv" in twice[0] and "checked" in twice[0]
    undeclared = [a for a in advisory if "copy-of-workbook.xls" in a]
    assert len(undeclared) == 1 and "does not" in undeclared[0]


# --------------------------------------------------------------------------- #
# 15, 17 -- the package names check
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    rf"\texttt{{02\_data/{_TRIAL_ID}/table.csv}}",
    rf"\path{{05_inputs/{_TRIAL_ID}/workbook.xls}}",
    r"\path{06_provenance/deposit.csv} lists every file.",
    rf"\path{{06_provenance/protocol/{_TRIAL_ID}/protocol-v1.json}}",
    "the first version (protocol-v1.json)",
    r"02\_data/claims\_all.csv",
])
def test_a_package_path_the_package_holds_passes(tmp_path, text):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    _set_main(ws, text)
    assert _gate(ws)[0] == []


@pytest.mark.parametrize("text, needle", [
    (rf"\texttt{{02\_data/{_TRIAL_ID}/absent.csv}}", "absent.csv"),
    (r"\texttt{deposit/data/table.csv}", f"{_DATA}/table.csv"),
    (r"\texttt{deposit/protocol/protocol-v1.json}",
     f"06_provenance/protocol/{_TRIAL_ID}/protocol-v1.json"),
    ("protocol-v7.json", "protocol-v7.json"),
])
def test_a_package_path_the_package_does_not_hold_fails(tmp_path, text, needle):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    _set_main(ws, text)
    fails = _gate(ws)[0]
    assert any(needle in f and "main.tex" in f for f in fails), fails


def test_a_path_into_a_withheld_runs_protocol_folder_fails_naming_the_run(tmp_path):
    ws = _ws(tmp_path, numeric=True)
    _withhold(_trial(ws))
    _render(_trial(ws))
    assemble_package(ws)
    _set_main(ws, rf"\path{{06_provenance/protocol/{_TRIAL_ID}/protocol-v1.json}}")
    fails = _gate(ws)[0]
    assert any(_TRIAL_ID in f and "withheld" in f for f in fails)

    # a second packaged run that ships its protocol is unaffected
    main_tex = _pkg(ws) / "01_manuscript" / "main.tex"
    main_tex.write_text(main_tex.read_text(encoding="utf-8").replace(
        f"protocol/{_TRIAL_ID}/", f"protocol/{_NUM_ID}/"), encoding="utf-8")
    assert _gate(ws)[0] == []


def test_a_withheld_run_without_any_shipped_protocol_fails_a_bare_name(tmp_path):
    ws = _ws(tmp_path)
    _withhold(_trial(ws))
    _render(_trial(ws))
    assemble_package(ws)
    _set_main(ws, r"\texttt{amendment-v2.json}")
    fails = _gate(ws)[0]
    assert any("amendment-v2.json" in f and "withheld" in f for f in fails)
    assert sum(f"protocol withheld ({_REASON})" in a for a in _gate(ws)[1]) == 1
