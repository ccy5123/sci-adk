"""
Deposit files, Phase 3 (design/deposit-files.md §5 Phase 3, D8, D9, D10, D12).

Two parts:

  - ``record.tex`` prints each Evidence item's ``created_at`` (D10: the SI's comparison of
    the protocol's time with the first record selection needs a time only an Evidence item
    holds, and ``record.tex`` printed none);
  - the workspace instructions: the experiment stage records ``<path> sha256=<hex>`` in
    ``data_ref`` for every output table a paper may ship; the publish stage writes
    ``drafts/<spec-id>/paper/deposit.json`` with its terms, declares a copy made of a
    third-party file as its own external entry, names deposited files by their bundle paths,
    leaves times to the deposited record and follows the D8 guidance; the package skill follows
    the same for package paths; the hub and the publish command mention ``--deposit``; the
    protocol-withhold switch and its consequence are explained once.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import sci_adk
from sci_adk.core.evidence import EvidenceItem
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.render.deposit import deposit_name_problems, plan_protocol, plan_run_protocol
from sci_adk.render.paper import check_paper_tool_vocabulary
from sci_adk.render.si import render_si_latex
from tests.test_deposit_protocol import _spec_of, _trial_run, _withhold

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_WS = Path(sci_adk.__file__).parent / "templates" / "research-workspace"
_CLAUDE = _WS / ".claude"
_EXPERIMENT = _CLAUDE / "skills" / "science-workflow-experiment" / "SKILL.md"
_EXPERIMENTALIST = _CLAUDE / "agents" / "expert-experimentalist.md"
_PUBLISH = _CLAUDE / "skills" / "science-workflow-publish" / "SKILL.md"
_WRITER = _CLAUDE / "agents" / "expert-writer.md"
_HUB = _CLAUDE / "skills" / "sci" / "SKILL.md"
_PACKAGE = _CLAUDE / "skills" / "science-workflow-package" / "SKILL.md"
_PUBLISH_COMMAND = _CLAUDE / "commands" / "sci" / "publish.md"
_RIGOR = _CLAUDE / "skills" / "science-foundation-rigor" / "SKILL.md"
_ORCHESTRATOR = _CLAUDE / "output-styles" / "science-orchestrator" / "science-orchestrator.md"
_README = Path(sci_adk.__file__).resolve().parents[2] / "README.md"

_DEPOSIT_HEADING = "### Deposit files"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    level = heading.split(" ", 1)[0]
    assert heading in text, f"no {heading!r} section"
    body = text.split(heading, 1)[1]
    return re.split(rf"\n{level} ", body, maxsplit=1)[0]


def _blocks(text: str) -> list[str]:
    """Paragraphs and list items, each a block of its own (as the other template tests)."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        starts_new = not line.strip() or re.match(r"^\s*(?:\d+\.|[-*])\s", line)
        if starts_new and current:
            blocks.append(current)
            current = []
        if line.strip():
            current.append(line)
    if current:
        blocks.append(current)
    return [_flat("\n".join(b)) for b in blocks]


def _quotes(text: str) -> list[str]:
    """Each Markdown block quote (consecutive ``> `` lines) as one string."""
    quotes: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            current.append(line[1:].strip())
        elif current:
            quotes.append(current)
            current = []
    if current:
        quotes.append(current)
    return [" ".join(q) for q in quotes]


def _evidence_section(record: str) -> str:
    head = r"\section{Evidence record}"
    assert head in record
    return record.split(head, 1)[1].split(r"\section{", 1)[0]


def _entries(section: str) -> dict[str, str]:
    """Evidence id -> the text of its ``\\item`` entry."""
    out: dict[str, str] = {}
    for chunk in section.split(r"\item[")[1:]:
        match = re.match(r"\\texttt\{([^}]*)\}", chunk)
        assert match, chunk[:80]
        out[match.group(1).replace("\\_", "_")] = chunk.split(r"\end{description}", 1)[0]
    return out


def _fixture_evidence(run_dir: Path) -> list[EvidenceItem]:
    return [
        EvidenceItem.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((run_dir / "evidence").glob("*.json"))
    ]


def _utc_label(t: datetime) -> str:
    t = t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# record.tex prints each Evidence item's created_at (D10; §5 Phase 3)
# --------------------------------------------------------------------------- #

