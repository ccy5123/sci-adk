"""
The canonical bibliography copy and its verify checks, round 8.

Independent checkers found more inputs that stop pdflatex or BibTeX, or keep them busy for
minutes, while render exits 0 and verify says nothing:

  1. a link inside a link: hyperref keeps at most 10 open ("TeX capacity exceeded, sorry [pdf
     link stack size=10]");
  2. math wrappers inside math wrappers: a \\sqrt with an index and the arrow accents typeset
     their argument four times per level, so pdflatex's time grows fourfold with each level;
     \\textsuperscript nested about 37 deep shrinks the type until "Improper `at' size"; a few
     thousand arrow accents in one reference take minutes;
  3. a citation key whose first character is outside ASCII stops every \\cite ("Missing
     \\endcsname inserted"), and a key of 100000 characters overflows TeX's buffer;
  5. a name ending in a comma followed only by '-', '--' or '~' (BibTeX: "has a comma at the
     end", exit 2);
  6. more than 26 entries with one natbib label (the year letters run past z);
  7. an author's bibliography holding a script error the copy fixes (x^2^3, x_1_2, x^2', x^$,
     x^\\rm 2 ...);
  8. the author-bib gate took minutes on large files (100000 @string macros, 50000 repeated
     keys, a 3 MB copy).

This file is ASCII-only: a backslash is BS, every other non-ASCII character is built with chr.
"""

from __future__ import annotations

import re
import subprocess
import time

import pytest

from sci_adk.render import bib_latex
from sci_adk.render.bib_latex import (
    MATH_COMMANDS,
    canonical_bib,
    command_issues,
    paper_bib,
    script_issues,
    typesettable,
)
from sci_adk.render.pkgreqs_checks import (
    bib_character_problems,
    bib_command_problems,
    bib_form_problems,
    bib_label_count_lines,
    bib_latex_safety_problems,
)
from tests.test_bib_allowlist import _preamble
from tests.test_bib_latex_copy import needs_tex
from tests.test_bib_round7 import BS, PKG, _TWO, _entry, _value

O_UML = chr(0xD6)  # LATIN CAPITAL LETTER O WITH DIAERESIS
U_UML = chr(0xFC)  # LATIN SMALL LETTER U WITH DIAERESIS
E_ACUTE = chr(0xE9)


def _live(text: str, name: str) -> int:
    """How often the command ``name`` is live in ``text`` (not printed as text)."""
    tail = r"(?![A-Za-z])" if name[-1].isalpha() else ""
    return len(re.findall(re.escape(BS + name) + tail, text))


def _nest(command: str, depth: int, inner: str = "x") -> str:
    value = inner
    for _ in range(depth):
        value = BS + command + "{" + value + "}"
    return value


def _build(tmp_path, bib: str, figure_bearing: bool, cites=("citep", "citet")):
    """The copy of ``bib``, every entry cited with each of ``cites``, built as Overleaf builds
    it under one of the preambles render emits: (errors, seconds the build took)."""
    copy = paper_bib(bib)
    (tmp_path / "references.bib").write_text(copy, encoding="utf-8")
    keys = re.findall(r"^@\w+\{([^,\n]+),", copy, re.M)
    body = [BS + "begin{document}"]
    body += [" ".join(BS + cmd + "{" + key + "}" for key in keys) for cmd in cites]
    body += [BS + "bibliographystyle{plainnat}", BS + "bibliography{references}",
             BS + "end{document}"]
    (tmp_path / "t.tex").write_text("\n".join(_preamble(figure_bearing, "paper") + body) + "\n",
                                    encoding="utf-8")
    pdflatex = ["pdflatex", "-interaction=nonstopmode", "t.tex"]
    status = 0
    start = time.monotonic()
    for cmd in (pdflatex, ["bibtex", "t"], pdflatex, pdflatex):
        status = subprocess.run(cmd, cwd=tmp_path, capture_output=True, check=False,
                                timeout=300).returncode
        if cmd[0] == "bibtex" and status >= 2:
            return [f"bibtex exited {status}"], time.monotonic() - start
    elapsed = time.monotonic() - start
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace")
    errors = [line for line in log.splitlines() if line.startswith("!")]
    errors += re.findall(r"Missing character: There is no .*", log)
    errors += re.findall(r"Citation .* undefined", log)
    if status != 0:
        errors.append(f"pdflatex exited {status}")
    return errors, elapsed


