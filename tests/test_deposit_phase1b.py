"""
Deposit files, Phase 1b (design/deposit-files.md D4, D8, D11; test plan items 3, 11, 15, 16
and the package part of 17).

``record.tex`` gains a Protocol history section (each protocol version and amendment file,
its time, its SHA-256, the protocol digest), so the per-run manifest's ``sha256_also_in``
names ``record.tex`` for every protocol row. ``run_index.csv`` gains the full protocol
digest. The package rebuilds ``06_provenance/protocol/<id>/`` from ``runs/<id>/`` on every
assembly, writes ``06_provenance/deposit.csv``, and its gate re-runs the protocol checks and
the package inventory.

Runs come from the trial fixture (``tests/fixtures/deposit_bcfkow``: the trial's real
``spec.json`` v2, ``spec_history/spec.v1.json`` and ``checkpoints/amendment-v2.json``) and
from the real loop (``run_checkpoint_loop``) and amend verb.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.pkgreqs import PackageReqs
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_package, verify_run
from sci_adk.render.deposit import plan_protocol, protocol_digest, protocol_history
from sci_adk.render.number_audit import RecordedValuePool, tokenize_quantitative
from sci_adk.render.number_literals import find_literals
from sci_adk.render.package import assemble_package
from sci_adk.render.paper import check_paper_tool_vocabulary
from sci_adk.render.si import render_si_latex
from tests.test_deposit_protocol import (
    _A2_SHA,
    _FIXTURE,
    _REASON,
    _TRIAL_ID,
    _V1_SHA,
    _V2_SHA,
    _deposit,
    _manifest_rows,
    _render,
    _spec_of,
    _trial_run,
    _withhold,
)
from tests.test_package_smoke import _numeric_experiment, _numeric_spec

_NUM_ID = "run-num"
_PKG_PROTOCOL = "06_provenance/protocol"
_PKG_RECORD = "06_provenance/record.tex"
_TEMPLATE_SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / "src" / "sci_adk" / "templates" / "research-workspace" / "package" / "04_scripts"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _section(record: str, title: str = "Protocol history") -> str:
    head = f"\\section{{{title}}}"
    assert head in record, f"no {head} in record.tex"
    return record.split(head, 1)[1].split("\\section{", 1)[0]


def _workspace(tmp_path: Path) -> Path:
    """A workspace with the amended trial run and an unamended numeric run."""
    ws = tmp_path / "ws"
    shutil.copytree(_FIXTURE, ws / "runs" / _TRIAL_ID)
    run_checkpoint_loop(
        run_dir=ws / "runs" / _NUM_ID, spec=_numeric_spec(_NUM_ID),
        experiment=_numeric_experiment(0.95), workspace_dir=ws,
    )
    return ws


def _pkg(ws: Path) -> Path:
    return ws / "package"


def _deposit_csv(ws: Path) -> list[dict]:
    text = (_pkg(ws) / "06_provenance" / "deposit.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _gate(ws: Path):
    report = verify_package(ws)
    fails = [p for p in report.package_requirements_problems if p.startswith("deposit files")]
    return fails, report.advisory


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"sciadk_test_{name.removesuffix('.py')}", _TEMPLATE_SCRIPTS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _files_under(root: Path) -> dict:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


# --------------------------------------------------------------------------- #
# record.tex: the Protocol history section (D11)
# --------------------------------------------------------------------------- #

def test_record_tex_lists_each_protocol_file_with_its_time_checksum_and_the_digest(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    record = (run_dir / "record.tex").read_text(encoding="utf-8")
    section = _section(record)
    digest = protocol_digest(plan_protocol(run_dir))

    for token in (_V1_SHA, _A2_SHA, _V2_SHA, digest):
        assert token in section
    # in the order the files were written: version 1, the amendment, version 2
    assert (section.index("protocol-v1.json") < section.index("amendment-v2.json")
            < section.index("protocol-v2.json"))
    # each time in an \mbox, so a line never breaks at one of its hyphens
    assert r"created \mbox{2026-10-08T10:03:39Z}" in section          # version 1
    assert r"recorded \mbox{2026-10-08T14:05:17Z}" in section         # the amendment receipt
    assert r"created \mbox{2026-10-08T14:05:17Z}" in section          # version 2
    assert "local clocks" in section
    assert record.index(r"\section{Protocol history}") < record.index(
        r"\section{Record integrity}")


def test_record_only_render_writes_the_same_record_tex_as_a_full_render(tmp_path):
    run_dir = _trial_run(tmp_path)
    ResearchCompiler(workspace_dir=tmp_path).stage_render_record(_spec_of(run_dir))
    record_only = (run_dir / "record.tex").read_bytes()
    assert b"Protocol history" in record_only
    _render(run_dir)
    assert (run_dir / "record.tex").read_bytes() == record_only


def test_a_version_not_kept_is_listed_without_a_checksum(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "spec_history" / "spec.v1.json").unlink()
    _render(run_dir)
    section = _section((run_dir / "record.tex").read_text(encoding="utf-8"))
    entry = section.split("protocol-v1.json", 1)[1].split(r"\item", 1)[0]
    assert "file not kept" in entry
    assert r"created \mbox{2026-10-08T10:03:39Z}" in entry   # the time version 2 records
    assert _V1_SHA not in section


def test_the_renderer_without_a_protocol_writes_no_protocol_history(tmp_path):
    run_dir = _trial_run(tmp_path)
    assert "Protocol history" not in render_si_latex(_spec_of(run_dir), [], [])


def test_protocol_history_entries_are_chronological(tmp_path):
    run_dir = _trial_run(tmp_path)
    entries = protocol_history(plan_protocol(run_dir))
    assert [e.name for e in entries] == [
        "protocol-v1.json", "amendment-v2.json", "protocol-v2.json"]
    assert [e.sha256 for e in entries] == [_V1_SHA, _A2_SHA, _V2_SHA]


# --------------------------------------------------------------------------- #
# the per-run manifest names record.tex (D4, test plan 11, 17)
# --------------------------------------------------------------------------- #

def test_sha256_also_in_names_record_tex_for_every_protocol_row(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    rows = {r[1]: r for r in _manifest_rows(run_dir)[1:]}
    assert rows[_V1_SHA][4] == "protocol/amendment-v2.json;record.tex"
    assert rows[_V2_SHA][4] == "record.tex"
    assert rows[_A2_SHA][4] == "record.tex"
    assert verify_run(run_dir).deposit_file_problems == []


def test_a_withheld_rows_sha256_also_in_names_record_tex(tmp_path):
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    rows = _manifest_rows(run_dir)[1:]
    assert len(rows) == 3
    assert {r[4] for r in rows} == {"record.tex"}
    assert verify_run(run_dir).deposit_file_problems == []


# --------------------------------------------------------------------------- #
# run_index.csv: the full protocol digest (D11)
# --------------------------------------------------------------------------- #

def test_run_index_carries_the_full_protocol_digest_of_every_run(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    text = (_pkg(ws) / "06_provenance" / "run_index.csv").read_text(encoding="utf-8")
    header = next(csv.reader(io.StringIO(text)))
    assert header[-1] == "protocol_digest_sha256"
    rows = list(csv.DictReader(io.StringIO(text)))
    assert sorted(r["run_id"] for r in rows) == [_TRIAL_ID, _NUM_ID]
    for row in rows:
        expected = protocol_digest(plan_protocol(ws / "runs" / row["run_id"]))
        assert row["protocol_digest_sha256"] == expected
        assert len(expected) == 64


def test_the_shipped_index_builder_writes_the_same_run_index(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    script = _pkg(ws) / "04_scripts" / "build_record_index.py"
    subprocess.run(
        [sys.executable, str(script), "--workspace", str(ws), "--out", "rebuilt"],
        check=True, capture_output=True,
    )
    assert (ws / "rebuilt" / "06_provenance" / "run_index.csv").read_bytes() == (
        _pkg(ws) / "06_provenance" / "run_index.csv").read_bytes()


def _variants(tmp_path: Path) -> list[Path]:
    """The trial run as kept, without version 1's file, without its receipt; an unamended
    run."""
    out = []
    for name in ("kept", "no-v1", "no-receipt"):
        run_dir = tmp_path / name / "runs" / _TRIAL_ID
        shutil.copytree(_FIXTURE, run_dir)
        out.append(run_dir)
    (out[1] / "spec_history" / "spec.v1.json").unlink()
    (out[2] / "checkpoints" / "amendment-v2.json").unlink()
    ws = tmp_path / "num"
    run_checkpoint_loop(run_dir=ws / "runs" / _NUM_ID, spec=_numeric_spec(_NUM_ID),
                        experiment=_numeric_experiment(0.95), workspace_dir=ws)
    out.append(ws / "runs" / _NUM_ID)
    return out


def test_the_shipped_scripts_compute_the_protocol_digest_and_history_as_render_does(tmp_path):
    index_builder = _load_script("build_record_index.py")
    record_builder = _load_script("make_si.py")
    for run_dir in _variants(tmp_path):
        plan = plan_protocol(run_dir)
        assert index_builder.protocol_digest(str(run_dir)) == protocol_digest(plan)
        entries, digest = record_builder.protocol_history(str(run_dir))
        assert digest == protocol_digest(plan)
        assert entries == [
            (e.name, e.description, e.time_label, e.sha256) for e in protocol_history(plan)]


# --------------------------------------------------------------------------- #
# package: 06_provenance/protocol/<id>/ and 06_provenance/deposit.csv (D8)
# --------------------------------------------------------------------------- #

def test_the_package_ships_each_runs_protocol_files_from_the_run_directory(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    trial = _pkg(ws) / _PKG_PROTOCOL / _TRIAL_ID
    assert sorted(p.name for p in trial.iterdir()) == [
        "amendment-v2.json", "protocol-v1.json", "protocol-v2.json"]
    runs = ws / "runs" / _TRIAL_ID
    assert (trial / "protocol-v1.json").read_bytes() == (
        runs / "spec_history" / "spec.v1.json").read_bytes()
    assert (trial / "protocol-v2.json").read_bytes() == (runs / "spec.json").read_bytes()
    assert (trial / "amendment-v2.json").read_bytes() == (
        runs / "checkpoints" / "amendment-v2.json").read_bytes()
    num = _pkg(ws) / _PKG_PROTOCOL / _NUM_ID
    assert sorted(p.name for p in num.iterdir()) == ["protocol-v1.json"]


def test_deposit_csv_lists_the_protocol_rows_under_package_paths(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    text = (_pkg(ws) / "06_provenance" / "deposit.csv").read_text(encoding="utf-8")
    assert next(csv.reader(io.StringIO(text))) == [
        "run", "file", "sha256", "bytes", "kind", "sha256_also_in", "cite", "license",
        "description", "evidence"]
    rows = _deposit_csv(ws)
    trial = f"{_PKG_PROTOCOL}/{_TRIAL_ID}"
    assert [r["file"] for r in rows] == [
        f"{trial}/amendment-v2.json", f"{trial}/protocol-v1.json", f"{trial}/protocol-v2.json",
        f"{_PKG_PROTOCOL}/{_NUM_ID}/protocol-v1.json"]
    by_sha = {r["sha256"]: r for r in rows}
    assert by_sha[_V1_SHA]["sha256_also_in"] == f"{trial}/amendment-v2.json;{_PKG_RECORD}"
    assert by_sha[_V2_SHA]["sha256_also_in"] == _PKG_RECORD
    assert by_sha[_A2_SHA]["sha256_also_in"] == _PKG_RECORD
    assert by_sha[_V1_SHA]["bytes"] == "17552"
    assert by_sha[_V1_SHA]["description"] == "protocol, version 1, replaced by version 2"
    assert [r["run"] for r in rows] == [_TRIAL_ID] * 3 + [_NUM_ID]
    assert {r["evidence"] for r in rows} == {""}
    assert text.endswith("\n") and "\r" not in text
    # without its run and evidence columns, deposit.csv passes the vocabulary check
    cells = "\n".join(",".join(v for k, v in r.items() if k not in ("run", "evidence"))
                      for r in rows)
    assert check_paper_tool_vocabulary(cells) == []


def test_the_package_record_tex_carries_each_runs_protocol_history(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    record = (_pkg(ws) / _PKG_RECORD).read_text(encoding="utf-8")
    section = _section(record)
    for run_id in (_TRIAL_ID, _NUM_ID):
        assert protocol_digest(plan_protocol(ws / "runs" / run_id)) in section
    for sha in (_V1_SHA, _V2_SHA, _A2_SHA):
        assert sha in section
    assert r"recorded \mbox{2026-10-08T14:05:17Z}" in section       # as the per-run record


def test_the_package_gate_passes_the_deposit_checks_on_a_fresh_package(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    fails, advisory = _gate(ws)
    assert fails == []
    assert not any("withheld" in a for a in advisory)


def test_the_package_builds_from_the_run_even_when_the_per_run_copy_is_stale(tmp_path):
    ws = _workspace(tmp_path)
    run_dir = ws / "runs" / _NUM_ID
    assert main(["amend-spec", str(run_dir), "--rationale", "a stated reason"]) == 0
    assert verify_run(run_dir).deposit_file_problems != []      # the per-run copy is stale
    assemble_package(ws)
    num = _pkg(ws) / _PKG_PROTOCOL / _NUM_ID
    assert sorted(p.name for p in num.iterdir()) == [
        "amendment-v2.json", "protocol-v1.json", "protocol-v2.json"]
    assert (num / "protocol-v2.json").read_bytes() == (run_dir / "spec.json").read_bytes()
    assert _gate(ws)[0] == []


def test_the_package_gate_fails_after_an_amendment_made_post_package(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    assert main(["amend-spec", str(ws / "runs" / _NUM_ID), "--rationale", "later"]) == 0
    fails = _gate(ws)[0]
    assert fails
    assert any(_NUM_ID in f and "protocol-v1.json" in f for f in fails)


def test_the_package_rebuild_is_byte_identical(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    first = _files_under(_pkg(ws))
    assemble_package(ws)
    assert _files_under(_pkg(ws)) == first


def test_the_package_manifest_lists_the_protocol_files_and_deposit_csv(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    manifest = (_pkg(ws) / "MANIFEST.md").read_text(encoding="utf-8")
    assert "`06_provenance/deposit.csv`" in manifest
    assert f"`{_PKG_PROTOCOL}/{_TRIAL_ID}/protocol-v1.json`" in manifest


def test_the_run_index_digest_column_adds_nothing_to_the_number_audit_pool(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    with_column = RecordedValuePool.from_package(_pkg(ws)).values
    index = _pkg(ws) / "06_provenance" / "run_index.csv"
    rows = list(csv.reader(io.StringIO(index.read_text(encoding="utf-8"))))
    buf = io.StringIO()
    csv.writer(buf).writerows(r[:-1] for r in rows)
    index.write_text(buf.getvalue(), encoding="utf-8")
    assert RecordedValuePool.from_package(_pkg(ws)).values == with_column


def test_an_invalid_persisted_declaration_stops_the_assembly(tmp_path, capsys):
    ws = _workspace(tmp_path)
    (ws / "runs" / _NUM_ID / "deposit.json").write_text(
        json.dumps({"spec_id": _NUM_ID, "protocol": "hidden"}), encoding="utf-8")
    with pytest.raises(ValueError, match="deposit.json"):
        assemble_package(ws)
    assert main(["package", str(ws)]) == 2
    assert "deposit.json" in capsys.readouterr().err


def test_a_declaration_made_invalid_after_assembly_fails_the_gate(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    (ws / "runs" / _NUM_ID / "deposit.json").write_text(
        json.dumps({"spec_id": "other"}), encoding="utf-8")
    assert any("deposit.json" in f for f in _gate(ws)[0])


def test_a_package_assembled_before_deposit_files_gets_one_advisory(tmp_path):
    # Before the feature a package had no deposit.csv, no protocol folder, no Protocol history
    # section in record.tex and no protocol digest column in run_index.csv (any one of them
    # left makes the missing files fail: tests/test_deposit_package_hardening.py).
    ws = _workspace(tmp_path)
    assemble_package(ws)
    (_pkg(ws) / "06_provenance" / "deposit.csv").unlink()
    shutil.rmtree(_pkg(ws) / _PKG_PROTOCOL)
    record = _pkg(ws) / _PKG_RECORD
    head, rest = record.read_text(encoding="utf-8").split("\\section{Protocol history}", 1)
    record.write_text(head + "\\section{" + rest.split("\\section{", 1)[1], encoding="utf-8")
    index = _pkg(ws) / "06_provenance" / "run_index.csv"
    rows = list(csv.reader(io.StringIO(index.read_text(encoding="utf-8"))))
    buf = io.StringIO()
    csv.writer(buf).writerows(row[:-1] for row in rows)       # the digest column is last
    index.write_text(buf.getvalue(), encoding="utf-8", newline="")
    fails, advisory = _gate(ws)
    assert fails == []
    assert sum("06_provenance/deposit.csv" in a for a in advisory) == 1


# --------------------------------------------------------------------------- #
# package: a withheld protocol (test plan 17)
# --------------------------------------------------------------------------- #

def test_a_withheld_run_ships_no_protocol_folder_and_keeps_its_checksums(tmp_path):
    ws = _workspace(tmp_path)
    _withhold(ws / "runs" / _TRIAL_ID)
    assemble_package(ws)

    assert not (_pkg(ws) / _PKG_PROTOCOL / _TRIAL_ID).exists()
    assert (_pkg(ws) / _PKG_PROTOCOL / _NUM_ID / "protocol-v1.json").is_file()
    rows = [r for r in _deposit_csv(ws) if r["run"] == _TRIAL_ID]
    assert [r["sha256"] for r in rows] == [_A2_SHA, _V1_SHA, _V2_SHA]   # places kept
    for row in rows:
        assert row["file"] == "" and row["license"] == ""
        assert row["description"].endswith(f"; withheld: {_REASON}")
        assert row["sha256_also_in"] == _PKG_RECORD
    assert rows[1]["bytes"] == "17552"

    index = list(csv.DictReader(io.StringIO(
        (_pkg(ws) / "06_provenance" / "run_index.csv").read_text(encoding="utf-8"))))
    trial = next(r for r in index if r["run_id"] == _TRIAL_ID)
    assert trial["protocol_digest_sha256"] == protocol_digest(
        plan_protocol(ws / "runs" / _TRIAL_ID))

    fails, advisory = _gate(ws)
    assert fails == []
    assert sum(f"protocol withheld ({_REASON})" in a and _TRIAL_ID in a
               for a in advisory) == 1


def test_the_per_run_and_package_rows_of_a_withheld_run_agree_but_for_paths(tmp_path):
    ws = _workspace(tmp_path)
    run_dir = ws / "runs" / _TRIAL_ID
    _withhold(run_dir)
    _render(run_dir)
    assemble_package(ws)
    per_run = [r[1:4] + r[5:] for r in _manifest_rows(run_dir)[1:]]
    package = [[r["sha256"], r["bytes"], r["kind"], r["cite"], r["license"],
                r["description"]] for r in _deposit_csv(ws) if r["run"] == _TRIAL_ID]
    assert per_run == package


def test_withholding_after_the_last_per_run_render_is_honoured_by_the_package(tmp_path):
    ws = _workspace(tmp_path)
    run_dir = ws / "runs" / _TRIAL_ID
    _render(run_dir)
    assert (_deposit(run_dir) / "protocol" / "protocol-v1.json").is_file()
    _withhold(run_dir)                                   # no re-render
    assemble_package(ws)
    assert not (_pkg(ws) / _PKG_PROTOCOL / _TRIAL_ID).exists()


# --------------------------------------------------------------------------- #
# package: shrink then rebuild, inventory (test plan 15)
# --------------------------------------------------------------------------- #

def test_shrink_then_rebuild_leaves_no_stale_protocol_file(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    trial = _pkg(ws) / _PKG_PROTOCOL / _TRIAL_ID

    # an author file in an owned namespace is gone after a rebuild
    (trial / "notes.txt").write_text("mine", encoding="utf-8")
    assert any("notes.txt" in f for f in _gate(ws)[0])
    assemble_package(ws)
    assert not (trial / "notes.txt").exists()

    # withholding shrinks the run to nothing: its namespace is absent, the inventory passes
    _withhold(ws / "runs" / _TRIAL_ID)
    assemble_package(ws)
    assert not trial.exists()
    rows = _deposit_csv(ws)
    assert len(rows) == 4 and all(r["file"] == "" for r in rows if r["run"] == _TRIAL_ID)
    assert _gate(ws)[0] == []

    # deselecting the run clears its namespace and its rows
    (ws / "runs" / _TRIAL_ID / "deposit.json").unlink()
    assemble_package(ws)
    assert trial.is_dir()
    assemble_package(ws, PackageReqs(runs=[_NUM_ID]))
    assert not trial.exists()
    assert {r["run"] for r in _deposit_csv(ws)} == {_NUM_ID}


def test_a_subfolder_of_the_protocol_folder_that_is_no_packaged_run_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    stray = _pkg(ws) / _PKG_PROTOCOL / "old-run"
    stray.mkdir()
    (stray / "protocol-v1.json").write_text("{}", encoding="utf-8")
    assert any("old-run" in f for f in _gate(ws)[0])
    assemble_package(ws)
    assert not stray.exists()


@pytest.mark.parametrize("tamper", ["edit", "delete", "sha-cell"])
def test_the_package_inventory_rechecks_every_hash(tmp_path, tamper):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    copy = _pkg(ws) / _PKG_PROTOCOL / _TRIAL_ID / "protocol-v1.json"
    if tamper == "edit":
        copy.write_bytes(copy.read_bytes() + b" ")
    elif tamper == "delete":
        copy.unlink()
    else:
        manifest = _pkg(ws) / "06_provenance" / "deposit.csv"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace(
            _V1_SHA, "0" * 64), encoding="utf-8")
    fails = _gate(ws)[0]
    assert any(f"{_TRIAL_ID}/protocol-v1.json" in f for f in fails)


def test_a_missing_deposit_csv_beside_a_protocol_folder_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    (_pkg(ws) / "06_provenance" / "deposit.csv").unlink()
    assert any("06_provenance/deposit.csv is missing" in f for f in _gate(ws)[0])


@pytest.mark.parametrize("cell", [
    "06_provenance/../README.md",
    "06_provenance/protocol/old-run/protocol-v1.json",
    "/etc/passwd",
])
def test_a_deposit_csv_cell_the_package_could_not_have_written_fails(tmp_path, cell):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    manifest = _pkg(ws) / "06_provenance" / "deposit.csv"
    original = f"{_PKG_PROTOCOL}/{_NUM_ID}/protocol-v1.json"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(original, cell),
                        encoding="utf-8")
    assert any(f"row file {cell!r}" in f for f in _gate(ws)[0])


def test_a_symlink_in_the_package_protocol_folder_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    copy = _pkg(ws) / _PKG_PROTOCOL / _NUM_ID / "protocol-v1.json"
    target = tmp_path / "elsewhere.json"
    target.write_bytes(copy.read_bytes())
    copy.unlink()
    copy.symlink_to(target)
    fails = _gate(ws)[0]
    assert any("symbolic link" in f for f in fails)
    assert any(f"{_NUM_ID}/protocol-v1.json is missing" in f for f in fails)


def test_a_deposit_csv_with_other_columns_fails(tmp_path):
    ws = _workspace(tmp_path)
    assemble_package(ws)
    manifest = _pkg(ws) / "06_provenance" / "deposit.csv"
    manifest.write_text("file,sha256\n", encoding="utf-8")
    assert any("does not have the columns" in f for f in _gate(ws)[0])


def test_the_package_skill_names_the_protocol_folder_and_the_naming_guidance():
    skill = (
        _TEMPLATE_SCRIPTS.parent.parent / ".claude" / "skills" / "science-workflow-package"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "protocol/<id>/" in skill and "deposit.csv" in skill
    assert r"\path{06_provenance/protocol/<run>/protocol-v1.json}" in skill
    assert "withheld" in skill and "never elided" in skill


# --------------------------------------------------------------------------- #
# how paths, checksums and times meet the number checks (D8; test plan 12, 15)
# --------------------------------------------------------------------------- #

_SPLIT_V1 = r"\allowbreak".join(
    rf"\texttt{{{_V1_SHA[i:i + 16]}}}" for i in range(0, 64, 16))


@pytest.mark.parametrize("tex, literals", [
    ("deposit/protocol/protocol-v1.json", []),
    (r"\texttt{deposit/protocol/protocol-v1.json}", []),
    ("deposit/data/chemicals.csv", []),
    (r"02\_data/SPEC-BCFKOW-001/chemicals.csv", ["02", "001"]),
    (r"\texttt{02\_data/SPEC-BCFKOW-001/chemicals.csv}", ["02", "001"]),
    (r"\path{02_data/SPEC-BCFKOW-001/chemicals.csv}", []),
    ("deposit/data/table-2.csv", ["2"]),
    (r"table\_2.csv, table2.csv, my\_table.csv", []),
    (_SPLIT_V1, []),
    (r"\texttt{1081e637}\ldots", ["1081e637"]),
])
def test_declared_number_literals_of_paths_and_checksums(tex, literals):
    assert [lit.text for lit in find_literals(tex)] == literals


def test_a_date_time_is_one_declared_number_literal_bare_or_in_texttt():
    for tex in ("2026-10-08T10:03:39Z", r"\texttt{2026-10-08T10:03:39Z}"):
        assert [lit.text for lit in find_literals(tex)] == ["2026-10-08T10:03:39Z"]


@pytest.mark.parametrize("tex, values", [
    ("deposit/protocol/protocol-v1.json", []),
    (r"\texttt{deposit/protocol/protocol-v1.json}", []),
    (r"02\_data/SPEC-BCFKOW-001/chemicals.csv", [2.0, 1.0]),
    (r"\texttt{02\_data/SPEC-BCFKOW-001/chemicals.csv}", []),
    (r"\path{02_data/SPEC-BCFKOW-001/chemicals.csv}", []),
    (r"06\_provenance/protocol/SPEC-BCFKOW-001/protocol-v1.json", [6.0, 1.0]),
    (r"\texttt{06\_provenance/protocol/SPEC-BCFKOW-001/protocol-v1.json}", []),
    ("4fa76e47", [4.0]),
    (r"\texttt{4fa76e47}", []),
    ("9dc5d638", [9.0]),
    ("2026-10-08T10:03:39Z", [-10.0, 8.0, 3.0, 39.0]),
    (r"\texttt{2026-10-08T10:03:39Z}", []),
    (_SPLIT_V1, []),
])
def test_package_pattern_audit_tokens_of_paths_checksums_and_times(tex, values):
    assert [t.value for t in tokenize_quantitative(tex)] == values
