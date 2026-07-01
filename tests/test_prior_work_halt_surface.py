"""
CLI-surface test for the acquisition halt (condition 1: unacquired papers).

The kernel already HALTS when a searched DOI has no downloadable Open-Access PDF
(``AcquisitionHalt.for_unacquired`` in loop/literature_acquirer.py) and the CLI
already surfaces it -- but the halt is *advisory*: the decision is still recorded
and the process exits 0. The orchestrator is therefore expected to watch STDERR,
not the exit code. These tests pin that contract so it cannot silently regress:

  - ``sci-adk prior-work --searched <doi>`` and ``sci-adk novelty --searched <doi>``
    both print ``halt (human input needed):`` + the missed DOI to STDERR, and
  - both return exit code 0 (the decision is recorded; the halt is soft).

Network-free: the paperforge adapter is stubbed so the requested DOI comes back
as a ``failed`` record (no OA PDF). ``--allow-no-email`` skips the *separate*
contact-email ConfigHalt (a different, hard, exit-2 halt) so this test exercises
only the OA-PDF-miss path.
"""

from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult

MISS_DOI = "10.9999/no-open-access"
PIN = "60fefedacb7349c755c29b2c2f26873464158c12"


class _NoOAAdapter:
    """A stub paperforge adapter: every requested DOI fails with 'no OA PDF'.

    Matches the real ``PaperforgeAdapter(email=...)`` constructor signature so it
    drops in where the acquirer default-constructs its adapter.
    """

    def __init__(self, *args, **kwargs):
        pass

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        records = [
            AcquisitionRecord(doi=doi, status="failed", error="no OA PDF")
            for doi in dois
        ]
        return AcquisitionResult(
            returncode=1,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=records,
            provenance={
                "tool": "paperforge",
                "pinned_sha": PIN,
                "installed_version": "0.1.0",
                "returncode": 1,
            },
        )


@pytest.fixture
def run_dir(tmp_path):
    """A real frozen run dir (t1-demo Spec) at ``tmp_path/runs/t1-godel``."""
    assert main(["init-spec", "--t1-demo", "-o", str(tmp_path)]) == 0
    return tmp_path / "runs" / "t1-godel"


@pytest.fixture(autouse=True)
def _stub_paperforge(monkeypatch):
    # The acquirer default-constructs ``PaperforgeAdapter(email=...)`` from the
    # symbol imported into loop.literature_acquirer -- patch it there.
    monkeypatch.setattr(
        "sci_adk.loop.literature_acquirer.PaperforgeAdapter", _NoOAAdapter
    )


def test_prior_work_searched_surfaces_halt_on_stderr(run_dir, capsys):
    rc = main(["prior-work", str(run_dir), "--searched", MISS_DOI,
               "--allow-no-email"])
    captured = capsys.readouterr()

    # the halt is SOFT: the decision is still recorded, exit code is 0
    assert rc == 0
    # ... and the miss reaches the human via STDERR (the orchestrator's cue)
    assert "halt (human input needed):" in captured.err
    assert MISS_DOI in captured.err
    assert "no OA PDF" in captured.err


def test_novelty_searched_surfaces_halt_on_stderr(run_dir, capsys):
    rc = main(["novelty", str(run_dir), "--hypothesis", "h-godel",
               "--kind", "result", "--searched", MISS_DOI,
               "--outcome", "found-nothing", "--allow-no-email"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "halt (human input needed):" in captured.err
    assert MISS_DOI in captured.err
    assert "no OA PDF" in captured.err
