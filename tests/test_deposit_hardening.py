"""
Deposit files: hardening of the core, render and verify paths (design/deposit-files.md D1-D5,
D7, D11, D13; change log "Hardening").

Each test pins one guard: a ``spec.json`` version far past the files on disk fails at once
instead of looping; the record's protocol files are never read through a symbolic link; the
"consistent" history line says which versions it compared; an unreadable source is a
declaration error, not a traceback; a case-only rename never deletes the renamed file; names
a Windows file system rejects are rejected; unshipped sources are hashed, not held; a source
inside a run's record is rejected; ``protocol_reason`` is one line by every line break
``str.splitlines`` knows; a stray file under ``paper/deposit/`` is named by render and by the
inventory; recorded times in ``record.tex`` do not break at hyphens; third-party data ships
only with both ``license`` and ``redistribution``.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.deposit import (
    DepositDeclarationError,
    load_deposit_declaration,
    parse_deposit_declaration,
)
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.render import deposit as render_deposit
from sci_adk.render.deposit import (
    plan_data,
    plan_protocol,
    prepare_deposit_write,
)
from tests.test_deposit_data import (
    _COPY_ENTRY,
    _NOTES,
    _NOTES_ENTRY,
    _NOTES_SRC,
    _TABLE,
    _TABLE_ENTRY,
    _TERMS,
    _W,
    _WORKBOOK,
    _WORKBOOK_ENTRY,
    _data_run,
    _declare,
    _parse,
    _row,
    _verify,
)
from tests.test_deposit_protocol import (
    _TRIAL_ID,
    _amended_run,
    _deposit,
    _render,
    _spec_of,
    _trial_run,
)


def _set_version(run_dir: Path, version: int) -> None:
    path = run_dir / "spec.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks not available")


# --------------------------------------------------------------------------- #
# 1 -- the version spec.json states is bounded by the files on disk
# --------------------------------------------------------------------------- #

def test_a_version_far_past_the_files_on_disk_fails_at_once(tmp_path):
    run_dir = _trial_run(tmp_path)
    _set_version(run_dir, 10_000_000)
    start = time.monotonic()
    with pytest.raises(ValueError, match="10000000") as exc:
        plan_protocol(run_dir)
    assert time.monotonic() - start < 5
    assert "spec.json" in str(exc.value)


def test_verify_reports_a_version_far_past_the_files_on_disk(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    _set_version(run_dir, 10_000_000)
    problems = verify_run(run_dir).deposit_file_problems
    assert any("10000000" in p for p in problems)


def test_the_margin_of_versions_no_file_accounts_for_is_allowed_and_one_more_is_not(tmp_path):
    # history v1 and receipt v2 account for versions 1 and 2, spec.json for the version it
    # states; every version between lacks a file
    run_dir = _trial_run(tmp_path)
    margin = render_deposit.VERSION_MARGIN
    _set_version(run_dir, 3 + margin)
    plan = plan_protocol(run_dir)
    assert plan.version == 3 + margin
    _set_version(run_dir, 4 + margin)
    with pytest.raises(ValueError, match="accounts for"):
        plan_protocol(run_dir)


def test_a_stray_high_numbered_history_file_does_not_lift_the_bound(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "spec_history" / "spec.v9999999.json").write_text("{}", encoding="utf-8")
    _set_version(run_dir, 10_000_000)
    with pytest.raises(ValueError, match="10000000"):
        plan_protocol(run_dir)


def test_an_amended_run_that_kept_no_file_still_plans_within_the_margin(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "spec_history" / "spec.v1.json").unlink()
    (run_dir / "checkpoints" / "amendment-v2.json").unlink()
    _set_version(run_dir, 4)                # a run amended before history files existed
    plan = plan_protocol(run_dir)
    assert [f.name for f in plan.files] == [
        "protocol-v1.json", "protocol-v2.json", "protocol-v3.json", "protocol-v4.json"]
    assert [f.kept for f in plan.files] == [False, False, False, True]


# --------------------------------------------------------------------------- #
# 2 -- the record's protocol files are never read through a symbolic link
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", [
    "spec.json", "spec_history/spec.v1.json", "checkpoints/amendment-v2.json",
])
def test_a_protocol_file_that_is_a_symlink_is_refused_naming_it(tmp_path, rel):
    run_dir = _trial_run(tmp_path)
    original = run_dir / rel
    elsewhere = tmp_path / "elsewhere" / original.name
    elsewhere.parent.mkdir()
    shutil.move(str(original), str(elsewhere))
    _symlink(original, elsewhere)
    with pytest.raises(ValueError, match="symbolic link") as exc:
        plan_protocol(run_dir)
    assert rel in str(exc.value)
    assert any(rel in p and "symbolic link" in p
               for p in verify_run(run_dir).deposit_file_problems)


def test_a_symlinked_history_folder_is_refused(tmp_path):
    run_dir = _trial_run(tmp_path)
    moved = tmp_path / "elsewhere"
    shutil.move(str(run_dir / "spec_history"), str(moved))
    _symlink(run_dir / "spec_history", moved)
    with pytest.raises(ValueError, match="spec_history"):
        plan_protocol(run_dir)


def test_render_refuses_a_symlinked_spec_before_writing_anything(tmp_path):
    run_dir = _trial_run(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "spec.json"
    elsewhere.parent.mkdir()
    shutil.move(str(run_dir / "spec.json"), str(elsewhere))
    _symlink(run_dir / "spec.json", elsewhere)
    with pytest.raises(ValueError, match="symbolic link"):
        _render(run_dir)
    assert not (run_dir / "paper").exists()


def test_record_only_render_reports_a_symlinked_spec_as_an_error(tmp_path, capsys):
    run_dir = _trial_run(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "spec.json"
    elsewhere.parent.mkdir()
    shutil.move(str(run_dir / "spec.json"), str(elsewhere))
    _symlink(run_dir / "spec.json", elsewhere)
    assert main(["render", str(run_dir), "--record-only"]) == 2
    assert "symbolic link" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# 3 -- the history line says which versions it compared
# --------------------------------------------------------------------------- #

def _receipt_without_checksum(run_dir: Path, version: int = 2) -> None:
    path = run_dir / "checkpoints" / f"amendment-v{version}.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["prior_spec_sha256"] = None
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")


def test_a_version_not_kept_makes_the_history_line_partial(tmp_path):
    run_dir = _amended_run(tmp_path)
    (run_dir / "spec_history" / "spec.v1.json").unlink()
    _receipt_without_checksum(run_dir)
    _render(run_dir)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    line = report.protocol_history
    assert line.startswith("protocol history: partly compared")
    assert "version 1 was not kept" in line
    assert "no step from one version to the next could be compared" in line
    assert "consistent --" not in line


def test_a_receipt_without_a_checksum_makes_the_history_line_partial(tmp_path):
    run_dir = _amended_run(tmp_path)
    _receipt_without_checksum(run_dir)
    _render(run_dir)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    assert "partly" in report.protocol_history
    assert "amendment-v2.json records no SHA-256 of version 1" in report.protocol_history


def test_a_missing_receipt_makes_the_history_line_partial(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "checkpoints" / "amendment-v2.json").unlink()
    _render(run_dir)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    assert "partly" in report.protocol_history
    assert "amendment-v2.json does not exist" in report.protocol_history


def test_the_partial_line_names_the_steps_it_compared(tmp_path):
    run_dir = _amended_run(tmp_path)
    assert main(["amend-spec", str(run_dir), "--rationale", "a second reason"]) == 0
    (run_dir / "checkpoints" / "amendment-v3.json").unlink()
    _render(run_dir)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    line = report.protocol_history
    assert "the step from version 1 to 2 agrees" in line
    assert "amendment-v3.json does not exist" in line
    assert "2 to 3 agree" not in line


def test_a_fully_kept_history_keeps_the_consistent_line(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    line = verify_run(run_dir).protocol_history
    assert line.startswith("protocol history: consistent -- versions 1 to 2")
    assert "partly" not in line


# --------------------------------------------------------------------------- #
# 4 -- a source that exists but cannot be read
# --------------------------------------------------------------------------- #

def _unreadable(path: Path) -> None:
    path.chmod(0)
    try:
        path.read_bytes()
    except PermissionError:
        return
    path.chmod(0o644)
    pytest.skip("file permissions are not enforced here (running as root?)")


@pytest.mark.parametrize("entry", [_NOTES_ENTRY, {**_TABLE_ENTRY, "source": _NOTES_SRC}],
                         ids=["shipped", "cited-not-shipped"])
def test_an_unreadable_source_is_a_declaration_error_in_render_and_verify(tmp_path, entry):
    run_dir = _data_run(tmp_path)
    _render(run_dir)                                  # a paper, so verify runs the checks
    _declare(run_dir, entry)
    source = tmp_path / "ws" / _NOTES_SRC
    _unreadable(source)
    try:
        with pytest.raises(DepositDeclarationError, match="not readable"):
            _render(run_dir)
        problems = verify_run(run_dir).deposit_file_problems
        assert any("not readable" in p and _NOTES_SRC in p for p in problems)
    finally:
        source.chmod(0o644)


# --------------------------------------------------------------------------- #
# 5 -- a case-only rename never deletes the renamed file
# --------------------------------------------------------------------------- #

def _renamed_notes(tmp_path: Path, *, same_file: bool, new_bytes: bytes = _NOTES) -> tuple:
    """Ship notes as ``Notes.csv``, then declare it as ``notes.csv``. ``same_file``
    simulates a case-insensitive file system: the new name is a hard link to the old file,
    as one file answers to both names there."""
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_NOTES_ENTRY, "name": "Notes.csv"})
    _render(run_dir)
    data_dir = _deposit(run_dir) / "data"
    assert (data_dir / "Notes.csv").read_bytes() == _NOTES
    if same_file:
        os.link(data_dir / "Notes.csv", data_dir / "notes.csv")
    (tmp_path / "ws" / _NOTES_SRC).write_bytes(new_bytes)
    plan = plan_protocol(run_dir)
    targets = {**plan.targets(), "data/notes.csv": new_bytes}
    return run_dir, prepare_deposit_write(run_dir / "paper", targets)


def test_a_case_only_rename_on_a_case_insensitive_file_system_removes_nothing(tmp_path):
    _, write = _renamed_notes(tmp_path, same_file=True)
    assert "data/Notes.csv" not in write.removals
    assert "data/notes.csv" in write.unchanged


def test_a_case_only_rename_with_new_bytes_is_written_not_refused(tmp_path):
    _, write = _renamed_notes(tmp_path, same_file=True, new_bytes=b"step,count\nfilter,5\n")
    assert "data/Notes.csv" not in write.removals
    assert "data/notes.csv" in write.writes


def test_a_case_only_rename_on_a_case_sensitive_file_system_removes_the_old_name(tmp_path):
    _, write = _renamed_notes(tmp_path, same_file=False)
    assert "data/Notes.csv" in write.removals
    assert "data/notes.csv" in write.writes


# --------------------------------------------------------------------------- #
# 6 -- names a Windows file system rejects
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [
    "con", "CON.csv", "prn", "aux.tar.gz", "nul.txt", "Nul", "com1", "COM9.dat", "lpt1.csv",
    "LPT9", "table.", "table.csv.",
])
def test_a_name_windows_rejects_is_rejected(name):
    with pytest.raises(DepositDeclarationError, match="name"):
        _parse([{**_NOTES_ENTRY, "name": name}])


@pytest.mark.parametrize("name", ["console.csv", "com10.csv", "lpt.csv", "nul_table.csv",
                                  "auxiliary.dat", "table.v2.csv"])
def test_names_that_only_resemble_a_device_name_load(name):
    assert _parse([{**_NOTES_ENTRY, "name": name}]).files[0].name == name


# --------------------------------------------------------------------------- #
# 7 -- unshipped sources are hashed, not held in memory
# --------------------------------------------------------------------------- #

def test_only_shipped_entries_hold_their_bytes(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, _TABLE_ENTRY, _WORKBOOK_ENTRY)
    decl = load_deposit_declaration(run_dir, _TRIAL_ID)
    notes, table, workbook = plan_data(run_dir, decl).files
    assert notes.data == _NOTES
    assert table.data is None and workbook.data is None
    assert (table.size, workbook.size) == (len(_TABLE), len(_WORKBOOK))
    assert workbook.sha256 == _W


def test_a_large_unshipped_source_is_hashed_in_chunks(tmp_path):
    run_dir = _data_run(tmp_path)
    big = tmp_path / "ws" / "data" / "raw" / "big.bin"
    payload = os.urandom(3 * 1024 * 1024 + 17)
    big.write_bytes(payload)
    _declare(run_dir, {**_WORKBOOK_ENTRY, "source": "data/raw/big.bin"})
    (df,) = plan_data(run_dir, load_deposit_declaration(run_dir, _TRIAL_ID)).files
    import hashlib
    assert df.sha256 == hashlib.sha256(payload).hexdigest()
    assert df.size == len(payload) and df.data is None


# --------------------------------------------------------------------------- #
# 8 -- a source inside a run's record is rejected
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", [
    "evidence/evi-obs-sample.json",
    f"runs/{_TRIAL_ID}/evidence/evi-obs-sample.json",
    "claims/claim-h1.json",
    "verdicts/verdict-h1.json",
    "checkpoints/prior_work.json",
    "numbers.json",
    "declarations.json",
])
def test_a_source_inside_the_runs_record_is_rejected(tmp_path, rel):
    run_dir = _data_run(tmp_path)
    for made in ("claims/claim-h1.json", "verdicts/verdict-h1.json",
                 "checkpoints/prior_work.json", "numbers.json", "declarations.json"):
        path = run_dir / made
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    _declare(run_dir, _WORKBOOK_ENTRY, {**_NOTES_ENTRY, "source": rel})
    with pytest.raises(DepositDeclarationError, match=r"files\[1\]") as exc:
        load_deposit_declaration(run_dir, _TRIAL_ID)
    assert "record" in str(exc.value)


def test_a_symlink_into_the_record_is_rejected(tmp_path):
    run_dir = _data_run(tmp_path)
    link = tmp_path / "ws" / "analysis" / "out" / "evidence-copy.json"
    _symlink(link, run_dir / "evidence" / "evi-obs-sample.json")
    _declare(run_dir, {**_NOTES_ENTRY, "source": "analysis/out/evidence-copy.json"})
    with pytest.raises(DepositDeclarationError, match="record"):
        load_deposit_declaration(run_dir, _TRIAL_ID)


def test_a_json_file_outside_the_record_loads(tmp_path):
    run_dir = _data_run(tmp_path)
    (tmp_path / "ws" / "analysis" / "out" / "counts.json").write_text("{}", encoding="utf-8")
    artifacts = run_dir / "artifacts"
    artifacts.mkdir()
    (artifacts / "table.json").write_text("{}", encoding="utf-8")
    _declare(run_dir, {**_NOTES_ENTRY, "source": "analysis/out/counts.json"},
             {**_NOTES_ENTRY, "source": "artifacts/table.json", "name": "t.json"})
    assert len(load_deposit_declaration(run_dir, _TRIAL_ID).files) == 2


# --------------------------------------------------------------------------- #
# 9 -- one line, by every line break str.splitlines knows
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("brk", ["\u2028", "\u2029", "\x85", "\x0b", "\x0c", "\x1c", "\x1d",
                                 "\x1e", "\r", "\n"])
def test_a_protocol_reason_with_any_line_break_is_rejected(brk):
    with pytest.raises(DepositDeclarationError, match="one line"):
        parse_deposit_declaration({
            "spec_id": "S", "protocol": "withheld",
            "protocol_reason": f"first part{brk}second part"}, "S")


def test_a_description_with_a_unicode_line_separator_is_rejected():
    with pytest.raises(DepositDeclarationError, match="one line"):
        _parse([{**_NOTES_ENTRY, "description": "Counts\u2028exported."}])


# --------------------------------------------------------------------------- #
# 10 -- a stray file under paper/deposit/ is named by verify and by render
# --------------------------------------------------------------------------- #

def test_the_inventory_names_a_stray_file_as_left_or_added_by_hand(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    (_deposit(run_dir) / "protocol" / "protocol-v9.json").write_text("{}", encoding="utf-8")
    problems = verify_run(run_dir).deposit_file_problems
    assert (
        "paper/deposit/protocol/protocol-v9.json is not in the manifest (left from an earlier "
        "render, or added by hand)") in problems


def test_render_warns_when_a_file_stays_that_the_new_manifest_does_not_list(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY)
    _render(run_dir)
    (_deposit(run_dir) / "manifest.csv").unlink()         # lost: nothing it listed is removed
    _declare(run_dir)
    compiler = _render(run_dir)
    assert (_deposit(run_dir) / "data" / "notes.csv").is_file()
    lines = [w for w in compiler.deposit_warnings if "paper/deposit/data/notes.csv" in w]
    assert len(lines) == 1
    assert "not list" in lines[0]


def test_a_changed_file_left_in_place_is_warned_about_once(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY)
    _render(run_dir)
    (_deposit(run_dir) / "data" / "notes.csv").write_bytes(b"edited by hand\n")
    _declare(run_dir)
    compiler = _render(run_dir)
    lines = [w for w in compiler.deposit_warnings if "paper/deposit/data/notes.csv" in w]
    assert len(lines) == 1


# --------------------------------------------------------------------------- #
# 11 -- recorded times in record.tex do not break at hyphens
# --------------------------------------------------------------------------- #

def test_record_tex_sets_each_recorded_time_in_an_mbox(tmp_path):
    run_dir = _trial_run(tmp_path)
    record = ResearchCompiler(workspace_dir=tmp_path).stage_render_record(
        _spec_of(run_dir)).read_text(encoding="utf-8")
    assert r"created \mbox{2026-10-08T10:03:39Z}" in record          # Protocol history
    assert r"recorded \mbox{2026-10-08T14:05:17Z}" in record
    assert r"\textit{created:} \mbox{2026-10-08T16:53:36Z}" in record  # Evidence record


# --------------------------------------------------------------------------- #
# 12 -- third-party data ships only with both license and redistribution
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("terms, ships", [
    ({}, False),
    ({"license": "CC-BY-4.0"}, False),
    ({"redistribution": "author-asserted"}, False),
    (_TERMS, True),
])
def test_an_external_entry_ships_only_with_both_terms(terms, ships):
    (entry,) = _parse([{**_WORKBOOK_ENTRY, "name": "workbook.xls", **terms}]).files
    assert entry.ships is ships


def test_an_external_entry_with_one_term_says_what_it_lacks(tmp_path):
    (entry,) = _parse([{**_WORKBOOK_ENTRY, "license": "CC-BY-4.0"}]).files
    assert entry.lacking == ("redistribution",)
    assert "lacks redistribution" in entry.not_shipped_reason()
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_WORKBOOK_ENTRY, "license": "CC-BY-4.0"})
    _render(run_dir)
    assert not (_deposit(run_dir) / "inputs").exists()
    assert _row(run_dir, _W)[6] == "not redistributed"
    problems, advisory = _verify(run_dir)
    assert problems == []
    assert any("lacks redistribution" in a for a in advisory)


def test_an_external_entry_with_both_terms_lands_in_inputs(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_WORKBOOK_ENTRY, "name": "workbook.xls", **_TERMS}, _COPY_ENTRY)
    _render(run_dir)
    assert (_deposit(run_dir) / "inputs" / "workbook.xls").read_bytes() == _WORKBOOK
    assert _row(run_dir, _W)[6] == "CC-BY-4.0; redistribution asserted by the authors"
    assert _verify(run_dir)[0] == []
