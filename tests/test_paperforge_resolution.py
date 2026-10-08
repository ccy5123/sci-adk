"""Which ``paperforge`` sci-adk runs, and what the provenance says about it.

A different program named ``paperforge`` earlier on PATH (e.g. inside a conda env) used
to be picked up silently by ``shutil.which``. Resolution order is now:

  a. explicit -- ``$SCI_ADK_PAPERFORGE``, else ``[literature] paperforge`` in the sci-adk
     config file. An explicit value that is missing / not executable / relative is an
     error; it never falls through to the other rules.
  b. the ``paperforge`` beside the running sci-adk (the ``sys.argv[0]`` directory, then
     ``sysconfig.get_path("scripts")``).
  c. ``shutil.which("paperforge")``.

Provenance records the resolved absolute path, the rule that chose it, and the version
the tool itself reports. Every test builds fake executables in a tmp dir; nothing here
touches the network or the real config file.
"""

from __future__ import annotations

import os
import stat
import sys
import sysconfig
from pathlib import Path

import pytest

from sci_adk.search.paperforge_adapter import (
    PINNED_SHA,
    AcquisitionToolError,
    PaperforgeAdapter,
    PaperforgeNotInstalled,
    PaperforgePathError,
)

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX shebang executables")

_FAKE_TOOL = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "{version}"; exit 0; fi
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; fi
  shift
done
printf 'index,doi,status,source,license,filename,origin,error\\n1,10.1/a,success,arxiv,,A.pdf,,\\n' > "$out/manifest.csv"
exit 0
"""


def _exe(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _tool(directory: Path, version: str = "paperforge 9.9.9") -> Path:
    return _exe(directory / "paperforge", _FAKE_TOOL.format(version=version))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate every resolution input: no env var, an empty config root, the sci-adk
    script dirs and PATH pointing at empty tmp dirs. Tests then populate what they need."""
    monkeypatch.delenv("SCI_ADK_PAPERFORGE", raising=False)
    cfg_root = tmp_path / "cfg"
    cfg_root.mkdir()
    argv_dir = tmp_path / "argv-bin"
    scripts_dir = tmp_path / "scripts-bin"
    path_dir = tmp_path / "path-bin"
    for d in (argv_dir, scripts_dir, path_dir):
        d.mkdir()
    monkeypatch.setattr(sys, "argv", [str(argv_dir / "sci-adk"), "prior-work"])
    real_get_path = sysconfig.get_path

    def fake_get_path(name, *a, **kw):
        return str(scripts_dir) if name == "scripts" else real_get_path(name, *a, **kw)

    monkeypatch.setattr(sysconfig, "get_path", fake_get_path)
    monkeypatch.setenv("PATH", str(path_dir))
    return {"cfg_root": cfg_root, "argv_dir": argv_dir, "scripts_dir": scripts_dir,
            "path_dir": path_dir, "tmp": tmp_path, "mp": monkeypatch}


def _write_config(cfg_root: Path, value: str) -> None:
    p = cfg_root / "sci-adk" / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'[literature]\npaperforge = "{value}"\n', encoding="utf-8")


def _adapter(env) -> PaperforgeAdapter:
    return PaperforgeAdapter(config_root=env["cfg_root"])


# --------------------------------------------------------------------------- #
# a. explicit
# --------------------------------------------------------------------------- #

def test_env_var_wins_over_config_same_dir_and_path(env):
    chosen = _tool(env["tmp"] / "explicit")
    _write_config(env["cfg_root"], str(_tool(env["tmp"] / "from-config")))
    _tool(env["argv_dir"])
    _tool(env["scripts_dir"])
    _tool(env["path_dir"])
    env["mp"].setenv("SCI_ADK_PAPERFORGE", str(chosen))

    a = _adapter(env)
    assert a.paperforge_bin == str(chosen)
    assert a.resolved_by == "env:SCI_ADK_PAPERFORGE"


