"""
The reference list a rendered paper prints: the ``paper/`` bibliography copy beyond LaTeX safety.

Render writes ``paper/references.bib`` (and the cited-only ``paper/references_SI.bib``) as
``bib_latex.paper_bib(store)``: the LaTeX-safe copy (``latex_safe_bib``, see
tests/test_bib_latex_copy.py) with four changes to what plainnat prints. The trial run's compiled
reference list (lit-search-trial-2, SPEC-BCFKOW-001) showed each problem:

1. plainnat lowercases a title (``change.case$`` "t": every letter at brace level 0 but the
   first): "(bcf)", "(baf)", "matula numbers", "Opera models", "Molecular connectivity iii",
   "log kow". The copy keeps the casing the source gives by bracing, in ``title`` and
   ``booktitle``, every word that carries an uppercase letter other than the field's first
   character (so "BCF", "OPERA", "III", "Matula" and "Kow" of "log Kow" print as acquired),
   every ``$...$`` holding an uppercase letter, and every ``{\\...}`` letter group holding
   one (BibTeX would lowercase inside it). An accent command with its unbraced capital
   (``\\"Osterreich``) and a control word with a capital in its name (``\\LaTeX``) are braced
   twice the same way. Already-braced text, other command names and the word a macro takes as
   its argument are left alone.
2. Every entry printed an ISSN and a ``dx.doi.org`` URL beside its DOI. ``issn`` is omitted,
   and so is a ``url`` that is the doi.org / dx.doi.org link of the entry's own DOI (DOIs
   compare case-insensitively); any other url, and every doi, stays.
3. "Donald. Mackay.": the store's ``author={Mackay, Donald.}`` carries a stray period after a
   full given name. A given-name token that is a capitalised word of three or more letters
   with a vowel loses its period; initials ("D.") keep theirs, and so do the old given-name
   abbreviations ("Chas.", "Thos.", ...).
4. "Šoškić" sorted after every ASCII name: BibTeX sorts raw UTF-8 bytes after "z". In
   ``author`` and ``editor`` a non-ASCII letter becomes LaTeX accent commands (the module's
   accent machinery) or a letter command (``{\\l}``, ``{\\o}``, ``{\\ss}`` ...), which BibTeX's
   purify$ reduces to the base letter: Šoškić sorts as "Soskic". Letters with no command
   outside T1 (Ð Þ Đ Ŋ ...) are kept as they are; verify names a cited entry whose first
   author still sorts after Z that way, as a non-gating advisory.

The store (``literature/references.bib``) is never rewritten and keys never change.
"""

from __future__ import annotations

import re

import pytest

from sci_adk.render.bib_latex import (
    field_value_spans,
    latex_safe_bib,
    paper_bib,
    raw_sort_letter,
)
from sci_adk.render.pkgreqs_checks import bib_keys, bib_latex_safety_problems, bib_sort_advisories
from tests.test_bib_latex_copy import _TRIAL_BIB, _compile_with_bib, needs_tex

_STORE = _TRIAL_BIB.read_text(encoding="utf-8")


def _store_entry(key: str) -> str:
    """The trial store's entry ``key`` (one entry per line in the store)."""
    return next(line for line in _STORE.splitlines() if line.startswith("@") and f"{{{key}," in line)


def _fields(entry: str) -> dict[str, str]:
    return {name: entry[start:end] for name, start, end in field_value_spans(entry)}


def _paper_fields(key: str) -> dict[str, str]:
    return _fields(paper_bib(_store_entry(key)))


def _title(raw: str) -> str:
    return _fields(paper_bib(f"@article{{X2020, title={{{raw}}}, year={{2020}}}}"))["title"]


def _author(raw: str) -> str:
    return _fields(paper_bib(f"@article{{X2020, author={{{raw}}}, title={{t}}, year={{2020}}}}"))[
        "author"
    ]


# -- 1. the casing the source gives ----------------------------------------------------------------


