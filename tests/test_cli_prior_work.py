"""
``sci-adk prior-work <run-dir>`` CLI surface (RED-first).

design/literature-acquisition.md §"Discovery trigger model": the in-session agent
records the Spec-time prior-work *decision* into the single Evidence log -- either
``--searched <dois...>`` (drives the existing acquirer -> a LITERATURE item) or
``--skip --reason "..."`` (a recorded null -> a PRIOR_WORK_DECISION item). The
existing ``run`` / ``resolve`` verbs keep working unchanged.

These tests use the ``--skip`` path (no network) plus an injected fake adapter is
covered at the library level in test_prior_work_trigger.py; here we assert the CLI
wiring and exit codes.
"""

from __future__ import annotations

from pathlib import Path

from sci_adk.cli import main
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.loop.compiler import ResearchCompiler

_PROPOSAL = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"


def _seed(workspace: Path, spec_id: str) -> Path:
    ResearchCompiler(workspace_dir=workspace).compile(_PROPOSAL, spec_id=spec_id)
    return workspace / "runs" / spec_id


def _load_evidence(run_dir: Path) -> list[EvidenceItem]:
    ev_dir = run_dir / "evidence"
    if not ev_dir.is_dir():
        return []
    import json

    return [
        EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(ev_dir.glob("*.json"))
    ]


def test_prior_work_skip_records_decision_and_exits_zero(tmp_path, capsys):
    run_dir = _seed(tmp_path, "cli-pw-skip")
    rc = main(["prior-work", str(run_dir), "--skip",
               "--reason", "pure-math reframing; no empirical prior art"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "prior_work_decision" in out.lower() or "skip" in out.lower()

    items = _load_evidence(run_dir)
    assert any(i.kind is EvidenceKind.PRIOR_WORK_DECISION for i in items)


def test_prior_work_skip_without_reason_errors(tmp_path, capsys):
    run_dir = _seed(tmp_path, "cli-pw-noreason")
    rc = main(["prior-work", str(run_dir), "--skip"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "reason" in err.lower()


def test_prior_work_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["prior-work", str(tmp_path / "runs" / "nope"),
               "--skip", "--reason", "r"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err.lower() or "no spec" in err.lower()
