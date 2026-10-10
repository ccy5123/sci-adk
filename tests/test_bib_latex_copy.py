"""
The bibliography render writes into ``paper/`` is LaTeX-safe; the literature store is not touched.

Crossref BibTeX (fetched by paperforge into ``runs/<id>/literature/references.bib``) carries
HTML entities (``&amp;``), HTML markup (``<i>K</i>``) and Unicode math characters (U+2212 MINUS
SIGN in the title of the trial run's entry ``oki2005``). pdflatex with ``utf8`` inputenc stops on
U+2212. Render used to copy the store verbatim into ``paper/references.bib`` (and the cited-only
``paper/references_SI.bib``); it now writes a LaTeX-safe copy:

  - HTML entities -> LaTeX (``&amp;`` -> ``\\&``, ``&lt;``/``&gt;`` -> ``\\textless{}``/
    ``\\textgreater{}``, never read as a tag; quotes);
  - ``<i>``/``<em>`` -> ``\\textit{}``, ``<b>``/``<strong>`` -> ``\\textbf{}``, ``<sub>``/``<sup>``
    -> ``\\textsubscript{}``/``\\textsuperscript{}``, other known tags stripped (their text
    kept); any other ``<`` / ``>`` is text, and math is never read as markup;
  - a bare ``&``, ``%`` or ``#`` is escaped, and a bare ``_`` or ``^`` outside math; ``url`` and
    ``doi`` values are left as they are (their command prints them verbatim), and so are fields
    no style prints (abstract, keywords, file, ...);
  - a character pdflatex cannot typeset with the preamble sci-adk emits (utf8 inputenc, T1,
    Latin Modern or, under the figure font policy, Times) -> the curated map render already uses for prose (``render/paper.py``
    ``_UNICODE_MAP``; inside math its form without the ``$``), or LaTeX accent commands for a
    letter with combining marks (never a dropped mark); accented Latin letters pdflatex has
    stay as they are;
  - a bare month name BibTeX does not define (``month=June``) becomes its macro (``jun``);
  - entry keys are never touched, and the store keeps the bytes paperforge wrote.

Verify reports what is still unsafe in a run's ``paper/`` bibliographies (raw entity or tag, a
broken ``$``, a character pdflatex cannot typeset) as a publishing-requirements failure naming
the file, the entry key and the character -- only when the run has a frozen ``pubreqs.json``.
The package gate runs the same check, and fails an author manuscript that loads no T1 font
encoding when the bibliography it loads holds a character only T1 typesets.

The entries below are real. ``_TRIAL`` holds lines copied from the trial run's
``literature/references.bib`` (lit-search-trial-2, SPEC-BCFKOW-001). ``_CROSSREF`` holds what
doi.org content negotiation returned for the same DOIs on 2026-10-10, under the key the store
gives each entry -- the form paperforge receives before its own clean-up, and the form a bib
from any other path can still carry.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import pytest

from sci_adk.render.bib_latex import latex_safe_bib, paper_bib, typesettable
from sci_adk.render.figures import ImageFigureSpec
from sci_adk.render.paper import _UNICODE_MAP, render_paper_latex
from sci_adk.render.pkgreqs_checks import bib_keys, bib_latex_safety_problems
from tests.test_si import _basic_record
from tests.test_si_authoring_m6 import _POOL_BIB, _compile, _si_citing
from tests.test_si_bib_integrity import _assemble_pkg_with_bibs, _pkg_problems

# -- real entries ------------------------------------------------------------------------------

# Title carries U+2212 MINUS SIGN ("Octanol−Water"); authors carry Š/š/ć (Latin Extended-A).
_OKI2005 = (
    "@article{oki2005, title={Modeling the Octanol\u2212Water Partition Coefficients by an "
    "Optimized Molecular Connectivity Index}, volume={45}, ISSN={1549-960X}, "
    "url={http://dx.doi.org/10.1021/ci050024v}, DOI={10.1021/ci050024v}, number={4}, "
    "journal={Journal of Chemical Information and Modeling}, publisher={American Chemical "
    "Society (ACS)}, author={Šoškić, Milan and Plavšić, Dejan}, year={2005}, month=June, "
    "pages={930–938} }"
)

# The store's (already clean) lines for the five entries whose Crossref form holds &amp; or <i>,
# plus entries carrying characters pdflatex DOES typeset: U+2010 HYPHEN (CarbDorca2009), U+2019
# (Arman2012), en-dash pages, Latin-1 / Latin Extended-A accents.
_TRIAL = {
    "Bertelsen1998": (
        "@article{Bertelsen1998, title={Evaluation of log \\textit{K}\\textsubscript{OW} and "
        "tissue lipid content as predictors of chemical partitioning to fish tissues}, "
        "volume={17}, ISSN={1552-8618}, url={http://dx.doi.org/10.1002/etc.5620170803}, "
        "DOI={10.1002/etc.5620170803}, number={8}, journal={Environmental Toxicology and "
        "Chemistry}, publisher={Oxford University Press (OUP)}, author={Bertelsen, Sharon L and "
        "Hoffman, Alex D and Gallinat, Carol A and Elonen, Colleen M and Nichols, John W}, "
        "year={1998}, month=Aug, pages={1447–1455} }"
    ),
    "Bintein1993": (
        "@article{Bintein1993, title={Nonlinear Dependence of Fish Bioconcentration on "
        "\\textit{n}-Octanol/Water Partition Coefficient}, volume={1}, ISSN={1029-046X}, "
        "url={http://dx.doi.org/10.1080/10629369308028814}, DOI={10.1080/10629369308028814}, "
        "number={1}, journal={SAR and QSAR in Environmental Research}, publisher={Informa UK "
        "Limited}, author={Bintein, S. and Devillers, J. and Karcher, W.}, year={1993}, "
        "month=Mar, pages={29–39} }"
    ),
    "Kenaga1980": (
        "@article{Kenaga1980, title={Correlation of bioconcentration factors of chemicals in "
        "aquatic and terrestrial organisms with their physical and chemical properties}, "
        "volume={14}, ISSN={1520-5851}, url={http://dx.doi.org/10.1021/es60165a001}, "
        "DOI={10.1021/es60165a001}, number={5}, journal={Environmental Science \\& Technology}, "
        "publisher={American Chemical Society (ACS)}, author={Kenaga, Eugene E.}, year={1980}, "
        "month=May, pages={553–556} }"
    ),
    "Mackay1982": (
        "@article{Mackay1982, title={Correlation of bioconcentration factors}, volume={16}, "
        "ISSN={1520-5851}, url={http://dx.doi.org/10.1021/es00099a008}, "
        "DOI={10.1021/es00099a008}, number={5}, journal={Environmental Science \\& Technology}, "
        "publisher={American Chemical Society (ACS)}, author={Mackay, Donald.}, year={1982}, "
        "month=May, pages={274–278} }"
    ),
    "Neely1974": (
        "@article{Neely1974, title={Partition coefficient to measure bioconcentration potential "
        "of organic chemicals in fish}, volume={8}, ISSN={1520-5851}, "
        "url={http://dx.doi.org/10.1021/es60098a008}, DOI={10.1021/es60098a008}, number={13}, "
        "journal={Environmental Science \\& Technology}, publisher={American Chemical Society "
        "(ACS)}, author={Neely, W. Brock and Branson, Dean R. and Blau, Gary E.}, year={1974}, "
        "month=Dec, pages={1113–1115} }"
    ),
    "CarbDorca2009": (
        "@article{CarbDorca2009, title={Notes on quantitative structure\u2010properties "
        "relationships (QSPR) part 2: The role of the number of atoms as a molecular "
        "descriptor}, volume={30}, ISSN={1096-987X}, url={http://dx.doi.org/10.1002/jcc.21208}, "
        "DOI={10.1002/jcc.21208}, number={13}, journal={Journal of Computational Chemistry}, "
        "publisher={Wiley}, author={Carbó\u2010Dorca, Ramon and Saliner, Ana Gallegos}, "
        "year={2009}, month=Feb, pages={2099–2104} }"
    ),
    "Neto2013": (
        "@article{Neto2013, title={Matula numbers, Gödel numbering and Fock space}, "
        "volume={51}, ISSN={1572-8897}, url={http://dx.doi.org/10.1007/s10910-013-0178-z}, "
        "DOI={10.1007/s10910-013-0178-z}, number={7}, journal={Journal of Mathematical "
        "Chemistry}, publisher={Springer Science and Business Media LLC}, author={Neto, Antônio "
        "Francisco}, year={2013}, month=Apr, pages={1802–1814} }"
    ),
    "Klimoszek2025": (
        "@article{Klimoszek2025, title={Use of TLC and Computational Methods to Determine "
        "Lipophilicity Parameters of Selected Neuroleptics: Comparison of Experimental and "
        "Theoretical Studies}, volume={18}, ISSN={1424-8247}, "
        "url={http://dx.doi.org/10.3390/ph18091255}, DOI={10.3390/ph18091255}, number={9}, "
        "journal={Pharmaceuticals}, publisher={MDPI AG}, author={Klimoszek, Daria and Dołowy, "
        "Małgorzata and Jeleń, Małgorzata and Bober-Majnusz, Katarzyna}, year={2025}, "
        "month=Aug, pages={1255} }"
    ),
    "Arman2012": (
        "@inbook{Arman2012, title={Structural Relationship Study of Octanol-Water Partitioning "
        "Coefficients and Total Biodegradation of Barbiturate Medicines by Randić Descriptor}, "
        "ISBN={9789535102618}, url={http://dx.doi.org/10.5772/31647}, DOI={10.5772/31647}, "
        "booktitle={Can\u2019t Sleep? Issues of Being an Insomniac}, publisher={InTech}, "
        "author={Arman, Avat and Taherpour, Zhiva and Taherpour, Omid}, year={2012}, month=Mar }"
    ),
}

# Crossref's form of the five entries (doi.org, 2026-10-10), under the store's key.
_CROSSREF = {
    # Crossref's current title breaks lines around the italic K and no longer marks "OW" as a
    # subscript; the store kept the earlier "<i>K</i><sub>OW</sub>" form, cleaned up.
    "Bertelsen1998": (
        " @article{Bertelsen1998, title={Evaluation of log\n                    <i>K</i>\n"
        "                    OW and tissue lipid content as predictors of chemical "
        "partitioning to fish tissues}, volume={17}, ISSN={1552-8618}, "
        "url={http://dx.doi.org/10.1002/etc.5620170803}, DOI={10.1002/etc.5620170803}, "
        "number={8}, journal={Environmental Toxicology and Chemistry}, publisher={Oxford "
        "University Press (OUP)}, author={Bertelsen, Sharon L and Hoffman, Alex D and "
        "Gallinat, Carol A and Elonen, Colleen M and Nichols, John W}, year={1998}, month=Aug, "
        "pages={1447–1455} }\n"
    ),
    "Bintein1993": _TRIAL["Bintein1993"].replace("\\textit{n}", "<i>n</i>"),
    "Kenaga1980": _TRIAL["Kenaga1980"].replace("\\&", "&amp;"),
    "Mackay1982": _TRIAL["Mackay1982"].replace("\\&", "&amp;"),
    "Neely1974": _TRIAL["Neely1974"].replace("\\&", "&amp;"),
}


def _entry(title: str, key: str = "X2020") -> str:
    return f"@article{{{key}, title={{{title}}}, year={{2020}}}}"


def _title_of(bib: str) -> str:
    start = bib.index("title={") + len("title={")
    return bib[start : bib.index("}, year={2020}")]


# -- the copy: Unicode ---------------------------------------------------------------------------


def test_minus_sign_in_a_real_title_becomes_a_math_minus():
    out = latex_safe_bib(_OKI2005)
    assert "\u2212" not in out
    assert "Octanol{$-$}Water" in out
    # Latin Extended-A author names pdflatex typesets are left exactly as acquired.
    assert "author={Šoškić, Milan and Plavšić, Dejan}" in out
    assert "pages={930–938}" in out
    assert out.startswith("@article{oki2005,")


@pytest.mark.parametrize("char", ["Δ", "α", "≥", "∞"])
def test_unicode_math_goes_through_the_prose_map_in_a_case_protecting_group(char):
    # The replacement is render's own curated map; braces keep BibTeX's title case change
    # from turning $\Delta$ into $\delta$.
    assert _title_of(latex_safe_bib(_entry(f"a {char} b"))) == f"a {{{_UNICODE_MAP[char]}}} b"


def test_characters_pdflatex_typesets_are_left_as_they_are():
    title = "Gödel, Erdős, Dołowy, Ivić 1–2 Can\u2019t structure\u2010properties ± 5 °C"
    assert _title_of(latex_safe_bib(_entry(title))) == title


def test_unusual_spaces_become_ascii_and_zero_width_characters_are_dropped():
    assert _title_of(latex_safe_bib(_entry("Jon\u2005A. Arnot\u00a0x"))) == "Jon A. Arnot x"
    assert _title_of(latex_safe_bib(_entry("a\u200bb\ufeffc"))) == "abc"


def test_a_decomposed_accent_is_composed():
    assert _title_of(latex_safe_bib(_entry("Ivic\u0301"))) == "Ivić"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ﬁne", "fine"),  # ligature: its compatibility decomposition
        ("ǆ", "dž"),  # dz with caron: decomposed, then recomposed to a letter pdflatex has
        ("ϑ", "{$\\theta$}"),  # theta symbol: folds to theta, which the prose map has
        ("Ａ", "A"),  # fullwidth A: a width variant
    ],
)
def test_a_compatibility_character_is_folded_when_the_fold_typesets(raw, expected):
    assert _title_of(latex_safe_bib(_entry(raw))) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Lǚ", 'L{\\v{\\"{u}}}'),  # u with diaeresis and caron: nested, innermost mark first
        ("Ștefan", "{\\textcommabelow{S}}tefan"),  # S with comma below (Latin Extended-B)
        ("Țară", "{\\textcommabelow{T}}ară"),
        ("q́", "{\\'{q}}"),  # a combining acute with no precomposed letter
        ("Nguyễn", "Nguy{\\~{\\^{e}}}n"),  # e with circumflex and tilde (Vietnamese)
        ("ǐ", "{\\v{\\i}}"),  # a mark above i sits on the dotless i
        ("Ǿ", "{\\'{Ø}}"),  # O with stroke and acute: Ø is a letter pdflatex has
        ("ạ", "{\\d{a}}"),  # dot below
        ("Ȩ", "{\\c{E}}"),  # cedilla
        ("ǭ", "{\\={\\k{o}}}"),  # o with ogonek and macron
        ("ḇ", "{\\b{b}}"),  # macron below
        ("ẘ", "{\\r{w}}"),  # ring above
        ("Ő", "Ő"),  # double acute, Latin Extended-A: pdflatex has the letter, kept as is
    ],
)
def test_an_accented_letter_without_a_glyph_becomes_latex_accent_commands(raw, expected):
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == expected
    assert bib_latex_safety_problems(out) == []


@pytest.mark.parametrize(
    "raw, kept",
    [
        ("ả", "U+1EA3"),  # a with hook above: LaTeX has no standard command for the hook
        ("ά", "U+03AC"),  # Greek alpha with tonos: not a Latin letter to put an accent on
        ("x̛", "U+031B"),  # combining horn
    ],
)
def test_a_mark_without_a_latex_command_is_kept_for_verify_to_name(raw, kept):
    # Never a silently dropped mark: the character stays and verify names it.
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == unicodedata.normalize("NFC", raw)
    assert any(kept in p for p in bib_latex_safety_problems(out)), bib_latex_safety_problems(out)


def test_an_unknown_entity_name_is_escaped_as_text():
    assert _title_of(latex_safe_bib(_entry("R&D;x"))) == "R\\&D;x"


def test_a_latin_a_letter_latex_defines_no_glyph_for_is_kept_and_named():
    out = latex_safe_bib(_entry("Ħamrun"))  # H with stroke (Maltese)
    assert "Ħ" in out
    assert any("U+0126" in p for p in bib_latex_safety_problems(out))


def test_a_character_with_no_latex_form_is_kept_for_verify_to_name():
    # No curated mapping, no ASCII fold: the copy does not invent a placeholder.
    out = latex_safe_bib(_entry("李 2020"))
    assert "李" in out
    problems = bib_latex_safety_problems(out)
    assert any("X2020" in p and "U+674E" in p for p in problems), problems


# -- the copy: HTML ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["Bintein1993", "Kenaga1980", "Mackay1982", "Neely1974"]
)
def test_crossref_entities_and_italics_become_the_latex_the_store_holds(key):
    assert latex_safe_bib(_CROSSREF[key]) == _TRIAL[key]


def test_crossref_italic_across_line_breaks_becomes_textit():
    out = latex_safe_bib(_CROSSREF["Bertelsen1998"])
    assert "\\textit{K}" in out
    assert "<" not in out and ">" not in out


def test_italic_then_subscript_becomes_the_stored_title():
    raw = _TRIAL["Bertelsen1998"].replace(
        "\\textit{K}\\textsubscript{OW}", "<i>K</i><sub>OW</sub>"
    )
    assert latex_safe_bib(raw) == _TRIAL["Bertelsen1998"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("<em>Daphnia</em> magna", "\\textit{Daphnia} magna"),
        ("<b>bold</b> and <strong>strong</strong>", "\\textbf{bold} and \\textbf{strong}"),
        ("<sup>14</sup>C-labelled", "\\textsuperscript{14}C-labelled"),
        ("<I>K</I>", "\\textit{K}"),
        ("<i>K<sub>OW</sub></i>", "\\textit{K\\textsubscript{OW}}"),
        ('<span class="x">plain</span>', "plain"),
        ("<scp>dna</scp> repair", "dna repair"),
        ("<mml:math><mml:mi>x</mml:mi></mml:math>", "x"),
        ("a <br/> b", "a  b"),
    ],
)
def test_html_markup(raw, expected):
    assert _title_of(latex_safe_bib(_entry(raw))) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("p &lt; 0.05 &gt; q", "p \\textless{} 0.05 \\textgreater{} q"),
        ("&quot;quoted&quot;", '{"}quoted{"}'),
        ("it&#39;s", "it's"),
        ("a&#8722;b", "a{$-$}b"),
        ("a&nbsp;b", "a b"),
        # Encoded markup is text the depositor wrote: printed, never read as a tag.
        (
            "&lt;i&gt;n&lt;/i&gt;-octanol",
            "\\textless{}i\\textgreater{}n\\textless{}/i\\textgreater{}-octanol",
        ),
        ("&#60;b&#62;", "\\textless{}b\\textgreater{}"),
        # Decoded < and > that would read as a tag "<y and z>": the text must survive.
        ("x&lt;y and z&gt;w", "x\\textless{}y and z\\textgreater{}w"),
        ("R &amp; D", "R \\& D"),
        ("Acme & Sons", "Acme \\& Sons"),
        ("Env Sci \\& Tech", "Env Sci \\& Tech"),
    ],
)
def test_html_entities_and_ampersands(raw, expected):
    assert _title_of(latex_safe_bib(_entry(raw))) == expected


# -- the copy: %, #, _ and the url/doi fields ---------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("50% of #1 cases", "50\\% of \\#1 cases"),
        ("log_2 values", "log\\_2 values"),
        ("the $K_{OW}$ and $x_1$ of a_b", "the $K_{OW}$ and $x_1$ of a\\_b"),  # math keeps _
        ("$50%$", "$50\\%$"),  # % comments out the rest of the line, even in math
        ("already 5\\% \\#2 a\\_b", "already 5\\% \\#2 a\\_b"),
        ("see \\url{http://x.org/a_b#c}", "see \\url{http://x.org/a_b#c}"),
    ],
)
def test_percent_hash_and_underscore_are_escaped_in_field_values(raw, expected):
    assert _title_of(latex_safe_bib(_entry(raw))) == expected


_URL = "http://example.org/a_b?x=1&y=2%20z#frag"
_SICI_DOI = "10.1002/(SICI)1097-4636(199601)30:1<1::AID_JBM1>3.0.CO;2-N"


@pytest.mark.parametrize("name", ["url", "doi", "URL", "DOI"])
def test_url_and_doi_values_are_never_escaped(name):
    # plainnat prints url and doi through \url / \Url, which typeset their argument verbatim:
    # an escape there prints its backslash (measured: "AID\_JBM1" for \_ in a doi).
    value = _URL if name.lower() == "url" else _SICI_DOI
    bib = f"@article{{A2020, title={{a_b & c}}, {name}={{{value}}}, year={{2020}}}}"
    out = latex_safe_bib(bib)
    assert f"{name}={{{value}}}" in out
    assert "title={a\\_b \\& c}" in out
    assert bib_latex_safety_problems(out) == []


def test_an_entity_in_a_url_is_decoded_to_its_character():
    out = latex_safe_bib("@misc{A2020, url={http://x.org/?a=1&amp;b=2}, title={T}}")
    assert "url={http://x.org/?a=1&b=2}" in out


def test_quoted_and_concatenated_values_are_field_values_too():
    bib = '@string{jn = "J. 50%"}\n@article{A2020, title = "a_b" # jn # {c#d}, year=2020}'
    out = latex_safe_bib(bib)
    assert '@string{jn = "J. 50\\%"}' in out
    assert 'title = "a\\_b" # jn # {c\\#d}' in out  # the concatenation # is BibTeX syntax


@pytest.mark.parametrize(
    "value, char",
    [("50% of", "%"), ("item #1", "#"), ("log_2", "_")],
)
def test_verify_names_a_bare_percent_hash_or_underscore(value, char):
    problems = bib_latex_safety_problems(_entry(value))
    assert any("X2020" in p and f"bare '{char}'" in p for p in problems), problems


def test_verify_accepts_url_and_doi_values_as_they_are():
    bib = f"@article{{A2020, title={{T}}, url={{{_URL}}}, doi={{{_SICI_DOI}}}, year={{2020}}}}"
    assert bib_latex_safety_problems(bib) == []


# -- the copy: what it never changes ---------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(_TRIAL))
def test_already_safe_store_entries_are_copied_byte_for_byte(key):
    assert latex_safe_bib(_TRIAL[key]) == _TRIAL[key]


def test_the_copy_is_idempotent():
    once = latex_safe_bib("\n\n".join([_OKI2005, *_CROSSREF.values()]))
    assert latex_safe_bib(once) == once


@pytest.mark.parametrize(
    "title",
    [
        "On $x ≥ 3$ and $α−1$, $Δx₂$, $q́$, $a ± b$, $x &lt; y$",  # math forms, \mbox
        "if n<k and m>j, $a<i>b$, x &lt;i&gt; y, Fe^3+",  # comparisons, caret
        "ȩ́ ẹ́ ố ở <i>K</i><sub>OW</sub> 50% a_b",  # accents, markup
    ],
)
def test_the_copy_of_the_second_review_cases_is_idempotent(title):
    once = latex_safe_bib(_entry(title).replace("year={2020}", "year={2020}, month=sept"))
    assert latex_safe_bib(once) == once


def test_keys_are_never_touched():
    bib = "@misc{R&D2020, title={Acme & Sons}}\n@misc{Tag<i>2021, title={x}}\n"
    out = latex_safe_bib(bib)
    assert out.startswith("@misc{R&D2020, title={Acme \\& Sons}}")
    assert "@misc{Tag<i>2021," in out
    assert bib_keys(out) == bib_keys(bib)


# -- verify: what is still unsafe ----------------------------------------------------------------


def test_verify_names_the_key_and_the_untypesettable_character():
    problems = bib_latex_safety_problems(_OKI2005)
    assert len(problems) == 1, problems
    assert "oki2005" in problems[0] and "U+2212" in problems[0]
    assert "references.bib" in problems[0]


def test_verify_names_the_entity_and_the_tag():
    problems = bib_latex_safety_problems(_CROSSREF["Kenaga1980"] + "\n" + _CROSSREF["Bintein1993"])
    assert any("Kenaga1980" in p and "&amp;" in p for p in problems), problems
    assert any("Bintein1993" in p and "<i>" in p for p in problems), problems
    # The one found, not a fixed example.
    problems = bib_latex_safety_problems(_entry("a &gt; b<sub>2</sub>"))
    assert any("X2020" in p and "&gt;" in p for p in problems), problems
    assert any("X2020" in p and "<sub>" in p for p in problems), problems


def test_verify_catches_a_tag_with_attributes():
    problems = bib_latex_safety_problems(_entry('a <span class="x">b</span>'))
    assert any("X2020" in p and "<span" in p for p in problems), problems


def test_verify_names_the_file_it_checked():
    problems = bib_latex_safety_problems(_OKI2005, source="references_SI.bib")
    assert problems and all("references_SI.bib" in p for p in problems)


def test_the_copy_of_every_real_entry_passes_verify():
    store = "\n\n".join([_OKI2005, *_CROSSREF.values(), *_TRIAL.values()])
    assert bib_latex_safety_problems(latex_safe_bib(store)) == []


# -- render: the paper/ copies -------------------------------------------------------------------

_RAW_POOL = "\n\n".join([_OKI2005, *_CROSSREF.values()]) + "\n"


def test_render_writes_latex_safe_copies_and_leaves_the_store_as_acquired(tmp_path):
    run_dir, _ = _compile(
        tmp_path, "t-bib-latex", _si_citing("oki2005", "Kenaga1980"), pool_bib=_RAW_POOL
    )
    store = run_dir / "artifacts" / "literature" / "references.bib"
    assert store.read_text(encoding="utf-8") == _RAW_POOL

    paper_copy = (run_dir / "paper" / "references.bib").read_text(encoding="utf-8")
    assert bib_keys(paper_copy) == bib_keys(_RAW_POOL)
    assert bib_latex_safety_problems(paper_copy) == []
    # The math minus, its neighbours' casing protected (tests/test_reference_list.py).
    assert "{Octanol}{$-$}{Water}" in paper_copy
    assert "Environmental Science \\& Technology" in paper_copy

    si_bib = (run_dir / "paper" / "references_SI.bib").read_text(encoding="utf-8")
    assert bib_keys(si_bib) == ["Kenaga1980", "oki2005"]
    assert bib_latex_safety_problems(si_bib, source="references_SI.bib") == []


# -- verify: the per-run and package gates --------------------------------------------------------


def _paper_problems(run_dir: Path, *, contract: bool) -> list[str]:
    from sci_adk.core.pubreqs import PubReqs
    from sci_adk.loop.verify import (
        _check_paper_requirements,
        _load_claims,
        _load_evidence,
        _load_spec,
    )

    if contract:
        (run_dir / "pubreqs.json").write_text(
            PubReqs(spec_id=run_dir.name, digest="fixture-digest").model_dump_json(),
            encoding="utf-8",
        )
    problems, _warnings = _check_paper_requirements(
        run_dir,
        _load_evidence(run_dir),
        list(_load_claims(run_dir).values()),
        _load_spec(run_dir),
    )
    return problems


def _safety_lines(problems: list[str]) -> list[str]:
    return [p for p in problems if "LaTeX-safety" in p]


def test_per_run_gate_is_clean_after_rendering_a_raw_crossref_pool(tmp_path):
    run_dir, _ = _compile(tmp_path, "t-bib-clean", _si_citing("oki2005"), pool_bib=_RAW_POOL)
    assert _safety_lines(_paper_problems(run_dir, contract=True)) == []


def test_per_run_gate_fails_on_an_unsafe_paper_bib_naming_key_and_character(tmp_path):
    run_dir, _ = _compile(tmp_path, "t-bib-main", _si_citing("A2020"))
    (run_dir / "paper" / "references.bib").write_text(_POOL_BIB + _OKI2005 + "\n", encoding="utf-8")
    lines = _safety_lines(_paper_problems(run_dir, contract=True))
    assert any(
        "references.bib" in p and "references_SI.bib" not in p
        and "oki2005" in p and "U+2212" in p
        for p in lines
    ), lines


def test_per_run_gate_fails_on_an_unsafe_si_bib(tmp_path):
    run_dir, _ = _compile(tmp_path, "t-bib-si", _si_citing("A2020"))
    (run_dir / "paper" / "references_SI.bib").write_text(
        _POOL_BIB + _CROSSREF["Kenaga1980"], encoding="utf-8"
    )
    lines = _safety_lines(_paper_problems(run_dir, contract=True))
    assert any("references_SI.bib" in p and "Kenaga1980" in p and "&amp;" in p for p in lines), lines


def test_a_run_without_a_contract_is_unaffected(tmp_path):
    run_dir, _ = _compile(tmp_path, "t-bib-nocontract", _si_citing("A2020"))
    (run_dir / "paper" / "references.bib").write_text(_OKI2005 + "\n", encoding="utf-8")
    assert _safety_lines(_paper_problems(run_dir, contract=False)) == []


def test_package_gate_checks_both_bibs(tmp_path):
    si_bib = "@article{A2020, title={Alpha &amp; Beta}, doi={10.1/a}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(
        tmp_path, main_bib=_POOL_BIB + _OKI2005 + "\n", si_bib=si_bib
    )
    lines = _safety_lines(_pkg_problems(ws, pkgreqs))
    assert any("references_SI.bib" in p and "A2020" in p for p in lines), lines
    assert any(
        "references.bib" in p and "references_SI.bib" not in p and "oki2005" in p
        for p in lines
    ), lines


def test_package_lines_name_the_package_source_file_not_a_rerender(tmp_path):
    # A package's bibliographies are copied from package_src/ unchanged, so re-rendering a
    # run never touches them: each package line names the file the author has to fix.
    si_bib = "@article{A2020, title={Alpha &amp; Beta}, doi={10.1/a}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(
        tmp_path, main_bib=_POOL_BIB + _OKI2005 + "\n", si_bib=si_bib
    )
    lines = _safety_lines(_pkg_problems(ws, pkgreqs))
    main = [p for p in lines if "references.bib entry" in p]
    si = [p for p in lines if "references_SI.bib entry" in p]
    assert main and all("package_src/references.bib" in p for p in main), main
    assert si and all("package_src/references_SI.bib" in p for p in si), si
    assert not any("re-render" in p or "paper/" in p for p in lines), lines


def test_package_si_bib_cut_from_the_main_bib_names_the_main_source(tmp_path):
    ws, pkgreqs = _assemble_pkg_with_bibs(
        tmp_path, main_bib=_POOL_BIB + _OKI2005 + "\n", si_bib=_POOL_BIB
    )
    # No author references_SI.bib: the package cuts it from package_src/references.bib.
    (ws / "package_src" / "references_SI.bib").unlink()
    (ws / "package" / "01_manuscript" / "references_SI.bib").write_text(
        _OKI2005 + "\n", encoding="utf-8"
    )
    lines = [p for p in _safety_lines(_pkg_problems(ws, pkgreqs)) if "references_SI.bib" in p]
    assert lines and all("package_src/references.bib" in p for p in lines), lines


def test_per_run_lines_keep_the_rerender_wording(tmp_path):
    run_dir, _ = _compile(tmp_path, "t-bib-wording", _si_citing("A2020"))
    (run_dir / "paper" / "references.bib").write_text(_POOL_BIB + _OKI2005 + "\n", encoding="utf-8")
    lines = _safety_lines(_paper_problems(run_dir, contract=True))
    assert any("U+2212" in p and "re-rendering a run rewrites its paper/ copy" in p for p in lines)
    assert not any("package_src" in p for p in lines), lines


# -- second review: math, unprinted fields, angle brackets, caret, accents, months, T1 ----------
#
# Each defect below was reproduced by compiling the old copy with the render preamble.


@pytest.mark.parametrize(
    "raw, expected",
    [
        # The prose map's $...$ forms inside author math: the inner form, never nested $.
        ("On $x ≥ 3$ and $α−1$", "On $x \\geq 3$ and $\\alpha-1$"),
        ("$αx$", "$\\alpha x$"),  # a control word never runs into the letter after it
        # An uppercase command keeps a brace group in math too: plainnat lowercases titles.
        ("$Δ x$ and Δ", "${\\Delta} x$ and {$\\Delta$}"),
        ("$x₂$", "$x_2$"),
        ("$a ± b$", "$a \\pm b$"),  # a sign pdflatex has in text takes its math form in math
        ("$q́$", "$\\mbox{{\\'{q}}}$"),  # accent commands are text-mode: boxed inside math
        ("$x &lt; y$ and x &lt; y", "$x < y$ and x \\textless{} y"),
    ],
)
def test_non_ascii_inside_math_takes_its_math_form_without_dollars(raw, expected):
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == expected
    assert bib_latex_safety_problems(out) == []


@pytest.mark.parametrize("value", ["On $x {$\\geq$} 3$", "Price in $US"])
def test_verify_names_a_dollar_nested_inside_math_or_left_open(value):
    problems = bib_latex_safety_problems(_entry(value))
    assert any("X2020" in p and "'$'" in p and "math" in p for p in problems), problems


@pytest.mark.parametrize(
    "value", ["$x$ and {$y$}", "$a \\mbox{if $b$} c$", "\\$5 and \\$6", "{\\$}", "$$x$$"]
)
def test_verify_accepts_well_formed_math(value):
    assert bib_latex_safety_problems(_entry(value)) == []


# A Zotero export: fields no BibTeX style prints carry raw Unicode, HTML and bare specials.
_ZOTERO = (
    "@article{Smith2020,\n"
    "  title = {Partitioning of {PFAS} in fish},\n"
    "  author = {Smith, Jane},\n"
    "  journal = {Environ. Sci. Technol.},\n"
    "  year = {2020},\n"
    "  url = {http://example.org/view?b&c;d},\n"
    "  doi = {10.1021/es0001},\n"
    "  abstract = {<jats:p>The \u03b1 value fell by 3\u22121 units: 50% of #2 log_K "
    "samples.</jats:p>},\n"
    "  keywords = {PFAS, log_K_OW, #bioaccumulation},\n"
    "  file = {Full Text PDF:/home/u/Zotero/storage/AB12/Smith_2020_50%.pdf:application/pdf},\n"
    "  annote = {see p. 4 & table_2},\n"
    "  timestamp = {2024-01-02T10:00:00Z},\n"
    "}\n"
)


def test_a_zotero_shaped_entry_passes_verify():
    assert bib_latex_safety_problems(_ZOTERO) == []


def test_the_copy_leaves_fields_no_style_prints_as_they_are():
    raw = _ZOTERO.replace("in fish", "in fish & sea")
    out = latex_safe_bib(raw)
    for field in ("url", "abstract", "keywords", "file", "annote", "timestamp"):
        line = next(x for x in raw.splitlines() if x.strip().startswith(field))
        assert line in out, field
    assert "in fish \\& sea" in out


def test_verify_still_checks_every_field_outside_the_unprinted_list():
    for field in ("note", "howpublished", "mynote"):
        problems = bib_latex_safety_problems(f"@misc{{A2020, {field}={{50% of x}}, title={{T}}}}")
        assert any("A2020" in p and "bare '%'" in p for p in problems), (field, problems)


def test_an_entity_shape_in_a_url_other_than_an_xml_escape_is_kept():
    out = latex_safe_bib("@misc{A2020, url={http://x.org/?a=1&copy;b=2&amp;c=3}, title={T}}")
    assert "url={http://x.org/?a=1&copy;b=2&c=3}" in out


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("if n<k and m>j", "if n\\textless{}k and m\\textgreater{}j"),
        ("$x<y $ and $z>w$", "$x<y $ and $z>w$"),
        ("$a<i>b$", "$a<i>b$"),  # math is never read as markup
        ("x <y> z", "x \\textless{}y\\textgreater{} z"),
        ('<span class="x">plain</span> <jats:italic>K</jats:italic>', "plain K"),
        ('<mml:mi mathvariant="normal">x</mml:mi>', "x"),
        ("<u>under</u> <sc>dna</sc> <p>para</p><div>d</div>", "under dna parad"),
    ],
)
def test_only_known_markup_is_read_as_a_tag(raw, expected):
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == expected
    assert bib_latex_safety_problems(out) == []


@pytest.mark.parametrize("value", ["if n<k and m>j", "$x<y $ and $z>w$", "x <y> z"])
def test_verify_does_not_read_comparisons_as_tags(value):
    assert not any("HTML tag" in p for p in bib_latex_safety_problems(_entry(value)))


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "Fe^3+ binding and 10^-3 M",
            "Fe\\textasciicircum{}3+ binding and 10\\textasciicircum{}-3 M",
        ),
        ("$10^{-3}$ M and \\^{o}", "$10^{-3}$ M and \\^{o}"),
    ],
)
def test_a_bare_caret_outside_math_prints_as_a_caret(raw, expected):
    # Measured: \textasciicircum{} prints U+005E; \^{} prints a raised accent (U+02C6).
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == expected
    assert bib_latex_safety_problems(out) == []


def test_verify_names_a_bare_caret():
    problems = bib_latex_safety_problems(_entry("Fe^3+"))
    assert any("X2020" in p and "bare '^'" in p and "\\textasciicircum{}" in p for p in problems)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("\u0229\u0301", "{\\'{\\c{e}}}"),  # e with cedilla (precomposed) + combining acute
        ("e\u0327\u0301", "{\\'{\\c{e}}}"),  # the same, fully decomposed
        ("\u1eb9\u0301", "{\\'{\\d{e}}}"),  # e with dot below + combining acute
        ("ố", "{\\'{\\^{o}}}"),  # o with circumflex and acute (Vietnamese)
    ],
)
def test_a_letter_whose_base_decomposes_further_gets_all_its_accents(raw, expected):
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == expected
    assert bib_latex_safety_problems(out) == []


@pytest.mark.parametrize("raw", ["ở", "ớ", "o\u031b\u0301"])
def test_a_letter_with_a_mark_latex_has_no_command_for_is_kept_whole(raw):
    # Horn and hook above have no LaTeX command: the acute is not turned into \' on a
    # letter that would then have lost its horn.
    out = latex_safe_bib(_entry(raw))
    assert _title_of(out) == unicodedata.normalize("NFC", raw)


def test_verify_says_how_to_fix_a_character_with_no_latex_form():
    problems = bib_latex_safety_problems(_entry("Hồ ở"))
    no_form = [p for p in problems if "U+1EDF" in p]
    assert len(no_form) == 1, problems
    assert "no automatic LaTeX form" in no_form[0]
    assert "ASCII approximation" in no_form[0]
    assert "literature/references.bib" in no_form[0]
    assert "U+2212" not in no_form[0] and "$-$" not in no_form[0]
    with_form = [p for p in problems if "U+1ED3" in p]
    assert with_form and "{\\`{\\^{o}}}" in with_form[0], problems


def test_verify_names_the_latex_form_of_a_character_that_has_one():
    problems = bib_latex_safety_problems(_OKI2005, package_source="package_src/references.bib")
    assert len(problems) == 1 and "{$-$}" in problems[0] and "package_src" in problems[0]
    assert "literature" not in problems[0], problems


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("month=June", "month=jun"),
        ("month = sept", "month = sep"),
        ("month=SEPTEMBER", "month=sep"),
        ("month=Aug", "month=Aug"),  # a macro BibTeX defines (case-insensitive): kept
        ("month=May", "month=May"),
        ("month={June}", "month={June}"),  # braced text is printed as it is
    ],
)
def test_a_bare_month_name_becomes_the_bibtex_month_macro(raw, expected):
    bib = f"@article{{A2020, title={{month = June}}, {raw}, year={{2020}}}}"
    out = latex_safe_bib(bib)
    assert f", {expected}," in out
    assert "title={month = June}" in out


def test_verify_advises_on_a_month_name_bibtex_does_not_define():
    from sci_adk.render.pkgreqs_checks import bib_month_advisories

    lines = bib_month_advisories("@article{A2020, month=June, title={T}}\n@misc{B2021, month=Jan}")
    assert len(lines) == 1, lines
    assert "A2020" in lines[0] and "June" in lines[0] and "month = jun" in lines[0]


def test_package_gate_advises_on_an_author_bib_month_name(tmp_path):
    from sci_adk.loop.verify import _check_package_requirements

    main_bib = _POOL_BIB + "@article{D2023, title={D}, month=sept, doi={10.1/d}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(tmp_path, main_bib=main_bib, si_bib=_POOL_BIB)
    problems, warnings, _runs, _repro = _check_package_requirements(ws, ws / "package", pkgreqs)
    assert any("D2023" in w and "month = sep" in w for w in warnings), warnings
    assert not any("D2023" in p for p in problems), problems


_NO_T1_MAIN = (
    "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{natbib}\n"
    "\\begin{document}\nx \\citep{Thor2001}\n\\bibliography{references}\n\\end{document}\n"
)
_T1_ONLY_BIB = (
    "@article{Thor2001, author={Þórðarson, Ð.}, title={T}, journal={J}, year={2001}}\n"
    "@article{Kap2002, author={Kap, A.}, title={{\\k{a}}}, journal={J}, year={2002}}\n"
    "@article{Ok2003, author={Gödel, K.}, title={Erdős – Dołowy}, journal={J}, year={2003},"
    " abstract={ŋ in an abstract}}\n"
)


def _font_problems(tex: str, bib: str) -> list[str]:
    from sci_adk.render.pkgreqs_checks import font_encoding_problems

    return font_encoding_problems(
        tex, bib, tex_name="main.tex", bib_name="references.bib", fix_in="package_src/main.tex"
    )


def test_a_manuscript_without_t1_fails_when_its_bib_holds_a_t1_only_character():
    problems = _font_problems(_NO_T1_MAIN, _T1_ONLY_BIB)
    assert len(problems) == 1, problems
    line = problems[0]
    for part in ("Þ", "ð", "Ð", "\\k", "Thor2001", "Kap2002", "references.bib",
                 "\\usepackage[T1]{fontenc}", "package_src/main.tex"):
        assert part in line, (part, line)
    assert "Ok2003" not in line and "ŋ" not in line  # OT1-safe letters; abstract not printed


@pytest.mark.parametrize(
    "preamble_line",
    ["\\usepackage[T1]{fontenc}", "\\usepackage[LY1,T1]{fontenc}", "\\usepackage{fontspec}"],
)
def test_a_manuscript_that_loads_t1_or_fontspec_is_unaffected(preamble_line):
    tex = _NO_T1_MAIN.replace("\\begin{document}", preamble_line + "\n\\begin{document}")
    assert _font_problems(tex, _T1_ONLY_BIB) == []


def test_a_bib_without_t1_only_characters_is_unaffected_and_a_commented_line_does_not_count():
    clean = _T1_ONLY_BIB.split("\n", 2)[2]
    assert _font_problems(_NO_T1_MAIN, clean) == []
    commented = _NO_T1_MAIN.replace(
        "\\begin{document}", "% \\usepackage[T1]{fontenc}\n\\begin{document}"
    )
    assert _font_problems(commented, _T1_ONLY_BIB)


def test_package_gate_checks_each_manuscript_against_the_bib_it_loads(tmp_path):
    from sci_adk.render.package import assemble_package

    si_bib = "@article{A2020, author={Đuro, Ana}, title={Alpha}, journal={J}, doi={10.1/a}}\n"
    ws, pkgreqs = _assemble_pkg_with_bibs(tmp_path, main_bib=_POOL_BIB + _T1_ONLY_BIB, si_bib=si_bib)
    lines = [p for p in _pkg_problems(ws, pkgreqs) if "T1" in p]
    # The author si.tex loads no fontenc and its references_SI.bib holds Đ; the main.tex
    # skeleton sci-adk writes loads T1, so its bib (Þ, Ð, \k) is fine.
    assert len(lines) == 1 and "si.tex" in lines[0] and "Đ" in lines[0], lines
    assert "package_src/si.tex" in lines[0]

    (ws / "package_src" / "main.tex").write_text(_NO_T1_MAIN, encoding="utf-8")
    assemble_package(ws, pkgreqs)
    lines = [p for p in _pkg_problems(ws, pkgreqs) if "T1" in p]
    assert any("main.tex" in p and "Thor2001" in p and "package_src/main.tex" in p for p in lines)


# -- pdflatex: what typesettable() accepts, and the copy of a real bib, compile ----------------

_TEX_TOOLS = ("pdflatex", "bibtex", "kpsewhich")
needs_tex = pytest.mark.skipif(
    not all(shutil.which(t) for t in _TEX_TOOLS), reason="pdflatex/bibtex/kpsewhich not on PATH"
)
_USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}")
# The packages the claim under test rests on: without them the test proves nothing. The text
# typeface is the one the preamble emits: Latin Modern without the figure font policy, Times
# (newtxtext + newtxmath) with it.
_ESSENTIAL = {"inputenc", "fontenc", "natbib", "hyperref", "url"}
_ESSENTIAL_FONTS = {False: {"lmodern"}, True: {"newtxtext", "newtxmath"}}
_TRIAL_BIB = Path(__file__).parent / "fixtures" / "bib_trial2" / "references.bib"


@functools.lru_cache(maxsize=None)
def _loadable(package: str) -> bool:
    """True iff this TeX install loads ``package`` and sets roman, typewriter and math text with
    it after T1 (a .sty kpsewhich finds can still fail on a missing dependency or font: newtx's
    newtxtext needs fontaxes and txfonts). Latin Modern is loaded first, so a package that sets
    no font leaves vector fonts in place (no bitmap font is generated for the probe)."""
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.tex"
        probe.write_text(
            "\\documentclass{article}\\usepackage[T1]{fontenc}\\usepackage{lmodern}"
            f"\\usepackage{{amsmath}}\\usepackage{{{package}}}"
            "\\begin{document}x \\texttt{x} $x$\\end{document}\n",
            encoding="utf-8",
        )
        return _run(["pdflatex", "-interaction=nonstopmode", "probe.tex"], Path(tmp)) == 0


def _render_preamble(figure_bearing: bool = True) -> tuple[list[str], list[str]]:
    """The preamble a render emits -- for a figure-bearing paper (font policy: Times text and
    math) or a figure-less one (Latin Modern) -- minus any package this TeX install cannot load
    (returned second, so a failure says which were dropped). Skips when an essential package
    (one the claim rests on, the text typeface included) cannot be loaded."""
    spec, claims, evidence = _basic_record()
    figures = (
        [ImageFigureSpec(kind="image", id="fig-a", caption="A caption.", image="a.png")]
        if figure_bearing
        else []
    )
    tex = render_paper_latex(spec, claims, evidence, figures=figures)
    kept: list[str] = []
    dropped: list[str] = []
    for line in tex[: tex.index(r"\begin{document}")].splitlines():
        m = _USEPACKAGE_RE.search(line)
        missing = [p.strip() for p in m.group(1).split(",") if not _loadable(p.strip())] if m else []
        if missing:
            dropped.extend(missing)
            continue
        kept.append(line)
    essential = _ESSENTIAL | _ESSENTIAL_FONTS[figure_bearing]
    if essential & set(dropped):
        pytest.skip(f"this TeX install cannot load {sorted(essential & set(dropped))}")
    return kept, dropped


def _run(cmd: list[str], cwd: Path) -> int:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, check=False).returncode


def _log_errors(log: str) -> list[str]:
    errors = [line for line in log.splitlines() if line.startswith("!")]
    errors += re.findall(r"Missing character: There is no .*", log)
    return errors


def _compile_with_bib(
    tmp_path: Path, bib: str, figure_bearing: bool = True
) -> tuple[list[str], str, list[str]]:
    """``\\nocite{*}`` over ``bib`` with the render's preamble (figure-bearing: Times;
    figure-less: Latin Modern) and plainnat, as Overleaf runs it (pdflatex, bibtex, pdflatex
    twice). Returns (errors, .bbl text, dropped packages)."""
    preamble, dropped = _render_preamble(figure_bearing)
    (tmp_path / "references.bib").write_text(bib, encoding="utf-8")
    body = [r"\begin{document}", r"\nocite{*}", r"\bibliographystyle{plainnat}",
            r"\bibliography{references}", r"\end{document}"]
    (tmp_path / "t.tex").write_text("\n".join(preamble + body) + "\n", encoding="utf-8")
    pdflatex = ["pdflatex", "-interaction=nonstopmode", "t.tex"]
    _run(pdflatex, tmp_path)
    bibtex_status = _run(["bibtex", "t"], tmp_path)
    _run(pdflatex, tmp_path)
    status = _run(pdflatex, tmp_path)
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace")
    errors = _log_errors(log)
    if bibtex_status >= 2:  # 1 = warnings only (e.g. an entry with no journal)
        errors.append(f"bibtex exited {bibtex_status}")
    # BibTeX drops a field whose bare macro it does not define (month = June): only a
    # warning, but the reference list silently loses the month.
    blg = (tmp_path / "t.blg").read_text(encoding="utf-8", errors="replace")
    errors += re.findall(r"Warning--string name .* is undefined", blg)
    if status != 0:
        errors.append(f"pdflatex exited {status}")
    bbl = (tmp_path / "t.bbl").read_text(encoding="utf-8", errors="replace")
    return errors, bbl, dropped


_PREAMBLES = pytest.mark.parametrize(
    "figure_bearing", [False, True], ids=["latin-modern", "times"]
)


@needs_tex
@_PREAMBLES
def test_every_character_typesettable_accepts_compiles_with_the_render_preamble(
    tmp_path, figure_bearing
):
    # Every non-ASCII character typesettable() accepts, plus printable ASCII that is not LaTeX
    # markup, one per line, in a document with the preamble a render emits: Latin Modern for
    # a figure-less paper, Times (newtxtext + newtxmath) for a figure-bearing one. A missing
    # glyph ("Missing character" in the log) counts as a failure.
    markup = set("\\{}$&#^_~%")
    accepted = [
        chr(c) for c in range(sys.maxunicode + 1)
        if (c >= 0x80 or 0x20 < c < 0x7F) and chr(c) not in markup and typesettable(chr(c))
    ]
    preamble, dropped = _render_preamble(figure_bearing)
    first = len(preamble) + 2  # the line number of the first character
    lines = preamble + [r"\begin{document}"] + [f"{ch}\\par" for ch in accepted] + [
        r"\end{document}"
    ]
    (tmp_path / "chars.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    status = _run(["pdflatex", "-interaction=nonstopmode", "chars.tex"], tmp_path)
    log = (tmp_path / "chars.log").read_text(encoding="utf-8", errors="replace")
    failing = sorted(
        {accepted[n - first] for n in map(int, re.findall(r"^l\.(\d+)", log, re.M))
         if 0 <= n - first < len(accepted)}
    )
    assert status == 0 and not _log_errors(log) and not failing, (
        f"typesettable() accepts characters pdflatex fails on: {failing!r} "
        f"(errors {_log_errors(log)[:5]}; packages dropped as not installed: {dropped})"
    )


def test_typesettable_rejects_the_ascii_controls_pdflatex_refuses():
    assert all(typesettable(c) for c in "\t\n\r")
    assert not any(typesettable(chr(c)) for c in [*range(0x00, 0x09), 0x0B, *range(0x0E, 0x20), 0x7F])


@needs_tex
@_PREAMBLES
def test_the_copy_of_the_trial_run_bib_compiles_with_bibtex_and_plainnat(
    tmp_path, figure_bearing
):
    # tests/fixtures/bib_trial2/references.bib: the trial run's literature/references.bib
    # (lit-search-trial-2, SPEC-BCFKOW-001; 40 entries as paperforge wrote them), copied
    # 2026-10-10. Its oki2005 title holds U+2212, which stopped the manuscript's compile.
    store = _TRIAL_BIB.read_text(encoding="utf-8")
    copy = latex_safe_bib(store)
    assert bib_latex_safety_problems(copy) == []
    errors, bbl, dropped = _compile_with_bib(tmp_path, copy, figure_bearing)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    assert set(re.findall(r"\\bibitem\[[^\]]*\]\{([^}]+)\}", bbl)) == set(bib_keys(store))


@needs_tex
@_PREAMBLES
def test_the_copy_of_the_hard_cases_compiles_with_bibtex_and_plainnat(tmp_path, figure_bearing):
    # The characters OT1 cannot typeset, accent commands, entities, the specials and verbatim
    # url/doi values, through bibtex + plainnat with the render's preamble.
    entries = [
        "@article{Thor2001, author={Þórðarson, Ð. and Łęcki, Ąda}, title={« Đuro » ‹x› "
        "‚y„ ŋ Ų į}, journal={J}, year={2001}}",
        "@article{Lu2002, author={Lǚ, Wei and Ștefan, Ion}, title={Nguyễn q\u0301 ǐ ḇ}, "
        "journal={J}, year={2002}}",
        "@article{Ent2003, title={x&lt;y and z&gt;w, &lt;i&gt;n&lt;/i&gt;, R &amp; D}, "
        "journal={Env Sci &amp; Tech}, year={2003}}",
        f"@article{{Spec2004, title={{50% of #1 log_2 $K_{{OW}}$}}, journal={{J}}, year={{2004}}, "
        f"url={{{_URL}}}, doi={{{_SICI_DOI}}}}}",
        # Second review: non-ASCII inside math, comparisons that are not markup, a bare
        # caret, letters whose base decomposes further, a bare month name.
        "@article{Math2005, title={On $x ≥ 3$ and $α−1$, $Δx₂$, $q́$, $a ± b$, "
        "$x &lt; y$}, journal={J}, year={2005}, month=June}",
        "@article{Angle2006, title={if n<k and m>j, $x<y $ and $z>w$, $a<i>b$, Fe^3+ and "
        "10^-3 M}, journal={J}, year={2006}, month=sept}",
        "@article{Acc2007, author={Lȩ́, Ann}, title={ẹ́ ố}, journal={J}, "
        "year={2007}}",
        _ZOTERO,
    ]
    copy = latex_safe_bib("\n\n".join(entries) + "\n")
    assert bib_latex_safety_problems(copy) == []
    errors, bbl, dropped = _compile_with_bib(tmp_path, copy, figure_bearing)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    assert len(re.findall(r"\\bibitem", bbl)) == 8
    # The reference-list copy render writes (name letters as commands, case protection, no
    # ISSN) of the same hard cases compiles too.
    errors, bbl, dropped = _compile_with_bib(tmp_path, paper_bib(copy), figure_bearing)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    assert len(re.findall(r"\\bibitem", bbl)) == 8


@needs_tex
@_PREAMBLES
def test_a_zotero_shaped_entry_compiles_as_it_is(tmp_path, figure_bearing):
    # Verify passes it (above) because no style prints abstract, keywords, file, annote or
    # timestamp; this shows the uncopied entry compiles, so the pass is not a blind spot.
    errors, bbl, dropped = _compile_with_bib(tmp_path, _ZOTERO, figure_bearing)
    assert errors == [], f"{errors[:10]} (packages dropped as not installed: {dropped})"
    assert "\\bibitem" in bbl and "PFAS" in bbl and "Zotero" not in bbl


@needs_tex
def test_t1_only_characters_are_exactly_those_ot1_cannot_typeset(tmp_path):
    # The package gate fails a manuscript that loads no T1 only on these (an author main.tex
    # may run in OT1): pin the set by compiling every typesettable character in OT1.
    from sci_adk.render.bib_latex import T1_ONLY_CHARS

    accepted = [chr(c) for c in range(0x80, sys.maxunicode + 1) if typesettable(chr(c))]
    items = accepted + ["{\\k{a}}"]
    preamble = [r"\documentclass{article}", r"\usepackage[utf8]{inputenc}"]
    first = len(preamble) + 2
    lines = preamble + [r"\begin{document}"] + [f"{x}\\par" for x in items] + [r"\end{document}"]
    (tmp_path / "ot1.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _run(["pdflatex", "-interaction=nonstopmode", "ot1.tex"], tmp_path)
    log = (tmp_path / "ot1.log").read_text(encoding="utf-8", errors="replace")
    failing = {items[n - first] for n in map(int, re.findall(r"^l\.(\d+)", log, re.M))
               if 0 <= n - first < len(items)}
    assert failing == set(T1_ONLY_CHARS) | {"{\\k{a}}"}


# --- final-review regressions (2026-10-10) ---

_ZOTERO_EXTRA = (
    "@article{zot2020,\n"
    "  title = {A study},\n"
    "  shorttitle = {R&D α_x #},\n"
    "  urldate = {2020-01-01},\n"
    "  language = {é ȩ},\n"
    "  author = {Doe, Jane},\n"
    "  journal = {J},\n"
    "  year = {2020}\n"
    "}\n"
)


def test_zotero_shorttitle_urldate_language_are_unprinted():
    """plainnat prints none of shorttitle/urldate/language (measured), so an author bib that
    compiles must not fail on them, and the copy leaves them as they are."""
    from sci_adk.render.bib_latex import latex_safe_bib
    from sci_adk.render.pkgreqs_checks import bib_latex_safety_problems

    assert bib_latex_safety_problems(_ZOTERO_EXTRA) == []
    copy = latex_safe_bib(_ZOTERO_EXTRA)
    assert "shorttitle = {R&D α_x #}" in copy
    assert "language = {é ȩ}" in copy


_STRING_MONTH = (
    '@string{june = "Juni"}\n'
    "@article{de2001,\n"
    "  title = {Titel},\n"
    "  author = {Müller, Hans},\n"
    "  journal = {Z},\n"
    "  month = june,\n"
    "  year = {2001}\n"
    "}\n"
)


def test_month_macro_defined_by_string_is_left_alone():
    """A bib that defines its own month macro keeps it: the rewrite only fixes names BibTeX
    would leave undefined."""
    from sci_adk.render.bib_latex import latex_safe_bib, undefined_month_tokens

    assert "month = june," in latex_safe_bib(_STRING_MONTH)
    assert undefined_month_tokens(_STRING_MONTH) == []
