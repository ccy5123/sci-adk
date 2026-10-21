"""
The canonical bibliography copy and its verify checks, round 6.

Independent checkers found that the copy and the checks still parted from what BibTeX and
pdflatex do:

  1. the reader parted from BibTeX after a syntax error in two places: a @string whose
     definition fails still defines the macro, as its own name, and an entry whose key repeats
     an earlier one is read no further than its key (BibTeX looks for the next '@' from there);
     an author's package bibliography then passed with \\input in what BibTeX printed;
  2. braces nested 254 deep stopped pdflatex (TeX's 255 grouping levels);
  3. a double superscript or subscript, or a command right after ^ or _ with no braces,
     stopped pdflatex;
  4. a command, math or a group in a year stopped natbib (Improper alphabetic constant);
  5. nested accent commands doubled pdflatex's time per level;
  6. the copy was not its own fixed point for about one value in ten, so verify failed a file
     render had just written;
  7. the package gate failed an SI bibliography the author had written in place;
  and the minor findings that go with them (characters with no LaTeX form, entry types,
  cross references, names, lengths, unprinted fields of an author's bibliography, keys).

This file is ASCII-only: a backslash is BS, every other non-ASCII character is built with chr.
"""

from __future__ import annotations

import random
import re
import subprocess
import time
from pathlib import Path

import pytest

from sci_adk.render import bib_latex
from sci_adk.render.bib_latex import canonical_bib, entry_values, paper_bib
from sci_adk.render.pkgreqs_checks import (
    bib_command_problems,
    bib_form_problems,
    bib_keys,
    bib_latex_safety_problems,
    bib_subset,
    bib_syntax_problems,
)
from tests.test_bib_latex_copy import _compile_with_bib, _render_preamble, needs_tex

BS = chr(92)
INPUT = BS + "input{marker}"
PKG = "package_src/references.bib, which the package copies unchanged"


def _entry(value: str, key: str = "K1", field: str = "title", extra: str = "") -> str:
    return "@article{" + key + ", " + field + " = {" + value + "}, year = {2020}" + extra + "}\n"


def _value(bib: str, field: str = "title", key: str | None = None) -> str:
    text = bib
    if key is not None:
        start = text.index("{" + key + ",")
        text = text[start: text.index("\n}", start)]
    m = re.search(r"^  " + field + r" = \{(.*)\},?$", text, re.M)
    assert m is not None, bib
    return m.group(1)


def _printed(bib: str) -> set[tuple[str, str, str]]:
    """(key, field, value) of every field entry_values reads, white space compressed."""
    return {
        (command.key, name, " ".join(value.split()))
        for command, values in entry_values(bib)
        for name, value in values
    }


def _depth(text: str) -> int:
    depth = deepest = 0
    for ch in text:
        if ch == "{":
            depth += 1
            deepest = max(deepest, depth)
        elif ch == "}":
            depth -= 1
    return deepest


# -- 1. the reader follows BibTeX after a failed @string and a repeated key ----------------------

_FAILED_STRING = {
    "space-after-the-name": "@string{" + BS + "input }\n",
    "equals-and-no-value": "@string{" + BS + "input=}\n",
    "hash-and-nothing": "@string{" + BS + "input = {a} # }\n",
    "parenthesised": "@string(" + BS + "input )\n",
    "upper-case-name": "@string{" + BS + "INPUT }\n",
}


@pytest.mark.parametrize("field", ["note", "title"])
@pytest.mark.parametrize("head", list(_FAILED_STRING.values()), ids=list(_FAILED_STRING))
def test_a_failed_string_definition_defines_the_macro_as_its_own_name(head, field):
    # Measured with BibTeX 0.99e: it stores the macro's name (lower case) as its text before it
    # reads the value, so the field prints \input{marker}.
    bib = head + "@article{K3, " + field + " = " + BS + "input # {{marker}}, year = {2020}}\n"
    assert ("K3", field, INPUT) in _printed(bib)


def test_a_failed_redefinition_replaces_the_macro_with_its_name():
    bib = '@string{zz = "ok"}\n@string{zz }\n@article{K3, note = zz, year = {2020}}\n'
    assert ("K3", "note", "zz") in _printed(bib)


