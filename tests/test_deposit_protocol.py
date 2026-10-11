"""
Deposit files, Phase 1a (design/deposit-files.md D1-D5, D11-D13; test plan items 1-4, 10,
11, 14 (protocol switch), 16 and the per-run part of 17).

The frozen protocol history ships with every full render under ``paper/deposit/protocol/``
as exact bytes, listed in ``paper/deposit/manifest.csv``; ``verify`` checks the copies
against the record, the record's history files and receipts against one another, prints a
protocol digest and a times advisory. A run withholds its protocol with two keys in its
persisted declaration, ``runs/<id>/deposit.json``.

The trial fixture (``tests/fixtures/deposit_bcfkow``) holds the trial run's real
``spec.json`` (version 2), ``spec_history/spec.v1.json``, ``checkpoints/amendment-v2.json``
and the nine Evidence items that the times advisory reads (the seven recorded between the
two versions and the two primary analyses). Other runs are built with the real verbs
(``init-spec``'s stage and ``amend-spec``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.deposit import (
    DepositDeclarationError,
    load_deposit_declaration,
    parse_deposit_declaration,
)
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.spec import Spec
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.provenance import record_digest
from sci_adk.render.deposit import (
    MANIFEST_MARKER,
    DepositRefused,
    digest_of_files,
    manifest_text,
    plan_protocol,
    protocol_digest,
    protocol_record_problems,
    protocol_rows,
    times_advisory,
)
from sci_adk.render.paper import check_paper_tool_vocabulary
from tests.test_amend_spec_content import _spec as _two_hyp_spec
from tests.test_verify import (
    _freeze_minimal_pubreqs,
    _numeric_experiment,
    _numeric_spec,
    _seed,
    _write_paper,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "deposit_bcfkow"
_TRIAL_ID = "SPEC-BCFKOW-001"
_V1_SHA = "4fa76e47b30482581e1fe74dc4d9b77ca16a50d52c886585a9b399c5a767fa66"
_V2_SHA = "c70d091fb152e32c15f20897c1d931ca69674fde402d9ef13171897de2f461ff"
_A2_SHA = "9035bfa84e0e78f34973036e14679fff89e7fa3e4f31336a1e8b6bc7e2c4cbb4"
_REASON = "The proposal includes a collaborator's unpublished results."
_PROTOCOL_FILES = ["amendment-v2.json", "protocol-v1.json", "protocol-v2.json"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _trial_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / _TRIAL_ID
    shutil.copytree(_FIXTURE, run_dir)
    return run_dir


def _spec_of(run_dir: Path) -> Spec:
    return Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))


def _render(run_dir: Path) -> ResearchCompiler:
    compiler = ResearchCompiler(workspace_dir=run_dir.parent.parent)
    compiler.stage_render(_spec_of(run_dir))
    return compiler


def _deposit(run_dir: Path) -> Path:
    return run_dir / "paper" / "deposit"


def _files_under(root: Path) -> dict:
    return {
        str(p.relative_to(root)).replace("\\", "/"): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _manifest_rows(run_dir: Path) -> list[list[str]]:
    import csv
    import io

    text = (_deposit(run_dir) / "manifest.csv").read_text(encoding="utf-8")
    lines = text.split("\n", 1)
    return list(csv.reader(io.StringIO(lines[1])))


def _withhold(run_dir: Path, reason: str = _REASON) -> None:
    (run_dir / "deposit.json").write_text(json.dumps({
        "spec_id": run_dir.name, "protocol": "withheld", "protocol_reason": reason,
    }), encoding="utf-8")


def _deposit_problems(run_dir: Path) -> list[str]:
    return verify_run(run_dir).deposit_file_problems


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _amended_run(tmp_path: Path, spec_id: str = "dep-am") -> Path:
    """A run frozen by init-spec's stage and amended once (rationale-only) by amend-spec."""
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=_two_hyp_spec(spec_id))
    run_dir = tmp_path / "runs" / spec_id
    assert main(["amend-spec", str(run_dir), "--rationale", "a stated reason"]) == 0
    return run_dir


def _passing_run(tmp_path: Path, spec_id: str = "dep-pass") -> Path:
    """A numeric run that verify passes once a clean draft replaces the skeleton."""
    run_dir = _seed(tmp_path, _numeric_spec(spec_id, value=0.9), _numeric_experiment(0.95))
    _freeze_minimal_pubreqs(run_dir)
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a} The point estimate is 0.95.")
    return run_dir


