"""The paper session weighs the author's instructions and gives the blind reviewer a turn.

Two defects of the publish workflow, seen on the second trial paper (2026-10-11):

(a) The paper audit's readers and refuters had been told to keep out of `drafts/`, so they
never saw the instructions written there for the writer. They asked for a bootstrap bound
to be printed as 0.0001 although the author's note said to print 0.00, because the bound
moves with the seed; the writer applied it. Now the orchestrator lists the author's
instruction files by path to every reader, every refuter and the writer; a finding that
conflicts with one is not applied by the writer but goes back to the orchestrator, who
keeps the instruction or asks the user, and the outcome is written in the audit file.

(b) The blind conclusions reviewer ran after the last revision, so its notes on the
opening had no turn to be addressed. Now it runs after the final audit-driven revision;
when it reads a conclusion differently from its declaration or notes anything, the writer
gets one more pass on those notes only, and the reviewer runs once more.

These tests pin the workspace templates. Nothing here reaches the engine: both guards stay
advisory and `sci-adk verify`'s exit code stays the verdict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import sci_adk

_KIT = Path(sci_adk.__file__).parent / "templates" / "research-workspace" / ".claude"
_PUBLISH = _KIT / "skills" / "science-workflow-publish" / "SKILL.md"
_HUB = _KIT / "skills" / "sci" / "SKILL.md"
_AUDITOR = _KIT / "agents" / "evaluator-paper.md"
_REVIEWER = _KIT / "agents" / "evaluator-conclusions.md"
_WRITER = _KIT / "agents" / "expert-writer.md"
_STYLE = _KIT / "output-styles" / "science-orchestrator" / "science-orchestrator.md"

_AUDIT_SPAWN = 'Agent(subagent_type: "evaluator-paper")'
_REVIEW_SPAWN = 'Agent(subagent_type: "evaluator-conclusions")'

# (a) -- what the author instructions are, said the same way in the hub and the skill
_INSTRUCTIONS = (
    "the author instructions are the files the orchestrator or the user wrote for the "
    "writer in `drafts/<spec-id>/paper/`"
)
_NOT_AUDITS = "not the audit files, which are other readers' findings"
_LISTED = "list each one by path in every reader's and every refuter's prompt"
_WEIGHED = "weigh them as instructions"
_NO_KEEP_OUT = "never tell a reader or refuter to keep out of `drafts/`"
_NOT_APPLIED = "a finding that conflicts with an author instruction is not applied by the writer"
_DECIDED = "keeps the instruction or asks the user with `askuserquestion`"
_RECORDED = "records the outcome against the finding in the audit file"

# (b) -- the reviewer's place and its one turn, said the same way in the hub and the skill
_AFTER_AUDIT = "after the final audit-driven revision"
_DISAGREE = "readings that disagree"
_ONE_PASS = "one more pass on those notes only"
_ONCE_MORE = "re-run the reviewer once"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Whitespace-normalised and lower-cased, so a phrase may wrap across lines."""
    return " ".join(text.split()).lower()


def _md_section(text: str, heading: str) -> str:
    """The body of the `## <heading>` section, up to the next level-2 heading."""
    return text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]


_HEADING = re.compile(r"^#{2,4} ")
_STEP_START = re.compile(r"^(?:#{2,4} |\d+\. )")


def _heading_section(text: str, needle: str) -> str:
    """The heading section holding the first line that contains `needle`."""
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if needle in line)
    start = max(i for i in range(at + 1) if _HEADING.match(lines[i]))
    end = next((i for i in range(at + 1, len(lines)) if _HEADING.match(lines[i])),
               len(lines))
    return "\n".join(lines[start:end])


def _step(text: str, needle: str) -> str:
    """The heading section or top-level numbered step holding the first `needle` line."""
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if needle in line)
    start = max(i for i in range(at + 1) if _STEP_START.match(lines[i]))
    end = next((i for i in range(at + 1, len(lines)) if _STEP_START.match(lines[i])),
               len(lines))
    return "\n".join(lines[start:end])


def _json_example(section: str) -> dict:
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match, "section has no json example"
    return json.loads(match.group(1))


# --------------------------------------------------------------------------- #
# (a) the author's instructions reach every reader, refuter and the writer
# --------------------------------------------------------------------------- #

def test_the_audit_lists_the_author_instructions_to_every_reader_and_refuter():
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_heading_section(_read(doc), _AUDIT_SPAWN))
        for phrase in (_INSTRUCTIONS, _NOT_AUDITS, _LISTED, _WEIGHED, _NO_KEEP_OUT):
            assert phrase in flat, f"{doc.parent.name}: missing '{phrase}'"