_REPEATED = {
    "string-after-the-key": ("@article{K1, title = {A}}\n@article{K1,@string{x = \"" + INPUT
                             + "\"}}\n@article{K3, title = x}\n"),
    "entry-on-the-next-line": ("@article{K1, title = {A}}\n@article{K1,\n@article{K3, title = {"
                               + INPUT + "}}}\n"),
    "empty-key": ("@article{, title = {A}}\n@article{,\n@article{K3, title = {" + INPUT
                  + "}}}\n"),
    "other-case": ("@article{K1, title = {A}}\n@article{k1,\n@article{K3, title = {" + INPUT
                   + "}}}\n"),
}


@pytest.mark.parametrize("bib", list(_REPEATED.values()), ids=list(_REPEATED))
def test_an_entry_repeating_a_key_is_read_no_further_than_its_key(bib):
    assert ("K3", "title", INPUT) in _printed(bib)


def test_a_preamble_after_a_repeated_key_is_read():
    bib = '@article{K1, title = {A}}\n@article{K1,@preamble{"' + INPUT + '"}}\n'
    assert any("@preamble" in line for line in bib_command_problems(bib))


def test_a_non_ascii_key_differing_only_in_case_is_not_a_repeat():
    # BibTeX lowers ASCII letters only: these are two entries.
    bib = ("@article{" + chr(0xC4) + "1, title = {A}}\n@article{" + chr(0xE4) + "1, title = {"
           + INPUT + "}}\n")
    assert (chr(0xE4) + "1", "title", INPUT) in _printed(bib)


_DIVERGENT = {
    **{f"failed-string-{k}": v + "@article{K3, note = " + BS + "input # {{marker}}, year = {2020}}\n"
       for k, v in _FAILED_STRING.items()},
    **{f"repeated-{k}": v for k, v in _REPEATED.items()},
}


@pytest.mark.parametrize("bib", list(_DIVERGENT.values()), ids=list(_DIVERGENT))
def test_an_author_bib_with_each_divergence_fails_naming_what_bibtex_prints(bib):
    lines = bib_latex_safety_problems(bib, source="references.bib", package_source=PKG)
    assert any("'K3'" in line and BS + "input" in line for line in lines), lines
    assert any("bib syntax" in line for line in lines), lines


def test_bib_syntax_problems_names_errors_repeats_and_failed_macros():
    bib = ("@string{" + BS + "input }\n@article{K1, title = {A}}\n@article{K1, title = {B}}\n"
           "@article{K2, title = {C} x}\n@article{K4, note = undefinedmacro, month = jan}\n")
    lines = bib_syntax_problems(bib, source="references.bib", package_source=PKG)
    text = "\n".join(lines)
    assert "@string" in text and BS + "input" in text
    assert "'K1'" in text and "repeat" in text
    assert "'K2'" in text
    assert "undefinedmacro" in text and "'K4'" in text
    assert "jan" not in text  # the month macros are defined by every style
    assert all(PKG in line for line in lines), lines


def test_a_journal_macro_every_style_defines_is_expanded_and_is_not_undefined():
    # plain.bst and the natbib styles define cacm, jacm ... with MACRO (TeX Live 2026).
    bib = "@article{K1, title = {T}, journal = cacm, year = {2020}}\n"
    assert _value(paper_bib(bib), "journal") == "Communications of the ACM"
    assert bib_syntax_problems(bib, package_source=PKG) == []


def test_a_clean_author_bib_has_no_syntax_problem():
    bib = ('@string{jpc = "J. Phys. Chem."}\n@article(A2020, title = "Alpha " # {Beta},'
           " journal = jpc, month = feb, year = 2020)\n% a comment me@example.org\n"
           "@book{B2021, title = {Gamma}, year = {2021},}\n")
    assert bib_syntax_problems(bib, source="references.bib", package_source=PKG) == []


def test_a_package_built_from_a_divergent_author_bib_fails_verify(tmp_path):
    from sci_adk.loop.verify import _check_package_requirements
    from sci_adk.render.package import assemble_package
    from tests.test_si_authoring_m6 import _freeze_pkgreqs, _pkgreqs_obj, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    (src / "references.bib").write_text(_REPEATED["entry-on-the-next-line"], encoding="utf-8")
    pkgreqs = _pkgreqs_obj(ws)
    assemble_package(ws, pkgreqs)
    problems, _w, _r, _p = _check_package_requirements(ws, ws / "package", pkgreqs)
    lines = [p for p in problems if "references.bib" in p]
    assert any("'K3'" in p and BS + "input" in p for p in lines), lines
    assert any("bib syntax" in p and "'K1'" in p for p in lines), lines


