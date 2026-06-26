"""Executable tests for the research-workspace enforcement hooks (Phase 2).

These tests exercise the two bash hooks shipped in
``src/sci_adk/templates/research-workspace/.claude/hooks/sci-adk/`` against fixture
workspaces built in ``tmp_path``. The hooks are run as real subprocesses; a
*stub* ``sci-adk`` is injected via ``SCI_ADK_CMD`` so the tests are hermetic
(no real sci-adk install needed and no real run-verification performed).

Design source: ``design/research-session-enforcement.md`` (D1 re-anchor,
D2 stop-gate strictness, D4 bash hooks).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

# --- locate the template kit (via the installer's own resolver, so the path
# follows the package wherever it ships -- editable or wheel) -----------------

from sci_adk.init_session import _templates_root

KIT = _templates_root()
HOOK_DIR = KIT / ".claude" / "hooks" / "sci-adk"
STOP_HOOK = HOOK_DIR / "stop-verify-gate.sh"
REANCHOR_HOOK = HOOK_DIR / "reanchor.sh"
SETTINGS = KIT / ".claude" / "settings.json"


# --- helpers ----------------------------------------------------------------


def _make_stub(tmp_path: Path, *, verify_exit: int) -> Path:
    """Write a fake ``sci-adk`` script and return its path.

    The stub understands the two verbs the hooks call:
      * ``verify <run>``  -> prints a line, exits ``verify_exit``
      * ``status <run>``  -> prints a recognizable marker + the run dir, exit 0
    Any other verb exits 0. It is pure POSIX sh so it runs anywhere bash does.
    """
    stub = tmp_path / "sci-adk-stub.sh"
    stub.write_text(
        "#!/bin/bash\n"
        'verb="$1"; shift || true\n'
        'case "$verb" in\n'
        "  verify)\n"
        '    echo "STUB-VERIFY run=$1"\n'
        f"    exit {verify_exit}\n"
        "    ;;\n"
        "  status)\n"
        # mirror the --json passthrough shape: last arg is the run dir
        '    for a in "$@"; do last="$a"; done\n'
        '    echo "STUB-STATUS-MARKER run=$last"\n'
        "    exit 0\n"
        "    ;;\n"
        "  *)\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _run_hook_raw(
    hook: Path,
    *,
    cwd: Path,
    sci_adk_cmd: str,
    project_dir: str | None,
) -> subprocess.CompletedProcess:
    """Run a hook with explicit control over cwd and CLAUDE_PROJECT_DIR.

    ``project_dir`` is the value of ``CLAUDE_PROJECT_DIR``; pass ``None`` to
    leave it unset (exercising the ``:-$PWD`` fallback). The hook reads NO
    stdin and discovers runs from ``$CLAUDE_PROJECT_DIR`` (falling back to
    ``$PWD``), never from a stdin payload.
    """
    env = dict(os.environ)
    env["SCI_ADK_CMD"] = sci_adk_cmd
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    return subprocess.run(
        ["bash", str(hook)],
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )


def _run_hook(hook: Path, workspace: Path, sci_adk_cmd: str) -> subprocess.CompletedProcess:
    """Run a hook with cwd = workspace root and NO CLAUDE_PROJECT_DIR set.

    This exercises the ``:-$PWD`` fallback: run discovery resolves to
    ``$PWD/runs`` == the workspace's runs/.
    """
    return _run_hook_raw(hook, cwd=workspace, sci_adk_cmd=sci_adk_cmd, project_dir=None)


def _make_run(workspace: Path, name: str, *, with_claim: bool) -> Path:
    """Create runs/<name>/ ; optionally drop one claim json into claims/."""
    run = workspace / "runs" / name
    run.mkdir(parents=True, exist_ok=True)
    claims = run / "claims"
    claims.mkdir(exist_ok=True)
    if with_claim:
        (claims / "c.json").write_text(json.dumps({"status": "SUPPORTED"}), encoding="utf-8")
    return run


# --- file-shape / validity checks -------------------------------------------


def test_hook_scripts_exist_and_are_executable():
    for hook in (STOP_HOOK, REANCHOR_HOOK):
        assert hook.is_file(), f"missing hook: {hook}"
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR, f"hook not executable (owner): {hook}"


def test_hook_scripts_have_lf_line_endings():
    for hook in (STOP_HOOK, REANCHOR_HOOK):
        raw = hook.read_bytes()
        assert b"\r\n" not in raw, f"CRLF line endings in {hook}"


def test_settings_json_is_valid_and_wires_both_hooks():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert data.get("outputStyle") == "science-orchestrator"
    hooks = data.get("hooks", {})
    assert "Stop" in hooks, "settings.json missing Stop hook event"
    assert "UserPromptSubmit" in hooks, "settings.json missing UserPromptSubmit hook event"
    # the wired commands reference the two .sh files by workspace-relative path
    stop_cmd = json.dumps(hooks["Stop"])
    ups_cmd = json.dumps(hooks["UserPromptSubmit"])
    assert "stop-verify-gate.sh" in stop_cmd
    assert "reanchor.sh" in ups_cmd


# --- Stop gate: the hard gate (D2 + D4) -------------------------------------


def test_stop_gate_blocks_when_claimed_run_fails_verify(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r1", with_claim=True)
    stub = _make_stub(tmp_path, verify_exit=3)  # DIVERGED/UNRESOLVED -> non-zero
    res = _run_hook(STOP_HOOK, ws, str(stub))
    assert res.returncode == 2, f"expected exit 2 (block), got {res.returncode}; stderr={res.stderr!r}"
    # stderr must name the failing run dir so the model knows what to fix
    assert "r1" in res.stderr
    assert "resolve" in res.stderr.lower()


def test_stop_gate_passes_when_verify_succeeds(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r1", with_claim=True)
    stub = _make_stub(tmp_path, verify_exit=0)
    res = _run_hook(STOP_HOOK, ws, str(stub))
    assert res.returncode == 0, f"expected exit 0, got {res.returncode}; stderr={res.stderr!r}"


def test_stop_gate_passes_through_claimless_run_without_running_verify(tmp_path):
    """D2: a run with NO recorded claim must NOT be verified, even if verify would fail."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r_empty", with_claim=False)  # empty claims/ dir
    stub = _make_stub(tmp_path, verify_exit=3)  # would fail IF it were run
    res = _run_hook(STOP_HOOK, ws, str(stub))
    assert res.returncode == 0, f"claimless run must pass; got {res.returncode}; stderr={res.stderr!r}"
    # the gate must not have invoked verify on the claimless run
    assert "STUB-VERIFY" not in (res.stdout + res.stderr)


