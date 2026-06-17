"""
E4 (change 2): the prior-work --searched path hard-requires a contact email BY
DEFAULT (design/evidence-validity.md E4).

The searched path uses the Unpaywall/OpenAlex polite pool; a missing contact email
means silently degraded OA resolution -- the exact silent-degradation the rice run
rode past. So by default a missing email HALTS (ConfigHalt) BEFORE any acquisition is
attempted; --allow-no-email is the explicit escape hatch to proceed degraded.

Covered:
  - library: record_prior_work_searched with no email -> ConfigHalt, NO acquisition
    attempted (the spy adapter's fetch is never called).
  - library: allow_no_email=True -> proceeds (degraded), no halt.
  - library: an injected/config/env email satisfies the requirement.
  - CLI: `prior-work --searched` with no email -> non-zero exit, friendly stderr
    naming the fix, no traceback, no acquisition attempted.
  - CLI: `prior-work --searched --allow-no-email` -> proceeds.
  - CLI: the --skip path is UNCHANGED (no email required).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.config import ConfigHalt
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.prior_work import record_prior_work_searched
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult

_PROPOSAL = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"


class _SpyAdapter:
    """A paperforge stand-in that records whether fetch() was ever called.

    If the email gate halts BEFORE acquisition, fetch must never run -- this spy makes
    'no acquisition attempted' an assertable fact, not an inference.
    """

    def __init__(self) -> None:
        self.fetch_calls = 0

    def fetch(self, dois, out_dir, **opts):
        self.fetch_calls += 1
        out_dir = Path(out_dir)
        return AcquisitionResult(
            returncode=0,
            output_dir=out_dir,
            manifest_path=out_dir / "manifest.csv",
            records=[AcquisitionRecord(doi=d, status="success", source="arxiv",
                                       license="cc-by", filename=f"{i}.pdf")
                     for i, d in enumerate(dois)],
            provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
        )


def _seed(workspace: Path, spec_id: str) -> Path:
    ResearchCompiler(workspace_dir=workspace).compile(_PROPOSAL, spec_id=spec_id)
    return workspace / "runs" / spec_id


def _no_email_env(monkeypatch, empty_config_root: Path) -> Path:
    """Make ALL email sources empty: no env var, and an empty config root."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    empty_config_root.mkdir(parents=True, exist_ok=True)  # exists but has no sci-adk/
    return empty_config_root


# ---------------------------------------------------------------------------
# library: record_prior_work_searched -- require-by-default.
# ---------------------------------------------------------------------------

def test_searched_no_email_halts_before_acquisition(tmp_path, monkeypatch):
    """No email anywhere -> ConfigHalt, and the spy adapter's fetch is NEVER called
    (the gate halts before any acquisition)."""
    cfg_root = _no_email_env(monkeypatch, tmp_path / "cfg")
    spy = _SpyAdapter()
    spec = _seed_spec(tmp_path, "pw-email-halt")

    with pytest.raises(ConfigHalt):
        record_prior_work_searched(
            spec, tmp_path, dois=["10.1/x"], adapter=spy, config_root=cfg_root)
    assert spy.fetch_calls == 0  # NO acquisition attempted


def test_searched_allow_no_email_proceeds_degraded(tmp_path, monkeypatch):
    """--allow-no-email (allow_no_email=True): proceeds with NO email -> acquisition
    runs (degraded), no halt."""
    cfg_root = _no_email_env(monkeypatch, tmp_path / "cfg")
    spy = _SpyAdapter()
    spec = _seed_spec(tmp_path, "pw-email-degraded")

    outcome = record_prior_work_searched(
        spec, tmp_path, dois=["10.1/x"], adapter=spy,
        allow_no_email=True, config_root=cfg_root)
    assert spy.fetch_calls == 1
    assert outcome.evidence.kind is EvidenceKind.LITERATURE


