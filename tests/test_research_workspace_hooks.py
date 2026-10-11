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
    stdin_text: str | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a hook with explicit control over cwd and CLAUDE_PROJECT_DIR.

    ``project_dir`` is the value of ``CLAUDE_PROJECT_DIR``; pass ``None`` to
    leave it unset (exercising the ``:-$PWD`` fallback). Runs are discovered from
    ``$CLAUDE_PROJECT_DIR`` (falling back to ``$PWD``), never from the stdin payload.
    ``stdin_text`` is the hook-input JSON Claude Code writes to the hook's stdin (the
    Stop gate reads ``stop_hook_active`` from it); ``None`` gives an empty stdin.
    """
    env = dict(os.environ)
    env["SCI_ADK_CMD"] = sci_adk_cmd
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    if extra_env:
        env.update(extra_env)
    stdin_kwargs: dict = (
        {"stdin": subprocess.DEVNULL} if stdin_text is None else {"input": stdin_text}
    )
    return subprocess.run(
        ["bash", str(hook)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        **stdin_kwargs,
    )


def _run_hook(
    hook: Path, workspace: Path, sci_adk_cmd: str, *, stdin_text: str | None = None
) -> subprocess.CompletedProcess:
    """Run a hook with cwd = workspace root and NO CLAUDE_PROJECT_DIR set.

    This exercises the ``:-$PWD`` fallback: run discovery resolves to
    ``$PWD/runs`` == the workspace's runs/.
    """
    return _run_hook_raw(hook, cwd=workspace, sci_adk_cmd=sci_adk_cmd, project_dir=None,
                         stdin_text=stdin_text)


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
    # the stub prints no DIVERGED/UNRESOLVED line, so the hook cannot name the cause; it
    # still blocks every Stop (the resolve advice appears only when verify names a claim)
    assert "blocks every stop" in res.stderr.lower()


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
    # the package gate is paper-side: it blocks once, and the message does not send the
    # session to `sci-adk resolve` (claims are not what failed)
    assert "once" in res.stderr.lower()
    assert "sci-adk resolve" not in res.stderr


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


# --- Stop gate: claim failures block every time, paper-side failures block once ----------
#
# Contract (design/research-session-enforcement.md D2, decided 2026-10-11): a recorded claim
# that does not re-derive (`sci-adk verify --claims-only` fails) blocks every Stop. A run
# whose claims reproduce but whose full `sci-adk verify` fails (manuscript, numbers,
# publishing requirements, deposit files) -- or a failing workspace package gate -- blocks
# the FIRST Stop with the reasons verify printed; when Claude Code retries the Stop with
# `"stop_hook_active": true` in the hook-input JSON, the hook lets the session end and warns.

_ACTIVE = json.dumps({"session_id": "s", "hook_event_name": "Stop", "stop_hook_active": True})
_INACTIVE = json.dumps({"session_id": "s", "hook_event_name": "Stop",
                        "stop_hook_active": False})

_DIVERGED_OUT = (
    "verified run 'S-1' -> runs/r1\n"
    "  record digest (sha256): 0123abcd\n"
    "    - H1: DIVERGED  (recorded=supported, re-derived=refuted)\n"
    "    - H2: REPRODUCED  (recorded=supported, re-derived=supported)\n"
)
_DIVERGED_ERR = "  NOT reproduced: at least one claim DIVERGED or is UNRESOLVED (see above)\n"
_REPRODUCED_OUT = (
    "verified run 'S-1' -> runs/r1\n"
    "    - H1: REPRODUCED  (recorded=supported, re-derived=supported)\n"
    "  all recorded claims reproduced from the record\n"
    "  paper-side checks not judged (--claims-only); `sci-adk verify runs/r1` is the full gate\n"
)


def _numbers_failure(n_bullets: int) -> str:
    lines = ["  numbers FAILED (a number in the paper is not in numbers.json, or does not "
             "match its recorded source):"]
    lines += [f"    - numbers: si.tex states 2026{i:02d} with no entry in numbers.json"
              for i in range(1, n_bullets + 1)]
    return "\n".join(lines) + "\n"


def _make_split_stub(
    tmp_path: Path,
    *,
    claims_exit: int = 0,
    claims_out: str = _REPRODUCED_OUT,
    claims_err: str = "",
    claims_fail_match: str | None = None,
    full_exit: int = 0,
    full_out: str = "verified run 'S-1'\n",
    full_err: str = "",
) -> Path:
    """A fake ``sci-adk`` that answers ``verify --claims-only`` and plain ``verify`` apart.

    ``verify --claims-only <run>`` prints ``claims_out`` / ``claims_err`` and exits
    ``claims_exit`` -- for every run, or, with ``claims_fail_match``, only for a run path
    containing that text (the others reproduce). Any other ``verify`` (a run's full gate or
    the workspace package gate) prints ``full_out`` / ``full_err`` and exits ``full_exit``.
    Every call is appended to ``calls.log`` beside the stub.
    """
    files = {
        "claims.out": claims_out, "claims.err": claims_err,
        "full.out": full_out, "full.err": full_err,
        "ok.out": _REPRODUCED_OUT,
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    d = str(tmp_path)
    if claims_fail_match is None:
        claims_branch = (f'cat "{d}/claims.out"; cat "{d}/claims.err" >&2; '
                         f"exit {claims_exit}")
    else:
        claims_branch = (
            f'case "$3" in *{claims_fail_match}*) '
            f'cat "{d}/claims.out"; cat "{d}/claims.err" >&2; exit {claims_exit};; '
            f'*) cat "{d}/ok.out"; exit 0;; esac'
        )
    stub = tmp_path / "sci-adk-split-stub.sh"
    stub.write_text(
        "#!/bin/bash\n"
        f'echo "$*" >> "{d}/calls.log"\n'
        'if [ "$1" = "verify" ] && [ "$2" = "--claims-only" ]; then\n'
        f"  {claims_branch}\n"
        "fi\n"
        'if [ "$1" = "verify" ]; then\n'
        f'  cat "{d}/full.out"; cat "{d}/full.err" >&2; exit {full_exit}\n'
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _workspace_with_claimed_run(tmp_path: Path, name: str = "r1") -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, name, with_claim=True)
    return ws


def test_stop_gate_claim_failure_blocks_even_when_stop_hook_active(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, claims_exit=1, claims_out=_DIVERGED_OUT,
                            claims_err=_DIVERGED_ERR, full_exit=1)
    for payload in (_INACTIVE, _ACTIVE):
        res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=payload)
        assert res.returncode == 2, (payload, res.stderr)
        assert "r1" in res.stderr
        # the message names the claim that does not re-derive, and only the relevant lines
        assert "H1: DIVERGED" in res.stderr
        assert "H2: REPRODUCED" not in res.stderr
        assert "sci-adk resolve" in res.stderr


def test_stop_gate_paper_failure_blocks_the_first_stop_with_the_reasons(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, full_exit=1, full_err=_numbers_failure(2))
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_INACTIVE)
    assert res.returncode == 2, res.stderr
    assert "r1" in res.stderr
    # the real reasons verify printed, not a guessed cause
    assert "numbers FAILED" in res.stderr
    assert "si.tex states 202601" in res.stderr
    assert "paper-side" in res.stderr
    assert "once" in res.stderr
    assert "sci-adk resolve" not in res.stderr
    assert "DIVERGED" not in res.stderr


def test_stop_gate_paper_failure_lets_the_retried_stop_end_with_a_warning(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, full_exit=1, full_err=_numbers_failure(2))
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_ACTIVE)
    assert res.returncode == 0, res.stderr
    # stderr: the warning with the run and the reasons
    assert "r1" in res.stderr
    assert "still fails" in res.stderr
    assert "numbers FAILED" in res.stderr
    # stdout: one JSON object whose systemMessage shows the user the same warning
    message = json.loads(res.stdout)["systemMessage"]
    assert "r1" in message
    assert "still fails" in message


def test_stop_gate_reads_the_flag_without_whitespace(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, full_exit=1, full_err=_numbers_failure(1))
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text='{"stop_hook_active":true}')
    assert res.returncode == 0, res.stderr


def test_stop_gate_empty_stdin_is_a_first_stop(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, full_exit=1, full_err=_numbers_failure(1))
    assert _run_hook(STOP_HOOK, ws, str(stub), stdin_text="").returncode == 2
    assert _run_hook(STOP_HOOK, ws, str(stub)).returncode == 2  # /dev/null


def test_stop_gate_paper_reasons_are_bounded(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, full_exit=1, full_err=_numbers_failure(10))
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_INACTIVE)
    assert res.returncode == 2
    assert "numbers FAILED" in res.stderr
    for shown in ("202601", "202602", "202603"):
        assert f"si.tex states {shown}" in res.stderr
    for hidden in ("202604", "202610"):
        assert f"si.tex states {hidden}" not in res.stderr
    assert "7 more" in res.stderr


def test_stop_gate_paper_failure_with_no_failed_line_points_to_verify(tmp_path):
    """verify can exit 1 without a FAILED header; the hook still says where to look."""
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path, full_exit=1, full_out="verified run 'S-1'\n")
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_INACTIVE)
    assert res.returncode == 2
    assert "sci-adk verify" in res.stderr
    assert "r1" in res.stderr


def test_stop_gate_package_failure_blocks_once_then_lets_stop(tmp_path):
    (tmp_path / "package").mkdir()
    err = ("  package requirements FAILED (declared requirements not met):\n"
           "    - number-audit: 0.42 in main.tex traces to no recorded value\n")
    stub = _make_split_stub(tmp_path, full_exit=1, full_err=err)
    first = _run_hook(STOP_HOOK, tmp_path, str(stub), stdin_text=_INACTIVE)
    assert first.returncode == 2
    assert "package requirements FAILED" in first.stderr
    assert "0.42 in main.tex" in first.stderr
    retried = _run_hook(STOP_HOOK, tmp_path, str(stub), stdin_text=_ACTIVE)
    assert retried.returncode == 0
    assert "package" in json.loads(retried.stdout)["systemMessage"]


def test_stop_gate_claim_failure_in_one_run_blocks_despite_paper_only_sibling(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_run(ws, "r_bad", with_claim=True)
    _make_run(ws, "r_paper", with_claim=True)
    stub = _make_split_stub(tmp_path, claims_exit=1, claims_out=_DIVERGED_OUT,
                            claims_err=_DIVERGED_ERR, claims_fail_match="r_bad",
                            full_exit=1, full_err=_numbers_failure(1))
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_ACTIVE)
    assert res.returncode == 2
    assert "r_bad" in res.stderr
    assert "H1: DIVERGED" in res.stderr


def test_stop_gate_passes_when_both_checks_pass_with_flag(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(tmp_path)
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_ACTIVE)
    assert res.returncode == 0
    assert res.stdout == ""


def test_stop_gate_missing_sci_adk_still_exit0_with_stdin(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    missing = str(tmp_path / "definitely-not-a-real-command-xyz")
    for payload in (_INACTIVE, _ACTIVE, ""):
        assert _run_hook(STOP_HOOK, ws, missing, stdin_text=payload).returncode == 0


# --- Stop gate against the real `sci-adk verify` ------------------------------------------


def _real_sci_adk_cmd() -> str:
    """This interpreter running the CLI module: the sci-adk under test, not one on PATH."""
    import sys

    return f"{sys.executable} -m sci_adk.cli"


def _seed_real_run(ws: Path, spec_id: str) -> Path:
    """A recorded run whose one claim reproduces, with no paper (paper side vacuous)."""
    import shutil

    from sci_adk.core.evidence import (
        Bearing,
        BearingDirection,
        EvidenceItem,
        EvidenceKind,
        Provenance,
        Result,
    )
    from sci_adk.core.spec import (
        DecisionRule,
        DecisionRuleKind,
        Hypothesis,
        HypothesisMode,
        MethodPlan,
        RawProposal,
        Spec,
        TargetClaim,
    )
    from sci_adk.loop.checkpoint_loop import run_checkpoint_loop

    spec = Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id="hyp-1", statement="the estimate clears 0.9",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
                referent="formal",
                non_circularity="the verifier checks a property not baked into the generator",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-1")],
    )

    def experiment(s, w):
        return [EvidenceItem(
            id="ev-1", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="fixture", data_source="generated"),
            result=Result(type="quantitative", point=0.95),
            bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
        )]

    run_dir = ws / "runs" / spec_id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=ws)
    shutil.rmtree(run_dir / "paper", ignore_errors=True)
    return run_dir


def _run_real_hook(ws: Path, stdin_text: str) -> subprocess.CompletedProcess:
    src = str(Path(__file__).resolve().parent.parent / "src")
    pythonpath = os.pathsep.join(p for p in (src, os.environ.get("PYTHONPATH")) if p)
    return _run_hook_raw(STOP_HOOK, cwd=ws, sci_adk_cmd=_real_sci_adk_cmd(),
                         project_dir=str(ws), stdin_text=stdin_text,
                         extra_env={"PYTHONPATH": pythonpath})


def test_stop_gate_real_verify_numbers_failure_blocks_once(tmp_path):
    """A paper-side failure from the real CLI: a declared number whose source is gone."""
    ws = tmp_path / "ws"
    ws.mkdir()
    run_dir = _seed_real_run(ws, "hook-real-numbers")
    (run_dir / "numbers.json").write_text(json.dumps({
        "spec_id": "hook-real-numbers",
        "numbers": [{"text": "0.95", "source": {"evidence": "ev-gone", "field": "point"}}],
    }), encoding="utf-8")

    first = _run_real_hook(ws, _INACTIVE)
    assert first.returncode == 2, first.stderr
    assert "hook-real-numbers" in first.stderr
    assert "numbers FAILED" in first.stderr
    assert "sci-adk resolve" not in first.stderr

    retried = _run_real_hook(ws, _ACTIVE)
    assert retried.returncode == 0, retried.stderr
    assert "numbers FAILED" in retried.stderr
    assert "hook-real-numbers" in json.loads(retried.stdout)["systemMessage"]


def test_stop_gate_real_verify_diverged_claim_blocks_every_time(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    run_dir = _seed_real_run(ws, "hook-real-diverged")
    claim_path = next((run_dir / "claims").glob("*.json"))
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["status"] = "contested"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")

    res = _run_real_hook(ws, _ACTIVE)
    assert res.returncode == 2, res.stderr
    assert "hook-real-diverged" in res.stderr
    assert "DIVERGED" in res.stderr


def test_stop_gate_real_verify_clean_run_passes(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed_real_run(ws, "hook-real-clean")
    res = _run_real_hook(ws, _INACTIVE)
    assert res.returncode == 0, res.stderr


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


# --- remedy text follows the actual cause (review of the hook rewrite, 2026-10-11) ---


def test_stop_gate_names_an_old_sci_adk_instead_of_advising_resolve(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(
        tmp_path, claims_exit=2, claims_out="",
        claims_err="usage: sci-adk verify [-h] [--strict-science] run_dir\n"
                   "sci-adk verify: error: unrecognized arguments: --claims-only\n",
        full_exit=1,
    )
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_INACTIVE)
    assert res.returncode == 2, res.stderr
    assert "older than this hook" in res.stderr
    assert "sci-adk resolve" not in res.stderr


def test_stop_gate_names_an_unreadable_record_instead_of_advising_resolve(tmp_path):
    ws = _workspace_with_claimed_run(tmp_path)
    stub = _make_split_stub(
        tmp_path, claims_exit=2, claims_out="",
        claims_err="error: runs/r1/spec.json is missing\n",
        full_exit=2,
    )
    res = _run_hook(STOP_HOOK, ws, str(stub), stdin_text=_INACTIVE)
    assert res.returncode == 2, res.stderr
    assert "spec.json is missing" in res.stderr
    assert "could not check the record" in res.stderr
    assert "sci-adk resolve" not in res.stderr