# -- 1. a link inside a link ----------------------------------------------------------------------

def _links(depth: int, inner: str = "x") -> str:
    value = inner
    for k in range(depth):
        value = BS + "href{https://example.org/" + str(k) + "}{" + value + "}"
    return value


_INNER_URL = BS + "url{https://example.org/u}"
_LINK_CASES = {
    "href-12": _links(12),
    "href-10-url": _links(10, _INNER_URL),
    "href-2": _links(2),
    "url-in-href": _links(1, _INNER_URL),
}


@pytest.mark.parametrize("value", list(_LINK_CASES.values()), ids=list(_LINK_CASES))
def test_a_link_inside_a_link_is_printed_as_text_with_a_note(value):
    copy = canonical_bib(_entry(value))
    title = _value(copy.text)
    assert _live(title, "href") + _live(title, "url") == 1, title
    assert any("inside another link" in note for note in copy.notes), copy.notes
    assert paper_bib(copy.text) == copy.text


def test_one_link_is_kept_without_a_note():
    copy = canonical_bib(_entry(_links(1)))
    assert _live(_value(copy.text), "href") == 1 and copy.notes == ()


@pytest.mark.parametrize("value", list(_LINK_CASES.values()), ids=list(_LINK_CASES))
def test_verify_fails_a_link_inside_a_link_in_an_author_bib(value):
    assert any("inside another link" in issue for issue in command_issues(value))
    lines = bib_latex_safety_problems(_entry(value), package_source=PKG)
    assert any("inside another link" in line for line in lines), lines


def _misc(key: str, value: str, fields=("title", "note", "howpublished")) -> str:
    return ("@misc{" + key + ", author = {Doe, J.}, "
            + ", ".join(f + " = {" + value + "}" for f in fields) + ", year = {2020}}\n")


@needs_tex
@_TWO
def test_nested_links_compile_in_both_preambles(tmp_path, figure_bearing):
    bib = _misc("L12", _links(12)) + _misc("L10u", _links(10, _INNER_URL))
    errors, _seconds = _build(tmp_path, bib, figure_bearing)
    assert errors == [], errors[:5]


# -- 2. math and text wrappers nested, and many in one value ---------------------------------------

_ARROW = "$" + BS + "overrightarrow{AB}$"
# (value, command counted, how often it stays live, a phrase of the note)
_PAST_CAP = {
    "root-index-12": ("$" + _nest("sqrt[3]", 12) + "$", "sqrt", 1, "inside another " + BS + "sqrt"),
    "root-index-in-root": ("$" + BS + "sqrt{" + BS + "sqrt[3]{x}}$", "sqrt", 1,
                           "inside another " + BS + "sqrt"),
    "arrows-11": ("$" + _nest("overrightarrow", 11) + "$", "overrightarrow", 1,
                  "inside another arrow"),
    "left-arrows-10": ("$" + _nest("overleftarrow", 10) + "$", "overleftarrow", 1,
                       "inside another arrow"),
    "mixed-arrows": ("$" + BS + "overrightarrow{" + BS + "overleftarrow{x}}$", "overleftarrow", 0,
                     "inside another arrow"),
    "text-mode-arrows": (_nest("overrightarrow", 3), "overrightarrow", 1, "inside another arrow"),
    "wrappers-5": ("$" + BS + "hat{" + BS + "bar{" + BS + "vec{" + BS + "tilde{" + BS
                   + "dot{x}}}}}$", "dot", 0, "nested more than 4 deep"),
    "roots-5": ("$" + _nest("sqrt", 5) + "$", "sqrt", 4, "nested more than 4 deep"),
    "superscript-40": (_nest("textsuperscript", 40), "textsuperscript", 8, "nested more than 8 deep"),
    "subscript-40": (_nest("textsubscript", 40), "textsubscript", 8, "nested more than 8 deep"),
    "superscript-in-math": ("$" + BS + "mbox{" + _nest("textsuperscript", 9) + "}$",
                            "textsuperscript", 8, "nested more than 8 deep"),
    "emph-9": (_nest("emph", 9), "emph", 8, "nested more than 8 deep"),
    "arrows-33": (" ".join([_ARROW] * 33), "overrightarrow", 32, "more than 32 math commands"),
    "arrows-40": (" ".join([_ARROW] * 40), "overrightarrow", 32, "more than 32 math commands"),
}
_AT_CAP = {
    "root-index-around-root": "$" + BS + "sqrt[3]{" + BS + "sqrt{x}}$",
    "arrow": _ARROW,
    "wrappers-4": "$" + BS + "sqrt[3]{" + BS + "overrightarrow{" + BS + "widehat{" + BS
                  + "widetilde{x}}}}$",
    "superscript-8": _nest("textsuperscript", 8),
    "arrows-32": " ".join([_ARROW] * 32),
}