def test_record_tex_prints_each_evidence_items_created_time(tmp_path):
    run_dir = _trial_run(tmp_path)
    spec = _spec_of(run_dir)
    record = ResearchCompiler(workspace_dir=tmp_path).stage_render_record(spec)
    entries = _entries(_evidence_section(record.read_text(encoding="utf-8")))
    printed = 0
    for ev in _fixture_evidence(run_dir):
        if ev.id not in entries:  # a repeat folded into an earlier entry
            continue
        printed += 1
        assert (f"\\textit{{created:}} \\mbox{{{_utc_label(ev.created_at)}}}"
                in entries[ev.id]), ev.id
    assert printed == len(entries) and printed >= 2
    # the two results the trial's hypotheses rest on, by their recorded times (each in an
    # \mbox, so a line never breaks at one of its hyphens)
    assert (r"\textit{created:} \mbox{2026-10-08T16:53:36Z}"
            in entries["evi-run-20261008-h1-primary-fit"])
    assert (r"\textit{created:} \mbox{2026-10-08T16:54:03Z}"
            in entries["evi-run-20261008-h2-primary-rho"])


def test_the_created_time_sits_between_the_entry_head_and_its_provenance(tmp_path):
    run_dir = _trial_run(tmp_path)
    spec = _spec_of(run_dir)
    record = ResearchCompiler(workspace_dir=tmp_path).stage_render_record(spec)
    entry = _entries(_evidence_section(record.read_text(encoding="utf-8")))[
        "evi-run-20261008-h1-primary-fit"]
    assert entry.index(r"\textit{created:}") < entry.index(r"\textit{provenance:}")


def test_the_evidence_record_says_its_times_come_from_local_clocks(tmp_path):
    run_dir = _trial_run(tmp_path)
    record = ResearchCompiler(workspace_dir=tmp_path).stage_render_record(_spec_of(run_dir))
    section = _flat(_evidence_section(record.read_text(encoding="utf-8")))
    intro = section.split(r"\begin{description}", 1)[0]
    assert "local clock" in intro and "nothing witnesses" in intro


def test_an_empty_evidence_record_prints_no_time_note(tmp_path):
    run_dir = _trial_run(tmp_path)
    tex = render_si_latex(_spec_of(run_dir), [], [])
    section = _evidence_section(tex)
    assert r"\emph{No evidence recorded.}" in section
    assert "local clock" not in section


def _copies(base: EvidenceItem, times: list[datetime]) -> list[EvidenceItem]:
    return [base.model_copy(update={"id": f"{base.id}-c{i}", "created_at": t})
            for i, t in enumerate(times)]


def test_a_collapsed_entry_prints_the_earliest_and_latest_time(tmp_path):
    run_dir = _trial_run(tmp_path)
    base = next(ev for ev in _fixture_evidence(run_dir) if ev.kind.value == "literature")
    utc = timezone.utc
    items = _copies(base, [datetime(2026, 10, 8, 11, 0, tzinfo=utc),
                           datetime(2026, 10, 8, 10, 0, tzinfo=utc),
                           datetime(2026, 10, 8, 12, 0, 5, tzinfo=utc)])
    entries = _entries(_evidence_section(render_si_latex(_spec_of(run_dir), [], items)))
    (entry,) = entries.values()
    assert "(recorded 3x)" in entry
    assert (r"\textit{created:} \mbox{2026-10-08T10:00:00Z} to \mbox{2026-10-08T12:00:05Z}"
            in entry)


def test_a_collapsed_entry_whose_items_share_one_second_prints_it_once(tmp_path):
    run_dir = _trial_run(tmp_path)
    base = next(ev for ev in _fixture_evidence(run_dir) if ev.kind.value == "literature")
    t = datetime(2026, 10, 9, 18, 14, 57, 126969, tzinfo=timezone.utc)
    items = _copies(base, [t, t + timedelta(microseconds=10)])
    (entry,) = _entries(_evidence_section(render_si_latex(_spec_of(run_dir), [], items))).values()
    assert r"\textit{created:} \mbox{2026-10-09T18:14:57Z}" in entry
    assert " to \\mbox" not in entry


def test_evidence_times_are_printed_in_utc(tmp_path):
    run_dir = _trial_run(tmp_path)
    evidence = _fixture_evidence(run_dir)
    base = next(ev for ev in evidence if ev.id == "evi-run-20261008-h1-primary-fit")
    seoul = timezone(timedelta(hours=9))
    shifted = base.model_copy(update={"created_at": datetime(2026, 10, 9, 1, 53, 36, tzinfo=seoul)})
    naive = base.model_copy(update={"id": "evi-naive", "result": base.result.model_copy(
        update={"finding": "another finding"}), "created_at": datetime(2026, 10, 8, 16, 0, 0)})
    entries = _entries(_evidence_section(render_si_latex(_spec_of(run_dir), [], [shifted, naive])))
    assert r"\textit{created:} \mbox{2026-10-08T16:53:36Z}" in entries[base.id]
    assert r"\textit{created:} \mbox{2026-10-08T16:00:00Z}" in entries["evi-naive"]


