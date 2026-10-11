"""
Deposit files -- hardening of the package (design/deposit-files.md D8, D11; the change log entry
"Hardening of the package").

1. The assembly never deletes or writes through a symbolic link: ``package/``, a folder it writes
   into, or a folder between ``package/`` and a path it clears that is a link stops it before
   anything is written (a link AT a cleared path is removed, never followed).
2. The package skeletons load ``url``, so the ``\\path{...}`` the package skill recommends
   compiles.
3. The package ``06_provenance/record.tex`` prints, for each declared ``recorded`` or
   ``external`` file, the Evidence item that holds its checksum and the checksum, so
   ``deposit.csv``'s ``evidence`` column resolves in the package and ``sha256_also_in`` names
   the record for those rows.
4. The package gate recomputes each packaged run's protocol digest from ``runs/<id>/`` and
   requires it in ``run_index.csv`` and in the run's Protocol history block of ``record.tex``.
5. A package is "assembled before deposit files" only when nothing of the feature is in it.
6. The gate's cite message names the package bibliography and where it comes from.
7. The assembly notes each file it removes from an owned folder that no row listed.
8. The shipped ``check_package.py`` re-checks ``deposit.csv``: hashes, inventory, names.
9. The shipped builders refuse linked protocol files and an unbounded version, and set each
   protocol time in ``\\mbox{}``.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.render.deposit import (
    ProtocolUnreadable,
    package_name_problems,
    plan_protocol,
    plan_run_deposit,
    protocol_digest,
)
from sci_adk.render.package import assemble_package, discover_runs
from tests.test_bib_latex_copy import _loadable, _run, needs_tex
from tests.test_deposit_data import (
    _C,
    _COPY_ENTRY,
    _N,
    _NOTES_ENTRY,
    _T,
    _TABLE_ENTRY,
    _TERMS,
    _W,
    _WORKBOOK_ENTRY,
    _declare,
)
from tests.test_deposit_data_package import (
    _DATA,
    _INPUTS,
    _deposit_csv,
    _set_main,
    _ship_all,
    _trial,
    _ws,
)
from tests.test_deposit_phase1b import (
    _NUM_ID,
    _gate,
    _load_script,
    _pkg,
    _section,
    _workspace,
)
from tests.test_deposit_protocol import _FIXTURE, _REASON, _TRIAL_ID, _render

_RECORD = "06_provenance/record.tex"
_RUN_INDEX = "06_provenance/run_index.csv"
_PROTOCOL = f"06_provenance/protocol/{_TRIAL_ID}"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _tree(root: Path) -> dict:
    """Every file and link under ``root`` (links not followed), with its bytes or target."""
    out = {}
    if not os.path.lexists(root):
        return out
    if root.is_symlink():
        return {".": f"-> {os.readlink(root)}"}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                out[rel] = f"-> {os.readlink(path)}"
            elif name in filenames:
                out[rel] = path.read_bytes()
    return out


def _outside(tmp_path: Path) -> Path:
    """A folder outside the package holding files at every path the assembly clears."""
    outside = tmp_path / "outside"
    for rel in (f"protocol/{_TRIAL_ID}/keep.json", f"{_TRIAL_ID}/keep.csv",
                f"06_provenance/protocol/{_TRIAL_ID}/keep.json",
                f"02_data/{_TRIAL_ID}/keep.csv", f"05_inputs/{_TRIAL_ID}/keep.csv"):
        path = outside / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not the package's\n")
    return outside


def _record(ws: Path) -> str:
    return (_pkg(ws) / _RECORD).read_text(encoding="utf-8")


def _items(section: str, label: str) -> list[str]:
    """The text of each ``\\item[\\texttt{<label>}]`` of ``section``, up to the next item."""
    head = f"\\item[\\texttt{{{label}}}]"
    return [chunk.split("\\item[", 1)[0].split("\\end{description}", 1)[0]
            for chunk in section.split(head)[1:]]


def _rewrite_run_index(ws: Path, edit) -> None:
    path = _pkg(ws) / _RUN_INDEX
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    rows = edit(rows)
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")


def _set_digest_cell(ws: Path, rid: str, value: str) -> None:
    def edit(rows):
        col = rows[0].index("protocol_digest_sha256")
        for row in rows[1:]:
            if row[0] == rid:
                row[col] = value
        return rows
    _rewrite_run_index(ws, edit)


def _drop_digest_column(ws: Path) -> None:
    def edit(rows):
        col = rows[0].index("protocol_digest_sha256")
        return [row[:col] + row[col + 1:] for row in rows]
    _rewrite_run_index(ws, edit)


def _strip_protocol_history(ws: Path) -> None:
    path = _pkg(ws) / _RECORD
    text = path.read_text(encoding="utf-8")
    head, rest = text.split("\\section{Protocol history}", 1)
    path.write_text(head + "\\section{" + rest.split("\\section{", 1)[1], encoding="utf-8")


def _remove_deposit_files(ws: Path) -> None:
    (_pkg(ws) / "06_provenance" / "deposit.csv").unlink()
    shutil.rmtree(_pkg(ws) / "06_provenance" / "protocol")


def _check(ws: Path) -> subprocess.CompletedProcess:
    script = _pkg(ws) / "04_scripts" / "check_package.py"
    return subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          cwd=_pkg(ws))


def _deposit_lines(run: subprocess.CompletedProcess) -> list[str]:
    return [line for line in run.stdout.splitlines() if line.startswith("[deposit]")]


def _load_packaged(ws: Path, name: str):
    """The copy of a builder inside the package (its paths resolve from its own location)."""
    spec = importlib.util.spec_from_file_location(
        f"sciadk_pkg_test_{name.removesuffix('.py')}", _pkg(ws) / "04_scripts" / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# 1 -- no delete or write through a symbolic link
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("linked", [
    "package", "06_provenance", "02_data", "05_inputs", "04_scripts/runs",
    "06_provenance/verify_logs",
])
def test_a_linked_folder_stops_the_assembly_before_anything_is_written(
        tmp_path, linked, capsys):
    ws = _ws(tmp_path)
    _ship_all(ws)
    outside = _outside(tmp_path)
    link = ws / linked if linked == "package" else _pkg(ws) / linked
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    outside_before, package_before = _tree(outside), _tree(_pkg(ws))

    with pytest.raises(ValueError, match="symbolic link"):
        assemble_package(ws)
    assert _tree(outside) == outside_before
    assert _tree(_pkg(ws)) == package_before

    assert main(["package", str(ws)]) == 2
    assert "symbolic link" in capsys.readouterr().err
    assert _tree(outside) == outside_before


@pytest.mark.parametrize("rel", [
    "06_provenance/protocol", f"02_data/{_TRIAL_ID}", f"05_inputs/{_TRIAL_ID}",
])
def test_a_link_at_a_cleared_path_is_removed_and_its_target_is_left_alone(tmp_path, rel):
    ws = _ws(tmp_path)
    _ship_all(ws)
    outside = _outside(tmp_path)
    before = _tree(outside)
    link = _pkg(ws) / rel
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    assemble_package(ws)
    assert _tree(outside) == before
    assert not (_pkg(ws) / rel).is_symlink()
    assert _gate(ws)[0] == []


def test_clear_refuses_a_link_between_the_package_and_the_path_it_clears(tmp_path):
    from sci_adk.render.package import _clear

    package = tmp_path / "package"
    (package / "a").mkdir(parents=True)
    outside = tmp_path / "outside"
    (outside / "c").mkdir(parents=True)
    (outside / "c" / "keep.csv").write_bytes(b"1\n")
    (package / "a" / "b").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="a/b"):
        _clear(package, "a/b/c")
    assert (outside / "c" / "keep.csv").read_bytes() == b"1\n"


# --------------------------------------------------------------------------- #
# 2 -- \path compiles in the skeletons
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["main.tex", "si.tex"])
def test_the_skeleton_preambles_load_url(tmp_path, name):
    ws = _ws(tmp_path)
    assemble_package(ws)
    tex = (_pkg(ws) / "01_manuscript" / name).read_text(encoding="utf-8")
    preamble = tex[: tex.index(r"\begin{document}")].splitlines()
    assert r"\usepackage{url}" in preamble


@needs_tex
@pytest.mark.parametrize("name", ["main.tex", "si.tex"])
def test_a_skeleton_naming_a_file_with_path_compiles(tmp_path, name):
    if not all(_loadable(p) for p in ("newtxtext", "newtxmath", "helvet")):
        pytest.skip("this TeX install cannot load the skeleton's typefaces")
    ws = _ws(tmp_path)
    assemble_package(ws)
    manuscript = _pkg(ws) / "01_manuscript"
    tex = (manuscript / name).read_text(encoding="utf-8").replace(
        r"\end{document}",
        rf"The table is \path{{02_data/{_TRIAL_ID}/table.csv}}." "\n" r"\end{document}")
    (manuscript / name).write_text(tex, encoding="utf-8")
    assert _run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", name],
                manuscript) == 0, (manuscript / name.replace(".tex", ".log")).read_text(
                    encoding="utf-8", errors="replace")[-2000:]


# --------------------------------------------------------------------------- #
# 3 -- the package record prints each recorded / external file's Evidence id and checksum
# --------------------------------------------------------------------------- #

def test_the_package_record_prints_each_recorded_or_external_files_evidence_and_checksum(
        tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    section = _section(_record(ws), "Declared data files")
    assert any(_T in item for item in _items(section, "evi-obs-sample"))
    datasource = _items(section, "evi-obs-datasource")
    assert any(_W in item for item in datasource) and any(_C in item for item in datasource)
    assert _N not in _record(ws)                      # derived: no integrity claim

    rows = {r["sha256"]: r for r in _deposit_csv(ws)}
    for sha, evidence in ((_T, "evi-obs-sample"), (_W, "evi-obs-datasource"),
                          (_C, "evi-obs-datasource")):
        assert _RECORD in rows[sha]["sha256_also_in"].split(";"), rows[sha]
        assert rows[sha]["evidence"] == evidence
    assert rows[_N]["sha256_also_in"] == ""
    assert _gate(ws)[0] == []


@needs_tex
def test_the_package_record_with_declared_files_compiles(tmp_path):
    ws = _ws(tmp_path)
    odd = r"Rows with 5% of x_1 & y ~ {z}^2, at $3 each, # from C:\data"
    _declare(_trial(ws), {**_TABLE_ENTRY, **_TERMS, "description": odd}, _COPY_ENTRY,
             license="CC0-1.0")
    _render(_trial(ws))
    assemble_package(ws)
    provenance = _pkg(ws) / "06_provenance"
    assert "Declared data files" in _record(ws)
    assert _run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "record.tex"],
                provenance) == 0, (provenance / "record.log").read_text(
                    encoding="utf-8", errors="replace")[-2000:]


def test_the_shipped_record_builder_rewrites_the_record_with_its_declared_files(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    record = _pkg(ws) / _RECORD
    before = record.read_bytes()
    record.write_text("stale\n", encoding="utf-8")
    subprocess.run([sys.executable, str(_pkg(ws) / "04_scripts" / "make_si.py")],
                   check=True, capture_output=True)
    assert record.read_bytes() == before


def test_a_package_without_declared_data_has_no_declared_files_section(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    assert "Declared data files" not in _record(ws)


def test_a_cited_only_derived_declaration_adds_no_declared_files_section(tmp_path):
    ws = _ws(tmp_path)
    _declare(_trial(ws), _NOTES_ENTRY)
    _render(_trial(ws))
    assemble_package(ws)
    assert "Declared data files" not in _record(ws)


# --------------------------------------------------------------------------- #
# 4 -- the gate requires each run's protocol digest in run_index.csv and record.tex
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value", ["0" * 64, "n/a", ""])
def test_a_run_index_protocol_digest_unlike_the_records_fails(tmp_path, value):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    _set_digest_cell(ws, _TRIAL_ID, value)
    fails = _gate(ws)[0]
    assert any("run_index.csv" in f and _TRIAL_ID in f and "protocol digest" in f
               for f in fails), fails
    assert not any(_NUM_ID in f for f in fails), fails


def test_a_run_index_without_the_protocol_digest_column_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    _drop_digest_column(ws)
    fails = _gate(ws)[0]
    assert any("run_index.csv" in f and "protocol_digest_sha256" in f for f in fails), fails


def test_a_record_protocol_digest_unlike_the_records_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    digest = protocol_digest(plan_protocol(ws / "runs" / _TRIAL_ID))
    path = _pkg(ws) / _RECORD
    assert digest in path.read_text(encoding="utf-8")
    path.write_text(path.read_text(encoding="utf-8").replace(digest, "0" * 64),
                    encoding="utf-8")
    fails = _gate(ws)[0]
    assert any("record.tex" in f and _TRIAL_ID in f and "protocol digest" in f
               for f in fails), fails
    assert not any(_NUM_ID in f for f in fails), fails


def test_a_record_without_the_runs_protocol_history_block_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    path = _pkg(ws) / _RECORD
    text = path.read_text(encoding="utf-8")
    head = f"\\subsection*{{Run \\texttt{{{_TRIAL_ID}}}}}"
    before, after = text.split(head, 1)
    path.write_text(before + "\\subsection*{" + after.split("\\subsection*{", 1)[1],
                    encoding="utf-8")
    fails = _gate(ws)[0]
    assert any("record.tex" in f and _TRIAL_ID in f and "protocol digest" in f
               for f in fails), fails


# --------------------------------------------------------------------------- #
# 5 -- "assembled before deposit files" only when nothing of the feature is there
# --------------------------------------------------------------------------- #

# (a package with no trace of the feature: test_deposit_phase1b.py,
#  test_a_package_assembled_before_deposit_files_gets_one_advisory)

@pytest.mark.parametrize("left", ["protocol history", "digest column"])
def test_missing_deposit_files_fail_when_the_package_has_the_feature(tmp_path, left):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    _remove_deposit_files(ws)
    if left == "protocol history":
        _drop_digest_column(ws)
    else:
        _strip_protocol_history(ws)
    fails = _gate(ws)[0]
    assert any("06_provenance/deposit.csv is missing" in f for f in fails), fails
    assert any(f"{_PROTOCOL}/protocol-v1.json is missing" in f for f in fails), fails


# --------------------------------------------------------------------------- #
# 6 -- the cite message names the package bibliography and its source
# --------------------------------------------------------------------------- #

def test_a_cite_key_missing_from_the_package_bib_names_where_that_bib_comes_from(tmp_path):
    ws = _ws(tmp_path)
    (ws / "package_src" / "references.bib").unlink()
    _ship_all(ws)
    assemble_package(ws)
    fails = _gate(ws)[0]
    assert any("Arnot2006" in f and "01_manuscript/references.bib, supplied via "
               "package_src/references.bib" in f for f in fails), fails


# --------------------------------------------------------------------------- #
# 7 -- the assembly notes what it removes that no row listed
# --------------------------------------------------------------------------- #

def test_the_assembly_notes_each_unlisted_file_it_removes(tmp_path):
    ws = _ws(tmp_path, numeric=True)
    _ship_all(ws)
    assemble_package(ws)
    extras = [f"{_DATA}/mine.csv", f"{_INPUTS}/mine.txt", f"{_PROTOCOL}/extra.json",
              f"02_data/{_NUM_ID}/old.csv"]
    for rel in extras:
        path = _pkg(ws) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x\n")
    notes = assemble_package(ws).notes
    for rel in extras:
        assert sum(rel in n and "removed" in n for n in notes) == 1, notes
    assert not any("removed" in n and ("table.csv" in n or "protocol-v1.json" in n)
                   for n in notes), notes
    assert not any("removed" in n for n in assemble_package(ws).notes)


def test_the_package_command_prints_the_removal_notes(tmp_path, capsys):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    (_pkg(ws) / _DATA / "mine.csv").write_bytes(b"x\n")
    main(["package", str(ws)])
    assert f"{_DATA}/mine.csv" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 8 -- the shipped check_package.py re-checks deposit.csv
# --------------------------------------------------------------------------- #

def test_check_package_rechecks_the_deposit_files_of_a_clean_package(tmp_path):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    run = _check(ws)
    lines = _deposit_lines(run)
    assert lines and not any("FAIL" in line for line in lines), run.stdout
    assert any("SHA-256" in line and "match" in line for line in lines), run.stdout
    assert run.returncode == 0 and "PACKAGE CHECK: PASS" in run.stdout, run.stdout


def _tamper(ws: Path, tmp_path: Path, how: str) -> str:
    """Tamper with the package; return the path the failure must name."""
    table = _pkg(ws) / _DATA / "table.csv"
    if how == "edit":
        table.write_bytes(table.read_bytes() + b"C,3.5\n")
        return f"{_DATA}/table.csv"
    if how == "delete":
        table.unlink()
        return f"{_DATA}/table.csv"
    if how == "extra":
        (_pkg(ws) / _DATA / "mine.csv").write_bytes(b"x\n")
        return f"{_DATA}/mine.csv"
    if how == "extra-protocol":
        (_pkg(ws) / _PROTOCOL / "extra.json").write_bytes(b"{}\n")
        return f"{_PROTOCOL}/extra.json"
    if how == "stray-run-folder":
        stray = _pkg(ws) / "06_provenance" / "protocol" / "not-a-run"
        stray.mkdir()
        (stray / "x.json").write_bytes(b"{}\n")
        return "06_provenance/protocol/not-a-run"
    if how == "link":
        copy = tmp_path / "copy.csv"
        copy.write_bytes(table.read_bytes())
        table.unlink()
        table.symlink_to(copy)
        return f"{_DATA}/table.csv"
    if how == "names":
        _set_main(ws, r"\texttt{deposit/data/table.csv}")
        return "deposit/data/table.csv"
    raise AssertionError(how)


@pytest.mark.parametrize("how", ["edit", "delete", "extra", "extra-protocol",
                                 "stray-run-folder", "link", "names"])
def test_check_package_fails_what_the_gate_fails_for_deposit_files(tmp_path, how):
    ws = _ws(tmp_path)
    _ship_all(ws)
    assemble_package(ws)
    needle = _tamper(ws, tmp_path, how)
    assert any(needle in f for f in _gate(ws)[0])
    run = _check(ws)
    assert run.returncode == 1, run.stdout
    assert "PACKAGE CHECK: FAIL" in run.stdout
    assert any("FAIL" in line and needle in line for line in _deposit_lines(run)), run.stdout


def test_check_package_fails_a_missing_deposit_csv_when_the_record_has_a_protocol_history(
        tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    _remove_deposit_files(ws)
    run = _check(ws)
    assert run.returncode == 1
    assert any("FAIL" in line and "06_provenance/deposit.csv" in line
               for line in _deposit_lines(run)), run.stdout


def test_check_package_does_not_check_a_package_with_no_trace_of_deposit_files(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    _remove_deposit_files(ws)
    _strip_protocol_history(ws)
    _drop_digest_column(ws)
    lines = _deposit_lines(_check(ws))
    assert any("not checked" in line for line in lines), lines
    assert not any("FAIL" in line for line in lines), lines


def test_check_package_carries_the_names_patterns_verbatim(tmp_path):
    from sci_adk.render import deposit

    script = _load_script("check_package.py")

    def patterns(compiled):
        return [(p.pattern, p.flags) for p in compiled]

    assert patterns(script.URL_MASK_RES) == patterns(deposit._URL_MASK_RES)
    assert patterns([script.DEPOSIT_PATH_RE, script.BARE_PROTOCOL_RE, script.PACKAGE_PATH_RE,
                     script.FILE_WITH_EXTENSION_RE, script.PLAIN_NAME_RE]) == patterns([
        deposit._DEPOSIT_PATH_RE, deposit._BARE_PROTOCOL_RE, deposit._PACKAGE_PATH_RE,
        deposit._FILE_WITH_EXTENSION_RE, deposit._PLAIN_NAME_RE])
    assert script.TRAILING == deposit._TRAILING
    assert tuple(script.DEPOSIT_COLUMNS) == deposit.PACKAGE_MANIFEST_COLUMNS


_NAME_TEXTS = [
    rf"\texttt{{02\_data/{_TRIAL_ID}/table.csv}}",
    rf"see \path{{05_inputs/{_TRIAL_ID}/workbook.xls}}.",
    r"\path{06_provenance/deposit.csv} lists every file.",
    r"02\_data/claims\_all.csv",
    r"\texttt{06\_provenance/absent.txt}",
    rf"\path{{06_provenance/protocol/{_TRIAL_ID}/protocol-v1.json}}",
    rf"\path{{06_provenance/protocol/{_NUM_ID}/protocol-v1.json}}",
    rf"\path{{02_data/{_TRIAL_ID}/../README.md}}",
    r"\texttt{deposit/data/table.csv}",
    r"\texttt{deposit/inputs/workbook.xls}",
    r"\texttt{deposit/protocol/protocol-v1.json}",
    r"\texttt{deposit/data/absent.csv}",
    r"\texttt{deposit/manifest.csv}",
    "protocol-v1.json, amendment-v2.json and protocol-v2.json",
    "protocol-v7.json",
    r"\url{https://example.org/02_data/x.csv} and \href{https://example.org/deposit/a.json}{b}",
]


@pytest.mark.parametrize("text", _NAME_TEXTS)
def test_check_package_names_rule_matches_the_gate(tmp_path, text):
    ws = _ws(tmp_path, numeric=True)
    _declare(_trial(ws), {**_TABLE_ENTRY, **_TERMS},
             {**_WORKBOOK_ENTRY, "name": "workbook.xls", **_TERMS}, _COPY_ENTRY,
             license="CC0-1.0", protocol="withheld", protocol_reason=_REASON)
    _render(_trial(ws))
    assemble_package(ws)
    deposits = [(rid, *plan_run_deposit(ws / "runs" / rid)) for rid in discover_runs(ws)]
    docs = {"main.tex": text}
    script = _load_packaged(ws, "check_package.py")
    assert script.name_problems(docs, script.read_deposit_rows()) == package_name_problems(
        _pkg(ws), docs, deposits)


# --------------------------------------------------------------------------- #
# 9 -- the shipped builders: no link, a bounded version, times in \mbox
# --------------------------------------------------------------------------- #

def _move_and_link(run_dir: Path, rel: str) -> None:
    real = run_dir / rel
    target = run_dir.parent.parent / f"elsewhere-{rel.replace('/', '-')}"
    real.rename(target)
    real.symlink_to(target, target_is_directory=target.is_dir())


@pytest.mark.parametrize("variant", [
    "spec.json", "spec_history", "spec_history/spec.v1.json", "checkpoints",
    "checkpoints/amendment-v2.json", "version far past the files",
])
def test_the_shipped_builders_refuse_what_plan_protocol_refuses(tmp_path, variant):
    run_dir = tmp_path / "ws" / "runs" / _TRIAL_ID
    shutil.copytree(_FIXTURE, run_dir)
    if variant == "version far past the files":
        spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
        spec["version"] = 50
        (run_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    else:
        _move_and_link(run_dir, variant)
    with pytest.raises(ProtocolUnreadable):
        plan_protocol(run_dir)

    index_builder = _load_script("build_record_index.py")
    assert index_builder.protocol_digest_cell(str(run_dir)) == "n/a"
    with pytest.raises(ValueError):
        index_builder.protocol_files(str(run_dir))
    record_builder = _load_script("make_si.py")
    with pytest.raises(ValueError):
        record_builder.protocol_history(str(run_dir))


def test_a_version_within_the_margin_still_plans_in_the_shipped_builders(tmp_path):
    run_dir = tmp_path / "ws" / "runs" / _TRIAL_ID
    shutil.copytree(_FIXTURE, run_dir)
    spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    spec["version"] = 12                       # 9 of versions 1..12 lack a file: allowed
    (run_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    digest = protocol_digest(plan_protocol(run_dir))
    assert _load_script("build_record_index.py").protocol_digest(str(run_dir)) == digest
    assert _load_script("make_si.py").protocol_history(str(run_dir))[1] == digest


def test_the_package_record_sets_each_protocol_time_in_an_mbox(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    section = _section(_record(ws), "Protocol history")
    assert r"created \mbox{2026-10-08T10:03:39Z}" in section          # version 1
    assert r"recorded \mbox{2026-10-08T14:05:17Z}" in section         # the amendment receipt
    assert r"created \mbox{2026-10-08T14:05:17Z}" in section          # version 2


# --------------------------------------------------------------------------- #
# a file the assembly writes by name is never written through a link
# (final check of the deposit round, 2026-10-11: MANIFEST.md linked to an outside
# file was overwritten with the generated manifest)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", [
    "MANIFEST.md", "README.md", "06_provenance/deposit.csv", "01_manuscript/main.tex",
    "04_scripts/make_si.py",
])
def test_a_linked_generated_file_stops_the_assembly_before_anything_is_written(
        tmp_path, rel, capsys):
    ws = _ws(tmp_path)
    _ship_all(ws)
    outside = _outside(tmp_path)
    target = outside / "victim.txt"
    target.write_text("must survive\n", encoding="utf-8")
    link = _pkg(ws) / rel
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(target)
    package_before = _tree(_pkg(ws))

    with pytest.raises(ValueError, match="symbolic link"):
        assemble_package(ws)
    assert target.read_text(encoding="utf-8") == "must survive\n"
    assert _tree(_pkg(ws)) == package_before

    assert main(["package", str(ws)]) == 2
    assert "symbolic link" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "must survive\n"
