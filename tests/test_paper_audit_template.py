"""The independent multi-lens paper audit is a step of the publish stage.

A paper can pass every machine check -- every number traces to the record, every
declared conclusion matches its recorded status -- and still mislead: a recorded count
in a sentence that misnames what was counted, a pre-registered band described as
something it is not, an interpretation that leaves out a pre-registered test. No check
reads meaning. Independent readers, each with one lens and each finding challenged by
refuters, did. These tests pin the workspace wiring of that audit: a read-only agent
with its lenses and a refute mode, run by the orchestrator after `verify` passes, its
surviving findings written for the writer, and nothing in the engine reading any of it.
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
_STYLE = _KIT / "output-styles" / "science-orchestrator" / "science-orchestrator.md"
_README = Path(__file__).resolve().parents[1] / "README.md"

_AUDIT_PATH = "drafts/<spec-id>/paper/audit-<date>.md"
_SPAWN = 'Agent(subagent_type: "evaluator-paper")'
# who runs the audit, stated once and identically in the hub and the publish skill: a
# worker cannot spawn agents, so the readers and refuters are the orchestrator's.
_OWNER = "the session driving `/sci publish`"
_OWNERSHIP = (
    "the session driving `/sci publish` (the orchestrator) spawns the readers and "
    "refuters and writes the audit file"
)
_WRITER_ROLE = "the writer only revises from the audit file"
_LENSES = [
    "number-sources",
    "claims-vs-design",
    "position-and-proportion",
    "reader-vocabulary",
    "result-fidelity",
    "structure-and-methods",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "agent template has no YAML frontmatter"
    return match.group(1)


def _lenses(agent_text: str) -> list[str]:
    return re.findall(r"^### Lens `([a-z-]+)`", agent_text, re.MULTILINE)


def _json_example(section: str) -> dict:
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match, "section has no json example"
    return json.loads(match.group(1))


def _flat(text: str) -> str:
    """Whitespace-normalised and lower-cased, so a phrase may wrap across lines."""
    return " ".join(text.split()).lower()


_STEP_START = re.compile(r"^(?:#{2,4} |\d+\. )")
_HEADING = re.compile(r"^#{2,4} ")
_BLOCK_START = re.compile(r"^\s*(?:\d+\.|[-*])\s")


def _spawn_section(text: str) -> str:
    """The whole heading section (not just the numbered step) that spawns the auditor."""
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if _SPAWN in line)
    start = max(i for i in range(at + 1) if _HEADING.match(lines[i]))
    end = next((i for i in range(at + 1, len(lines)) if _HEADING.match(lines[i])),
               len(lines))
    return "\n".join(lines[start:end])


def _md_section(text: str, heading: str) -> str:
    """The body of the `## <heading>` section, up to the next level-2 heading."""
    return text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]


def _spawn_step(text: str) -> str:
    """The heading section or top-level numbered step whose text spawns the auditor."""
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if _SPAWN in line)
    start = max(i for i in range(at + 1) if _STEP_START.match(lines[i]))
    end = next((i for i in range(at + 1, len(lines)) if _STEP_START.match(lines[i])),
               len(lines))
    return "\n".join(lines[start:end])


def _blocks(text: str) -> list[str]:
    """Paragraphs and list items (nested ones on their own), headings dropped."""
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        heading_or_blank = not line.strip() or line.startswith("#")
        if heading_or_blank or _BLOCK_START.match(line):
            if current:
                blocks.append(" ".join(current))
            current = []
            if heading_or_blank:
                continue
        current.append(line.strip())
    if current:
        blocks.append(" ".join(current))
    return blocks


def test_the_paper_auditor_can_read_but_cannot_change_anything():
    front = _frontmatter(_read(_AGENT))
    assert re.search(r"^name: evaluator-paper$", front, re.MULTILINE)
    granted = {t.strip() for t in re.search(r"^tools: (.*)$", front, re.MULTILINE)
               .group(1).split(",")}
    assert {"Read", "Grep", "Glob"} <= granted
    # no write path, and no shell: a value computed in the audit is not in the record
    assert not granted & {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}


def test_the_auditor_reads_through_exactly_the_six_lenses():
    assert _lenses(_read(_AGENT)) == _LENSES


def test_every_lens_is_spawned_by_the_publish_stage():
    """A lens the agent defines but the orchestrator never spawns is never read."""
    lenses = _lenses(_read(_AGENT))
    for doc in (_PUBLISH, _HUB):
        text = _read(doc)
        missing = [lens for lens in lenses if f"`{lens}`" not in text]
        assert not missing, f"{doc.parent.name} never spawns lens(es) {missing}"


def test_each_lens_is_named_in_the_step_that_spawns_the_auditor():
    """A lens named only elsewhere in the skill is not one the spawning step reads."""
    lenses = _lenses(_read(_AGENT))
    for doc in (_PUBLISH, _HUB):
        step = _spawn_step(_read(doc))
        missing = [lens for lens in lenses if f"`{lens}`" not in step]
        assert not missing, f"{doc.parent.name}: spawn step omits lens(es) {missing}"


def test_the_hub_and_the_publish_skill_agree_who_runs_the_audit():
    """The orchestrator spawns the readers and refuters; the writer only revises.

    Both documents once disagreed: each assigned the spawning to the orchestrator in one
    place and, in another, listed the audit as a step of the paper session or the writer
    -- which a worker reading its own instructions cannot carry out. Every passage that
    mentions the paper audit must now name who runs it.
    """
    for doc in (_PUBLISH, _HUB):
        text = _read(doc)
        assert _OWNERSHIP.lower() in _flat(text), doc.parent.name
        assert _WRITER_ROLE in _flat(text), doc.parent.name
        unowned = [b for b in _blocks(text)
                   if "paper audit" in b.lower() and _OWNER.lower() not in b.lower()]
        assert not unowned, f"{doc.parent.name}: audit mentioned without its owner: {unowned}"


def test_no_worker_is_told_to_spawn_the_auditor():
    for agent in sorted((_KIT / "agents").glob("*.md")):
        assert _SPAWN not in _read(agent), agent.name


def test_the_audit_bounds_how_many_agents_it_spawns():
    """No refuters for an empty lens, waves of about ten, once per publish session."""
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_read(doc))
        for phrase in (
            "a lens that returns no findings gets no refuters",
            "in waves of at most about 10 agents at a time",
            "split into index ranges counts as one lens",
            "the full audit runs once per publish session",
            "only the lenses whose findings were fixed",
        ):
            assert phrase in flat, f"{doc.parent.name}: missing '{phrase}'"


def _guard_agents() -> list[str]:
    return sorted(p.stem for p in (_KIT / "agents").glob("evaluator-*.md"))


def test_every_guard_agent_is_in_the_persona_guard_catalog():
    catalog = _read(_STYLE).split("## 5. Guard Catalog", 1)[1].split("\n## ", 1)[0]
    for guard in _guard_agents():
        row = next((line for line in catalog.splitlines()
                    if line.startswith(f"| `{guard}` |")), None)
        assert row, f"guard {guard} missing from the persona's guard catalog"
        assert "No (advisory)" in row, guard


def test_every_guard_agent_is_in_the_readme_agent_list():
    readme = _read(_README)
    guards = readme.split("- **Guard agents**", 1)[1].split("\n- **", 1)[0]
    missing = [g for g in _guard_agents() if f"`{g}`" not in guards]
    assert not missing, f"README guard-agent list omits {missing}"


def test_a_finding_carries_its_quote_evidence_severity_and_fix():
    section = _read(_AGENT).split("## Return Contract", 1)[1].split("## Refute Mode", 1)[0]
    example = _json_example(section)
    assert example["lens"] in _LENSES
    assert example["findings"], "the example shows no finding"
    for finding in example["findings"]:
        assert {"id", "severity", "document", "location", "quote", "issue",
                "evidence", "fix"} <= set(finding)
        assert finding["severity"] in {"major", "minor"}


def test_the_auditor_can_be_asked_to_refute_a_finding():
    refute = _read(_AGENT).split("## Refute Mode", 1)[1].split("\n## ", 1)[0]
    example = _json_example(refute)
    assert example["mode"] == "refute"
    judgements = {j["judgement"] for j in example["judgements"]}
    assert judgements <= {"upheld", "refuted"} and judgements
    for judgement in example["judgements"]:
        assert {"id", "judgement", "reason"} <= set(judgement)


def test_publish_runs_the_audit_after_verify_and_keeps_verify_the_verdict():
    for doc in (_PUBLISH, _HUB):
        text = _read(doc)
        assert 'Agent(subagent_type: "evaluator-paper")' in text, doc.parent.name
        assert _AUDIT_PATH in text, doc.parent.name
        assert "after `sci-adk verify` passes" in text, doc.parent.name
        assert "a majority of its refuters" in text, doc.parent.name
        assert "The audit is advisory" in text, doc.parent.name
        assert "remains the verdict" in text, doc.parent.name
        # a fix that needs an unrecorded number goes back, never into numbers.json
        assert "back to the experiment stage" in text, doc.parent.name


def test_the_audit_never_reaches_the_verdict_path():
    """No engine change: the installer copies the agent and nothing else names it."""
    readers = sorted(p.name for p in _PKG.rglob("*.py")
                     if "evaluator-paper" in p.read_text(encoding="utf-8"))
    assert readers == ["init_session.py"]


def test_a_split_number_sources_lens_has_a_range_size_and_unique_finding_ids():
    """Ranges of about 25 entries; each range reader numbers under its own id prefix.

    Several range readers each numbering from 1 would pool findings with clashing ids,
    and a refuter's judgement could no longer be traced to one finding.
    """
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_spawn_section(_read(doc)))
        assert "about 25 entries each" in flat, doc.parent.name
        assert "number-sources-r2-<n>" in flat, doc.parent.name
    contract = _md_section(_read(_AGENT), "Return Contract")
    assert "number-sources-r2-<n>" in contract


def test_a_revision_that_touches_the_conclusions_reruns_the_conclusions_reader():
    """The blind reading was of the old text; a rewritten conclusion was never read."""
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_spawn_section(_read(doc)))
        assert "re-run `evaluator-conclusions`" in flat, doc.parent.name
        assert "if any declared sentence or the opening changed" in flat, doc.parent.name


def test_the_audit_procedure_ends_and_keeps_every_file_and_open_finding():
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_spawn_section(_read(doc)))
        for phrase in (
            # a same-day re-run is a new file, never an overwrite of the first
            "drafts/<spec-id>/paper/audit-<date>-2.md",
            "never overwriting",
            # the re-run is the last round
            "go to the writer once, and then the audit ends",
            # silence, a blocker or a missing judgement is not an uphold
            "a refuter that returns nothing usable counts as not upholding",
            # what the writer did not fix is not dropped from the file
            "stay listed in the audit file as open",
        ):
            assert phrase in flat, f"{doc.parent.name}: missing '{phrase}'"


def test_the_audit_reads_the_merged_manuscript_and_hands_the_worktree_writer_the_file():
    """The writer runs in its own worktree: neither side may read the other's stale copy."""
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_spawn_section(_read(doc)))
        assert "after the writer's output is merged back" in flat, doc.parent.name
        assert "the audit file's content or its absolute path" in flat, doc.parent.name


