"""
Where a run-in heading ``\\paragraph{<text>}`` may stand, and what happens when it may not.

S1 let ``\\paragraph{<text>}`` through every prose slot. Two inputs then rendered a draft
pdflatex cannot compile while render and verify both exited 0:

  (a) a heading in the abstract -- ``\\begin{abstract}\\paragraph{...}`` stops pdflatex with
      "Something's wrong--perhaps a missing \\item" (the abstract is a list environment);
  (b) a heading whose text holds a blank line -- ``\\paragraph{a<blank line>b} c`` stops it
      with "Paragraph ended before \\@sect was complete".

Now (b) is not a heading: the heading text may hold single line breaks but no paragraph
break, so such a construct stays literal text. (a) is refused: render fails loud naming the
slot, as it does for a fact the record cannot back. The title takes no heading either (it is
not a prose slot, so the command would print as literal text): refused the same way. A
heading inside a novelty sentence cannot occur -- the sentence text of ``\\novelty{..}{..}{..}``
is brace-free by construction -- and declared conclusion sentences are not rendered.

(c) A ``\\paragraph`` the prose carries in any other form (braces or commands in its text, a
blank line, ``\\paragraph*``, a space before the brace) prints as literal text; render names
the command in a warning instead of printing it silently -- the general rule for every
command printed as literal text (``paper.literal_command_warnings``,
``tests/test_latex_sanitize_hardening.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sci_adk
from sci_adk.cli import main
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.render.paper import (
    _latex_sanitize,
    _latex_sanitize_prose,
    literal_command_warnings,
    render_paper_latex,
)
from sci_adk.render.prose import PaperProse, SIProse
from tests.test_bib_latex_copy import needs_tex
from tests.test_prose_paragraph_and_date import _compile
from tests.test_render_record_only import _seed
from tests.test_si import _basic_record


def _draft(**slots: str) -> str:
    spec, claims, evidence = _basic_record()
    return render_paper_latex(spec, claims, evidence, prose=PaperProse(**slots))


# -- (b) the heading text cannot span a paragraph break ----------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "\\paragraph{a\n\nb} c",
        "\\paragraph{a\n   \nb} c",          # a line of spaces is a blank line to TeX
        "\\paragraph{a\r\n\r\nb} c",        # Windows line ends
        "\\paragraph{a\n\t\nb} c",
    ],
    ids=["blank-line", "spaces-only-line", "crlf", "tab-only-line"],
)
def test_a_heading_holding_a_blank_line_is_not_a_heading(text):
    assert _latex_sanitize_prose(text) == _latex_sanitize(text)
    assert r"\paragraph{" not in _latex_sanitize_prose(text)


def test_a_heading_holding_a_single_line_break_still_passes():
    # Written on one line (round 3): the line break becomes a space.
    out = _latex_sanitize_prose("\\paragraph{Data\nand code.} x")
    assert out == "\\paragraph{Data and code.} x"


def test_a_blank_line_after_the_heading_is_untouched():
    out = _latex_sanitize_prose("\\paragraph{Data.} x\n\n\\paragraph{Code.} y")
    assert out == "\\paragraph{Data.} x\n\n\\paragraph{Code.} y"


def test_a_draft_with_a_blank_line_inside_a_heading_prints_it_as_text():
    tex = _draft(methods="\\paragraph{a\n\nb} c")
    assert r"\textbackslash{}paragraph\{a" in tex
    assert "\\paragraph{a" not in tex


# -- (a) the abstract and the title take no heading --------------------------------------


@pytest.mark.parametrize(
    "abstract",
    [
        r"\paragraph{Aim.} We measured the slope.",
        r"We measured the slope. \paragraph{Result.} It was 1.5.",
    ],
    ids=["opening", "inside"],
)
def test_render_refuses_a_heading_in_the_abstract(abstract):
    with pytest.raises(ValueError) as excinfo:
        _draft(abstract=abstract)
    message = str(excinfo.value)
    assert "abstract" in message
    assert r"\paragraph{" in message
    assert "Methods or Results" in message


def test_a_heading_substituted_into_the_abstract_is_refused_too():
    # The record value makes the heading text brace-free: render would emit a real heading.
    with pytest.raises(ValueError, match="abstract"):
        _draft(abstract=r"\paragraph{Effect \evval{ev-1}{effect_size}.} Text.")


def test_render_refuses_a_heading_in_the_title():
    with pytest.raises(ValueError) as excinfo:
        _draft(title=r"\paragraph{Lead.} A study", methods="M.")
    message = str(excinfo.value)
    assert "title" in message
    assert r"\paragraph{Lead.}" in message


def test_an_abstract_with_a_malformed_heading_renders_it_as_literal_text():
    # Not a heading (a command inside its text): literal text, as before -- with a warning.
    tex = _draft(abstract=r"\paragraph{A \textbf{b}.} Text.")
    assert r"\textbackslash{}paragraph\{A" in tex


@pytest.mark.parametrize("slot", ["introduction", "methods", "results", "discussion", "conclusion"])
def test_every_section_slot_takes_a_heading(slot):
    tex = _draft(**{slot: r"\paragraph{Lead.} Text."})
    assert r"\paragraph{Lead.} Text." in tex


def test_the_cli_render_refuses_an_abstract_heading_and_writes_no_draft(tmp_path, capsys):
    run_dir = _seed(tmp_path, "head-abs")
    prose = tmp_path / "prose.json"
    prose.write_text(
        PaperProse(abstract=r"\paragraph{Aim.} We measured it.", methods="M.")
        .model_dump_json(),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["render", str(run_dir), "--prose", str(prose)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "abstract" in err
    assert not (run_dir / "paper" / "draft.tex").exists()


# -- (c) a \paragraph that is not a heading is named in a warning ------------------------


@pytest.mark.parametrize(
    "text, commands",
    [
        (r"\paragraph{A \textbf{b}.} x", [r"\paragraph", r"\textbf"]),
        ("\\paragraph{a\n\nb} c", [r"\paragraph"]),
        (r"\paragraph*{X.} y", [r"\paragraph"]),
        (r"\paragraph {X.} y", [r"\paragraph"]),
        (r"text \paragraph{unclosed", [r"\paragraph"]),
    ],
    ids=["command-inside", "blank-line", "starred", "space-before-brace", "unclosed"],
)
def test_a_paragraph_that_is_not_a_heading_is_warned_about(text, commands):
    warnings = literal_command_warnings(PaperProse(methods=text))
    assert [w.split(": ")[1].split(" ")[0] for w in warnings] == commands, warnings
    assert all(w.startswith("prose slot 'methods': ") for w in warnings)
    assert all("prints as literal text" in w for w in warnings)


@pytest.mark.parametrize(
    "text",
    [
        r"\paragraph{Data.} x",
        "\\paragraph{Data\nand code.} x",
        r"\paragraph{Effect \evval{ev-1}{effect_size}.} x",   # brace-free once substituted
        r"\paragraph{Share of \status{hyp-t1}.} x",
        r"no heading at all",
    ],
    ids=["heading", "line-break", "evval", "status", "none"],
)
def test_a_heading_is_not_warned_about(text):
    assert literal_command_warnings(PaperProse(methods=text)) == []


@pytest.mark.parametrize(
    "text, command",
    [(r"\subparagraph{X.} y", r"\subparagraph"), (r"\paragraphs{X.} y", r"\paragraphs")],
    ids=["subparagraph", "longer-name"],
)
def test_another_command_is_warned_about_by_its_own_name(text, command):
    warnings = literal_command_warnings(PaperProse(methods=text))
    assert [w.split(": ")[1].split(" ")[0] for w in warnings] == [command]


def test_every_prose_slot_is_checked_and_named():
    bad = r"\paragraph{A \emph{b}.} x"
    prose = PaperProse(
        title=bad, abstract=bad, introduction=bad, methods=bad, results=bad,
        discussion=bad, conclusion=bad,
    )
    warnings = literal_command_warnings(prose, SIProse(overview=bad, notes=bad))
    slots = list(dict.fromkeys(w.split("'")[1] for w in warnings))
    assert slots == [
        "title", "abstract", "introduction", "methods", "results", "discussion",
        "conclusion", "overview", "notes",
    ]


def test_no_prose_gives_no_warning():
    assert literal_command_warnings(None) == []
    assert literal_command_warnings(None, None) == []


def test_the_cli_render_prints_the_warning_and_succeeds(tmp_path, capsys):
    run_dir = _seed(tmp_path, "head-warn")
    prose = tmp_path / "prose.json"
    prose.write_text(
        PaperProse(methods=r"\paragraph{A \textbf{b}.} M.").model_dump_json(),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["render", str(run_dir), "--prose", str(prose)]) == 0
    err = capsys.readouterr().err
    assert "warning: prose slot 'methods'" in err
    assert "literal text" in err


def test_the_compiler_keeps_the_warnings_of_the_last_render(tmp_path):
    run_dir = _seed(tmp_path, "head-keep")
    from sci_adk.core.spec import Spec

    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    assert compiler.prose_warnings == []
    compiler.stage_render(spec, prose=PaperProse(methods=r"\paragraph*{X.} M."))
    # One command line, then the rule (stated once per render since round 3).
    assert len(compiler.prose_warnings) == 2
    assert compiler.prose_warnings[0].endswith(r"\paragraph prints as literal text")
    compiler.stage_render(spec, prose=PaperProse(methods=r"\paragraph{X.} M."))
    assert compiler.prose_warnings == []


# -- the writer is told ------------------------------------------------------------------

_CLAUDE = Path(sci_adk.__file__).parent / "templates" / "research-workspace" / ".claude"


@pytest.mark.parametrize(
    "rel",
    ["agents/expert-writer.md", "skills/science-workflow-publish/SKILL.md"],
)
def test_the_writer_instructions_give_the_lead_in_label_form(rel):
    flat = " ".join((_CLAUDE / rel).read_text(encoding="utf-8").split())
    lines = [ln for ln in flat.split("- ") if r"\paragraph{Label.}" in ln]
    assert len(lines) == 1, lines
    assert "Methods" in lines[0] and "Results" in lines[0]
    assert "brace-free" in lines[0]
    assert "not in the abstract" in lines[0]


# -- compile: the allowed cases compile, and what render refuses would not ---------------


@needs_tex
def test_headings_in_every_section_slot_compile(tmp_path):
    lead = r"\paragraph{Lead.} Text with 50% kept and \citet{Veith1979}."
    tex = _draft(
        abstract="We measured the slope.",
        introduction=lead, methods=lead + "\n\n" + r"\paragraph{Second.} More.",
        results=lead, discussion=lead, conclusion=lead,
    )
    assert _compile(tmp_path, tex, "draft") == []


@needs_tex
def test_the_literal_forms_compile(tmp_path):
    # What is not a heading prints as escaped text, in the abstract as in a section.
    tex = _draft(
        abstract=r"\paragraph{A \textbf{b}.} Text.",
        methods="\\paragraph{a\n\nb} c " + r"\paragraph*{X.} y",
    )
    assert _compile(tmp_path, tex, "draft") == []


@needs_tex
def test_a_heading_in_the_abstract_would_stop_pdflatex(tmp_path):
    # Why render refuses it: the construct the old render wrote does not compile.
    tex = _draft(abstract="We measured the slope.", methods="M.").replace(
        "We measured the slope.", r"\paragraph{Aim.} We measured the slope."
    )
    assert r"\begin{abstract}" + "\n" + r"\paragraph{Aim.}" in tex
    errors = _compile(tmp_path, tex, "draft")
    assert any("missing \\item" in e for e in errors), errors


@needs_tex
def test_a_heading_holding_a_blank_line_would_stop_pdflatex(tmp_path):
    # Why the heading text may not span a paragraph break: the old render wrote it verbatim.
    tex = _draft(methods="PLACEHOLDER").replace("PLACEHOLDER", "\\paragraph{a\n\nb} c")
    errors = _compile(tmp_path, tex, "draft")
    assert any("Paragraph ended before" in e for e in errors), errors
