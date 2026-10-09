"""
The second-generation number tokenizer (design/declared-numbers.md §4.2).

It FINDS the number literals in a rendered manuscript and never judges them: whether a
literal is a count, a year, a page or a registry number is declared in ``numbers.json``,
not guessed here. What it keeps are the exemptions LaTeX itself defines (comments, the
arguments of \\ref / \\cite / \\label / \\includegraphics ..., the verbatim spans, macro
definitions) and a few lexical rules that do not depend on the field:

  - digits joined by hyphens with no spaces are ONE literal (17109-49-8, 2026-10-08);
  - an en dash / ``--`` between two numbers separates a range (the second is not negated);
  - a minus negates only when it is unary;
  - digits in a superscript or subscript are not literals; other numbers in math are;
  - ``95\\%`` is the literal 95; ``6,973`` is one literal (a thousands separator).

There is NO year / page / date / version rule: "P 47" holds the literal 47, and a
four-digit count is a literal like any other.
"""

from __future__ import annotations

import pytest

from sci_adk.render.number_literals import (
    find_literals,
    find_text_literals,
    parse_literal_text,
)


def texts(tex: str) -> list[str]:
    return [lit.text for lit in find_literals(tex, "draft.tex")]


# --------------------------------------------------------------------------- #
# plain numbers
# --------------------------------------------------------------------------- #

def test_decimal_and_integer_literals_in_source_order():
    assert texts("The slope over 341 chemicals was 0.769.") == ["341", "0.769"]


def test_a_literal_carries_its_value_document_and_position():
    tex = "The slope over these chemicals was 0.769 (fitted)."
    (lit,) = find_literals(tex, "si.tex")
    assert lit.value == pytest.approx(0.769)
    assert lit.document == "si.tex"
    assert tex[lit.start:lit.end] == "0.769"
    assert "chemicals was 0.769" in lit.snippet


def test_printed_decimals_are_recorded():
    by_text = {lit.text: lit for lit in find_literals("0.769 and 341 and -0.06 and 1.2e-3")}
    assert by_text["0.769"].decimals == 3
    assert by_text["341"].decimals == 0
    assert by_text["-0.06"].decimals == 2
    assert by_text["1.2e-3"].decimals == 4
    assert by_text["1.2e-3"].value == pytest.approx(0.0012)


def test_no_year_page_date_or_version_rules():
    # "P 47" is phosphorus and its prime, not a page; a four-digit count is a count.
    assert texts("P 47 and S 53") == ["47", "53"]
    assert texts("2393 records from 6973") == ["2393", "6973"]
    assert texts("see p. 47") == ["47"]


# --------------------------------------------------------------------------- #
# the lexical rules
# --------------------------------------------------------------------------- #

def test_hyphen_joined_digit_groups_are_one_literal():
    lits = find_literals("CAS RN 17109-49-8, retrieved 2026-10-08.")
    assert [lit.text for lit in lits] == ["17109-49-8", "2026-10-08"]
    assert all(lit.value is None for lit in lits)  # not one number


def test_en_dash_and_double_hyphen_separate_a_range():
    assert texts("0.712--0.826") == ["0.712", "0.826"]
    assert texts("0.712–0.826") == ["0.712", "0.826"]
    assert texts("5---6") == ["5", "6"]


def test_minus_negates_only_when_unary():
    assert texts("a = -0.806, b") == ["-0.806"]
    assert texts("(-0.06)") == ["-0.06"]
    assert texts("n - 2 degrees") == ["2"]
    assert texts("−0.5") == ["-0.5"]            # U+2212 MINUS SIGN
    assert texts("$-0.5$") == ["-0.5"]
    assert texts("$-$0.5") == ["-0.5"]
    by_text = {lit.text: lit for lit in find_literals("a = -0.806")}
    assert by_text["-0.806"].value == pytest.approx(-0.806)


def test_numbers_glued_to_letters_by_a_hyphen_are_literals():
    # Declared in numbers.json (an identifier, usually); `context` disambiguates.
    assert texts("criterion-5 and GPT-4") == ["5", "4"]
    assert texts("1-pentanol") == ["1"]


def test_digits_continuing_a_word_are_part_of_it():
    assert texts("log10 code of CO2") == []


def test_superscript_and_subscript_digits_are_not_literals():
    assert texts("R$^2$ = 0.678") == ["0.678"]
    assert texts("H$_2$O") == []
    assert texts("10$^-$$^3$") == ["10"]
    assert texts("$x^{12} + 3$") == ["3"]
    assert texts(r"m\textsuperscript{2} and CO\textsubscript{2}") == []


def test_other_numbers_inside_math_are_literals():
    assert texts("$p < 0.05$") == ["0.05"]
    assert texts(r"\[ y = 2.5 x \]") == ["2.5"]