# The BibTeX differential: a style that writes every field of every entry, and mutated bibs.
_DUMP_FIELDS = ("title", "note", "author", "year", "journal")
_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")
_MONTH_MACROS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                 "dec")


def _dump_bst() -> str:
    lines = ["ENTRY { " + " ".join(_DUMP_FIELDS) + " } {} {}"]
    lines += ["MACRO {" + m + '} {"' + n + '"}' for m, n in zip(_MONTH_MACROS, _MONTH_NAMES)]
    body = " ".join(
        f"{f} missing$ 'skip$ {{ \"<<R>>\" cite$ * \"|{f}|\" * {f} * \"<<E>>\" * write$ "
        f"newline$ }} if$" for f in _DUMP_FIELDS
    )
    lines.append("FUNCTION {dump} { " + body + " }")
    for kind in ("article", "misc", "book", "default.type"):
        lines.append("FUNCTION {" + kind + "} { dump }")
    lines += ["READ", "ITERATE {call.type$}"]
    return "\n".join(lines) + "\n"


def _bibtex_rows(directory: Path, bib: str) -> set[tuple[str, str, str]]:
    (directory / "r.bib").write_text(bib, encoding="utf-8")
    (directory / "r.aux").write_text(
        BS + "relax\n" + BS + "citation{*}\n" + BS + "bibstyle{dump}\n" + BS + "bibdata{r}\n",
        encoding="utf-8")
    bbl = directory / "r.bbl"
    if bbl.exists():
        bbl.unlink()
    subprocess.run(["bibtex", "-terse", "r"], cwd=directory, capture_output=True, check=False)
    text = bbl.read_text(encoding="utf-8", errors="replace").replace("\n", " ") if bbl.exists() else ""
    return {
        (m.group(1), m.group(2), " ".join(m.group(3).split()))
        for m in re.finditer(r"<<R>>(.*?)\|(\w+)\|(.*?)<<E>>", text)
        if m.group(3).strip()
    }


_PIECES = [
    "@string{", "@string(", "@article{K1,", "@article{K3,", "@article(K2,", "@misc{K4,",
    "@preamble{", "@comment{", "@", "}", ")", "{", '"', " # ", " = ", ",", " ", "\n", "%",
    "title", "note", "x", "y", "jan", "{" + INPUT + "}", BS + "input", "{marker}", "K1",
    "@article{k1,", "1999", "x = ", "title = ", "note = x # ", '"a"', "{b}", "@string{x = {X}}",
    "@article{K1, title = {A}}", "author = ", "year = 2001",
]