@pytest.mark.parametrize("case", list(_PAST_CAP.values()), ids=list(_PAST_CAP))
def test_past_a_cap_the_deeper_commands_are_printed_as_text_with_a_note(case):
    value, name, live, phrase = case
    copy = canonical_bib(_entry(value))
    title = _value(copy.text)
    assert _live(title, name) == live, title[:600]
    assert any(phrase in note for note in copy.notes), copy.notes
    assert paper_bib(copy.text) == copy.text


@pytest.mark.parametrize("case", list(_PAST_CAP.values()), ids=list(_PAST_CAP))
def test_verify_fails_past_a_cap_in_an_author_bib(case):
    value, _name, _live_count, phrase = case
    assert any(phrase in issue for issue in command_issues(value)), command_issues(value)
    lines = bib_latex_safety_problems(_entry(value), package_source=PKG)
    assert any(phrase in line for line in lines), lines


@pytest.mark.parametrize("value", list(_AT_CAP.values()), ids=list(_AT_CAP))
def test_at_a_cap_nothing_is_printed_as_text(value):
    copy = canonical_bib(_entry(value))
    assert copy.notes == () and "textbackslash" not in copy.text, (copy.notes, copy.text)
    assert command_issues(value) == []


def _random_nesting(rng, depth: int) -> str:
    """A value of links, text markup and math commands nested at random."""
    if depth == 0:
        return rng.choice(["x", "AB", "$y$", "2", ""])
    inner = _random_nesting(rng, depth - 1)
    pieces = [
        BS + "href{https://example.org/" + str(depth) + "}{" + inner + "}",
        BS + "url{https://example.org/u}" + inner,
        BS + "textsuperscript{" + inner + "}",
        BS + "emph{" + inner + "}",
        "$" + BS + "sqrt[3]{" + inner.replace("$", "") + "}$",
        "$" + BS + "sqrt{" + inner.replace("$", "") + "}$",
        "$" + BS + "overrightarrow{" + inner.replace("$", "") + "}$",
        "$" + BS + "hat{" + inner.replace("$", "") + "}^2^3$",
        "$" + BS + "frac{" + inner.replace("$", "") + "}{2}_1'$",
        "$" + BS + "mbox{" + inner.replace("$", "") + "}$",
        BS + "overleftarrow{" + inner + "}",
        inner + " " + inner,
    ]
    return rng.choice(pieces)


def test_the_copy_of_random_nestings_is_its_own_fixed_point_and_clean():
    import random

    rng = random.Random(20261021)
    for _ in range(400):
        value = _random_nesting(rng, rng.randint(1, 14))
        copy = paper_bib(_entry(value))
        assert paper_bib(copy) == copy, value
        written = _value(copy)
        assert command_issues(written) == [], (value, written, command_issues(written))
        assert script_issues(written) == [], (value, written)


@needs_tex
@_TWO
def test_values_at_the_caps_compile_fast(tmp_path, figure_bearing):
    bib = "".join(_entry(v, key="C" + str(k)) for k, v in enumerate(_AT_CAP.values()))
    errors, seconds = _build(tmp_path, bib, figure_bearing)
    assert errors == [], errors[:5]
    assert seconds < 60, seconds


@needs_tex
@_TWO
def test_values_past_the_caps_compile_fast_because_the_excess_is_text(tmp_path, figure_bearing):
    values = [case[0] for case in _PAST_CAP.values()]
    values.append("$" + _nest("overrightarrow", 49) + "$")
    bib = "".join(_entry(v, key="P" + str(k)) for k, v in enumerate(values))
    errors, seconds = _build(tmp_path, bib, figure_bearing)
    assert errors == [], errors[:5]
    assert seconds < 60, seconds


