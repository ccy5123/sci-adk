"""
Escape bypasses left after the second hardening pass (``test_latex_keys_and_bib_escapes.py``).

Found by independent checkers on the hardened render path (render and verify exited 0):

  1. A run-in heading ``\\paragraph{...}`` was judged on the raw text and its text folded
     afterwards: a line inside it holding only Unicode spaces (U+00A0, U+3000, U+2003) or only
     combining marks (U+0301) passed the blank-line rule, then folded to an empty line, and
     pdflatex stopped with "Paragraph ended before \\@sect was complete". The heading text is
     now emitted on one line.
  2. An image figure's ``width`` and the extension of its ``image`` went into
     ``\\includegraphics[width=...]{figures/fig<N><ext>}`` as written: either could close the
     command and ``\\input`` a file. Both are validated when the spec is read.
  3. Without a ``.bib``, the cited DOIs were written into ``\\url{https://doi.org/<doi>}`` as
     written; a DOI holding ``}`` closed the ``\\url`` and ran what followed. A DOI must now
     have the DOI form to be cited; any other is left out with a render warning.
  4. Verify failed any bib command outside a closed list of known-harmless ones. It now fails
     only a command that can read or write a file, define a macro, change how TeX reads its
     input or end the document (and ``^^`` notation), names any other unknown command in an
     advisory, and runs on every bibliography render writes, with or without a publishing
     contract.
  5. Further: warnings (one short line per command, the rule once, replaced characters named),
     the authored SI body cleaned of control characters, the record's bibliography decided
     from its closing lines, the reproduction listing's ids on one line, an HTML entity
     decoded inside bib math boxed, and the package record script escaping like render.
"""

from __future__ import annotations

import re

import pytest

from sci_adk.render.paper import literal_command_warnings, render_paper_latex
from sci_adk.render.prose import PaperProse, SIProse
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import needs_tex
from tests.test_latex_sanitize_hardening import _build, _pdf_text
from tests.test_si import _basic_record

BS = chr(92)  # a backslash, spelled out so no escape in this file is ambiguous
BEGIN = BS + "begin{document}"
_MARKER = "MARKERTEXTQZX"


def _draft(font_policy=None, **slots: str) -> str:
    spec, claims, evidence = _basic_record()
    return render_paper_latex(
        spec, claims, evidence, prose=PaperProse(**slots), font_policy=font_policy
    )


def _record(**slots: str) -> str:
    spec, claims, evidence = _basic_record()
    return render_si_latex(spec, claims, evidence, prose=SIProse(**slots))


# -- 1. a heading line that folds to nothing -------------------------------------------------

# A line inside a heading that holds only these passes the blank-line rule as written, and
# folds to a space (the spaces) or to nothing (the combining mark).
_FOLDS_TO_BLANK = {
    "no-break-space": chr(0xA0),
    "ideographic-space": chr(0x3000),
    "em-space": chr(0x2003),
    "combining-acute": chr(0x301),
}
_DRAFT_SLOTS = ["introduction", "methods", "results", "discussion", "conclusion"]
_SI_SLOTS = ["overview", "notes"]


def _heading(line: str) -> str:
    return BS + "paragraph{Data\n" + line + "\nand code.} Text."


def _data_headings(tex: str) -> list[str]:
    return [h for h in re.findall(BS * 2 + r"paragraph\{([^{}]*)\}", tex) if h.startswith("Data")]


@pytest.mark.parametrize("slot", _DRAFT_SLOTS + _SI_SLOTS)
@pytest.mark.parametrize("line", list(_FOLDS_TO_BLANK.values()), ids=list(_FOLDS_TO_BLANK))
def test_a_heading_whose_line_folds_to_nothing_is_one_line(slot, line):
    text = _heading(line)
    if slot in _SI_SLOTS:
        tex = _record(**{slot: text})
        warnings = literal_command_warnings(None, SIProse(**{slot: text}))
    else:
        tex = _draft(**{slot: text})
        warnings = literal_command_warnings(PaperProse(**{slot: text}))
    headings = _data_headings(tex)
    assert len(headings) == 1, headings
    assert "\n" not in headings[0], repr(headings[0])
    assert headings[0].startswith("Data ") and headings[0].endswith(" and code.")
    assert warnings == []


@needs_tex
@pytest.mark.parametrize("font_policy", [False, True], ids=["latin-modern", "times"])
def test_headings_with_such_lines_compile_in_every_slot(tmp_path, font_policy):
    body = " ".join(_heading(line) for line in _FOLDS_TO_BLANK.values())
    draft = _draft(font_policy=font_policy, **{slot: body for slot in _DRAFT_SLOTS})
    assert _build(tmp_path, draft, "draft") == []
    record = _record(**{slot: body for slot in _SI_SLOTS})
    # The record in the draft's faces (the run's SI follows the draft's font policy).
    preamble = draft.split(BEGIN, 1)[0]
    assert _build(tmp_path, preamble + BEGIN + record.split(BEGIN, 1)[1], "record") == []


@needs_tex
def test_the_old_heading_would_stop_pdflatex(tmp_path):
    # Why: what the renderer wrote before (the heading text folded across its lines).
    tex = _draft(methods="PLACE").replace(
        "PLACE", BS + "paragraph{Data\n \nand code.} Text."
    )
    errors = _build(tmp_path, tex, "old")
    assert any("Paragraph ended before" in e for e in errors), errors


# -- 2. an image figure's width and file extension --------------------------------------------

