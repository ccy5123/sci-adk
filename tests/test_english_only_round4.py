"""English-only scripts and the research-workspace kit, round 4.

Independent checkers found:

  1. the previous round changed the kit's existing Stop hook timeout from 30000 to 30 and the
     UserPromptSubmit one from 10000 to 10. The Stop hook verifies every run (about 0.9 s per
     run; a workspace of 116 runs takes about 108 s), and Claude Code cancels a hook at its
     timeout, and a cancelled hook does not block: both go back to the values on master;
  2. "a line written back unchanged is allowed" compared lines byte for byte, so an LF Write
     over a CRLF legacy script was blocked;
  3. render --record-only said the scripts it shows by name only are "shipped byte for byte
     under paper/code/", but that mode writes nothing under paper/;
  4. check-ascii is an internal hook helper (user decision 2026-10-21): it is hidden from
     'sci-adk --help', the subcommand list and the "invalid choice" error of an unknown
     verb; the hook keeps calling it.

This file is ASCII-only itself: every non-ASCII character is built with ``chr``.
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from sci_adk.cli import build_parser, main
from sci_adk.loop.ascii_scripts import check_hook_input
from tests.test_english_only_scripts import GEUL, HAN, SETTINGS, _payload, _write

# -- 1. the Stop and UserPromptSubmit timeouts are the ones on master -----------------------------

# The values on master (8178fd1); the kit's settings must keep them.
_MASTER_TIMEOUTS = {"Stop": [30000], "UserPromptSubmit": [10000]}


def test_the_stop_and_user_prompt_submit_timeouts_are_the_master_values():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    for event, expected in _MASTER_TIMEOUTS.items():
        timeouts = [h["timeout"] for g in data["hooks"][event] for h in g["hooks"]]
        assert timeouts == expected, (event, timeouts)


def test_the_pretooluse_timeout_stays_30():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    timeouts = [h["timeout"] for g in data["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert timeouts == [30], timeouts


# -- 2. a CRLF legacy line written back with LF ---------------------------------------------------

_LEGACY_LINE = "# " + HAN + GEUL + " comment"


def test_an_lf_write_over_a_crlf_legacy_script_keeps_its_legacy_line(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_bytes((_LEGACY_LINE + "\r\nx = 1\r\n").encode("utf-8"))
    decision = check_hook_input(_write(tmp_path, "legacy.py", _LEGACY_LINE + "\nx = 2\n"))
    assert not decision.blocked, decision.message


def test_a_crlf_write_over_an_lf_legacy_script_keeps_its_legacy_line(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_bytes((_LEGACY_LINE + "\nx = 1\n").encode("utf-8"))
    decision = check_hook_input(_write(tmp_path, "legacy.py", _LEGACY_LINE + "\r\nx = 2\r\n"))
    assert not decision.blocked, decision.message


def test_an_lf_edit_of_a_crlf_legacy_script_keeps_its_legacy_line(tmp_path):
    script = tmp_path / "legacy.py"
    old = _LEGACY_LINE + "\r\nx = 1\r\n"
    script.write_bytes(old.encode("utf-8"))
    payload = _payload("Edit", {"file_path": str(script), "old_string": old,
                                "new_string": _LEGACY_LINE + "\nx = 2\n"}, tmp_path)
    decision = check_hook_input(payload)
    assert not decision.blocked, decision.message


def test_a_new_non_ascii_line_in_a_crlf_script_is_still_blocked(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_bytes((_LEGACY_LINE + "\r\nx = 1\r\n").encode("utf-8"))
    decision = check_hook_input(
        _write(tmp_path, "legacy.py", _LEGACY_LINE + "\nx = 1\ny = 2  # " + GEUL + "\n"))
    assert decision.blocked
    assert "line 3" in decision.message and "line 1" not in decision.message


# -- 3. the names-only notice of a record-only render ---------------------------------------------

def _names_only_lines(capsys, argv) -> list[str]:
    capsys.readouterr()
    assert main(argv) == 0
    captured = capsys.readouterr()
    return [line for line in (captured.out + captured.err).splitlines() if "by name only" in line]


def _run_with_non_ascii_script(tmp_path):
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "names-only-r4", code_ref="code/gen.py")
    script = run_dir / "code" / "gen.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# caf" + chr(0xE9) + "\nprint('x')\n", encoding="utf-8")
    return run_dir


def test_a_record_only_render_does_not_say_it_shipped_the_script(tmp_path, capsys):
    run_dir = _run_with_non_ascii_script(tmp_path)
    lines = _names_only_lines(capsys, ["render", str(run_dir), "--record-only"])
    assert len(lines) == 1, lines
    assert "shipped byte for byte" not in lines[0], lines[0]
    assert "a full render ships each under paper/code/" in lines[0], lines[0]
    assert not (run_dir / "paper").exists()


def test_a_full_render_still_says_it_shipped_the_script(tmp_path, capsys):
    run_dir = _run_with_non_ascii_script(tmp_path)
    lines = _names_only_lines(capsys, ["render", str(run_dir)])
    assert len(lines) == 1, lines
    assert "shipped byte for byte under paper/code/" in lines[0], lines[0]
    assert (run_dir / "paper" / "code" / "gen.py").is_file()


# -- 4. check-ascii is internal -------------------------------------------------------------------

def _top_level_help(capsys) -> str:
    with pytest.raises(SystemExit):
        main(["--help"])
    return capsys.readouterr().out


def test_check_ascii_is_not_in_the_top_level_help(capsys):
    text = _top_level_help(capsys)
    assert "check-ascii" not in text, text
    assert "SUPPRESS" not in text, text


def test_check_ascii_is_not_in_the_subcommand_list_of_a_usage_error(capsys):
    with pytest.raises(SystemExit):
        main([])
    err = capsys.readouterr().err
    assert "the following arguments are required" in err, err
    assert "check-ascii" not in err, err


def test_an_unknown_verb_error_does_not_name_check_ascii(capsys):
    with pytest.raises(SystemExit):
        main(["bogusverb"])
    err = capsys.readouterr().err
    assert "invalid choice: 'bogusverb'" in err, err
    assert "check-ascii" not in err, err
    assert "'render'" in err and "'init-session'" in err, err  # the public verbs stay listed


def test_the_public_verbs_are_listed_and_check_ascii_is_not():
    sub = next(a for a in build_parser()._actions if a.dest == "command")
    listed = sub.metavar.strip("{}").split(",")
    assert "check-ascii" not in listed
    assert "check-ascii" in sub.choices  # still a verb the hook runs
    assert sorted(listed) == sorted(n for n in sub.choices if n != "check-ascii")
    shown = [a.dest for a in sub._get_subactions()]
    assert "check-ascii" not in shown and "render" in shown


def test_the_hook_still_runs_check_ascii(tmp_path, monkeypatch):
    payload = _write(tmp_path, "fit.py", "x = 1  # " + HAN + "\n")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload.encode("utf-8"))))
    assert main(["check-ascii"]) == 3


def test_check_ascii_help_names_its_exit_codes(capsys):
    with pytest.raises(SystemExit):
        main(["check-ascii", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "exits 3" in text and "CHECK_ASCII_BLOCKED" in text and "exits 1" not in text, text
    assert "internal" in text.lower(), text