def _evidence_at(spec_id: str, ev_id: str, when: str, target: str | None) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id, spec_id=spec_id, kind=EvidenceKind.OBSERVATION,
        created_at=datetime.fromisoformat(when.replace("Z", "+00:00")),
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="qualitative", finding="an observation"),
        bears_on=(
            [Bearing(target_id=target, direction=BearingDirection.NEUTRAL)] if target else []
        ),
    )


# --------------------------------------------------------------------------- #
# 1 -- protocol render
# --------------------------------------------------------------------------- #

def test_render_ships_the_protocol_history_as_exact_bytes(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)

    protocol = _deposit(run_dir) / "protocol"
    assert sorted(p.name for p in protocol.iterdir()) == _PROTOCOL_FILES
    assert (protocol / "protocol-v1.json").read_bytes() == (
        run_dir / "spec_history" / "spec.v1.json").read_bytes()
    assert (protocol / "protocol-v2.json").read_bytes() == (run_dir / "spec.json").read_bytes()
    assert (protocol / "amendment-v2.json").read_bytes() == (
        run_dir / "checkpoints" / "amendment-v2.json").read_bytes()
    receipt = json.loads((protocol / "amendment-v2.json").read_text(encoding="utf-8"))
    assert _sha((protocol / "protocol-v1.json").read_bytes()) == _V1_SHA
    assert receipt["prior_spec_sha256"] == _V1_SHA


def test_manifest_starts_with_the_marker_and_lists_the_protocol_rows_by_path(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)

    text = (_deposit(run_dir) / "manifest.csv").read_text(encoding="utf-8")
    assert text.split("\n", 1)[0] == MANIFEST_MARKER
    assert MANIFEST_MARKER == (
        "# Written with this paper; do not edit. Paths are relative to this folder.")
    header, *rows = _manifest_rows(run_dir)
    assert header == ["file", "sha256", "bytes", "kind", "sha256_also_in", "cite",
                      "license", "description"]
    assert [r[0] for r in rows] == [f"protocol/{n}" for n in _PROTOCOL_FILES]
    by_file = {r[0]: r for r in rows}
    v1 = by_file["protocol/protocol-v1.json"]
    assert v1[1:4] == [_V1_SHA, "17552", "protocol"]
    assert v1[7] == "protocol, version 1, replaced by version 2"
    v2 = by_file["protocol/protocol-v2.json"]
    assert v2[1:4] == [_V2_SHA, "18761", "protocol"]
    assert v2[7] == "protocol, version 2 (current)"
    a2 = by_file["protocol/amendment-v2.json"]
    assert a2[1] == _A2_SHA and a2[3] == "amendment"
    assert a2[7] == "amendment that produced version 2"