@pytest.mark.parametrize(
    "key, expected",
    [
        (
            "Arnot2006",
            "A review of bioconcentration factor ({BCF}) and bioaccumulation factor ({BAF}) "
            "assessments for organic chemicals in aquatic organisms",
        ),
        (
            "Mansouri2018",
            "{OPERA} models for predicting physicochemical properties and environmental fate "
            "endpoints",
        ),
        ("Murray1975", "Molecular {Connectivity} {III}: {Relationship} to {Partition} {Coefficients}"),
        ("Elk1995", "Expansion of {Matula} {Numbers} to {Heteroatoms} and to {Ring} {Compounds}"),
        ("Devillers1996", "Comparison of {BCF} models based on log {P}"),
        (
            "Gimeno2024",
            "Are current regulatory log {Kow} cut-off values fit-for-purpose as a screening tool "
            "for bioaccumulation potential in aquatic organisms?",
        ),
        # The field's first letter is printed as it is: "Matula" needs no braces there.
        ("Neto2013", "Matula numbers, {Gödel} numbering and {Fock} space"),
        # Markup arguments are brace groups already.
        (
            "Bertelsen1998",
            "Evaluation of log \\textit{K}\\textsubscript{OW} and tissue lipid content as "
            "predictors of chemical partitioning to fish tissues",
        ),
        # A command name is never braced; the words after its argument are.
        (
            "Bintein1993",
            "Nonlinear {Dependence} of {Fish} {Bioconcentration} on \\textit{n}-{Octanol}/{Water} "
            "{Partition} {Coefficient}",
        ),
        # The minus the LaTeX-safe copy wrote is already a protected group.
        (
            "oki2005",
            "Modeling the {Octanol}{$-$}{Water} {Partition} {Coefficients} by an {Optimized} "
            "{Molecular} {Connectivity} {Index}",
        ),
        ("Weininger1989", "{SMILES}. 2. {Algorithm} for generation of unique {SMILES} notation"),
    ],
)
def test_title_case_given_by_the_source_is_protected(key, expected):
    assert _paper_fields(key)["title"] == expected


def test_booktitle_case_is_protected_too():
    assert _paper_fields("Arman2012")["booktitle"] == "Can\u2019t {Sleep}? {Issues} of {Being} an {Insomniac}"
    assert _paper_fields("AVDossouOlory2025")["booktitle"] == (
        "Number {Theory} - {Classical} {Foundations} and {Modern} {Perspectives}"
    )


def test_journal_is_not_braced():
    # No natbib style changes the case of a journal name.
    assert _paper_fields("Arnot2006")["journal"] == "Environmental Reviews"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("the $K_{OW}$ of x", "the {$K_{OW}$} of x"),  # BibTeX would lowercase K inside $...$
        ("a $x \\geq 3$ bound", "a $x \\geq 3$ bound"),  # nothing to lowercase
        ("of $$\\Delta G$$", "of {$$\\Delta G$$}"),
        ("{DNA} and {Matula Numbers}", "{DNA} and {Matula Numbers}"),  # already braced
        ("on {\\textcommabelow{S}}tefan", "on {{\\textcommabelow{S}}}tefan"),  # a letter group
        ("on {\\'e}t{\\'e}", "on {\\'e}t{\\'e}"),  # lowercase letter groups need nothing
        # An accent with its unbraced capital is braced twice (section 1b below).
        ("an \\'Etude of X", "an {{\\'E}}tude of {X}"),
        ("Science \\& Technology Review", "Science \\& {Technology} {Review}"),
        ("see \\url{http://X.org/A} Now", "see \\url{http://X.org/A} {Now}"),
        ("3D-QSAR of CO2", "{3D}-{QSAR} of {CO2}"),
        # A brace group that opens with a command is a BibTeX "special character": its
        # letters are lowercased like any other, so it is braced once more.
        ("so-called {\\em Matula} trees", "so-called {{\\em Matula}} trees"),
    ],
)
def test_case_protection_leaves_math_groups_and_commands_intact(raw, expected):
    out = _title(raw)
    assert out == expected
    assert bib_latex_safety_problems(f"@article{{X2020, title={{{out}}}, year={{2020}}}}") == []


