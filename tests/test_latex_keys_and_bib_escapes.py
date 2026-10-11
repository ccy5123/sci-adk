"""
Escape bypasses left after the first hardening pass (``test_latex_sanitize_hardening.py``).

Found by independent checkers on the hardened render path (render and verify both exited 0):

  1. A ``\\ref``/``\\autoref``/``\\cite``/``\\citep``/``\\citet`` key passed verbatim whatever it
     held except braces and a blank line. ``\\ref{\\input <file> }`` made pdflatex read the file
     into the PDF; ``%``, ``#``, a backslash (``fig:a\\_b``), ``\\par`` and non-ASCII letters
     (Cyrillic, Greek, ``Ș``, a fullwidth character) in a key stopped it, with no warning. A key
     now holds only ASCII letters, digits, ``: _ . , ; + / = @ -``, spaces, tabs and single line
     breaks; any other key stays literal text and the warning names the command.
  2. Eight letters of the passthrough window U+00C0..U+017E have no LaTeX glyph (Ħ ħ ĸ Ŀ ŀ ŉ Ŧ
     ŧ) and stopped pdflatex under both render preambles; the bib copy already knew them
     (``bib_latex._UNDEFINED_LATIN_A``). They now take the fold/placeholder path; the two
     modules share one constant.
  3. The bib copy kept the ASCII fold of a compatibility character raw: a fullwidth
     ``\\input{<file>}`` in a bib title came out as ``\\input{<file>}`` and pdflatex read the
     file from the ``.bbl``; fullwidth ``& % # _`` and C0 controls came out raw too. The fold
     is now escaped (braces as commands, so BibTeX's brace count holds; boxed in math) and
     controls are dropped. Verify names any command in a printed bib value that is not an
     accent, letter, markup, symbol or math command, and ``^^`` in math (TeX's character-code
     notation: ``^^5c`` is a backslash); the copy writes math ``^^`` as two printed carets.
  4. A blank line in a claim statement stopped pdflatex on the record (``\\subsection{}``);
     the same held for every macro argument the renderers fill with free text or an id
     (``\\item[...]``, ``\\texttt{}``, a table cell, a figure caption, an axis label). Each is
     now one line.
"""

from __future__ import annotations

import re
import unicodedata

import pytest

from sci_adk.cli import main
from sci_adk.render import bib_latex
from sci_adk.render.bib_latex import latex_safe_bib, paper_bib
from sci_adk.render.figures import ImageFigureSpec
from sci_adk.render.paper import (
    _UNICODE_MAP,
    _latex_sanitize,
    _latex_sanitize_prose,
    literal_command_warnings,
    render_paper_latex,
)
from sci_adk.render.pkgreqs_checks import bib_latex_safety_problems
from sci_adk.render.prose import PaperProse
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import (
    _PREAMBLES,
    _compile_with_bib,
    _entry,
    _log_errors,
    _render_preamble,
    _run,
    _title_of,
    needs_tex,
)
from tests.test_latex_sanitize_hardening import _build, _pdf_text, fw
from tests.test_render_record_only import _seed
from tests.test_si import _basic_record, _quant_ev

BS = chr(92)  # a backslash, spelled out so no escape in this file is ambiguous
_CITE_COMMANDS = ["ref", "autoref", "cite", "citep", "citet"]
_MARKER = "MARKERTEXTQZX"


def _draft(**slots: str) -> str:
    spec, claims, evidence = _basic_record()
    return render_paper_latex(spec, claims, evidence, prose=PaperProse(**slots))


# -- 1. a key holds label characters only ----------------------------------------------------

_BAD_KEYS = {
    "input": BS + "input marker ",
    "hash": "a#b",
    "percent": "a%b",
    "par": BS + "par",
    "end": BS + "end",
    "escaped-underscore": "fig:a" + BS + "_b",
    "undefined-command": BS + "undefinedcs",
    "dollar": "a$b",
    "ampersand": "a&b",
    "caret": "a^b",
    "tilde": "fig~a",
    "cyrillic": chr(0x416),
    "greek": chr(0x3B1) + chr(0x3B2),
    "s-comma": chr(0x218),
    "cjk": "k" + chr(0x4E2D),
    "fullwidth-backslash": chr(0xFF3C) + "input x",
    "fullwidth-letter": chr(0xFF21),
    "accent": "G" + chr(0xF6) + "del",
}


