"""
The paper audit reads the study the paper reports, not only its words and claims.

The audit's six lenses read numbers, verbs, proportion, vocabulary, results and structure.
None asked whether the paper poses one question from title to conclusion, whether its
introduction shows the gap it claims (with the works the run's own searches acquired),
whether exploratory results say so with their n, whether the central claim rests on
evidence thin enough that the author must be told, whether statements about when work was
done match the times the record logged, or whether the deposited code and data follow the
same rules as the text. Nor did any lens catch remarks about how the paper was written left
in its text.

These tests pin the workspace wiring: a seventh lens, `study-and-question`, in the
auditor; the reader-vocabulary lens reading process remarks; a finding field that sends a
problem prose cannot fix to the author; the publish stage spawning the lens and routing
those findings; the writer's own rules; and the design note mapping each rule to where the
kit enforces it. The kit carries the rules itself: no template points at a personal file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import sci_adk

_PKG = Path(sci_adk.__file__).parent
_KIT = _PKG / "templates" / "research-workspace" / ".claude"
_AGENT = _KIT / "agents" / "evaluator-paper.md"
_WRITER = _KIT / "agents" / "expert-writer.md"
_PUBLISH = _KIT / "skills" / "science-workflow-publish" / "SKILL.md"
_HUB = _KIT / "skills" / "sci" / "SKILL.md"
_DESIGN = Path(__file__).resolve().parents[1] / "design" / "reader-facing-prose.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


def _lens(name: str) -> str:
    text = _read(_AGENT)
    return text.split(f"### Lens `{name}`", 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]


def test_the_study_lens_reads_one_question_through_the_paper():
    lens = _flat(_lens("study-and-question"))
    for part in ("title", "first sentence of the abstract", "end of the introduction",
                 "conclusion", "same question"):
        assert part in lens, part
    assert "bears on no question" in lens


def test_the_study_lens_checks_the_gap_against_the_run_literature_store():
    lens = _flat(_lens("study-and-question"))
    assert "known" in lens and "unresolved" in lens and "this work" in lens
    assert "literature/references.bib" in lens
    assert "never cites" in lens
    assert "never propose a citation" in lens
    assert "goes to the author" in lens


def test_the_study_lens_reads_evidence_size_thin_evidence_times_and_deposits():
    lens = _flat(_lens("study-and-question"))
    for word in ("pilot", "exploratory", "post hoc", "its n"):
        assert word in lens, word
    assert "single run" in lens and "no comparison" in lens
    assert "trivial alternative" in lens
    assert "for_author: true" in lens
    assert "logged times" in lens and "not when the work was done" in lens
    for word in ("one canonical file per role", "versioned names", "paper/code/readme.md",
                 "absolute local path"):
        assert word in lens, word


def test_the_vocabulary_lens_reads_process_remarks():
    lens = _flat(_lens("reader-vocabulary"))
    assert "how the paper was written or checked" in lens
    assert "this could not be fully verified" in lens
    assert "never left in the paper" in lens


def test_a_finding_can_be_sent_to_the_author():
    text = _read(_AGENT)
    carries = text.split("## What A Finding Must Carry", 1)[1].split("\n## ", 1)[0]
    assert "**for_author**" in carries
    contract = text.split("## Return Contract", 1)[1].split("## Refute Mode", 1)[0]
    example = json.loads(re.search(r"```json\n(.*?)\n```", contract, re.DOTALL).group(1))
    assert all("for_author" in f for f in example["findings"])


def test_the_auditor_reads_what_the_study_lens_needs():
    reads = _flat(_read(_AGENT).split("## What I Read", 1)[1].split("\n## The Lenses", 1)[0])
    assert "search logs" in reads
    assert "paper/deposit/" in reads


def test_the_blocker_counts_seven_lenses():
    assert "one of the seven above" in _read(_AGENT)


def test_publish_and_hub_route_author_findings_to_the_user():
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_read(doc))
        assert "`study-and-question`" in flat, doc.parent.name
        assert "`for_author`" in flat, doc.parent.name
        assert "for the author" in flat, doc.parent.name
        assert "askuserquestion" in flat, doc.parent.name
        assert "writing cannot fix the study" in flat, doc.parent.name


def test_the_writer_knows_the_study_rules():
    flat = _flat(_read(_WRITER))
    section = _flat(_read(_WRITER).split("## The Study The Paper Reports", 1)[1]
                    .split("\n## ", 1)[0])
    for phrase in ("same question", "known", "pilot", "exploratory", "with its n",
                   "thin", "logged times"):
        assert phrase in section, phrase
    assert "how the paper was written or checked" in section
    assert "paper/code/readme.md" in section and "versioned" in section
    assert "`for_author`" in flat


def test_the_publish_standard_carries_the_study_rules_in_order_of_work():
    text = _read(_PUBLISH)
    section = _flat(text.split("### Report the study the record holds", 1)[1]
                    .split("\n### ", 1)[0])
    for phrase in ("one question", "the gap is shown", "pilot", "thin evidence",
                   "logged times", "deposited code and data"):
        assert phrase in section, phrase
    order = _flat(text.split("**Order of work before render:**", 1)[1].split("\n### ", 1)[0])
    assert "same question" in order and "known" in order and "with its n" in order


def test_the_design_note_maps_each_rule_to_where_it_is_enforced():
    text = _read(_DESIGN)
    section = text.split("## 16. ", 1)[1].split("\n## ", 1)[0]
    flat = _flat(section)
    assert "| rule |" in flat
    for word in ("study-and-question", "paper/code/readme.md", "render", "verify",
                 "for_author", "reader-vocabulary"):
        assert word in flat, word


def test_the_kit_does_not_point_at_a_personal_file():
    for path in _KIT.rglob("*.md"):
        text = _read(path)
        assert "~/.claude/CLAUDE.md" not in text, path
        assert "Writing for readers who were not in the room" not in text, path


def test_the_new_rules_stay_domain_general():
    for path in (_AGENT, _WRITER, _PUBLISH, _HUB):
        low = _read(path).lower()
        for word in ("kow", "bioconcentration", "bcf"):
            assert word not in low, (path.name, word)