def test_a_quoted_or_concatenated_title_is_protected_part_by_part():
    out = paper_bib('@article{X2020, title = "OPERA and" # { BCF}, year=2020}')
    assert 'title = "{OPERA} and" # { {BCF}}' in out


# -- 1b. an accent command or a capitalised control word written without braces ------------------
#
# plainnat's change.case$ "t" works letter by letter at brace level 0, command names and accent
# arguments included: \"Osterreich -> \"osterreich, \'Etude -> \'etude, \LaTeX -> \latex (an
# undefined command: the compile stops), \H O -> \h o. One brace pair does not protect an accent:
# {\"O} is a BibTeX "special character", whose letters BibTeX lowercases ({\"o}), and {\AE} is
# one whose command it lowercases ({\ae}) -- measured with bibtex + plainnat (TeX Live 2026).
# So the command and its letter (or its adjacent brace arguments) are braced twice, as an
# existing {\...} group holding a capital is. The space TeX swallows after a control word stays
# inside the braces, so the typeset text does not change.


@pytest.mark.parametrize(
    "raw, expected",
    [
        (r'Trade in \"Osterreich', r'Trade in {{\"O}}sterreich'),
        (r"une \'Etude", r"une {{\'E}}tude"),
        # BibTeX lowercases it even as the field's first letter (its "first character" is \).
        (r'\"Uber alles', r'{{\"U}}ber alles'),
        (r'zu \" Ubung', r'zu {{\" U}}bung'),  # the accent's argument may follow a space
        (r"the \v Skoda and \c Cedric", r"the {{\v S}}koda and {{\c C}}edric"),
        (r"on \H O and \H o", r"on {{\H O}} and {{\H o}}"),  # \H itself would become \h
        (r"\H{o}szi", r"{{\H{o}}}szi"),
        (r"the \LaTeX\ Workshop", r"the {{\LaTeX}}\ {Workshop}"),
        (r"the \LaTeX Workshop", r"the {{\LaTeX }}{Workshop}"),  # TeX eats that space
        (r"the \LaTeX{} Companion", r"the {{\LaTeX{}}} {Companion}"),
        (r"\AE ther and \O rsted", r"{{\AE }}ther and {{\O }}rsted"),
        # Lowercase: nothing BibTeX can change.
        (r'an \'etude, \"uber, \v skoda', r'an \'etude, \"uber, \v skoda'),
        (r"a \textit{Daphnia} test", r"a \textit{Daphnia} test"),
        # A lowercase accent, then capitals in the same word.
        (r"\'eTUDE", r"\'e{TUDE}"),
        # Already protected: left alone.
        (r'{\"O}sterreich and \"{O}sterreich', r'{{\"O}}sterreich and \"{O}sterreich'),
    ],
)
def test_an_unbraced_accent_or_capitalised_command_is_protected(raw, expected):
    out = _title(raw)
    assert out == expected
    assert bib_latex_safety_problems(f"@article{{X2020, title={{{out}}}, year={{2020}}}}") == []
    assert _title(out) == out  # idempotent


_UNBRACED_COMMANDS_BIB = (
    "@article{Unb2001, author={Doe, Jane}, title={Trade in \\\"Osterreich and \\'Etude on "
    "\\LaTeX\\ Workshop and \\AE ther}, journal={J}, year={2001}}\n"
    "@article{Unb2002, author={Roe, Ann}, title={\\\"Uber \\v Skoda and \\H O and \\LaTeX{} "
    "Companion}, journal={J}, year={2002}}\n"
)


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_unbraced_accents_and_capitalised_commands_print_as_written(tmp_path, figure_bearing):
    # As acquired, BibTeX lowercases \LaTeX to the undefined \latex: the compile fails.
    errors, _bbl, _dropped = _compile_with_bib(tmp_path, _UNBRACED_COMMANDS_BIB, figure_bearing)
    assert any("Undefined control sequence" in e for e in errors), errors
    # The reference-list copy compiles and prints every capital as written.
    errors, bbl, dropped = _compile_with_bib(
        tmp_path, paper_bib(_UNBRACED_COMMANDS_BIB), figure_bearing
    )
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    # BibTeX breaks long lines at spaces (one inside "{{\AE }}" too): compare with each run
    # of white space read as one space, as TeX reads it.
    items = {key: " ".join(text.split()) for key, text in _bibitems(bbl).items()}
    for printed in ('{{\\"O}}sterreich', "{{\\'E}}tude", "{{\\LaTeX}}\\ {Workshop}",
                    "{{\\AE }}ther"):
        assert printed in items["Unb2001"], items["Unb2001"]
    for printed in ('{{\\"U}}ber', "{{\\v S}}koda", "{{\\H O}}", "{{\\LaTeX{}}} {Companion}"):
        assert printed in items["Unb2002"], items["Unb2002"]
    assert "\\latex" not in bbl and "\\ae" not in bbl and "\\h " not in bbl