def test_the_writer_knows_what_to_do_with_an_audit_file():
    text = _read(_WRITER)
    assert "audit file" in _md_section(text, "Input Contract").lower()
    duties = _flat(_md_section(text, "Blocker Protocol") + _md_section(text, "Success Criteria"))
    assert "at the strength the record supports without adding a hedge" in duties
    assert "returned as a blocker for the experiment stage" in duties


def test_the_hub_verdict_rule_names_every_guard_as_advisory():
    rule = _md_section(_read(_HUB), "The Verdict Rule")
    missing = [g for g in _guard_agents() if f"`{g}`" not in rule]
    assert not missing, f"the Verdict Rule omits guard(s) {missing}"
    assert "ADVISORY" in rule


def test_the_paper_session_spawns_the_writer_and_runs_the_audit_itself():
    """Session B is the top-level session; the writer it spawns authors, it audits."""
    for doc in (_PUBLISH, _HUB):
        flat = _flat(_read(doc))
        assert "new top-level session" in flat, doc.parent.name
        assert "spawns `expert-writer` to author the paper" in flat, doc.parent.name
        assert "runs the audit itself" in flat, doc.parent.name
    # the old wording left "you" ambiguous between the session and the writer
    assert "if you are the paper session" not in _flat(_read(_PUBLISH))


