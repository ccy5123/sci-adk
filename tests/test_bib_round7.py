"""
The canonical bibliography copy and its verify checks, round 7.

Independent checkers found six more inputs that stop pdflatex in draft.tex, si.tex and
deposit/record.tex while render exits 0 and verify says nothing, because the copy is its own
fixed point:

  1. an unbraced '(' in a last name or a key field, followed by a command, an accent group or a
     letter outside ASCII: natbib takes the label up to the first '(' as the names and the rest
     as the year ("Improper alphabetic constant");
  2. an entry plainnat labels by the first three characters of its organization (an authorless
     manual or proceedings) or of its citation key (no author, editor, key or organization):
     three characters can cut an escaped special or math, or a letter outside ASCII, in two;
     and a key field long enough for BibTeX to cut the label;
  3. the math command not followed by anything but one character or one plain math symbol:
     newtxmath's version loops ("TeX capacity exceeded");
  4. a font declaration (rm it bf sf tt) between two scripts of one kind ("Double
     superscript");
  5. an author's package bibliography with a command holding a capital letter, or math, at
     brace level 0 of a title: BibTeX's case change lowercases it;
  6. an accent over an empty or doubly braced group ("Missing endcsname inserted").

This file is ASCII-only: a backslash is BS, every other non-ASCII character is built with chr.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from sci_adk.render.bib_latex import canonical_bib, command_issues, paper_bib
from sci_adk.render.pkgreqs_checks import bib_form_problems, bib_latex_safety_problems
from tests.test_bib_allowlist import _RENDER_PREAMBLES, _preamble
from tests.test_bib_latex_copy import _compile_with_bib, needs_tex

BS = chr(92)
O_UML = chr(0xD6)  # LATIN CAPITAL LETTER O WITH DIAERESIS
SHARP_S = chr(0xDF)
E_ACUTE = chr(0xE9)
PKG = "package_src/references.bib, which the package copies unchanged"

_FOUR = pytest.mark.parametrize(
    "figure_bearing, which", [(f, w) for _n, f, w in _RENDER_PREAMBLES],
    ids=[n for n, _f, _w in _RENDER_PREAMBLES],
)
_TWO = pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])


def _entry(value: str, key: str = "K1", field: str = "title") -> str:
    return "@article{" + key + ", " + field + " = {" + value + "}, year = {2020}}\n"


def _value(bib: str, field: str = "title", key: str | None = None) -> str:
    text = bib
    if key is not None:
        start = text.index("{" + key + ",")
        text = text[start: text.index("\n}", start)]
    m = re.search(r"^  " + field + r" = \{(.*)\},?$", text, re.M)
    assert m is not None, bib
    return m.group(1)


def _level0(text: str) -> str:
    """The characters of ``text`` at brace level 0 (an escaped brace is no brace)."""
    out, depth, i = [], 0, 0
    while i < len(text):
        c = text[i]
        if c == BS:
            if depth == 0:
                out.append(text[i: i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 0:
            out.append(c)
        i += 1
    return "".join(out)


def _live(text: str) -> str:
    """``text`` without the commands the copy printed as text."""
    return text.replace("{" + BS + "textbackslash}", "")


def _cited_build(tmp_path, bib: str, figure_bearing: bool, which: str) -> list[str]:
    """The copy cited by every key (citep and citet) under one of the preambles render emits,
    built as Overleaf builds it; the errors pdflatex and bibtex report."""
    copy = paper_bib(bib)
    (tmp_path / "references.bib").write_text(copy, encoding="utf-8")
    keys = re.findall(r"^@\w+\{([^,\n]+),", copy, re.M)
    body = [BS + "begin{document}",
            "See " + BS + "citep{" + ",".join(keys) + "} and " + BS + "citet{" + ",".join(keys) + "}.",
            BS + "nocite{*}", BS + "bibliographystyle{plainnat}", BS + "bibliography{references}",
            BS + "end{document}"]
    (tmp_path / "t.tex").write_text("\n".join(_preamble(figure_bearing, which) + body) + "\n",
                                    encoding="utf-8")
    pdflatex = ["pdflatex", "-interaction=nonstopmode", "t.tex"]
    status = 0
    for cmd in (pdflatex, ["bibtex", "t"], pdflatex, pdflatex):
        status = subprocess.run(cmd, cwd=tmp_path, capture_output=True, check=False,
                                timeout=120).returncode
        if cmd[0] == "bibtex" and status >= 2:
            return [f"bibtex exited {status}"]
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace")
    errors = [line for line in log.splitlines() if line.startswith("!")]
    errors += re.findall(r"Missing character: There is no .*", log)
    errors += re.findall(r"Citation .* undefined", log)
    if status != 0:
        errors.append(f"pdflatex exited {status}")
    return errors


# -- 1. a parenthesis in a name or a key -----------------------------------------------------------

_PAREN_NAMES = {
    "accent-group": "Doe ({" + BS + '"{O}}nal), J.',
    "raw-letter": "Doe (" + O_UML + "nal), J.",
    "escaped-special": "Doe (" + BS + "_), J.",
    "markup": "Doe (" + BS + "textit{x}), J.",
    "math": "Doe ($" + BS + "alpha$), J.",
    "sharp-s": "Doe (" + SHARP_S + "), J.",
    "space-then-accent": "Doe ( " + BS + "'e), J.",
    "open-only": "Doe (" + BS + "'e, J.",
}
_LABEL_ENTRY = {
    "author": "@article{{{key}, author = {{{name}}}, title = {{T}}, journal = {{J}}, year = {{2020}}}}\n",
    "editor": "@book{{{key}, editor = {{{name}}}, title = {{T}}, publisher = {{P}}, year = {{2020}}}}\n",
    "key": "@misc{{{key}, key = {{{name}}}, title = {{T}}, year = {{2020}}}}\n",
}


def _label_entry(field: str, name: str, key: str = "K1") -> str:
    return _LABEL_ENTRY[field].format(key=key, name=name)


@pytest.mark.parametrize("field", list(_LABEL_ENTRY))
@pytest.mark.parametrize("name", list(_PAREN_NAMES.values()), ids=list(_PAREN_NAMES))
def test_a_parenthesis_at_brace_level_0_of_a_label_field_is_braced(field, name):
    copy = paper_bib(_label_entry(field, name))
    value = _value(copy, field)
    assert "(" not in _level0(value) and ")" not in _level0(value), value
    assert "{(}" in value, value
    assert paper_bib(copy) == copy


def test_a_parenthesis_in_a_title_or_a_first_name_is_left_as_it_is():
    copy = paper_bib("@article{K1, author = {Doe, J. (Jr)}, title = {Growth (in vitro)},"
                     " year = {2020}}\n")
    assert "(in vitro)" in _value(copy) and "{(}" not in _value(copy)


@needs_tex
@_FOUR
def test_the_copy_of_each_parenthesised_label_compiles_when_cited(tmp_path, figure_bearing, which):
    bib = "".join(_label_entry(field, name, f"P{k}{field[0]}")
                  for field in _LABEL_ENTRY for k, name in enumerate(_PAREN_NAMES.values()))
    errors = _cited_build(tmp_path, bib, figure_bearing, which)
    assert errors == [], errors[:5]


@pytest.mark.parametrize("field", list(_LABEL_ENTRY))
@pytest.mark.parametrize("name", list(_PAREN_NAMES.values()), ids=list(_PAREN_NAMES))
def test_an_author_bib_with_the_parenthesis_trap_fails_naming_the_entry(field, name):
    lines = bib_latex_safety_problems(_label_entry(field, name), package_source=PKG)
    assert any("'K1'" in line and "'('" in line and "natbib" in line and PKG in line
               for line in lines), lines


@pytest.mark.parametrize("name", ["Doe (onal), J.", "{Umweltbundesamt (" + O_UML + "sterreich)}",
                                  "Doe (2), J.", "Doe, J. (" + BS + "'e)", "Doe {(}" + BS + "'e{)}, J."])
def test_an_author_bib_with_a_harmless_parenthesis_passes(name):
    lines = bib_latex_safety_problems(_label_entry("author", name), package_source=PKG)
    assert not [line for line in lines if "'('" in line], lines


# -- 2. a label made of the first three characters --------------------------------------------------

_ORGS = {
    "ampersand": "AT&T Bell Laboratories",
    "percent": "50% Corp",
    "underscore": "My_Company",
    "dollar": "US" + BS + "$ Corp",
    "math": "$" + BS + "alpha$ Corp",
    "cut-letter": "AB" + O_UML + " Corp",
    "the-then-ampersand": "The A&B Group",
}


def _org_entry(kind: str, org: str, key: str = "K1", extra: str = "") -> str:
    return ("@" + kind + "{" + key + ", organization = {" + org + "}, title = {T}, year = {1979}"
            + extra + "}\n")


@pytest.mark.parametrize("kind", ["manual", "proceedings"])
@pytest.mark.parametrize("org", list(_ORGS.values()), ids=list(_ORGS))
def test_an_authorless_entry_labelled_by_an_unsafe_organization_gets_a_plain_key(kind, org):
    result = canonical_bib(_org_entry(kind, org))
    key = _value(result.text, "key")
    assert key and len(key) <= 3 and all(c.isalnum() or c == " " for c in key), key
    assert any("'K1'" in n and "key" in n and "label" in n for n in result.notes), result.notes
    assert paper_bib(result.text) == result.text


@pytest.mark.parametrize("kind", ["manual", "proceedings"])
def test_an_authorless_entry_with_a_plain_organization_keeps_plainnat_s_label(kind):
    copy = paper_bib(_org_entry(kind, "IEEE Standards Association"))
    assert "key =" not in copy


def test_an_entry_with_an_author_editor_or_key_gets_no_key():
    for bib in ("@manual{K1, author = {Doe, J.}, organization = {AT&T}, title = {T}}\n",
                "@proceedings{K1, editor = {Doe, J.}, organization = {AT&T}, title = {T}}\n",
                "@manual{K1, key = {ATT}, organization = {AT&T}, title = {T}}\n"):
        copy = paper_bib(bib)
        assert copy.count("key =") == bib.count("key ="), copy


def test_an_empty_key_field_is_replaced_not_repeated():
    copy = paper_bib("@manual{K1, key = { }, organization = {AT&T}, title = {T}}\n")
    assert copy.count("key =") == 1 and _value(copy, "key").strip(), copy


@pytest.mark.parametrize("key", ["a_b2020", "Ab" + E_ACUTE + "2019", "_x2020"])
def test_an_entry_labelled_by_an_unsafe_citation_key_prefix_gets_a_plain_key(key):
    result = canonical_bib("@misc{" + key + ", title = {T}, year = {2020}}\n")
    written = _value(result.text, "key")
    assert written and "_" not in _level0(written).replace(BS + "_", ""), written
    assert paper_bib(result.text) == result.text


@pytest.mark.parametrize("key", ["Doe2020", "A" + E_ACUTE + "b2019", "abc_2020"])
def test_an_entry_labelled_by_a_safe_citation_key_prefix_gets_no_key(key):
    assert "key =" not in paper_bib("@misc{" + key + ", title = {T}, year = {2020}}\n")


def test_a_key_field_is_bounded_like_a_last_name():
    result = canonical_bib("@misc{K1, key = {" + "abc " * 70 + "{" + BS + "'e}}, title = {T}}\n")
    assert len(_value(result.text, "key")) <= 110
    assert any("'K1'" in n and "key" in n for n in result.notes), result.notes
    assert paper_bib(result.text) == result.text


_LONG_KEY = "a" * 245 + "{" + BS + "'e}" + "b" * 20


@needs_tex
@_FOUR
def test_the_copy_of_each_three_character_label_compiles_when_cited(tmp_path, figure_bearing, which):
    bib = "".join(_org_entry(kind, org, f"O{k}{kind[0]}")
                  for kind in ("manual", "proceedings") for k, org in enumerate(_ORGS.values()))
    bib += ("@inproceedings{C1, author = {Doe, J.}, title = {T}, booktitle = {B}, crossref = {Q9},"
            " year = {1979}}\n" + _org_entry("proceedings", "AT&T Bell Laboratories", "Q9"))
    bib += "".join("@misc{" + key + ", title = {T}, year = {2020}}\n"
                   for key in ("a_b2020", "Ab" + E_ACUTE + "2019"))
    bib += "@misc{L1, key = {" + _LONG_KEY + "}, title = {T}, year = {2020}}\n"
    errors = _cited_build(tmp_path, bib, figure_bearing, which)
    assert errors == [], errors[:5]


@pytest.mark.parametrize("bib", [
    _org_entry("manual", "AT&T Bell Laboratories"),
    _org_entry("proceedings", "50% Corp"),
    "@misc{a_b2020, title = {T}, year = {2020}, note = {x}}\n",
    "@misc{L1, key = {" + _LONG_KEY + "}, title = {T}, year = {2020}}\n",
], ids=["manual", "proceedings", "key-prefix", "long-key"])
def test_an_author_bib_with_an_unsafe_label_fails_naming_the_entry(bib):
    lines = bib_latex_safety_problems(bib, package_source=PKG)
    assert any("label" in line and "natbib" in line and PKG in line for line in lines), lines


def test_an_author_bib_with_a_plain_three_character_label_passes():
    lines = bib_latex_safety_problems(_org_entry("manual", "IEEE Standards"), package_source=PKG)
    assert not [line for line in lines if "label" in line], lines


# -- 3. the math command not -----------------------------------------------------------------------

_NOT = BS + "not"
_NOT_PRINTED = [
    "$" + _NOT + BS + "foo$", "$" + _NOT + BS + "nmid$", "$" + _NOT + BS + "textit{x}$",
    "$" + _NOT + BS + "ss$", "$" + _NOT + BS + "textendash$", "$" + _NOT + BS + "frac{a}{b}$",
    "$" + _NOT + BS + "sqrt{x}$", "$" + _NOT + BS + "hat{x}$", "$" + _NOT + BS + "mathrm{x}$",
    "$" + _NOT + "{" + BS + "mbox{" + BS + "ss}}$", "$" + _NOT + "{}$", "$" + _NOT + "{{x}}$",
    "$a" + _NOT + "$", "$" + _NOT + " " + E_ACUTE + "$", "$" + _NOT + "{=x}$",
    _NOT + BS + "foo in text", "$" + _NOT + BS + "rm x$",
]
_NOT_KEPT = [
    "$a" + _NOT + BS + "in b$", "$a" + _NOT + "= b$", "$a" + _NOT + BS + "equiv b$",
    "$a" + _NOT + "{=} b$", "$a" + _NOT + "<b$", "$a" + _NOT + "{" + BS + "subset} b$",
    "$a " + _NOT + " " + BS + "approx b$", "$" + _NOT + " x$",
]


@pytest.mark.parametrize("math", _NOT_PRINTED)
def test_not_before_anything_but_one_symbol_is_printed_as_text(math):
    value = _value(paper_bib(_entry(math)))
    assert _NOT not in _live(value), value
    assert "{" + BS + "textbackslash}not" in value, value
    assert BS + "not" in " ".join(command_issues(math)), command_issues(math)


@pytest.mark.parametrize("math", _NOT_KEPT)
def test_not_before_one_character_or_one_plain_symbol_is_kept(math):
    value = _value(paper_bib(_entry(math)))
    assert _NOT + "{" in _live(value), value
    assert _NOT + "{}" not in value and _NOT + "{{" not in value, value
    assert command_issues(math) == []


@needs_tex
@_TWO
def test_the_copy_of_each_not_shape_compiles(tmp_path, figure_bearing):
    bib = "".join(_entry(m, f"N{k}") for k, m in enumerate(_NOT_PRINTED + _NOT_KEPT))
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- 4. a font declaration between two scripts -------------------------------------------------

_FONT_SCRIPTS = [
    "$x^2" + BS + "rm^3$", "$x'" + BS + "sf^2$", "$x_1" + BS + "it_2$", "$x^2" + BS + "tt^3_1$",
    "$x_1" + BS + "bf_2$", "$x'" + BS + "rm'$", "$x^2 " + BS + "rm ^3$", "$x^2" + BS + "-^3$",
    "$x_1" + BS + "rm" + BS + "it_2$",
]


@pytest.mark.parametrize("math", _FONT_SCRIPTS)
def test_a_script_after_a_font_declaration_on_a_scripted_base_gets_an_empty_base(math):
    value = _value(paper_bib(_entry(math)))
    assert re.search(r"\{\}[\^_']", value), value


def test_a_font_declaration_before_the_first_script_changes_nothing():
    value = _value(paper_bib(_entry("$" + BS + "rm x^2$")))
    assert "{}^" not in value, value


@needs_tex
@_TWO
def test_the_copy_of_each_font_and_script_shape_compiles(tmp_path, figure_bearing):
    bib = "".join(_entry(m, f"F{k}") for k, m in enumerate(_FONT_SCRIPTS))
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- 5. BibTeX's case change in an author's bibliography -----------------------------------------

_CASE_CHANGED = {
    "LaTeX": "About " + BS + "LaTeX",
    "TeX": "On " + BS + "TeX{} macros",
    "section-sign": BS + "S 3 of the code",
    "Re": "The $" + BS + "Re z$ axis",
    "Delta": "Free energy $" + BS + "Delta G$",
    "capital-in-math": "Effect of $T$ on growth",
}


@pytest.mark.parametrize("title", list(_CASE_CHANGED.values()), ids=list(_CASE_CHANGED))
def test_an_author_bib_title_bibtex_would_lowercase_fails_with_the_braces_fix(title):
    lines = bib_latex_safety_problems(_entry(title), package_source=PKG)
    assert any("'K1'" in line and "case" in line and "braces" in line and PKG in line
               for line in lines), lines


def test_an_author_bib_edition_and_type_are_case_changed_too():
    bib = ("@book{K1, title = {T}, edition = {" + BS + "TeX}, year = {2020}}\n"
           "@techreport{K2, title = {T}, type = {" + BS + "LaTeX{} note}, year = {2020}}\n")
    lines = bib_latex_safety_problems(bib, package_source=PKG)
    assert any("'K1'" in line and "case" in line for line in lines), lines
    assert any("'K2'" in line and "case" in line for line in lines), lines


@pytest.mark.parametrize("title", [
    "About {" + BS + "LaTeX}", "About {" + BS + "TeX}", "The {$" + BS + "Re z$} axis",
    "{" + BS + "AE}sop and " + BS + "'Ecole", BS + "AE sop", "plain " + BS + "'e and $x$",
])
def test_an_author_bib_title_bibtex_leaves_alone_passes(title):
    lines = bib_latex_safety_problems(_entry(title), package_source=PKG)
    assert not [line for line in lines if "case" in line], lines


def test_a_note_is_not_case_changed():
    lines = bib_latex_safety_problems(_entry("About " + BS + "LaTeX", field="note"),
                                      package_source=PKG)
    assert not [line for line in lines if "case" in line], lines


@needs_tex
def test_the_case_change_route_does_stop_pdflatex(tmp_path):
    # Why: what BibTeX makes of an unbraced capital command in an author's title.
    errors, bbl, _dropped = _compile_with_bib(tmp_path, _entry("About " + BS + "LaTeX"), False)
    assert BS + "latex" in bbl and errors


def test_a_package_built_from_such_an_author_bib_fails_verify(tmp_path):
    lines = _package_bib_problems(tmp_path, _entry("About " + BS + "LaTeX", "A2020"))
    assert any("'A2020'" in line and "case" in line for line in lines), lines


def _package_bib_problems(tmp_path, bib: str) -> list[str]:
    from sci_adk.loop.verify import _check_package_requirements
    from sci_adk.render.package import assemble_package
    from tests.test_si_authoring_m6 import (
        _AUTHOR_SI_HEAD, _freeze_pkgreqs, _pkgreqs_obj, _seed_workspace,
    )

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    (src / "si.tex").write_text(_AUTHOR_SI_HEAD + BS + "citep{A2020}." + BS
                                + "bibliography{references_SI}" + BS + "end{document}",
                                encoding="utf-8")
    (src / "references.bib").write_text(bib, encoding="utf-8")
    pkgreqs = _pkgreqs_obj(ws)
    assemble_package(ws, pkgreqs)
    problems, _w, _r, _p = _check_package_requirements(ws, ws / "package", pkgreqs)
    return problems


# -- 6. an accent over an empty or doubly braced group -----------------------------------------

_ACCENTS = ["~", "'", '"', "^", "`", "c", "H", "u", "r", "k", "t", "v", "=", ".", "b", "d",
            "textcommabelow"]
_ACCENT_ARGS = {
    "empty-group": "{{}}",
    "space-then-group": "{ {}}",
    "group-then-space": "{{} }",
    "two-groups": "{{}{}}",
    "doubly-braced-command": "{{" + BS + "foo}}",
    "inner-accent-over-a-group": "{" + BS + "'{{}}}",
    "group-then-command": "{{a" + BS + "'e}b}",
}


@pytest.mark.parametrize("accent", ["~", "'", "c", "H"])
def test_an_accent_over_an_empty_group_gets_an_empty_argument(accent):
    value = _value(paper_bib(_entry("a " + BS + accent + "{{}} z")))
    assert BS + accent + "{}" in value, value


def test_an_accent_over_a_doubly_braced_command_loses_one_brace_pair():
    value = _value(paper_bib(_entry("a " + BS + '"{{' + BS + "foo}} z")))
    assert BS + '"{{' + BS + "textbackslash}foo}" in value, value


@pytest.mark.parametrize("arg", ["{{e}}", "{e}", "{{e}f}", "{" + BS + "i}", "{oo}", "{}"])
def test_an_accent_whose_argument_compiles_is_left_as_it_is(arg):
    value = _value(paper_bib(_entry("a " + BS + "~" + arg + " z")))
    assert BS + "~" + arg in value, value
    assert command_issues("a " + BS + "~" + arg + " z") == []


@pytest.mark.parametrize("arg", list(_ACCENT_ARGS.values()), ids=list(_ACCENT_ARGS))
def test_verify_names_an_author_accent_over_such_a_group(arg):
    assert command_issues("a " + BS + "~" + arg + " z"), arg


@pytest.mark.parametrize("arg", list(_ACCENT_ARGS.values()), ids=list(_ACCENT_ARGS))
def test_the_copy_of_each_accent_shape_is_its_own_fixed_point(arg):
    bib = "".join(_entry("a " + BS + acc + arg + " z", f"A{k}") for k, acc in enumerate(_ACCENTS))
    copy = paper_bib(bib)
    assert paper_bib(copy) == copy
    assert bib_form_problems(copy) == []


@needs_tex
@_TWO
def test_the_copy_of_each_accent_shape_compiles(tmp_path, figure_bearing):
    bib = "".join(
        "@misc{A" + str(j) + "x" + str(k) + ", title = {a " + BS + acc + arg + " z}, note = {a "
        + BS + acc + arg + " z}, year = {2020}}\n"
        for j, arg in enumerate(_ACCENT_ARGS.values()) for k, acc in enumerate(_ACCENTS)
    )
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), figure_bearing)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- every new check is silent on the copy render writes ----------------------------------------

_VOCABULARY = [
    "(", ")", " (", "( ", "[", "]", "{", "}", "{}", "{{}}", BS + "~", BS + "'", BS + '"',
    BS + "c", BS + "not", BS + "rm", BS + "it", "^", "_", "'", "$", BS + "in", "=", "x", "A",
    " ", ",", " and ", BS + "&", "&", "%", BS + "_", BS + "$", O_UML, SHARP_S, E_ACUTE,
    BS + "foo", BS + "textit", BS + "LaTeX", BS + "Delta", "The ", "AT", BS + "ss", "2020", "-",
]


@needs_tex
@_TWO
def test_the_copy_of_a_fuzz_compiles_when_every_entry_is_cited(tmp_path, figure_bearing):
    import random

    rng = random.Random(7)
    letters = "abcdefghijklmnopqrstuvwxyz"
    bib = ""
    for k in range(120):
        field = rng.choice(["author", "editor", "key", "title", "organization", "year", "note"])
        kind = rng.choice(["manual", "proceedings", "misc", "book", "article"])
        # distinct three-character prefixes: more than 26 entries sharing one label make
        # plainnat's year letters run past z (a separate limit, left open)
        key = rng.choice(["K", "_", "e", "a"]) + letters[k // 26] + letters[k % 26] + str(k)
        value = "".join(rng.choice(_VOCABULARY) for _ in range(rng.randint(1, 10)))
        bib += "@" + kind + "{" + key + ", " + field + " = {" + value + "}, title = {T}}\n"
    errors = _cited_build(tmp_path, bib, figure_bearing, "paper")
    assert errors == [], errors[:5]


# -- minor: time on tiny bibliographies ----------------------------------------------------------

def _doubling_chain(count: int) -> str:
    bib = '@string{a0 = "xy z"}\n' + "".join(
        "@string{a" + str(k) + " = a" + str(k - 1) + " # a" + str(k - 1) + "}\n"
        for k in range(1, count + 1))
    return bib + "@article{K1, title = a" + str(count) + ", year = {2020}}\n"


def test_a_chain_of_doubling_macros_is_cut_at_bibtex_s_limit_quickly():
    import time

    bib = _doubling_chain(27)  # 4 * 2**27 characters if expanded in full
    start = time.monotonic()
    result = canonical_bib(bib)
    assert time.monotonic() - start < 20
    assert any("'K1'" in n and "long" in n for n in result.notes), result.notes
    assert paper_bib(result.text) == result.text
    start = time.monotonic()
    lines = bib_latex_safety_problems(bib, package_source=PKG)
    assert time.monotonic() - start < 20
    assert any("'K1'" in line and "longer than" in line for line in lines), lines


@pytest.mark.parametrize("count", [20000, 200000])
def test_many_unclosed_markup_tags_are_read_in_linear_time(count):
    import time

    start = time.monotonic()
    canonical_bib(_entry("<i>" * count))
    assert time.monotonic() - start < 10


def test_nested_markup_of_one_kind_is_written_balanced():
    value = _value(paper_bib(_entry("<i>a<i>b</i>c</i> and <b>x</b>")))
    assert BS + "textit{a" + BS + "textit{b}c}" in value, value
    assert value.count("{") == value.count("}"), value
    assert command_issues("<i>a<i>b</i>c</i>") == []


# -- minor: the reader against BibTeX, in both directions ---------------------------------------

@needs_tex
def test_the_reader_reads_exactly_what_bibtex_prints_when_bibtex_reads_no_error(tmp_path):
    # The reader may read MORE than BibTeX in two places: after a syntax error, and on the
    # file's last line, where BibTeX reads only the first command (measured: a @string and an
    # entry on the last line give no entry; the same two lines followed by any other line give
    # both). With no error and a last line that holds no command, the two agree.
    from sci_adk.render.bib_latex import bib_syntax_issues
    from tests.test_bib_round6 import _bibtex_rows, _dump_bst, _mutated_bibs, _printed

    (tmp_path / "dump.bst").write_text(_dump_bst(), encoding="utf-8")
    checked, extra = 0, []
    for bib in _mutated_bibs(600, seed=101):
        bib += "\n\n"
        if bib_syntax_issues(bib):
            continue
        checked += 1
        rows = _bibtex_rows(tmp_path, bib)
        mine = {row for row in _printed(bib) if row[2]}
        if mine != rows:
            extra.append((bib, sorted(mine ^ rows)[:2]))
    assert checked > 50
    assert extra == [], extra[:3]


# -- minor: the lint for author-written LaTeX ---------------------------------------------------

@pytest.mark.parametrize("command", ["VerbatimInput", "makeatletter", "newread", "newwrite"])
def test_the_lint_names_more_file_readers_and_writers(command):
    from sci_adk.render.latex_lint import lint_commands

    assert lint_commands(BS + command + "{x}"), command


# -- minor: the form remedy once per file ----------------------------------------------------------

def test_the_form_remedy_is_printed_once_per_file_and_entry_lines_are_short():
    bib = "".join("@article{K" + str(k) + ",title={T" + str(k) + "}}\n" for k in range(5))
    lines = bib_form_problems(bib)
    assert sum("sci-adk render" in line for line in lines) == 1, lines
    entry_lines = [line for line in lines if "entry 'K" in line]
    assert len(entry_lines) == 5 and all("sci-adk render" not in line and len(line) < 200
                                         for line in entry_lines), entry_lines


# -- minor: an author's bibliography with other label and entry shapes ---------------------------

@pytest.mark.parametrize("bib, what", [
    ("@misc{K1, author = {[Anonymous]}, title = {T}, year = {2020}}\n", "'['"),
    ("@article{K1, author = {Doe, J.}, title = {T}, year = {20" + BS + "textit{20}}}\n", "year"),
    ("@article{k" + BS + "input, author = {Doe, J.}, title = {T}, year = {2020}}\n", "key"),
    ("@output{K1, author = {Doe, J.}, title = {T}, year = {2020}}\n", "@output"),
], ids=["bracketed-name", "year-with-markup", "backslash-in-key", "type-named-like-a-function"])
def test_an_author_bib_with_a_shape_bibtex_or_natbib_stops_on_fails(bib, what):
    lines = [line for line in bib_latex_safety_problems(bib, package_source=PKG)
             if line.startswith(("bib label:", "bib entry:"))]
    assert any(what in line and PKG in line for line in lines), lines


def test_an_author_bib_with_a_common_extra_type_passes():
    lines = bib_latex_safety_problems(
        "@online{K1, author = {Doe, J.}, title = {T}, year = {2020}}\n", package_source=PKG)
    assert not [line for line in lines if line.startswith("bib entry:")], lines


def test_the_copy_is_its_own_fixed_point_and_passes_the_label_checks_over_a_fuzz():
    import random

    rng = random.Random(20261021)
    failures = []
    for _ in range(1500):
        field = rng.choice(["author", "editor", "key", "title", "organization", "year"])
        kind = rng.choice(["manual", "proceedings", "misc", "book", "article"])
        key = rng.choice(["K1", "a_b1", "Ab" + E_ACUTE + "1", "Doe2020"])
        value = "".join(rng.choice(_VOCABULARY) for _ in range(rng.randint(1, 12)))
        bib = "@" + kind + "{" + key + ", " + field + " = {" + value + "}, title = {T}}\n"
        once = paper_bib(bib)
        lines = [line for line in bib_latex_safety_problems(once, package_source=PKG)
                 if line.startswith(("bib label:", "bib case:", "bib entry:"))]
        if paper_bib(once) != once or lines:
            failures.append((bib, lines[:1]))
    assert failures == [], failures[:3]

def test_the_author_bib_checks_never_fail_the_copy_itself():
    shapes = (list(_PAREN_NAMES.values()) + list(_ORGS.values()) + _NOT_PRINTED + _NOT_KEPT
              + _FONT_SCRIPTS + list(_CASE_CHANGED.values())
              + ["a " + BS + "~" + a + " z" for a in _ACCENT_ARGS.values()])
    bib = "".join(_label_entry("author", s, f"S{k}") + _entry(s, f"T{k}")
                  + _org_entry("manual", s, f"M{k}") for k, s in enumerate(shapes))
    bib += "@misc{a_b2020, title = {T}}\n@misc{L1, key = {" + _LONG_KEY + "}, title = {T}}\n"
    copy = paper_bib(bib)
    lines = bib_latex_safety_problems(copy, package_source=PKG)
    assert not [line for line in lines if "label" in line or "case" in line
                or "'('" in line], lines[:5]
