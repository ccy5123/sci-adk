"""The publish skill's compile check.

Two things the trial's paper session hit when compiling ``paper/``:

  - ``bibtex si`` on an SI that cites nothing (render writes no ``\\bibliography`` for it)
    exits with status 2 ("I found no \\bibdata command"), which read as a broken SI. bibtex
    runs for a document only when its ``.aux`` holds a ``\\bibdata`` line.
  - a long ``\\texttt`` run (a checksum, a code call) cannot break and ran into the margin;
    the writer splits it with ``\\allowbreak``.
"""

from __future__ import annotations

import re
from pathlib import Path

import sci_adk

_PUBLISH = (Path(sci_adk.__file__).parent / "templates" / "research-workspace" / ".claude"
            / "skills" / "science-workflow-publish" / "SKILL.md")


def _compile_section() -> str:
    text = _PUBLISH.read_text(encoding="utf-8")
    match = re.search(r"\n### Compile check\n(.*?)(?=\n### |\n## )", text, re.DOTALL)
    assert match, "the publish skill has no '### Compile check' section"
    return match.group(1)


def test_bibtex_runs_only_for_a_document_whose_aux_has_bibdata():
    section = _compile_section()
    flat = " ".join(section.split())
    assert "\\bibdata" in section
    assert "bibtex" in section and ".aux" in section
    assert "exit status 2" in flat or "exits with status 2" in flat
    # the command shown guards bibtex on the \bibdata line (an `if`, so a document without
    # one does not end the shell line with grep's exit status 1)
    assert re.search(r"if grep -q '\\\\bibdata' (\w+)\.aux; then bibtex \1; fi", section), (
        section)


def test_long_texttt_runs_are_split_with_allowbreak():
    flat = " ".join(_compile_section().split())
    assert "\\allowbreak" in flat and "\\texttt" in flat
    assert "margin" in flat
    assert "checksum" in flat and "code call" in flat