@pytest.mark.parametrize("cmd", _CITE_COMMANDS)
@pytest.mark.parametrize("key", list(_BAD_KEYS.values()), ids=list(_BAD_KEYS))
def test_a_key_holding_anything_but_label_characters_stays_literal(cmd, key):
    text = BS + cmd + "{" + key + "} x"
    assert _latex_sanitize_prose(text) == _latex_sanitize(text)
    assert BS + cmd + "{" not in _latex_sanitize_prose(text)


@pytest.mark.parametrize("cmd", _CITE_COMMANDS)
@pytest.mark.parametrize("key", list(_BAD_KEYS.values()), ids=list(_BAD_KEYS))
def test_a_key_that_stays_literal_is_named_in_a_warning(cmd, key):
    warnings = literal_command_warnings(PaperProse(methods=BS + cmd + "{" + key + "} x"))
    assert warnings, "no warning"
    assert warnings[0].startswith(
        "prose slot 'methods': " + BS + cmd + " prints as literal text"
    ), warnings


@pytest.mark.parametrize("cmd", _CITE_COMMANDS)
@pytest.mark.parametrize(
    "key",
    ["fig:a_b", "Smith2020a", "Doe2020_SI", "a, b", "a,b;c", "x+y/z=w@v-u.t", "", "a\tb",
     "Arnot2006,\nArman2012"],
    ids=["underscore", "suffix", "si-key", "comma-space", "semicolon", "punctuation", "empty",
         "tab", "line-break"],
)
def test_a_key_of_label_characters_still_passes(cmd, key):
    text = BS + cmd + "{" + key + "}"
    assert _latex_sanitize_prose(text) == text
    assert literal_command_warnings(PaperProse(methods=text)) == []


def test_the_warning_says_what_a_key_may_hold():
    from sci_adk.render.paper import prose_warnings

    # Stated once per render, after the per-command lines (round 3).
    line = prose_warnings(PaperProse(methods=BS + "cite{a#b}"))[-1]
    assert "ASCII letters, digits" in line
    assert "no blank line" in line