def _worker_agents() -> list[str]:
    return sorted(p.stem for p in (_KIT / "agents").glob("*.md")
                  if not p.stem.startswith("evaluator-"))


def test_every_worker_agent_is_in_the_persona_worker_catalog():
    catalog = _read(_STYLE).split("## 4. Delegation", 1)[1].split("\n## ", 1)[0]
    rows = catalog.splitlines()
    missing = [w for w in _worker_agents()
               if not any(row.startswith(f"| `{w}` |") for row in rows)]
    assert not missing, f"persona worker catalog omits {missing}"


def test_every_worker_agent_is_in_the_readme_agent_list():
    readme = _read(_README)
    workers = readme.split("- **Worker agents**", 1)[1].split("\n- **", 1)[0]
    missing = [w for w in _worker_agents() if f"`{w}`" not in workers]
    assert not missing, f"README worker-agent list omits {missing}"


def test_the_persona_places_both_paper_session_guards_outside_stage_5():
    lines = _read(_STYLE).split("## 5. Guard Catalog", 1)[1].split("\n## ", 1)[0].splitlines()
    table_end = max(i for i, line in enumerate(lines) if line.startswith("|"))
    note = "\n".join(lines[table_end + 1:])
    for guard in ("evaluator-conclusions", "evaluator-paper"):
        assert f"`{guard}`" in note, guard
    assert "paper session" in note
