"""English-only (ASCII) scripts, round 2 (design/english-only-scripts.md).

Independent checkers found:

  1. the hook blocked on any exit 1 of ``sci-adk check-ascii`` -- also the exit 1 of a crash
     (a broken import, a bug), so a Korean ``.md`` Write was refused with a traceback, against
     the contract that a sci-adk that cannot check lets the call through with a warning;
  2. the ``.claude/`` exemption matched any path component, so a script under a Claude Code
     isolation worktree (``.claude/worktrees/<name>/...``) skipped the rule;
  3. an Edit of a legacy script was refused when its new text repeated, unchanged, a
     non-ASCII line its old text held.

This file is ASCII-only itself: every non-ASCII character is built with ``chr``.
"""

from __future__ import annotations

import io
import sys

from sci_adk.cli import main
from tests.test_english_only_scripts import (
    GEUL,
    HAN,
    KOREAN_COMMENT_SCRIPT,
    _payload,
    _run_gate,
    _stub,
    _write,
)

_CRASH = ('echo "Traceback (most recent call last):" >&2\n'
          'echo "RuntimeError: boom" >&2\nexit 1\n')


# -- 1. only a block exits the dedicated code --------------------------------------------

def _check_ascii(monkeypatch, payload: str) -> int:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload.encode("utf-8"))))
    return main(["check-ascii"])


def test_check_ascii_exits_3_on_a_block(tmp_path, monkeypatch, capsys):
    assert _check_ascii(monkeypatch, _write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT)) == 3
    assert "Blocked" in capsys.readouterr().err


def test_check_ascii_exits_0_when_it_allows(tmp_path, monkeypatch):
    assert _check_ascii(monkeypatch, _write(tmp_path, "notes.md", "# " + HAN + "\n")) == 0


def test_a_crash_of_sci_adk_never_blocks_a_korean_note(tmp_path):
    # A document target now passes before sci-adk starts (tests/test_english_only_round3.py);
    # a crash on a target that does reach sci-adk is the next test.
    stub = _stub(tmp_path, _CRASH)
    proc = _run_gate(_write(tmp_path, "notes.md", "# " + HAN + "\n"), tmp_path,
                     sci_adk_cmd=str(stub))
    assert proc.returncode == 0, proc.stderr
    assert "RuntimeError" not in proc.stderr


def test_a_crash_of_sci_adk_names_the_exception_in_its_warning(tmp_path):
    stub = _stub(tmp_path, _CRASH)
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path,
                     sci_adk_cmd=str(stub))
    assert proc.returncode == 0, proc.stderr
    assert "WARNING" in proc.stderr and "exited 1" in proc.stderr
    assert "RuntimeError: boom" in proc.stderr  # the exception, not the traceback's head


def test_a_crash_of_sci_adk_lets_a_script_through_with_a_warning(tmp_path):
    stub = _stub(tmp_path, _CRASH)
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path,
                     sci_adk_cmd=str(stub))
    assert proc.returncode == 0, proc.stderr
    assert "WARNING" in proc.stderr and "append-evidence" in proc.stderr


def test_the_gate_blocks_on_exit_3_and_shows_the_reason(tmp_path):
    stub = _stub(tmp_path, 'echo "[sci-adk] Blocked: reason" >&2\nexit 3\n')
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path,
                     sci_adk_cmd=str(stub))
    assert proc.returncode == 2
    assert "Blocked: reason" in proc.stderr


def test_the_real_sci_adk_still_blocks_a_korean_script(tmp_path):
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "U+D55C" in proc.stderr


# -- 2. the project's own .claude/ only --------------------------------------------------

def test_a_script_in_a_claude_isolation_worktree_is_checked(tmp_path):
    rel = ".claude/worktrees/agent-1/analysis/fit.py"
    proc = _run_gate(_write(tmp_path, rel, KOREAN_COMMENT_SCRIPT), tmp_path)
    assert proc.returncode == 2, proc.stderr


def test_a_claude_directory_inside_the_project_tree_is_checked(tmp_path):
    proc = _run_gate(_write(tmp_path, "analysis/.claude/fit.py", KOREAN_COMMENT_SCRIPT),
                     tmp_path)
    assert proc.returncode == 2, proc.stderr


def test_the_projects_own_claude_directory_is_not_checked(tmp_path):
    proc = _run_gate(_write(tmp_path, ".claude/hooks/mine.py", KOREAN_COMMENT_SCRIPT), tmp_path)
    assert proc.returncode == 0, proc.stderr


# -- 3. an unchanged legacy line ---------------------------------------------------------

_LEGACY = "# " + HAN + GEUL + " comment\nx = 1\n"


def test_an_edit_that_keeps_a_legacy_non_ascii_line_is_allowed(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_text(_LEGACY, encoding="utf-8")
    payload = _payload("Edit", {"file_path": str(script), "old_string": _LEGACY,
                                "new_string": _LEGACY.replace("x = 1", "x = 2")}, tmp_path)
    proc = _run_gate(payload, tmp_path)
    assert proc.returncode == 0, proc.stderr


def test_an_edit_that_adds_a_non_ascii_line_to_a_legacy_script_is_blocked(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_text(_LEGACY, encoding="utf-8")
    payload = _payload("Edit", {"file_path": str(script), "old_string": _LEGACY,
                                "new_string": _LEGACY + "y = 2  # " + GEUL + "\n"}, tmp_path)
    proc = _run_gate(payload, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "line 3" in proc.stderr and "line 1" not in proc.stderr


def test_a_multiedit_that_keeps_a_legacy_line_is_allowed(tmp_path):
    script = tmp_path / "legacy.R"
    script.write_text(_LEGACY, encoding="utf-8")
    payload = _payload("MultiEdit", {"file_path": str(script), "edits": [
        {"old_string": _LEGACY.splitlines()[0] + "\nx", "new_string": _LEGACY.splitlines()[0]
         + "\nz"}]}, tmp_path)
    assert _run_gate(payload, tmp_path).returncode == 0


def test_a_write_that_keeps_the_file_s_legacy_lines_is_allowed_but_not_new_ones(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_text(_LEGACY, encoding="utf-8")
    kept = _run_gate(_write(tmp_path, "legacy.py", _LEGACY + "y = 3\n"), tmp_path)
    assert kept.returncode == 0, kept.stderr
    added = _run_gate(_write(tmp_path, "legacy.py", _LEGACY + "# " + GEUL + "\n"), tmp_path)
    assert added.returncode == 2
    assert "line 3" in added.stderr


def test_the_kit_s_own_scripts_are_ascii():
    # The workspace's own .claude/ is outside the rule (Claude Code's configuration); the
    # package builders under package/04_scripts/ are scripts the rule covers.
    from sci_adk.init_session import _templates_root
    from sci_adk.loop.ascii_scripts import is_ascii_script

    root = _templates_root()
    offending = [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
        and p.relative_to(root).parts[0] != ".claude"
        and is_ascii_script(p.name, p.read_bytes()[:2]) and not p.read_bytes().isascii()
    ]
    assert offending == []


def test_the_design_says_writes_through_bash_bypass_the_hook():
    from pathlib import Path

    design = (Path(__file__).resolve().parent.parent / "design" / "english-only-scripts.md")
    text = design.read_text(encoding="utf-8")
    assert "Bash tool" in text and "append-evidence" in text
