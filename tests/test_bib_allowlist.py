"""
The bibliography render ships is a canonical copy holding only allow-listed commands.

Independent checkers showed that the deny-list over the bib copy (``DANGEROUS_COMMANDS``) could
not be closed:

  1. a command split across BibTeX ``#`` parts or ``@string`` macros is never seen by a scan of
     the parts, but BibTeX joins it (``{see \\}`` ``#`` ``{input{marker}}``);
  2. BibTeX's ``change.case$`` lowercases title text at brace level 0, so ``\\INPUT{marker}``
     in a title (through a ``@string`` or in a parenthesised entry) becomes ``\\input`` in the
     ``.bbl``;
  3. expl3 (``\\ExplSyntaxOn \\file_input:n``), ``\\expandableinput``, PDF actions
     (``\\pdfstartlink``), hyperref form fields (``\\PushButton``) and ``\\typein`` were not
     listed;
  4. the control symbols ``\\( \\) \\[ \\]`` broke the compile with no signal;
  5. commands on the old safe list are undefined in a figure-less preamble (``\\mathbb``,
     ``\\text``, ``\\operatorname`` ...), so pdflatex stopped while verify was silent;
  6. a name holding ``[`` or ``]`` broke natbib's author-year label;
  7. the copy's own regex reader diverged from BibTeX after a syntax error.

Now render writes every entry BibTeX reads as ``@type{key, field = {value}, ...}`` (macros
expanded, ``#`` parts joined, no ``@string``/``@preamble``/``@comment``), every command in a value
on an allow-list that a test compiles under the preambles render emits, and anything else printed
as text. verify fails a shipped bibliography that is not in that form.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from sci_adk.render import bib_latex
from sci_adk.render.bib_latex import canonical_bib, paper_bib
from tests.test_bib_latex_copy import _compile_with_bib, needs_tex
from tests.test_latex_sanitize_round4 import _marker_file, _read_marker

BS = chr(92)  # a backslash, spelled out so no escape in this file is ambiguous
_INPUT = BS + "input{marker}"


def _entry(title: str, key: str = "K1", extra: str = "") -> str:
    return "@article{" + key + ", title = {" + title + "}, year = {2020}" + extra + "}\n"


# -- 1-3. the bypasses the deny-list could not close ----------------------------------------------

_BYPASSES = {
    "hash-split": "@article{K1, title = {see " + BS + "} # {input{marker}}, year = {2020}}\n",
    "string-split": ('@string{a = "' + BS + 'in"}\n'
                     '@article{K1, title = {T}, note = a # "put{marker}", year = {2020}}\n'),
    "upper-case-through-a-string": ('@string{t = "' + BS + 'INPUT{marker}"}\n'
                                    "@article{K1, title = t, year = {2020}}\n"),
    "upper-case-in-a-parenthesised-entry": ("@article(K1, title = {" + BS + "INPUT{marker}},"
                                            " year = {2020})\n"),
    "expl3-file-input": _entry(BS + "ExplSyntaxOn " + BS + "file_input:n{marker} "
                               + BS + "ExplSyntaxOff"),
    "expl3-file-write": _entry(BS + "ExplSyntaxOn " + BS + "iow_open:Nn " + BS
                               + "g_tmpa_iow {marker2.tex} " + BS + "ExplSyntaxOff"),
    "expandableinput": _entry(BS + "expandableinput{marker}"),
    "pdf-launch": _entry(BS + "pdfstartlink user{/Subtype/Link/A<</S/Launch/F(calc.exe)>>}x"
                         + BS + "pdfendlink"),
    "push-button": _entry(BS + "PushButton[onclick={app.launchURL(1)}]{x}"),
    "typein": _entry(BS + "typein{x}"),
    "csname": _entry(BS + "csname @@input" + BS + "endcsname marker" + BS + "relax"),
    "string-named-like-a-field": ('@string{abstract = "' + _INPUT + '"}\n'
                                  "@article{K1, title = abstract, year = {2020}}\n"),
    "preamble": '@preamble{"' + _INPUT + '"}\n' + _entry("Plain"),
    "comment-hides-preamble": '@comment{ @preamble{"' + _INPUT + '"} }\n' + _entry("Plain"),
}


def _live(text: str) -> str:
    """``text`` without the commands the copy printed as text (``{\\textbackslash}name``)."""
    return text.replace("{" + BS + "textbackslash}", "")


@pytest.mark.parametrize("bib", list(_BYPASSES.values()), ids=list(_BYPASSES))
def test_the_copy_of_each_bypass_holds_no_live_file_command(bib):
    copy = paper_bib(bib)
    for name in ("input", "INPUT", "file", "iow", "expandableinput", "pdfstartlink",
                 "pdfendlink", "PushButton", "typein", "csname", "ExplSyntaxOn"):
        assert BS + name not in _live(copy), (name, copy)
    assert "@string" not in copy.lower() and "@preamble" not in copy.lower()
    assert "@comment" not in copy.lower()


@pytest.mark.parametrize("bib", list(_BYPASSES.values()), ids=list(_BYPASSES))
def test_verify_fails_each_bypass_left_in_a_shipped_bibliography(bib):
    from sci_adk.render.pkgreqs_checks import bib_command_problems, bib_form_problems

    assert bib_form_problems(bib) and bib_command_problems(bib), bib


def test_verify_names_the_command_a_split_value_joins_into():
    # The deny-list scanned the two parts as written and saw no \input; BibTeX joins them.
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    lines = bib_command_problems(_BYPASSES["hash-split"])
    assert any("'K1'" in line and BS + "input" in line for line in lines), lines


@needs_tex
@pytest.mark.parametrize("case", list(_BYPASSES))
def test_the_copy_of_each_bypass_compiles_and_reads_no_file(tmp_path, case):
    _marker_file(tmp_path)
    errors, bbl, dropped = _compile_with_bib(tmp_path, paper_bib(_BYPASSES[case]), False)
    assert not _read_marker(tmp_path, "t"), bbl
    assert not (tmp_path / "marker2.tex").exists()
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


@needs_tex
def test_the_case_change_route_did_read_the_file_before(tmp_path):
    # Why: what BibTeX makes of \INPUT in a title, without the copy (measured with bibtex).
    _marker_file(tmp_path)
    errors, bbl, _dropped = _compile_with_bib(tmp_path, _BYPASSES["upper-case-through-a-string"])
    assert BS + "input{marker}" in bbl and (_read_marker(tmp_path, "t") or errors)


# -- 4-5. control symbols and commands the preamble does not define -------------------------------

def _value(bib: str, field: str = "title") -> str:
    m = re.search(r"^  " + field + r" = \{(.*)\},?$", bib, re.M)
    assert m is not None, bib
    return m.group(1)


def test_balanced_math_delimiters_become_dollar_math():
    copy = paper_bib(_entry("a " + BS + "(x^2" + BS + ") and " + BS + "[y" + BS + "]"))
    # a script argument is always braced (tests/test_bib_round6.py)
    assert "{$x^{2}$}" in copy and "{$y$}" in copy and BS + "(" not in copy


@pytest.mark.parametrize("title", ["a " + BS + "( b", "a " + BS + ") b", "a " + BS + "[ b",
                                   "a " + BS + "] b"])
def test_an_unbalanced_math_delimiter_is_printed_as_text(title):
    copy = paper_bib(_entry(title))
    assert "{" + BS + "textbackslash}" in _value(copy)


_UNDEFINED = [BS + "mathbb{R}", "$" + BS + "mathbb{R}$", BS + "text{x}", "$" + BS + "text{x}$",
              "$" + BS + "operatorname{d}$", "$" + BS + "dfrac{1}{2}$",
              "$" + BS + "boldsymbol{x}$", "$a " + BS + "leqslant b$", "$" + BS + "varnothing$",
              BS + "doi{10.1000/x}", "$" + BS + "omicron$", BS + "up{x}", BS + "hbox to 9pt{x}",
              BS + "hspace{20000pt}", BS + "MakeUppercase{x}", BS + "bibitem{zzz} x"]


@pytest.mark.parametrize("title", _UNDEFINED)
def test_a_command_off_the_allow_list_is_printed_as_text(title):
    name = re.search(r"\\([A-Za-z]+)", title).group(1)
    value = _value(paper_bib(_entry(title)))
    # In a title a printed name with a capital is braced too (its case is protected).
    assert re.search(r"\{\\textbackslash\}\{?" + name, value), value
    assert BS + name not in _live(value), value


@needs_tex
def test_the_copy_of_commands_off_the_allow_list_compiles_without_amsmath(tmp_path):
    bib = "".join(_entry(t, f"K{k}") for k, t in enumerate(_UNDEFINED))
    bib += _entry("a " + BS + "( b", "KA") + _entry("x " + BS + "] y", "KB")
    errors, _bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), False)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


def test_a_math_command_in_running_text_is_put_in_math():
    copy = paper_bib(_entry("Decay of " + BS + "alpha particles and " + BS + "frac{1}{2}"))
    assert "{$" + BS + "alpha$}" in copy and "{$" + BS + "frac{1}{2}$}" in copy


def test_a_text_command_in_math_is_boxed():
    copy = paper_bib(_entry("$" + BS + "'e + " + BS + "textit{x} + " + BS + "ss$"))
    value = _value(copy)
    assert BS + "mbox{" + BS + "'{e}}" in value and BS + "mbox{" + BS + "textit{x}}" in value
    assert BS + "mbox{" + BS + "ss}" in value


def test_caret_notation_never_survives():
    copy = paper_bib(_entry("$x^^5cinput$ and a^^b and $y^^$"))
    assert "^^" not in copy


def test_kept_commands_are_braced_so_bibtex_cannot_change_their_case():
    copy = paper_bib(_entry(BS + "'e and " + BS + "textit{Escherichia} and " + BS + "AE"))
    value = _value(copy)
    assert "{" + BS + "'{e}}" in value
    assert "{{" + BS + "textit{Escherichia}}}" in value  # capital: braced once more
    assert "{{" + BS + "AE}}" in value


def test_a_font_declaration_is_scoped_to_its_group():
    copy = paper_bib(_entry("A {" + BS + "em Escherichia coli} study and " + BS + "bf rest"))
    value = _value(copy)
    assert "{" + BS + "em Escherichia coli}" in value or "{{" + BS + "em Escherichia coli}}" in value
    assert BS + "bf rest}" in value


# -- 6. names holding brackets --------------------------------------------------------------------

def test_brackets_in_a_name_are_braced():
    copy = paper_bib("@misc{K1, author = {[Anonymous]}, title = {T}, year = {2020}}\n")
    assert _value(copy, "author") == "{[}Anonymous{]}"


@needs_tex
def test_a_bracketed_name_compiles_with_natbib(tmp_path):
    bib = "@misc{K1, author = {[Anonymous]}, title = {T}, year = {2020}}\n"
    errors, bbl, dropped = _compile_with_bib(tmp_path, paper_bib(bib), False)
    assert errors == [], f"{errors[:5]} (dropped {dropped})"


# -- 7. the reader BibTeX uses, and the canonical form ---------------------------------------------

_RESUME = {
    "value-token-holding-an-at": ("@article{a, title = {A}, year = {2001}, note = x@article{e1,"
                                  " title = {E}, year = {2002}}\n@article{b, title = {B}, year ="
                                  " {2003}}\n"),
    "number-then-at": ("@article{a, title = {A}, year = 2001@article{e4, title = {E}, year ="
                       " {2002}}\n@article{b, title = {B}, year = {2003}}\n"),
    "key-then-junk": ("@article{a x@article{e7, title = {E}, year = {2002}}\n"
                      "@article{b, title = {B}, year = {2003}}\n"),
    "type-holding-an-at": "@x@article{e8, title = {E}, year = {2002}}\n",
    "string-value-holding-an-at": ("@string{foo = x@article{e3, title = {E}, year = {2002}}\n"
                                   "@article{b, title = {B}, year = {2003}}\n"),
}


@needs_tex
@pytest.mark.parametrize("case", list(_RESUME))
def test_the_copy_keeps_the_entries_bibtex_reads_after_a_syntax_error(tmp_path, case):
    from sci_adk.render.pkgreqs_checks import bib_keys

    bib = _RESUME[case]
    (tmp_path / "r.bib").write_text(bib, encoding="utf-8")
    (tmp_path / "r.aux").write_text(
        BS + "relax\n" + BS + "citation{*}\n" + BS + "bibstyle{plainnat}\n" + BS + "bibdata{r}\n",
        encoding="utf-8")
    subprocess.run(["bibtex", "-terse", "r"], cwd=tmp_path, capture_output=True, check=False)
    bbl = (tmp_path / "r.bbl").read_text(encoding="utf-8", errors="replace")
    read = sorted(re.findall(r"\\bibitem\[[^\n]*?\]\{([^}]*)\}", bbl, re.S))
    assert sorted(bib_keys(paper_bib(bib))) == read


def test_the_copy_is_one_braced_value_per_field_and_entries_only():
    bib = ('% a comment line\n@string{jpc = "J. Phys. Chem."}\n'
           '@ARTICLE ( A2020 ,\n  Title = "Alpha " # {Beta},\n  journal = jpc,\n'
           "  year = 2020, month = jan, pages = {1--2}, abstract = {x}, issn = {1234-5678})\n"
           "junk between\n@book{B2021, title = {Gamma}, year = {2021},}\n")
    assert paper_bib(bib) == (
        "@article{A2020,\n  title = {Alpha {Beta}},\n  journal = {J. Phys. Chem.},\n"
        "  year = {2020},\n  month = jan,\n  pages = {1--2}\n}\n\n"
        "@book{B2021,\n  title = {Gamma},\n  year = {2021}\n}\n"
    )


def test_the_copy_is_idempotent_and_keys_never_change():
    from sci_adk.render.pkgreqs_checks import bib_keys

    bib = "".join(_BYPASSES.values()) + "".join(_entry(t, f"U{k}") for k, t in enumerate(_UNDEFINED))
    copy = paper_bib(bib)
    assert paper_bib(copy) == copy
    assert set(bib_keys(copy)) <= set(bib_keys(bib))


def test_a_repeated_key_or_field_keeps_the_first_as_bibtex_does():
    bib = ("@article{K1, title = {First}, title = {Second}, year = {2020}}\n"
           "@article{k1, title = {Again}, year = {2021}}\n")
    result = canonical_bib(bib)
    assert "First" in result.text and "Second" not in result.text and "Again" not in result.text
    assert any("'k1'" in note for note in result.notes)


def test_a_key_that_is_not_plain_ascii_is_left_out_with_a_note():
    bib = "@article(" + BS + "input{x}, title = {T})\n" + _entry("Kept", "K2")
    result = canonical_bib(bib)
    assert "Kept" in result.text and "input" not in result.text
    assert any("left out" in note for note in result.notes)


@pytest.mark.parametrize(
    "field, value",
    [("url", "https://example.org/a%20b"), ("url", "https://example.org/a#frag"),
     ("url", "file:///etc/passwd"), ("url", "http://a.org/" + BS + "x"), ("url", "http://a b"),
     ("doi", "10.1/x"), ("doi", "10.1000/a%2Fb"), ("doi", "10.1000/x" + BS + "relax")],
)
def test_a_url_or_doi_that_fails_the_strict_check_is_dropped_with_a_note(field, value):
    result = canonical_bib("@misc{K1, title = {T}, " + field + " = {" + value + "}, year = {2020}}\n")
    assert field + " =" not in result.text
    assert any("'K1'" in note and field in note for note in result.notes), result.notes


@pytest.mark.parametrize(
    "field, value, written",
    [("url", "https://example.org/a_b?c=1&d=2~e", "https://example.org/a_b?c=1&d=2~e"),
     ("url", "ftp://ftp.example.org/x", "ftp://ftp.example.org/x"),
     ("doi", "10.1002/(SICI)1097-4636(199601)30:1<1::AID-JBM1>3.0.CO;2-6",
      "10.1002/(SICI)1097-4636(199601)30:1<1::AID-JBM1>3.0.CO;2-6"),
     ("doi", "https://doi.org/10.1000/xyz", "10.1000/xyz")],
)
def test_a_plain_url_or_doi_is_kept_as_written(field, value, written):
    copy = paper_bib("@misc{K1, title = {T}, " + field + " = {" + value + "}, year = {2020}}\n")
    assert "  " + field + " = {" + written + "}" in copy


def test_braces_nested_hundreds_deep_give_an_empty_value_and_a_note():
    from sci_adk.render.pkgreqs_checks import bib_command_problems

    bib = _entry("{" * 2000 + "x" + "}" * 2000)
    result = canonical_bib(bib)
    assert "  title = {}" in result.text and any("nested" in n for n in result.notes)
    assert any("nested" in line for line in bib_command_problems(bib))


def test_a_month_macro_stays_a_macro_and_an_undefined_month_name_becomes_one():
    copy = paper_bib("@misc{K1, title = {T}, month = Sept, year = {2020}}\n"
                     "@misc{K2, title = {T}, month = feb, year = {2020}}\n")
    assert "month = sep" in copy and "month = feb" in copy


# -- the allow-list compiles under every preamble render emits --------------------------------------

_TEXT_SYMBOL_SAMPLES = [BS + c + "{e}" for c in "'`^\"~=."] + [
    BS + c for c in "&%$#_{},-"] + ["a" + BS + " b"]
_MATH_SYMBOL_SAMPLES = ["$a" + BS + c + "b$" for c in ",;:!|{}&%$#_ "]


def _samples() -> tuple[str, str]:
    """A title using every allow-listed text command, and one using every math command."""
    text, math = list(_TEXT_SYMBOL_SAMPLES), list(_MATH_SYMBOL_SAMPLES)
    for name, kind in sorted(bib_latex.TEXT_COMMANDS.items()):
        call = BS + name
        sample = {
            "zero": call + "{}", "accent": call + "{e}", "one": call + "{ab}",
            "declaration": "{" + call + " ab}", "url": call + "{https://example.org/a}",
            "href": call + "{https://example.org/}{x}", "math": call + "{x}",
        }[kind]
        text.append(sample)
    for name, kind in sorted(bib_latex.MATH_COMMANDS.items()):
        call = BS + name
        sample = {
            "zero": call + " x", "one": call + "{x}", "two": call + "{1}{2}",
            "declaration": "{" + call + " x}", "text": call + "{e}", "math": call + "{x}",
        }[kind]
        math.append("$a " + sample + "$")
    return " ".join(text), " ".join(math)


def test_every_allow_listed_command_survives_the_copy():
    text, math = _samples()
    copy = paper_bib(_entry(text, "T1") + _entry(math, "M1"))
    printed = re.findall(r"\{\\textbackslash\}[A-Za-z]+", copy)
    assert printed == [], printed


def test_every_command_the_copy_writes_is_on_the_allow_list():
    from sci_adk.render.paper import _UNICODE_MAP

    names = set()
    for latex in _UNICODE_MAP.values():
        names |= set(re.findall(r"\\([A-Za-z]+)", latex))
    allowed = set(bib_latex.TEXT_COMMANDS) | set(bib_latex.MATH_COMMANDS)
    assert names <= allowed, names - allowed


_RENDER_PREAMBLES = [
    ("paper-latin-modern", False, "paper"), ("paper-times", True, "paper"),
    ("record-latin-modern", False, "record"), ("record-times", True, "record"),
]


def _preamble(figure_bearing: bool, which: str) -> list[str]:
    from sci_adk.render.figures import ImageFigureSpec
    from sci_adk.render.paper import render_paper_latex
    from sci_adk.render.si import render_si_latex
    from tests.test_si import _basic_record

    spec, claims, evidence = _basic_record()
    figures = ([ImageFigureSpec(kind="image", id="fig-a", caption="A caption.", image="a.png")]
               if figure_bearing else [])
    if which == "paper":
        tex = render_paper_latex(spec, claims, evidence, figures=figures)
    else:
        tex = render_si_latex(spec, claims, evidence, figures=figures)
    return [line for line in tex[: tex.index(BS + "begin{document}")].splitlines()
            if "pgfplots" not in line]


@needs_tex
@pytest.mark.parametrize("name, figure_bearing, which", _RENDER_PREAMBLES,
                         ids=[p[0] for p in _RENDER_PREAMBLES])
def test_every_allow_listed_command_compiles_under_the_preambles_render_emits(
    tmp_path, name, figure_bearing, which
):
    text, math = _samples()
    copy = paper_bib(_entry(text, "T1") + _entry(math, "M1"))
    (tmp_path / "references.bib").write_text(copy, encoding="utf-8")
    body = [BS + "begin{document}", BS + "nocite{*}", BS + "bibliographystyle{plainnat}",
            BS + "bibliography{references}", BS + "end{document}"]
    (tmp_path / "t.tex").write_text("\n".join(_preamble(figure_bearing, which) + body) + "\n",
                                    encoding="utf-8")
    for cmd in (["pdflatex", "-interaction=nonstopmode", "t.tex"], ["bibtex", "t"],
                ["pdflatex", "-interaction=nonstopmode", "t.tex"]):
        subprocess.run(cmd, cwd=tmp_path, capture_output=True, check=False)
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace")
    errors = [line for line in log.splitlines() if line.startswith("!")]
    errors += re.findall(r"Missing character: There is no .*", log)
    assert errors == [], errors[:5]


# -- verify ---------------------------------------------------------------------------------------

def _rendered_run(tmp_path, spec_id):
    from tests.test_latex_sanitize_round3 import _rendered_run as rendered

    return rendered(tmp_path, spec_id)


def test_verify_passes_the_bibliographies_render_wrote(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "canon-ok")
    report = verify_run(run_dir)
    assert not [p for p in report.paper_requirements_problems if "bib" in p.lower()], (
        report.paper_requirements_problems)


def test_verify_fails_a_hand_edited_bibliography_naming_the_entry(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "canon-edit")
    bib = run_dir / "paper" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8").replace("{Alpha}", "{Alpha  beta}"),
                   encoding="utf-8")
    report = verify_run(run_dir)
    lines = [p for p in report.paper_requirements_problems if "references.bib" in p]
    assert any("'A2020'" in line and "title" in line for line in lines), lines
    assert not report.passed


def test_verify_fails_a_command_off_the_allow_list_in_the_si_bibliography(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "canon-si")
    bib = run_dir / "paper" / "references_SI.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + _entry(BS + "hspace{9pt}x", "Z2020"),
                   encoding="utf-8")
    report = verify_run(run_dir)
    assert any("references_SI.bib" in p and "'Z2020'" in p and BS + "hspace" in p
               for p in report.paper_requirements_problems), report.paper_requirements_problems


def test_verify_no_longer_advises_on_unknown_bib_commands(tmp_path):
    from sci_adk.loop.verify import verify_run

    run_dir = _rendered_run(tmp_path, "canon-noadv")
    report = verify_run(run_dir)
    assert not [n for n in report.paper_advisory if n.startswith("bib commands:")]


def test_a_package_author_bib_gets_the_allow_list_check():
    from sci_adk.render.pkgreqs_checks import bib_latex_safety_problems

    clean = "@string{j = {J}}\n@article(K1, title = {A " + BS + "'e " + BS + "textit{x}}, journal = j)\n"
    assert bib_latex_safety_problems(clean, package_source="package_src/references.bib") == []
    dirty = _entry(BS + "MakeUppercase{x}")
    lines = bib_latex_safety_problems(dirty, package_source="package_src/references.bib")
    assert any("'K1'" in line and BS + "MakeUppercase" in line
               and "package_src/references.bib" in line for line in lines), lines


def test_render_notes_what_the_copy_dropped_or_printed_as_text(tmp_path, capsys):
    from sci_adk.cli import main
    from tests.test_render_record_only import _seed

    run_dir = _seed(tmp_path, "canon-notes")
    (run_dir / "literature").mkdir(parents=True, exist_ok=True)
    (run_dir / "literature" / "references.bib").write_text(
        _entry(BS + "hspace{9pt}", "Q2020", ", url = {https://a.org/%20}"), encoding="utf-8")
    capsys.readouterr()
    assert main(["render", str(run_dir)]) == 0
    err = capsys.readouterr().err
    assert any("'Q2020'" in line and BS + "hspace" in line for line in err.splitlines()), err
    assert any("'Q2020'" in line and "url" in line for line in err.splitlines()), err
