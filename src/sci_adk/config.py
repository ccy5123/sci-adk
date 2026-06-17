"""
sci-adk minimal configuration (contact email for OA acquisition).

design/evidence-validity.md E4: the Unpaywall/OpenAlex polite-pool contact email is
resolved from (explicit arg -> a small sci-adk config file -> ``$UNPAYWALL_EMAIL``).
When ALL are empty the resolver HALTS with a clear, how-to-fix message instead of
silently running degraded -- silent degradation is how the rice run bypassed the
literature gate (it generated data rather than acquiring it).

The config file is a tiny TOML at ``~/.config/sci-adk/config.toml``::

    [contact]
    email = "you@example.org"

Read-only, stdlib-only (``tomllib``), no LLM. The config ROOT is overridable so tests
never touch a real home directory.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Optional

# The relative path of the config file under the XDG-style config root.
_CONFIG_RELPATH = Path("sci-adk") / "config.toml"

# The environment variable paperforge itself also consults (kept identical so the
# resolution order is honest about what the tool falls back to).
_ENV_VAR = "UNPAYWALL_EMAIL"


class ConfigHalt(Exception):
    """A HARD halt: a required piece of configuration is missing.

    Raised when the contact email cannot be resolved from any source. The CLI/adapter
    surfaces it as a friendly message naming exactly how to set/persist the value,
    rather than proceeding in a silently degraded mode (no ``--email`` -> weaker OA
    results, the failure mode the rice run rode past).
    """


def _config_root(config_root: Optional[Path]) -> Path:
    """Resolve the config root (default ``~/.config``; overridable for tests)."""
    if config_root is not None:
        return Path(config_root)
    # Honor XDG_CONFIG_HOME when set, else ~/.config (the conventional default).
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def _read_config_email(config_root: Optional[Path]) -> Optional[str]:
    """Return the ``[contact] email`` from the config file, or None if absent/blank."""
    path = _config_root(config_root) / _CONFIG_RELPATH
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        # A malformed config file is treated as "no email here" rather than crashing;
        # the resolver still halts (with guidance) if no other source supplies one.
        return None
    contact = data.get("contact")
    if not isinstance(contact, dict):
        return None
    email = contact.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


def resolve_contact_email(
    explicit: Optional[str] = None,
    *,
    config_root: Optional[Path] = None,
) -> str:
    """Resolve the contact email from (arg -> config file -> ``$UNPAYWALL_EMAIL``).

    Args:
        explicit: an email passed in directly (highest priority). Blank/whitespace is
            treated as absent.
        config_root: override the config root (default ``~/.config`` or
            ``$XDG_CONFIG_HOME``); used by tests so no real home directory is touched.

    Returns:
        The resolved, non-empty contact email.

    Raises:
        ConfigHalt: when no source supplies a non-empty email.
    """
    # @MX:NOTE: [AUTO] resolution order is arg > config file > $UNPAYWALL_EMAIL; a
    #   blank value at any layer is treated as absent and falls through. Empty
    #   everywhere -> ConfigHalt (no silent degraded run) per evidence-validity E4.
    if explicit and explicit.strip():
        return explicit.strip()

    from_config = _read_config_email(config_root)
    if from_config:
        return from_config

    from_env = os.environ.get(_ENV_VAR)
    if from_env and from_env.strip():
        return from_env.strip()

    cfg_path = _config_root(config_root) / _CONFIG_RELPATH
    raise ConfigHalt(
        "no contact email configured for Open-Access acquisition (required for the "
        "Unpaywall/OpenAlex polite pool). Set ONE of:\n"
        f"  - pass it explicitly (e.g. --email you@example.org), or\n"
        f"  - persist it in {cfg_path} under:\n"
        f'        [contact]\n        email = "you@example.org"\n'
        f"  - export {_ENV_VAR}=you@example.org\n"
        "Running without it would silently degrade OA resolution -- refused."
    )


__all__ = [
    "ConfigHalt",
    "resolve_contact_email",
]
