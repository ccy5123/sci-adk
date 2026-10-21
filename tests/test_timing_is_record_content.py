"""
Times, logged-at lists and tool-run details are record content, not paper content.

Decision (user, 2026-10-21): every sentence sci-adk puts into a manuscript is judged by
"would a real paper in this venue contain it, and does it help the reader?". Timestamps,
"logged at" lists, statements of when each step was done and search-failure counts are
what the deposited record (``paper/deposit/record.tex``) carries. A real paper states a
pre-registration in one sentence plus its deviations, where the venue has that norm, and
labels exploratory or post hoc results next to the results, with n.

The workspace kit used to tell the writer the opposite: state every time "as a recorded
time", with an example SI sentence giving the protocol's creation time to the second. These
tests pin the new instructions in the writer, the publish and package skills and the paper
audit, and the one place the design states the principle.
"""

from __future__ import annotations

from pathlib import Path

import sci_adk

_PKG = Path(sci_adk.__file__).parent
_KIT = _PKG / "templates" / "research-workspace" / ".claude"
_AGENT = _KIT / "agents" / "evaluator-paper.md"
_WRITER = _KIT / "agents" / "expert-writer.md"
_PUBLISH = _KIT / "skills" / "science-workflow-publish" / "SKILL.md"
_PACKAGE = _KIT / "skills" / "science-workflow-package" / "SKILL.md"
_DESIGN = Path(__file__).resolve().parents[1] / "design" / "reader-facing-prose.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


def _between(text: str, start: str, *ends: str) -> str:
    assert start in text, start
    body = text.split(start, 1)[1]
    for end in ends:
        body = body.split(end, 1)[0]
    return body


def _lens(name: str) -> str:
    return _flat(_between(_read(_AGENT), f"### Lens `{name}`", "\n### ", "\n## "))


# The instructions that told the writer to put times into the paper.
_OLD_TIMING_RULES = (
    "state every time as a recorded time",
    "write each as a recorded time",
    "times are logged times",
    "times are recorded times",
    'say "recorded at"',
    "claim no order the recorded times do not show",
    "when things happened",
)


def test_no_template_tells_the_writer_to_state_times():
    for path in sorted(_KIT.rglob("*.md")):
        flat = _flat(_read(path))
        for rule in _OLD_TIMING_RULES:
            assert rule not in flat, (path.relative_to(_KIT), rule)


def test_no_template_example_gives_a_timestamp_for_the_paper():
    # A date-time to the second inside an example paper sentence is record content.
    for path in (_WRITER, _PUBLISH, _PACKAGE):
        for line in _read(path).splitlines():
            if line.startswith(">"):
                assert "T10:03:39Z" not in line and "T14:05:17Z" not in line, (path.name, line)


# --------------------------------------------------------------------------- #
# the paper audit
# --------------------------------------------------------------------------- #

def test_the_study_lens_checks_pre_specified_claims_against_the_frozen_protocol():
    lens = _lens("study-and-question")
    assert "pre-specified" in lens
    assert "frozen protocol" in lens and "spec.json" in lens
    assert "post hoc" in lens


def test_the_study_lens_reports_timestamps_and_tool_runs_as_a_machinery_leak():
    lens = _lens("study-and-question")
    for phrase in ("timestamps", '"logged at"', "when each step was done", "tool",
                   "machinery leak", "deposit/record.tex"):
        assert phrase in lens, phrase


def test_the_study_lens_holds_a_pre_registration_statement_to_one_sentence():
    lens = _lens("study-and-question")
    assert "pre-registration statement" in lens
    assert "one sentence" in lens and "deviation" in lens


def test_the_study_lens_labels_post_hoc_results_next_to_the_result_with_n():
    lens = _lens("study-and-question")
    assert "added after the results were known" in lens
    assert "next to" in lens and "its n" in lens


def test_the_vocabulary_lens_reads_timestamps_and_tool_runs_as_machinery():
    lens = _lens("reader-vocabulary")
    for phrase in ("timestamps", '"logged at"', "when each step was done", "tool",
                   "deposit/record.tex"):
        assert phrase in lens, phrase


# --------------------------------------------------------------------------- #
# the writer and the publish skill
# --------------------------------------------------------------------------- #

def _writer_study() -> str:
    return _flat(_between(_read(_WRITER), "## The Study The Paper Reports", "\n## "))


def _publish_study() -> str:
    return _flat(_between(_read(_PUBLISH), "### Report the study the record holds", "\n### "))


def test_the_writer_and_the_publish_skill_carry_the_four_rules():
    for name, section in (("writer", _writer_study()), ("publish", _publish_study())):
        # (a) no times in the paper; the deposited record carries them
        for phrase in ("timestamps", '"logged at"', "when each step was done",
                       "deposited record"):
            assert phrase in section, (name, phrase)
        # (b) exploratory / post hoc next to the result, with n
        assert "added after the results were known" in section, name
        assert "post hoc" in section and "with its n" in section, name
        # (c) "pre-specified" only when the frozen protocol holds it
        assert "pre-specified" in section and "frozen protocol" in section, name
        # (d) a pre-registration statement where the venue expects one
        assert "pre-registration statement" in section, name
        assert "one sentence" in section and "deviation" in section, name


def test_the_publish_order_of_work_deletes_times():
    order = _flat(_between(_read(_PUBLISH), "**Order of work before render:**", "\n### "))
    assert "timestamps" in order and "pre-specified" in order


def test_the_deposit_guidance_points_to_the_record_for_times():
    writer = _flat(_between(_read(_WRITER), "## Deposit Files", "\n## "))
    publish = _flat(_between(_read(_PUBLISH), "### Deposit files", "\n### "))
    for name, section in (("writer", writer), ("publish", publish)):
        assert "deposit/record.tex" in section, name
        assert "states no times" in section, name


def test_the_package_skill_points_to_the_record_for_times():
    section = _flat(_between(_read(_PACKAGE), "### Naming files and checksums in the merged "
                                              "manuscript", "\n### "))
    assert "06_provenance/record.tex" in section
    assert "timestamps" in section and "states no times" in section


def test_the_novelty_guidance_no_longer_promises_counts_in_the_paper():
    for path in (_WRITER, _PUBLISH):
        flat = _flat(_read(path))
        assert "how many of how many" not in flat, path.name
        assert "the queries and their outcomes" in flat, path.name


# --------------------------------------------------------------------------- #
# the design states the principle once
# --------------------------------------------------------------------------- #

def test_the_design_states_the_principle_in_section_16():
    section = _flat(_between(_read(_DESIGN), "## 16. ", "\n## "))
    assert "would a real paper in this venue contain it" in section
    assert "record content" in section
    for phrase in ("timestamps", '"logged at"', "pre-specified", "one sentence",
                   "deviation", "added after the results were known"):
        assert phrase in section, phrase
    rows = [r for r in section.split("|") if "times" in r]
    assert not any("times are logged times" in r for r in rows), rows