def test_config_key_wins_over_same_dir_and_path(env):
    chosen = _tool(env["tmp"] / "from-config")
    _write_config(env["cfg_root"], str(chosen))
    _tool(env["argv_dir"])
    _tool(env["path_dir"])

    a = _adapter(env)
    assert a.paperforge_bin == str(chosen)
    assert a.resolved_by == "config:[literature] paperforge"


def test_nonexistent_env_path_errors_without_falling_through(env):
    _tool(env["argv_dir"])
    _tool(env["path_dir"])
    missing = env["tmp"] / "nowhere" / "paperforge"
    env["mp"].setenv("SCI_ADK_PAPERFORGE", str(missing))

    with pytest.raises(PaperforgePathError) as exc:
        _adapter(env)
    msg = str(exc.value)
    assert str(missing) in msg and "SCI_ADK_PAPERFORGE" in msg
    # caught by every CLI verb's existing "acquisition failed, nothing recorded" path
    assert isinstance(exc.value, AcquisitionToolError)


def test_nonexistent_config_path_errors_without_falling_through(env):
    _tool(env["path_dir"])
    missing = env["tmp"] / "nowhere" / "paperforge"
    _write_config(env["cfg_root"], str(missing))

    with pytest.raises(PaperforgePathError) as exc:
        _adapter(env)
    assert str(missing) in str(exc.value)
    assert "[literature] paperforge" in str(exc.value)


def test_explicit_path_that_is_not_executable_errors(env):
    plain = env["tmp"] / "plain" / "paperforge"
    plain.parent.mkdir()
    plain.write_text("not a program", encoding="utf-8")
    env["mp"].setenv("SCI_ADK_PAPERFORGE", str(plain))

    with pytest.raises(PaperforgePathError, match="not executable"):
        _adapter(env)


def test_explicit_relative_path_errors(env):
    _tool(env["path_dir"])
    env["mp"].setenv("SCI_ADK_PAPERFORGE", "bin/paperforge")

    with pytest.raises(PaperforgePathError, match="absolute"):
        _adapter(env)


# --------------------------------------------------------------------------- #
# b. beside the running sci-adk
# --------------------------------------------------------------------------- #

def test_same_dir_as_sci_adk_wins_over_path(env):
    chosen = _tool(env["argv_dir"])
    _tool(env["path_dir"], version="unrelated 1.0")

    a = _adapter(env)
    assert a.paperforge_bin == str(chosen)
    assert a.resolved_by == "sci-adk-dir"


def test_interpreter_scripts_dir_wins_over_path(env):
    chosen = _tool(env["scripts_dir"])
    _tool(env["path_dir"], version="unrelated 1.0")

    a = _adapter(env)
    assert a.paperforge_bin == str(chosen)
    assert a.resolved_by == "sci-adk-dir"


def test_console_script_dir_preferred_over_interpreter_scripts_dir(env):
    """User installs put the console script in ~/.local/bin while
    ``sysconfig.get_path('scripts')`` names the system dir: the dir of the sci-adk that
    is actually running is checked first."""
    chosen = _tool(env["argv_dir"])
    _tool(env["scripts_dir"])

    assert _adapter(env).paperforge_bin == str(chosen)


# --------------------------------------------------------------------------- #
# c. PATH
# --------------------------------------------------------------------------- #

def test_falls_back_to_path(env):
    chosen = _tool(env["path_dir"])

    a = _adapter(env)
    assert a.paperforge_bin == str(chosen)
    assert a.resolved_by == "PATH"


def test_nothing_found_raises_not_installed_on_use(env, tmp_path):
    a = _adapter(env)
    assert a.paperforge_bin is None
    with pytest.raises(PaperforgeNotInstalled):
        a.build_command(["10.1/a"], tmp_path / "out")