# -- 2. no ISSN, no URL that repeats the DOI ---------------------------------------------------


def test_issn_and_the_doi_url_are_omitted_and_the_doi_kept():
    fields = _paper_fields("Arnot2006")
    assert "issn" not in fields and "url" not in fields
    assert fields["doi"] == "10.1139/a06-005"
    assert set(fields) == {
        "title", "volume", "doi", "number", "journal", "publisher", "author", "year", "pages",
    }


def test_a_doi_url_matches_its_doi_whatever_the_letter_case():
    # Elk1990: url .../10.1007/BF01170004, DOI={10.1007/bf01170004}.
    fields = _paper_fields("Elk1990")
    assert "url" not in fields and fields["doi"] == "10.1007/bf01170004"


@pytest.mark.parametrize(
    "url, kept",
    [
        ("https://doi.org/10.1/abc", False),
        ("http://dx.doi.org/10.1/ABC", False),
        ("https://doi.org/10.1/a%62c", False),  # percent-encoded
        ("https://doi.org/10.1/other", True),  # another DOI: kept
        ("https://example.org/paper.pdf", True),
    ],
)
def test_only_a_url_that_is_the_entrys_own_doi_link_is_omitted(url, kept):
    bib = f"@article{{X2020, title={{t}}, url={{{url}}}, doi={{10.1/abc}}, year={{2020}}}}"
    assert ("url" in _fields(paper_bib(bib))) == kept


def test_a_url_is_kept_when_the_entry_has_no_doi():
    bib = "@misc{X2020, title={t}, url={https://doi.org/10.1/abc}, issn={1234-5678}}"
    assert _fields(paper_bib(bib)) == {"title": "t", "url": "https://doi.org/10.1/abc"}


def test_removing_fields_keeps_a_multi_line_entry_well_formed():
    bib = (
        "@article{X2020,\n"
        "  issn = {1234-5678},\n"
        "  title = {t},\n"
        "  url = {https://doi.org/10.1/abc},\n"
        "  doi = {10.1/abc},\n"
        "  ISSN = {8765-4321}\n"
        "}\n"
    )
    assert paper_bib(bib) == "@article{X2020,\n  title = {t},\n  doi = {10.1/abc}\n}\n"


# -- 3. a stray period after a full given name ------------------------------------------------


def test_mackays_stray_period_is_dropped():
    assert _paper_fields("Mackay1982")["author"] == "Mackay, Donald"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Bintein, S. and Devillers, J.", "Bintein, S. and Devillers, J."),  # initials keep it
        ("Neely, W. Brock and Blau, Gary E.", "Neely, W. Brock and Blau, Gary E."),
        ("Donald. Mackay", "Donald Mackay"),  # First Last form
        ("Dupont, Jean-Pierre.", "Dupont, Jean-Pierre"),
        ("Darwin, Chas. and Hardy, Thos.", "Darwin, Chas. and Hardy, Thos."),  # abbreviations
        ("Smith, Wm.", "Smith, Wm."),  # two letters: an abbreviation
        ("Smith, John. and Doe, Jane.", "Smith, John and Doe, Jane"),
        ("{World Health Organization.}", "{World Health Organization.}"),  # braced name
        ("Mackay. Jr, Donald", "Mackay. Jr, Donald"),  # only the given name is touched
    ],
)
def test_only_a_full_given_name_loses_a_stray_period(raw, expected):
    assert _author(raw) == expected


