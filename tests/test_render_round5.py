"""
Render and verify defects left open after the bibliography allow-list rewrite, and the
record-listing policy (user decision 2026-10-20).

  - a LINT for author-written LaTeX (the authored SI body, a package main.tex / si.tex): it names
    commands that read or write files or run code, in a render warning and a verify advisory --
    author LaTeX is outside sci-adk's execution and compile guarantee;
  - ``sci-adk verify`` on a run with no ``pubreqs.json`` exited 1 and printed no reason;
  - a CSV cell of non-ASCII digits was written raw as a number; the package builders' BASIS
    regexes matched Unicode digits;
  - a claims-table row whose first cell starts with ``[`` was read by ``\\\\`` as its optional
    argument;
  - an unbreakable record ``\\item[...]`` label of a very long id;
  - an image whose bytes are not its extension's format;
  - a .tex line longer than TeX's buffer;
  - a script the record cannot typeset is one line naming why, where and its SHA-256, and render
    says once which scripts it showed by name only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

import sci_adk
from tests.test_bib_latex_copy import needs_tex
from tests.test_latex_sanitize_hardening import _build

BS = chr(92)
_TEMPLATES = Path(sci_adk.__file__).parent / "templates" / "research-workspace" / "package" / "04_scripts"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"sci_adk_test_{name}", _TEMPLATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- the lint for author-written LaTeX ---------------------------------------------------------------

_LINTED = {
    "input": BS + "input{x}",
    "include": BS + "include{x}",
    "input-if-file-exists": BS + "InputIfFileExists{x}{}{}",
    "expandable-input": BS + "expandableinput{x}",
    "scantokens": BS + "scantokens{x}",
    "write18": BS + "immediate" + BS + "write18{ls}",
    "openout": BS + "openout1=x",
    "read": BS + "openin1=x " + BS + "read1 to" + BS + "y",
    "expl3-switch": BS + "ExplSyntaxOn",
    "expl3-function": BS + "file_input:n{x}",
    "expl3-variable": BS + "l_tmpa_tl",
    "directlua": BS + "directlua{os.exit()}",
    "pdf-primitive": BS + "pdfstartlink user{/S/Launch}x" + BS + "pdfendlink",
    "push-button": BS + "PushButton[onclick=x]{y}",
    "typein": BS + "typein{x}",
    "special": BS + "special{x}",
}


@pytest.mark.parametrize("tex", list(_LINTED.values()), ids=list(_LINTED))
def test_the_lint_names_file_and_execution_primitives(tex):
    from sci_adk.render.latex_lint import lint_commands

    assert lint_commands("Text " + tex + " more.") != []


@pytest.mark.parametrize(
    "tex",
    ["$" + BS + "sigma_x + " + BS + "mu_{ij}$", BS + "textit{x} " + BS + "cite{A2020}",
     "% " + BS + "input{x} in a comment", BS + "ref{fig:a} and " + BS + "label{eq:1}",
     BS + "includegraphics{figures/fig1.png}", "50" + BS + "% of input-free text",
     "a" + BS + BS + "% " + BS + "input{x} after an escaped backslash is a comment"],
)
def test_the_lint_passes_ordinary_latex(tex):
    from sci_adk.render.latex_lint import lint_commands

    assert lint_commands(tex) == []


def test_render_warns_about_a_lint_command_in_the_authored_si_body(tmp_path, capsys):
    from sci_adk.cli import main
    from sci_adk.render.prose import AuthoredSI, SISection
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "lint-si")
    si = tmp_path / "si.json"
    si.write_text(AuthoredSI(sections=[SISection(title="Notes", body="See " + BS + "input{x}.")])
                  .model_dump_json(), encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir), "--si", str(si)]) == 0
    err = capsys.readouterr().err
    assert any("'Notes'" in line and BS + "input" in line for line in err.splitlines()), err


def test_verify_advises_on_a_lint_command_in_si_tex(tmp_path):
    from sci_adk.loop.verify import verify_run
    from tests.test_latex_sanitize_round3 import _rendered_run

    run_dir = _rendered_run(tmp_path, "lint-verify")
    si_tex = run_dir / "paper" / "si.tex"
    si_tex.write_text(si_tex.read_text(encoding="utf-8").replace(
        BS + "end{document}", BS + "write18{ls}\n" + BS + "end{document}"), encoding="utf-8")
    report = verify_run(run_dir)
    notes = [n for n in report.paper_advisory if "si.tex" in n and BS + "write" in n]
    assert notes and "author" in notes[0], report.paper_advisory


def test_the_design_says_author_latex_is_outside_the_guarantee():
    text = (Path(sci_adk.__file__).parents[2] / "design" / "render-architecture-reframe.md"
            ).read_text(encoding="utf-8").lower()
    assert "author-written latex is outside the guarantee" in text
    assert "## 4h." in text and "[superseded by §4h" in text


def test_package_verify_advises_on_a_lint_command_in_an_author_main_tex(tmp_path):
    from sci_adk.loop.verify import verify_package
    from sci_adk.render.package import assemble_package
    from tests.test_si_authoring_m6 import _freeze_pkgreqs, _pkgreqs_obj, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    (ws / "package_src").mkdir()
    (ws / "package_src" / "main.tex").write_text(
        BS + "documentclass{article}" + BS + "begin{document}x " + BS + "input{secret}"
        + BS + "end{document}\n", encoding="utf-8")
    assembly = assemble_package(ws, _pkgreqs_obj(ws))
    assert any("main.tex" in n and BS + "input" in n for n in assembly.notes), assembly.notes
    report = verify_package(ws)
    assert any("main.tex" in n and BS + "input" in n for n in report.advisory), report.advisory


# -- verify prints why a run without pubreqs.json fails ------------------------------------------------

def test_verify_without_a_contract_prints_the_reasons(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_latex_sanitize_round3 import _rendered_run

    run_dir = _rendered_run(tmp_path, "no-contract")
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + "@misc{Z2020, title={" + BS + "relax}}\n",
                   encoding="utf-8")
    capsys.readouterr()
    assert main(["verify", str(run_dir)]) == 1
    err = capsys.readouterr().err
    assert "publishing requirements FAILED" in err
    assert "pubreqs.json" in err and "'Z2020'" in err, err


# -- numbers written raw from a CSV ---------------------------------------------------------------------

@pytest.mark.parametrize("cell", ["\uff11\uff12", "1_000", "\u0663", "\u00b2", "1e\u0663", "nan",
                                  "inf", ""])
def test_a_csv_cell_that_is_not_an_ascii_number_is_not_written(cell):
    from sci_adk.render.package import _csv_number

    assert _csv_number(cell) is None


@pytest.mark.parametrize("cell", ["0.95", "-1.5e-3", "12", "+3"])
def test_an_ascii_number_is_written_as_recorded(cell):
    from sci_adk.render.package import _csv_number

    assert _csv_number(cell) == cell


@pytest.mark.parametrize("name", ["make_si", "build_record_index"])
def test_the_builders_basis_regex_reads_ascii_digits_only(name):
    module = _module(name)
    assert module.BASIS.search("'point'=0.9 >= 0.5") is not None
    assert module.BASIS.search("'point'=\u0660.\u0669 >= 0.5") is None
    assert module.BASIS.flags & re.ASCII


# -- the package record's claims table ----------------------------------------------------------------

def test_each_claims_row_starts_with_an_empty_group(tmp_path):
    from tests.test_latex_sanitize_round3 import _built_package_record

    record = _built_package_record(tmp_path)
    table = record.split(BS + "label{tab:claims}")[1].split(BS + "end{longtable}")[0]
    rows = [line for line in table.splitlines()
            if " & " in line and BS + "toprule" not in line]
    assert rows and all(row.startswith("{}") for row in rows), rows


@needs_tex
def test_a_row_starting_with_a_bracket_needs_the_empty_group(tmp_path):
    head = (BS + "documentclass{article}" + BS + "usepackage{longtable}" + BS + "begin{document}"
            + BS + "begin{longtable}{ll}a & b " + BS + BS + "\n")
    tail = BS + "end{longtable}" + BS + "end{document}\n"
    assert _build(tmp_path, head + "{}[x] & y " + BS + BS + "\n" + tail, "good") == []
    assert _build(tmp_path, head + "[x] & y " + BS + BS + "\n" + tail, "bad") != []


# -- a very long id in a record label --------------------------------------------------------------

def _record_with_id(evidence_id: str) -> str:
    from sci_adk.render.si import render_si_latex
    from tests.test_si import _basic_record, _qual_ev

    spec, claims, evidence = _basic_record()
    item = _qual_ev(evidence_id, finding="an observation of its own")
    return render_si_latex(spec, claims, evidence + [item])


def test_a_long_evidence_id_is_cut_in_its_label_and_shown_whole_in_the_body():
    long_id = "ev-" + "x" * 400
    record = _record_with_id(long_id)
    labels = re.findall(r"\\item\[\\texttt\{([^}]*)\}", record)
    assert all(len(label) <= 220 for label in labels), [len(x) for x in labels]
    assert any(label.endswith("...") for label in labels)
    assert long_id in record.replace(BS + "allowbreak{}", "")


def test_the_cut_is_named_in_a_render_warning():
    from sci_adk.render.si import record_label_warnings
    from tests.test_si import _qual_ev

    assert record_label_warnings([_qual_ev("ev-" + "x" * 400)]) != []
    assert record_label_warnings([_qual_ev("ev-short")]) == []


@needs_tex
def test_a_record_with_a_very_long_id_compiles(tmp_path):
    assert _build(tmp_path, _record_with_id("ev-" + "x" * 5000), "record") == []


# -- an image whose bytes are not its extension's format ------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
_PDF = b"%PDF-1.5\n"
_EPS = b"%!PS-Adobe-3.0 EPSF-3.0\n"


@pytest.mark.parametrize(
    "name, data, ok",
    [("a.png", _PNG, True), ("a.jpg", _JPEG, True), ("a.JPEG", _JPEG, True), ("a.pdf", _PDF, True),
     ("a.eps", _EPS, True), ("a.png", _JPEG, False), ("a.pdf", _PNG, False),
     ("a.jpg", b"GIF89a", False), ("a.eps", _PDF, False), ("a.png", b"", False)],
)
def test_an_image_must_be_the_format_its_extension_names(name, data, ok):
    from sci_adk.render.figures import image_format_problem

    assert (image_format_problem(name, data) is None) is ok


def test_render_refuses_a_mislabelled_image_naming_the_figure(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "fig-magic")
    (tmp_path / "plot.png").write_bytes(_JPEG)
    figures = tmp_path / "figures.json"
    figures.write_text(json.dumps([{"kind": "image", "id": "fig-plot", "caption": "C.",
                                    "image": str(tmp_path / "plot.png")}]), encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir), "--figures", str(figures)]) == 2
    err = capsys.readouterr().err
    assert "error:" in err and "fig-plot" in err and "PNG" in err, err


# -- a .tex line longer than TeX's buffer ----------------------------------------------------------

def test_a_long_line_is_broken_at_white_space():
    from sci_adk.render.paper import break_long_lines

    text = "x" + " word" * 5000 + "\n% c" + " comment" * 3000 + "\n"
    out = break_long_lines(text, limit=1000)
    assert all(len(line) <= 1000 for line in out.splitlines())
    assert out.replace("\n% ", " ").split() == text.replace("\n% ", " ").split()
    comment = out.split("\n% c", 1)[1].splitlines()[1:]
    assert comment and all(line.startswith("% ") for line in comment), comment[:3]


def test_the_package_record_script_breaks_lines_exactly_like_render():
    from sci_adk.render.paper import break_long_lines

    module = _module("make_si")
    samples = [
        "x" + " word" * 5000 + "\n% c" + " comment" * 3000 + "\n",
        "a" * 12000 + " b\n",
        BS + "begin{lstlisting}\n" + "y " * 6000 + "\n" + BS + "end{lstlisting}\n" + "z " * 6000,
        "50" + BS + "% " + "q " * 6000 + "% tail " + "r " * 6000,
        "text " + BS + " " * 3 + "w " * 6000,
    ]
    for text in samples:
        for limit in (100, 1000, 10000):
            assert module.break_long_lines(text, limit) == break_long_lines(text, limit)


def test_a_line_with_no_white_space_to_break_at_is_named():
    from sci_adk.render.paper import break_long_lines, long_line_warnings

    tex = "a\n" + "x" * 20000 + "\nb"
    assert break_long_lines(tex) == tex
    lines = long_line_warnings(tex, "draft.tex")
    assert len(lines) == 1 and "draft.tex" in lines[0] and "20000" in lines[0]
    assert long_line_warnings("a b\n" * 3, "draft.tex") == []


def test_a_listing_body_is_never_broken():
    from sci_adk.render.paper import break_long_lines

    body = "x = '" + "a " * 3000 + "'"
    text = BS + "begin{lstlisting}\n" + body + "\n" + BS + "end{lstlisting}\n"
    assert break_long_lines(text, limit=1000) == text


def test_a_draft_with_a_240000_character_title_has_no_line_over_the_limit():
    from sci_adk.render.paper import render_paper_latex
    from sci_adk.render.prose import PaperProse
    from tests.test_si import _basic_record

    spec, claims, evidence = _basic_record()
    title = ("Word " * 48000).strip()
    tex = render_paper_latex(spec, claims, evidence, prose=PaperProse(title=title))
    assert max(len(line) for line in tex.splitlines()) <= 10000


@needs_tex
def test_a_draft_with_a_240000_character_title_compiles(tmp_path):
    from sci_adk.render.paper import render_paper_latex
    from sci_adk.render.prose import PaperProse
    from tests.test_si import _basic_record

    spec, claims, evidence = _basic_record()
    tex = render_paper_latex(spec, claims, evidence,
                             prose=PaperProse(title=("Word " * 48000).strip()))
    assert _build(tmp_path, tex, "draft") == []


# -- the record shows a script it cannot typeset by name, and render says so once -------------------------

def _script(text: str, name: str = "gen.py"):
    from sci_adk.render.reproduction import ReproListing

    return ReproListing(evidence_id="ev-1", code_ref=f"code/{name}", kind="script", text=text,
                        filename=name)


@pytest.mark.parametrize(
    "text, reason",
    [("# caf\u00e9\n", "non-ASCII characters"), ("x = '" + "a" * 3000 + "'\n", "line too long")],
    ids=["non-ascii", "long-line"],
)
def test_a_script_shown_by_name_is_one_line_naming_reason_place_and_hash(text, reason):
    from sci_adk.render.reproduction import render_reproduction_section

    section = render_reproduction_section([_script(text)])
    lines = [line for line in section.splitlines() if "paper/code/gen.py" in line]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(lines) == 1 and reason in lines[0] and digest in lines[0], section


def test_an_ascii_script_is_still_inlined():
    from sci_adk.render.reproduction import render_reproduction_section

    section = render_reproduction_section([_script("print('ok')\n")])
    assert BS + "begin{lstlisting}" in section


def test_render_lists_the_scripts_shown_by_name_once(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "names-only", code_ref="code/gen.py")
    script = run_dir / "code" / "gen.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# caf\u00e9\nprint('x')\n", encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    captured = capsys.readouterr()
    out = captured.out + captured.err
    lines = [line for line in out.splitlines() if "by name only" in line]
    assert len(lines) == 1 and "gen.py" in lines[0] and "non-ASCII" in lines[0], out


# -- the package SI bibliography is cut from the canonical copy ------------------------------------------

def test_the_package_si_bibliography_is_canonical(tmp_path):
    from sci_adk.render.bib_latex import paper_bib
    from sci_adk.render.package import assemble_package
    from tests.test_si_authoring_m6 import _freeze_pkgreqs, _pkgreqs_obj, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    (src / "references.bib").write_text(
        '@string{j = "J. Chem."}\n@article (A2020, title = "Alpha", journal = j, year = 2020)\n'
        "@ article{B2021, title = {Beta}, year = {2021}}\n", encoding="utf-8")
    (src / "si.tex").write_text(
        BS + "documentclass{article}" + BS + "usepackage{natbib}" + BS + "begin{document}"
        + BS + "citep{A2020,B2021}" + BS + "bibliographystyle{plainnat}" + BS
        + "bibliography{references_SI}" + BS + "end{document}\n", encoding="utf-8")
    assemble_package(ws, _pkgreqs_obj(ws))
    si_bib = (ws / "package" / "01_manuscript" / "references_SI.bib").read_text(encoding="utf-8")
    assert "A2020" in si_bib and "B2021" in si_bib and "J. Chem." in si_bib
    assert paper_bib(si_bib) == si_bib