@pytest.mark.parametrize("tex,expected", [
    (r"\(x^2 + 1.5\)", ["1.5"]),
    (r"$$a_{10} = 4$$", ["4"]),
    (r"\begin{equation} E = 3 m c^2 \end{equation}", ["3"]),
    (r"\begin{align*} y_1 = 0.25 \end{align*}", ["0.25"]),
    (r"$x^\alpha 2$", ["2"]),          # a command is a one-token script target
    (r"$x^ {12} 7$", ["7"]),           # spaces before the target
])
def test_every_math_delimiter_is_read_the_same_way(tex, expected):
    assert texts(tex) == expected


def test_an_unclosed_group_or_math_span_does_not_break_the_tokenizer():
    assert texts("$x^{12") == []
    assert texts(r"\(y = 3") == ["3"]
    assert texts(r"\label{fig:3") == []


def test_options_of_a_citation_are_part_of_it():
    assert texts(r"\citep[see][p.~5]{Key2} and 6") == ["6"]


def test_a_line_break_before_a_name_is_not_a_command_argument():
    # "\\" is a line break; the "label{5}" after it is text, not a \label argument.
    assert texts(r"a\\label{5}") == ["5"]


def test_an_escaped_dollar_does_not_open_math():
    assert texts(r"it costs \$5 and R$^2$ is 0.9") == ["5", "0.9"]


def test_percent_is_the_number():
    assert texts(r"the 95\% confidence interval") == ["95"]


def test_thousands_separator():
    lits = find_literals("6,973 records and 1,234,567 rows")
    assert [lit.text for lit in lits] == ["6,973", "1,234,567"]
    assert lits[0].value == 6973
    assert texts("(3,4)") == ["3", "4"]
    assert texts("1234,567") == ["1234", "567"]


def test_leading_dot_decimal_and_dotted_groups():
    (lit,) = find_literals("r = .76")
    assert lit.text == ".76" and lit.value == pytest.approx(0.76)
    (dotted,) = find_literals("RDKit 2025.09.4")
    assert dotted.text == "2025.09.4" and dotted.value is None


# --------------------------------------------------------------------------- #
# what LaTeX itself exempts
# --------------------------------------------------------------------------- #

def test_reference_citation_label_and_file_arguments_are_not_literals():
    tex = (r"\cite{Arnot2006} \citep[p.~5]{Veith1979} \ref{fig:h1} \label{tab:2} "
           r"\input{part2} \includegraphics[width=0.8\textwidth]{figures/fig1.png}")
    assert texts(tex) == []


def test_preamble_package_options_are_not_literals():
    tex = (r"\documentclass[11pt]{article}" "\n" r"\usepackage[utf8]{inputenc}" "\n"
           r"\pgfplotsset{compat=1.18}" "\n" r"\bibliography{refs2024}")
    assert texts(tex) == []


def test_verbatim_spans_comments_and_macro_definitions_are_not_literals():
    tex = (r"\texttt{s4_h1_fit.py v2} \url{https://x.org/1} \href{https://y/2}{a link} "
           r"\verb|x = 3| \newcommand{\nov}[3]{#3} % 99 is a comment")
    assert texts(tex) == []


def test_href_text_is_prose():
    assert texts(r"\href{https://y/2}{the 2 datasets}") == ["2"]


def test_novelty_ids_are_not_literals_but_its_text_is():
    assert texts(r"\novelty{result}{H2}{none of 3 studies}") == ["3"]


def test_section_titles_and_captions_are_prose():
    assert texts(r"\section{Results for 341 chemicals}") == ["341"]
    assert texts(r"\caption{The 341 chemicals.}\label{fig:a}") == ["341"]


def test_plot_coordinates_are_figure_data_not_literals():
    tex = r"\addplot[only marks] coordinates {(1.06, 0.5) (2, 3)};"
    assert texts(tex) == []


# --------------------------------------------------------------------------- #
# plain text + a single literal
# --------------------------------------------------------------------------- #

def test_plain_text_mode_reads_unicode_minus_and_en_dash():
    lits = find_text_literals("slope in [0.7, 1.0]; −1.86; 5–6")
    assert [lit.text for lit in lits] == ["0.7", "1.0", "-1.86", "5", "6"]


def test_parse_literal_text_accepts_exactly_one_literal():
    assert parse_literal_text("0.769").value == pytest.approx(0.769)
    assert parse_literal_text("−0.806").text == "-0.806"
    assert parse_literal_text("17109-49-8").value is None
    assert parse_literal_text("6,973").value == 6973
    assert parse_literal_text("95%") is None       # the literal is "95"
    assert parse_literal_text("0.7 to 1.0") is None
    assert parse_literal_text("R2") is None
