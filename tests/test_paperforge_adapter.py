"""
Network-free unit tests for the paperforge acquisition adapter.

These exercise the pure parts (command construction, manifest parsing) and the
subprocess path with a mocked ``subprocess.run`` -- no network, no paperforge
install required. A real-download smoke test is run manually (see the tool
integration notes), not here, to keep the suite hermetic.
"""

import csv
import subprocess
from pathlib import Path

import pytest

from sci_adk.search.paperforge_adapter import (
    EXIT_NO_DOIS,
    EXIT_SOME_FAILED,
    PINNED_SHA,
    AcquisitionRecord,
    AcquisitionResult,
    PaperforgeAdapter,
    PaperforgeNotInstalled,
)

FAKE_BIN = "/usr/bin/paperforge"


def _adapter(**kwargs) -> PaperforgeAdapter:
    kwargs.setdefault("paperforge_bin", FAKE_BIN)
    return PaperforgeAdapter(**kwargs)


def _write_manifest(path: Path, rows: list[dict]) -> None:
    fields = ["index", "doi", "status", "source", "license",
              "filename", "origin", "error"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


class TestBuildCommand:
    def test_basic_invocation(self, tmp_path):
        cmd = _adapter().build_command(["10.1/x", "10.2/y"], tmp_path)
        assert cmd[0] == FAKE_BIN
        assert "10.1/x" in cmd and "10.2/y" in cmd
        assert "-o" in cmd
        assert str(tmp_path) in cmd

    def test_all_options_passed_through(self, tmp_path):
        cmd = _adapter(email="me@example.org").build_command(
            ["10.1/x"],
            tmp_path,
            source_order=["arxiv", "unpaywall"],
            licenses=["cc-by", "cc0"],
            require_known_license=True,
            no_metadata=True,
            overwrite=True,
            verbose=True,
        )
        assert cmd[cmd.index("--email") + 1] == "me@example.org"
        assert cmd[cmd.index("--source-order") + 1] == "arxiv,unpaywall"
        assert cmd[cmd.index("--licenses") + 1] == "cc-by,cc0"
        assert "--require-known-license" in cmd
        assert "--no-metadata" in cmd
        assert "--overwrite" in cmd
        assert "--verbose" in cmd

    def test_no_email_omits_flag(self, tmp_path):
        cmd = _adapter(email=None).build_command(["10.1/x"], tmp_path)
        assert "--email" not in cmd

    def test_missing_binary_raises(self, tmp_path):
        # Force the "not installed" state: __init__ falls back to
        # shutil.which("paperforge"), which finds it when the tool is installed
        # in the test environment, so set the attribute directly to test the guard.
        adapter = PaperforgeAdapter(paperforge_bin=FAKE_BIN)
        adapter.paperforge_bin = None
        with pytest.raises(PaperforgeNotInstalled):
            adapter.build_command(["10.1/x"], tmp_path)


class TestParseManifest:
    def test_absent_manifest_returns_empty(self, tmp_path):
        assert PaperforgeAdapter.parse_manifest(tmp_path / "nope.csv") == []

    def test_parses_success_and_failure_rows(self, tmp_path):
        manifest = tmp_path / "manifest.csv"
        _write_manifest(manifest, [
            {"doi": "10.1/a", "status": "success", "source": "arxiv",
             "license": "cc-by", "filename": "A.pdf"},
            {"doi": "10.2/b", "status": "failed", "error": "no OA PDF"},
        ])
        records = PaperforgeAdapter.parse_manifest(manifest)
        assert records[0] == AcquisitionRecord(
            doi="10.1/a", status="success", source="arxiv",
            license="cc-by", filename="A.pdf",
        )
        assert records[0].ok is True
        assert records[1].ok is False
        assert records[1].error == "no OA PDF"


class TestFetch:
    def test_parses_records_and_captures_provenance(self, tmp_path, monkeypatch):
        out = tmp_path / "out"

        def fake_run(cmd, **kwargs):
            # paperforge writes the manifest as a side effect; simulate it.
            _write_manifest(out / "manifest.csv", [
                {"doi": "10.1/a", "status": "success",
                 "source": "arxiv", "filename": "A.pdf"},
                {"doi": "10.2/b", "status": "failed", "error": "no OA PDF"},
            ])
            return subprocess.CompletedProcess(
                cmd, EXIT_SOME_FAILED,
                stdout="1 downloaded, 1 failed", stderr="",
            )

        monkeypatch.setattr(
            "sci_adk.search.paperforge_adapter.subprocess.run", fake_run)

        result = _adapter(email="me@example.org").fetch(["10.1/a", "10.2/b"], out)

        assert isinstance(result, AcquisitionResult)
        assert result.returncode == EXIT_SOME_FAILED
        assert [r.doi for r in result.succeeded] == ["10.1/a"]
        assert [r.doi for r in result.failed] == ["10.2/b"]
        assert result.manifest_path == out / "manifest.csv"
        assert result.stdout == "1 downloaded, 1 failed"
        # provenance ties the run to an exact tool version + command.
        assert result.provenance["tool"] == "paperforge"
        assert result.provenance["pinned_sha"] == PINNED_SHA
        assert result.provenance["returncode"] == EXIT_SOME_FAILED
        assert result.provenance["command"][0] == FAKE_BIN
        assert "timestamp" in result.provenance

    def test_creates_output_dir_and_handles_no_manifest(self, tmp_path, monkeypatch):
        out = tmp_path / "nested" / "out"

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, EXIT_NO_DOIS, stdout="", stderr="No DOIs found")

        monkeypatch.setattr(
            "sci_adk.search.paperforge_adapter.subprocess.run", fake_run)

        result = _adapter().fetch(["not-a-doi"], out)
        assert out.exists()           # output dir created even on early exit
        assert result.records == []   # no manifest was written
        assert result.returncode == EXIT_NO_DOIS
