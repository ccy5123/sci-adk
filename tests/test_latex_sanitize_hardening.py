"""
What the LaTeX sanitizer may never let through, and what the prose passthrough may never pass.

Found by an adversarial pass over the second trial paper's render path (render and verify both
exited 0, pdflatex stopped or read a file):

  1. Escape bypass. ``_latex_sanitize`` escaped the ASCII specials first and then folded each
     non-ASCII character (NFKD), appending the ASCII fallout unescaped. Fullwidth and small-form
     characters fold to live specials: a fullwidth ``\\input{/etc/hostname}`` was read into the
     PDF, a fullwidth ``\\end{document}`` cut the paper short, a fullwidth ``\\paragraph{}``
     slipped past the abstract refusal, and a plain fullwidth ``& # _ $ ^`` stopped pdflatex in
     every prose slot. Now the fold output is escaped like any other text; the curated unicode
     map (subscripts, relations, Greek, the micro sign) is unchanged.
  2. Control characters. C0 controls (BEL, backspace, VT, FF, ESC, ...) and DEL passed through
     and stopped pdflatex in the title, the author, the abstract, every section slot, heading
     text and cite keys. Now line ends are normalized and every C0 control except tab and line
     feed, and DEL, is removed before anything else -- before the passthrough match, so a key
     or a heading can never carry one. C1 controls already became ``?`` through the fold.
  3. A cite or ref whose key spans a blank line passed verbatim and stopped pdflatex
     ("Paragraph ended before \\@citex was complete"); it now stays literal text, like a
     heading holding a blank line. A single line break still passes.
  4. One warning rule: every backslash command the sanitizer prints as literal text is named,
     per slot and command (:func:`paper.literal_command_warnings`).
  5. ``\\eqref`` no longer passes: a figure-less draft loads no amsmath, and prose cannot carry
     an equation, so it could never resolve.
  6. ``sci-adk run --prose`` with a heading in the abstract ended in a traceback; it now exits
     2 with the message, as ``render`` does.

Also: whitespace runs (blank lines included) in a title or the author collapse to one space --
a blank line in ``\\author{}`` stopped pdflatex ("Paragraph ended before \\author was
complete").
"""

from __future__ import annotations

import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.render.authored_si import render_authored_si_latex
from sci_adk.render.figures import ImageFigureSpec, order_figures_by_reference
from sci_adk.render.paper import (
    _UNICODE_MAP,
    _latex_sanitize,
    _latex_sanitize_prose,
    render_paper_latex,
)
from sci_adk.render.prose import AuthoredSI, PaperProse, SIProse, SISection
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import _USEPACKAGE_RE, _loadable, _log_errors, _run, needs_tex
from tests.test_render_merge_wiring import PROPOSAL
from tests.test_si import _basic_record

BS = chr(92)  # a backslash, spelled out so no escape in this file is ambiguous


def fw(text: str) -> str:
    """``text`` with every printable ASCII character but the space as its fullwidth form
    (U+FF01..U+FF5E), each of which NFKD-folds back to the ASCII character."""
    return "".join(chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c for c in text)


def _warnings(prose=None, si_prose=None) -> list[str]:
    from sci_adk.render.paper import literal_command_warnings

    return literal_command_warnings(prose, si_prose)


def _draft(**slots: str) -> str:
    spec, claims, evidence = _basic_record()
    return render_paper_latex(spec, claims, evidence, prose=PaperProse(**slots))


def _record(prose: SIProse) -> str:
    spec, claims, evidence = _basic_record()
    return render_si_latex(spec, claims, evidence, prose=prose)


