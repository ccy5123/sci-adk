"""
``sci-adk novelty`` + ``sci-adk contested`` CLI surfaces (RED-first).

design/literature-acquisition.md §"Discovery trigger model": the in-session agent
records the novelty / contested decisions into the single Evidence log, mirroring the
existing ``prior-work`` verb:

    sci-adk novelty <run> --hypothesis <id> --searched <dois...> [--allow-no-email]
    sci-adk novelty <run> --hypothesis <id> --skip --reason "..."
    sci-adk contested <run> --hypothesis <id> [--searched <dois...> | --note "..."]

``ValidityHalt`` / ``ConfigHalt`` -> exit 2. The ``run`` / ``resolve`` / ``verify`` /
``prior-work`` verbs keep working unchanged. These tests assert wiring + exit codes
(the --skip / --note paths need no network; the searched paths inject a fake adapter).
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.cli import main
from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import HypothesisMode
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult

# A proposal whose parsed Spec carries a hypothesis the agent can name. The parser
# assigns deterministic hypothesis ids; the tests below read the seeded spec.json to
# discover the real id rather than guessing.
_PROPOSAL = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"


def _seed(workspace: Path, spec_id: str) -> tuple[Path, str]:
    """Compile a run; return (run_dir, first hypothesis id)."""
    result = ResearchCompiler(workspace_dir=workspace).compile(_PROPOSAL, spec_id=spec_id)
    return workspace / "runs" / spec_id, result.spec.hypotheses[0].id


def _load_evidence(run_dir: Path) -> list[EvidenceItem]:
    ev_dir = run_dir / "evidence"
    if not ev_dir.is_dir():
        return []
    return [
        EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(ev_dir.glob("*.json"))
    ]


class _FakeAdapter:
    def fetch(self, dois, out_dir, **opts):
        out_dir = Path(out_dir)
        return AcquisitionResult(
            returncode=0, output_dir=out_dir, manifest_path=out_dir / "manifest.csv",
            records=[AcquisitionRecord(doi=d, status="success", source="arxiv",
                                       license="cc-by", filename=f"{i}.pdf")
                     for i, d in enumerate(dois)],
            provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
        )


# --------------------------------------------------------------------------- #
# novelty --skip
# --------------------------------------------------------------------------- #

def test_novelty_skip_records_decision_exit_zero(tmp_path, capsys):
    run_dir, hyp_id = _seed(tmp_path, "cli-nov-skip")
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id,
               "--skip", "--reason", "priority framing dropped in review"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "novelty_decision" in out.lower() or "skip" in out.lower()
    items = _load_evidence(run_dir)
    assert any(i.kind is EvidenceKind.NOVELTY_DECISION for i in items)


def test_novelty_skip_without_reason_errors(tmp_path, capsys):
    run_dir, hyp_id = _seed(tmp_path, "cli-nov-noreason")
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id, "--skip"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "reason" in err.lower()


def test_novelty_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["novelty", str(tmp_path / "runs" / "nope"),
               "--hypothesis", "hyp-1", "--skip", "--reason", "r"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err.lower() or "no spec" in err.lower()


# --------------------------------------------------------------------------- #
# novelty --searched (email policy + happy path)
# --------------------------------------------------------------------------- #

def test_novelty_searched_no_email_exits_two_friendly(tmp_path, monkeypatch, capsys):
    """No email -> ConfigHalt -> exit 2 + friendly stderr (mirrors prior-work)."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)

    run_dir, hyp_id = _seed(tmp_path, "cli-nov-noemail")
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id,
               "--searched", "10.1/x", "--outcome", "found-nothing"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err
    assert "--allow-no-email" in err
    assert "Traceback (most recent call last)" not in err


def test_novelty_searched_requires_outcome(tmp_path, capsys):
    """--searched without --outcome is rejected (they are required together)."""
    run_dir, hyp_id = _seed(tmp_path, "cli-nov-no-outcome")
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id, "--searched", "10.1/x"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "outcome" in err.lower()


