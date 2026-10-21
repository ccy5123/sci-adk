"""
Inputs that still stopped pdflatex or made it read a file after the third hardening pass
(``test_latex_sanitize_round3.py``). Found by independent checkers; render and verify exited 0.

  1. A recorded string cited with ``\\evval`` in the authored SI body went into ``si.tex`` as
     written (the SI body is LaTeX written as is): ``sample_A``, ``Fe & Ni`` and ``x^2`` stopped
     pdflatex, ``x}\\input{marker}%`` made it read a file. A recorded string is now written as
     text there; numbers and verdicts are unchanged.
  2. BibTeX prints more than the ``@type{key,`` bodies the bib checks read: a ``@preamble``, a
     ``@string`` macro (also one named like an unprinted field, such as ``abstract``), a
     parenthesised entry, ``@ article``, and a value holding ``@word{``. The checks now read a
     ``.bib`` as BibTeX does; the paper's copy leaves out every ``@preamble``. A ``url`` or
     ``doi`` value (and the URL argument of ``\\url``/``\\href`` in a value) holding a
     backslash, ``^^`` or a brace, or a ``run:``/``file:`` link, fails: hyperref expands a URL.
  3. A shipped script was inlined in an ``lstlisting`` whenever it lacked
     ``\\end{lstlisting}``: any non-ASCII character, a control character or a line of about
     3000 characters stopped pdflatex. Only printable ASCII, tabs and line feeds, with lines
     of at most 2000 columns, are typeset now; any other body is named as shipped.
  4. The package ``main.tex`` skeleton escaped only ``\\ _ % & # $``: a hypothesis statement
     with ``^``, a brace, Greek letters or CJK stopped pdflatex, and a section name could hold
     a blank line. It now uses render's sanitizer; ``reference_style`` must be a BibTeX style
     name.
  5. An image figure's extension and width: only the graphics pdfLaTeX loads are accepted
     (``.svg``, ``.tiff``, ``.gif`` ... are refused), the extension is written in lower case,
     and a width is bounded (at most 1000pt, or 10 times a text width). An axis label is at
     most 200 characters (a longer one cannot be broken and stopped pdflatex).
  6. A literature ``references.bib`` that is not UTF-8 stopped ``sci-adk render`` with exit 2
     after it had written the paper; it is copied as before, and render says it is not UTF-8.
  7. The authored SI body is LaTeX written as is: a character pdflatex cannot typeset there is
     now named in a render warning.
  8. Bib content that cannot compile and passed verify: a math command in running text
     (``\\alpha``, ``\\frac``) is named, an accented letter inside bib math is boxed by the copy
     and named in a package bib, ``\\bibitem`` fails, and ``\\hbox`` is an unknown command.

Sections 2 and 8 changed after this pass (tests/test_bib_allowlist.py): the paper's
bibliography is a canonical copy holding only allow-listed commands, so the copy of each bypass
holds none of it, and a command off the allow-list (or in the wrong mode, in an author's
bibliography) fails rather than being advised on.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata

import pytest

from sci_adk.render.paper import _latex_sanitize, _one_line, render_paper_latex
from sci_adk.render.prose import AuthoredSI, PaperProse, SISection
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import _compile_with_bib, needs_tex
from tests.test_latex_sanitize_hardening import _build, _pdf_text
from tests.test_si import _basic_record, _qual_ev

BS = chr(92)  # a backslash, spelled out so no escape in this file is ambiguous
_MARKER = "MARKERTEXTQZX"
_INPUT = BS + "input{marker}"


def _marker_file(directory) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")


def _read_marker(directory, name: str) -> bool:
    """True iff pdflatex opened ./marker.tex while building ``name`` (the log lists each file
    it opens), or the marker's text reached the PDF."""
    log = (directory / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    if "marker.tex" in log:
        return True
    return (directory / f"{name}.pdf").is_file() and _MARKER in _pdf_text(directory, name)


# -- 1. a recorded string cited in the authored SI body -----------------------------------------

_RECORDED_STRINGS = {
    "underscore": "sample_A",
    "ampersand": "Fe & Ni",
    "caret": "x^2",
    "closes-and-inputs": "x}" + _INPUT + "%",
    "inputs": _INPUT,
    "specials": "50% of #1 ~ $5 {a}",
    "blank-line": "a\n\nb",
    "unicode": "mu " + chr(0x3BC) + " " + chr(0x2265) + " 2 " + chr(0x4E2D),
}


def _finding_record(value: str):
    spec, claims, evidence = _basic_record()
    return spec, claims, evidence + [_qual_ev("ev-4", finding=json.dumps({"sample": value}))]


def _authored_with(value: str, body: str) -> str:
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _finding_record(value)
    si = AuthoredSI(sections=[SISection(title="Notes", body=body)])
    return render_authored_si_latex(si, spec, claims, evidence)


@pytest.mark.parametrize("value", list(_RECORDED_STRINGS.values()), ids=list(_RECORDED_STRINGS))
def test_a_recorded_string_cited_in_the_authored_si_is_written_as_text(value):
    tex = _authored_with(value, "Sample " + BS + "evval{ev-4}{sample} done.")
    assert "Sample " + _latex_sanitize(_one_line(value)) + " done." in tex


def test_numbers_and_verdicts_cited_in_the_authored_si_are_written_as_before():
    body = "Slope " + BS + "evval{ev-1}{effect_size}, verdict " + BS + "status{hyp-t1}."
    assert "Slope 1.5, verdict supported." in _authored_with("s", body)


def test_a_recorded_string_in_a_table_cell_stays_in_its_cell():
    body = (BS + "begin{tabular}{ll} a & " + BS + "evval{ev-4}{sample} " + BS * 2 + " "
            + BS + "end{tabular}")
    tex = _authored_with("Fe & Ni", body)
    assert "a & Fe " + BS + "& Ni " + BS * 2 in tex


def test_a_paper_slot_still_escapes_a_recorded_string_once():
    spec, claims, evidence = _finding_record("Fe & Ni_2")
    prose = PaperProse(methods="Alloy " + BS + "evval{ev-4}{sample}.")
    tex = render_paper_latex(spec, claims, evidence, prose=prose)
    assert "Alloy Fe " + BS + "& Ni" + BS + "_2." in tex


@needs_tex
@pytest.mark.parametrize("value", list(_RECORDED_STRINGS.values()), ids=list(_RECORDED_STRINGS))
def test_an_authored_si_citing_a_hostile_recorded_string_compiles_and_reads_no_file(
    tmp_path, value
):
    _marker_file(tmp_path)
    tex = _authored_with(value, "Sample " + BS + "evval{ev-4}{sample} done.")
    assert _build(tmp_path, tex, "si") == []
    assert not _read_marker(tmp_path, "si")


# -- 7. the authored SI body: a character pdflatex cannot typeset is named ----------------------

def test_an_authored_si_body_character_pdflatex_cannot_typeset_is_named():
    from sci_adk.render.authored_si import authored_si_warnings

    body = ("alpha " + chr(0x3B1) + " geq " + chr(0x2265) + " cjk " + chr(0x4E2D)
            + " kept " + chr(0xE9) + " " + chr(0x2013) + " end")
    si = AuthoredSI(sections=[SISection(title="Notes", body=body),
                              SISection(title="Clean", body="Plain text.")])
    lines = authored_si_warnings(si)
    named = [line for line in lines if "'Notes'" in line]
    assert len(named) == 1, lines
    for codepoint in ("U+03B1", "U+2265", "U+4E2D"):
        assert codepoint in named[0]
    for codepoint in ("U+00E9", "U+2013"):  # typeset as written
        assert codepoint not in named[0]
    assert not any("'Clean'" in line for line in lines)
    assert len(lines) == 2  # the section line, and the rule once


def test_a_clean_or_absent_authored_si_gives_no_warning():
    from sci_adk.render.authored_si import authored_si_warnings

    clean = AuthoredSI(sections=[SISection(title="N", body="Plain " + chr(0xE9) + " $x$ ok.")])
    assert authored_si_warnings(clean) == []
    assert authored_si_warnings(None) == []


def test_the_cli_render_names_a_character_in_the_authored_si_body(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "si-unicode")
    si = tmp_path / "si.json"
    si.write_text(
        AuthoredSI(sections=[SISection(title="Notes", body="alpha " + chr(0x3B1) + ".")])
        .model_dump_json(),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["render", str(run_dir), "--si", str(si)]) == 0
    err = capsys.readouterr().err
    assert any(
        line.startswith("  warning: ") and "'Notes'" in line and "U+03B1" in line
        for line in err.splitlines()
    ), err


# -- 3. a shipped script inlined in the record ---------------------------------------------------

_NOT_TYPESET = {
    "latin-1-letter": "# caf" + chr(0xE9) + "\nx = 1\n",
    "greek-and-relation": "# " + chr(0x3BC) + " = 0.5, " + chr(0x3C3) + " " + chr(0x2265) + " 1\n",
    "cjk": "# " + chr(0x4E2D) + chr(0x6587) + "\n",
    "emoji": "# done " + chr(0x1F600) + "\n",
    "byte-order-mark": chr(0xFEFF) + "x = 1\n",
    "curly-quote": "# it" + chr(0x2019) + "s\n",
    "degree": "T = 30  # " + chr(0xB0) + "C\n",
    "nul": "x = 1" + chr(0) + "\n",
    "escape": "x = '" + chr(0x1B) + "[0m'\n",
    "bell": "x" + chr(7) + "\n",
    "form-feed": "a\n" + chr(0x0C) + "\nb\n",
    "delete": "a" + chr(0x7F) + "\n",
    "carriage-return": "a\rb\n",
    "long-line": "x = '" + "a" * 3000 + "'\n",
    "long-tabbed-line": "\t" * 300 + "x\n",
}
_TYPESET = {
    "ascii": "import os\nprint('ok')  # done\n",
    "tabs": "def f():\n\treturn 1\n",
    "line-of-2000": "x = '" + "a" * 1994 + "'\n",
}


def _script(text: str):
    from sci_adk.render.reproduction import ReproListing

    return ReproListing(
        evidence_id="ev-1", code_ref="code/gen.py", kind="script", text=text, filename="gen.py"
    )


@pytest.mark.parametrize("text", list(_NOT_TYPESET.values()), ids=list(_NOT_TYPESET))
def test_a_body_that_is_not_printable_ascii_tabs_and_line_feeds_is_not_typeset(text):
    from sci_adk.render.reproduction import (
        listing_inlinable,
        render_reproduction_section,
        reproduction_uses_listings,
    )

    assert listing_inlinable(text) is False
    section = render_reproduction_section([_script(text)])
    assert "lstlisting" not in section
    assert "paper/code/gen.py" in section and "its body is not typeset here" in section
    assert reproduction_uses_listings([_script(text)]) is False


@pytest.mark.parametrize("text", list(_TYPESET.values()), ids=list(_TYPESET))
def test_a_printable_ascii_body_is_typeset(text):
    from sci_adk.render.reproduction import listing_inlinable, render_reproduction_section

    assert listing_inlinable(text) is True
    section = render_reproduction_section([_script(text)])
    assert BS + "begin{lstlisting}" in section and text.rstrip("\n") in section


@needs_tex
def test_a_record_naming_each_such_script_compiles(tmp_path):
    spec, claims, evidence = _basic_record()
    listings = [_script(t) for t in _NOT_TYPESET.values()]
    listings += [_script(t) for t in _TYPESET.values()]
    record = render_si_latex(spec, claims, evidence, repro_listings=listings)
    assert _build(tmp_path, record, "record") == []


@needs_tex
def test_render_of_a_run_whose_script_holds_non_ascii_writes_a_record_that_compiles(tmp_path):
    from sci_adk.cli import main
    from sci_adk.loop.compiler import deposit_record_path
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "rec-utf8", code_ref="code/gen.py")
    script = run_dir / "code" / "gen.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# threshold " + chr(0x3BC) + " = 0.5 (caf" + chr(0xE9) + ")\nprint('x')\n",
                      encoding="utf-8")
    assert main(["render", str(run_dir)]) == 0
    record = deposit_record_path(run_dir).read_text(encoding="utf-8")
    assert "print('x')" not in record and "paper/code/gen.py" in record
    (tmp_path / "build").mkdir()
    assert _build(tmp_path / "build", record, "record") == []


