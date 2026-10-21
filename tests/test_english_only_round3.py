"""English-only (ASCII) scripts, round 3 (design/english-only-scripts.md).

Independent checkers found minor gaps:

  1. the fast path let an input that is not JSON at all through silently (the contract says a
     hook that cannot read its input warns);
  2. the fast path scanned the whole payload, so any non-ASCII byte anywhere (a Korean .md, a
     home directory outside ASCII) started Python and sci-adk on every Write/Edit;
  3. the verify advisory for a recorded non-ASCII script printed as 'advisory:' without a
     publishing contract and as 'publishing advisory:' with one;
  4. the check-ascii help text said it exits 1 on a block (it exits 3);
  5. the new PreToolUse hook's timeout is in seconds (Claude Code reads seconds). The kit's
     Stop and UserPromptSubmit timeouts keep the values on master (round 4 pins them).

This file is ASCII-only itself: every non-ASCII character is built with ``chr``.
"""

from __future__ import annotations

import json
import re

import pytest

from sci_adk.cli import main
from tests.test_english_only_scripts import (
    GATE,
    HAN,
    KOREAN_COMMENT_SCRIPT,
    SETTINGS,
    _run_gate,
    _seed_recorded_run,
    _stub,
    _write,
)

_RECORDING_STUB = 'echo called >> "$CLAUDE_PROJECT_DIR/stub-called"\nexit 0\n'


# -- 1. an input that is not JSON warns ------------------------------------------------------

@pytest.mark.parametrize("payload", [b"not json", b"{", b"[1, 2]", b"  \n"])
def test_an_input_that_is_not_a_json_object_goes_through_with_a_warning(tmp_path, payload):
    proc = _run_gate(payload, tmp_path, sci_adk_cmd=str(_stub(tmp_path, _RECORDING_STUB)))
    assert proc.returncode == 0, proc.stderr
    assert "WARNING" in proc.stderr and "append-evidence" in proc.stderr
    assert "systemMessage" in proc.stdout


def test_a_plain_ascii_hook_input_goes_through_silently(tmp_path):
    proc = _run_gate(_write(tmp_path, "fit.py", "x = 1\n"), tmp_path,
                     sci_adk_cmd=str(_stub(tmp_path, _RECORDING_STUB)))
    assert proc.returncode == 0 and proc.stderr == "" and proc.stdout == ""
    assert not (tmp_path / "stub-called").exists()


# -- 2. a document target exits before sci-adk starts ------------------------------------------

@pytest.mark.parametrize("rel", ["notes.md", "data/table.csv", "paper/x.tex", "spec.json",
                                 "README.txt", "proof.lean"])
def test_a_document_write_holding_korean_never_starts_sci_adk(tmp_path, rel):
    proc = _run_gate(_write(tmp_path, rel, "# " + HAN + "\n"), tmp_path,
                     sci_adk_cmd=str(_stub(tmp_path, _RECORDING_STUB)))
    assert proc.returncode == 0 and proc.stderr == "", proc.stderr
    assert not (tmp_path / "stub-called").exists()


def test_a_script_write_holding_korean_still_reaches_sci_adk(tmp_path):
    proc = _run_gate(_write(tmp_path, "fit.py", KOREAN_COMMENT_SCRIPT), tmp_path,
                     sci_adk_cmd=str(_stub(tmp_path, _RECORDING_STUB)))
    assert proc.returncode == 0
    assert (tmp_path / "stub-called").exists()


def test_a_script_under_a_home_directory_outside_ascii_is_still_judged(tmp_path):
    home = tmp_path / ("d" + HAN)
    home.mkdir()
    proc = _run_gate(_write(home, "fit.py", KOREAN_COMMENT_SCRIPT), home)
    assert proc.returncode == 2, proc.stderr


def test_the_hook_s_document_extensions_are_none_the_rule_covers():
    from sci_adk.loop.ascii_scripts import is_ascii_script

    m = re.search(r'^doc_exts="([^"]*)"', GATE.read_text(encoding="utf-8"), re.M)
    assert m is not None, "the hook lists the document extensions it lets through at once"
    exts = m.group(1).split()
    assert {"md", "csv", "json", "tex", "lean"} <= set(exts)
    covered = [e for e in exts if is_ascii_script("x." + e, b"#!")]
    assert covered == [], covered


# -- 3. one prefix for the recorded-script advisory ---------------------------------------------

def _advisory_lines(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if "non-ASCII" in line]


def test_the_recorded_script_advisory_has_one_prefix_with_or_without_a_contract(tmp_path, capsys):
    from sci_adk.core.pubreqs import PubReqs

    from tests.test_english_only_scripts import KOREAN_COMMENT_SCRIPT as SCRIPT

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    without = _seed_recorded_run(tmp_path / "a", "old-run-a", SCRIPT)
    main(["verify", str(without)])
    plain = _advisory_lines(capsys.readouterr().out)
    with_contract = _seed_recorded_run(tmp_path / "b", "old-run-b", SCRIPT)
    (with_contract / "pubreqs.json").write_text(
        PubReqs(spec_id="old-run-b", digest="fixture-digest").model_dump_json(),
        encoding="utf-8")
    main(["verify", str(with_contract)])
    contract = _advisory_lines(capsys.readouterr().out)
    assert plain and contract
    assert {line.split(":", 1)[0] for line in plain + contract} == {"advisory"}, plain + contract


# -- 4. the help text --------------------------------------------------------------------------

def test_the_check_ascii_help_names_the_exit_codes(capsys):
    # check-ascii is internal (round 4): its own --help carries the text.
    with pytest.raises(SystemExit):
        main(["check-ascii", "--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "exits 3" in help_text and "exits 1" not in help_text, help_text
    assert "CHECK_ASCII_BLOCKED" in help_text, help_text


# -- 5. the new hook's timeout is in seconds ------------------------------------------------------

def test_the_pretooluse_hook_timeout_is_in_seconds():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    timeouts = [h["timeout"] for g in data["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert timeouts and all(t <= 120 for t in timeouts), timeouts