# -- 4. non-ASCII letters in names as LaTeX commands -------------------------------------------


@pytest.mark.parametrize(
    "key, expected",
    [
        ("oki2005", "{\\v{S}}o{\\v{s}}ki{\\'{c}}, Milan and Plav{\\v{s}}i{\\'{c}}, Dejan"),
        (
            "Klimoszek2025",
            "Klimoszek, Daria and Do{\\l}owy, Ma{\\l}gorzata and Jele{\\'{n}}, Ma{\\l}gorzata "
            "and Bober-Majnusz, Katarzyna",
        ),
        ("Neto2013", "Neto, Ant{\\^{o}}nio Francisco"),
        ("CarbDorca2009", "Carb{\\'{o}}\u2010Dorca, Ramon and Saliner, Ana Gallegos"),
        ("Gutman1996", "Gutman, Ivan and Ivi{\\'{c}}, Aleksandar"),
    ],
)
def test_non_ascii_letters_in_author_names_become_latex_commands(key, expected):
    assert _paper_fields(key)["author"] == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Børge, Ærø and Strauß, Œdipe", "B{\\o}rge, {\\AE}r{\\o} and Strau{\\ss}, {\\OE}dipe"),
        ("Łukasz, Ąda", "{\\L}ukasz, {\\k{A}}da"),
        # T1-only letters with no OT1 command stay raw (the package T1 gate keeps seeing them).
        ("Þórðarson, Ð.", "Þ{\\'{o}}rðarson, Ð."),
    ],
)
def test_letter_commands_for_letters_without_accents(raw, expected):
    assert _author(raw) == expected


def test_editor_names_are_tidied_like_author_names():
    out = _fields(paper_bib("@book{X2020, editor={Šoškić, Milan.}, title={t}, year={2020}}"))
    assert out["editor"] == "{\\v{S}}o{\\v{s}}ki{\\'{c}}, Milan"


def test_titles_keep_their_letters_as_they_are():
    # Only names are rewritten for sorting; a title's Randić stays a UTF-8 letter.
    assert "{Randić}" in _paper_fields("Arman2012")["title"]


# -- 4b. a first author BibTeX still sorts after Z: a verify advisory ----------------------------
#
# Ð Þ Đ Ŋ have only T1 commands, which purify$ drops whole (so {\DJ}uro would sort as "uro"):
# the copy keeps them raw, and BibTeX sorts a raw UTF-8 letter after every ASCII one, so
# Đorđević prints after Zhang. (Ħ Ŧ fail the LaTeX-safety check before any compile; Ŀ is
# written L·.) Verify names each cited entry whose first author is sorted by a raw non-ASCII
# letter, as a non-gating advisory. BibTeX's sort key starts with the first author's von part,
# else the last name ("Last, First" or "First von Last").


@pytest.mark.parametrize(
    "names, letter",
    [
        ("Đorđević, Ana", "Đ"),
        ("Ana Đorđević", "Đ"),
        ("Þ{\\'{o}}rðarson, Ð.", "Þ"),
        ("{Đ}uro, Ana", "Đ"),  # purify$ drops the braces
        ("{Đông Á Bank}", "Đ"),
        ("Ħal, A. and Doe, J.", "Ħ"),
        ("Ŀlop, Ana", "Ŀ"),
        ("Ølsen, K.", "Ø"),  # raw in a bib nobody rewrote (an author's package bib)
        ("Doe, Jane and Đuro, Ana", None),  # only the first author decides
        ("de Ðuro, Ana", None),  # sorted by its von part, "de"
        ("Ðuro de Vries", None),  # First von Last: sorted by "de Vries"
        ("Ana Doe", None),
        ("{\\v{S}}o{\\v{s}}ki{\\'{c}}, Milan", None),  # purify$ leaves the S
        ("{\\DJ}uro, Ana", None),
        ("", None),
    ],
)
def test_the_raw_letter_a_first_author_is_sorted_by(names, letter):
    assert raw_sort_letter(names) == letter


