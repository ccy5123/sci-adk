"""The workspace publish skill describes the SI as it is rendered now.

SPEC-SI-AUTHORING-001 split the old SI in two: ``paper/si.tex`` is AUTHORED (an
``AuthoredSI`` JSON passed as ``sci-adk render --si``; no ``--si``, no si.tex) and the
deterministic record dump is the deposit ``runs/<id>/record.tex``. The template the
writer reads still said the SI was "the full record, auto-dumped", which tells a writer
not to author it.
"""

from __future__ import annotations

from pathlib import Path

import sci_adk

_PUBLISH = (Path(sci_adk.__file__).parent / "templates" / "research-workspace" / ".claude"
            / "skills" / "science-workflow-publish" / "SKILL.md")


def _text() -> str:
    return _PUBLISH.read_text(encoding="utf-8")


def test_publish_skill_no_longer_calls_the_si_a_record_dump():
    text = _text()
    for stale in (
        "auto-dumped",
        "auto record-dump",
        "SI = the full record",
        "the SI is the deterministic dump of the record",
        "The SI is the deterministic record dump",
    ):
        assert stale not in text, f"stale SI description still present: {stale!r}"


def test_publish_skill_render_tree_shows_an_authored_si_and_the_deposited_record():
    text = _text()
    tree_line = next(line for line in text.splitlines() if line.startswith("├── si.tex"))
    assert "authored" in tree_line.lower()
    assert "--si" in tree_line
    assert "runs/<id>/record.tex" in text.split("### Render", 1)[1].split("###", 1)[0]


def test_publish_skill_names_the_authored_si_hook():
    text = _text()
    hooks = text.split("### Author the hooks", 1)[1].split("###", 1)[0]
    assert "`AuthoredSI`" in hooks
    assert "`--si si.json`" in hooks
    # SIProse wraps the deposited record dump, not the submitted SI
    siprose = next(line for line in hooks.splitlines() if "**`SIProse`**" in line)
    assert "record.tex" in siprose
