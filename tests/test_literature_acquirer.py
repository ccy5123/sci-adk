"""
Network-free unit tests for the literature acquisition loop stage.

A fake adapter stands in for paperforge (no subprocess, no network); the Spec is
a minimal stub since the stage only reads ``spec.id``. These verify the stage's
real job: turning an acquisition result into a LITERATURE EvidenceItem under
runs/<spec.id>/ and persisting it.
"""

import json
import types
from pathlib import Path

from sci_adk.core.evidence import BearingDirection, EvidenceItem, EvidenceKind
from sci_adk.loop.literature_acquirer import LiteratureAcquirer, acquire_literature
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

    ev = acquirer.acquire(["10.1/a", "10.2/b"])

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
    ev = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                            adapter=adapter).acquire(["10.1/a"])
    assert ev.bears_on == []


def test_target_id_attaches_neutral_bearing(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    ev = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                            adapter=adapter).acquire(["10.1/a"], target_id="hyp-1")
    assert len(ev.bears_on) == 1
    assert ev.bears_on[0].target_id == "hyp-1"
    # acquisition asserts no direction of its own -> NEUTRAL context link
    assert ev.bears_on[0].direction == BearingDirection.NEUTRAL


def test_options_passthrough_via_convenience(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    acquire_literature(
        _spec("s2"), ["10.1/a"], workspace_dir=tmp_path, adapter=adapter,
        source_order=["arxiv"], no_metadata=True,
    )
    _, _, options = adapter.calls[0]
    assert options["source_order"] == ["arxiv"]
    assert options["no_metadata"] is True