def _mutated_bibs(count: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    bibs = list(_DIVERGENT.values())
    while len(bibs) < count:
        prefix = rng.choice(["", "@string{x = {X}}\n", "@article{K1, title = {A}}\n"])
        bibs.append(prefix + "".join(rng.choice(_PIECES) for _ in range(rng.randint(3, 28))))
    return bibs


@needs_tex
def test_every_field_bibtex_prints_is_one_the_reader_reads(tmp_path):
    (tmp_path / "dump.bst").write_text(_dump_bst(), encoding="utf-8")
    missed = []
    for bib in _mutated_bibs(260, seed=6):
        for row in _bibtex_rows(tmp_path, bib) - _printed(bib):
            missed.append((bib, row))
    assert missed == [], missed[:3]


# -- 2. braces nested past TeX's grouping limit ---------------------------------------------------

@pytest.mark.parametrize("depth", [70, 254, 300, 2000])
def test_a_value_nested_past_the_cap_is_written_empty_with_a_note(depth):
    result = canonical_bib(_entry("{" * depth + "x" + "}" * depth))
    assert "  title = {}" in result.text
    assert any("'K1'" in note and "nested" in note for note in result.notes), result.notes


def test_a_value_nested_within_the_cap_is_kept_and_math_too():
    assert "x" in _value(paper_bib(_entry("{" * 40 + "x" + "}" * 40)))
    math = "$x" + "^{y" * 40 + "}" * 40 + "$"
    assert "y" in _value(paper_bib(_entry(math)))


def test_math_nested_past_the_cap_is_written_empty():
    math = "$x" + "^{y" * 400 + "}" * 400 + "$"
    result = canonical_bib(_entry(math))
    assert "  title = {}" in result.text and any("nested" in n for n in result.notes)


def test_verify_fails_an_author_bib_nested_past_the_cap():
    lines = bib_command_problems(_entry("{" * 254 + "x" + "}" * 254), package_source=PKG)
    assert any("'K1'" in line and "nested" in line for line in lines), lines


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_the_copy_of_deep_values_compiles(tmp_path, figure_bearing):
    bib = (_entry("{" * 254 + "x" + "}" * 254, "D1") + _entry("{" * 60 + "x" + "}" * 60, "D2")
           + _entry("$x" + "^{y" * 400 + "}" * 400 + "$", "D3")
           + _entry("$x" + "^{y" * 30 + "}" * 30 + "$", "D4"))
    copy = paper_bib(bib)
    assert _depth(copy) < 100
    errors, _bbl, dropped = _compile_with_bib(tmp_path, copy, figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- 3. scripts in math ------------------------------------------------------------------------

_SCRIPTS = [
    "$x^2^3$", "$x_1_2$", "$a^{b}^{c}$", "$x^" + BS + "prime^" + BS + "prime$",
    "$" + BS + "alpha_" + BS + "beta_" + BS + "gamma$", "$x^{}^{}$", "$x^2'$", "$x_1^2_3$",
    "$x''$", "$x'^2$", "$x^_$", "$x^ ^2$", "$x^$", "$_2$", "$x^" + BS + "sin$",
    "$x^" + BS + "log$", "$x^" + BS + "hat{y}$", "$x^" + BS + "sqrt{y}$", "$x^" + BS + "int$",
    "$x_" + BS + "sum$", "$x^" + BS + "AA$", "$x^" + BS + "ss$", "$x^" + BS + "textbar$",
    "$x^" + BS + "mbox{a}$", "$x^" + BS + "frac{1}{2}$", "$x^" + BS + "sqrt[3]{2}$",
    "$x^" + BS + "rm a$", "$x^" + BS + "input$", "$x^" + BS + "'e$",
]


def test_a_script_argument_is_always_braced():
    for math in ("$x^" + BS + "hat{y}$", "$x^2$", "$x_" + BS + "alpha$"):
        value = _value(paper_bib(_entry(math)))
        assert re.search(r"[\^_]\{", value), value
        assert not re.search(r"[\^_][^{]", value), value


def test_a_second_script_on_one_base_gets_an_empty_base():
    value = _value(paper_bib(_entry("$x^2^3$")))
    assert value.count("^{") == 2 and "{}^{" in value, value


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_the_copy_of_each_script_shape_compiles(tmp_path, figure_bearing):
    bib = "".join(_entry(math, f"S{k}") for k, math in enumerate(_SCRIPTS))
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


def _script_samples() -> list[str]:
    """Every allow-listed command in math, as x^NAME, x_NAME and x^NAME^2."""
    calls = []
    for name, kind in sorted(bib_latex.MATH_COMMANDS.items()):
        calls.append({"zero": BS + name, "one": BS + name + "{a}", "two": BS + name + "{1}{2}",
                      "declaration": BS + name + " a", "text": BS + name + "{e}",
                      "math": BS + name + "{x}"}[kind])
    for name, kind in sorted(bib_latex.TEXT_COMMANDS.items()):
        calls.append({"zero": BS + name, "accent": BS + name + "{e}", "one": BS + name + "{a}",
                      "declaration": BS + name + " a", "url": BS + name + "{https://a.org/}",
                      "href": BS + name + "{https://a.org/}{x}", "math": BS + name + "{x}"}[kind])
    return calls


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_every_allow_listed_command_compiles_as_a_script(tmp_path, figure_bearing):
    calls = _script_samples()
    forms = (("^", ""), ("_", ""), ("^", "^2"))
    bib = "".join(
        _entry(" ".join("$x" + before + call + after + "$" for call in calls[k:k + 40]),
               f"C{n}x{k}")
        for n, (before, after) in enumerate(forms)
        for k in range(0, len(calls), 40)
    )
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- 4. the year natbib reads into its label ------------------------------------------------------

_YEARS = [BS + "textit{2020}", BS + "emph{2020}", BS + "texttt{2020}", BS + "mbox{2020}",
          "$2020$", BS + "alpha 2020", BS + "ss 2020", BS + "url{https://a.org/}",
          BS + "href{https://a.org/}{2020}", "$", BS + "input 2020", "20" + BS + "relax 20",
          "{" + BS + "em 2020}", "2020 " + BS + "'e"]
_PLAIN_YEAR = re.compile(r"[A-Za-z0-9 ~().,/?:;'-]*")


@pytest.mark.parametrize("year", _YEARS)
def test_a_year_holding_a_command_is_written_as_plain_text_with_a_note(year):
    result = canonical_bib("@article{K1, title = {T}, year = {" + year + "}}\n")
    written = _value(result.text, "year")
    assert _PLAIN_YEAR.fullmatch(written), written
    assert any("'K1'" in n and "year" in n for n in result.notes), result.notes


@pytest.mark.parametrize("year, written", [("2020", "2020"), ("2020~a", "2020~a"),
                                           ("in press", "in press"), ("{2020}", "2020"),
                                           ("2020--2021", "2020--2021")])
def test_a_plain_year_is_kept(year, written):
    result = canonical_bib("@article{K1, title = {T}, year = {" + year + "}}\n")
    assert _value(result.text, "year") == written
    assert not any("year" in n for n in result.notes), result.notes


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_the_copy_of_each_year_compiles(tmp_path, figure_bearing):
    bib = "".join("@article{Y" + str(k) + ", author = {Doe, J.}, title = {T}, journal = {J},"
                  " year = {" + y + "}}\n" for k, y in enumerate(_YEARS))
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- 5. nested accents ------------------------------------------------------------------------

_ACCENTS = ["'", "`", "^", '"', "~", "=", ".", "c", "v", "H", "u", "r", "t"]


def _nested_accent(accent: str, depth: int) -> str:
    return (BS + accent + "{") * depth + "x" + "}" * depth


@pytest.mark.parametrize("accent", _ACCENTS)
def test_accents_nest_at_most_three_deep_in_the_copy(accent):
    result = canonical_bib(_entry(_nested_accent(accent, 22)))
    value = _value(result.text)
    assert value.count(BS + accent + "{") <= 3, value
    assert any("'K1'" in n and "accent" in n for n in result.notes), result.notes


def test_three_nested_accents_are_kept():
    value = _value(paper_bib(_entry(BS + "'{" + BS + "^{" + BS + "d{e}}}")))
    assert BS + "textbackslash" not in value, value


def test_combining_marks_nest_no_deeper_than_three_either():
    value = _value(paper_bib(_entry("e" + chr(0x301) * 20)))
    assert value.count(BS + "'") <= 3, value


@needs_tex
def test_the_copy_of_deep_accents_compiles_quickly(tmp_path):
    bib = "".join(_entry(_nested_accent(a, d), f"A{k}{d}") for k, a in enumerate(_ACCENTS)
                  for d in (22, 40))
    start = time.monotonic()
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), False)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"
    assert time.monotonic() - start < 60