def test_record_only_render_with_the_protocol_withheld_prints_the_same_times(tmp_path):
    run_dir = _trial_run(tmp_path)
    spec = _spec_of(run_dir)
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    shipped = compiler.stage_render_record(spec).read_text(encoding="utf-8")
    _withhold(run_dir)
    assert compiler.stage_render_record(spec).read_text(encoding="utf-8") == shipped


# --------------------------------------------------------------------------- #
# the experiment stage: output tables by checksum in data_ref
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("doc", [_EXPERIMENT, _EXPERIMENTALIST], ids=["skill", "agent"])
def test_the_experiment_stage_records_each_shippable_table_by_its_checksum(doc):
    blocks = [b for b in _blocks(_read(doc)) if "data_ref" in b and "table" in b]
    assert blocks, f"{doc.name}: no data_ref guidance for output tables"
    block = " ".join(blocks)
    assert "<path> sha256=<hex>" in block
    assert "every output table" in block
    assert "derived" in block  # what a table whose checksum no item holds can only be
    assert "third-party" in block and "copy" in block


# --------------------------------------------------------------------------- #
# the publish stage: deposit.json, terms, names, times
# --------------------------------------------------------------------------- #

def _deposit_section() -> str:
    return _section(_read(_PUBLISH), _DEPOSIT_HEADING)


def test_the_publish_skill_has_a_deposit_section_naming_the_declaration_and_flag():
    flat = _flat(_deposit_section())
    assert "drafts/<spec-id>/paper/deposit.json" in flat
    assert "--deposit" in flat
    assert "runs/<id>/deposit.json" in flat
    assert "paper/deposit/" in flat
    for key in ('"spec_id"', '"source"', '"name"', '"origin"', '"evidence"', '"cite"',
                '"description"'):
        assert key in flat, key
    for origin in ("`recorded`", "`derived`", "`external`"):
        assert origin in flat, origin


def test_the_publish_skill_states_the_terms_rules():
    flat = _flat(_deposit_section())
    assert '"redistribution": "author-asserted"' in flat
    assert '"license"' in flat
    assert "cited, not shipped" in flat
    assert "both" in flat  # a cited study table ships only with both statements
    assert "checks neither" in flat


def test_the_publish_skill_ships_a_third_party_file_only_with_both_terms():
    # §7 Q9 (decided 2026-10-11): an `external` entry takes the same two-field rule as a
    # study file of cited values; "either" was the v0.3 rule.
    terms = next(b for b in _blocks(_deposit_section()) if b.startswith("- **Terms.**"))
    assert not re.search(r"\beither\b", terms), terms
    external = [s for s in re.split(r"(?<=\.)\s+", terms) if "`external`" in s]
    assert external and all("both" in s for s in external), external


def test_the_writer_states_the_same_terms_for_a_third_party_file():
    section = _flat(_section(_read(_WRITER), "## Deposit Files — Declared Beside the Paper"))
    terms = section.split("cited, not shipped", 1)[0].rsplit("(", 1)[1]
    assert "third-party file" in terms, terms
    assert not re.search(r"\beither\b", section)


def test_the_publish_skill_declares_a_copy_of_a_third_party_file_as_its_own_entry():
    blocks = [b for b in _blocks(_deposit_section()) if "copy" in b and "third-party" in b]
    assert any("its own `external` entry" in b for b in blocks), blocks


def test_the_publish_skill_names_deposited_files_by_their_bundle_paths():
    flat = _flat(_deposit_section())
    for path in ("deposit/protocol/protocol-v1.json", "deposit/protocol/amendment-v2.json",
                 "deposit/manifest.csv", "deposit/data/"):
        assert path in flat, path
    # internal names the vocabulary check rejects are named as what not to write
    assert "spec.json" in flat and "checkpoints/" in flat


def test_the_publish_skill_leaves_the_times_to_the_record():
    # Times are record content (design/reader-facing-prose.md §16): the paper states none
    # and points to deposit/record.tex, which prints each one with its local-clock note.
    flat = _flat(_deposit_section())
    assert "states no times" in flat
    assert "deposit/record.tex" in flat
    assert "local clock" in flat