_SORT_BIB = (
    "@article{Dordevic2020, author={Đorđević, Ana}, title={A}, journal={J}, year={2020}, "
    "doi={10.1/a}}\n"
    "@article{Zhang2021, author={Zhang, Wei and Đuro, Bo}, title={B}, journal={J}, year={2021}, "
    "doi={10.1/b}}\n"
    "@article{Hal2019, author={Ħal, Bo}, title={C}, journal={J}, year={2019}, doi={10.1/c}}\n"
    "@book{Ed2018, editor={Þorsteinsson, Ari}, title={D}, publisher={P}, year={2018}}\n"
)


def test_the_sort_advisory_names_each_cited_entry_sorted_after_z():
    lines = bib_sort_advisories(r"\citep{Dordevic2020,Zhang2021} and \citet{Ed2018}", _SORT_BIB)
    assert len(lines) == 2, lines  # Hal2019 is not cited; Zhang2021's first author is ASCII
    dordevic = next(line for line in lines if "Dordevic2020" in line)
    assert "references.bib" in dordevic and "Đ" in dordevic and "after" in dordevic
    assert any("Ed2018" in line and "Þ" in line for line in lines)  # the editor, no author


def test_the_sort_advisory_names_the_command_for_a_letter_that_has_one():
    # An author bib the package copies unchanged keeps Ø raw; {\O} sorts under O.
    lines = bib_sort_advisories(
        r"\cite{Olsen2001}",
        "@article{Olsen2001, author={Ølsen, Kari}, title={T}, journal={J}, year={2001}}\n",
        source="references.bib",
        package_source="package_src/references.bib",
    )
    assert len(lines) == 1, lines
    assert "{\\O}" in lines[0] and "package_src/references.bib" in lines[0]


@needs_tex
def test_a_raw_first_letter_does_sort_after_z(tmp_path):
    # The premise of the advisory, measured: plainnat lists Đorđević after Zhang.
    bib = paper_bib(
        "@article{Dordevic2020, author={Đorđević, Ana}, title={A}, journal={J}, year={2020}}\n"
        "@article{Zhang2021, author={Zhang, Wei}, title={B}, journal={J}, year={2021}}\n"
        "@article{Abel2019, author={Abel, Bo}, title={C}, journal={J}, year={2019}}\n"
    )
    errors, bbl, dropped = _compile_with_bib(tmp_path, bib, figure_bearing=False)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    assert list(_bibitems(bbl)) == ["Abel2019", "Zhang2021", "Dordevic2020"]
    assert len(bib_sort_advisories(r"\nocite{x}\cite{Dordevic2020}", bib)) == 1


def test_per_run_verify_carries_the_sort_advisory(tmp_path):
    from sci_adk.loop.verify import verify_run
    from tests.test_paper_gate_enforcement import _draft, _freeze_pubreqs, _write_run

    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    _draft(run_dir, r"\section{Results}As shown \citep{Dordevic2020}, the value is 0.61.")
    bib = (
        "@article{Dordevic2020, author={Đorđević, Ana}, title={A}, journal={J}, year={2020}, "
        "doi={10.1/a}}\n"
        "@article{Zhang2021, author={Zhang, Wei}, title={B}, journal={J}, year={2021}, "
        "doi={10.1/b}}\n"
    )
    (run_dir / "paper" / "references.bib").write_text(paper_bib(bib), encoding="utf-8")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.passed  # advisory only
    lines = [n for n in report.paper_advisory if n.startswith("bib sort:")]
    assert len(lines) == 1 and "Dordevic2020" in lines[0], report.paper_advisory