# -- 6. the copy is its own fixed point ---------------------------------------------------------

_NOT_FIXED = [
    BS + "[", BS + "]", "a " + BS + "[ b", BS + "(" + BS + ")", "$$$$", "$ $",
    BS + "ensuremath" + BS + "-", "$" + BS + "-$", BS + "hat " + chr(0xE9),
    BS + "mathrm " + chr(0xE9), BS + "sqrt " + chr(0xE9), "{" + BS + "em" + BS + " }",
    "$" + BS + "alpha" + BS + BS + "$", BS + "href{" + chr(0x2212),
    BS + "ensuremath{" + BS + "url{http://a&b}}", "$" + chr(0xE9) + "$", "x " + BS + "] y",
    "[" + BS + "[", BS + "(a" + BS + ")" + BS + "(", "$a$$b$", BS + "textit{$$}",
]


@pytest.mark.parametrize("field", ["title", "author", "journal", "note", "booktitle", "year"])
@pytest.mark.parametrize("value", _NOT_FIXED)
def test_the_copy_of_each_finding_is_its_own_fixed_point(field, value):
    once = paper_bib(_entry(value, field=field))
    assert paper_bib(once) == once
    assert bib_form_problems(once) == []


_VOCABULARY = [
    BS + "[", BS + "]", BS + "(", BS + ")", "$", "$$", "{", "}", BS + "'", BS + '"', BS + "^",
    BS + "hat ", BS + "mathrm ", BS + "sqrt", chr(0xE9), chr(0xFC), BS + "alpha", "^", "_",
    BS + "-", BS + BS, BS + " ", BS + "em", BS + "textit", BS + "url", BS + "href", "&", "%",
    "#", "~", "[", "]", BS + "ensuremath", chr(0x2212), "x", "A", " ", BS + "input",
    BS + "textbackslash", BS + "{", BS + "}", "<i>", "</i>", "&amp;", BS + "mbox", BS + "frac",
    BS + "$", "--", "'", '"', "http://a&b", ",", " and ", BS + "ss", BS + "i", "1",
    chr(0x1F600), chr(0x3B1), "a", BS + "c", "{" + BS + "'e}", BS + "AA", BS + "bf", "\n",
    chr(0x301), BS + "url{https://a.org/}", "$x$", BS + "textsuperscript", "&#92;", "<",
]