def test_constructor_argument_is_used_verbatim(env):
    a = PaperforgeAdapter(paperforge_bin="/opt/x/paperforge", config_root=env["cfg_root"])
    assert a.paperforge_bin == "/opt/x/paperforge"
    assert a.resolved_by == "argument"


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def test_provenance_records_resolved_path_rule_and_reported_version(env):
    chosen = _tool(env["tmp"] / "explicit", version="paperforge 9.9.9")
    env["mp"].setenv("SCI_ADK_PAPERFORGE", str(chosen))

    result = _adapter(env).fetch(["10.1/a"], env["tmp"] / "out")

    prov = result.provenance
    assert [r.doi for r in result.succeeded] == ["10.1/a"]
    assert prov["tool_path"] == str(chosen)
    assert prov["tool_resolved_by"] == "env:SCI_ADK_PAPERFORGE"
    assert prov["tool_version"] == "paperforge 9.9.9"
    assert prov["command"][0] == str(chosen)
    # the declared pin stays, labelled as what pyproject declares -- not as what ran
    assert prov["pinned_sha"] == PINNED_SHA
    # the sci-adk interpreter's own paperforge package says nothing about what ran
    assert "installed_version" not in prov


def test_version_unknown_when_tool_reports_none(env):
    silent = _exe(env["path_dir"] / "paperforge", "#!/bin/sh\nexit 0\n")

    result = _adapter(env).fetch(["10.1/a"], env["tmp"] / "out")
    assert result.provenance["tool_path"] == str(silent)
    assert result.provenance["tool_version"] == "unknown"


def test_version_falls_back_to_the_tools_own_python_package(env):
    """A paperforge without ``--version`` (the real one today) is asked through the
    interpreter on its shebang line for its installed distribution's version."""
    fake_python = _exe(env["tmp"] / "py" / "python3",
                       '#!/bin/sh\nif [ "$1" = "-c" ]; then echo "0.1.0 git abc123"; fi\n')
    tool = _exe(env["path_dir"] / "paperforge", f"#!{fake_python}\n")

    result = _adapter(env).fetch(["10.1/a"], env["tmp"] / "out")
    assert result.provenance["tool_path"] == str(tool)
    assert result.provenance["tool_version"] == "0.1.0 git abc123"


def test_version_fallback_never_runs_a_non_python_shebang(env):
    """The fallback probe passes Python source to the shebang interpreter; for a
    non-Python interpreter it must not run at all."""
    marker = env["tmp"] / "ran"
    fake_sh = _exe(env["tmp"] / "sh" / "notpython",
                   f'#!/bin/sh\nif [ "$1" = "-c" ]; then touch "{marker}"; fi\n')
    _exe(env["path_dir"] / "paperforge", f"#!{fake_sh}\n")

    result = _adapter(env).fetch(["10.1/a"], env["tmp"] / "out")
    assert result.provenance["tool_version"] == "unknown"
    assert not marker.exists()


# --------------------------------------------------------------------------- #
# the LITERATURE Evidence item names what ran
# --------------------------------------------------------------------------- #

def test_literature_evidence_environment_names_the_tool_that_ran(env):
    """Provenance.environment used to read paperforge@<pinned sha> whatever
    executable ran. It now carries the resolved path, the rule, and the reported
    version; the pin appears only as the declared pin."""
    import types

    from sci_adk.loop.literature_acquirer import LiteratureAcquirer

    chosen = _tool(env["tmp"] / "explicit", version="paperforge 9.9.9")
    env["mp"].setenv("SCI_ADK_PAPERFORGE", str(chosen))
    spec = types.SimpleNamespace(id="sp-env")
    acquirer = LiteratureAcquirer(spec, workspace_dir=env["tmp"] / "ws",
                                  adapter=_adapter(env))

    environment = acquirer.acquire(["10.1/a"]).evidence.provenance.environment
    assert f"path={chosen}" in environment
    assert "resolved_by=env:SCI_ADK_PAPERFORGE" in environment
    assert "version=paperforge 9.9.9" in environment
    assert f"declared_pin={PINNED_SHA[:7]}" in environment
    assert "paperforge@" not in environment