def test_the_publish_skill_follows_the_naming_and_checksum_guidance():
    flat = _flat(_deposit_section())
    assert r"\path{" in flat
    assert r"\allowbreak" in flat and "never elided" in flat
    assert "digit group after a hyphen" in flat
    assert "table_2.csv" in flat and "table-2.csv" in flat


def test_the_publish_skill_render_tree_shows_the_deposit_folder():
    tree = _section(_read(_PUBLISH), "### Render").split("```", 2)[1]
    assert "deposit/" in tree and "manifest.csv" in tree


def test_the_publish_skill_examples_pass_the_vocabulary_check():
    quotes = _quotes(_deposit_section())
    assert len(quotes) >= 3, quotes
    for quote in quotes:
        assert check_paper_tool_vocabulary(quote) == [], quote


def test_the_shipped_protocol_example_passes_the_names_check_on_an_amended_run(tmp_path):
    example = next(q for q in _quotes(_deposit_section()) if "protocol-v1.json" in q)
    run_dir = _trial_run(tmp_path)
    fails, _ = deposit_name_problems({"si.tex": example}, plan_protocol(run_dir))
    assert fails == []


def test_the_withheld_protocol_example_passes_the_names_check_when_withheld(tmp_path):
    example = next(q for q in _quotes(_deposit_section())
                   if "not distributed with this paper" in q)
    run_dir = _trial_run(tmp_path)
    _withhold(run_dir)
    plan = plan_run_protocol(run_dir)
    assert plan.withheld
    fails, _ = deposit_name_problems({"si.tex": example}, plan)
    assert fails == []
    assert "deposit/manifest.csv" in example


def test_the_cited_table_example_names_no_bundle_path_and_gives_the_checksum():
    example = next(q for q in _quotes(_deposit_section()) if "is not distributed" in q
                   and "protocol" not in q)
    assert "deposit/data/" not in example
    assert "SHA-256" in example


# --------------------------------------------------------------------------- #
# the protocol-withhold switch: explained once
# --------------------------------------------------------------------------- #

def _template_docs() -> list[Path]:
    return sorted(p for p in _CLAUDE.rglob("*.md")) + [_WS / "CLAUDE.md"]


def test_the_protocol_withhold_switch_is_explained_once_in_the_publish_skill():
    where = {p: _read(p).count('"protocol": "withheld"') for p in _template_docs()}
    assert {p for p, n in where.items() if n} == {_PUBLISH}, where
    assert where[_PUBLISH] == 1
    consequence = {p for p in _template_docs()
                   if "readers cannot check the protocol" in _flat(_read(p))}
    assert consequence == {_PUBLISH}
    switch = _flat(_deposit_section())
    assert '"protocol_reason"' in switch
    assert "readers cannot check the protocol" in switch
    assert "advisory" in switch


def test_the_package_skill_refers_to_the_switch_instead_of_restating_it():
    flat = _flat(_read(_PACKAGE))
    assert "withholds its protocol" in flat
    assert "science-workflow-publish" in flat
    assert '"protocol_reason"' not in flat


# --------------------------------------------------------------------------- #
# the hub, the publish command and the writer agree with the publish skill
# --------------------------------------------------------------------------- #

_RENDER_RE = re.compile(r"sci-adk render <run>[^`\n]*")


def _paper_render_flags(text: str) -> set[frozenset[str]]:
    """The flag sets of every paper render shown (a render with ``--prose``)."""
    out = set()
    for match in _RENDER_RE.finditer(_flat(text)):
        command = match.group(0)
        if "--prose" in command:
            out.add(frozenset(re.findall(r"--[a-z][a-z-]*", command)))
    return out


def test_the_hub_and_the_publish_skill_show_the_same_paper_render():
    hub, publish = _paper_render_flags(_read(_HUB)), _paper_render_flags(_read(_PUBLISH))
    assert hub and publish
    assert hub == publish, (hub, publish)
    assert all("--deposit" in flags for flags in hub)


def test_the_writer_shows_the_same_paper_render():
    writer = _paper_render_flags(_read(_WRITER))
    assert writer and writer <= _paper_render_flags(_read(_PUBLISH)), writer


# Every template that lists what `sci-adk render` writes (the foundation skill's verb table
# and the output style's Stage 4 included) names the deposit folder and the flag, and shows
# the publish skill's paper render.
_RENDER_LISTS = {
    "hub": _HUB,
    "writer": _WRITER,
    "foundation-rigor": _RIGOR,
    "orchestrator": _ORCHESTRATOR,
}


