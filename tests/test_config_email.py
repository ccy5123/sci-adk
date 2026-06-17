"""
E4 -- contact-email config halt (design/evidence-validity.md Guard, §E4).

Resolving the Unpaywall/OpenAlex contact email from (arg -> a small sci-adk config
file -> $UNPAYWALL_EMAIL); if ALL are empty the adapter HALTS with a clear message
naming how to set/persist it, instead of silently running degraded (which is how the
rice run bypassed the literature gate).

The config read is a tiny TOML file at ~/.config/sci-adk/config.toml under
``[contact] email = "..."``; the path root is overridable for tests so no real
home directory is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sci_adk.config import ConfigHalt, resolve_contact_email
from sci_adk.search.paperforge_adapter import PaperforgeAdapter


def _write_config(config_root: Path, email: str) -> None:
    cfg_dir = config_root / "sci-adk"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(
        f'[contact]\nemail = "{email}"\n', encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Resolution order: arg > config file > env.
# ---------------------------------------------------------------------------

def test_explicit_arg_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("UNPAYWALL_EMAIL", "env@x.org")
    _write_config(tmp_path, "config@x.org")
    got = resolve_contact_email("arg@x.org", config_root=tmp_path)
    assert got == "arg@x.org"


def test_config_file_used_when_no_arg(tmp_path, monkeypatch):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    _write_config(tmp_path, "config@x.org")
    got = resolve_contact_email(None, config_root=tmp_path)
    assert got == "config@x.org"


def test_env_used_when_no_arg_and_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("UNPAYWALL_EMAIL", "env@x.org")
    got = resolve_contact_email(None, config_root=tmp_path)  # empty config dir
    assert got == "env@x.org"


def test_all_empty_raises_config_halt(tmp_path, monkeypatch):
    """No arg, no config file, no env -> ConfigHalt with how-to-set guidance."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    with pytest.raises(ConfigHalt) as exc:
        resolve_contact_email(None, config_root=tmp_path)
    msg = str(exc.value)
    # Names all three resolution paths so the user knows how to fix it.
    assert "config.toml" in msg
    assert "UNPAYWALL_EMAIL" in msg


def test_blank_values_are_treated_as_empty(tmp_path, monkeypatch):
    """A whitespace-only env value is not a real email -> still halts."""
    monkeypatch.setenv("UNPAYWALL_EMAIL", "   ")
    _write_config(tmp_path, "   ")
    with pytest.raises(ConfigHalt):
        resolve_contact_email("  ", config_root=tmp_path)


# ---------------------------------------------------------------------------
# PaperforgeAdapter integration: a require_email path that halts.
# ---------------------------------------------------------------------------

def test_adapter_resolve_email_halts_when_unset(tmp_path, monkeypatch):
    """The adapter can resolve+require the contact email; with nothing set it raises
    ConfigHalt rather than silently building a command without --email (degraded)."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    adapter = PaperforgeAdapter(paperforge_bin="/usr/bin/true", email=None)
    with pytest.raises(ConfigHalt):
        adapter.resolve_email(require=True, config_root=tmp_path)


def test_adapter_resolve_email_returns_when_set(tmp_path, monkeypatch):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    _write_config(tmp_path, "config@x.org")
    adapter = PaperforgeAdapter(paperforge_bin="/usr/bin/true", email=None)
    assert adapter.resolve_email(require=True, config_root=tmp_path) == "config@x.org"


def test_adapter_explicit_email_does_not_consult_config(tmp_path, monkeypatch):
    """An email passed to the adapter wins and never touches the config file/env."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    adapter = PaperforgeAdapter(paperforge_bin="/usr/bin/true", email="explicit@x.org")
    assert adapter.resolve_email(require=True, config_root=tmp_path) == "explicit@x.org"