def test_the_copy_is_its_own_fixed_point_over_a_vocabulary_fuzz():
    rng = random.Random(20261021)
    failures = []
    fields = ["title", "author", "journal", "year", "note", "booktitle"]
    for _ in range(2500):
        value = "".join(rng.choice(_VOCABULARY) for _ in range(rng.randint(1, 14)))
        bib = "@article{K1, " + rng.choice(fields) + " = {" + value + "}}\n"
        once = paper_bib(bib)
        if paper_bib(once) != once:
            failures.append(value)
    assert failures == [], failures[:5]


# -- 7. the package SI bibliography --------------------------------------------------------------

def _assembled(tmp_path, *, author_si: str | None = None):
    from sci_adk.render.package import assemble_package
    from tests.test_si_authoring_m6 import (
        _AUTHOR_SI_HEAD, _POOL_BIB, _freeze_pkgreqs, _pkgreqs_obj, _seed_workspace,
    )

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    if author_si is not None:
        src = ws / "package_src"
        src.mkdir()
        (src / "si.tex").write_text(
            _AUTHOR_SI_HEAD + author_si + BS + "bibliography{references_SI}" + BS
            + "end{document}", encoding="utf-8")
        (src / "references.bib").write_text(_POOL_BIB, encoding="utf-8")
    pkgreqs = _pkgreqs_obj(ws)
    assemble_package(ws, pkgreqs)
    return ws, pkgreqs


def _package_problems(ws, pkgreqs):
    from sci_adk.loop.verify import _check_package_requirements

    problems, _w, _r, _p = _check_package_requirements(ws, ws / "package", pkgreqs)
    return problems


def test_an_si_bib_written_in_place_gets_no_form_check(tmp_path):
    ws, pkgreqs = _assembled(tmp_path)
    si_bib = ws / "package" / "01_manuscript" / "references_SI.bib"
    si_bib.write_text('@article{A2020, title = "Alpha", year = 2020}\n', encoding="utf-8")
    assert not [p for p in _package_problems(ws, pkgreqs) if "bib form" in p]


def test_an_si_bib_the_assembler_cut_and_was_edited_fails_with_the_package_remedy(tmp_path):
    ws, pkgreqs = _assembled(tmp_path, author_si=BS + "citep{A2020}.")
    si_bib = ws / "package" / "01_manuscript" / "references_SI.bib"
    assert si_bib.is_file()
    assert not [p for p in _package_problems(ws, pkgreqs) if "bib form" in p]
    si_bib.write_text(si_bib.read_text(encoding="utf-8").replace("{Alpha}", "{Alpha  x}"),
                      encoding="utf-8")
    lines = [p for p in _package_problems(ws, pkgreqs) if "bib form" in p]
    # the remedy is written once for the file (tests/test_bib_round7.py)
    assert sum("sci-adk package" in p and "package_src/references_SI.bib" in p
               for p in lines) == 1, lines
    assert lines and not any("render the run again" in p for p in lines), lines


# -- minor: characters with no LaTeX form ---------------------------------------------------------
#
# The copy keeps such a character (a reference must not silently lose a letter, the module's
# policy); render notes it and verify fails it, whether or not a publishing contract is frozen.

@pytest.mark.parametrize("cp", [0x1F600, 0x2216, 0x338, 0x10348])
def test_a_character_with_no_latex_form_is_kept_and_noted(cp):
    result = canonical_bib(_entry("a" + chr(cp) + "b"))
    assert chr(cp) in _value(result.text)
    assert any("'K1'" in n and "U+%04X" % cp in n for n in result.notes), result.notes
    assert paper_bib(result.text) == result.text


@pytest.mark.parametrize("cp", [0x2028, 0x2029])
def test_a_line_or_paragraph_separator_becomes_a_space(cp):
    assert _value(paper_bib(_entry("a" + chr(cp) + "b"))) == "a b"


