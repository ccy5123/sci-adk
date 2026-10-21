"""English-only (ASCII) scripts in a research workspace (design/english-only-scripts.md).

The rule: a script in a research workspace is ASCII-only. A character the data needs is
written as an escape. Two layers enforce it:

  1. the kit's PreToolUse hook (``.claude/hooks/sci-adk/ascii-script-gate.sh``), which
     feeds the hook input to ``sci-adk check-ascii`` and blocks (exit 2) a Write / Edit /
     MultiEdit / NotebookEdit that would put a non-ASCII character into a script;
  2. ``sci-adk append-evidence``, which refuses (exit 2, nothing recorded) an Evidence item
     whose ``code_ref`` names such a script.

``verify`` adds one advisory per recorded script that holds non-ASCII bytes (never a FAIL).

This file is ASCII-only itself: every non-ASCII character is built with ``chr``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from sci_adk.cli import main
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
from sci_adk.init_session import _templates_root, install_session
from sci_adk.loop.compiler import ResearchCompiler

HAN = chr(0xD55C)  # HANGUL SYLLABLE HAN
GEUL = chr(0xAE00)  # HANGUL SYLLABLE GEUL
MICRO = chr(0xB5)  # MICRO SIGN
FORALL = chr(0x2200)  # FOR ALL (Lean notation)
BS = chr(92)  # a backslash, kept out of the source text

KIT = _templates_root()
GATE = KIT / ".claude" / "hooks" / "sci-adk" / "ascii-script-gate.sh"
SETTINGS = KIT / ".claude" / "settings.json"
GATE_REL = ".claude/hooks/sci-adk/ascii-script-gate.sh"
SRC = str(Path(__file__).resolve().parent.parent / "src")


# --- helpers ------------------------------------------------------------------------


def _sci_adk_cmd() -> str:
    """This interpreter running the CLI module: the sci-adk under test, not one on PATH."""
    return f"{sys.executable} -m sci_adk.cli"


def _run_gate(
    stdin: bytes | str | None, cwd: Path, *, sci_adk_cmd: str | None = None
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (SRC, os.environ.get("PYTHONPATH")) if p)
    env["SCI_ADK_CMD"] = sci_adk_cmd if sci_adk_cmd is not None else _sci_adk_cmd()
    env["CLAUDE_PROJECT_DIR"] = str(cwd)
    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    kwargs: dict = {"stdin": subprocess.DEVNULL} if stdin is None else {"input": stdin}
    proc = subprocess.run(
        ["bash", str(GATE)], cwd=str(cwd), env=env, capture_output=True, **kwargs
    )
    return subprocess.CompletedProcess(
        proc.args,
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


def _payload(tool: str, tool_input: dict, cwd: Path, *, ensure_ascii: bool = False) -> str:
    """The JSON Claude Code writes to a PreToolUse hook's stdin."""
    return json.dumps(
        {
            "session_id": "test-session",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": str(cwd),
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": tool_input,
        },
        ensure_ascii=ensure_ascii,
    )


def _write(ws: Path, rel: str, content: str, **kw) -> str:
    return _payload("Write", {"file_path": str(ws / rel), "content": content}, ws, **kw)


def _stub(tmp_path: Path, body: str) -> Path:
    stub = tmp_path / "sci-adk-stub.sh"
    stub.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


KOREAN_COMMENT_SCRIPT = "import math\n# " + HAN + GEUL + " comment\nx = math.pi\n"


# --- the shipped hook and its wiring -------------------------------------------------


def test_gate_hook_ships_executable_with_lf_endings_and_ascii_text():
    assert GATE.is_file(), f"missing hook: {GATE}"
    assert GATE.stat().st_mode & stat.S_IXUSR, "hook not executable (owner)"
    raw = GATE.read_bytes()
    assert b"\r\n" not in raw
    assert raw.isascii(), "the hook is a script: it must be ASCII-only too"


def test_settings_wire_the_gate_as_a_pretooluse_hook_on_the_writing_tools():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    groups = data["hooks"]["PreToolUse"]
    ours = [g for g in groups if "ascii-script-gate.sh" in json.dumps(g)]
    assert len(ours) == 1
    matcher = ours[0]["matcher"]
    for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        assert tool in matcher.split("|"), tool
    # Claude Code reads a hook timeout in seconds
    assert all(h["timeout"] <= 120 for h in ours[0]["hooks"])


