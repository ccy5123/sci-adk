"""The workspace templates describe the SI and the numbers list as they work now.

SPEC-SI-AUTHORING-001 made ``paper/si.tex`` an AUTHORED document, written only when
``sci-adk render`` is given ``--si si.json``; the deterministic record dump is deposited as
``runs/<id>/record.tex``, outside the submission. Several templates still said "the SI is
the FULL RECORD auto-dumped" or listed ``paper/{draft.tex, si.tex, ...}`` as what every
render writes, which tells a writer not to author the SI. The publish skill is pinned in
``tests/test_publish_skill_si.py``; this file pins the agent, hub, foundation skill,
output style and command that describe the same render.

The declared-numbers tokenizer reads ``\\texttt`` as prose (a seed or a size written as
code is a number the paper states), and ``numbers draft`` reads ``--si`` so the SI's
literals are proposed too; the writer guidance has to say both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sci_adk

_WS = Path(sci_adk.__file__).parent / "templates" / "research-workspace"
_WRITER = _WS / ".claude" / "agents" / "expert-writer.md"
_PUBLISH = _WS / ".claude" / "skills" / "science-workflow-publish" / "SKILL.md"
_RENDER_DESCRIBERS = {
    "expert-writer": _WRITER,
    "sci hub": _WS / ".claude" / "skills" / "sci" / "SKILL.md",
    "foundation-rigor": _WS / ".claude" / "skills" / "science-foundation-rigor" / "SKILL.md",
    "orchestrator": (_WS / ".claude" / "output-styles" / "science-orchestrator"
                     / "science-orchestrator.md"),
}
_PUBLISH_COMMAND = _WS / ".claude" / "commands" / "sci" / "publish.md"

_LIST_ITEM = re.compile(r"^\s*(?:\d+\.|[-*])\s")


def _templates() -> list[Path]:
    return sorted(_WS.rglob("*.md"))


def _blocks(text: str) -> list[str]:
    """Paragraphs, with each list item and each table row a block of its own."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        starts_new = (not line.strip() or line.lstrip().startswith("|")
                      or _LIST_ITEM.match(line) is not None)
        if starts_new and current:
            blocks.append(current)
            current = []
        if line.strip():
            current.append(line)
            if line.lstrip().startswith("|"):
                blocks.append(current)
                current = []
    if current:
        blocks.append(current)
    return ["\n".join(b) for b in blocks]


def _section(text: str, heading: str) -> str:
    level = heading.split(" ", 1)[0]
    body = text.split(heading, 1)[1]
    return re.split(rf"\n{level} ", body, maxsplit=1)[0]


# -- the SI is authored; the record dump is deposited ----------------------------------


def test_no_template_calls_the_si_the_record_dump():
    for path in _templates():
        text = path.read_text(encoding="utf-8").lower()
        for stale in ("full record auto", "auto-dumped", "the si is the full record"):
            assert stale not in text, f"{path.relative_to(_WS)}: {stale!r}"


def test_no_template_lists_si_tex_as_written_by_every_render():
    for path in _templates():
        text = path.read_text(encoding="utf-8")
        assert "paper/{draft.tex, si.tex" not in text, path.relative_to(_WS)


@pytest.mark.parametrize("name", sorted(_RENDER_DESCRIBERS))
def test_render_descriptions_say_the_si_is_authored_and_the_record_deposited(name):
    text = _RENDER_DESCRIBERS[name].read_text(encoding="utf-8")
    described = [b for b in _blocks(text) if "sci-adk render" in b and "si.tex" in b]
    assert described, f"{name}: no render description names si.tex"
    for block in described:
        assert "--si" in block, f"{name}: si.tex without --si:\n{block}"
        assert "runs/<id>/record.tex" in block, f"{name}: no record deposit:\n{block}"


def test_the_writer_is_told_it_authors_the_si():
    discipline = _section(_WRITER.read_text(encoding="utf-8"),
                          "## The Discipline (record vs belief)")
    first = _blocks(discipline)[0]
    assert "author" in first.lower()
    assert "si.tex" in first and "--si" in first
    assert "runs/<id>/record.tex" in first


def test_the_publish_command_describes_the_authored_si():
    text = _PUBLISH_COMMAND.read_text(encoding="utf-8")
    description = next(line for line in text.splitlines() if line.startswith("description:"))
    assert "--si" in description
    assert "record.tex" in description


# -- the numbers guidance: \texttt literals and the SI ---------------------------------

_NUMBER_SECTIONS = {
    "expert-writer": (_WRITER, "## Numbers — Declared Beside the Paper"),
    "publish skill": (_PUBLISH, "### Declare the numbers beside the paper"),
}


@pytest.mark.parametrize("name", sorted(_NUMBER_SECTIONS))
def test_numbers_guidance_covers_numbers_written_in_texttt(name):
    path, heading = _NUMBER_SECTIONS[name]
    section = _section(path.read_text(encoding="utf-8"), heading)
    blocks = [b for b in _blocks(section) if "\\texttt" in b]
    assert blocks, f"{name}: the numbers section never mentions \\texttt"
    block = " ".join(blocks).lower()
    for word in ("seed", "size", "timestamp", "hash", "identifier"):
        assert word in block, f"{name}: {word!r} missing from the \\texttt guidance"


@pytest.mark.parametrize("name", sorted(_NUMBER_SECTIONS))
def test_numbers_guidance_says_numbers_draft_reads_the_si(name):
    path, heading = _NUMBER_SECTIONS[name]
    section = _section(path.read_text(encoding="utf-8"), heading)
    blocks = [b for b in _blocks(section) if "numbers draft" in b and "--si" in b]
    assert blocks, f"{name}: numbers draft is never shown with --si"
    assert any("si.tex" in b and "propos" in b for b in blocks), (
        f"{name}: it does not say --si makes numbers draft propose the SI's literals"
    )


# -- the repository README and the publishing design describe the same render -----------

_REPO = Path(sci_adk.__file__).resolve().parents[2]
_README = _REPO / "README.md"
_PUBREQS_DESIGN = _REPO / "design" / "paper-publishing-requirements.md"


@pytest.mark.parametrize("path", [_README, _PUBREQS_DESIGN], ids=["README", "pubreqs-design"])
def test_no_repository_document_calls_the_si_the_record_dump(path):
    text = " ".join(path.read_text(encoding="utf-8").split()).lower()
    for stale in ("auto-record-dump", "si record dump", "si record-dump", "auto-dumped",
                  "the si is the full record", "the si remains the exempt record dump",
                  "the si is the exempt record dump"):
        assert stale not in text, f"{path.name}: {stale!r}"


def test_the_readme_feature_list_says_the_si_is_authored_and_the_record_deposited():
    bullets = [b for b in _blocks(_README.read_text(encoding="utf-8"))
               if b.lstrip().startswith("- **Paper figures + SI**")]
    assert len(bullets) == 1
    assert "--si" in bullets[0] and "runs/<id>/record.tex" in bullets[0], bullets[0]