def test_package_verify_carries_the_sort_advisory(tmp_path):
    from sci_adk.loop.verify import _check_package_requirements
    from tests.test_si_authoring_m6 import _POOL_BIB
    from tests.test_si_bib_integrity import _assemble_pkg_with_bibs

    si_bib = "@article{A2020, author={Ølsen, Kari}, title={Alpha}, doi={10.1/a}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(tmp_path, main_bib=_POOL_BIB, si_bib=si_bib)
    problems, warnings, _runs, _repro = _check_package_requirements(ws, ws / "package", pkgreqs)
    lines = [w for w in warnings if w.startswith("bib sort:")]
    assert len(lines) == 1, warnings
    assert "A2020" in lines[0] and "references_SI.bib" in lines[0] and "{\\O}" in lines[0]
    assert not any("bib sort" in p for p in problems)


# -- the copy as a whole ----------------------------------------------------------------------------


def test_the_paper_copy_of_the_trial_store_keeps_keys_and_passes_verify():
    copy = paper_bib(_STORE)
    assert bib_keys(copy) == bib_keys(_STORE)
    assert bib_latex_safety_problems(copy) == []
    assert "ISSN" not in copy and "dx.doi.org" not in copy


def test_the_paper_copy_is_idempotent():
    once = paper_bib(_STORE)
    assert paper_bib(once) == once


def test_the_paper_copy_starts_from_the_latex_safe_copy():
    # The minus sign in oki2005's title: the LaTeX-safe copy's math minus, then protected.
    assert "{Octanol}{$-$}{Water}" in paper_bib(_store_entry("oki2005"))
    assert "Octanol{$-$}Water" in latex_safe_bib(_store_entry("oki2005"))


def test_render_writes_the_paper_copy_and_leaves_the_store_as_acquired(tmp_path):
    from tests.test_si_authoring_m6 import _compile, _si_citing

    pool = "\n\n".join(_store_entry(k) for k in ("Arnot2006", "Mackay1982", "oki2005")) + "\n"
    run_dir, _ = _compile(tmp_path, "t-ref-list", _si_citing("oki2005"), pool_bib=pool)
    store = run_dir / "artifacts" / "literature" / "references.bib"
    assert store.read_text(encoding="utf-8") == pool

    paper = (run_dir / "paper" / "references.bib").read_text(encoding="utf-8")
    assert paper == paper_bib(pool)
    si = (run_dir / "paper" / "references_SI.bib").read_text(encoding="utf-8")
    assert bib_keys(si) == ["oki2005"]
    assert "{\\v{S}}o{\\v{s}}ki{\\'{c}}" in si and "ISSN" not in si


# -- bibtex + plainnat: the printed reference list ----------------------------------------------


def _bibitems(bbl: str) -> dict[str, str]:
    """``{key: printed text}`` of each ``\\bibitem`` in a .bbl, in order."""
    items = re.split(r"\\bibitem", bbl)[1:]
    out: dict[str, str] = {}
    for item in items:
        m = re.match(r"\[[^\]]*\]\{([^}]+)\}", item)
        out[m.group(1)] = item[m.end():].split("\\end{thebibliography}")[0]
    return out


@needs_tex
@pytest.mark.parametrize("figure_bearing", [False, True], ids=["latin-modern", "times"])
def test_the_trial_reference_list_prints_as_the_source_gives(tmp_path, figure_bearing):
    errors, bbl, dropped = _compile_with_bib(tmp_path, paper_bib(_STORE), figure_bearing)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    items = _bibitems(bbl)
    assert set(items) == set(bib_keys(_STORE))
    assert "ISSN" not in bbl and "doi.org" not in bbl
    assert "({BCF})" in items["Arnot2006"] and "({BAF})" in items["Arnot2006"]
    assert "{OPERA} models" in items["Mansouri2018"]
    assert "Molecular {Connectivity} {III}:" in items["Murray1975"]
    assert "{Matula} {Numbers}" in items["Elk1995"]
    assert "log {Kow}" in items["Finizio1995"]
    assert "Donald Mackay." in items["Mackay1982"] and "Donald." not in items["Mackay1982"]
    assert "\\doi{10.1021/es00099a008}" in items["Mackay1982"]
    # Šoškić sorts with the S names (plainnat sorts by author): after Sorgun, before Souza.
    order = list(items)
    assert order.index("Sorgun2025") < order.index("oki2005") < order.index("Souza2011"), order