# -- 5. an image figure's extension, its width, an axis label -------------------------------------

def _image(**fields):
    from sci_adk.render.figures import ImageFigureSpec

    return ImageFigureSpec(**{"kind": "image", "id": "fig-a", "caption": "C.", **fields})


_LOADED = ["a.pdf", "a.png", "a.jpg", "a.jpeg", "a.PDF", "a.PNG", "a.Jpg", "a.JPEG", "a.eps"]
_NOT_LOADED = ["a.svg", "a.gif", "a.tiff", "a.tif", "a.webp", "a.bmp", "a.abcdefgh", "a.123",
               "a.gz", "a.svgz"]


@pytest.mark.parametrize("image", _LOADED)
def test_a_graphic_pdflatex_loads_is_accepted_and_written_in_lower_case(image):
    from sci_adk.render.figures import image_figure_filename, render_image_figure

    spec = _image(image=image)
    ext = "." + image.rsplit(".", 1)[1].lower()
    assert image_figure_filename(spec, 1) == "fig1" + ext
    assert "{figures/fig1" + ext + "}" in render_image_figure(spec, 1)


@pytest.mark.parametrize("image", _NOT_LOADED)
def test_an_extension_pdflatex_cannot_load_is_refused(image):
    with pytest.raises(ValueError, match="extension") as caught:
        _image(image=image)
    assert ".png" in str(caught.value) and ".pdf" in str(caught.value)