def test_searched_config_email_satisfies_requirement(tmp_path, monkeypatch):
    """A [contact] email in the sci-adk config file satisfies the requirement."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    cfg_root = tmp_path / "cfg"
    (cfg_root / "sci-adk").mkdir(parents=True, exist_ok=True)
    (cfg_root / "sci-adk" / "config.toml").write_text(
        '[contact]\nemail = "config@x.org"\n', encoding="utf-8")
    spy = _SpyAdapter()
    spec = _seed_spec(tmp_path, "pw-email-config")

    outcome = record_prior_work_searched(
        spec, tmp_path, dois=["10.1/x"], adapter=spy, config_root=cfg_root)
    assert spy.fetch_calls == 1
    assert outcome.evidence.kind is EvidenceKind.LITERATURE


def test_searched_explicit_email_satisfies_requirement(tmp_path, monkeypatch):
    """An explicit email arg satisfies the requirement without consulting config/env."""
    cfg_root = _no_email_env(monkeypatch, tmp_path / "cfg")
    spy = _SpyAdapter()
    spec = _seed_spec(tmp_path, "pw-email-arg")

    outcome = record_prior_work_searched(
        spec, tmp_path, dois=["10.1/x"], adapter=spy,
        email="explicit@x.org", config_root=cfg_root)
    assert spy.fetch_calls == 1
    assert outcome.evidence.kind is EvidenceKind.LITERATURE


# ---------------------------------------------------------------------------
# CLI: prior-work --searched require-by-default + escape hatch.
# ---------------------------------------------------------------------------

def test_cli_searched_no_email_exits_nonzero_friendly(tmp_path, monkeypatch, capsys):
    """`prior-work --searched` with no email -> non-zero exit + friendly stderr naming
    the fix (env var / config.toml / --allow-no-email), no raw traceback, and NO
    acquisition attempted (the acquirer is never even constructed)."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    # Point the config resolver at an empty XDG root so no real ~/.config is consulted.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)

    # Patch the acquirer WHERE prior_work uses it (bound at import) so we can prove it
    # is never constructed -- the email gate halts before acquisition.
    import sci_adk.loop.prior_work as pw_mod
    built = {"count": 0}
    real_acquirer = pw_mod.LiteratureAcquirer

    class _SpyingAcquirer(real_acquirer):
        def __init__(self, *a, **k):
            built["count"] += 1
            super().__init__(*a, **k)

    monkeypatch.setattr(pw_mod, "LiteratureAcquirer", _SpyingAcquirer)

    run_dir = _seed(tmp_path, "cli-pw-email-halt")
    rc = main(["prior-work", str(run_dir), "--searched", "10.1/x"])
    captured = capsys.readouterr()

    assert rc == 2
    assert "error:" in captured.err
    # Names how to fix it.
    assert "UNPAYWALL_EMAIL" in captured.err
    assert "config.toml" in captured.err
    assert "--allow-no-email" in captured.err
    # No raw traceback leaked.
    assert "Traceback (most recent call last)" not in captured.err
    # The halt fired before the acquirer was ever constructed (no acquisition).
    assert built["count"] == 0
    # And no LITERATURE/decision evidence was written.
    ev_dir = run_dir / "evidence"
    items = (
        [EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
         for p in ev_dir.glob("*.json")]
        if ev_dir.is_dir() else []
    )
    assert items == []


def test_cli_searched_allow_no_email_proceeds(tmp_path, monkeypatch, capsys):
    """`prior-work --searched --allow-no-email` proceeds (degraded), exit 0. The
    acquisition is faked so no network is touched."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)

    # Swap the acquirer (WHERE prior_work uses it) for one wired to the spy adapter so
    # no real paperforge runs.
    import sci_adk.loop.prior_work as pw_mod
    spy = _SpyAdapter()
    real_acquirer = pw_mod.LiteratureAcquirer

    class _FakeAcquirer(real_acquirer):
        def __init__(self, spec, workspace_dir=None, adapter=None, email=None):
            super().__init__(spec, workspace_dir, adapter=spy, email=email)

    monkeypatch.setattr(pw_mod, "LiteratureAcquirer", _FakeAcquirer)

    run_dir = _seed(tmp_path, "cli-pw-email-degraded")
    rc = main(["prior-work", str(run_dir), "--searched", "10.1/x",
               "--allow-no-email"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "searched" in out.lower()
    assert spy.fetch_calls == 1


def test_cli_skip_path_needs_no_email(tmp_path, monkeypatch, capsys):
    """The --skip path is UNCHANGED: no acquisition, no email required (exit 0)."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    run_dir = _seed(tmp_path, "cli-pw-skip-noemail")
    rc = main(["prior-work", str(run_dir), "--skip", "--reason", "no prior art applies"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "skip" in out.lower() or "prior_work_decision" in out.lower()


# ---------------------------------------------------------------------------
# helper: a minimal spec on disk (the CLI reads spec.json; the library takes a Spec).
# ---------------------------------------------------------------------------

def _seed_spec(workspace: Path, spec_id: str):
    """Compile a run and return the in-memory Spec (for the library-level tests)."""
    return ResearchCompiler(workspace_dir=workspace).compile(
        _PROPOSAL, spec_id=spec_id).spec