def test_no_reader_or_refuter_is_told_to_keep_out_of_drafts():
    """The trial's instruction that hid the author's notes must not come back."""
    keep_out = re.compile(
        r"(?:do not|don't|never|must not)\s+(?:read|open|look (?:in|at))\b[^.]*drafts/",
        re.IGNORECASE)
    for doc in (_PUBLISH, _HUB, _AUDITOR):
        hits = keep_out.findall(" ".join(_read(doc).split()))
        assert not hits, f"{doc.name}: {hits}"


def test_the_auditor_reads_the_author_instructions_it_is_given():
    text = _read(_AUDITOR)
    reads = _flat(_md_section(text, "What I Read"))
    assert "author instructions" in reads
    assert "drafts/<spec-id>/paper/" in reads
    assert "only the files the orchestrator lists by path" in reads
    assert _WEIGHED in reads
    # the refuters weigh them too: an instruction's reason can refute a finding
    assert "author instruction" in _flat(_md_section(text, "Refute Mode"))


def test_a_finding_names_the_author_instruction_it_conflicts_with():
    text = _read(_AUDITOR)
    example = _json_example(_md_section(text, "Return Contract"))
    for finding in example["findings"]:
        assert "conflicts_with" in finding, finding["id"]
    carry = _flat(_md_section(text, "What A Finding Must Carry"))
    assert "**conflicts_with**" in carry


def test_a_conflicting_finding_goes_to_the_orchestrator_and_its_outcome_to_the_file():
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_heading_section(_read(doc), _AUDIT_SPAWN))
        for phrase in (_NOT_APPLIED, _DECIDED, _RECORDED):
            assert phrase in flat, f"{doc.parent.name}: missing '{phrase}'"


def test_the_writer_takes_the_author_instructions_and_returns_a_conflict_unapplied():
    text = _read(_WRITER)
    contract = _flat(_md_section(text, "Input Contract"))
    assert "author instructions" in contract
    assert "drafts/<spec-id>/paper/" in contract
    assert "do not apply it: return it as a conflict" in contract
    returned = _flat(_md_section(text, "Return Contract"))
    assert "a conflict" in returned and "instruction" in returned
    # the writer cannot ask the user; the orchestrator does
    assert "askuserquestion" not in _flat(text)


# --------------------------------------------------------------------------- #
# (b) the blind reviewer reads the final text, and its notes get one turn
# --------------------------------------------------------------------------- #

def test_the_conclusions_reviewer_is_spawned_after_the_audit():
    for doc in (_PUBLISH, _HUB):
        text = _read(doc)
        assert _REVIEW_SPAWN in text, doc.parent.name
        assert text.index(_AUDIT_SPAWN) < text.index(_REVIEW_SPAWN), (
            f"{doc.parent.name}: the reviewer is spawned before the audit")


def test_the_reviewer_step_runs_after_the_final_revision_and_gives_its_notes_a_turn():
    # the skill gives the reviewer its own section; the hub, one numbered step
    for doc, scope in ((_PUBLISH, _heading_section), (_HUB, _step)):
        flat = _flat(scope(_read(doc), _REVIEW_SPAWN))
        for phrase in (_AFTER_AUDIT, _DISAGREE, "`opening_notes`", _ONE_PASS, _ONCE_MORE):
            assert phrase in flat, f"{doc.parent.name}: missing '{phrase}'"
        # still blind: the step never hands it the declared statuses
        assert "declarations.json" in flat and "never" in flat


def test_the_reviewer_is_no_longer_run_before_the_audit():
    """The old order ran it on the first render and again only if a conclusion changed."""
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_read(doc))
        assert "if any declared sentence or the opening changed" not in flat, doc.parent.name
    assert "optionally `agent(subagent_type: \"evaluator-conclusions\")`" not in _flat(
        _read(_HUB))


def test_the_writer_takes_the_reviewers_notes_as_input_for_one_pass():
    contract = _flat(_md_section(_read(_WRITER), "Input Contract"))
    for phrase in ("`opening_notes`", _DISAGREE, _ONE_PASS):
        assert phrase in contract, f"expert-writer input contract: missing '{phrase}'"


def test_the_reviewer_and_the_persona_state_the_same_order():
    description = _flat(re.match(r"---\n(.*?)\n---\n", _read(_REVIEWER), re.DOTALL)
                        .group(1))
    assert _AFTER_AUDIT in description
    assert "after the writer has rendered and declared" not in description
    note = _flat(_read(_STYLE).split("## 5. Guard Catalog", 1)[1].split("\n## ", 1)[0])
    assert _AFTER_AUDIT in note
    assert "once the writer has rendered the paper" not in note