def test_verify_names_a_character_with_no_latex_form_in_a_shipped_copy(tmp_path):
    from sci_adk.loop.verify import _check_bib_commands
    from tests.test_latex_sanitize_round3 import _rendered_run

    run_dir = _rendered_run(tmp_path, "round6-chars")
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + "\n" + paper_bib(_entry("x", "Z2020"))
                   .replace("{x}", "{x" + chr(0x2216) + "}"), encoding="utf-8")
    lines = _check_bib_commands(run_dir)
    assert any("'Z2020'" in line and "U+2216" in line for line in lines), lines


# -- minor: entry types, cross references, names --------------------------------------------------

@pytest.mark.parametrize("kind", ["output", "not", "and", "or", "emphasize", "format.names",
                                  "fin.entry", "software"])
def test_an_entry_type_that_is_not_a_standard_one_is_written_misc(kind):
    copy = paper_bib("@" + kind + "{K1, title = {T}, year = {2020}}\n")
    assert copy.startswith("@misc{K1,"), copy


def test_the_standard_entry_types_are_kept():
    for kind in ("article", "book", "booklet", "conference", "inbook", "incollection",
                 "inproceedings", "manual", "mastersthesis", "misc", "phdthesis",
                 "proceedings", "techreport", "unpublished"):
        assert paper_bib("@" + kind.upper() + "{K1, title = {T}}\n").startswith("@" + kind + "{")


def test_a_crossref_to_an_entry_the_copy_lacks_is_left_out_with_a_note():
    result = canonical_bib(_entry("T", extra=", crossref = {ZZ}"))
    assert "crossref" not in result.text
    assert any("'K1'" in n and "crossref" in n for n in result.notes), result.notes


def test_a_crossref_to_an_entry_of_the_copy_is_kept_and_the_subset_keeps_its_target():
    bib = ("@inbook{C1, author = {Doe, J.}, title = {Child}, chapter = {1}, crossref = {p1}}\n"
           "@book{P1, title = {Parent}, year = {2020}, publisher = {P}}\n"
           "@book{Q1, title = {Other}, year = {2020}}\n")
    copy = paper_bib(bib)
    assert "crossref = {p1}" in copy
    subset = bib_subset(copy, ["C1"])
    assert sorted(bib_keys(subset)) == ["C1", "P1"]
    assert paper_bib(subset) == subset


@pytest.mark.parametrize("author", ["Doe, Jr., John, X", "Doe, J.,", ",", "Doe,",
                                    "A and B, C, D, E", "Doe, John and ,"])
def test_a_name_bibtex_reads_as_too_many_commas_is_braced_with_a_note(author):
    result = canonical_bib("@article{K1, author = {" + author + "}, title = {T}}\n")
    assert any("'K1'" in n and "comma" in n for n in result.notes), result.notes


def test_a_name_too_long_for_natbib_s_label_is_shortened_with_a_note():
    result = canonical_bib("@article{K1, author = {" + "A" * 5000 + "}, title = {T}}\n")
    assert len(_value(result.text, "author")) <= 110
    assert any("'K1'" in n and "author" in n for n in result.notes), result.notes


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_the_copy_of_odd_names_types_and_crossrefs_compiles(tmp_path, figure_bearing):
    names = ["Doe, Jr., John, X", "Doe, J.,", ",", "Doe,", "A and B, C, D, E", "Doe, John and ,",
             "A" * 5000, "{" + "A " * 300 + "}", "A" * 200 + " and " + "B" * 200]
    bib = "".join("@article{N" + str(k) + ", author = {" + a + "}, title = {T}, journal = {J},"
                  " year = {2020}}\n" for k, a in enumerate(names))
    bib += "".join("@" + kind + "{T" + str(k) + ", author = {Doe, J.}, title = {T}, year = {2020}}\n"
                   for k, kind in enumerate(["output", "not", "and", "or", "emphasize"]))
    bib += _entry("T", "X1", extra=", crossref = {ZZ}")
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- minor: lengths and time ---------------------------------------------------------------------

@pytest.mark.parametrize("piece", [BS + "(", BS + "[", BS + "sqrt[", "$$"])
def test_a_long_run_of_one_opening_delimiter_is_copied_in_linear_time(piece):
    start = time.monotonic()
    canonical_bib(_entry(piece * 8000))
    assert time.monotonic() - start < 5


def test_a_numeric_entity_with_thousands_of_digits_does_not_stop_the_copy():
    result = canonical_bib(_entry("a &#" + "9" * 5000 + "; b"))
    assert "K1" in result.text