def test_an_unvalidated_spec_with_an_svg_still_cannot_reach_latex():
    from sci_adk.render.figures import ImageFigureSpec, image_figure_filename, render_image_figure

    spec = ImageFigureSpec.model_construct(kind="image", id="f", caption="C.", image="a.svg",
                                           width="")
    with pytest.raises(ValueError, match="extension"):
        render_image_figure(spec, 1)
    with pytest.raises(ValueError, match="extension"):
        image_figure_filename(spec, 1)


def test_the_cli_render_refuses_an_svg_with_exit_2(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "fig-svg")
    (tmp_path / "a.svg").write_text("<svg/>", encoding="utf-8")
    figures = tmp_path / "figures.json"
    figures.write_text(json.dumps([{"kind": "image", "id": "f", "caption": "C.",
                                    "image": str(tmp_path / "a.svg")}]), encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir), "--figures", str(figures)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "extension" in err
    assert not (run_dir / "paper" / "draft.tex").exists()


_WIDTHS_AT_THE_BOUND = ["1000pt", "10" + BS + "textwidth", "10 " + BS + "linewidth", "13.8in",
                        "35cm", "0pt", "83em", "0.000001pt"]
_WIDTHS_TOO_LARGE = {
    "16383pt": "16383pt",
    "20000pt": "20000pt",
    "1001pt": "1001pt",
    "1000in": "1000in",
    "36cm": "36cm",
    "84em": "84em",
    "factor-11": "11" + BS + "linewidth",
    "factor-100000": "100000" + BS + "textwidth",
    "thirty-digits": "1" * 30 + "pt",
    "long-fraction": "1." + "0" * 30 + "pt",
}