# The ten ASCII specials and the escaped form the sanitizer gives each.
_ESCAPED = {
    BS: r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def _without_escapes(tex: str) -> str:
    for form in sorted(_ESCAPED.values(), key=len, reverse=True):
        tex = tex.replace(form, "")
    return tex


# -- 1. the fold output is escaped ---------------------------------------------------------


@pytest.mark.parametrize(
    "codepoint, special",
    [
        (0xFF3C, BS), (0xFF5B, "{"), (0xFF5D, "}"), (0xFF06, "&"), (0xFF05, "%"),
        (0xFF03, "#"), (0xFF3F, "_"), (0xFF04, "$"), (0xFF3E, "^"), (0xFF5E, "~"),
        (0xFE60, "&"), (0xFE5F, "#"), (0xFE68, BS), (0xFE69, "$"), (0xFE6A, "%"),
        (0xFE5B, "{"), (0xFE5C, "}"), (0xFE4D, "_"),
    ],
    ids=lambda v: f"U+{v:04X}" if isinstance(v, int) else None,
)
def test_a_compatibility_form_of_a_special_is_escaped(codepoint, special):
    assert unicodedata.normalize("NFKD", chr(codepoint)) == special
    assert _latex_sanitize(chr(codepoint)) == _ESCAPED[special]
    assert _latex_sanitize_prose(chr(codepoint)) == _ESCAPED[special]


def test_a_fullwidth_backslash_prints_as_a_backslash_and_never_acts_as_one():
    assert _latex_sanitize(chr(0xFF3C) + "&") == r"\textbackslash{}\&"
    out = _latex_sanitize_prose(fw(BS + "input{/etc/hostname}"))
    assert out == r"\textbackslash{}input\{/etc/hostname\}"
    assert _latex_sanitize_prose(fw(BS + "end{document}")) == r"\textbackslash{}end\{document\}"


def test_no_codepoint_folds_to_a_raw_special_or_a_control():
    # Every codepoint the curated map does not own: what the sanitizer emits, its escaped
    # forms taken out, holds no LaTeX special and no control character.
    for cp in range(0x80, 0x20000):
        if 0xD800 <= cp <= 0xDFFF or chr(cp) in _UNICODE_MAP:
            continue
        out = _without_escapes(_latex_sanitize(chr(cp)))
        assert not set(out) & set(_ESCAPED), (hex(cp), out)
        assert not any(ord(c) < 0x20 or ord(c) == 0x7F for c in out), (hex(cp), out)


def test_a_fullwidth_heading_in_the_abstract_is_literal_text_not_a_heading():
    tex = _draft(abstract=fw(BS + "paragraph{Aim.}") + " We measured it.", methods="M.")
    assert r"\textbackslash{}paragraph\{Aim.\} We measured it." in tex
    assert r"\begin{abstract}" + "\n" + r"\paragraph" not in tex


def test_the_curated_unicode_map_is_unchanged():
    # Byte for byte what the sanitizer gave before the fold output was escaped.
    cases = {
        "H" + chr(0x2082) + "O": "H$_2$O",
        "x " + chr(0x2265) + " 5": r"x $\geq$ 5",
        chr(0x3B1) + " decay": r"$\alpha$ decay",
        "5 " + chr(0xB5) + "m": r"5 $\mu$m",
        "G" + chr(0xF6) + "del Erd" + chr(0x151) + "s " + chr(0x142) + " " + chr(0xF8) + " "
        + chr(0xE9): "G" + chr(0xF6) + "del Erd" + chr(0x151) + "s " + chr(0x142) + " "
        + chr(0xF8) + " " + chr(0xE9),
        chr(0x218) + "i " + chr(0x21A): "Si T",
        chr(0x2212) + " 0.8": "$-$ 0.8",
        chr(0xB0) + "C": r"\textdegree{}C",
        chr(0x2018) + "q" + chr(0x2019) + " " + chr(0x201C) + "d" + chr(0x201D) + " "
        + chr(0x2026): r"`q' ``d'' \ldots{}",
        chr(0x2013) + " " + chr(0x2014): "-- ---",
        chr(0x1D465): "x",
        chr(0x4E2D) + chr(0x6587): "??",
        chr(0xA0) + "nbsp": " nbsp",
        chr(0xFB01) + " ligature": "fi ligature",
        chr(0x2126) + " ohm": "? ohm",
    }
    for given, expected in cases.items():
        assert _latex_sanitize(given) == expected, given
        assert _latex_sanitize_prose(given) == expected, given


# -- 2. control characters -----------------------------------------------------------------

_CONTROLS = "".join(chr(c) for c in (0x00, 0x01, 0x07, 0x08, 0x0B, 0x0C, 0x1B, 0x1F, 0x7F))


def test_c0_controls_and_del_are_removed_tab_and_line_feed_kept():
    assert _latex_sanitize("a" + _CONTROLS + "b") == "ab"
    assert _latex_sanitize("a\tb\nc") == "a\tb\nc"
    assert _latex_sanitize_prose("a" + _CONTROLS + "b") == "ab"


def test_line_ends_are_normalized():
    assert _latex_sanitize("a\r\nb\rc") == "a\nb\nc"
    assert _latex_sanitize_prose("a\r\nb\rc") == "a\nb\nc"


def test_c1_controls_become_the_placeholder():
    assert _latex_sanitize(chr(0x80) + chr(0x85) + chr(0x9F)) == "???"


def test_a_key_or_a_heading_never_carries_a_control():
    assert _latex_sanitize_prose(BS + "citep{Doe" + chr(7) + "2020}") == BS + "citep{Doe2020}"
    assert _latex_sanitize_prose(BS + "ref{fig:a" + chr(0x7F) + "}") == BS + "ref{fig:a}"
    assert _latex_sanitize_prose(BS + "paragraph{Da" + chr(0x0C) + "ta.} x") == (
        BS + "paragraph{Data.} x"
    )


def test_a_control_inside_the_command_does_not_hide_a_heading_from_the_abstract_refusal():
    # The refusal sees what the sanitizer sees: with the BEL removed this is a heading.
    with pytest.raises(ValueError, match="abstract"):
        _draft(abstract=BS + "paragraph" + chr(7) + "{Aim.} We measured it.")


def test_controls_are_removed_from_every_slot_of_the_draft_and_the_record():
    bel = chr(7)
    tex = _draft(
        title="A" + bel + "title", author="An" + bel + "author", abstract="Ab" + bel + "stract.",
        methods=BS + "paragraph{He" + bel + "ad.} Me" + bel + "thods " + BS + "citep{K" + bel
        + "1}.",
    )
    assert bel not in tex
    assert r"\title{Atitle}" in tex and r"\author{Anauthor}" in tex
    assert BS + "paragraph{Head.} Methods " + BS + "citep{K1}." in tex
    record = _record(SIProse(overview="O" + bel + "v.", notes="N" + chr(0x1B) + "otes."))
    assert bel not in record and chr(0x1B) not in record
    assert "Ov." in record and "Notes." in record



def test_figure_numbers_follow_the_cleaned_refs():
    # The renderer numbers the figures from the prose refs, and the compiler re-derives the
    # numbers from the rendered draft to name the copied image files: both read the key as
    # the sanitizer leaves it, without its control character.
    spec, claims, evidence = _basic_record()
    figures = [
        ImageFigureSpec(kind="image", id="alpha", caption="A.", image="a.png"),
        ImageFigureSpec(kind="image", id="beta", caption="B.", image="b.png"),
    ]
    results = "First " + BS + "ref{fig:be" + chr(7) + "ta}, then " + BS + "ref{fig:alpha}."
    tex = render_paper_latex(
        spec, claims, evidence, prose=PaperProse(results=results), figures=figures
    )
    assert [f.id for _, f in order_figures_by_reference(figures, tex)] == ["beta", "alpha"]
    assert tex.index(r"\label{fig:beta}") < tex.index(r"\label{fig:alpha}")

# -- 3. a cite or ref key cannot span a blank line -----------------------------------------


@pytest.mark.parametrize("cmd", ["cite", "citep", "citet", "ref", "autoref"])
def test_a_key_holding_a_blank_line_stays_literal(cmd):
    text = BS + cmd + "{Arnot2006,\n\nArman2012}"
    assert _latex_sanitize_prose(text) == _latex_sanitize(text)
    assert BS + cmd + "{" not in _latex_sanitize_prose(text)


@pytest.mark.parametrize(
    "gap", ["\n   \n", "\n\t\n", "\r\n\r\n"], ids=["spaces-line", "tab-line", "crlf"]
)
def test_a_line_of_blanks_inside_a_key_is_a_blank_line(gap):
    text = BS + "citep{Arnot2006," + gap + "Arman2012}"
    assert BS + "citep{" not in _latex_sanitize_prose(text)


def test_a_key_holding_a_single_line_break_still_passes():
    text = BS + "citep{Arnot2006,\nArman2012}"
    assert _latex_sanitize_prose(text) == text


# -- 5. \eqref no longer passes ------------------------------------------------------------


def test_eqref_prints_as_literal_text():
    assert _latex_sanitize_prose(BS + "eqref{eq:1}") == r"\textbackslash{}eqref\{eq:1\}"


# -- 4. one warning rule: every command printed as literal text is named -------------------


@pytest.mark.parametrize(
    "text, command",
    [
        (BS + "textbf{x} y", BS + "textbf"),
        (BS + "emph{x} y", BS + "emph"),
        (BS + "section{X} y", BS + "section"),
        (BS + "subparagraph{X.} y", BS + "subparagraph"),
        (BS + "paragraphs{X.} y", BS + "paragraphs"),
        (BS + "paragraph*{X.} y", BS + "paragraph"),
        (BS + "citep[e.g.][]{Doe2020} y", BS + "citep"),
        (BS + "citep{Arnot2006,\n\nArman2012} y", BS + "citep"),
        (BS + "eqref{eq:1} y", BS + "eqref"),
        (fw(BS + "textbf{x}") + " y", BS + "textbf"),
        ("50" + BS + "% of it", BS + "%"),
        (BS + "te" + chr(7) + "xtbf{x}", BS + "textbf"),
    ],
    ids=[
        "textbf", "emph", "section", "subparagraph", "longer-name", "starred",
        "cite-optional-args", "cite-blank-line", "eqref", "fullwidth-backslash",
        "control-symbol", "control-inside",
    ],
)
def test_a_command_printed_as_literal_text_is_named(text, command):
    from sci_adk.render.paper import prose_warnings

    warnings = _warnings(PaperProse(methods=text))
    assert warnings == ["prose slot 'methods': " + command + " prints as literal text"]
    # What passes is stated once per render, after the per-command lines (round 3).
    rule = prose_warnings(PaperProse(methods=text))[-1]
    for passing in ("ref", "autoref", "cite", "citep", "citet", "paragraph{<brace-free text>}"):
        assert BS + passing in rule


@pytest.mark.parametrize(
    "text",
    [
        BS + "ref{fig:a} and " + BS + "autoref{tab:b}",
        BS + "cite{a,b} " + BS + "citep{c} " + BS + "citet{d}",
        BS + "citep{Arnot2006,\nArman2012}",
        BS + "paragraph{Data.} x",
        BS + "paragraph{Effect " + BS + "evval{ev-1}{effect_size}.} x",
        "The slope was " + BS + "evval{ev-1}{effect_size} (" + BS + "status{hyp-t1}).",
        BS + "novelty{result}{hyp-t1}{No earlier study reports this}.",
        "Plain prose with 50% & a_b.",
        "A lone backslash " + BS + " and C:" + BS + "2020.",
    ],
    ids=["refs", "cites", "cite-line-break", "heading", "evval-heading", "facts", "novelty",
         "specials", "lone-backslash"],
)
def test_what_passes_or_is_substituted_is_not_warned_about(text):
    assert _warnings(PaperProse(methods=text)) == []


def test_one_line_per_slot_and_command():
    text = BS + "textbf{a} " + BS + "emph{b} " + BS + "textbf{c}"
    warnings = _warnings(PaperProse(methods=text, results=BS + "textbf{d}"))
    named = [(w.split("'")[1], w.split(": ")[1].split(" ")[0]) for w in warnings]
    assert named == [
        ("methods", BS + "textbf"), ("methods", BS + "emph"), ("results", BS + "textbf"),
    ]


def test_the_title_and_the_author_pass_no_command():
    from sci_adk.render.paper import prose_warnings

    prose = PaperProse(title="On " + BS + "ref{x}", author="A " + BS + "and B")
    warnings = _warnings(prose)
    assert [w.split("'")[1] for w in warnings] == ["title", "author"]
    assert BS + "and prints as literal text" in warnings[1]
    assert prose_warnings(prose)[-1] == (
        "the title and the author are plain text: no command passes there"
    )


def test_every_slot_is_checked_in_order():
    bad = BS + "emph{b} x"
    prose = PaperProse(
        title=bad, author=bad, abstract=bad, introduction=bad, methods=bad, results=bad,
        discussion=bad, conclusion=bad,
    )
    warnings = _warnings(prose, SIProse(overview=bad, notes=bad))
    assert [w.split("'")[1] for w in warnings] == [
        "title", "author", "abstract", "introduction", "methods", "results", "discussion",
        "conclusion", "overview", "notes",
    ]
    assert warnings[-1].startswith("SI prose slot 'notes': " + BS + "emph")


def test_no_prose_gives_no_warning():
    assert _warnings(None) == []
    assert _warnings(None, None) == []


# -- 6. run --prose with a refused abstract exits 2 ----------------------------------------


def test_run_with_a_heading_in_the_abstract_exits_2_with_the_message(tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    prose = tmp_path / "prose.json"
    prose.write_text(
        PaperProse(abstract=BS + "paragraph{Aim.} We measured it.", methods="M.")
        .model_dump_json(),
        encoding="utf-8",
    )
    capsys.readouterr()
    rc = main([
        "run", str(proposal), "-o", str(tmp_path), "--spec-id", "t-run-abs-head",
        "--prose", str(prose),
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "abstract" in err
    assert "Traceback" not in err


# -- whitespace runs in a title or the author ----------------------------------------------


def test_the_title_and_the_author_are_one_line():
    tex = _draft(title="A\n\nlong   title", author="One\n\n  Author\r\nTwo", methods="M.")
    assert r"\title{A long title}" in tex
    assert r"\author{One Author Two}" in tex


def test_the_authored_si_title_and_section_titles_are_one_line():
    spec, claims, evidence = _basic_record()
    tex = render_authored_si_latex(
        AuthoredSI(
            title="Supporting\n\ninformation",
            sections=[SISection(title="Pro\n\n tocol", body="Body.")],
        ),
        spec, claims, evidence,
    )
    assert r"\title{Supporting information}" in tex
    assert r"\section{Pro tocol}" in tex


# -- pdflatex builds -----------------------------------------------------------------------


def _build(tmp_path: Path, tex: str, name: str) -> list[str]:
    """pdflatex ``tex`` as rendered (title and author included), minus a package this TeX
    install cannot load; the log errors (empty = compiled cleanly)."""
    head, body = tex.split(r"\begin{document}", 1)
    kept = []
    for line in head.splitlines():
        m = _USEPACKAGE_RE.search(line)
        if m and not all(_loadable(p.strip()) for p in m.group(1).split(",")):
            if m.group(1) in {"inputenc", "fontenc", "lmodern"}:
                pytest.skip(f"this TeX install cannot load {m.group(1)}")
            continue
        kept.append(line)
    source = "\n".join(kept) + "\n" + r"\begin{document}" + body
    (tmp_path / f"{name}.tex").write_text(source, encoding="utf-8")
    status = _run(["pdflatex", "-interaction=nonstopmode", f"{name}.tex"], tmp_path)
    errors = _log_errors((tmp_path / f"{name}.log").read_text(encoding="utf-8", errors="replace"))
    if status != 0:
        errors.append(f"pdflatex exited {status}")
    return errors


def _pdf_text(tmp_path: Path, name: str) -> str:
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext not on PATH")
    out = subprocess.run(
        ["pdftotext", f"{name}.pdf", "-"], cwd=tmp_path, capture_output=True, text=True,
        check=True,
    ).stdout
    return " ".join(out.split())


_FW_SPECIALS = fw(BS + "{}&%#_$^~")
_FW_INPUT = fw(BS + "input{/etc/hostname}")
_FW_END = fw(BS + "end{document}")


@needs_tex
def test_fullwidth_specials_in_the_draft_compile_and_print_literally(tmp_path):
    tex = _draft(
        abstract="Abstract " + _FW_SPECIALS + " and " + _FW_INPUT + " end.",
        methods="Methods " + _FW_SPECIALS + " " + _FW_END + " afterwards.",
        results=fw(BS + "paragraph{x}") + " results.",
    )
    assert _build(tmp_path, tex, "draft") == []
    text = _pdf_text(tmp_path, "draft")
    assert "Abstract " + BS + "{}&%#_$^~ and " + BS + "input{/etc/hostname} end." in text
    assert "Methods " + BS + "{}&%#_$^~ " + BS + "end{document} afterwards." in text
    hostname = Path("/etc/hostname")
    if hostname.is_file() and hostname.read_text().strip():
        assert hostname.read_text().strip() not in text


@needs_tex
def test_fullwidth_specials_in_the_record_prose_compile_and_print_literally(tmp_path):
    record = _record(SIProse(
        overview="Overview " + _FW_SPECIALS + " " + _FW_INPUT + ".",
        notes="Notes " + _FW_SPECIALS + " " + _FW_END + " afterwards.",
    ))
    assert _build(tmp_path, record, "record") == []
    text = _pdf_text(tmp_path, "record")
    assert "Overview " + BS + "{}&%#_$^~ " + BS + "input{/etc/hostname}." in text
    assert "Notes " + BS + "{}&%#_$^~ " + BS + "end{document} afterwards." in text


@needs_tex
def test_control_characters_in_every_slot_compile(tmp_path):
    c = "".join(chr(x) for x in (0x07, 0x08, 0x0B, 0x0C, 0x1B, 0x7F))
    tex = _draft(
        title="Ti" + c + "tle\n\nsplit", author="Au" + c + "thor\n\nTwo",
        abstract="Ab" + c + "stract.",
        introduction="In" + c + "tro " + BS + "citep{Doe" + c + "2020}.",
        methods=BS + "paragraph{He" + c + "ad.} Me" + c + "thods.",
    )
    assert _build(tmp_path, tex, "draft") == []
    record = _record(SIProse(overview="Ov" + c + "erview.", notes="No" + c + "tes."))
    assert _build(tmp_path, record, "record") == []


@needs_tex
def test_a_cite_with_a_blank_line_compiles_and_is_warned_about(tmp_path):
    methods = "Values " + BS + "citep{Arnot2006,\n\nArman2012} were used."
    tex = _draft(methods=methods)
    assert _build(tmp_path, tex, "draft") == []
    assert [w.split(": ")[1].split(" ")[0] for w in _warnings(PaperProse(methods=methods))] == [
        BS + "citep"
    ]


@needs_tex
def test_a_cite_with_a_single_line_break_passes_and_compiles(tmp_path):
    tex = _draft(methods="Values " + BS + "citep{Arnot2006,\nArman2012} were used.")
    assert BS + "citep{Arnot2006,\nArman2012}" in tex
    assert _build(tmp_path, tex, "draft") == []


@needs_tex
def test_the_old_constructs_would_stop_pdflatex(tmp_path):
    # Why: what the renderer used to emit for a blank-line cite and a blank-line author.
    tex = _draft(methods="PLACE").replace("PLACE", BS + "citep{Arnot2006,\n\nArman2012}")
    assert any("Paragraph ended before" in e for e in _build(tmp_path, tex, "cite"))
    tex = _draft(methods="M.").replace(r"\author{}", r"\author{One" + "\n\n" + "Two}")
    assert any("Paragraph ended before" in e for e in _build(tmp_path, tex, "author"))