def test_stop_gate_passes_when_claims_dir_absent(tmp_path):
    """A run dir with no claims/ subdir at all is also claimless -> pass-through."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "runs" / "r_no_claims").mkdir(parents=True)
    stub = _make_stub(tmp_path, verify_exit=3)
    res = _run_hook(STOP_HOOK, ws, str(stub))
    assert res.returncode == 0
    assert "STUB-VERIFY" not in (res.stdout + res.stderr)


def test_stop_gate_blocks_only_the_claimed_run_when_mixed(tmp_path):
    """One claimed+failing run blocks; a sibling claimless run is ignored."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r_claimed", with_claim=True)
    _make_run(ws, "r_empty", with_claim=False)
    stub = _make_stub(tmp_path, verify_exit=4)
    res = _run_hook(STOP_HOOK, ws, str(stub))
    assert res.returncode == 2
    assert "r_claimed" in res.stderr


def test_stop_gate_exit0_when_runs_dir_absent(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()  # no runs/ at all
    stub = _make_stub(tmp_path, verify_exit=3)
    res = _run_hook(STOP_HOOK, ws, str(stub))
    assert res.returncode == 0, f"no runs/ must pass; got {res.returncode}"


def test_stop_gate_exit0_when_sci_adk_absent(tmp_path):
    """Graceful degradation: resolved command not found -> exit 0 (never brick a session)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r1", with_claim=True)
    missing = str(tmp_path / "definitely-not-a-real-command-xyz")
    res = _run_hook(STOP_HOOK, ws, missing)
    assert res.returncode == 0, f"missing sci-adk must pass; got {res.returncode}; stderr={res.stderr!r}"


def test_stop_gate_uses_claude_project_dir_not_cwd(tmp_path):
    """The gate must discover runs via $CLAUDE_PROJECT_DIR, not the hook's cwd.

    Claude Code sets $CLAUDE_PROJECT_DIR to the project root but does NOT
    guarantee the hook's cwd is the project root. If the gate reads $PWD/runs,
    it silently finds nothing and exits 0 — enforcement silently disabled.
    Here the workspace (with a claimed, failing run) is reached only via
    $CLAUDE_PROJECT_DIR; cwd points at an unrelated dir with no runs/.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r1", with_claim=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()  # the hook's cwd; deliberately has NO runs/
    stub = _make_stub(tmp_path, verify_exit=3)  # verify fails for the claimed run
    res = _run_hook_raw(STOP_HOOK, cwd=elsewhere, sci_adk_cmd=str(stub), project_dir=str(ws))
    assert res.returncode == 2, (
        f"gate must fire via CLAUDE_PROJECT_DIR, not cwd; got {res.returncode}; "
        f"stderr={res.stderr!r}"
    )
    assert "r1" in res.stderr


def test_stop_gate_exit0_when_no_project_dir_and_no_cwd_runs(tmp_path):
    """Lock the ``:-$PWD`` fallback: no CLAUDE_PROJECT_DIR + no runs/ under cwd -> exit 0."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()  # cwd has no runs/; CLAUDE_PROJECT_DIR unset -> falls back to $PWD
    stub = _make_stub(tmp_path, verify_exit=3)
    res = _run_hook_raw(STOP_HOOK, cwd=elsewhere, sci_adk_cmd=str(stub), project_dir=None)
    assert res.returncode == 0, f"fallback with no runs/ must pass; got {res.returncode}"
    assert "STUB-VERIFY" not in (res.stdout + res.stderr)


# --- Stop gate: the package gate at session close (SPEC-PAPER-GATE-001 MP-5, REQ-PG-104) ----


def test_stop_gate_blocks_when_package_gate_fails(tmp_path):
    """MP-5: a conclusion-bearing package/ that fails `verify <ws>` BLOCKS Stop (exit 2).

    The package/ exists with NO runs/ -- the package gate runs regardless (it does not depend
    on the per-run claim-reproduction loop), proving the two gates are independent + additive.
    """
    (tmp_path / "package").mkdir()           # a conclusion-bearing package to gate
    stub = _make_stub(tmp_path, verify_exit=5)  # the package gate fails
    res = _run_hook(STOP_HOOK, tmp_path, str(stub))
    assert res.returncode == 2, f"package failure must block; got {res.returncode}; stderr={res.stderr!r}"
    assert "package" in res.stderr.lower()
    assert "resolve" in res.stderr.lower()


def test_stop_gate_allows_when_package_gate_passes(tmp_path):
    """MP-5: a clean package/ allows Stop (no false block)."""
    (tmp_path / "package").mkdir()
    stub = _make_stub(tmp_path, verify_exit=0)
    res = _run_hook(STOP_HOOK, tmp_path, str(stub))
    assert res.returncode == 0, f"clean package must pass; got {res.returncode}; stderr={res.stderr!r}"


def test_stop_gate_skips_package_gate_without_package_dir(tmp_path):
    """MP-5 (D2-style strictness): no package/ -> the package gate is NOT run (low noise)."""
    _make_run(tmp_path, "r1", with_claim=False)   # a claimless run, and NO package/
    stub = _make_stub(tmp_path, verify_exit=5)    # would fail IF verify were run
    res = _run_hook(STOP_HOOK, tmp_path, str(stub))
    assert res.returncode == 0, f"no package/ must skip the gate; got {res.returncode}; stderr={res.stderr!r}"
    assert "STUB-VERIFY" not in (res.stdout + res.stderr)


# --- reanchor: re-anchor (D1) -----------------------------------------------


def test_reanchor_prints_protocol_and_status_for_latest_run(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    # two runs; make r_new the most-recently-modified so it is "the current run"
    _make_run(ws, "r_old", with_claim=True)
    new = _make_run(ws, "r_new", with_claim=True)
    # bump mtime of r_new clearly ahead of r_old
    future = new.stat().st_mtime + 100
    os.utime(new, (future, future))
    stub = _make_stub(tmp_path, verify_exit=0)
    res = _run_hook(REANCHOR_HOOK, ws, str(stub))
    assert res.returncode == 0
    # the protocol reminder line
    assert "sci-adk" in res.stdout.lower()
    assert "verify" in res.stdout.lower()
    # the stub status output for the LATEST run
    assert "STUB-STATUS-MARKER" in res.stdout
    assert "r_new" in res.stdout
    # multiple runs -> a note about the count of the others
    assert "1" in res.stdout  # one other run besides the latest


def test_reanchor_exit0_when_no_runs(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    stub = _make_stub(tmp_path, verify_exit=0)
    res = _run_hook(REANCHOR_HOOK, ws, str(stub))
    assert res.returncode == 0
    # no status invocation when there is nothing to anchor to
    assert "STUB-STATUS-MARKER" not in res.stdout


def test_reanchor_exit0_when_sci_adk_absent(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r1", with_claim=True)
    missing = str(tmp_path / "definitely-not-a-real-command-xyz")
    res = _run_hook(REANCHOR_HOOK, ws, missing)
    assert res.returncode == 0