@pytest.mark.parametrize("width", _WIDTHS_AT_THE_BOUND)
def test_a_width_up_to_the_bound_is_accepted(width):
    assert _image(image="a.png", width=width).width == width


@pytest.mark.parametrize("width", list(_WIDTHS_TOO_LARGE.values()), ids=list(_WIDTHS_TOO_LARGE))
def test_a_width_above_the_bound_is_refused(width):
    with pytest.raises(ValueError, match="width"):
        _image(image="a.png", width=width)


def _images(directory) -> None:
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    picture = Image.new("RGB", (4, 4), (200, 30, 30))
    picture.save(directory / "fig1.png")
    picture.save(directory / "fig2.jpg", "JPEG")
    picture.save(directory / "fig3.jpeg", "JPEG")
    picture.save(directory / "fig4.pdf", "PDF")


@needs_tex
def test_each_accepted_extension_and_width_at_the_bound_compiles(tmp_path):
    pytest.importorskip("PIL")
    spec, claims, evidence = _basic_record()
    figures = [_image(id="p1", image="x.PNG", width="1000pt"),
               _image(id="p2", image="x.jpg", width="10" + BS + "textwidth"),
               _image(id="p3", image="x.JPEG", width="13.8in"),
               _image(id="p4", image="x.pdf", width="83em")]
    _images(tmp_path / "figures")
    tex = render_paper_latex(spec, claims, evidence, figures=figures)
    assert _build(tmp_path, tex, "figs") == []


@pytest.mark.parametrize("axis", ["xlabel", "ylabel"])
def test_an_axis_label_longer_than_200_characters_is_refused(axis):
    from sci_adk.render.figures import NativePlot, PlotPoint, PlotSeries

    series = [PlotSeries(points=[PlotPoint(evidence_id="ev-1", x=1.0)])]
    assert getattr(NativePlot(type="line", series=series, **{axis: "a" * 200}), axis) == "a" * 200
    with pytest.raises(ValueError):
        NativePlot(type="line", series=series, **{axis: "a" * 201})


# -- 4. the package main.tex skeleton --------------------------------------------------------------

_STATEMENTS = {
    "caret": "runtime grows as O(n^2) on the tested set",
    "closing-brace": "the closing brace } is rare",
    "opening-brace": "an opening brace { is rare",
    "greek-and-relation": "mean " + chr(0x3BC) + " exceeds " + chr(0x3C3) + " by " + chr(0x2265) + " 2",
    "cjk": chr(0x4E2D) + chr(0x6587) + " samples agree",
    "blank-line": "first\n\nsecond",
    "tilde": "approximately ~3 units",
}