_LONG_FIELDS = ("title", "booktitle", "series", "chapter", "publisher", "address", "edition",
                "note")


@needs_tex
@_TWO
def test_eight_long_fields_of_arrows_compile_fast(tmp_path, figure_bearing):
    arrows = " ".join([_ARROW] * 4500)  # about 99000 characters
    assert 95000 < len(arrows) < 100000
    bib = ("@incollection{A2020, author = {Doe, J.}, "
           + ", ".join(f + " = {" + arrows + "}" for f in _LONG_FIELDS) + ", year = {2020}}\n")
    errors, seconds = _build(tmp_path, bib, figure_bearing)
    assert errors == [], errors[:5]
    assert seconds < 120, seconds


# -- 3. citation keys ---------------------------------------------------------------------------------

_NON_ASCII_LETTERS = [chr(c) for c in range(0xA0, 0x250) if chr(c).isalpha() and typesettable(chr(c))]


def _article(key: str, year: int = 2020) -> str:
    return ("@article{" + key + ", author = {Doe, J.}, title = {T}, journal = {J}, year = {"
            + str(year) + "}}\n")


def test_a_key_starting_outside_ascii_is_left_out_with_a_note_suggesting_an_ascii_key():
    assert len(_NON_ASCII_LETTERS) > 60
    for c in _NON_ASCII_LETTERS:
        key = c + "nal2019"
        copy = canonical_bib(_article(key))
        assert "@article{" + key not in copy.text, key
        notes = [note for note in copy.notes if key in note]
        assert len(notes) == 1 and "ASCII" in notes[0], (key, copy.notes)
    note = next(n for n in canonical_bib(_article(O_UML + "nal2019")).notes)
    assert "'Onal2019'" in note, note


def test_a_key_with_a_letter_outside_ascii_after_the_first_is_kept():
    key = "M" + U_UML + "ller2019"
    copy = canonical_bib(_article(key))
    assert "@article{" + key + "," in copy.text and copy.notes == ()


def test_a_key_longer_than_200_characters_is_left_out():
    assert "@article{" + "a" * 200 + "," in paper_bib(_article("a" * 200))
    copy = canonical_bib(_article("a" * 201))
    assert "@article" not in copy.text
    assert any("200 characters" in note for note in copy.notes), copy.notes


@pytest.mark.parametrize("key", [O_UML + "nal2019", chr(0xAA) + "x2019", "a" * 201],
                         ids=["o-umlaut", "ordinal", "long"])
def test_verify_fails_such_a_key_in_an_author_bib(key):
    lines = bib_latex_safety_problems(_article(key), package_source=PKG)
    assert any(line.startswith("bib entry:") and key[:30] in line for line in lines), lines


_CITE_COMMANDS = ("citep", "citet", "cite", "citeauthor")


@needs_tex
@_TWO
def test_every_first_character_the_copy_keeps_is_citable_by_each_cite_command(
    tmp_path, figure_bearing
):
    firsts = sorted(bib_latex._KEY_ASCII)
    accepted = {chr(c) for c in range(0x21, 0x3000) if bib_latex._key_ok(chr(c) + "key")}
    assert accepted == set(firsts)
    keys = [c + "key" for c in firsts] + ["M" + U_UML + "ller2019", "k" * 200]
    bib = "".join(_article(key, 1800 + k) for k, key in enumerate(keys))
    errors, _seconds = _build(tmp_path, bib, figure_bearing, cites=_CITE_COMMANDS)
    assert errors == [], errors[:5]


# -- 5. a name ending in a comma and only ties or hyphens ---------------------------------------------

_EMPTY_TAILS = ["Doe, -", "Doe, J, -", "Doe, ~", "Doe,--", "Doe, J., ~", "Doe, - ~"]


def _named(name: str, key: str = "N1") -> str:
    return "@misc{" + key + ", author = {" + name + "}, title = {T}, year = {2020}}\n"


@pytest.mark.parametrize("name", _EMPTY_TAILS)
def test_a_name_ending_in_a_comma_and_only_ties_or_hyphens_is_written_without_them(name):
    copy = canonical_bib(_named(name))
    author = _value(copy.text, "author")
    assert not re.search(r",[\s~-]*$", author), author
    assert author.startswith("Doe"), author
    assert any("comma" in note for note in copy.notes), copy.notes
    assert paper_bib(copy.text) == copy.text