def test_init_session_installs_the_gate_and_wires_it_once(tmp_path):
    install_session(tmp_path)
    hook = tmp_path / GATE_REL
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        h["command"]
        for g in settings["hooks"]["PreToolUse"]
        for h in g["hooks"]
        if "ascii-script-gate.sh" in h["command"]
    ]
    assert len(commands) == 1
    install_session(tmp_path)  # idempotent: no second PreToolUse entry
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    again = [
        h["command"]
        for g in settings["hooks"]["PreToolUse"]
        for h in g["hooks"]
        if "ascii-script-gate.sh" in h["command"]
    ]
    assert again == commands


def test_init_session_rerun_on_an_older_workspace_adds_the_gate(tmp_path):
    """A workspace installed before the gate existed: re-running adds the hook file and the
    PreToolUse entry, and leaves its (older) CLAUDE.md alone."""
    install_session(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    old = json.loads(settings_path.read_text(encoding="utf-8"))
    del old["hooks"]["PreToolUse"]
    settings_path.write_text(json.dumps(old), encoding="utf-8")
    hook = tmp_path / GATE_REL
    hook.rename(tmp_path / "gate.bak")
    (tmp_path / "CLAUDE.md").write_text("# an older protocol\n", encoding="utf-8")

    report = install_session(tmp_path)
    assert hook.is_file()
    assert any("ascii-script-gate.sh" in a for a in report.installed)
    assert "wired PreToolUse hook" in report.settings_changes
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "# an older protocol\n"


def test_init_session_keeps_a_users_own_pretooluse_hook(tmp_path):
    (tmp_path / ".claude").mkdir()
    user_group = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-guard.sh"}]}
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [user_group]}}), encoding="utf-8"
    )
    install_session(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = settings["hooks"]["PreToolUse"]
    assert groups[0] == user_group
    assert any("ascii-script-gate.sh" in json.dumps(g) for g in groups[1:])


# --- the hook: what it blocks ---------------------------------------------------------


def test_gate_blocks_a_write_of_a_korean_comment_into_a_python_script(tmp_path):
    proc = _run_gate(_write(tmp_path, "analysis/fit.py", KOREAN_COMMENT_SCRIPT), tmp_path)
    assert proc.returncode == 2, proc.stderr
    err = proc.stderr
    assert "analysis/fit.py" in err
    assert "line 2" in err
    assert "U+D55C" in err and "U+AE00" in err
    # the escape advice names the escape for the character found
    assert '"' + BS + 'ud55c"' in err
    assert "record.tex" in err
    assert "line 1" not in err and "line 3" not in err


def test_gate_blocks_non_ascii_sent_as_json_escapes(tmp_path):
    payload = _write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT, ensure_ascii=True)
    assert payload.isascii()
    proc = _run_gate(payload, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "U+D55C" in proc.stderr


def test_gate_allows_an_ascii_script_that_writes_characters_as_escapes(tmp_path):
    content = 'UNIT = "' + BS + 'u00b5g/L"  # micro gram per litre\nprint(UNIT)\n'
    proc = _run_gate(_write(tmp_path, "fit.py", content), tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "" and proc.stdout == ""


def test_gate_names_the_file_line_of_an_edit(tmp_path):
    script = tmp_path / "analysis" / "fit.py"
    script.parent.mkdir()
    script.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    payload = _payload(
        "Edit",
        {"file_path": str(script), "old_string": "b = 2", "new_string": "b = 2  # " + HAN},
        tmp_path,
    )
    proc = _run_gate(payload, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "line 2" in proc.stderr
    assert "U+D55C" in proc.stderr


def test_gate_names_the_file_line_of_a_multiedit(tmp_path):
    script = tmp_path / "fit.R"
    script.write_text("a <- 1\nb <- 2\nc <- 3\n", encoding="utf-8")
    payload = _payload(
        "MultiEdit",
        {
            "file_path": str(script),
            "edits": [
                {"old_string": "a <- 1", "new_string": "a <- 10"},
                {"old_string": "c <- 3", "new_string": "c <- 3\nunit <- '" + MICRO + "g'"},
            ],
        },
        tmp_path,
    )
    proc = _run_gate(payload, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "line 4" in proc.stderr
    assert "U+00B5" in proc.stderr
    assert BS + "u00b5" in proc.stderr  # R takes the same escape


def test_gate_blocks_an_edit_whose_old_text_is_not_found_by_new_text_line(tmp_path):
    script = tmp_path / "fit.py"
    script.write_text("a = 1\n", encoding="utf-8")
    payload = _payload(
        "Edit",
        {"file_path": str(script), "old_string": "zzz", "new_string": "ok\n# " + HAN},
        tmp_path,
    )
    proc = _run_gate(payload, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "line 2 of the new text" in proc.stderr


@pytest.mark.parametrize(
    "rel",
    ["fit.py", "gui.pyw", "fit.R", "fit.r", "fit.jl", "fit.m", "run.sh", "run.bash",
     "run.zsh", "fit.pl", "fit.rb", "plot.js", "plot.mjs", "plot.ts", "fit.sage",
     "fit.do", "fit.sas", "query.sql", "solver.c", "Makefile"],
)
def test_gate_blocks_every_script_kind(tmp_path, rel):
    proc = _run_gate(_write(tmp_path, rel, "x = 1\n# " + HAN + "\n"), tmp_path)
    assert proc.returncode == 2, (rel, proc.stderr)


def test_gate_blocks_an_extensionless_shebang_script(tmp_path):
    proc = _run_gate(_write(tmp_path, "bin/run_all", "#!/bin/sh\necho " + HAN + "\n"), tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "printf" in proc.stderr or "U+D55C" in proc.stderr


def test_gate_shell_advice_is_printf_octal_bytes(tmp_path):
    proc = _run_gate(_write(tmp_path, "run.sh", "echo '" + MICRO + "'\n"), tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "printf '" + BS + "302" + BS + "265'" in proc.stderr


def test_gate_blocks_a_notebook_code_cell_but_not_a_markdown_cell(tmp_path):
    nb = str(tmp_path / "analysis.ipynb")
    code = _payload(
        "NotebookEdit",
        {"notebook_path": nb, "new_source": "x = 1\n# " + HAN, "cell_type": "code",
         "edit_mode": "insert"},
        tmp_path,
    )
    proc = _run_gate(code, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "line 2" in proc.stderr
    markdown = _payload(
        "NotebookEdit",
        {"notebook_path": nb, "new_source": "# " + HAN + GEUL, "cell_type": "markdown",
         "edit_mode": "insert"},
        tmp_path,
    )
    proc = _run_gate(markdown, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""


# --- the hook: what it allows ---------------------------------------------------------


@pytest.mark.parametrize(
    "rel", ["notes.md", "spec.json", "data/table.csv", "paper/draft.tex", "README.txt",
            "analysis.ipynb", "report.Rmd"],
)
def test_gate_allows_non_ascii_in_files_that_are_not_scripts(tmp_path, rel):
    proc = _run_gate(_write(tmp_path, rel, HAN + GEUL + " " + MICRO + "\n"), tmp_path)
    assert proc.returncode == 0, (rel, proc.stderr)
    assert proc.stderr == "" and proc.stdout == ""


def test_gate_allows_lean_unicode_notation(tmp_path):
    proof = "theorem t : " + FORALL + " n : Nat, n = n := fun _ => rfl\n"
    proc = _run_gate(_write(tmp_path, "proofs/T.lean", proof), tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""


def test_gate_does_not_check_files_under_dot_claude(tmp_path):
    proc = _run_gate(_write(tmp_path, ".claude/hooks/mine.py", KOREAN_COMMENT_SCRIPT), tmp_path)
    assert proc.returncode == 0, proc.stderr


def test_gate_allows_an_edit_of_a_data_file(tmp_path):
    table = tmp_path / "data.csv"
    table.write_text("a,b\n1,2\n", encoding="utf-8")
    payload = _payload(
        "Edit", {"file_path": str(table), "old_string": "a,b", "new_string": HAN + ",b"},
        tmp_path,
    )
    assert _run_gate(payload, tmp_path).returncode == 0


def test_gate_ignores_other_tools(tmp_path):
    payload = _payload("Bash", {"command": "echo " + HAN}, tmp_path)
    assert _run_gate(payload, tmp_path).returncode == 0


# --- the hook: graceful when it cannot check --------------------------------------------


def test_gate_lets_unreadable_input_through_with_a_warning(tmp_path):
    proc = _run_gate('{"tool_name": "Write", "tool_input": {"content": "' + HAN, tmp_path)
    assert proc.returncode == 0
    assert "WARNING" in proc.stderr
    assert "append-evidence" in proc.stderr  # the second layer still applies
    assert "systemMessage" in json.loads(proc.stdout.strip().splitlines()[-1])


def test_gate_lets_input_without_tool_fields_through_with_a_warning(tmp_path):
    proc = _run_gate(json.dumps({"tool_name": "Write", "note": HAN}, ensure_ascii=False),
                     tmp_path)
    assert proc.returncode == 0
    assert "WARNING" in proc.stderr


def test_gate_lets_empty_input_through_with_a_warning(tmp_path):
    proc = _run_gate(b"", tmp_path)
    assert proc.returncode == 0
    assert "WARNING" in proc.stderr


def test_gate_passes_ascii_input_without_running_sci_adk(tmp_path):
    marker = tmp_path / "ran"
    stub = _stub(tmp_path, f'touch "{marker}"\nexit 1\n')
    proc = _run_gate(_write(tmp_path, "fit.py", "x = 1\n"), tmp_path, sci_adk_cmd=str(stub))
    assert proc.returncode == 0
    assert not marker.exists(), "an ASCII-only input must not start sci-adk"


def test_gate_without_sci_adk_lets_the_call_through_with_a_warning(tmp_path):
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path,
                     sci_adk_cmd=str(tmp_path / "no-such-sci-adk"))
    assert proc.returncode == 0
    assert "WARNING" in proc.stderr


def test_gate_with_an_older_sci_adk_says_to_upgrade(tmp_path):
    stub = _stub(
        tmp_path,
        "echo \"sci-adk: error: argument command: invalid choice: 'check-ascii'\" >&2\n"
        "exit 2\n",
    )
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path,
                     sci_adk_cmd=str(stub))
    assert proc.returncode == 0
    assert "upgrade" in proc.stderr


def test_check_ascii_verb_refuses_a_terminal_stdin(monkeypatch, capsys):
    class _Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", _Tty())
    assert main(["check-ascii"]) == 2
    assert capsys.readouterr().err.startswith("error:")


# --- the record-time refusal (append-evidence) -----------------------------------------

_HYP = "hyp-1"


def _spec(spec_id: str) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=_HYP, statement="the estimate clears 0.9",
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
        target_claims=[TargetClaim(id="tc", statement="t", answers=_HYP)],
    )


def _item(spec_id: str, ev_id: str, code_ref: str) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id, spec_id=spec_id, kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref=code_ref, data_source="generated"),
        result=Result(type="quantitative", point=0.95),
        bears_on=[Bearing(target_id=_HYP, direction=BearingDirection.SUPPORTS)],
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append(ws: Path, run_dir: Path, item: EvidenceItem) -> int:
    ev = ws / f"{item.id}.json"
    ev.write_text(json.dumps(item.model_dump(mode="json")), encoding="utf-8")
    return main(["append-evidence", str(run_dir), "--evidence", str(ev)])


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ResearchCompiler(workspace_dir=workspace).stage_init_spec(spec=_spec("ascii-run"))
    return workspace


def test_append_evidence_refuses_a_script_holding_non_ascii(ws, capsys):
    script = ws / "analysis" / "fit.py"
    script.parent.mkdir()
    script.write_text(KOREAN_COMMENT_SCRIPT, encoding="utf-8")
    run_dir = ws / "runs" / "ascii-run"
    rc = _append(ws, run_dir, _item("ascii-run", "ev-1", f"analysis/fit.py sha256={_sha(script)}"))
    err = capsys.readouterr().err
    assert rc == 2
    assert err.startswith("error:")
    assert "analysis/fit.py" in err and "line 2" in err and "U+D55C" in err
    assert '"' + BS + 'ud55c"' in err
    assert "nothing was recorded" in err
    assert not (run_dir / "evidence" / "ev-1.json").exists()


def test_append_evidence_refusal_covers_every_script_the_code_ref_names(ws, capsys):
    first = ws / "analysis" / "a.py"
    first.parent.mkdir()
    first.write_text("print(1)\n", encoding="utf-8")
    second = ws / "analysis" / "b.py"
    second.write_text("x = 1\ny = 2\nlabel = '" + MICRO + "g'\n", encoding="utf-8")
    ref = (f"analysis/a.py sha256={_sha(first)} (inputs from analysis/b.py "
           f"sha256={_sha(second)})")
    run_dir = ws / "runs" / "ascii-run"
    assert _append(ws, run_dir, _item("ascii-run", "ev-2", ref)) == 2
    err = capsys.readouterr().err
    assert "analysis/b.py" in err and "line 3" in err and "U+00B5" in err
    assert not (run_dir / "evidence" / "ev-2.json").exists()


def test_append_evidence_names_bytes_that_are_not_utf8(ws, capsys):
    script = ws / "fit.py"
    script.write_bytes(b"x = 1\n# caf\xe9\n")
    run_dir = ws / "runs" / "ascii-run"
    assert _append(ws, run_dir, _item("ascii-run", "ev-3", "fit.py")) == 2
    err = capsys.readouterr().err
    assert "line 2" in err and "0xE9" in err


def test_append_evidence_accepts_an_ascii_script_with_escapes(ws, capsys):
    script = ws / "fit.py"
    script.write_text('UNIT = "' + BS + 'u00b5g/L"\n', encoding="utf-8")
    run_dir = ws / "runs" / "ascii-run"
    assert _append(ws, run_dir, _item("ascii-run", "ev-4", f"fit.py sha256={_sha(script)}")) == 0
    assert (run_dir / "evidence" / "ev-4.json").exists()


def test_append_evidence_accepts_a_lean_proof_and_a_data_file_with_unicode(ws, capsys):
    proof = ws / "T.lean"
    proof.write_text("theorem t : " + FORALL + " n : Nat, n = n := fun _ => rfl\n",
                     encoding="utf-8")
    table = ws / "data.csv"
    table.write_text(HAN + ",b\n1,2\n", encoding="utf-8")
    ref = f"T.lean sha256={_sha(proof)} (reads data.csv sha256={_sha(table)})"
    run_dir = ws / "runs" / "ascii-run"
    assert _append(ws, run_dir, _item("ascii-run", "ev-5", ref)) == 0
    assert (run_dir / "evidence" / "ev-5.json").exists()


def test_append_evidence_does_not_check_a_pointer(ws, capsys):
    run_dir = ws / "runs" / "ascii-run"
    assert _append(ws, run_dir, _item("ascii-run", "ev-6", "commit 0123abc " + HAN)) == 0


# --- verify: an advisory for a script recorded before the rule ---------------------------


def _seed_recorded_run(ws: Path, spec_id: str, script_text: str) -> Path:
    """A run whose claim reproduces and whose two items name one script (recorded by the
    Python API, i.e. without the append-evidence refusal), with no paper."""
    from sci_adk.loop.checkpoint_loop import run_checkpoint_loop

    script = ws / "analysis" / "fit.py"
    script.parent.mkdir(exist_ok=True)
    script.write_text(script_text, encoding="utf-8")
    ref = f"analysis/fit.py sha256={_sha(script)}"
    spec = _spec(spec_id)

    def experiment(s, w):
        return [_item(s.id, "ev-a", ref), _item(s.id, "ev-b", ref)]

    run_dir = ws / "runs" / spec_id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment, workspace_dir=ws)
    shutil.rmtree(run_dir / "paper", ignore_errors=True)
    return run_dir


def test_verify_advises_once_per_recorded_non_ascii_script_and_still_passes(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _seed_recorded_run(tmp_path, "old-run", KOREAN_COMMENT_SCRIPT)
    report = verify_run(run_dir)
    notes = [n for n in report.paper_advisory if "non-ASCII" in n]
    assert len(notes) == 1, report.paper_advisory
    assert "analysis/fit.py" in notes[0] and "line 2" in notes[0] and "U+D55C" in notes[0]
    assert "\n" not in notes[0]
    assert report.passed


def test_verify_says_nothing_for_an_ascii_script(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _seed_recorded_run(tmp_path, "new-run", "x = 1\n")
    report = verify_run(run_dir)
    assert not [n for n in report.paper_advisory if "non-ASCII" in n]
    assert report.passed


def test_cli_verify_prints_the_advisory_and_exits_zero(tmp_path, capsys):
    run_dir = _seed_recorded_run(tmp_path, "old-run-cli", KOREAN_COMMENT_SCRIPT)
    rc = main(["verify", str(run_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "analysis/fit.py" in out and "non-ASCII" in out


# --- the rule's file set --------------------------------------------------------------


def test_rule_covers_scripts_and_exempts_lean_notebooks_and_documents():
    from sci_adk.loop.ascii_scripts import ASCII_EXEMPT_EXTENSIONS, is_ascii_script

    for path in ("a.py", "a.PY", "a.pyw", "a.R", "a.sql", "dir/Makefile", "x.c"):
        assert is_ascii_script(path), path
    for path in ("a.md", "a.json", "a.csv", "a.tex", "a.txt", "a.lean", "a.ipynb",
                 "a.Rmd", "a.qmd", "bin/run"):
        assert not is_ascii_script(path), path
    assert is_ascii_script("bin/run", b"#!")
    assert not is_ascii_script("bin/run", b"ab")
    assert ".lean" in ASCII_EXEMPT_EXTENSIONS


def test_kit_instructions_state_the_rule():
    """The workspace CLAUDE.md and the skills/agents that write analysis code state it."""
    for rel in (
        "CLAUDE.md",
        ".claude/skills/sci/SKILL.md",
        ".claude/skills/science-foundation-rigor/SKILL.md",
        ".claude/skills/science-workflow-experiment/SKILL.md",
        ".claude/agents/expert-experimentalist.md",
        ".claude/agents/expert-replicator.md",
    ):
        text = (KIT / rel).read_text(encoding="utf-8")
        assert "ASCII-only" in text, rel
        assert BS + "u00b5" in text or "escape" in text, rel