def _swap_acquirer(monkeypatch):
    import sci_adk.loop.literature_triggers as lt_mod
    spy = _FakeAdapter()
    real_acquirer = lt_mod.LiteratureAcquirer

    class _FakeAcquirer(real_acquirer):
        def __init__(self, spec, workspace_dir=None, adapter=None, email=None):
            super().__init__(spec, workspace_dir, adapter=spy, email=email)

    monkeypatch.setattr(lt_mod, "LiteratureAcquirer", _FakeAcquirer)


def _novelty_outcomes(run_dir: Path) -> list[str]:
    return [
        i.literature_decision.outcome
        for i in _load_evidence(run_dir)
        if i.kind is EvidenceKind.NOVELTY_DECISION and i.literature_decision is not None
    ]


def test_novelty_searched_found_nothing_proceeds(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)
    _swap_acquirer(monkeypatch)

    run_dir, hyp_id = _seed(tmp_path, "cli-nov-found-nothing")
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id,
               "--searched", "10.1/x", "--outcome", "found-nothing", "--allow-no-email"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "found_nothing" in out.lower() or "found-nothing" in out.lower() \
        or "searched" in out.lower()
    assert "found_nothing" in _novelty_outcomes(run_dir)


def test_novelty_searched_found_prior_art_proceeds(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)
    _swap_acquirer(monkeypatch)

    run_dir, hyp_id = _seed(tmp_path, "cli-nov-found-prior-art")
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id,
               "--searched", "10.1/x", "--outcome", "found-prior-art",
               "--allow-no-email"])
    assert rc == 0
    assert "found_something" in _novelty_outcomes(run_dir)


# --------------------------------------------------------------------------- #
# contested --note / --searched
# --------------------------------------------------------------------------- #

def _seed_with_contested_claim(tmp_path, spec_id) -> tuple[Path, str]:
    run_dir, hyp_id = _seed(tmp_path, spec_id)
    claims_dir = run_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim = Claim(
        id=f"claim-{hyp_id}", spec_id=spec_id, answers=hyp_id, statement="c",
        status=ClaimStatus.CONTESTED,
        confidence=Confidence(type=ConfidenceType.GRADED, level="moderate", basis="mixed"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (claims_dir / f"claim-{hyp_id}.json").write_text(
        json.dumps(claim.model_dump(mode="json"), indent=2), encoding="utf-8")
    return run_dir, hyp_id


def test_contested_note_records_and_exits_zero(tmp_path, capsys):
    run_dir, hyp_id = _seed_with_contested_claim(tmp_path, "cli-con-note")
    rc = main(["contested", str(run_dir), "--hypothesis", hyp_id,
               "--note", "conflicting prior work surfaced after the result"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "contested_record" in out.lower() or "recorded" in out.lower()
    items = _load_evidence(run_dir)
    assert any(i.kind is EvidenceKind.CONTESTED_RECORD for i in items)


def test_contested_missing_run_dir_errors(tmp_path, capsys):
    rc = main(["contested", str(tmp_path / "runs" / "nope"),
               "--hypothesis", "hyp-1", "--note", "n"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err.lower() or "no spec" in err.lower()


def test_contested_searched_allow_no_email_proceeds(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)

    import sci_adk.loop.literature_triggers as lt_mod
    spy = _FakeAdapter()
    real_acquirer = lt_mod.LiteratureAcquirer

    class _FakeAcquirer(real_acquirer):
        def __init__(self, spec, workspace_dir=None, adapter=None, email=None):
            super().__init__(spec, workspace_dir, adapter=spy, email=email)

    monkeypatch.setattr(lt_mod, "LiteratureAcquirer", _FakeAcquirer)

    run_dir, hyp_id = _seed_with_contested_claim(tmp_path, "cli-con-searched")
    rc = main(["contested", str(run_dir), "--hypothesis", hyp_id,
               "--searched", "10.1/conflict", "--allow-no-email"])
    out = capsys.readouterr().out
    assert rc == 0
    items = _load_evidence(run_dir)
    assert any(i.kind is EvidenceKind.CONTESTED_RECORD for i in items)