_GOOD_WIDTHS = [
    "", BS + "linewidth", "0.8" + BS + "textwidth", ".5" + BS + "columnwidth",
    "0.45 " + BS + "linewidth", "8cm", "3.5in", "100pt", "12mm", "20em", "4ex", "72bp", "6pc",
    "2 cm",
]
_BAD_WIDTHS = {
    "closes-the-option": "1pt]{marker}" + BS + "input{marker}" + BS + "includegraphics[width=1pt",
    "input": BS + "input{marker}",
    "second-key": "0.8" + BS + "textwidth,angle=90",
    "no-unit": "10",
    "negative": "-1cm",
    "exponent": "1e3pt",
    "other-length-command": BS + "paperwidth",
    "unknown-unit": "3px",
    "brace": "{3cm}",
    "line-break": "3\ncm",
}
_GOOD_IMAGES = ["a.png", "dir/fig.PDF", "x.jpeg", "plots/v2.final.eps", "diagram"]
_BAD_IMAGES = {
    "closes-the-path": "a.b}" + BS + "input{marker}%",
    "space": "a.p g",
    "non-ascii": "a.p" + chr(0xF1) + "g",
    "too-long": "a.abcdefghi",
    "percent": "a.pn%",
    "hash": "a.p#g",
}


def _image(**fields):
    from sci_adk.render.figures import ImageFigureSpec

    return ImageFigureSpec(**{"kind": "image", "id": "fig-a", "caption": "C.", **fields})


@pytest.mark.parametrize("width", _GOOD_WIDTHS)
def test_a_tex_length_or_a_factor_of_the_text_width_is_accepted(width):
    from sci_adk.render.figures import render_image_figure

    tex = render_image_figure(_image(image="a.png", width=width), 1)
    expected = width.strip() or BS + "linewidth"
    assert BS + "includegraphics[width=" + expected + "]{figures/fig1.png}" in tex


@pytest.mark.parametrize("width", list(_BAD_WIDTHS.values()), ids=list(_BAD_WIDTHS))
def test_any_other_width_is_refused_when_the_spec_is_read(width):
    with pytest.raises(ValueError, match="width"):
        _image(image="a.png", width=width)


@pytest.mark.parametrize("image", _GOOD_IMAGES)
def test_a_plain_file_extension_is_accepted(image):
    assert _image(image=image).image == image


@pytest.mark.parametrize("image", list(_BAD_IMAGES.values()), ids=list(_BAD_IMAGES))
def test_any_other_file_extension_is_refused_when_the_spec_is_read(image):
    with pytest.raises(ValueError, match="extension"):
        _image(image=image)


def test_the_figure_union_and_the_authored_si_refuse_them_too():
    from pydantic import TypeAdapter

    from sci_adk.render.figures import AnyFigure, PaperFigures
    from sci_adk.render.prose import AuthoredSI

    bad = {"kind": "image", "id": "f", "caption": "C.", "image": "a.png",
           "width": _BAD_WIDTHS["closes-the-option"]}
    with pytest.raises(ValueError):
        TypeAdapter(list[AnyFigure]).validate_python([bad])
    with pytest.raises(ValueError):
        PaperFigures.model_validate({"figures": [bad]})
    with pytest.raises(ValueError):
        AuthoredSI.model_validate({"figures": [dict(bad, width="", image=_BAD_IMAGES["closes-the-path"])]})


def test_a_spec_that_skipped_validation_still_cannot_reach_latex():
    from sci_adk.render.figures import ImageFigureSpec, image_figure_filename, render_image_figure

    spec = ImageFigureSpec.model_construct(
        kind="image", id="f", caption="C.", image=_BAD_IMAGES["closes-the-path"], width=""
    )
    with pytest.raises(ValueError, match="extension"):
        render_image_figure(spec, 1)
    with pytest.raises(ValueError, match="extension"):
        image_figure_filename(spec, 1)
    spec = ImageFigureSpec.model_construct(
        kind="image", id="f", caption="C.", image="a.png", width=_BAD_WIDTHS["input"]
    )
    with pytest.raises(ValueError, match="width"):
        render_image_figure(spec, 1)


@pytest.mark.parametrize("x", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"])
def test_a_plot_point_x_must_be_finite(x):
    from sci_adk.render.figures import PlotPoint

    with pytest.raises(ValueError, match="finite"):
        PlotPoint(evidence_id="ev-1", x=x)


def test_the_cli_render_refuses_a_hostile_width_with_exit_2(tmp_path, capsys):
    import json

    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "fig-width")
    figures = tmp_path / "figures.json"
    figures.write_text(json.dumps([{
        "kind": "image", "id": "f", "caption": "C.", "image": "a.png",
        "width": _BAD_WIDTHS["closes-the-option"],
    }]), encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir), "--figures", str(figures)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "width" in err
    assert not (run_dir / "paper" / "draft.tex").exists()


