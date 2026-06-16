"""
Network-free unit tests for the literature acquisition loop stage.

A fake adapter stands in for paperforge (no subprocess, no network); the Spec is
a minimal stub since the stage only reads ``spec.id``. These verify the stage's
real jobs: turning an acquisition result into a LITERATURE EvidenceItem under
runs/<spec.id>/, persisting it, and raising the right halt (unacquired papers /
Supporting Information needed).
"""

import json
import types
from pathlib import Path

from sci_adk.core.evidence import BearingDirection, EvidenceItem, EvidenceKind
from sci_adk.loop.literature_acquirer import (
    AcquisitionHalt,
    AcquisitionOutcome,
    HaltItem,
    HaltReason,
    LiteratureAcquirer,
    acquire_literature,
)
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult

PIN = "60fefedacb7349c755c29b2c2f26873464158c12"


class FakeAdapter:
    """Records the fetch call and returns a result built from the given dir."""

    def __init__(self, records, returncode=0):
        self.records = records
        self.returncode = returncode
        self.calls = []

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        self.calls.append((list(dois), output_dir, options))
        return AcquisitionResult(
            returncode=self.returncode,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=self.records,
            provenance={
                "tool": "paperforge",
                "pinned_sha": PIN,
                "installed_version": "0.1.0",
                "returncode": self.returncode,
            },
        )


def _spec(spec_id="test-spec"):
    return types.SimpleNamespace(id=spec_id)


def test_acquire_writes_literature_evidence(tmp_path):
    records = [
        AcquisitionRecord(doi="10.1/a", status="success",
                          source="arxiv", filename="A.pdf"),
        AcquisitionRecord(doi="10.2/b", status="failed", error="no OA PDF"),
    ]
    adapter = FakeAdapter(records, returncode=1)
    acquirer = LiteratureAcquirer(_spec(), workspace_dir=tmp_path, adapter=adapter)

    outcome = acquirer.acquire(["10.1/a", "10.2/b"])
    assert isinstance(outcome, AcquisitionOutcome)
    ev = outcome.evidence

    assert isinstance(ev, EvidenceItem)
    assert ev.kind == EvidenceKind.LITERATURE
    assert ev.spec_id == "test-spec"
    assert ev.result.type == "qualitative"

    summary = json.loads(ev.result.finding)
    assert summary["counts"] == {"succeeded": 1, "failed": 1}
    assert summary["acquired"][0]["doi"] == "10.1/a"
    assert summary["acquired"][0]["source"] == "arxiv"
    assert summary["failed"][0]["doi"] == "10.2/b"

    lit_dir = tmp_path / "runs" / "test-spec" / "literature"
    assert ev.result.artifact_ref == str(lit_dir)
    assert ev.provenance.data_ref == str(lit_dir / "manifest.csv")
    assert "paperforge@60fefed" in ev.provenance.environment

    # the adapter was driven with the run's literature dir
    called_dois, called_dir, _ = adapter.calls[0]
    assert called_dois == ["10.1/a", "10.2/b"]
    assert called_dir == lit_dir

    # evidence is persisted to the append-only log on disk
    ev_files = list((tmp_path / "runs" / "test-spec" / "evidence").glob("*.json"))
    assert len(ev_files) == 1
    on_disk = json.loads(ev_files[0].read_text(encoding="utf-8"))
    assert on_disk["kind"] == "literature"
    assert on_disk["spec_id"] == "test-spec"


def test_no_target_means_empty_bears_on(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a"])
    assert outcome.evidence.bears_on == []


def test_target_id_attaches_neutral_bearing(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a"], target_id="hyp-1")
    bears_on = outcome.evidence.bears_on
    assert len(bears_on) == 1
    assert bears_on[0].target_id == "hyp-1"
    # acquisition asserts no direction of its own -> NEUTRAL context link
    assert bears_on[0].direction == BearingDirection.NEUTRAL


def test_options_passthrough_via_convenience(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    outcome = acquire_literature(
        _spec("s2"), ["10.1/a"], workspace_dir=tmp_path, adapter=adapter,
        source_order=["arxiv"], no_metadata=True,
    )
    assert isinstance(outcome, AcquisitionOutcome)
    _, _, options = adapter.calls[0]
    assert options["source_order"] == ["arxiv"]
    assert options["no_metadata"] is True


# -- halt gates --------------------------------------------------------------

def test_unacquired_papers_trigger_halt(tmp_path):
    records = [
        AcquisitionRecord(doi="10.1/ok", status="success", source="arxiv"),
        AcquisitionRecord(doi="10.2/miss", status="failed", error="no OA PDF"),
        AcquisitionRecord(doi="10.3/miss", status="failed", error="paywalled"),
    ]
    adapter = FakeAdapter(records, returncode=1)
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(
                                     ["10.1/ok", "10.2/miss", "10.3/miss"])

    assert outcome.should_halt is True
    assert outcome.halt.reason == HaltReason.UNACQUIRED_PAPERS
    # the halt lists exactly the misses, with their reasons, for user feedback
    halted = {it.doi: it.detail for it in outcome.halt.items}
    assert halted == {"10.2/miss": "no OA PDF", "10.3/miss": "paywalled"}
    fb = outcome.halt.feedback()
    assert "10.2/miss" in fb and "paywalled" in fb
    # the whole batch is still recorded (the success too) -- halt != skip
    assert json.loads(outcome.evidence.result.finding)["counts"]["succeeded"] == 1


def test_all_acquired_means_no_halt(tmp_path):
    records = [
        AcquisitionRecord(doi="10.1/a", status="success", source="arxiv"),
        AcquisitionRecord(doi="10.2/b", status="success", source="unpaywall"),
    ]
    adapter = FakeAdapter(records, returncode=0)
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a", "10.2/b"])
    assert outcome.should_halt is False
    assert outcome.halt is None


def test_supporting_info_halt_factory():
    # Condition 2 is agent-judged: the orchestrator builds this after Claude
    # reads a main text and decides the SI is required.
    halt = AcquisitionHalt.for_supporting_info(
        [HaltItem(doi="10.1/a", detail="needs SI table S3", title="Paper A")],
        note="dataset lives only in the SI.",
    )
    assert halt.reason == HaltReason.SUPPORTING_INFO_NEEDED
    assert halt.items[0].doi == "10.1/a"
    fb = halt.feedback()
    assert "Supporting Information" in fb
    assert "10.1/a" in fb and "table S3" in fb
    assert "dataset lives only in the SI." in fb