def test_rerender_is_byte_identical(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    first = _files_under(_deposit(run_dir))
    _render(run_dir)
    assert _files_under(_deposit(run_dir)) == first


def test_unamended_run_ships_protocol_v1_alone(tmp_path):
    run_dir = _passing_run(tmp_path)
    assert sorted(p.name for p in (_deposit(run_dir) / "protocol").iterdir()) == [
        "protocol-v1.json"]
    assert (_deposit(run_dir) / "protocol" / "protocol-v1.json").read_bytes() == (
        run_dir / "spec.json").read_bytes()
    rows = _manifest_rows(run_dir)[1:]
    assert [r[0] for r in rows] == ["protocol/protocol-v1.json"]
    assert rows[0][7] == "protocol, version 1 (current)"


def test_record_only_render_writes_nothing_under_paper(tmp_path):
    run_dir = _trial_run(tmp_path)
    ResearchCompiler(workspace_dir=tmp_path).stage_render_record(_spec_of(run_dir))
    assert not (run_dir / "paper").exists()


# --------------------------------------------------------------------------- #
# 11 -- manifests
# --------------------------------------------------------------------------- #

def test_manifest_carries_no_record_identifier_and_passes_the_vocabulary_check(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    text = (_deposit(run_dir) / "manifest.csv").read_text(encoding="utf-8")
    assert "evi-" not in text
    assert check_paper_tool_vocabulary(text) == []


def test_sha256_also_in_names_the_amendment_and_the_record_where_they_print_it(tmp_path):
    run_dir = _trial_run(tmp_path)
    plan = plan_protocol(run_dir)
    rows = {r.file: r for r in protocol_rows(plan, record_text="")}
    assert rows["protocol/protocol-v1.json"].sha256_also_in == "protocol/amendment-v2.json"
    assert rows["protocol/protocol-v2.json"].sha256_also_in == ""
    assert rows["protocol/amendment-v2.json"].sha256_also_in == ""
    # record.tex is searched for each 64-hex token (Phase 1b prints the protocol history
    # there); a token inside a longer hex run is not a match
    record = f"v1 {_V1_SHA}; v2 {_V2_SHA.upper()}; a {_A2_SHA}0"
    rows = {r.file: r for r in protocol_rows(plan, record_text=record)}
    assert rows["protocol/protocol-v1.json"].sha256_also_in == (
        "protocol/amendment-v2.json;record.tex")
    assert rows["protocol/protocol-v2.json"].sha256_also_in == "record.tex"
    assert rows["protocol/amendment-v2.json"].sha256_also_in == ""


def test_top_level_license_appears_in_shipped_protocol_rows(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "deposit.json").write_text(json.dumps(
        {"spec_id": _TRIAL_ID, "license": "CC-BY-4.0"}), encoding="utf-8")
    _render(run_dir)
    assert {r[6] for r in _manifest_rows(run_dir)[1:]} == {"CC-BY-4.0"}


def test_an_edited_sha256_cell_fails(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    manifest = _deposit(run_dir) / "manifest.csv"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        _V2_SHA, "0" * 64), encoding="utf-8")
    problems = _deposit_problems(run_dir)
    assert any("protocol/protocol-v2.json" in p and "SHA-256" in p for p in problems)


# --------------------------------------------------------------------------- #
# 2 -- protocol checks
# --------------------------------------------------------------------------- #

def test_verify_passes_on_a_rendered_trial_bundle_and_says_consistent(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    assert report.deposit_files_clean
    assert "consistent" in report.protocol_history
    assert "record digest" in report.protocol_history
    assert "verified" not in report.protocol_history


def test_verify_passes_end_to_end_on_a_rendered_numeric_run(tmp_path):
    run_dir = _passing_run(tmp_path)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    assert report.passed


def test_one_changed_byte_in_a_shipped_protocol_file_fails(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    copy = _deposit(run_dir) / "protocol" / "protocol-v1.json"
    data = bytearray(copy.read_bytes())
    data[10] ^= 0x01
    copy.write_bytes(bytes(data))
    report = verify_run(run_dir)
    assert not report.deposit_files_clean
    assert any("protocol-v1.json" in p for p in report.deposit_file_problems)
    assert not report.passed


def test_an_amendment_after_the_render_fails_plan_and_current_protocol(tmp_path):
    run_dir = _amended_run(tmp_path)
    _render(run_dir)
    assert _deposit_problems(run_dir) == []
    assert main(["amend-spec", str(run_dir), "--rationale", "another reason"]) == 0
    problems = _deposit_problems(run_dir)
    assert any("re-render" in p for p in problems)
    assert any("protocol-v3.json" in p for p in problems)


def test_a_version_not_kept_is_advisory(tmp_path):
    run_dir = _amended_run(tmp_path)
    (run_dir / "spec_history" / "spec.v1.json").unlink()
    receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["prior_spec_sha256"] = None
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    _render(run_dir)

    rows = {r[7]: r for r in _manifest_rows(run_dir)[1:]}
    not_kept = rows["protocol, version 1; file not kept"]
    assert not_kept[0] == "" and not_kept[1] == "" and not_kept[2] == ""
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    assert any("version 1" in note and "not kept" in note for note in report.paper_advisory)


def test_a_deleted_history_file_whose_checksum_the_receipt_holds_fails(tmp_path):
    run_dir = _amended_run(tmp_path)
    (run_dir / "spec_history" / "spec.v1.json").unlink()
    fails, _notes = protocol_record_problems(plan_protocol(run_dir))
    assert any("spec.v1.json" in f and "missing" in f for f in fails)


def test_a_consistent_rewrite_of_version_1_passes_the_chain_and_moves_only_the_protocol_digest(
    tmp_path,
):
    run_dir = _amended_run(tmp_path)
    digest_before = protocol_digest(plan_protocol(run_dir))
    record_before = record_digest(run_dir)

    history = run_dir / "spec_history" / "spec.v1.json"
    payload = json.loads(history.read_text(encoding="utf-8"))
    payload["raw_proposal"]["goal"] = "A different goal, written later."
    history.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["prior_spec_sha256"] = _sha(history.read_bytes())
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    fails, _notes = protocol_record_problems(plan_protocol(run_dir))
    assert fails == []          # what the chain does not show
    assert record_digest(run_dir) == record_before
    assert protocol_digest(plan_protocol(run_dir)) != digest_before


def test_a_changed_created_at_of_version_1_fails_the_prior_version_link(tmp_path):
    run_dir = _amended_run(tmp_path)
    history = run_dir / "spec_history" / "spec.v1.json"
    payload = json.loads(history.read_text(encoding="utf-8"))
    payload["created_at"] = "2020-01-02T00:00:00Z"
    history.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["prior_spec_sha256"] = _sha(history.read_bytes())
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    fails, _notes = protocol_record_problems(plan_protocol(run_dir))
    assert any("prior_version_id" in f for f in fails)


def test_a_changed_receipt_rationale_fails_the_amendments_check(tmp_path):
    run_dir = _amended_run(tmp_path)
    receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["rationale"] = "a rationale written afterwards"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    fails, _notes = protocol_record_problems(plan_protocol(run_dir))
    assert any("rationale" in f for f in fails)


def test_render_prints_record_side_problems_as_warnings(tmp_path):
    run_dir = _amended_run(tmp_path)
    receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["rationale"] = "a rationale written afterwards"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    compiler = _render(run_dir)
    assert any("rationale" in w for w in compiler.deposit_warnings)


# --------------------------------------------------------------------------- #
# 3 -- protocol digest
# --------------------------------------------------------------------------- #

def test_protocol_digest_equals_the_sha256sum_recipe_on_the_bundle(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    expected = protocol_digest(plan_protocol(run_dir))
    lines = "".join(
        f"{_sha((_deposit(run_dir) / 'protocol' / n).read_bytes())}  {n}\n"
        for n in sorted(_PROTOCOL_FILES)
    )
    assert expected == _sha(lines.encode("ascii"))
    assert verify_run(run_dir).protocol_digest == expected
    if shutil.which("sha256sum") and shutil.which("sh"):
        out = subprocess.run(
            "LC_ALL=C sha256sum $(LC_ALL=C ls) | sha256sum", shell=True, check=True,
            cwd=_deposit(run_dir) / "protocol", capture_output=True, text=True,
        ).stdout.split()[0]
        assert out == expected


def test_appending_evidence_leaves_the_protocol_digest_and_an_amendment_changes_it(tmp_path):
    run_dir = _amended_run(tmp_path)
    before = protocol_digest(plan_protocol(run_dir))
    ev = _evidence_at("dep-am", "evi-late", "2030-01-01T00:00:00Z", "hyp-a")
    (run_dir / "evidence").mkdir(exist_ok=True)
    (run_dir / "evidence" / "evi-late.json").write_text(
        ev.model_dump_json(indent=2), encoding="utf-8")
    assert protocol_digest(plan_protocol(run_dir)) == before

    assert main(["amend-spec", str(run_dir), "--rationale", "a third version"]) == 0
    assert protocol_digest(plan_protocol(run_dir)) != before
    # the value printed while version 2 was current is recomputed from the files of
    # versions 1 and 2 and amendment 2
    files = {
        "protocol-v1.json": (run_dir / "spec_history" / "spec.v1.json").read_bytes(),
        "protocol-v2.json": (run_dir / "spec_history" / "spec.v2.json").read_bytes(),
        "amendment-v2.json": (run_dir / "checkpoints" / "amendment-v2.json").read_bytes(),
    }
    assert digest_of_files(files) == before


# --------------------------------------------------------------------------- #
# 4 -- times advisory
# --------------------------------------------------------------------------- #

def _fixture_evidence(run_dir: Path) -> list[EvidenceItem]:
    return [
        EvidenceItem.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((run_dir / "evidence").glob("*.json"))
    ]


def test_times_advisory_on_the_trial_prints_its_lines_and_flags_nothing(tmp_path):
    run_dir = _trial_run(tmp_path)
    text = times_advisory(plan_protocol(run_dir), _fixture_evidence(run_dir))
    lines = [line.strip() for line in text.splitlines()]
    assert lines[0] == ("times (local clocks, not witnessed): protocol v1 2026-10-08T10:03:39Z; "
                        "amendment v2 2026-10-08T14:05:17Z")
    assert lines[1] == ("earliest Evidence 2026-10-08T10:04:41Z (literature); earliest "
                        "bearing on a hypothesis 2026-10-08T16:53:36Z")
    assert lines[2] == ("7 item(s) recorded between v1 and v2 bear on no hypothesis "
                        "(literature 3, novelty_decision 2, prior_work_decision 1, "
                        "contested_record 1)")
    assert len(lines) == 3


def test_an_item_bearing_on_h1_before_version_2_is_flagged(tmp_path):
    run_dir = _trial_run(tmp_path)
    early = _evidence_at(_TRIAL_ID, "evi-early-h1", "2026-10-08T12:00:00Z", "H1")
    text = times_advisory(plan_protocol(run_dir), [*_fixture_evidence(run_dir), early])
    flagged = [line for line in text.splitlines() if "evi-early-h1" in line]
    assert len(flagged) == 1
    assert "before protocol v2" in flagged[0] and "H1" in flagged[0]


def test_an_item_created_before_version_1_is_flagged_whatever_it_bears_on(tmp_path):
    run_dir = _trial_run(tmp_path)
    early = _evidence_at(_TRIAL_ID, "evi-before-v1", "2026-10-08T09:00:00Z", None)
    text = times_advisory(plan_protocol(run_dir), [*_fixture_evidence(run_dir), early])
    assert any("evi-before-v1" in line and "before protocol v1" in line
               for line in text.splitlines())


def test_a_version_not_kept_makes_every_hypothesis_count_as_changed(tmp_path):
    run_dir = _amended_run(tmp_path)        # rationale-only: hypotheses depend on version 1
    between = _evidence_at("dep-am", "evi-between", "2021-01-01T00:00:00Z", "hyp-a")
    text = times_advisory(plan_protocol(run_dir), [between])
    assert "evi-between" not in text

    (run_dir / "spec_history" / "spec.v1.json").unlink()
    text = times_advisory(plan_protocol(run_dir), [between])
    assert any("evi-between" in line and "before protocol v2" in line
               for line in text.splitlines())
    assert any("version 1" in line and "not kept" in line for line in text.splitlines())


def test_verify_adds_the_times_advisory_for_a_run_with_a_paper(tmp_path):
    run_dir = _passing_run(tmp_path)
    notes = [n for n in verify_run(run_dir).paper_advisory if n.startswith("times (")]
    assert len(notes) == 1
    assert "protocol v1 " in notes[0]


# --------------------------------------------------------------------------- #
# 10 -- ownership and removal guards
# --------------------------------------------------------------------------- #

def test_author_files_outside_the_deposit_are_neither_touched_nor_inventoried(tmp_path):
    run_dir = _trial_run(tmp_path)
    author = run_dir / "paper" / "data" / "table.dat"
    author.parent.mkdir(parents=True)
    author.write_bytes(b"1 2 3\n")
    _render(run_dir)
    assert author.read_bytes() == b"1 2 3\n"
    assert _deposit_problems(run_dir) == []


def test_an_author_file_inside_the_deposit_fails_the_inventory_and_survives_a_rerender(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    dropped = _deposit(run_dir) / "data" / "mine.csv"
    dropped.parent.mkdir()
    dropped.write_bytes(b"a,b\n")
    assert any("data/mine.csv" in p for p in _deposit_problems(run_dir))
    _render(run_dir)
    assert dropped.read_bytes() == b"a,b\n"
    assert any("data/mine.csv" in p for p in _deposit_problems(run_dir))


def test_an_unlisted_file_with_other_bytes_at_a_target_stops_the_render(tmp_path):
    run_dir = _trial_run(tmp_path)
    target = _deposit(run_dir) / "protocol" / "protocol-v1.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"someone else's file")
    with pytest.raises(DepositRefused, match="protocol-v1.json"):
        _render(run_dir)
    assert target.read_bytes() == b"someone else's file"
    assert not (run_dir / "paper" / "draft.tex").exists()


@pytest.mark.parametrize("cell", ["../draft.tex", "data/../../draft.tex", "/tmp/x"])
def test_a_tampered_manifest_cell_removes_nothing(tmp_path, cell):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    draft = run_dir / "paper" / "draft.tex"
    draft_bytes = draft.read_bytes()
    manifest = _deposit(run_dir) / "manifest.csv"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f"{cell},{_sha(draft_bytes)},{len(draft_bytes)},protocol,,,,x\n",
        encoding="utf-8",
    )
    _withhold(run_dir)          # this render writes no protocol file: removal is attempted
    compiler = _render(run_dir)
    assert draft.read_bytes() == draft_bytes
    assert all((_deposit(run_dir) / "protocol" / n).is_file() for n in _PROTOCOL_FILES)
    assert any(cell in w for w in compiler.deposit_warnings)


def test_a_manifest_cell_through_a_symlink_removes_nothing(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    draft = run_dir / "paper" / "draft.tex"
    draft_bytes = draft.read_bytes()
    link = _deposit(run_dir) / "data" / "link.tex"
    link.parent.mkdir()
    try:
        link.symlink_to(draft)
    except OSError:
        pytest.skip("symlinks not available")
    manifest = _deposit(run_dir) / "manifest.csv"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f"data/link.tex,{_sha(draft_bytes)},{len(draft_bytes)},study data,,,,x\n",
        encoding="utf-8",
    )
    compiler = _render(run_dir)
    assert draft.read_bytes() == draft_bytes
    assert link.is_symlink()
    assert any("data/link.tex" in w for w in compiler.deposit_warnings)


def test_a_manifest_without_the_marker_stops_the_render_and_removes_nothing(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    manifest = _deposit(run_dir) / "manifest.csv"
    manifest.write_text("file,sha256\n", encoding="utf-8")
    before = _files_under(_deposit(run_dir))
    _withhold(run_dir)
    with pytest.raises(DepositRefused, match="manifest.csv"):
        _render(run_dir)
    assert _files_under(_deposit(run_dir)) == before


def test_a_listed_file_edited_by_hand_is_not_removed_and_fails_the_inventory(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    edited = _deposit(run_dir) / "protocol" / "protocol-v1.json"
    edited.write_bytes(edited.read_bytes() + b"\n")
    _withhold(run_dir)
    compiler = _render(run_dir)
    assert edited.is_file()
    assert any("protocol/protocol-v1.json" in w for w in compiler.deposit_warnings)
    assert not (_deposit(run_dir) / "protocol" / "protocol-v2.json").exists()
    assert any("protocol/protocol-v1.json" in p for p in _deposit_problems(run_dir))


def test_a_lost_manifest_does_not_block_the_next_render(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    manifest = _deposit(run_dir) / "manifest.csv"
    lost = manifest.read_bytes()
    manifest.unlink()
    _render(run_dir)
    assert manifest.read_bytes() == lost
    assert _deposit_problems(run_dir) == []

    manifest.unlink()
    _withhold(run_dir)          # the declaration shrinks with the manifest lost
    _render(run_dir)
    assert (_deposit(run_dir) / "protocol" / "protocol-v1.json").is_file()
    problems = _deposit_problems(run_dir)
    assert any("protocol/protocol-v1.json" in p for p in problems)


@pytest.mark.parametrize("which", ["deposit", "protocol"])
def test_a_symlinked_deposit_folder_stops_the_render_without_writing(tmp_path, which):
    run_dir = _trial_run(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = _deposit(run_dir) if which == "deposit" else _deposit(run_dir) / "protocol"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")
    with pytest.raises(DepositRefused, match="symbolic link"):
        _render(run_dir)
    assert list(elsewhere.iterdir()) == []


# --------------------------------------------------------------------------- #
# 16 -- backward compatibility
# --------------------------------------------------------------------------- #

def test_a_paper_rendered_before_deposit_files_gets_one_advisory_and_the_same_verdict(tmp_path):
    run_dir = _passing_run(tmp_path)
    shutil.rmtree(_deposit(run_dir))
    report = verify_run(run_dir)
    assert report.passed
    assert report.deposit_file_problems == []
    notes = [n for n in report.paper_advisory if "paper/deposit/" in n]
    assert len(notes) == 1 and "re-render" in notes[0]


def test_a_run_without_a_paper_gets_no_deposit_check(tmp_path):
    run_dir = _trial_run(tmp_path)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    assert not any("paper/deposit/" in n for n in report.paper_advisory)
    assert report.protocol_digest == protocol_digest(plan_protocol(run_dir))


# --------------------------------------------------------------------------- #
# 14 -- the protocol switch in the declaration
# --------------------------------------------------------------------------- #

def test_a_declaration_with_only_the_switch_loads_with_no_files():
    decl = parse_deposit_declaration(
        {"spec_id": "S", "protocol": "withheld", "protocol_reason": _REASON}, "S")
    assert decl.withheld and decl.protocol_reason == _REASON and decl.files == ()


@pytest.mark.parametrize("payload, needle", [
    ({"spec_id": "S", "protocol": "hidden", "protocol_reason": "r"}, "protocol"),
    ({"spec_id": "S", "protocol": "withheld"}, "protocol_reason"),
    ({"spec_id": "S", "protocol_reason": "r"}, "protocol_reason"),
    ({"spec_id": "S", "protocol": "withheld", "protocol_reason": "one\ntwo"}, "line"),
    ({"spec_id": "S", "protocol": "withheld", "protocol_reason": ""}, "protocol_reason"),
    ({"spec_id": "S", "protocol": "withheld", "protocol_reason": "   "}, "protocol_reason"),
    ({"spec_id": "S", "protocol": "withheld",
      "protocol_reason": "The frozen Spec names a partner."}, "vocabulary"),
    ({"spec_id": "S", "extra": 1}, "extra"),
    ({"spec_id": "T"}, "spec_id"),
    ({}, "spec_id"),
    ({"spec_id": "S", "files": {}}, "files"),
])
def test_an_invalid_switch_or_top_level_key_is_rejected(payload, needle):
    with pytest.raises(DepositDeclarationError, match=needle):
        parse_deposit_declaration(payload, "S")


def test_an_invalid_persisted_declaration_stops_the_render_before_anything_is_written(tmp_path):
    run_dir = _trial_run(tmp_path)
    (run_dir / "deposit.json").write_text(
        json.dumps({"spec_id": _TRIAL_ID, "protocol": "withheld"}), encoding="utf-8")
    with pytest.raises(DepositDeclarationError):
        _render(run_dir)
    assert not (run_dir / "paper").exists()
    assert load_deposit_declaration(tmp_path / "runs" / "none", "x") is None


# --------------------------------------------------------------------------- #
# 17 -- withheld protocol (per run)
# --------------------------------------------------------------------------- #

def test_a_withheld_protocol_ships_the_manifest_alone_with_the_checksums(tmp_path):
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)

    assert sorted(p.name for p in _deposit(run_dir).iterdir()) == ["manifest.csv"]
    rows = _manifest_rows(run_dir)[1:]
    assert len(rows) == 3
    by_sha = {r[1]: r for r in rows}
    assert set(by_sha) == {_V1_SHA, _V2_SHA, _A2_SHA}
    v1 = by_sha[_V1_SHA]
    assert v1[0] == "" and v1[2] == "17552" and v1[6] == ""
    for row in rows:
        assert row[0] == "" and row[6] == ""
        assert row[7].endswith(f"; withheld: {_REASON}")
    # the rows keep the places their files would have
    assert [r[1] for r in rows] == [_A2_SHA, _V1_SHA, _V2_SHA]
    text = (_deposit(run_dir) / "manifest.csv").read_text(encoding="utf-8")
    assert check_paper_tool_vocabulary(text) == []


def test_a_withheld_unamended_run_has_one_row(tmp_path):
    run_dir = _passing_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    rows = _manifest_rows(run_dir)[1:]
    assert len(rows) == 1 and rows[0][0] == ""


def test_withholding_changes_neither_the_record_nor_the_digests(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    shipped = ((run_dir / "record.tex").read_bytes(), protocol_digest(plan_protocol(run_dir)),
               record_digest(run_dir))
    _withhold(run_dir)
    _render(run_dir)
    assert ((run_dir / "record.tex").read_bytes(), protocol_digest(plan_protocol(run_dir)),
            record_digest(run_dir)) == shipped


def test_verify_on_a_withheld_bundle_passes_with_one_advisory_naming_the_reason(tmp_path):
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    report = verify_run(run_dir)
    assert report.deposit_file_problems == []
    notes = [n for n in report.paper_advisory if n.startswith("protocol withheld")]
    assert notes == [
        f"protocol withheld ({_REASON}): readers cannot check the protocol or what the paper "
        "says about it, such as when it was written; the manifest lists the SHA-256 of each "
        "withheld file"
    ]


@pytest.mark.parametrize("tamper", ["rationale", "created_at"])
def test_the_record_side_comparisons_still_run_when_withheld(tmp_path, tamper):
    run_dir = _amended_run(tmp_path)
    _withhold(run_dir)
    _render(run_dir)
    assert _deposit_problems(run_dir) == []
    if tamper == "rationale":
        receipt_path = run_dir / "checkpoints" / "amendment-v2.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["rationale"] = "a rationale written afterwards"
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    else:
        history = run_dir / "spec_history" / "spec.v1.json"
        payload = json.loads(history.read_text(encoding="utf-8"))
        payload["created_at"] = "2020-01-02T00:00:00Z"
        history.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    problems = _deposit_problems(run_dir)
    assert any(("rationale" if tamper == "rationale" else "prior_version_id") in p
               for p in problems)


def test_shipped_then_withheld_then_shipped_again(tmp_path):
    run_dir = _trial_run(tmp_path)
    _render(run_dir)
    first = _files_under(_deposit(run_dir))

    _withhold(run_dir)                       # written by hand
    assert any("re-render" in p for p in _deposit_problems(run_dir))   # plan
    _render(run_dir)
    assert not (_deposit(run_dir) / "protocol").exists()
    assert _deposit_problems(run_dir) == []

    copied = _deposit(run_dir) / "protocol" / "protocol-v1.json"
    copied.parent.mkdir()
    copied.write_bytes((run_dir / "spec_history" / "spec.v1.json").read_bytes())
    assert any("protocol/protocol-v1.json" in p for p in _deposit_problems(run_dir))
    copied.unlink()
    copied.parent.rmdir()

    (run_dir / "deposit.json").write_text(json.dumps({"spec_id": _TRIAL_ID}), encoding="utf-8")
    _render(run_dir)
    assert _files_under(_deposit(run_dir)) == first


def test_record_only_with_the_switch_persisted_writes_the_same_record(tmp_path):
    run_dir = _trial_run(tmp_path)
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_render_record(_spec_of(run_dir))
    shipped = (run_dir / "record.tex").read_bytes()
    _withhold(run_dir)
    compiler.stage_render_record(_spec_of(run_dir))
    assert (run_dir / "record.tex").read_bytes() == shipped


# --------------------------------------------------------------------------- #
# CLI -- the protocol digest is printed
# --------------------------------------------------------------------------- #

def test_render_status_and_verify_print_the_protocol_digest(tmp_path, capsys):
    run_dir = _trial_run(tmp_path)
    digest = protocol_digest(plan_protocol(run_dir))
    line = f"  protocol digest (sha256): {digest}"

    assert main(["render", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert line in out.splitlines()
    assert "paper/deposit/protocol" in out

    main(["status", str(run_dir)])
    assert line in capsys.readouterr().out.splitlines()

    main(["verify", str(run_dir)])
    assert line in capsys.readouterr().out.splitlines()


def test_render_says_when_the_protocol_is_withheld(tmp_path, capsys):
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    assert main(["render", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert f"protocol withheld ({_REASON})" in out


def test_render_cli_reports_a_refused_deposit_as_an_error(tmp_path, capsys):
    run_dir = _trial_run(tmp_path)
    manifest = _deposit(run_dir) / "manifest.csv"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("not ours\n", encoding="utf-8")
    assert main(["render", str(run_dir)]) == 2
    assert "manifest.csv" in capsys.readouterr().err


def test_run_prints_the_deposit_and_reports_a_refused_one_as_an_error(tmp_path, capsys):
    proposal = tmp_path / "p.md"
    proposal.write_text(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n", encoding="utf-8")
    assert main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "dep-run"]) == 0
    out = capsys.readouterr().out
    assert any(line.startswith("  protocol digest (sha256): ") for line in out.splitlines())

    manifest = tmp_path / "runs" / "dep-run" / "paper" / "deposit" / "manifest.csv"
    manifest.write_text("not ours\n", encoding="utf-8")
    assert main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "dep-run"]) == 2
    err = capsys.readouterr().err
    assert "manifest.csv" in err and "Traceback" not in err


def test_rows_of_a_plan_render_through_manifest_text_deterministically(tmp_path):
    run_dir = _trial_run(tmp_path)
    plan = plan_protocol(run_dir)
    text = manifest_text(protocol_rows(plan, record_text=None))
    assert text == manifest_text(protocol_rows(plan_protocol(run_dir), record_text=None))
    assert text.endswith("\n") and "\r" not in text
