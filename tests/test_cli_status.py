"""
``sci-adk status <run> [--json]`` CLI surface (RED-first).

design/research-session-enforcement.md §6 D1: a read-only verb printing a terse
session-state summary. Exit 0 ALWAYS (read-only report; it never fails the session --
that is the Stop gate's job). A nonexistent run dir -> a graceful "nothing recorded"
report on stdout, exit 0 (it must NOT raise). ``--json`` emits the report model dump.

Mirrors tests/test_cli_literature_triggers.py (uses the compiler seeder).
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.cli import main
from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
)
from sci_adk.core.spec import HypothesisMode
from sci_adk.loop.compiler import ResearchCompiler

_PROPOSAL = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"


def _seed(workspace: Path, spec_id: str) -> tuple[Path, str]:
    result = ResearchCompiler(workspace_dir=workspace).compile(_PROPOSAL,
                                                               spec_id=spec_id)
    return workspace / "runs" / spec_id, result.spec.hypotheses[0].id


def test_status_prints_headline_exit_zero(tmp_path, capsys):
    run_dir, hyp_id = _seed(tmp_path, "cli-status-ok")
    rc = main(["status", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    # the headline is the first line of stdout
    first = out.splitlines()[0]
    assert first.startswith("sci-adk status")


def test_status_missing_run_dir_exit_zero_nothing_recorded(tmp_path, capsys):
    rc = main(["status", str(tmp_path / "runs" / "nope")])
    out = capsys.readouterr().out
    assert rc == 0  # read-only report never fails
    assert "nothing recorded" in out.lower()


def test_status_json_emits_valid_keys(tmp_path, capsys):
    run_dir, hyp_id = _seed(tmp_path, "cli-status-json")
    # make the experiment claim PROPOSED so there is something to report
    claims_dir = run_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim = Claim(
        id=f"claim-{hyp_id}", spec_id="cli-status-json", answers=hyp_id,
        statement="c", status=ClaimStatus.PROPOSED,
        confidence=Confidence(type=ConfidenceType.GRADED, level="moderate",
                              basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (claims_dir / f"claim-{hyp_id}.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8")

    rc = main(["status", str(run_dir), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)  # must be valid JSON
    for key in (
        "spec_id", "run_name", "n_hypotheses", "claim_counts",
        "unresolved_claim_ids", "contested_claim_ids", "prior_work_open",
        "novelty_unresolved", "contested_pending",
        "checkpoints_awaiting_verdict", "headline",
    ):
        assert key in data, f"missing key {key} in --json output"
    assert f"claim-{hyp_id}" in data["unresolved_claim_ids"]