def _png(path) -> None:
    """A valid 1x1 PNG (stdlib only), for pdflatex to include."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(
            ">I", zlib.crc32(kind + data) & 0xFFFFFFFF
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b"")
    )


@needs_tex
def test_every_accepted_width_compiles(tmp_path):
    spec, claims, evidence = _basic_record()
    figures = [
        _image(id=f"w{i}", image="a.png", width=width) for i, width in enumerate(_GOOD_WIDTHS)
    ]
    for number in range(1, len(figures) + 1):
        _png(tmp_path / "figures" / f"fig{number}.png")
    tex = render_paper_latex(spec, claims, evidence, figures=figures)
    assert _build(tmp_path, tex, "widths") == []


# -- 3. a cited DOI without a .bib --------------------------------------------------------------

_GOOD_DOIS = [
    "10.1021/es0605101",
    "10.1016/j.chemosphere.2006.01.001",
    "10.1002/(SICI)1097-4636(199907)46:1<1::AID-JBM1>3.0.CO;2-Z",
    "10.48550/arXiv.1301.1493",
    "10.1000.10/123456",
    "10.5281/zenodo.123_456",
]
_BAD_DOIS = {
    "closes-the-url": "10.1/x}" + BS + "input{marker}%",
    "closes-a-real-prefix": "10.1021/x}" + BS + "input{marker}%",
    "space": "10.1021/a b",
    "line-break": "10.1021/a\nb",
    "prefix-word": "doi:10.1021/x",
    "brace": "10.1021/x{y}",
    "backslash": "10.1021/x" + BS + "y",
    "percent": "10.1021/x%y",
    "hash": "10.1021/x#y",
    "caret": "10.1021/x^^5cinput",
    "non-ascii": "10.1021/x" + chr(0x2013) + "y",
    "short-prefix": "10.12/x",
    "no-suffix": "10.1021/",
}


@pytest.mark.parametrize("doi", _GOOD_DOIS)
def test_a_doi_is_cited_as_a_url(doi):
    from sci_adk.render.paper import is_doi

    assert is_doi(doi)
    tex = render_paper_latex(*_basic_record(), cited_dois=[doi])
    assert BS + "url{https://doi.org/" + doi + "}" in tex


@pytest.mark.parametrize("doi", list(_BAD_DOIS.values()), ids=list(_BAD_DOIS))
def test_anything_else_is_not_cited(doi):
    from sci_adk.render.paper import is_doi

    assert not is_doi(doi)
    tex = render_paper_latex(*_basic_record(), cited_dois=[doi, "10.1021/es0605101"])
    assert BS + "url{https://doi.org/10.1021/es0605101}" in tex
    assert tex.count(BS + "url{") == 1
    assert BS + "input{marker}" not in tex


def _literature_run(tmp_path, dois, spec_id="doi-run"):
    """A seeded run whose literature manifest lists ``dois`` and that has no references.bib."""
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, spec_id)
    lit = run_dir / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    rows = "".join(f"{i},{doi},success,x,,X{i}.pdf,cli,\n" for i, doi in enumerate(dois, 1))
    (lit / "manifest.csv").write_text(
        "index,doi,status,source,license,filename,origin,error\n" + rows, encoding="utf-8"
    )
    return run_dir


def test_render_leaves_a_non_doi_out_and_names_it(tmp_path, capsys):
    from sci_adk.cli import main

    hostile = _BAD_DOIS["closes-a-real-prefix"]
    run_dir = _literature_run(tmp_path, ['"' + hostile + '"', "10.1021/es0605101"])
    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    err = capsys.readouterr().err
    tex = (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8")
    assert BS + "url{https://doi.org/10.1021/es0605101}" in tex
    assert BS + "input{marker}" not in tex
    lines = [line for line in err.splitlines() if "not a DOI" in line]
    assert len(lines) == 1, err
    assert "manifest.csv" in lines[0] and "left out of the References" in lines[0]


def test_render_with_a_bib_does_not_warn_about_the_doi_list(tmp_path):
    from sci_adk.loop.compiler import ResearchCompiler
    from sci_adk.core.spec import Spec

    run_dir = _literature_run(tmp_path, ["10.1/x}" + BS + "input{marker}"], "doi-bib")
    (run_dir / "literature" / "references.bib").write_text(
        "@article{Doe2020, author={Doe, J.}, title={T}, journal={J}, year={2020}}\n",
        encoding="utf-8",
    )
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    compiler.stage_render(spec)
    assert not any("not a DOI" in w for w in compiler.reference_warnings)


@needs_tex
def test_a_hostile_doi_list_compiles_and_reads_no_file(tmp_path):
    (tmp_path / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")
    tex = render_paper_latex(*_basic_record(), cited_dois=list(_BAD_DOIS.values()) + _GOOD_DOIS)
    assert _build(tmp_path, tex, "dois") == []
    assert _MARKER not in _pdf_text(tmp_path, "dois")


@needs_tex
def test_the_old_doi_list_would_read_the_file(tmp_path):
    # Why: what the renderer used to write for the DOI 10.1/x}\input{marker}%.
    (tmp_path / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")
    old = BS + "url{https://doi.org/" + _BAD_DOIS["closes-the-url"] + "}"
    tex = render_paper_latex(*_basic_record(), cited_dois=["10.1021/es0605101"])
    tex = tex.replace(BS + "url{https://doi.org/10.1021/es0605101}", old)
    errors = _build(tmp_path, tex, "old-dois")
    read = (tmp_path / "old-dois.pdf").is_file() and _MARKER in _pdf_text(tmp_path, "old-dois")
    assert read or errors


# -- 12. the reproduction listing's ids, code reference and caption on one line ---------------

def _repro_listings():
    from sci_adk.render.reproduction import ReproListing

    return [
        ReproListing(
            evidence_id="ev-\n\nscript", code_ref="code/run.py", kind="script",
            text="import sys\nprint('hello', sys.argv)\n", filename="run.py",
        ),
        ReproListing(
            evidence_id="ev-\n \npointer", code_ref="commit:abc\n\n  see the lab notebook",
            kind="pointer",
        ),
    ]


def test_the_reproduction_section_writes_each_macro_argument_on_one_line():
    from sci_adk.render.reproduction import render_reproduction_section

    tex = render_reproduction_section(_repro_listings())
    caption = re.search(r"caption=\{([^{}]*)\}", tex).group(1)
    assert "\n" not in caption and "ev- script" in caption
    texttts = re.findall(BS * 2 + r"texttt\{([^{}]*)\}", tex)
    assert "ev- pointer" in texttts
    assert "commit:abc see the lab notebook" in texttts
    assert all("\n" not in t for t in texttts)


@needs_tex
def test_a_record_with_such_a_listing_compiles(tmp_path):
    spec, claims, evidence = _basic_record()
    record = render_si_latex(spec, claims, evidence, repro_listings=_repro_listings())
    assert _build(tmp_path, record, "repro") == []


# -- 13. an HTML entity decoded inside bib math -----------------------------------------------

# Each decodes to an ASCII character whose text form is a text-mode command or an escape.
_MATH_ENTITIES = {
    "backslash": "&#92;", "brace-left": "&#123;", "brace-right": "&#125;", "tilde": "&#126;",
    "caret": "&#94;", "dollar": "&#36;", "ampersand": "&amp;", "percent": "&#37;",
    "hash": "&#35;", "underscore": "&#95;", "quote": "&quot;", "hex-backslash": "&#x5C;",
}


def _math_of(bib: str) -> str:
    from tests.test_bib_latex_copy import _title_of

    title = _title_of(bib)
    return title[title.index("$") : title.rindex("$") + 1]


@pytest.mark.parametrize("entity", list(_MATH_ENTITIES.values()), ids=list(_MATH_ENTITIES))
def test_an_entity_decoded_in_math_is_text_in_a_box(entity):
    from sci_adk.render.bib_latex import latex_safe_bib
    from sci_adk.render.pkgreqs_checks import bib_latex_safety_problems
    from tests.test_bib_latex_copy import _entry

    out = latex_safe_bib(_entry("On $a " + entity + " b$ here"))
    math = _math_of(out)
    assert math.startswith("$a " + BS + "mbox{") and math.endswith("} b$"), math
    assert re.search(r"(?<!" + BS * 2 + r"mbox\{)" + BS * 2 + "text", math) is None, math
    assert latex_safe_bib(out) == out
    assert bib_latex_safety_problems(out) == []


def test_a_less_than_entity_in_math_stays_a_relation():
    from sci_adk.render.bib_latex import latex_safe_bib
    from tests.test_bib_latex_copy import _entry

    assert _math_of(latex_safe_bib(_entry("On $x &lt; y &gt; z$ here"))) == "$x < y > z$"


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_entities_decoded_in_math_compile(tmp_path, figure_bearing):
    from sci_adk.render.bib_latex import latex_safe_bib, paper_bib
    from tests.test_bib_latex_copy import _compile_with_bib, _entry

    title = "Entities $a " + " ".join(_MATH_ENTITIES.values()) + " &#94;&#94;5c b$ end"
    copy = paper_bib(latex_safe_bib(_entry(title, "Ent2020")))
    errors, bbl, dropped = _compile_with_bib(tmp_path, copy, figure_bearing)
    assert errors == [], f"{errors[:10]} (dropped {dropped})"


# -- 10. the authored SI body: verbatim LaTeX, cleaned of control characters -----------------

_CONTROLS = "".join(chr(c) for c in (0, 1, 7, 8, 0x0B, 0x0C, 0x1B, 0x1F, 0x7F))


def _authored(body: str, title: str = "Supplementary Notes"):
    from sci_adk.render.authored_si import render_authored_si_latex
    from sci_adk.render.prose import AuthoredSI, SISection

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(sections=[SISection(title=title, body=body)])
    return render_authored_si_latex(si, spec, claims, evidence)


def test_the_authored_si_body_loses_its_control_characters_and_keeps_its_latex():
    body = (
        "A " + BS + "textbf{bold}" + _CONTROLS + " table:\r\n"
        + BS + "begin{tabular}{ll} a & b " + BS * 2 + BS + "end{tabular}\rDone."
    )
    tex = _authored(body)
    assert not any(ch in tex for ch in _CONTROLS + "\r")
    assert BS + "textbf{bold} table:\n" + BS + "begin{tabular}{ll} a & b " in tex
    assert BS + "end{tabular}\nDone." in tex


def test_a_control_character_inside_a_fact_macro_is_cleaned_before_substitution():
    tex = _authored("Slope " + BS + "ev" + chr(7) + "val{ev-1}{effect_size}.")
    assert "Slope 1.5." in tex
    assert "evval" not in tex


def test_the_si_bibliography_reads_the_cleaned_body(tmp_path):
    from sci_adk.loop.compiler import ResearchCompiler
    from sci_adk.render.prose import AuthoredSI, SISection

    run_dir = tmp_path / "runs" / "si-clean"
    (run_dir / "literature").mkdir(parents=True)
    (run_dir / "literature" / "references.bib").write_text(
        "@article{Doe2020, author={Doe, J.}, title={T}, journal={J}, year={2020}}\n",
        encoding="utf-8",
    )
    si = AuthoredSI(sections=[SISection(title="N", body="See " + BS + "ci" + chr(7) + "te{Doe2020}.")])
    subset = ResearchCompiler._si_bib_subset(run_dir, si)
    assert subset is not None and "Doe2020" in subset


@needs_tex
def test_an_authored_si_with_control_characters_compiles(tmp_path):
    tex = _authored("Text" + _CONTROLS + " with a bell and a form feed." + chr(0x0C) + " End.")
    assert _build(tmp_path, tex, "authored") == []


# -- 11. whether the record names a bibliography: its closing lines ---------------------------

_BIB_LINES = BS + "bibliographystyle{plainnat}\n" + BS + "bibliography{references}\n"


def _listing_with(text: str):
    from sci_adk.render.reproduction import ReproListing

    return ReproListing(
        evidence_id="ev-1", code_ref="code/make.py", kind="script", text=text,
        filename="make.py",
    )


@pytest.mark.parametrize(
    "script",
    [
        "# writes the paper\nprint('x')\n" + BS + "bibliography{references}\n",
        "doc = '''\n" + _BIB_LINES + "'''\n",
    ],
    ids=["bibliography-line", "style-and-bibliography-lines"],
)
def test_a_listing_holding_the_bibliography_lines_is_not_the_record_bibliography(script):
    from sci_adk.render.deposit import record_bibliography

    spec, claims, evidence = _basic_record()
    record = render_si_latex(
        spec, claims, evidence, repro_listings=[_listing_with(script)],
        bib_path="/x/references.bib",
    )
    assert BS + "bibliography{references}" in record  # in the listing
    assert record_bibliography(record.encode("utf-8")) is None


@pytest.mark.parametrize("line_end", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_a_record_whose_prose_cites_names_its_bibliography(line_end):
    from sci_adk.render.deposit import RECORD_BIB_NAME, record_bibliography

    spec, claims, evidence = _basic_record()
    record = render_si_latex(
        spec, claims, evidence, prose=SIProse(notes="As in " + BS + "citep{Doe2020}."),
        bib_path="/x/references.bib",
        repro_listings=[_listing_with("print('x')\n" + BS + "bibliography{references}\n")],
    )
    assert record.rstrip().endswith(_BIB_LINES + "\n" + BS + "end{document}")
    data = record.replace("\n", line_end).encode("utf-8")
    assert record_bibliography(data) == RECORD_BIB_NAME
    assert record_bibliography(data + line_end.encode()) == RECORD_BIB_NAME


def test_a_record_with_text_after_the_bibliography_lines_names_none():
    from sci_adk.render.deposit import record_bibliography

    tail = _BIB_LINES + "\n" + BS + "end{lstlisting}\n" + BS + "end{document}\n"
    assert record_bibliography(tail.encode("utf-8")) is None
    assert record_bibliography(None) is None


# -- 4. bib commands: fail on a dangerous one, advise on an unknown one, always ----------------

# Publisher / Crossref commands that print a symbol or change case: harmless, and unknown to
# the list of commands a reference needs.
_HARMLESS_UNKNOWN = [
    "texttimes", "textpm", "textminus", "textmicro", "textcelsius", "texteuro", "textsterling",
    "MakeUppercase", "uppercase", "hspace", "texthyphen",
]
# The commands that can read or write a file, define a macro, change how TeX reads its input
# or end the document (the list the checkers named).
_DANGEROUS = [
    "input", "include", "InputIfFileExists", "def", "edef", "gdef", "xdef", "let", "futurelet",
    "write", "immediate", "openout", "openin", "read", "catcode", "csname", "expandafter",
    "newcommand", "renewcommand", "providecommand", "DeclareRobustCommand", "usepackage",
    "RequirePackage", "documentclass", "begin", "end", "special", "jobname", "endinput",
]


def _bib_entry(title: str, key: str = "X2020") -> str:
    return f"@article{{{key}, title={{{title}}}, year={{2020}}}}"


def _command_lines(problems: list[str]) -> list[str]:
    return [p for p in problems if "command" in p]


def test_harmless_publisher_commands_do_not_fail_and_are_named_in_an_advisory():
    from sci_adk.render.pkgreqs_checks import (
        bib_command_advisories,
        bib_command_problems,
        bib_latex_safety_problems,
    )

    title = " ".join(BS + name + "{x}" for name in _HARMLESS_UNKNOWN) + " " + BS + "nolinkurl{a}"
    bib = _bib_entry(title)
    assert _command_lines(bib_latex_safety_problems(bib)) == []
    assert bib_command_problems(bib) == []
    notes = bib_command_advisories(bib)
    assert len(notes) == 1, notes
    for name in _HARMLESS_UNKNOWN:
        assert BS + name in notes[0]
    assert "entry 'X2020'" in notes[0]


@pytest.mark.parametrize("name", _DANGEROUS)
def test_a_dangerous_command_fails(name):
    from sci_adk.render.pkgreqs_checks import (
        bib_command_advisories,
        bib_command_problems,
        bib_latex_safety_problems,
    )

    bib = _bib_entry("x " + BS + name + "{m} y")
    lines = bib_command_problems(bib)
    assert len(lines) == 1 and BS + name in lines[0], lines
    assert _command_lines(bib_latex_safety_problems(bib)) == lines
    assert bib_command_advisories(bib) == []


def test_every_command_on_the_deny_list_fails_and_none_is_safe():
    from sci_adk.render.bib_latex import DANGEROUS_COMMANDS, SAFE_COMMANDS
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    assert not DANGEROUS_COMMANDS & SAFE_COMMANDS
    assert set(_DANGEROUS) <= DANGEROUS_COMMANDS
    for name in sorted(DANGEROUS_COMMANDS):
        assert bib_command_problems(_bib_entry("$" + BS + name + "$")), name


@pytest.mark.parametrize("value", ["x^^5cinput{m}", "$x^^5cinput{m}$"], ids=["text", "math"])
def test_caret_notation_fails_in_text_and_in_math(value):
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    assert any("'^^'" in p for p in bib_command_problems(_bib_entry(value)))


def test_a_url_with_a_backslash_fails():
    # Changed in the fourth pass (test_latex_sanitize_round4.py): hyperref reads a URL as TeX,
    # so a backslash in one is a command that runs, not a character the url package prints.
    from sci_adk.render.pkgreqs_checks import bib_command_advisories, bib_command_problems

    bib = "@misc{X2020, title={T}, url={http://a.org/" + BS + "input}, year={2020}}"
    problems = bib_command_problems(bib)
    assert len(problems) == 1 and "a backslash" in problems[0] and "URL" in problems[0]
    assert bib_command_advisories(bib) == []


def _rendered_run(tmp_path, spec_id):
    from tests.test_si_authoring_m6 import _compile, _si_citing

    run_dir, _ = _compile(tmp_path, spec_id, _si_citing("A2020"))
    return run_dir


def test_verify_fails_a_dangerous_bib_command_without_a_publishing_contract(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "bib-always")
    assert not (run_dir / "pubreqs.json").exists()
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + _bib_entry("x " + BS + "input{m}", "Z2020"),
                   encoding="utf-8")
    report = verify_run(run_dir)
    lines = [p for p in report.paper_requirements_problems if BS + "input" in p]
    assert len(lines) == 1 and "references.bib entry 'Z2020'" in lines[0], lines
    assert not report.passed


def test_verify_names_a_dangerous_command_once_with_a_contract(tmp_path):
    from sci_adk.cli import main
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "bib-once")
    assert main(["pubreqs", "freeze", str(run_dir), "--defaults"]) == 0
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + _bib_entry("x " + BS + "def" + BS + "y{}", "Z2020"),
                   encoding="utf-8")
    report = verify_run(run_dir)
    assert len([p for p in report.paper_requirements_problems if BS + "def" in p]) == 1


def test_verify_checks_the_deposit_bibliography_and_advises_on_unknown_commands(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "bib-deposit")
    deposit = run_dir / "paper" / "deposit"
    deposit.mkdir(parents=True, exist_ok=True)
    (deposit / "references.bib").write_text(_bib_entry("x " + BS + "write18{ls}"), encoding="utf-8")
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + _bib_entry(BS + "texttimes{} 3", "Z2020"),
                   encoding="utf-8")
    report = verify_run(run_dir)
    assert any("deposit/references.bib" in p and BS + "write" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems
    assert not any(BS + "texttimes" in p for p in report.paper_requirements_problems)
    assert any(BS + "texttimes" in n and "Z2020" in n for n in report.paper_advisory)


def test_the_package_gate_advises_on_unknown_commands(tmp_path):
    from sci_adk.loop.verify import _check_package_requirements
    from tests.test_si_bib_integrity import _assemble_pkg_with_bibs

    si_bib = "@article{A2020, title={Alpha " + BS + "textpm{} 1}, doi={10.1000/a}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(tmp_path, main_bib=si_bib, si_bib=si_bib)
    problems, warnings, _runs, _repro = _check_package_requirements(ws, ws / "package", pkgreqs)
    assert not any(BS + "textpm" in p for p in problems)
    assert any(BS + "textpm" in w and "package_src/references.bib" in w for w in warnings)


def test_render_warns_about_a_dangerous_command_in_the_bib_it_writes(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "bib-render")
    (run_dir / "literature").mkdir(parents=True, exist_ok=True)
    (run_dir / "literature" / "references.bib").write_text(
        _bib_entry("x " + BS + "input{m}", "Doe2020"), encoding="utf-8"
    )
    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    err = capsys.readouterr().err
    assert any(
        line.startswith("  warning: ") and BS + "input" in line and "Doe2020" in line
        for line in err.splitlines()
    ), err


# -- 8. one short line per command, the rule once ---------------------------------------------

def test_each_command_line_is_short_and_each_rule_is_stated_once():
    from sci_adk.render.paper import _PASSING_COMMANDS, _PLAIN_RULE, prose_warnings

    bad = BS + "textbf{a} " + BS + "emph{b} " + BS + "geq "
    prose = PaperProse(title="On " + BS + "ref{x}", abstract=bad, methods=bad, results=bad)
    lines = prose_warnings(prose, SIProse(overview=bad, notes=bad))
    commands = [line for line in lines if line.endswith(" prints as literal text")]
    assert len(commands) == 1 + 5 * 3, lines
    assert all(len(line) < 70 for line in commands), max(commands, key=len)
    assert lines.count(_PASSING_COMMANDS) == 1
    assert lines.count(_PLAIN_RULE) == 1
    assert len(lines) == len(commands) + 2


def test_the_plain_rule_is_left_out_when_only_prose_slots_warn():
    from sci_adk.render.paper import _PASSING_COMMANDS, _PLAIN_RULE, prose_warnings

    lines = prose_warnings(PaperProse(methods=BS + "textbf{a}"))
    assert lines == ["prose slot 'methods': " + BS + "textbf prints as literal text",
                     _PASSING_COMMANDS]
    assert _PLAIN_RULE not in prose_warnings(PaperProse(methods=BS + "textbf{a}"))
    assert prose_warnings(PaperProse(author="A " + BS + "and B"))[-1] == _PLAIN_RULE
    assert prose_warnings(None) == []


def test_the_cli_render_prints_the_rule_once(tmp_path, capsys):
    from sci_adk.cli import main
    from sci_adk.render.paper import _PASSING_COMMANDS
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "rule-once")
    prose = tmp_path / "prose.json"
    bad = BS + "textbf{a} " + BS + "emph{b}"
    prose.write_text(PaperProse(methods=bad, results=bad, discussion=bad).model_dump_json(),
                     encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir), "--prose", str(prose)]) == 0
    err = capsys.readouterr().err
    assert err.count(_PASSING_COMMANDS) == 1
    assert err.count("prints as literal text\n") == 6


# -- 9. a replaced character is named ---------------------------------------------------------

def test_a_character_replaced_by_the_placeholder_is_named_per_slot():
    from sci_adk.render.paper import _PLACEHOLDER_RULE, placeholder_warnings, prose_warnings

    prose = PaperProse(
        title="On " + chr(0x126) + "alite", author="J. " + chr(0x13F) + "lull",
        methods="Samples " + chr(0x4E2D) + chr(0x6587) + " and " + chr(0x1F600) + " and "
        + chr(0x4E2D) + ".",
    )
    lines = placeholder_warnings(prose, SIProse(notes="Note " + chr(0x167) + "."))
    assert [line.split("'")[1] for line in lines] == ["title", "author", "methods", "notes"]
    assert "U+0126 (LATIN CAPITAL LETTER H WITH STROKE)" in lines[0]
    assert "U+013F" in lines[1]
    assert lines[2].count("U+4E2D") == 1 and "U+6587" in lines[2] and "U+1F600" in lines[2]
    assert lines[3].startswith("SI prose slot 'notes': U+0167")
    assert prose_warnings(prose).count(_PLACEHOLDER_RULE) == 1


@pytest.mark.parametrize(
    "text",
    [
        "G" + chr(0xF6) + "del, Erd" + chr(0x151) + "s, " + chr(0x142) + ", " + chr(0xF8),
        chr(0x3B1) + " " + chr(0x2265) + " 3, H" + chr(0x2082) + "O, 30" + chr(0xB0) + "C",
        "Rom" + chr(0x2C) + " " + chr(0x218) + "tefan " + chr(0x21A),
        "fullwidth " + chr(0xFF21) + chr(0xFF3C),
        "a" + chr(0x301) + " combining",
    ],
    ids=["latin-accents", "curated-symbols", "latin-extended-b-folds", "fullwidth", "combining"],
)
def test_a_character_the_sanitizer_typesets_or_folds_is_not_named(text):
    from sci_adk.render.paper import placeholder_warnings

    assert placeholder_warnings(PaperProse(methods=text, title=text, author=text)) == []


def test_the_placeholder_line_names_eight_characters_and_counts_the_rest():
    from sci_adk.render.paper import placeholder_warnings

    text = "".join(chr(0x4E00 + i) for i in range(11))
    (line,) = placeholder_warnings(PaperProse(methods=text))
    assert line.count("U+") == 8 and ", and 3 more print(s) as '?'" in line


def test_a_character_only_inside_a_fact_macro_argument_is_not_named():
    from sci_adk.render.paper import placeholder_warnings

    assert placeholder_warnings(PaperProse(methods=BS + "status{h" + chr(0x4E2D) + "}")) == []


def test_the_cli_render_names_a_replaced_character(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "placeholder")
    prose = tmp_path / "prose.json"
    prose.write_text(PaperProse(results="Data " + chr(0x4E2D) + ".").model_dump_json(),
                     encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir), "--prose", str(prose)]) == 0
    err = capsys.readouterr().err
    assert "warning: prose slot 'results': U+4E2D (CJK UNIFIED IDEOGRAPH-4E2D)" in err


# -- 5. a control character inside a fact macro or a heading: render and the warnings agree ---

_BEL = chr(7)


@pytest.mark.parametrize("slot", ["abstract", "methods"])
def test_a_control_character_inside_a_fact_macro_name_is_substituted_and_not_warned(slot):
    text = ("Slope " + BS + "ev" + _BEL + "val{ev-1}{effect_size} (" + BS + "sta" + _BEL
            + "tus{hyp-t1}).")
    tex = _draft(**{slot: text})
    assert "Slope 1.5 (" in tex and "evval" not in tex and "status" not in tex
    assert literal_command_warnings(PaperProse(**{slot: text})) == []


def test_a_control_character_inside_a_heading_name_in_a_section_is_a_heading():
    text = BS + "para" + _BEL + "graph{Data.} Text."
    assert BS + "paragraph{Data.} Text." in _draft(methods=text)
    assert literal_command_warnings(PaperProse(methods=text)) == []


def test_a_control_character_inside_a_heading_name_in_the_abstract_is_refused():
    text = BS + "para" + _BEL + "graph{Data.} Text."
    with pytest.raises(ValueError, match="abstract"):
        _draft(abstract=text)
    assert literal_command_warnings(PaperProse(abstract=text)) == []


def test_a_control_character_inside_a_novelty_name_is_novelty_markup():
    # Unbacked by the record either way: render refuses both alike, and neither warns.
    clean = BS + "novelty{result}{hyp-t1}{No earlier study reports this}."
    dirty = clean.replace("novelty", "nov" + _BEL + "elty")
    errors = []
    for text in (clean, dirty):
        with pytest.raises(ValueError) as caught:
            _draft(methods=text)
        errors.append(str(caught.value))
        assert literal_command_warnings(PaperProse(methods=text)) == []
    assert errors[0] == errors[1]


# -- 6. the run verb prints the warnings -------------------------------------------------------

def test_the_run_verb_prints_a_literal_command_warning(tmp_path, capsys):
    from sci_adk.cli import main

    proposal = tmp_path / "p.md"
    proposal.write_text(
        "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n", encoding="utf-8"
    )
    prose = tmp_path / "prose.json"
    prose.write_text(PaperProse(methods="Bold " + BS + "textbf{x}.").model_dump_json(),
                     encoding="utf-8")
    capsys.readouterr()
    rc = main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "run-warn",
               "--prose", str(prose)])
    err = capsys.readouterr().err
    assert rc == 0, err
    assert "warning: prose slot 'methods': " + BS + "textbf prints as literal text" in err


# -- 14. the package record script escapes like render ----------------------------------------

def _make_si_module(path=None):
    """The shipped ``make_si.py`` (the template, or an assembled package's copy) as a module."""
    import importlib.util
    from pathlib import Path

    import sci_adk

    path = path or (
        Path(sci_adk.__file__).parent / "templates" / "research-workspace" / "package"
        / "04_scripts" / "make_si.py"
    )
    spec = importlib.util.spec_from_file_location("sci_adk_test_make_si", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _escape_sample() -> list[str]:
    import random

    from sci_adk.render.paper import _UNICODE_MAP

    singles = [chr(cp) for cp in range(0x3000) if not 0xD800 <= cp <= 0xDFFF]
    singles += [chr(cp) for cp in range(0xFE10, 0xFFF0)]  # small and fullwidth forms
    singles += [chr(cp) for cp in (0x4E2D, 0x1F600, 0x1D400, 0x1D4D0, 0x1D7CE, 0x20AC)]
    pieces = singles + list(_UNICODE_MAP) + [
        "a\n\nb", "a\r\nb\rc", " lead and trail \t", "x" + chr(0) + chr(7) + chr(0x7F) + "y",
        BS + "input{x}", "50% & a_b #1 $x$ ^ ~ {}", "H" + chr(0x2082) + "O " + chr(0x2265) + " 3",
        "e" + chr(0x301) + chr(0x323), "fw " + chr(0xFF3C) + "input" + chr(0xFF5B) + "x" + chr(0xFF5D),
    ]
    rng = random.Random(20261012)
    mixed = ["".join(rng.choice(pieces) for _ in range(12)) for _ in range(400)]
    return pieces + mixed


def test_the_package_record_script_escapes_exactly_like_render():
    from sci_adk.render.paper import _latex_sanitize, _one_line

    module = _make_si_module()
    mismatches = [s for s in _escape_sample() if module.tex(s) != _latex_sanitize(_one_line(s))]
    assert mismatches == [], [repr(s) for s in mismatches[:5]]


def test_the_package_record_script_carries_render_s_symbol_map():
    from sci_adk.render import paper

    module = _make_si_module()
    assert module._UNICODE_MAP == paper._UNICODE_MAP
    assert module._UNDEFINED_LATIN_A == paper._UNDEFINED_LATIN_A
    assert (module._ACCENT_LO, module._ACCENT_HI) == (paper._ACCENT_LO, paper._ACCENT_HI)


def test_the_package_record_script_imports_nothing_from_sci_adk_to_escape():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(_make_si_module().__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {"tex", "_sanitize", "_one_line"}:
            imports = [n for n in ast.walk(node) if isinstance(n, (ast.Import, ast.ImportFrom))]
            assert imports == [], node.name


def _built_package_record(tmp_path) -> str:
    """The package record ``make_si.py`` builds for a workspace whose narrative.json holds
    blank lines, specials, a command and characters to fold or placehold."""
    import json

    from sci_adk.render.package import assemble_package
    from tests.test_si_authoring_m6 import _freeze_pkgreqs, _pkgreqs_obj, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    assemble_package(ws, _pkgreqs_obj(ws))
    package = ws / "package"
    (package / "narrative.json").write_text(json.dumps({
        "title": "Record of\n\nH" + chr(0x2082) + "O {x} " + BS + "input{marker}",
        "author": "A. Author\n\n& B. " + chr(0x4E2D),
        "runs": [{"id": "run-alpha", "label": "first\n\nlabel 50%", "section": "Band\n\n#1"}],
    }), encoding="utf-8")
    _make_si_module(package / "04_scripts" / "make_si.py").build()
    return (package / "06_provenance" / "record.tex").read_text(encoding="utf-8")


def test_the_package_record_is_built_with_one_line_escaped_fields(tmp_path):
    record = _built_package_record(tmp_path)
    assert BS + "title{Record of H$_2$O " + BS + "{x" + BS + "} " + BS + "textbackslash{}input" \
        + BS + "{marker" + BS + "}}" in record
    assert BS + "author{A. Author " + BS + "& B. ?}" in record
    assert "first label 50" + BS + "%" in record
    assert BS + "textit{Band " + BS + "#1}" in record


@needs_tex
def test_the_package_record_with_hostile_narrative_fields_compiles(tmp_path):
    record = _built_package_record(tmp_path)
    build = tmp_path / "build"
    build.mkdir()
    (build / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")
    assert _build(build, record, "record") == []
    assert _MARKER not in _pdf_text(build, "record")
