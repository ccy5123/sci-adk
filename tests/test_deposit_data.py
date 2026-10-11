"""
Deposit files, Phase 2 -- declared data, per run (design/deposit-files.md D2-D5, D7, D9, D13;
test plan items 5-12, 14 and the names part of 17).

The author declares data files in ``deposit.json``, passed with ``render --deposit`` /
``run --deposit`` and persisted as ``runs/<id>/deposit.json``. A study file with no cited
source ships under ``paper/deposit/data/``; a study file holding values from a cited source
is cited, not shipped, unless it states both ``license`` and ``redistribution``; third-party
data ships under ``paper/deposit/inputs/`` only with ``license`` or ``redistribution``. Every
declared file is a manifest row with its SHA-256; ``verify`` checks the recorded and external
ones against the named Evidence item, the citations against ``references.bib``, and the paths
the paper names against the manifest.

Runs are the trial fixture (``tests/fixtures/deposit_bcfkow``, amended v1 -> v2) in a
workspace that adds small synthetic files and Evidence items holding their checksums -- the
same shape as the trial (a table whose checksum sits in three items, a third-party file and
its decrypted copy recorded in one item, the copy in two more). Domain-neutral bytes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.deposit import (
    DepositDeclarationError,
    load_deposit_declaration,
    parse_deposit_declaration,
)
from sci_adk.core.evidence import EvidenceItem, EvidenceKind, Provenance, Result
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.render.deposit import DepositRefused
from sci_adk.render.paper import check_paper_tool_vocabulary
from tests.test_deposit_protocol import (
    _A2_SHA,
    _TRIAL_ID,
    _V1_SHA,
    _V2_SHA,
    _deposit,
    _files_under,
    _manifest_rows,
    _render,
    _spec_of,
    _trial_run,
    _withhold,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_TABLE = b"id,value\nA,1.5\nB,2.5\n"
_WORKBOOK = b"\xd0\xcf\x11\xe0 the third-party file as received\n"
_COPY = b"\xd0\xcf\x11\xe0 the same file, decrypted\n"
_NOTES = b"step,count\nfilter,4\n"
_T, _W, _C, _N = _sha(_TABLE), _sha(_WORKBOOK), _sha(_COPY), _sha(_NOTES)

_TABLE_SRC = "analysis/out/table.csv"
_WORKBOOK_SRC = "data/raw/workbook.xls"
_COPY_SRC = "data/raw/workbook.decrypted.xls"
_NOTES_SRC = "analysis/out/notes.csv"

_BIB = (
    "@article{Arnot2006, title={A review}, author={Arnot, Jon A}, year={2006}, "
    "doi={10.1139/a06-005}}\n"
)

_TABLE_HOLDERS = ("evi-obs-sample", "evi-obs-fit", "evi-obs-baseline")
_COPY_HOLDERS = ("evi-obs-datasource", "evi-obs-step-a", "evi-obs-step-b")

_TABLE_ENTRY = {
    "source": _TABLE_SRC, "name": "table.csv", "origin": "recorded",
    "evidence": "evi-obs-sample", "cite": ["Arnot2006"],
    "description": "The rows that passed the filters, with their values.",
}
_WORKBOOK_ENTRY = {
    "source": _WORKBOOK_SRC, "origin": "external", "evidence": "evi-obs-datasource",
    "cite": ["Arnot2006"], "description": "The cited supplementary file, as received.",
}
_COPY_ENTRY = {
    "source": _COPY_SRC, "origin": "external", "evidence": "evi-obs-datasource",
    "cite": ["Arnot2006"],
    "description": "The same file decrypted; every analysis step read this copy.",
}
_NOTES_ENTRY = {
    "source": _NOTES_SRC, "name": "notes.csv", "origin": "derived",
    "description": "Counts exported while writing.",
}
_TERMS = {"license": "CC-BY-4.0", "redistribution": "author-asserted"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _item(run_dir: Path, ev_id: str, data_ref: str, *, write: bool = True) -> EvidenceItem:
    ev = EvidenceItem(
        id=ev_id, spec_id=run_dir.name, kind=EvidenceKind.OBSERVATION,
        created_at=datetime(2026, 10, 8, 16, 0, 0, tzinfo=timezone.utc),
        provenance=Provenance(code_ref="fixture", data_source="measured", data_ref=data_ref),
        # distinct findings: record.tex prints one item of a run of identical findings
        result=Result(type="qualitative", finding=f"the recorded step {ev_id}"),
        bears_on=[],
    )
    if write:
        (run_dir / "evidence" / f"{ev_id}.json").write_text(
            ev.model_dump_json(indent=2), encoding="utf-8")
    return ev


def _data_run(tmp_path: Path) -> Path:
    """The trial run in workspace ``tmp_path/ws``, with the synthetic files and items."""
    ws = tmp_path / "ws"
    run_dir = _trial_run(ws)
    for rel, data in ((_TABLE_SRC, _TABLE), (_WORKBOOK_SRC, _WORKBOOK), (_COPY_SRC, _COPY),
                      (_NOTES_SRC, _NOTES)):
        path = ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    lit = run_dir / "literature"
    lit.mkdir()
    (lit / "references.bib").write_text(_BIB, encoding="utf-8")
    _item(run_dir, "evi-obs-sample", f"{_TABLE_SRC} sha256 {_T}")
    _item(run_dir, "evi-obs-fit", f"{_TABLE_SRC} sha256={_T}")
    _item(run_dir, "evi-obs-baseline", f"(the table, sha256 {_T.upper()})")
    _item(run_dir, "evi-obs-datasource",
          f"{_WORKBOOK_SRC} sha256 {_W}; decrypted copy sha256 {_C}")
    _item(run_dir, "evi-obs-step-a", f"{_COPY_SRC} sha256 {_C}")
    _item(run_dir, "evi-obs-step-b", f"input sha256={_C}")
    return run_dir


def _declare(run_dir: Path, *entries: dict, **top) -> None:
    payload = {"spec_id": run_dir.name, **top, "files": list(entries)}
    (run_dir / "deposit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _rows(run_dir: Path) -> list[list[str]]:
    return _manifest_rows(run_dir)[1:]


def _row(run_dir: Path, sha: str) -> list[str]:
    matches = [r for r in _rows(run_dir) if r[1] == sha]
    assert len(matches) == 1, _rows(run_dir)
    return matches[0]


def _verify(run_dir: Path):
    report = verify_run(run_dir)
    return report.deposit_file_problems, report.paper_advisory


def _parse(files: list, **top):
    return parse_deposit_declaration({"spec_id": "S", **top, "files": files}, "S")


def _without(entry: dict, *keys: str) -> dict:
    return {k: v for k, v in entry.items() if k not in keys}


def _write_si(run_dir: Path, body: str) -> None:
    (run_dir / "paper" / "si.tex").write_text(
        "\\documentclass{article}\\begin{document}\n" + body + "\n\\end{document}\n",
        encoding="utf-8")


def _names_fails(run_dir: Path) -> list[str]:
    return [p for p in verify_run(run_dir).deposit_file_problems if "names" in p]


# --------------------------------------------------------------------------- #
# 14 -- schema
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("entry, needle", [
    ({**_TABLE_ENTRY, "extra": 1}, "extra"),
    ({**_TABLE_ENTRY, "name": "a/b.csv"}, "name"),
    ({**_TABLE_ENTRY, "name": ".hidden.csv"}, "name"),
    ({**_TABLE_ENTRY, "name": "spec.json"}, "vocabulary"),
    ({**_TABLE_ENTRY, "name": "claims.csv"}, "reserved"),
    ({**_TABLE_ENTRY, "name": "README.MD"}, "reserved"),
    ({**_TABLE_ENTRY, "source": "/abs/table.csv"}, "source"),
    ({**_TABLE_ENTRY, "source": "../table.csv"}, "source"),
    ({**_TABLE_ENTRY, "source": "analysis/../../table.csv"}, "source"),
    ({**_TABLE_ENTRY, "origin": "made"}, "origin"),
    ({**_TABLE_ENTRY, "description": "The frozen Spec rows."}, "vocabulary"),
    ({**_TABLE_ENTRY, "description": "two\nlines"}, "line"),
    (_without(_TABLE_ENTRY, "description"), "description"),
    ({**_TABLE_ENTRY, **_TERMS, "redistribution": "yes"}, "redistribution"),
    (_without(_TABLE_ENTRY, "evidence"), "evidence"),
    (_without(_WORKBOOK_ENTRY, "cite"), "cite"),
    ({**_WORKBOOK_ENTRY, "cite": []}, "cite"),
    ({**_TABLE_ENTRY, "cite": "Arnot2006"}, "cite"),
    ({**_without(_TABLE_ENTRY, "name"), **_TERMS}, "name"),          # ships, so needs a name
    ({**_without(_NOTES_ENTRY, "name")}, "name"),                    # empty cite: ships
    ({**_WORKBOOK_ENTRY, **_TERMS}, "name"),                         # external that ships
])
def test_an_invalid_entry_is_rejected_with_its_index(entry, needle):
    with pytest.raises(DepositDeclarationError, match=needle) as exc:
        _parse([_WORKBOOK_ENTRY, entry])
    assert "files[1]" in str(exc.value)


@pytest.mark.parametrize("first, second", [
    ("table.csv", "table.csv"),
    ("Chemicals.csv", "chemicals.csv"),
])
def test_two_names_in_one_folder_that_differ_at_most_in_case_are_rejected(first, second):
    a = {**_TABLE_ENTRY, **_TERMS, "name": first}
    b = {**_TABLE_ENTRY, **_TERMS, "name": second, "source": _NOTES_SRC}
    with pytest.raises(DepositDeclarationError, match=r"files\[1\]") as exc:
        _parse([a, b])
    assert second in str(exc.value)


def test_the_same_name_in_the_data_and_inputs_folders_loads():
    a = {**_TABLE_ENTRY, **_TERMS, "name": "same.xls"}
    b = {**_WORKBOOK_ENTRY, **_TERMS, "name": "same.xls"}
    assert len(_parse([a, b]).files) == 2


def test_a_cited_entry_that_does_not_ship_loads_without_a_name():
    decl = _parse([_without(_TABLE_ENTRY, "name"), _WORKBOOK_ENTRY])
    table, workbook = decl.files
    assert table.name is None and not table.ships
    assert workbook.name is None and not workbook.ships


def test_which_entries_ship():
    entries = _parse([
        _TABLE_ENTRY,                                          # cited, no terms
        {**_TABLE_ENTRY, "license": "CC-BY-4.0", "name": "b.csv"},
        {**_TABLE_ENTRY, "redistribution": "author-asserted", "name": "c.csv"},
        {**_TABLE_ENTRY, **_TERMS, "name": "d.csv"},
        _NOTES_ENTRY,                                          # derived, empty cite
        _WORKBOOK_ENTRY,                                       # external, no terms
        {**_WORKBOOK_ENTRY, "redistribution": "author-asserted", "name": "v.xls"},
        {**_WORKBOOK_ENTRY, "license": "CC-BY-4.0", "name": "u.xls"},
        {**_WORKBOOK_ENTRY, **_TERMS, "name": "w.xls"},        # external, both terms (Q9)
    ]).files
    assert [e.ships for e in entries] == [
        False, False, False, True, True, False, False, False, True]


def test_a_top_level_license_flagged_by_the_vocabulary_check_is_rejected():
    with pytest.raises(DepositDeclarationError, match="license"):
        _parse([], license="the Spec license")


def test_load_resolves_sources_in_the_run_dir_then_the_workspace(tmp_path):
    run_dir = _data_run(tmp_path)
    (run_dir / "local.csv").write_bytes(b"x\n")
    _declare(run_dir, {**_NOTES_ENTRY, "source": "local.csv"}, _NOTES_ENTRY | {"name": "n.csv"})
    decl = load_deposit_declaration(run_dir, _TRIAL_ID)
    assert [e.source for e in decl.files] == ["local.csv", _NOTES_SRC]


@pytest.mark.parametrize("case", [
    "missing", "outside-symlink", "spec", "history", "receipt", "paper",
])
def test_load_rejects_a_source_it_must_not_copy_with_the_entry_index(tmp_path, case):
    run_dir = _data_run(tmp_path)
    source = {
        "missing": "analysis/out/nothing.csv",
        "spec": "spec.json",
        "history": "spec_history/spec.v1.json",
        "receipt": "checkpoints/amendment-v2.json",
        "paper": f"runs/{_TRIAL_ID}/paper/table.csv",
        "outside-symlink": "analysis/out/linked.csv",
    }[case]
    if case == "paper":
        (run_dir / "paper").mkdir()
        (run_dir / "paper" / "table.csv").write_bytes(_TABLE)
    if case == "outside-symlink":
        outside = tmp_path / "outside" / "shared.csv"
        outside.parent.mkdir()
        outside.write_bytes(_TABLE)
        try:
            (tmp_path / "ws" / source).symlink_to(outside)
        except OSError:
            pytest.skip("symlinks not available")
    _declare(run_dir, _WORKBOOK_ENTRY, {**_NOTES_ENTRY, "source": source})
    with pytest.raises(DepositDeclarationError, match=r"files\[1\]"):
        load_deposit_declaration(run_dir, _TRIAL_ID)


def test_a_symlink_that_resolves_inside_the_workspace_is_accepted(tmp_path):
    run_dir = _data_run(tmp_path)
    link = tmp_path / "ws" / "analysis" / "out" / "alias.csv"
    try:
        link.symlink_to(tmp_path / "ws" / _NOTES_SRC)
    except OSError:
        pytest.skip("symlinks not available")
    _declare(run_dir, {**_NOTES_ENTRY, "source": "analysis/out/alias.csv"})
    assert load_deposit_declaration(run_dir, _TRIAL_ID).files[0].source == "analysis/out/alias.csv"


# --------------------------------------------------------------------------- #
# 5, 8 -- recorded tables: cited, not shipped, by default; shipped with both terms
# --------------------------------------------------------------------------- #

def test_a_cited_recorded_table_is_listed_with_its_checksum_and_not_shipped(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _TABLE_ENTRY)
    compiler = _render(run_dir)

    assert not (_deposit(run_dir) / "data").exists()
    row = _row(run_dir, _T)
    assert row == ["", _T, str(len(_TABLE)), "study data", "record.tex", "Arnot2006",
                   "not redistributed", _TABLE_ENTRY["description"]]
    summary = compiler.deposit_summary
    assert summary.data_shipped == ()
    assert len(summary.not_shipped) == 1
    assert _TABLE_SRC in summary.not_shipped[0]
    assert "license and redistribution" in summary.not_shipped[0]

    problems, advisory = _verify(run_dir)
    assert problems == []
    notes = [n for n in advisory if "cited, not shipped" in n]
    assert len(notes) == 1
    assert _T in notes[0] and "Arnot2006" in notes[0]
    assert "license and redistribution" in notes[0]


def test_a_cited_table_stating_both_terms_ships(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, **_TERMS})
    compiler = _render(run_dir)

    assert (_deposit(run_dir) / "data" / "table.csv").read_bytes() == _TABLE
    row = _row(run_dir, _T)
    assert row[0] == "data/table.csv"
    assert row[4] == "record.tex"
    assert row[6] == "CC-BY-4.0; redistribution asserted by the authors"
    assert compiler.deposit_summary.data_shipped == ("data/table.csv",)

    problems, advisory = _verify(run_dir)
    assert problems == []
    assert not any("cited, not shipped" in n for n in advisory)
    terms = [n for n in advisory if n.startswith("terms:") and "data/table.csv" in n]
    assert len(terms) == 1
    assert "CC-BY-4.0; redistribution asserted by the authors" in terms[0]


@pytest.mark.parametrize("given, missing", [
    ({"license": "CC-BY-4.0"}, "redistribution"),
    ({"redistribution": "author-asserted"}, "license"),
])
def test_one_term_alone_does_not_ship_a_cited_table(tmp_path, given, missing):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, **given})
    compiler = _render(run_dir)
    assert not (_deposit(run_dir) / "data").exists()
    assert _row(run_dir, _T)[0] == ""
    assert f"lacks {missing}" in compiler.deposit_summary.not_shipped[0]
    problems, advisory = _verify(run_dir)
    assert problems == []
    notes = [n for n in advisory if "cited, not shipped" in n]
    assert len(notes) == 1 and f"lacks {missing}" in notes[0]


def test_a_derived_entry_with_a_cite_follows_the_same_rule(tmp_path):
    run_dir = _data_run(tmp_path)
    cited = {**_NOTES_ENTRY, "cite": ["Arnot2006"]}
    _declare(run_dir, cited)
    _render(run_dir)
    assert not (_deposit(run_dir) / "data").exists()
    assert _row(run_dir, _N)[6] == "not redistributed"
    _declare(run_dir, {**cited, **_TERMS})
    _render(run_dir)
    assert (_deposit(run_dir) / "data" / "notes.csv").read_bytes() == _NOTES


def test_dropping_one_term_removes_the_copy_an_earlier_render_wrote(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, **_TERMS})
    _render(run_dir)
    assert (_deposit(run_dir) / "data" / "table.csv").is_file()
    _declare(run_dir, {**_TABLE_ENTRY, "license": "CC-BY-4.0"})
    _render(run_dir)
    assert not (_deposit(run_dir) / "data").exists()
    assert _verify(run_dir)[0] == []


def test_a_recorded_entry_against_an_item_without_the_hash_fails_naming_those_with_it(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, "evidence": "evi-obs-step-a"})
    compiler = _render(run_dir)
    assert any("evi-obs-step-a" in w for w in compiler.deposit_warnings)
    problems = _verify(run_dir)[0]
    lines = [p for p in problems if "evi-obs-step-a" in p]
    assert len(lines) == 1
    for holder in _TABLE_HOLDERS:
        assert holder in lines[0]


def test_a_recorded_entry_naming_an_item_the_record_lacks_fails(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, "evidence": "evi-obs-nowhere"})
    _render(run_dir)
    assert any("evi-obs-nowhere" in p for p in _verify(run_dir)[0])


def test_a_modified_shipped_copy_fails(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, **_TERMS})
    _render(run_dir)
    copy = _deposit(run_dir) / "data" / "table.csv"
    copy.write_bytes(_TABLE + b"C,3.5\n")
    assert any("data/table.csv" in p for p in _verify(run_dir)[0])


def test_a_source_changed_after_the_render_fails(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _TABLE_ENTRY)
    _render(run_dir)
    (tmp_path / "ws" / _TABLE_SRC).write_bytes(_TABLE + b"C,3.5\n")
    problems = _verify(run_dir)[0]
    assert any("re-render" in p for p in problems)                  # plan
    assert any("evi-obs-sample" in p for p in problems)             # recorded


def test_render_checks_the_evidence_it_is_given_and_verify_reads_the_disk(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, "evidence": "evi-obs-late"})
    late = _item(run_dir, "evi-obs-late", f"late copy sha256 {_T}", write=False)
    on_disk = [
        EvidenceItem.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((run_dir / "evidence").glob("*.json"))
    ]
    compiler = ResearchCompiler(workspace_dir=run_dir.parent.parent)
    compiler.stage_render(_spec_of(run_dir), evidence=[*on_disk, late])
    assert not any("evi-obs-late" in w for w in compiler.deposit_warnings)
    assert any("evi-obs-late" in p for p in _verify(run_dir)[0])


# --------------------------------------------------------------------------- #
# 6 -- derived
# --------------------------------------------------------------------------- #

def test_a_derived_file_ships_unchecked_and_names_no_other_file(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, license="CC-BY-4.0")
    _render(run_dir)
    assert (_deposit(run_dir) / "data" / "notes.csv").read_bytes() == _NOTES
    row = _row(run_dir, _N)
    assert row == ["data/notes.csv", _N, str(len(_NOTES)), "study data", "", "", "CC-BY-4.0",
                   _NOTES_ENTRY["description"]]
    problems, advisory = _verify(run_dir)
    assert problems == []
    notes = [n for n in advisory if "unchecked" in n and "notes.csv" in n]
    assert len(notes) == 1


def test_a_derived_entry_naming_a_missing_item_fails(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_NOTES_ENTRY, "evidence": "evi-obs-nowhere"})
    _render(run_dir)
    assert any("evi-obs-nowhere" in p for p in _verify(run_dir)[0])


def test_a_derived_file_the_record_holds_is_advised_to_be_declared_recorded(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_NOTES_ENTRY, "source": _TABLE_SRC, "name": "t.csv"})
    _render(run_dir)
    assert _row(run_dir, _T)[4] == ""             # a derived row names no other file
    problems, advisory = _verify(run_dir)
    assert problems == []
    notes = [n for n in advisory if "declare it recorded" in n]
    assert len(notes) == 1 and "evi-obs-sample" in notes[0]


# --------------------------------------------------------------------------- #
# 7 -- external
# --------------------------------------------------------------------------- #

def test_the_third_party_file_and_its_copy_are_listed_with_their_checksums_not_copied(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _WORKBOOK_ENTRY, _COPY_ENTRY)
    compiler = _render(run_dir)
    assert not (_deposit(run_dir) / "inputs").exists()
    for sha, data, entry in ((_W, _WORKBOOK, _WORKBOOK_ENTRY), (_C, _COPY, _COPY_ENTRY)):
        assert _row(run_dir, sha) == ["", sha, str(len(data)), "third-party data",
                                      "record.tex", "Arnot2006", "not redistributed",
                                      entry["description"]]
    assert len(compiler.deposit_summary.not_shipped) == 2
    assert all("third-party" in line for line in compiler.deposit_summary.not_shipped)
    assert _verify(run_dir)[0] == []


def test_an_external_copy_against_an_item_without_it_fails_naming_those_with_it(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_COPY_ENTRY, "evidence": "evi-obs-sample"})
    _render(run_dir)
    lines = [p for p in _verify(run_dir)[0] if "evi-obs-sample" in p]
    assert len(lines) == 1
    for holder in _COPY_HOLDERS:
        assert holder in lines[0]


def test_an_external_entry_with_both_terms_lands_in_inputs_with_its_terms_listed(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_WORKBOOK_ENTRY, "name": "workbook.xls", **_TERMS})
    _render(run_dir)
    assert (_deposit(run_dir) / "inputs" / "workbook.xls").read_bytes() == _WORKBOOK
    assert _row(run_dir, _W)[0] == "inputs/workbook.xls"
    assert _row(run_dir, _W)[6] == "CC-BY-4.0; redistribution asserted by the authors"
    problems, advisory = _verify(run_dir)
    assert problems == []
    assert any(n.startswith("terms:") and "inputs/workbook.xls" in n for n in advisory)


@pytest.mark.parametrize("entry", [
    {**_WORKBOOK_ENTRY, "cite": ["Nobody1999"]},
    {**_TABLE_ENTRY, "cite": ["Nobody1999"]},                  # cited, not shipped
    {**_TABLE_ENTRY, **_TERMS, "cite": ["Nobody1999"]},        # shipped
])
def test_a_cite_key_absent_from_the_bibliography_fails(tmp_path, entry):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, entry)
    _render(run_dir)
    assert any("Nobody1999" in p and "references.bib" in p for p in _verify(run_dir)[0])


def test_a_third_party_checksum_the_record_does_not_hold_fails(tmp_path):
    run_dir = _data_run(tmp_path)
    (tmp_path / "ws" / "data" / "raw" / "other.xls").write_bytes(b"unrecorded bytes")
    _declare(run_dir, {**_WORKBOOK_ENTRY, "source": "data/raw/other.xls"})
    _render(run_dir)
    assert any("no Evidence item holds it" in p for p in _verify(run_dir)[0])


# --------------------------------------------------------------------------- #
# 8 -- terms
# --------------------------------------------------------------------------- #

def test_no_top_level_license_gives_one_advisory(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY)
    _render(run_dir)
    notes = [n for n in _verify(run_dir)[1] if "no top-level license" in n]
    assert len(notes) == 1

    _declare(run_dir, _NOTES_ENTRY, license="CC-BY-4.0")
    _render(run_dir)
    assert not any("no top-level license" in n for n in _verify(run_dir)[1])


def test_the_top_level_license_goes_to_protocol_and_uncited_rows_never_to_cited_ones(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, _TABLE_ENTRY, {**_TABLE_ENTRY, "name": "t2.csv",
             "license": "ODbL-1.0", "redistribution": "author-asserted"},
             license="CC0-1.0")
    _render(run_dir)
    assert _row(run_dir, _V1_SHA)[6] == "CC0-1.0"
    assert _row(run_dir, _N)[6] == "CC0-1.0"
    cited = [r for r in _rows(run_dir) if r[1] == _T]
    assert sorted(r[6] for r in cited) == [
        "ODbL-1.0; redistribution asserted by the authors", "not redistributed"]


# --------------------------------------------------------------------------- #
# 11 -- manifests
# --------------------------------------------------------------------------- #

def test_the_manifest_with_data_rows_carries_no_record_id_and_passes_the_vocabulary_check(
        tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, **_TERMS}, _NOTES_ENTRY, _WORKBOOK_ENTRY, _COPY_ENTRY,
             license="CC-BY-4.0")
    _render(run_dir)
    text = (_deposit(run_dir) / "manifest.csv").read_text(encoding="utf-8")
    assert "evi-" not in text
    assert check_paper_tool_vocabulary(text) == []


def test_rows_order_protocol_by_path_then_unshipped_study_then_third_party_by_sha(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _COPY_ENTRY, _WORKBOOK_ENTRY, _TABLE_ENTRY)
    _render(run_dir)
    third = sorted([_W, _C])
    # the shipped record (record.tex) sorts by its path, after the protocol rows
    record = _sha((run_dir / "record.tex").read_bytes())
    assert [r[1] for r in _rows(run_dir)] == [_A2_SHA, _V1_SHA, _V2_SHA, record, _T, *third]

    _withhold(run_dir)
    payload = json.loads((run_dir / "deposit.json").read_text(encoding="utf-8"))
    payload["files"] = [_COPY_ENTRY, _WORKBOOK_ENTRY, _TABLE_ENTRY]
    (run_dir / "deposit.json").write_text(json.dumps(payload), encoding="utf-8")
    _render(run_dir)
    assert [r[1] for r in _rows(run_dir)] == [_A2_SHA, _V1_SHA, _V2_SHA, record, _T, *third]


def test_a_shipped_data_row_sorts_by_its_path_before_the_protocol_rows(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, {**_WORKBOOK_ENTRY, "name": "w.xls", **_TERMS})
    _render(run_dir)
    assert [r[0] for r in _rows(run_dir)] == [
        "data/notes.csv", "inputs/w.xls", "protocol/amendment-v2.json",
        "protocol/protocol-v1.json", "protocol/protocol-v2.json", "record.tex"]


def test_rerender_with_data_is_byte_identical(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_TABLE_ENTRY, **_TERMS}, _NOTES_ENTRY, _WORKBOOK_ENTRY)
    _render(run_dir)
    first = _files_under(_deposit(run_dir))
    _render(run_dir)
    assert _files_under(_deposit(run_dir)) == first


# --------------------------------------------------------------------------- #
# 9 -- the persisted declaration and the --deposit flag
# --------------------------------------------------------------------------- #

def _declaration_file(tmp_path: Path, run_dir: Path, *entries: dict, **top) -> Path:
    path = tmp_path / "drafts" / "deposit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"spec_id": run_dir.name, **top, "files": list(entries)}
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return path


def test_render_with_deposit_persists_the_declaration_and_says_what_it_shipped(
        tmp_path, capsys):
    run_dir = _data_run(tmp_path)
    decl = _declaration_file(tmp_path, run_dir, _NOTES_ENTRY, _TABLE_ENTRY, _WORKBOOK_ENTRY)
    assert main(["render", str(run_dir), "--deposit", str(decl)]) == 0
    assert (run_dir / "deposit.json").read_bytes() == decl.read_bytes()
    out = capsys.readouterr().out
    assert str(decl) in out
    assert "1 data file(s) shipped" in out
    assert "2 cited only" in out
    assert _TABLE_SRC in out and _WORKBOOK_SRC in out
    assert (_deposit(run_dir) / "data" / "notes.csv").is_file()

    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert f"runs/{_TRIAL_ID}/deposit.json" in out.replace("\\", "/")


def test_a_bare_render_and_resolve_ship_what_the_last_declaration_named(tmp_path):
    run_dir = _data_run(tmp_path)
    decl = _declaration_file(tmp_path, run_dir, _NOTES_ENTRY)
    assert main(["render", str(run_dir), "--deposit", str(decl)]) == 0
    first = _files_under(_deposit(run_dir))
    assert "data/notes.csv" in first
    assert main(["render", str(run_dir)]) == 0
    assert _files_under(_deposit(run_dir)) == first
    run_checkpoint_loop(run_dir=run_dir, spec=_spec_of(run_dir))
    # resolve records new Claims, so the record copy and its manifest row follow the record;
    # every other file is unchanged
    after = _files_under(_deposit(run_dir))
    assert sorted(after) == sorted(first)
    assert after["record.tex"] == (run_dir / "record.tex").read_bytes()
    unchanged = [k for k in first if k not in ("record.tex", "manifest.csv")]
    assert [after[k] for k in unchanged] == [first[k] for k in unchanged]


def test_run_with_deposit_and_a_bare_run_and_resolve_ship_the_data(tmp_path, capsys):
    ws = tmp_path / "ws"
    proposal = tmp_path / "p.md"
    proposal.write_text(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n", encoding="utf-8")
    (ws / "analysis" / "out").mkdir(parents=True)
    (ws / _NOTES_SRC).write_bytes(_NOTES)
    run_dir = ws / "runs" / "dep-data-run"
    decl = tmp_path / "deposit.json"
    decl.write_text(json.dumps({"spec_id": "dep-data-run", "files": [_NOTES_ENTRY]}),
                    encoding="utf-8")
    argv = ["run", str(proposal), "-o", str(ws), "--spec-id", "dep-data-run"]
    assert main([*argv, "--deposit", str(decl)]) == 0
    assert "1 data file(s) shipped" in capsys.readouterr().out
    shipped = _deposit(run_dir) / "data" / "notes.csv"
    assert shipped.read_bytes() == _NOTES
    assert (run_dir / "deposit.json").read_bytes() == decl.read_bytes()
    assert main(argv) == 0
    assert shipped.read_bytes() == _NOTES
    assert main(["resolve", str(run_dir)]) == 0
    assert shipped.read_bytes() == _NOTES


def test_an_empty_or_absent_file_list_stops_shipping_and_removes_the_files(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, {**_TABLE_ENTRY, **_TERMS})
    _render(run_dir)
    assert (_deposit(run_dir) / "data").is_dir()
    decl = _declaration_file(tmp_path, run_dir)                        # files: []
    assert main(["render", str(run_dir), "--deposit", str(decl)]) == 0
    assert not (_deposit(run_dir) / "data").exists()
    assert _verify(run_dir)[0] == []
    (run_dir / "deposit.json").write_text(json.dumps({"spec_id": _TRIAL_ID}), encoding="utf-8")
    _render(run_dir)
    assert load_deposit_declaration(run_dir, _TRIAL_ID).files == ()


def test_an_invalid_declaration_changes_nothing(tmp_path, capsys):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY)
    _render(run_dir)
    persisted = (run_dir / "deposit.json").read_bytes()
    before = _files_under(run_dir / "paper")
    bad = _declaration_file(tmp_path, run_dir, {**_NOTES_ENTRY, "colour": "red"})
    assert main(["render", str(run_dir), "--deposit", str(bad)]) == 2
    assert "colour" in capsys.readouterr().err
    assert (run_dir / "deposit.json").read_bytes() == persisted
    assert _files_under(run_dir / "paper") == before


def test_a_declaration_whose_source_is_missing_stops_the_render(tmp_path, capsys):
    run_dir = _data_run(tmp_path)
    bad = _declaration_file(tmp_path, run_dir, {**_NOTES_ENTRY, "source": "nowhere.csv"})
    assert main(["render", str(run_dir), "--deposit", str(bad)]) == 2
    assert "nowhere.csv" in capsys.readouterr().err
    assert not (run_dir / "deposit.json").exists()
    assert not (run_dir / "paper").exists()


def test_deposit_with_record_only_is_rejected_and_nothing_under_paper_changes(tmp_path, capsys):
    run_dir = _data_run(tmp_path)
    decl = _declaration_file(tmp_path, run_dir, _NOTES_ENTRY)
    with pytest.raises(SystemExit) as exc:
        main(["render", str(run_dir), "--record-only", "--deposit", str(decl)])
    assert exc.value.code == 2
    assert "--deposit" in capsys.readouterr().err
    assert not (run_dir / "paper").exists()
    assert not (run_dir / "deposit.json").exists()


def test_a_missing_deposit_file_is_an_error(tmp_path, capsys):
    run_dir = _data_run(tmp_path)
    assert main(["render", str(run_dir), "--deposit", str(tmp_path / "none.json")]) == 2
    assert "none.json" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# 10 -- ownership and removal guards, with data
# --------------------------------------------------------------------------- #

def test_a_declared_name_colliding_with_an_unlisted_file_stops_the_render(tmp_path):
    run_dir = _data_run(tmp_path)
    _render(run_dir)
    foreign = _deposit(run_dir) / "data" / "notes.csv"
    foreign.parent.mkdir()
    foreign.write_bytes(b"an author's own file")
    _declare(run_dir, _NOTES_ENTRY)
    with pytest.raises(DepositRefused, match="notes.csv"):
        _render(run_dir)
    assert foreign.read_bytes() == b"an author's own file"


def test_removing_one_entry_removes_only_that_entrys_file(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, {**_TABLE_ENTRY, **_TERMS})
    _render(run_dir)
    _declare(run_dir, _NOTES_ENTRY)
    _render(run_dir)
    assert sorted(p.name for p in (_deposit(run_dir) / "data").iterdir()) == ["notes.csv"]


@pytest.mark.parametrize("cell", ["../draft.tex", "data/../../draft.tex", "/tmp/x"])
def test_a_tampered_data_row_removes_nothing(tmp_path, cell):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, {**_TABLE_ENTRY, **_TERMS})
    _render(run_dir)
    draft = run_dir / "paper" / "draft.tex"
    draft_bytes = draft.read_bytes()
    manifest = _deposit(run_dir) / "manifest.csv"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        "data/notes.csv", cell, 1), encoding="utf-8")
    _declare(run_dir)                                    # the declaration shrinks to nothing
    compiler = _render(run_dir)
    assert draft.read_bytes() == draft_bytes
    assert (_deposit(run_dir) / "data" / "table.csv").is_file()
    assert (_deposit(run_dir) / "data" / "notes.csv").is_file()
    assert any(cell in w for w in compiler.deposit_warnings)


def test_a_lost_manifest_with_data_does_not_block_and_leaves_a_dropped_file_to_the_author(
        tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _NOTES_ENTRY, {**_TABLE_ENTRY, **_TERMS})
    _render(run_dir)
    manifest = _deposit(run_dir) / "manifest.csv"
    lost = manifest.read_bytes()
    manifest.unlink()
    _render(run_dir)
    assert manifest.read_bytes() == lost
    assert _verify(run_dir)[0] == []

    manifest.unlink()
    _declare(run_dir, _NOTES_ENTRY)                      # shrinks with the manifest lost
    _render(run_dir)
    assert (_deposit(run_dir) / "data" / "table.csv").is_file()
    assert any("data/table.csv" in p and "not in the manifest" in p
               for p in _verify(run_dir)[0])


def test_a_symlinked_data_folder_stops_the_render_without_writing(tmp_path):
    run_dir = _data_run(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = _deposit(run_dir) / "data"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")
    _declare(run_dir, _NOTES_ENTRY)
    with pytest.raises(DepositRefused, match="symbolic link"):
        _render(run_dir)
    assert list(elsewhere.iterdir()) == []


# --------------------------------------------------------------------------- #
# 12, 17 -- names the paper gives deposited files
# --------------------------------------------------------------------------- #

def _named_run(tmp_path: Path) -> Path:
    """Ships data/my_table.csv and the protocol; the cited table is cited, not shipped."""
    run_dir = _data_run(tmp_path)
    _declare(run_dir, {**_NOTES_ENTRY, "name": "my_table.csv"}, _TABLE_ENTRY,
             license="CC-BY-4.0")
    _render(run_dir)
    return run_dir


@pytest.mark.parametrize("text", [
    r"The table (deposit/data/my\_table.csv) lists them.",
    r"See \texttt{deposit/data/my\_table.csv}.",
    r"See \path{deposit/data/my_table.csv}.",
    "the rows in deposit/data/my_table.csv.",
    "the rows in deposit/data/my_table.csv, and",
    "(deposit/data/my_table.csv)",
    "deposit/manifest.csv lists every file",
    "the script reads data/raw/x.xls",
    "an archive at zenodo.org/deposit/1.json",
    r"\url{https://example.org/deposit/x.csv}",
    r"\href{https://example.org/deposit/y.csv}{the archive}",
    "the files in deposit/protocol/ and deposit/data/",
    "protocol-v1.json and protocol-v2.json",
    r"\texttt{amendment-v2.json}",
    "my-protocol-v1.json",
])
def test_a_name_the_bundle_holds_or_that_is_no_deposit_path_passes(tmp_path, text):
    run_dir = _named_run(tmp_path)
    _write_si(run_dir, text)
    assert _names_fails(run_dir) == []


@pytest.mark.parametrize("text, needle", [
    ("see deposit/data/missing.csv", "deposit/data/missing.csv"),
    ("see deposit/data/My_table.csv", "deposit/data/My_table.csv"),
    ("protocol-v3.json", "protocol-v3.json"),
    ("Protocol-V1.json", "Protocol-V1.json"),
    (r"\texttt{deposit/protocol/protocol-v3.json}", "deposit/protocol/protocol-v3.json"),
])
def test_a_name_the_bundle_does_not_hold_fails(tmp_path, text, needle):
    run_dir = _named_run(tmp_path)
    _write_si(run_dir, text)
    fails = _names_fails(run_dir)
    assert len(fails) == 1 and needle in fails[0] and "si.tex" in fails[0]


def test_naming_a_cited_table_that_is_not_shipped_fails_saying_so(tmp_path):
    run_dir = _named_run(tmp_path)
    _write_si(run_dir, r"The table is \texttt{deposit/data/table.csv}.")
    fails = _names_fails(run_dir)
    assert len(fails) == 1 and "not shipped" in fails[0]


def test_names_in_the_draft_are_checked_too(tmp_path):
    run_dir = _named_run(tmp_path)
    draft = run_dir / "paper" / "draft.tex"
    draft.write_text(draft.read_text(encoding="utf-8").replace(
        r"\end{document}", "See deposit/data/absent.csv.\n\\end{document}"), encoding="utf-8")
    fails = _names_fails(run_dir)
    assert len(fails) == 1 and "draft.tex" in fails[0]


@pytest.mark.parametrize("text", [
    r"\texttt{deposit/protocol/protocol-v1.json}",
    "the first version (protocol-v1.json)",
    r"\texttt{amendment-v2.json}",
])
def test_naming_a_withheld_protocol_file_fails_saying_it_is_withheld(tmp_path, text):
    run_dir = _data_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    _write_si(run_dir, text)
    fails = _names_fails(run_dir)
    assert len(fails) == 1 and "withheld" in fails[0]


def test_the_withheld_example_of_d9_passes(tmp_path):
    run_dir = _data_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    text = (
        "The protocol (versions 1 and 2) and its amendment are not distributed with this "
        "paper: the proposal includes a collaborator's unpublished results. "
        r"\texttt{deposit/manifest.csv} lists the SHA-256 of each of the three files, so a "
        "copy released later can be checked against them."
    )
    _write_si(run_dir, text)
    assert _names_fails(run_dir) == []
    assert check_paper_tool_vocabulary(text) == []


def test_the_trial_si_rewritten_as_in_d9_passes_the_vocabulary_and_names_checks(tmp_path):
    run_dir = _data_run(tmp_path)
    _declare(run_dir, _TABLE_ENTRY, _WORKBOOK_ENTRY, _COPY_ENTRY, license="CC-BY-4.0")
    _render(run_dir)
    split = r"\allowbreak".join(rf"\texttt{{{_V1_SHA[i:i + 16]}}}" for i in range(0, 64, 16))
    text = (
        r"Version 1 of the protocol (\texttt{deposit/protocol/protocol-v1.json}) was created "
        r"at 2026-10-08T10:03:39Z. The amendment (\texttt{deposit/protocol/amendment-v2.json}, "
        f"recorded at 2026-10-08T14:05:17Z) stores the SHA-256 of the version it replaced, "
        f"{split}, which is the checksum of \\texttt{{deposit/protocol/protocol-v1.json}}. "
        r"Version 2 (\texttt{deposit/protocol/protocol-v2.json}) is the protocol the results "
        "were judged against.\n\n"
        r"The protocol in both versions and its amendment (\texttt{deposit/protocol/}) are "
        r"distributed with this paper; \texttt{deposit/manifest.csv} lists every file with its "
        "SHA-256 and the terms it is distributed under. Files produced in this study are "
        "distributed under CC BY 4.0. The table of the rows that passed the filters contains "
        "values from Arnot and Gobas (2006) and is not distributed."
    )
    _write_si(run_dir, text)
    assert _names_fails(run_dir) == []
    assert check_paper_tool_vocabulary(text) == []


def test_a_paper_naming_no_deposited_file_gets_the_pointed_to_advisory(tmp_path):
    run_dir = _named_run(tmp_path)
    _write_si(run_dir, "Nothing about the files here.")
    assert sum("pointed to" in n for n in _verify(run_dir)[1]) == 1
    _write_si(run_dir, r"See \texttt{deposit/data/my\_table.csv}.")
    assert not any("pointed to" in n for n in _verify(run_dir)[1])