def test_a_word_too_long_for_tex_s_buffer_is_broken_at_ten_thousand_characters():
    copy = paper_bib(_entry("a" * 250000))
    assert max(len(w) for w in _value(copy).split(" ")) <= 10000
    assert paper_bib(copy) == copy


def test_a_field_too_long_for_bibtex_is_cut_with_a_note():
    result = canonical_bib(_entry(" ".join(["word"] * 60000)))
    assert len(_value(result.text)) <= 100000
    assert any("'K1'" in n and "long" in n for n in result.notes), result.notes
    assert paper_bib(result.text) == result.text


# -- minor: an author's bibliography is checked in every field -------------------------------------

def test_an_author_bib_s_unprinted_fields_are_checked_for_commands():
    bib = "@article{K1, title = {T}, annote = {" + INPUT + "}, year = {2020}}\n"
    lines = bib_latex_safety_problems(bib, package_source=PKG)
    assert any("'K1'" in line and BS + "input" in line for line in lines), lines
    assert bib_command_problems(paper_bib(bib)) == []  # the copy leaves annote out


# -- minor: the form FAIL line names the full re-render ------------------------------------------

def test_the_form_line_of_a_run_copy_names_the_re_render_and_its_inputs():
    lines = bib_form_problems(_entry("T") + "junk\n")
    # the remedy is written once for the file (tests/test_bib_round7.py)
    assert sum("sci-adk render" in p and "--prose" in p for p in lines) == 1, lines


# -- minor: what a syntax error lost is noted ----------------------------------------------------

def test_an_entry_a_syntax_error_cut_short_is_noted():
    result = canonical_bib("@article{K1, title = {50% off} {x}, year = {2020}, journal = {J}}\n"
                           "@article{SteveOHagan2006,_dunn_x, title = {T}}\n")
    assert any("'K1'" in n and "syntax error" in n for n in result.notes), result.notes
    assert any("'SteveOHagan2006'" in n for n in result.notes), result.notes


# -- minor: keys with Latin letters -----------------------------------------------------------------

def test_a_key_with_a_latin_letter_is_kept_and_one_with_other_letters_is_left_out():
    mueller = "M" + chr(0xFC) + "ller2019"
    bib = _entry("T", mueller) + _entry("T", chr(0x5F20) + "2019")
    result = canonical_bib(bib)
    assert "{" + mueller + "," in result.text
    assert chr(0x5F20) not in result.text
    assert any("left out" in n for n in result.notes)


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_a_latin_letter_key_compiles_when_cited(tmp_path, figure_bearing):
    # Round 8: a letter outside ASCII compiles after the first character of a key, cited alone
    # or first; a key that starts with one stops a \cite that names it first (the copy leaves
    # such an entry out, tests/test_bib_round8.py).
    keys = ["M" + chr(0xFC) + "ller2019", "J" + chr(0xF8) + "rgensen2020", "W" + chr(0x142)
            + "odek2021", "Ko" + chr(0x161) + "ir2022"]
    bib = "".join("@article{" + k + ", author = {Doe, J.}, title = {T}, journal = {J},"
                  " year = {2020}}\n" for k in keys)
    (tmp_path / "references.bib").write_text(paper_bib(bib), encoding="utf-8")
    preamble, dropped = _render_preamble(figure_bearing)
    body = [BS + "begin{document}", "See " + BS + "citep{" + ",".join(keys) + "}."]
    body += [BS + "citep{" + k + "} " + BS + "citet{" + k + "}" for k in keys]
    body += [BS + "bibliographystyle{plainnat}", BS + "bibliography{references}",
             BS + "end{document}"]
    (tmp_path / "t.tex").write_text("\n".join(preamble + body) + "\n", encoding="utf-8")
    for cmd in (["pdflatex", "-interaction=nonstopmode", "t.tex"], ["bibtex", "t"],
                ["pdflatex", "-interaction=nonstopmode", "t.tex"],
                ["pdflatex", "-interaction=nonstopmode", "t.tex"]):
        subprocess.run(cmd, cwd=tmp_path, capture_output=True, check=False)
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace")
    errors = [line for line in log.splitlines() if line.startswith("!")]
    errors += re.findall(r"Citation .* undefined", log)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- minor: the lint for author-written LaTeX ------------------------------------------------------

@pytest.mark.parametrize("command", ["verbatiminput", "lstinputlisting", "csname"])
def test_the_lint_names_more_file_readers(command):
    from sci_adk.render.latex_lint import lint_commands

    assert lint_commands(BS + command + "{x}")