def _bibtex_status(tmp_path, bib: str) -> int:
    (tmp_path / "references.bib").write_text(bib, encoding="utf-8")
    (tmp_path / "t.aux").write_text(BS + "citation{*}\n" + BS + "bibstyle{plainnat}\n" + BS
                                    + "bibdata{references}\n", encoding="utf-8")
    return subprocess.run(["bibtex", "t"], cwd=tmp_path, capture_output=True, check=False,
                          timeout=120).returncode


@needs_tex
def test_bibtex_reads_the_copy_of_those_names_without_an_error(tmp_path):
    bib = "".join(_named(name, "N" + str(k)) for k, name in enumerate(_EMPTY_TAILS))
    raw = tmp_path / "raw"
    raw.mkdir()
    assert _bibtex_status(raw, bib) == 2  # the store as written: "has a comma at the end"
    assert _bibtex_status(tmp_path, paper_bib(bib)) == 0


# -- 6. more than 26 entries with one label ---------------------------------------------------------

def _same_label(n: int, author: str = "Doe, J.", prefix: str = "D") -> str:
    return "".join("@article{" + prefix + str(k) + ", author = {" + author + "}, title = {T"
                   + str(k) + "}, journal = {J}, year = {2020}}\n" for k in range(n))


def _cite_all(n: int) -> str:
    return BS + "citep{" + ",".join("D" + str(k) for k in range(n)) + "}"


def test_more_than_26_entries_with_one_label_are_a_render_warning_and_not_rewritten():
    copy = canonical_bib(_same_label(27))
    notes = [note for note in copy.notes if "27 entries" in note]
    assert len(notes) == 1 and "Doe (2020)" in notes[0], copy.notes
    assert copy.text.count("@article") == 27
    assert canonical_bib(_same_label(26)).notes == ()


def test_verify_fails_more_than_26_cited_entries_with_one_label_and_advises_otherwise():
    bib = paper_bib(_same_label(27))
    problems, advisories = bib_label_count_lines(bib, _cite_all(27), source="references.bib")
    assert len(problems) == 1 and problems[0].startswith("bib label:") and not advisories
    assert "27" in problems[0] and "Doe (2020)" in problems[0], problems
    problems, advisories = bib_label_count_lines(bib, BS + "citep{D1,D2}", source="references.bib")
    assert not problems and len(advisories) == 1 and "2 of them" in advisories[0], advisories
    problems, _ = bib_label_count_lines(bib, BS + "nocite{*}", source="references.bib")
    assert len(problems) == 1
    assert bib_label_count_lines(paper_bib(_same_label(26)), _cite_all(26)) == ([], [])


def test_the_label_is_the_one_plainnat_makes():
    mixed = _same_label(14, "Doe, J.", "E") + _same_label(13, "Doe, John")
    assert len(bib_label_count_lines(mixed, BS + "nocite{*}")[0]) == 1  # one label: Doe (2020)
    first_last = _same_label(14, "J. Doe", "E") + _same_label(13, "Doe, J.")
    assert len(bib_label_count_lines(first_last, BS + "nocite{*}")[0]) == 1
    two = _same_label(14, "Doe, J. and Roe, R.", "E") + _same_label(13, "Doe, J.")
    assert bib_label_count_lines(two, BS + "nocite{*}") == ([], [])
    etal = (_same_label(14, "Doe, J. and Roe, R. and Poe, P.", "E")
            + _same_label(13, "Doe, J. and Moe, M. and Zoe, Z."))
    assert len(bib_label_count_lines(etal, BS + "nocite{*}")[0]) == 1  # Doe et al. (2020)