@pytest.mark.parametrize("statement", list(_STATEMENTS.values()), ids=list(_STATEMENTS))
def test_a_results_sentence_writes_record_text_as_render_does(statement):
    from sci_adk.render.package import _results_sentence

    sentence = _results_sentence({
        "run_id": "run_a", "hyp_id": "hyp-1", "statement": statement, "status": "supported",
        "point_statistic": "0.9", "op": ">=", "threshold": "0.8",
    })
    assert "---" + _latex_sanitize(_one_line(statement)) + "---" in sentence
    assert "For run" + BS + "_a (hyp-1)" in sentence
    assert "The recorded point statistic was 0.9." in sentence


def _skeleton(tmp_path, sections, rows=None, reference_style=None):
    from sci_adk.core.pkgreqs import PackageReqs
    from sci_adk.render.package import _skeleton_main_tex

    package = tmp_path / "package"
    (package / "02_data").mkdir(parents=True, exist_ok=True)
    if rows:
        header = ["run_id", "hyp_id", "status", "point_statistic", "op", "threshold", "statement"]
        with open(package / "02_data" / "claims_all.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
    pkgreqs = PackageReqs(required_sections=sections, reference_style=reference_style)
    return _skeleton_main_tex(tmp_path, package, [], pkgreqs)


def test_a_section_name_is_one_line_and_escaped_as_render_does(tmp_path):
    names = ["Results", "Data\n\nand code", "Cost ^ {per} unit & 5% #1"]
    tex = _skeleton(tmp_path, names)
    for name in names[1:]:
        assert BS + "section{" + _latex_sanitize(_one_line(name)) + "}" in tex
    for line in tex.splitlines():
        if line.startswith("%"):
            assert "(skeleton)" in line or line.strip() == "%"


@pytest.mark.parametrize("style", ["plainnat", "apalike", "unsrtnat", "ieeetr", "my-style_2.0"])
def test_a_bibtex_style_name_is_accepted_as_the_reference_style(style):
    from sci_adk.core.pkgreqs import PackageReqs

    assert PackageReqs(reference_style=style).reference_style == style


@pytest.mark.parametrize(
    "style", ["plain}x", "plain}" + _INPUT + "%", "plain nat", "a/b", "x{y}"],
    ids=["brace", "brace-input", "space", "slash", "braces"],
)
def test_any_other_reference_style_is_refused(style):
    from sci_adk.core.pkgreqs import PackageReqs

    with pytest.raises(ValueError, match="reference_style"):
        PackageReqs(reference_style=style)


def test_an_unvalidated_reference_style_cannot_reach_the_skeleton(tmp_path):
    from sci_adk.core.pkgreqs import PackageReqs
    from sci_adk.render.package import _skeleton_main_tex

    pkgreqs = PackageReqs.model_construct(required_sections=[], reference_style="plain}x")
    with pytest.raises(ValueError, match="reference_style"):
        _skeleton_main_tex(tmp_path, tmp_path / "package", [], pkgreqs)


@needs_tex
def test_a_skeleton_with_hostile_record_text_compiles(tmp_path):
    rows = [{"run_id": "run_" + str(i), "hyp_id": "h-" + str(i), "status": "supported",
             "point_statistic": "0.9", "op": ">=", "threshold": "0.8", "statement": statement}
            for i, statement in enumerate(_STATEMENTS.values())]
    names = ["Abstract", "Introduction", "Results", "Data\n\nand code", "Cost ^ {per} unit & 5%"]
    tex = _skeleton(tmp_path, names, rows=rows, reference_style="plainnat")
    (tmp_path / "build").mkdir()
    assert _build(tmp_path / "build", tex, "main") == []


# -- 6. a literature references.bib that is not UTF-8 -----------------------------------------------

_LATIN1_BIB = ("@article{Doe2020, author={Herv" + chr(0xE9) + ", A.}, title={Caf" + chr(0xE9)
               + " " + BS + "input{m}}, year={2020}}\n")


def test_render_of_a_run_whose_bibliography_is_not_utf8_exits_0_and_says_so(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "bib-latin1")
    (run_dir / "literature").mkdir(parents=True, exist_ok=True)
    raw = _LATIN1_BIB.encode("latin-1")
    (run_dir / "literature" / "references.bib").write_bytes(raw)
    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    err = capsys.readouterr().err
    assert (run_dir / "paper" / "references.bib").read_bytes() == raw
    assert any("not UTF-8" in line and "references.bib" in line for line in err.splitlines()), err
    assert any(BS + "input" in line and "Doe2020" in line for line in err.splitlines()), err


def test_an_authored_si_citing_a_bibliography_that_is_not_utf8_renders(tmp_path):
    from sci_adk.core.spec import Spec
    from sci_adk.loop.compiler import ResearchCompiler
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "si-latin1")
    (run_dir / "literature").mkdir(parents=True, exist_ok=True)
    raw = _LATIN1_BIB.encode("latin-1")
    (run_dir / "literature" / "references.bib").write_bytes(raw)
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    si = AuthoredSI(sections=[SISection(title="N", body="See " + BS + "citep{Doe2020}.")])
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_render(spec, si=si)
    assert (run_dir / "paper" / "references_SI.bib").read_bytes().strip() == raw.strip()
    assert any("not UTF-8" in line for line in compiler.reference_warnings)