@needs_tex
@pytest.mark.parametrize("cmd", _CITE_COMMANDS)
def test_a_draft_with_hostile_keys_compiles_and_reads_no_file(tmp_path, cmd):
    (tmp_path / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")
    keys = " ".join(BS + cmd + "{" + key + "}" for key in _BAD_KEYS.values())
    tex = _draft(methods="Keys: " + keys + " end.")
    assert _build(tmp_path, tex, "draft") == []
    assert _MARKER not in _pdf_text(tmp_path, "draft")


@needs_tex
def test_the_old_keys_would_stop_pdflatex_or_read_the_file(tmp_path):
    # Why: what the renderer used to emit for \ref{\input marker } and \cite{a#b} (the
    # checkers saw the file read into the PDF; here pdflatex stops on the \input).
    (tmp_path / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")
    tex = _draft(methods="PLACE").replace("PLACE", BS + "ref{" + BS + "input marker }")
    errors = _build(tmp_path, tex, "old")
    read = (tmp_path / "old.pdf").is_file() and _MARKER in _pdf_text(tmp_path, "old")
    assert errors or read
    tex = _draft(methods="PLACE").replace("PLACE", BS + "cite{a#b}")
    assert any("Illegal parameter number" in e for e in _build(tmp_path, tex, "hash"))


@needs_tex
def test_the_cli_render_warns_about_a_hostile_key_and_the_draft_compiles(tmp_path, capsys):
    run_dir = _seed(tmp_path, "key-hash")
    prose = tmp_path / "prose.json"
    prose.write_text(
        PaperProse(methods="See " + BS + "cite{a#b} and " + BS + "ref{a%b}.").model_dump_json(),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["render", str(run_dir), "--prose", str(prose)]) == 0
    err = capsys.readouterr().err
    assert "warning: prose slot 'methods': " + BS + "cite prints as literal text" in err
    assert "warning: prose slot 'methods': " + BS + "ref prints as literal text" in err
    tex = (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    assert _build(build, tex, "draft") == []


# -- 2. the eight Latin Extended-A letters LaTeX has no glyph for -----------------------------

_NO_GLYPH = {
    chr(0x126): "?", chr(0x127): "?", chr(0x138): "?", chr(0x13F): "L?", chr(0x140): "l?",
    chr(0x149): "?n", chr(0x166): "?", chr(0x167): "?",
}


def test_the_letters_without_a_glyph_take_the_fold_and_placeholder_path():
    for letter, expected in _NO_GLYPH.items():
        assert _latex_sanitize(letter) == expected, hex(ord(letter))
        assert _latex_sanitize_prose(letter) == expected, hex(ord(letter))


def test_the_paper_and_the_bib_copy_share_one_set_of_letters_without_a_glyph():
    from sci_adk.render import paper

    assert bib_latex._UNDEFINED_LATIN_A is paper._UNDEFINED_LATIN_A
    assert set(_NO_GLYPH) == set(paper._UNDEFINED_LATIN_A)


def test_the_other_letters_of_the_window_still_pass_unchanged():
    from sci_adk.render import paper

    for cp in range(0xC0, 0x17F):
        ch = chr(cp)
        if ch in _UNICODE_MAP or ch in paper._UNDEFINED_LATIN_A:
            continue
        assert _latex_sanitize(ch) == ch, hex(cp)


@needs_tex
@_PREAMBLES
def test_every_letter_of_the_window_compiles_as_sanitized(tmp_path, figure_bearing):
    # Every code point of U+00C0..U+017E the curated map does not own, as the sanitizer emits
    # it, one per line, under the preamble a render emits (Latin Modern / Times).
    chars = [chr(cp) for cp in range(0xC0, 0x17F) if chr(cp) not in _UNICODE_MAP]
    preamble, dropped = _render_preamble(figure_bearing)
    first = len(preamble) + 2
    lines = preamble + [r"\begin{document}"] + [
        _latex_sanitize(ch) + r"\par" for ch in chars
    ] + [r"\end{document}"]
    (tmp_path / "window.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    status = _run(["pdflatex", "-interaction=nonstopmode", "window.tex"], tmp_path)
    log = (tmp_path / "window.log").read_text(encoding="utf-8", errors="replace")
    failing = sorted(
        {chars[n - first] for n in map(int, re.findall(r"^l\.(\d+)", log, re.M))
         if 0 <= n - first < len(chars)}
    )
    assert status == 0 and not _log_errors(log) and not failing, (
        f"fails on {failing!r} (errors {_log_errors(log)[:5]}; dropped {dropped})"
    )


@needs_tex
def test_a_draft_with_maltese_and_sami_letters_compiles(tmp_path):
    letters = "".join(_NO_GLYPH)
    tex = _draft(title=chr(0x126) + "amrun " + chr(0x166), methods="Letters: " + letters + ".")
    assert _build(tmp_path, tex, "draft") == []


# -- 3. the bib copy: compatibility folds escaped, controls dropped ---------------------------

_FOLDED = {
    0xFF3C: r"\textbackslash{}", 0xFF5B: r"\textbraceleft{}", 0xFF5D: r"\textbraceright{}",
    0xFF06: r"\&", 0xFF05: r"\%", 0xFF03: r"\#", 0xFF3F: r"\_", 0xFF04: r"\$",
    0xFF3E: r"\textasciicircum{}", 0xFF5E: r"\textasciitilde{}", 0xFF1C: r"\textless{}",
    0xFF1E: r"\textgreater{}", 0xFF02: '{"}', 0xFE68: r"\textbackslash{}", 0xFE60: r"\&",
    0xFE5F: r"\#",
}


@pytest.mark.parametrize(
    "codepoint", list(_FOLDED), ids=lambda v: f"U+{v:04X}"
)
def test_a_compatibility_form_of_a_special_in_a_bib_title_is_escaped(codepoint):
    assert unicodedata.normalize("NFKC", chr(codepoint)) in BS + "{}&%#_$^~<>\""
    out = latex_safe_bib(_entry("a" + chr(codepoint) + "b"))
    assert _title_of(out) == "a" + _FOLDED[codepoint] + "b"
    assert latex_safe_bib(out) == out  # idempotent
    assert bib_latex_safety_problems(out) == []


def test_a_fullwidth_input_in_a_bib_title_prints_and_never_runs():
    out = latex_safe_bib(_entry(fw(BS + "input{marker}")))
    assert _title_of(out) == r"\textbackslash{}input\textbraceleft{}marker\textbraceright{}"
    assert BS + "input{" not in paper_bib(out)


def test_a_compatibility_form_of_a_special_in_bib_math_is_boxed():
    out = latex_safe_bib(_entry("$a" + chr(0xFF3C) + "b" + chr(0xFF06) + "c$"))
    assert _title_of(out) == r"$a\mbox{\textbackslash{}}b\mbox{\&}c$"
    assert bib_latex_safety_problems(out) == []


def test_ascii_controls_in_a_bib_value_are_dropped():
    raw = "a" + "".join(chr(c) for c in (0x07, 0x08, 0x0B, 0x0C, 0x1B, 0x7F)) + "b"
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == "ab"
    math = latex_safe_bib(_entry("$x" + chr(7) + "y$"))
    assert _title_of(math) == "$xy$"


def test_the_ascii_fold_of_an_ordinary_letter_is_unchanged():
    assert _title_of(latex_safe_bib(_entry(chr(0xFF21) + chr(0xFB01) + "ne"))) == "Afine"


# -- 3. verify: commands and ^^ in a printed bib value ----------------------------------------


@pytest.mark.parametrize(
    "title, command",
    [
        ("x " + BS + "input{m} y", BS + "input"),
        ("x " + BS + "include{m}", BS + "include"),
        ("x " + BS + "end{document}", BS + "end"),
        (BS + "def" + BS + "x{y}", BS + "def"),
        (BS + "csname input" + BS + "endcsname{m}", BS + "csname"),
        (BS + "immediate" + BS + "write18{ls}", BS + "immediate"),
        ("$" + BS + "input{m}$", BS + "input"),
        (BS + "href{http://x.org}{" + BS + "input{m}}", BS + "input"),
        (BS + BS + BS + "input{m}", BS + "input"),
    ],
    ids=["input", "include", "end", "def", "csname", "write18", "in-math", "href-text",
         "after-a-line-break"],
)
def test_verify_names_a_command_no_reference_needs(title, command):
    problems = bib_latex_safety_problems(_entry(title))
    lines = [p for p in problems if "command" in p]
    assert len(lines) == 1, problems
    assert command in lines[0]
    assert "entry 'X2020'" in lines[0]
    assert "literature/references.bib" in lines[0]


@pytest.mark.parametrize(
    "title",
    [
        BS + "textit{n}-Octanol and " + BS + "emph{in vivo}",
        "{" + BS + '"O}zt' + BS + "\"urk, " + BS + "'e, {" + BS + "v{S}}, {" + BS
        + "textcommabelow{S}}, {" + BS + "i}, {" + BS + "o}, " + BS + "ss, {" + BS + "AE}",
        "CO" + BS + "textsubscript{2} and " + BS + "textsuperscript{14}C",
        "$" + BS + "alpha$, $" + BS + "times$, $" + BS + "mathrm{CO}_2$, $" + BS + "geq 3$",
        "R " + BS + "& D, 50" + BS + "%, " + BS + "#1, a" + BS + "_b",
        "{" + BS + "LaTeX} and " + BS + "url{http://a.org/x_y}",
        BS + BS + "input as text after a line break",
    ],
    ids=["markup", "accents-and-letters", "sub-superscript", "math", "escapes", "logo-url",
         "line-break"],
)
def test_verify_accepts_the_commands_a_reference_carries(title):
    assert [p for p in bib_latex_safety_problems(_entry(title)) if "command" in p] == []


def test_every_command_the_copy_writes_is_accepted():
    # The curated map's commands (in text and in math) and the accent commands.
    raw = "".join(_UNICODE_MAP) + " Lǚ Ștefan ǐ ǭ ḇ ẘ ạ Ȩ"
    out = latex_safe_bib(_entry(raw) + "\n" + _entry("$" + "".join(_UNICODE_MAP) + "$", "Y2020"))
    assert [p for p in bib_latex_safety_problems(out) if "command" in p] == []
    assert [p for p in bib_latex_safety_problems(paper_bib(out)) if "command" in p] == []


def test_verify_names_caret_notation_in_math():
    problems = bib_latex_safety_problems(_entry("$x^^5cinput{m}$"))
    assert any("'^^'" in p for p in problems), problems


def test_the_copy_writes_caret_notation_in_math_as_printed_carets():
    out = latex_safe_bib(_entry("$x^^5cinput{m}$"))
    assert "^^" not in out
    assert _title_of(out) == r"$x\mbox{\textasciicircum{}\textasciicircum{}}5cinput{m}$"
    assert bib_latex_safety_problems(out) == []
    assert latex_safe_bib(out) == out


def test_a_package_bib_command_names_the_package_source():
    problems = bib_latex_safety_problems(
        _entry("x " + BS + "input{m}"), package_source="package_src/references.bib"
    )
    line = next(p for p in problems if "command" in p)
    assert "package_src/references.bib" in line


@needs_tex
@_PREAMBLES
def test_fullwidth_specials_in_a_bib_title_compile_and_read_no_file(tmp_path, figure_bearing):
    (tmp_path / "marker.tex").write_text(_MARKER + "\n", encoding="utf-8")
    title = (
        "Fullwidth " + fw(BS + "input{marker}") + " " + fw("&%#_$^~<>") + " bell" + chr(7)
        + " and $a" + chr(0xFF3C) + "b$ and $x^^5cinput{marker}$"
    )
    store = (
        "@article{Fw2020, author={Doe, Jane}, title={" + title + "}, journal={J}, "
        "year={2020}}\n"
    )
    copy = paper_bib(latex_safe_bib(store))
    assert bib_latex_safety_problems(copy) == []
    errors, bbl, dropped = _compile_with_bib(tmp_path, copy, figure_bearing)
    assert errors == [], f"{errors[:10]} (dropped {dropped})"
    assert BS + "input{" not in bbl
    assert _MARKER not in _pdf_text(tmp_path, "t")


# -- 4. free text and ids in a macro argument are one line ------------------------------------


def _record_with(statement: str | None = None, extra_ev_id: str | None = None) -> str:
    spec, claims, evidence = _basic_record()
    if statement is not None:
        claims = [claims[0].model_copy(update={"statement": statement})]
    if extra_ev_id is not None:
        evidence = evidence + [_quant_ev(extra_ev_id, point=2.0, effect_size=0.5)]
    return render_si_latex(spec, claims, evidence)


def test_a_claim_statement_with_a_blank_line_is_one_subsection_title():
    record = _record_with(statement="First part.\n\n  Second\r\npart.")
    assert r"\subsection{First part. Second part.}" in record


def test_an_evidence_id_with_a_blank_line_is_one_line_in_the_record():
    record = _record_with(extra_ev_id="ev\n\nx")
    assert r"\item[\texttt{ev x}" in record
    assert r"\texttt{ev x} &" in record


def test_a_figure_caption_with_a_blank_line_is_one_line():
    spec, claims, evidence = _basic_record()
    fig = ImageFigureSpec(kind="image", id="fa", caption="A cap.\n\nMore.", image="a.png")
    tex = render_paper_latex(spec, claims, evidence, figures=[fig])
    assert r"\caption{A cap. More.}" in tex


@needs_tex
def test_a_record_with_a_blank_line_in_a_statement_and_an_id_compiles(tmp_path):
    record = _record_with(statement="First part.\n\nSecond part.", extra_ev_id="ev\n\nx")
    assert _build(tmp_path, record, "record") == []


@needs_tex
def test_a_draft_with_a_blank_line_in_a_caption_compiles(tmp_path):
    spec, claims, evidence = _basic_record()
    fig = ImageFigureSpec(kind="image", id="fa", caption="A cap.\n\nMore.", image="a.png")
    tex = render_paper_latex(
        spec, claims, evidence, figures=[fig],
        prose=PaperProse(results="See " + BS + "ref{fig:fa}."),
    )
    # No image file in the build: a rule stands in for the graphic, the caption is as emitted.
    lines = [
        r"\rule{1cm}{1cm}" if BS + "includegraphics" in line else line
        for line in tex.splitlines()
    ]
    assert _build(tmp_path, "\n".join(lines), "draft") == []


@needs_tex
def test_the_old_statement_would_stop_pdflatex(tmp_path):
    record = _record_with(statement="PLACE").replace("PLACE", "First part.\n\nSecond part.")
    assert any("Paragraph ended before" in e for e in _build(tmp_path, record, "old"))