def test_verify_of_a_run_fails_more_than_26_cited_entries_with_one_label(tmp_path):
    from sci_adk.loop.verify import verify_run
    from tests.test_latex_sanitize_round3 import _rendered_run

    run_dir = _rendered_run(tmp_path, "bib-labels")
    paper = run_dir / "paper"
    (paper / "references.bib").write_text(paper_bib(_same_label(27)), encoding="utf-8")
    draft = paper / "draft.tex"
    text = draft.read_text(encoding="utf-8")
    end = BS + "end{document}"
    draft.write_text(text.replace(end, _cite_all(27) + "\n" + end), encoding="utf-8")
    report = verify_run(run_dir)
    assert [p for p in report.paper_requirements_problems if p.startswith("bib label:")], (
        report.paper_requirements_problems)
    draft.write_text(text.replace(end, BS + "citep{D1}\n" + end), encoding="utf-8")
    report = verify_run(run_dir)
    assert not [p for p in report.paper_requirements_problems if p.startswith("bib label:")]
    assert [a for a in report.paper_advisory if a.startswith("bib label:")], report.paper_advisory


# -- 7. a script error in an author's bibliography --------------------------------------------------

_SCRIPT_ERRORS = {
    "double-superscript": "$x^2^3$",
    "double-subscript": "$x_1_2$",
    "prime-after-superscript": "$x^2'$",
    "braced-double": "$x^{2}^{3}$",
    "nothing-to-take": "$x^$",
    "declaration": "$x^" + BS + "rm 2$",
    "spaced-primes": "$x' '$",
    "spaced-prime-superscript": "$x' ^2$",
    "accent-unbraced": "$x^" + BS + "hat{y}$",
    "macro-unbraced": "$x^" + BS + "cdots$",
    "operator-unbraced": "$x_" + BS + "log$",
    "letter-outside-ascii": "$x^" + E_ACUTE + "$",
    "tie": "$x^~$",
    "math-space": "$x^" + BS + ",$",
}
_SCRIPTS_FINE = {
    "prime-superscript": "$x'^2$",
    "primes": "$x''$",
    "symbol": "$x^" + BS + "alpha$",
    "prime-command": "$x^" + BS + "prime$",
    "mathrm": "$x^" + BS + "mathrm{T}$",
    "both": "$x^{2}_{1}$",
    "sub-sup": "$x_1^2$",
    "prime-sub": "$x'_1$",
    "escaped-brace": "$" + BS + "{x" + BS + "}^2$",
    "group-base": "${x^2}^3$",
    "frac": "$x^" + BS + "frac{1}{2}$",
}


@pytest.mark.parametrize("value", list(_SCRIPT_ERRORS.values()), ids=list(_SCRIPT_ERRORS))
def test_an_author_bib_with_a_script_error_fails_with_a_bib_script_line(value):
    assert script_issues(value), value
    lines = bib_latex_safety_problems(_entry(value), package_source=PKG)
    assert [line for line in lines if line.startswith("bib script:")], lines


@pytest.mark.parametrize("value", list(_SCRIPTS_FINE.values()), ids=list(_SCRIPTS_FINE))
def test_a_script_that_compiles_does_not_fail(value):
    assert script_issues(value) == [], script_issues(value)
    lines = bib_latex_safety_problems(_entry(value), package_source=PKG)
    assert not [line for line in lines if line.startswith("bib script:")], lines


@pytest.mark.parametrize("value", list(_SCRIPT_ERRORS.values()) + list(_SCRIPTS_FINE.values()),
                         ids=list(_SCRIPT_ERRORS) + list(_SCRIPTS_FINE))
def test_the_copy_holds_no_script_error(value):
    copy = paper_bib(_entry(value))
    assert script_issues(_value(copy)) == [], _value(copy)
    assert not [line for line in bib_command_problems(copy) if line.startswith("bib script:")]
    assert paper_bib(copy) == copy


def test_the_copy_keeps_a_superscript_right_after_a_prime_on_its_base():
    assert _value(paper_bib(_entry("$x'^2$"))) == "{$x'^{2}$}"
    assert _value(paper_bib(_entry("$x' '$"))) == "{$x' {}'$}"


@needs_tex
@_TWO
def test_the_copy_of_every_script_case_compiles(tmp_path, figure_bearing):
    values = list(_SCRIPT_ERRORS.values()) + list(_SCRIPTS_FINE.values())
    bib = "".join(_entry(v, key="S" + str(k)) for k, v in enumerate(values))
    errors, _seconds = _build(tmp_path, bib, figure_bearing)
    assert errors == [], errors[:5]


def _script_probe(name: str) -> str:
    kind = MATH_COMMANDS[name]
    args = "{a}{b}" if kind == "two" else "{a}" if kind in ("one", "text", "math") else ""
    return "$x^" + BS + name + args + "$ $x_" + BS + name + args + "$" + BS + "par"


