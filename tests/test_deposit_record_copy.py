"""
The record ships with the paper (design/deposit-files.md D4, D5, D9, D13; the user's decision
of 2026-10-11).

Every full render writes a byte copy of ``runs/<id>/record.tex`` to
``paper/deposit/record.tex`` and lists it in ``paper/deposit/manifest.csv``, so the
``sha256_also_in`` cells that name ``record.tex`` point at a file the reader holds. ``verify``
fails a copy that is not byte-identical to ``runs/<id>/record.tex`` and a ``sha256_also_in``
target the bundle does not hold. A ``--record-only`` render still writes nothing under
``paper/``; a run that withholds its protocol still ships the record.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.evidence import EvidenceItem, EvidenceKind, Provenance, Result
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.render.deposit import (
    RECORD_DESCRIPTION,
    DataPlan,
    DepositRefused,
    ProtocolPlan,
    deposit_bundle_problems,
    deposit_name_problems,
    plan_protocol,
    prepare_deposit_write,
)
from sci_adk.render.paper import check_paper_tool_vocabulary
from sci_adk.render.prose import AuthoredSI, SISection
from tests.test_deposit_protocol import (
    _PROTOCOL_FILES,
    _deposit,
    _deposit_problems,
    _files_under,
    _manifest_rows,
    _passing_run,
    _render,
    _sha,
    _spec_of,
    _trial_run,
    _withhold,
)

_DESCRIPTION = (
    "the deterministic record of the study: every recorded item, its time and checksums"
)


def _record(run_dir: Path) -> bytes:
    return (run_dir / "record.tex").read_bytes()


def _copy(run_dir: Path) -> Path:
    return _deposit(run_dir) / "record.tex"


def _rows_by_file(run_dir: Path) -> dict:
    return {r[0]: r for r in _manifest_rows(run_dir)[1:] if r[0]}


def _append_evidence(run_dir: Path, ev_id: str = "evi-obs-late-1") -> None:
    item = EvidenceItem(
        id=ev_id, spec_id=run_dir.name, kind=EvidenceKind.OBSERVATION,
        created_at=datetime.fromisoformat("2026-10-09T09:00:00+00:00"),
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="qualitative", finding="a late observation, recorded after render"),
    )
    (run_dir / "evidence" / f"{ev_id}.json").write_text(
        item.model_dump_json(indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #

def test_render_ships_a_byte_copy_of_the_record(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    assert _copy(run_dir).read_bytes() == _record(run_dir)


def test_the_manifest_lists_the_record_after_the_protocol_rows(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    rows = _manifest_rows(run_dir)[1:]
    assert [r[0] for r in rows] == [*(f"protocol/{n}" for n in _PROTOCOL_FILES), "record.tex"]
    data = _record(run_dir)
    assert rows[-1] == [
        "record.tex", _sha(data), str(len(data)), "record", "", "", "", _DESCRIPTION]
    assert RECORD_DESCRIPTION == _DESCRIPTION


def test_the_record_row_takes_the_top_level_license(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "deposit.json").write_text(json.dumps(
        {"spec_id": run_dir.name, "license": "CC-BY-4.0"}), encoding="utf-8")
    _render(run_dir)
    assert _rows_by_file(run_dir)["record.tex"][6] == "CC-BY-4.0"


def test_every_sha256_also_in_target_is_a_file_of_the_bundle(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    rows = _manifest_rows(run_dir)[1:]
    targets = {t for r in rows for t in r[4].split(";") if t}
    assert "record.tex" in targets
    for target in targets:
        assert (_deposit(run_dir) / target).is_file(), target


def test_the_manifest_with_the_record_row_passes_the_vocabulary_check(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    text = (_deposit(run_dir) / "manifest.csv").read_text(encoding="utf-8")
    assert "evi-" not in text
    assert check_paper_tool_vocabulary(text) == []


def test_a_rerender_leaves_the_copy_byte_identical_and_warns_nothing(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    first = _files_under(_deposit(run_dir))
    compiler = _render(run_dir)
    assert _files_under(_deposit(run_dir)) == first
    assert not any("record.tex" in w for w in compiler.deposit_warnings)


def test_a_rerender_after_new_evidence_replaces_the_copy(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    old = _copy(run_dir).read_bytes()
    _append_evidence(run_dir)
    _render(run_dir)
    assert _copy(run_dir).read_bytes() == _record(run_dir) != old
    assert _rows_by_file(run_dir)["record.tex"][1] == _sha(_record(run_dir))
    assert _deposit_problems(run_dir) == []


def test_an_unamended_run_ships_the_record_beside_its_protocol(tmp_path):
    run_dir = _passing_run(tmp_path)
    assert sorted(_files_under(_deposit(run_dir))) == [
        "manifest.csv", "protocol/protocol-v1.json", "record.tex"]
    assert _copy(run_dir).read_bytes() == _record(run_dir)


def test_render_says_the_record_shipped(tmp_path, capsys):
    run_dir = _trial_run(tmp_path)
    assert main(["render", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "deposit: no declaration (no runs/<id>/deposit.json): the protocol and the record " \
        "ship" in out
    assert f"deposit: record shipped -> {_copy(run_dir)}" in out


def test_record_only_writes_nothing_under_paper_and_leaves_a_shipped_copy_alone(tmp_path):
    run_dir = _trial_run(tmp_path)
    ResearchCompiler(workspace_dir=tmp_path).stage_render_record(_spec_of(run_dir))
    assert not (run_dir / "paper").exists()

    _render(run_dir)
    before = _files_under(_deposit(run_dir))
    ResearchCompiler(workspace_dir=tmp_path).stage_render_record(_spec_of(run_dir))
    assert _files_under(_deposit(run_dir)) == before


# --------------------------------------------------------------------------- #
# withheld protocol: the record still ships
# --------------------------------------------------------------------------- #

def test_a_withheld_protocol_still_ships_the_record(tmp_path):
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    assert sorted(_files_under(_deposit(run_dir))) == ["manifest.csv", "record.tex"]
    assert _copy(run_dir).read_bytes() == _record(run_dir)
    rows = _manifest_rows(run_dir)[1:]
    assert [r[0] for r in rows] == ["", "", "", "record.tex"]
    assert _deposit_problems(run_dir) == []


def test_with_no_top_level_license_the_terms_advisory_names_the_record(tmp_path):
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)              # no protocol file ships, no data declared: the record does
    _render(run_dir)
    notes = [n for n in verify_run(run_dir).paper_advisory
             if n.startswith("terms: no top-level license")]
    assert len(notes) == 1 and "the record, the protocol files" in notes[0], notes


def test_the_shipped_record_carries_no_raw_proposal_and_no_amendment_rationale(tmp_path):
    """Withholding stops the protocol files; the record holds the hypotheses' statements and
    decision rules (as the paper does) and the protocol checksums, never the raw proposal
    or the amendment rationale (measured on the trial fixture)."""
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    record = _copy(run_dir).read_text(encoding="utf-8")
    spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    texts = [v for v in spec["raw_proposal"].values() if isinstance(v, str) and v]
    texts.append(spec["amendment_rationale"])
    assert texts
    for text in texts:
        assert text[:60] not in record, text[:60]
    for f in plan_protocol(run_dir).files:
        assert f.sha256 in record


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #

def test_verify_passes_a_fresh_render_with_the_record_copy(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    assert _deposit_problems(run_dir) == []


def test_a_changed_byte_in_the_copy_fails(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    copy = _copy(run_dir)
    copy.write_bytes(copy.read_bytes().replace(b"\\section{", b"\\section*{", 1))
    problems = _deposit_problems(run_dir)
    assert f"paper/deposit/record.tex differs from runs/{run_dir.name}/record.tex -- " \
        "re-render" in problems


def test_a_record_changed_after_the_render_fails_the_copy_and_the_plan(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    _append_evidence(run_dir)
    ResearchCompiler(workspace_dir=tmp_path).stage_render_record(_spec_of(run_dir))
    problems = _deposit_problems(run_dir)
    assert f"paper/deposit/record.tex differs from runs/{run_dir.name}/record.tex -- " \
        "re-render" in problems
    assert any("lacks the row" in p and "record.tex" in p for p in problems)


def test_a_missing_copy_fails(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    _copy(run_dir).unlink()
    problems = _deposit_problems(run_dir)
    assert any(p.startswith("paper/deposit/record.tex is missing") for p in problems)


def test_a_missing_record_fails_the_copy_check(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    (run_dir / "record.tex").unlink()
    problems = _deposit_problems(run_dir)
    assert any(p.startswith(f"runs/{run_dir.name}/record.tex is missing") for p in problems)


def test_a_sha256_also_in_target_the_bundle_does_not_hold_fails(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    manifest = _deposit(run_dir) / "manifest.csv"
    marker, body = manifest.read_text(encoding="utf-8").split("\n", 1)
    rows = list(csv.reader(io.StringIO(body)))
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(r for r in rows if r[0] != "record.tex")
    manifest.write_text(marker + "\n" + buf.getvalue(), encoding="utf-8")
    _copy(run_dir).unlink()
    plan = plan_protocol(run_dir)
    problems = deposit_bundle_problems(run_dir / "paper", plan, _record(run_dir), DataPlan())
    assert any(
        "sha256_also_in points to record.tex, which the bundle does not hold" in p
        for p in problems
    ), problems


# --------------------------------------------------------------------------- #
# D13: render owns paper/deposit/record.tex
# --------------------------------------------------------------------------- #

def test_an_unlisted_record_with_other_bytes_stops_the_render_before_writing(tmp_path):
    run_dir = _trial_run(tmp_path)
    target = _copy(run_dir)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"an author's own notes")
    with pytest.raises(DepositRefused, match="record.tex"):
        _render(run_dir)
    assert target.read_bytes() == b"an author's own notes"
    assert not (run_dir / "paper" / "draft.tex").exists()


def test_a_listed_copy_edited_by_hand_is_replaced_by_the_next_render(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    copy = _copy(run_dir)
    copy.write_bytes(copy.read_bytes() + b"% edited\n")
    _render(run_dir)
    assert copy.read_bytes() == _record(run_dir)
    assert _deposit_problems(run_dir) == []


def test_a_lost_manifest_with_the_same_record_bytes_does_not_block(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    manifest = _deposit(run_dir) / "manifest.csv"
    lost = manifest.read_bytes()
    manifest.unlink()
    _render(run_dir)
    assert manifest.read_bytes() == lost
    assert _deposit_problems(run_dir) == []


def test_a_manifest_listing_record_tex_is_trusted_and_another_root_file_is_not(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    paper = run_dir / "paper"
    write = prepare_deposit_write(paper, {})
    assert write.warnings == ()
    assert "record.tex" in write.removals

    manifest = _deposit(run_dir) / "manifest.csv"
    draft = paper / "draft.tex"
    data = draft.read_bytes()
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f"../draft.tex,{_sha(data)},{len(data)},record,,,,x\n", encoding="utf-8")
    write = prepare_deposit_write(paper, {})
    assert write.removals == ()
    assert any("../draft.tex" in w for w in write.warnings)


def test_a_symlinked_record_copy_stops_the_render(tmp_path):
    run_dir = _trial_run(tmp_path)
    elsewhere = tmp_path / "elsewhere.tex"
    elsewhere.write_bytes(b"kept")
    link = _copy(run_dir)
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(elsewhere)
    except OSError:
        pytest.skip("symlinks not available")
    with pytest.raises(DepositRefused, match="symbolic link"):
        _render(run_dir)
    assert elsewhere.read_bytes() == b"kept"


# --------------------------------------------------------------------------- #
# names: the paper and SI may name deposit/record.tex
# --------------------------------------------------------------------------- #

def test_the_names_check_accepts_deposit_record_tex():
    docs = {"si.tex": r"Every item is in the record of the study (\path{deposit/record.tex})."}
    plan = ProtocolPlan(spec_id="S", version=1, files=())
    fails, advisories = deposit_name_problems(docs, plan, DataPlan())
    assert fails == []
    assert not any("pointed to" in a for a in advisories)
    assert check_paper_tool_vocabulary(docs["si.tex"]) == []


def test_an_authored_si_naming_deposit_record_tex_renders_and_verifies(tmp_path):
    run_dir = _trial_run(tmp_path)
    si = AuthoredSI(sections=[SISection(
        title="Data and code availability",
        body=(r"The record of the study (\path{deposit/record.tex}) lists every recorded "
              r"item with its time and the checksums of the files it used; "
              r"\path{deposit/manifest.csv} lists every file with its checksum."),
    )])
    ResearchCompiler(workspace_dir=tmp_path).stage_render(_spec_of(run_dir), si=si)
    si_tex = (run_dir / "paper" / "si.tex").read_text(encoding="utf-8")
    assert "deposit/record.tex" in si_tex
    assert not any("names" in p for p in _deposit_problems(run_dir))
    assert _deposit_problems(run_dir) == []
