"""
``sci-adk init-session <dir> [--dry-run]`` -- the Phase-3 installer (RED-first).

design/research-session-enforcement.md D3: install the Phase-2
``templates/research-workspace/`` kit into a target research workspace.

The two load-bearing invariants are NON-CLOBBERING and IDEMPOTENT:
  - never overwrite a file the user already has (identical -> no-op; differs -> skip);
  - re-running the installer changes nothing the second time (no duplicate hooks, no
    file churn, exit 0).

These two properties are tested explicitly below (they are the whole point of the verb).
The settings.json merge is the fiddly core: outputStyle is conflict-safe (an existing
non-"researcher" value is preserved, reported as a conflict, never overwritten); the
Stop / UserPromptSubmit hooks are matched by their ``command`` string and APPENDED to
the user's existing event arrays (never reordered, never duplicated).
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.init_session import InstallReport, install_session

# The four plain file assets the kit installs (relative to the target dir). CLAUDE.md
# and settings.json have their own special handling and are asserted separately.
_FILE_ASSETS = (
    ".claude/hooks/sci-adk/stop-verify-gate.sh",
    ".claude/hooks/sci-adk/reanchor.sh",
    ".claude/output-styles/researcher/researcher.md",
    ".claude/commands/research.md",
)
_HOOK_SHELL_SCRIPTS = (
    ".claude/hooks/sci-adk/stop-verify-gate.sh",
    ".claude/hooks/sci-adk/reanchor.sh",
)
_SETTINGS = ".claude/settings.json"


def _settings(target: Path) -> dict:
    return json.loads((target / _SETTINGS).read_text(encoding="utf-8"))


def _stop_commands(settings: dict) -> list[str]:
    """All Stop-hook command strings (flattened across matcher groups)."""
    cmds: list[str] = []
    for group in settings.get("hooks", {}).get("Stop", []):
        for h in group.get("hooks", []):
            cmds.append(h.get("command", ""))
    return cmds


def _ups_commands(settings: dict) -> list[str]:
    cmds: list[str] = []
    for group in settings.get("hooks", {}).get("UserPromptSubmit", []):
        for h in group.get("hooks", []):
            cmds.append(h.get("command", ""))
    return cmds


# --------------------------------------------------------------------------- #
# 1. fresh install into an empty target dir
# --------------------------------------------------------------------------- #


def test_install_into_empty_dir_lays_down_every_asset(tmp_path):
    report = install_session(tmp_path)

    assert isinstance(report, InstallReport)
    # all four plain assets + CLAUDE.md present
    for rel in _FILE_ASSETS:
        assert (tmp_path / rel).is_file(), f"missing asset: {rel}"
    assert (tmp_path / "CLAUDE.md").is_file()

    # settings.json created, persona + both hook events wired
    settings = _settings(tmp_path)
    assert settings["outputStyle"] == "researcher"
    stop_cmds = _stop_commands(settings)
    ups_cmds = _ups_commands(settings)
    assert any("stop-verify-gate.sh" in c for c in stop_cmds)
    assert any("reanchor.sh" in c for c in ups_cmds)

    # the report names what it installed (asset basenames appear somewhere)
    blob = "\n".join(report.installed + report.settings_changes)
    assert "settings.json" in "\n".join(report.settings_changes).lower() \
        or settings["outputStyle"] == "researcher"
    assert any("stop-verify-gate.sh" in a for a in report.installed)


def test_installed_hook_scripts_are_executable(tmp_path):
    install_session(tmp_path)
    for rel in _HOOK_SHELL_SCRIPTS:
        mode = (tmp_path / rel).stat().st_mode
        assert mode & stat.S_IXUSR, f"hook not executable (no user-x bit): {rel}"
        # owner/group/other execute (0o111) -- matches a 0o755 install
        assert mode & 0o111, f"hook not executable at all: {rel}"


# --------------------------------------------------------------------------- #
# 2. idempotency [HARD] -- the second run is a clean no-op
# --------------------------------------------------------------------------- #


def test_install_is_idempotent_no_churn_no_duplicate_hooks(tmp_path):
    install_session(tmp_path)

    # snapshot bytes + mtimes after the first install
    tracked = list(_FILE_ASSETS) + ["CLAUDE.md", _SETTINGS]
    before = {
        rel: ((tmp_path / rel).read_bytes(), (tmp_path / rel).stat().st_mtime_ns)
        for rel in tracked
    }

    report2 = install_session(tmp_path)

    # second run: everything reports already-current, nothing installed/skipped
    assert report2.installed == []
    assert report2.skipped == []
    assert report2.conflicts == []
    assert len(report2.already_current) >= len(_FILE_ASSETS)

    # bytes unchanged AND no rewrite (mtime stable -> no file churn)
    for rel in tracked:
        cur_bytes = (tmp_path / rel).read_bytes()
        cur_mtime = (tmp_path / rel).stat().st_mtime_ns
        assert cur_bytes == before[rel][0], f"bytes changed on re-run: {rel}"
        assert cur_mtime == before[rel][1], f"file rewritten on re-run (churn): {rel}"

    # exactly ONE Stop hook + ONE UserPromptSubmit hook -- no duplicates
    settings = _settings(tmp_path)
    stop = [c for c in _stop_commands(settings) if "stop-verify-gate.sh" in c]
    ups = [c for c in _ups_commands(settings) if "reanchor.sh" in c]
    assert len(stop) == 1, f"duplicate Stop hook: {stop}"
    assert len(ups) == 1, f"duplicate UserPromptSubmit hook: {ups}"


# --------------------------------------------------------------------------- #
# 3. settings.json merge -- outputStyle conflict is preserved, not overwritten
# --------------------------------------------------------------------------- #


def test_existing_outputstyle_is_preserved_and_reported_as_conflict(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps({"outputStyle": "MoAI", "model": "opusplan"}, indent=2),
        encoding="utf-8",
    )

    report = install_session(tmp_path)

    settings = _settings(tmp_path)
    # the user's outputStyle is NOT clobbered
    assert settings["outputStyle"] == "MoAI"
    # an unrelated key is preserved untouched
    assert settings["model"] == "opusplan"
    # a conflict is reported (warning, not failure)
    assert any("outputStyle" in c for c in report.conflicts)
    # but the hooks are STILL merged in despite the persona conflict
    assert any("stop-verify-gate.sh" in c for c in _stop_commands(settings))
    assert any("reanchor.sh" in c for c in _ups_commands(settings))


# --------------------------------------------------------------------------- #
# 4. settings.json merge -- the user's existing Stop hook survives; ours appends
# --------------------------------------------------------------------------- #


def test_existing_stop_hook_is_kept_and_ours_appended(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    user_settings = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "/usr/bin/my-own-stop.sh"}
                    ]
                }
            ]
        }
    }
    (claude / "settings.json").write_text(json.dumps(user_settings, indent=2),
                                          encoding="utf-8")

    install_session(tmp_path)

    settings = _settings(tmp_path)
    stop_cmds = _stop_commands(settings)
    # the user's hook is still present
    assert any("my-own-stop.sh" in c for c in stop_cmds)
    # AND ours was appended (both commands now present; array grew)
    assert any("stop-verify-gate.sh" in c for c in stop_cmds)
    assert len(stop_cmds) >= 2


# --------------------------------------------------------------------------- #
# 5. existing CLAUDE.md -- left intact; protocol written to a sidecar instead
# --------------------------------------------------------------------------- #


def test_existing_claude_md_left_intact_protocol_written_to_sidecar(tmp_path):
    original = "# My own project rules\nkeep me\n"
    (tmp_path / "CLAUDE.md").write_text(original, encoding="utf-8")

    report = install_session(tmp_path)

    # CLAUDE.md is byte-for-byte unchanged
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == original
    # the research protocol is written to the sidecar instead
    sidecar = tmp_path / ".claude" / "sci-adk-research-protocol.md"
    assert sidecar.is_file()
    # the report tells the user what happened
    blob = "\n".join(report.skipped + report.installed + report.conflicts)
    assert "sci-adk-research-protocol.md" in blob


# --------------------------------------------------------------------------- #
# 6. --dry-run writes NOTHING
# --------------------------------------------------------------------------- #


def test_dry_run_writes_nothing_but_reports_planned_actions(tmp_path):
    report = install_session(tmp_path, dry_run=True)

    # the report lists planned actions (it installed nothing yet, but planned to)
    assert report.installed, "dry-run should still report what it WOULD install"

    # ...and the target dir is untouched: no .claude/, no CLAUDE.md
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    # truly empty
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# 7. a non-clobbering plain asset that already exists but DIFFERS -> skipped
# --------------------------------------------------------------------------- #


def test_existing_differing_asset_is_skipped_not_overwritten(tmp_path):
    rel = ".claude/commands/research.md"
    p = tmp_path / rel
    p.parent.mkdir(parents=True)
    user_content = "# my own research command, do not touch\n"
    p.write_text(user_content, encoding="utf-8")

    report = install_session(tmp_path)

    # the user's file is untouched
    assert p.read_text(encoding="utf-8") == user_content
    # and it was reported as skipped
    assert any("research.md" in s for s in report.skipped)


# --------------------------------------------------------------------------- #
# 8. target dir does not exist -> a clear error, no traceback
# --------------------------------------------------------------------------- #


def test_missing_target_dir_raises_clear_error(tmp_path):
    # LOW: tightened to the ACTUAL single type raised so the test is diagnostic.
    missing = tmp_path / "does-not-exist"
    with pytest.raises(NotADirectoryError):
        install_session(missing)


def test_target_is_a_file_not_a_dir_raises(tmp_path):
    # LOW: tightened to the ACTUAL single type raised so the test is diagnostic.
    f = tmp_path / "a-file"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        install_session(f)


def test_empty_target_string_is_rejected_not_coerced_to_cwd(tmp_path):
    # Path("") resolves to cwd -- which, in the build repo, would clobber-check the
    # build workspace (the two-environment hazard). Reject it explicitly.
    with pytest.raises((NotADirectoryError, ValueError)):
        install_session(Path(""))


# --------------------------------------------------------------------------- #
# 8b. HIGH (the incident class): refuse to install into the sci-adk build repo
#     / a MoAI build harness. The empty/`.` guard does NOT stop an absolute path
#     (or a relative path resolving) into the build repo -- a marker-based guard
#     does. These assert a RAISE, so nothing is written.
# --------------------------------------------------------------------------- #


def _build_repo_root() -> Path:
    # <repo>/tests/test_init_session.py -> parents[1] = <repo>
    return Path(__file__).resolve().parents[1]


def test_refuses_the_actual_sci_adk_build_repo(tmp_path):
    # the real build repo (this very checkout) must be refused -- never written to.
    with pytest.raises(NotADirectoryError):
        install_session(_build_repo_root())


def test_refuses_a_dir_with_sci_adk_package_layout(tmp_path):
    # marker 1: src/sci_adk/ -> looks like the sci-adk build repo.
    (tmp_path / "src" / "sci_adk").mkdir(parents=True)
    with pytest.raises(NotADirectoryError):
        install_session(tmp_path)
    # and nothing was written (no kit landed).
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_refuses_a_dir_with_moai_build_harness_marker(tmp_path):
    # marker 2: .claude/output-styles/moai/ -> a MoAI build harness.
    (tmp_path / ".claude" / "output-styles" / "moai").mkdir(parents=True)
    with pytest.raises(NotADirectoryError):
        install_session(tmp_path)
    # the pre-existing .claude is left as-is; no settings.json was written into it.
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_clean_dir_without_markers_still_installs(tmp_path):
    # regression: a clean workspace (no build markers) installs normally.
    report = install_session(tmp_path)
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert any("stop-verify-gate.sh" in a for a in report.installed)


# --------------------------------------------------------------------------- #
# 8c. MEDIUM: a malformed existing settings.json must NOT crash with a raw
#     traceback -- it raises a clean ValueError (mapped to a non-zero CLI exit).
# --------------------------------------------------------------------------- #


def test_malformed_existing_settings_json_raises_value_error(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text("{ this is not valid json,,, ",
                                          encoding="utf-8")
    with pytest.raises(ValueError):
        install_session(tmp_path)


# --------------------------------------------------------------------------- #
# 9. CLI surface
# --------------------------------------------------------------------------- #


def test_cli_init_session_exit_zero_prints_report(tmp_path, capsys):
    rc = main(["init-session", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    # the report names installed asset(s)
    assert "stop-verify-gate.sh" in out
    # files really landed
    assert (tmp_path / ".claude" / "settings.json").is_file()


def test_cli_init_session_dry_run_writes_nothing(tmp_path, capsys):
    rc = main(["init-session", str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert list(tmp_path.iterdir()) == []  # nothing written
    # but the plan was reported
    assert "stop-verify-gate.sh" in out


def test_cli_init_session_missing_dir_nonzero_no_traceback(tmp_path, capsys):
    rc = main(["init-session", str(tmp_path / "nope")])
    err = capsys.readouterr().err
    assert rc != 0
    assert err.strip()  # a friendly error message, not silence
    assert "error" in err.lower()


def test_cli_init_session_exit_zero_even_with_conflicts(tmp_path, capsys):
    # an outputStyle conflict is a warning, not a failure -> still exit 0
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps({"outputStyle": "MoAI"}, indent=2), encoding="utf-8")
    rc = main(["init-session", str(tmp_path)])
    assert rc == 0


def test_cli_init_session_malformed_settings_nonzero_no_traceback(tmp_path, capsys):
    # MEDIUM: a malformed existing settings.json -> a clean error line + non-zero
    # exit, NOT a raw traceback.
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text("{ broken,,,", encoding="utf-8")
    rc = main(["init-session", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc != 0
    assert "error" in err.lower()
    assert "settings.json" in err.lower()


def test_cli_init_session_refuses_build_repo_nonzero(tmp_path, capsys):
    # HIGH: the CLI must refuse a build-repo-marked target with a clean non-zero
    # exit (the marker guard maps to NotADirectoryError -> rc 2, no traceback).
    (tmp_path / "src" / "sci_adk").mkdir(parents=True)
    rc = main(["init-session", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc != 0
    assert "error" in err.lower()