def _probe_errors(tmp_path, lines: list[str], figure_bearing: bool) -> list[str]:
    preamble = _preamble(figure_bearing, "paper")
    (tmp_path / "t.tex").write_text("\n".join(preamble + [BS + "begin{document}"] + lines
                                              + [BS + "end{document}"]) + "\n", encoding="utf-8")
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "t.tex"], cwd=tmp_path,
                   capture_output=True, check=False, timeout=300)
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace").splitlines()
    offset = len(preamble) + 1
    failed = []
    for k, line in enumerate(log):
        if line.startswith("!"):
            where = next((x for x in log[k: k + 8] if x.startswith("l.")), "")
            if where:
                failed.append(lines[int(where[2:].split()[0]) - offset - 1])
    return failed


@needs_tex
@_TWO
def test_every_math_command_off_the_unsafe_list_takes_no_braces_after_a_script(
    tmp_path, figure_bearing
):
    names = sorted(n for n in MATH_COMMANDS if n not in bib_latex._SCRIPT_UNSAFE)
    failed = _probe_errors(tmp_path, [_script_probe(n) for n in names], figure_bearing)
    assert failed == [], failed[:5]


@needs_tex
def test_each_command_on_the_unsafe_list_needs_braces_in_one_of_the_preambles(tmp_path):
    names = sorted(bib_latex._SCRIPT_UNSAFE)
    lines = [_script_probe(n) for n in names]
    failed: set[str] = set()
    for figure_bearing in (False, True):
        run = tmp_path / ("times" if figure_bearing else "lm")
        run.mkdir()
        failed |= set(_probe_errors(run, lines, figure_bearing))
    assert {n for n, line in zip(names, lines) if line not in failed} == set()


# -- 8. the author-bib gate on large files -----------------------------------------------------------

def _timed(function, *args, **kwargs):
    start = time.monotonic()
    out = function(*args, **kwargs)
    return out, time.monotonic() - start


def test_the_gate_reads_100000_string_macros_quickly_and_fails_their_number():
    bib = ("".join("@string{m" + str(i) + " = {Value " + str(i) + "}}\n" for i in range(100000))
           + "@article{A2020, title = m1, year = {2020}}\n")
    lines, seconds = _timed(bib_latex_safety_problems, bib, package_source=PKG)
    assert seconds < 30, seconds
    assert [line for line in lines if line.startswith("bib size:")], lines[:3]


def test_the_gate_reads_50000_repeated_keys_quickly():
    bib = "".join("@article{A2020, title = {T" + str(i) + "}, year = {2020}}\n"
                  for i in range(50000))
    lines, seconds = _timed(bib_latex_safety_problems, bib, package_source=PKG)
    assert seconds < 30, seconds
    assert [line for line in lines if line.startswith("bib size:")], lines[:3]
    assert [line for line in lines if "repeats the key" in line]


def _canonical_copy(entries: int) -> str:
    one = paper_bib("@article{K0, author = {Doe, J. and Roe, R.}, title = {A title with $x^2$ and "
                    + BS + "textit{italics}}, journal = {J. Chem.}, year = {2020}, pages = {1--10}}\n")
    return "\n".join(one.replace("{K0,", "{K" + str(i) + ",", 1) for i in range(entries))


def test_a_3_mb_copy_is_checked_quickly():
    copy = _canonical_copy(19000)
    assert len(copy) > 3_000_000
    start = time.monotonic()
    lines = (bib_form_problems(copy) + bib_command_problems(copy) + bib_character_problems(copy)
             + bib_latex_safety_problems(copy))
    seconds = time.monotonic() - start
    assert seconds < 30, seconds
    assert [line for line in lines if line.startswith("bib size:")], lines[:3]


def test_below_the_size_cap_the_checks_find_nothing_and_stay_quick():
    copy = _canonical_copy(4000)
    start = time.monotonic()
    lines = (bib_form_problems(copy) + bib_command_problems(copy) + bib_character_problems(copy)
             + bib_latex_safety_problems(copy, package_source=PKG))
    seconds = time.monotonic() - start
    assert lines == [], lines[:3]
    assert seconds < 30, seconds