def _render_lists(text: str) -> list[str]:
    """Each paragraph, list item or table row that lists what ``sci-adk render`` writes: it
    names the verb and both ``draft.tex`` and ``si.tex``."""
    rows: list[str] = []
    for line_block in re.split(r"\n\s*\n", text):
        lines = line_block.splitlines()
        if lines and all(line.lstrip().startswith("|") for line in lines):
            rows.extend(_flat(line) for line in lines)
        else:
            rows.extend(_blocks(line_block))
    return [b for b in rows if "sci-adk render" in b and "draft.tex" in b and "si.tex" in b]


@pytest.mark.parametrize("name", sorted(_RENDER_LISTS))
def test_every_list_of_what_render_writes_names_the_deposit_folder_and_flag(name):
    lists = _render_lists(_read(_RENDER_LISTS[name]))
    assert lists, f"{name}: no list of what sci-adk render writes"
    for block in lists:
        assert "paper/deposit/" in block, f"{name}: no paper/deposit/ in:\n{block}"
        assert "--deposit" in block, f"{name}: no --deposit in:\n{block}"
        # The record copy ships in the bundle too (design/deposit-files.md §7 Q10).
        assert "deposit/record.tex" in block, f"{name}: no deposit/record.tex in:\n{block}"


@pytest.mark.parametrize("name", ["foundation-rigor", "orchestrator"])
def test_the_foundation_skill_and_the_output_style_show_the_same_paper_render(name):
    shown = _paper_render_flags(_read(_RENDER_LISTS[name]))
    assert shown and shown <= _paper_render_flags(_read(_PUBLISH)), (name, shown)


def test_the_hub_publish_section_mentions_the_declaration():
    publish = _flat(_section(_read(_HUB), "### publish"))
    assert "--deposit" in publish
    assert "drafts/<spec-id>/paper/deposit.json" in publish
    assert "science-workflow-publish" in publish


def test_the_publish_command_mentions_deposit():
    text = _read(_PUBLISH_COMMAND)
    description = next(line for line in text.splitlines() if line.startswith("description:"))
    assert "--deposit" in description and "paper/deposit/" in description
    assert "deposit/record.tex" in description


# --------------------------------------------------------------------------- #
# the package skill: package paths for data, the same guidance
# --------------------------------------------------------------------------- #

def test_the_package_skill_names_the_data_namespaces_in_its_layout():
    tree = _section(_read(_PACKAGE), "### The 6-folder layout ([2])").split("```", 2)[1]
    assert "02_data/" in tree and "05_inputs/" in tree
    assert tree.count("<id>/") >= 3  # 02_data/<id>/, 05_inputs/<id>/, protocol/<id>/


def test_the_package_skill_names_data_files_by_their_package_paths():
    section = _flat(_section(_read(_PACKAGE),
                             "### Naming files and checksums in the merged manuscript"))
    assert r"\path{02_data/<run>/<name>}" in section
    assert r"\path{05_inputs/<run>/<name>}" in section
    assert "deposit/" in section and "fails" in section  # a per-run path fails in the package
    assert "cited, not shipped" in section
    # times stay in the record (design/reader-facing-prose.md §16)
    assert "states no times" in section and "06_provenance/record.tex" in section


def test_the_package_skill_says_path_needs_the_url_package_the_skeletons_load():
    section = _flat(_section(_read(_PACKAGE),
                             "### Naming files and checksums in the merged manuscript"))
    assert r"\usepackage{url}" in section
    assert "skeleton" in section and "preamble" in section


# --------------------------------------------------------------------------- #
# README
# --------------------------------------------------------------------------- #

def test_the_readme_has_one_paragraph_on_deposit_files():
    bullets = [b for b in _blocks(_read(_README)) if b.startswith("- **Deposit files**")]
    assert len(bullets) == 1, bullets
    bullet = bullets[0]
    for phrase in ("paper/deposit/", "--deposit", "withheld", "manifest.csv",
                   "design/deposit-files.md"):
        assert phrase in bullet, phrase


def test_the_readme_deposit_bullet_is_two_sentences_what_ships_and_the_third_party_default():
    bullet = next(b for b in _blocks(_read(_README)) if b.startswith("- **Deposit files**"))
    body = bullet.split("**Deposit files**:", 1)[1].strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z`])", body)
    assert len(sentences) == 2, sentences
    assert "paper/deposit/" in sentences[0]
    assert "third-party" in sentences[1] and "both" in sentences[1], sentences[1]
    assert not re.search(r"\beither\b", bullet)