def test_verify_with_a_contract_names_a_bibliography_that_is_not_utf8(tmp_path):
    from sci_adk.cli import main
    from sci_adk.loop.verify import verify_run
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "verify-latin1")
    (run_dir / "literature").mkdir(parents=True, exist_ok=True)
    (run_dir / "literature" / "references.bib").write_bytes(_LATIN1_BIB.encode("latin-1"))
    assert main(["render", str(run_dir)]) == 0
    assert main(["pubreqs", "freeze", str(run_dir), "--defaults"]) == 0
    report = verify_run(run_dir)
    assert any("references.bib" in p and "not UTF-8" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems
    assert not report.passed


# -- 2. what BibTeX prints, read as BibTeX reads it ---------------------------------------------------

_ENTRY = "@article{K2, title={Plain}, year={2020}}\n"
_BYPASSES = {
    "preamble": '@preamble{ "' + _INPUT + '" }\n' + _ENTRY,
    "string-macro": '@string{evil = "' + _INPUT + '"}\n@article{K1, title=evil, year={2020}}\n',
    "string-concatenated": ('@string{evil = "' + _INPUT + '"}\n'
                            "@article{K1, title={A} # evil, year={2020}}\n"),
    "string-named-like-an-unprinted-field": ('@string{abstract = "' + _INPUT + '"}\n'
                                             "@article{K1, title=abstract, year={2020}}\n"),
    "parenthesised-entry": "@article(K1, title={A " + _INPUT + "}, year={2020})\n",
    "space-after-at": "@ article{K1, title={A " + _INPUT + "}, year={2020}}\n",
    "at-word-inside-a-value": "@article{K1, title={See @a{ " + _INPUT + "}}, year={2020}}\n",
    "preamble-inside-a-comment": '@comment{ @preamble{"' + _INPUT + '"} }\n' + _ENTRY,
    "preamble-after-a-syntax-error": '@article{K1 junk @preamble{"' + _INPUT + '"}\n' + _ENTRY,
    "percent-is-not-a-comment": '% @preamble{"' + _INPUT + '"}\n' + _ENTRY,
    "url-csname": ("@misc{K1, title={T}, url={http://a.org/" + BS + "csname @@input"
                   + BS + "endcsname marker" + BS + "relax}, year={2020}}\n"),
    "url-input": "@misc{K1, title={T}, url={http://a.org/" + _INPUT + "}, year={2020}}\n",
    "url-caret-notation": "@misc{K1, title={T}, url={http://a.org/^^5cinput marker}, year={2020}}\n",
    "url-run-link": "@misc{K1, title={T}, url={run:calc.exe}, year={2020}}\n",
    "doi-backslash": "@misc{K1, title={T}, doi={10.1000/x" + BS + "relax}, year={2020}}\n",
    "href-run-link": "@misc{K1, title={" + BS + "href{run:calc.exe}{click}}, year={2020}}\n",
    "href-file-link": "@misc{K1, title={" + BS + "href{file:///etc/passwd}{x}}, year={2020}}\n",
    "url-argument-backslash": "@misc{K1, title={" + BS + "url{http://a.org/" + BS + "x}}, year={2020}}\n",
    "url-argument-braces": "@misc{K1, title={" + BS + "href{ru{}n:calc.exe}{x}}, year={2020}}\n",
    "bibitem": "@misc{K1, title={" + BS + "bibitem{zzz} x}, year={2020}}\n",
}
# The inputs the checkers measured with bibtex and pdflatex: ./marker.tex was opened.
_MEASURED = ["preamble", "string-macro", "string-concatenated",
             "string-named-like-an-unprinted-field", "parenthesised-entry", "space-after-at",
             "at-word-inside-a-value", "url-csname"]


@pytest.mark.parametrize("bib", list(_BYPASSES.values()), ids=list(_BYPASSES))
def test_the_command_check_fails_each_bypass(bib):
    from sci_adk.render.pkgreqs_checks import bib_command_problems, bib_latex_safety_problems

    problems = bib_command_problems(bib)
    assert problems, "the command check passed it"
    safety = bib_latex_safety_problems(bib)
    assert all(p in safety for p in problems)


@pytest.mark.parametrize("bib", list(_BYPASSES.values()), ids=list(_BYPASSES))
def test_the_paper_copy_of_each_bypass_passes_verify_and_holds_no_preamble(bib):
    from sci_adk.render.bib_latex import paper_bib
    from sci_adk.render.pkgreqs_checks import bib_command_problems, bib_form_problems

    copy = paper_bib(bib)
    assert "@preamble" not in copy.lower() and "@string" not in copy.lower()
    assert bib_command_problems(copy) == [] and bib_form_problems(copy) == []


def test_the_paper_copy_drops_every_preamble_and_keeps_the_entries():
    from sci_adk.render.bib_latex import paper_bib
    from sci_adk.render.pkgreqs_checks import bib_keys

    bib = ('@PREAMBLE( "' + BS + 'newcommand{' + BS + 'noopsort}[1]{}" )\n'
           '@string{jpc = "J. Phys. Chem."}\n'
           "@article{A2020, title={Alpha}, journal=jpc, year={2020}}\n"
           '@preamble{"x"}\n'
           "@article{B2021, title={Beta}, year={2021}}\n")
    copy = paper_bib(bib)
    assert "preamble" not in copy.lower() and "noopsort" not in copy
    assert bib_keys(copy) == ["A2020", "B2021"]
    assert "journal = {J. Phys. Chem.}" in copy  # the macro, expanded
    assert paper_bib(copy) == copy


@needs_tex
@pytest.mark.parametrize("case", _MEASURED)
def test_each_measured_bypass_reads_the_file_without_the_check(tmp_path, case):
    # Why: what BibTeX and pdflatex do with the raw input -- the check above is what stops it.
    _marker_file(tmp_path)
    errors, _bbl, _dropped = _compile_with_bib(tmp_path, _BYPASSES[case])
    assert _read_marker(tmp_path, "t") or errors


@needs_tex
@pytest.mark.parametrize("case", list(_BYPASSES))
def test_a_copy_the_check_passes_reads_no_file(tmp_path, case):
    from sci_adk.render.bib_latex import paper_bib
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    copy = paper_bib(_BYPASSES[case])
    if bib_command_problems(copy):
        return  # verify fails it, render warns
    _marker_file(tmp_path)
    _compile_with_bib(tmp_path, copy)
    assert not _read_marker(tmp_path, "t")


def test_a_string_macro_is_checked_whatever_its_name_and_where_it_is_printed():
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    bib = '@string{abstract = "x ' + BS + 'def' + BS + 'y{}"}\n@article{K1, title=abstract}\n'
    lines = bib_command_problems(bib, source="references.bib")
    assert len(lines) == 2, lines  # the macro, and the entry that prints it (expanded)
    assert any("@string 'abstract'" in line and BS + "def" in line for line in lines), lines
    assert any("entry 'K1'" in line and BS + "def" in line for line in lines), lines


def test_a_preamble_is_named_as_a_preamble():
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    lines = bib_command_problems('@preamble{"' + BS + 'relax"}\n' + _ENTRY)
    assert len(lines) == 1 and "@preamble" in lines[0], lines


def test_a_plain_url_and_doi_pass():
    from sci_adk.render.bib_latex import paper_bib
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    bib = ("@article{K1, title={T " + BS + "url{https://example.org/a_b?c=1&d=2}}, "
           "url={https://example.org/a%20b~c#frag}, doi={10.1002/(SICI)1097-4636(199601)30:1<1::AID-JBM1>3.0.CO;2-6}, "
           "year={2020}}\n")
    assert bib_command_problems(bib) == []
    # The copy keeps a url only when it is plain: % and # are TeX's comment and parameter
    # characters, so that url is left out of it (and named in a render warning).
    copy = paper_bib(bib)
    assert "url = {" not in copy and BS + "url{https://example.org/a_b?c=1&d=2}" in copy


def test_verify_fails_a_string_macro_bypass_in_the_rendered_bibliography(tmp_path):
    from sci_adk.loop.verify import verify_run
    from tests.test_latex_sanitize_round3 import _rendered_run

    run_dir = _rendered_run(tmp_path, "bib-string")
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + _BYPASSES["string-macro"], encoding="utf-8")
    report = verify_run(run_dir)
    assert any("@string 'evil'" in p and BS + "input" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems
    assert not report.passed


def test_render_warns_about_a_bypass_in_the_literature_bibliography(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "bib-paren")
    (run_dir / "literature").mkdir(parents=True, exist_ok=True)
    (run_dir / "literature" / "references.bib").write_text(_BYPASSES["parenthesised-entry"],
                                                           encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    err = capsys.readouterr().err
    assert any(line.startswith("  warning: ") and BS + "input" in line and "'K1'" in line
               for line in err.splitlines()), err


# -- 8. bib content in the wrong mode, accents in math, arguments --------------------------------------

_MATH_IN_TEXT = ["Decay of " + BS + "alpha particles", BS + "frac{1}{2} of it",
                 BS + "mathrm{x}", BS + "hat{x}", BS + "sqrt{2}", "a " + BS + "pm b"]


@pytest.mark.parametrize("title", _MATH_IN_TEXT)
def test_a_math_command_in_running_text_fails_and_the_copy_puts_it_in_math(title):
    from sci_adk.render.bib_latex import paper_bib
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    bib = "@article{K1, title={" + title + "}, year={2020}}\n"
    lines = bib_command_problems(bib)
    assert len(lines) == 1 and "running text" in lines[0] and "'K1'" in lines[0], lines
    assert bib_command_problems(paper_bib(bib)) == []


@pytest.mark.parametrize(
    "title",
    ["Decay of $" + BS + "alpha$ particles", "Decay of {" + BS + "ensuremath{" + BS + "alpha}}",
     BS + "ldots and " + BS + "S 3 and " + BS + "textit{x}", "$" + BS + "frac{1}{2}$"],
)
def test_a_math_command_in_math_is_not_named(title):
    from sci_adk.render.pkgreqs_checks import bib_command_problems, bib_latex_safety_problems

    bib = "@article{K1, title={" + title + "}, year={2020}}\n"
    assert bib_command_problems(bib) == []
    assert not any("math" in p for p in bib_latex_safety_problems(bib))


# The Latin Extended-A letters whose utf8 definition is an accent with no T1 glyph: in math
# pdflatex stops on each ("Please use \mathaccent for accents in math mode").
_ACCENT_IN_MATH = "ĀāĈĉĊċĒēĔĕĖėĜĝĠġĤĥĨĩĪīĬĭĴĵŌōŎŏŜŝŨũŪūŬŭŴŵŶŷ"


def test_the_copy_boxes_an_accented_letter_inside_math():
    from sci_adk.render.bib_latex import latex_safe_bib

    copy = latex_safe_bib("@article{K1, title={Spectra of $" + chr(0x16B) + "x$ ions}}\n")
    math = re.search(r"\$(.*?)\$", copy).group(1)
    assert chr(0x16B) not in math and BS + "mbox{" in math
    assert latex_safe_bib(copy) == copy


def test_a_package_bib_with_an_accented_letter_in_math_fails():
    from sci_adk.render.pkgreqs_checks import bib_latex_safety_problems

    bib = "@article{K1, title={Spectra of $" + chr(0x16B) + "x$ ions}}\n"
    assert any("U+016B" in p and "math" in p for p in bib_latex_safety_problems(bib))


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_the_copy_of_accented_letters_in_math_compiles(tmp_path, figure_bearing):
    from sci_adk.render.bib_latex import latex_safe_bib

    assert all(unicodedata.normalize("NFD", c) != c for c in _ACCENT_IN_MATH)
    bib = "@article{K1, title={Spectra of $" + _ACCENT_IN_MATH + "x$ and $" + chr(0xE9)
    bib += " " + chr(0x10D) + "$}, year={2020}}\n"
    errors, _bbl, dropped = _compile_with_bib(tmp_path, latex_safe_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


@pytest.mark.parametrize(
    "title",
    [BS + "hbox to 100000pt{x}", BS + "hspace{20000pt}", BS + "rule{1000000pt}{1pt}",
     BS + "setcounter{page}{99999999999}", "$" + BS + "upmu$"],
    ids=["hbox", "hspace", "rule", "setcounter", "upmu"],
)
def test_a_command_whose_argument_can_stop_pdflatex_fails(title):
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    lines = bib_command_problems("@article{K1, title={" + title + "}, year={2020}}\n")
    assert len(lines) == 1 and "'K1'" in lines[0], lines


def test_bibitem_hbox_and_upmu_are_off_the_allow_list():
    from sci_adk.render.bib_latex import MATH_COMMANDS, TEXT_COMMANDS

    for name in ("bibitem", "hbox", "upmu", "hspace", "setcounter", "rule"):
        assert name not in TEXT_COMMANDS and name not in MATH_COMMANDS, name
