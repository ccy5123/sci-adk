"""
The second-generation number tokenizer (design/declared-numbers.md §4.2).

It FINDS the number literals in a rendered manuscript and never judges them: whether a
literal is a count, a year, a page or a registry number is declared in ``numbers.json``,
not guessed here. What it keeps are the exemptions LaTeX itself defines (comments, the
arguments of \\ref / \\cite / \\label / \\includegraphics ..., the verbatim spans, macro
definitions) and a few lexical rules that do not depend on the field:

  - digits joined by hyphens with no spaces are ONE literal (17109-49-8, 2026-10-08);
  - an ISO-8601 date-time is ONE literal (2026-10-08T10:03:39Z), and a hex digest none;
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
    is_date_time,
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


# --------------------------------------------------------------------------- #
# checksums and other hex digests (the strings of run SPEC-BCFKOW-001)
# --------------------------------------------------------------------------- #

DRAFT_DECRYPTED = (
    "The file is encrypted with Excel's built-in default key and was decrypted with "
    "msoffcrypto-tool 6.0.0 before reading; the decrypted copy, which all steps read, has "
    "SHA-256 1081e637f6bd39f9ba86d0e005cf657ea054ad302fd57e5d2e8d6841fd95c461. Records "
    "were kept in this order")
DRAFT_ORIGINAL = (
    "received on 2026-10-08 (SHA-256 "
    "d5f642bdaf3c69fa1cf5de3679a5f6d5ed920d8ca68cc8bd86aaece87dc7f8f0); it holds 6973 "
    "records for 842 chemicals.")
DRAFT_OPERA = (
    r"(OPERA data release v2.9.5, file LogP\_QR.sdf, SHA-256 "
    "de50a1eb020ae42f7f89f8cb7dd73987048e80f30ef32eeaf376451cb832e489, from "
    r"OPERA\_Data.zip, SHA-256 "
    "9dc5d6387201df0f66e9472b034aeaa09ef7a47f705b9b5f50d7c9af8a1aadc3, downloaded "
    "2026-10-08 from github.com/kmansouri/OPERA); this applied to 5 chemicals.")
SI_CHECKSUMS = (
    r"The checksums of the data file (original \texttt{d5f642bdaf3c69fa}\allowbreak"
    r"\texttt{1cf5de3679a5f6d5}\allowbreak\texttt{ed920d8ca68cc8bd}\allowbreak"
    r"\texttt{86aaece87dc7f8f0}, decrypted copy \texttt{1081e637f6bd39f9}\allowbreak"
    r"\texttt{ba86d0e005cf657e}\allowbreak\texttt{a054ad302fd57e5d}\allowbreak"
    r"\texttt{2e8d6841fd95c461}) were recorded at")


def test_a_checksum_in_prose_is_not_a_number():
    # It used to read as 1081e637 (10^640, beyond a float) and as 9 -- fragments of a code.
    assert texts(DRAFT_DECRYPTED) == ["6.0.0", "256"]
    assert texts(DRAFT_ORIGINAL) == ["2026-10-08", "256", "6973", "842"]
    assert texts(DRAFT_OPERA) == ["256", "256", "2026-10-08", "5"]


def test_a_checksum_in_spec_text_is_not_a_number():
    assert [lit.text for lit in find_text_literals(
        "decrypted copy SHA-256 1081e637f6bd39f9ba86d0e005cf657e")] == ["256"]
    assert parse_literal_text("1081e637f6bd39f9") is None


def test_a_checksum_split_into_typewriter_pieces_is_not_a_number():
    # The SI writes each checksum as \texttt pieces joined by \allowbreak.
    assert texts(SI_CHECKSUMS) == []


def test_a_piece_of_a_split_checksum_that_looks_like_a_number_is_part_of_it():
    # Alone, 1234567e89012345 and 1081e637 read as numbers; joined to their neighbours by
    # \allowbreak they are pieces of one checksum. Plain pieces join the same way.
    assert texts(r"\texttt{a16a50d52c886585}\allowbreak\texttt{1234567e89012345}") == []
    assert texts(r"1081e637\allowbreak f6bd39f9ba86d0e0") == []
    assert texts(r"\texttt{1081e637\allowbreak f6bd39f9}") == []
    # A space is not a join: two words, and the second is a number.
    assert texts("3fa7c9b0e1 1234567") == ["1234567"]


@pytest.mark.parametrize("tex,expected", [
    ("code 3fa7c9b0e1 here", []),             # >= 7 hex characters, a digit and a letter
    ("lot 12ab34c", []),                      # exactly seven
    ("lot 12ab34", ["12"]),                   # six: too short to be a digest
    ("1234567 rows", ["1234567"]),            # no letter: a number
    ("12345e6 m", ["12345e6"]),               # digits, e, digits: an exponent
    ("fragment 1081e637", ["1081e637"]),      # the same shape (value: see below)
    ("lot 12ab34cg", ["12"]),                 # g is not a hex character
    ("1081E637F6BD39F9", []),                 # an upper-case digest
    ("1081e637F6bd39F9", ["1081e637"]),       # mixed case is not one digest
])
def test_digest_rule_boundaries(tex, expected):
    assert texts(tex) == expected


def test_a_non_finite_literal_has_no_value():
    (lit,) = find_literals("a lone fragment 1081e637 here")
    assert lit.text == "1081e637"
    assert lit.value is None and lit.decimals is None
    assert parse_literal_text("1e999").value is None


def test_typewriter_text_is_prose():
    # \texttt is a font, not verbatim (it needs \_ like any prose): a seed or a size
    # written as code is still a number the paper states. File names yield nothing.
    tex = (r"50 positions are drawn without replacement with "
           r"\texttt{numpy.random.default\_rng(20261008).choice(N, size=50, replace=False)}.")
    assert texts(tex) == ["50", "20261008", "50"]
    assert texts(r"produced by the script \texttt{s1\_select\_records.py}") == []
    # A date-time written as code is one literal (see the date-time tests below).
    assert texts(r"recorded at \texttt{2026-10-08T14:48:59Z}") == ["2026-10-08T14:48:59Z"]


def test_a_version_with_a_leading_letter_is_not_a_literal():
    # "v2.9.5" continues the word "v2", so no literal starts in it (the checks, the draft
    # helper and the pattern audit all ignore it); written bare it is one dotted literal.
    assert texts("OPERA data release v2.9.5") == []
    (lit,) = find_literals("OPERA data release 2.9.5")
    assert lit.text == "2.9.5" and lit.value is None


# --------------------------------------------------------------------------- #
# the digest rule leaves scientific notation alone
# --------------------------------------------------------------------------- #
# A mantissa of seven or more digits ends in a run like "2345678e" (digits, then the
# exponent marker), which has a digit, a hex letter and one case -- the shape of a digest.
# It is the tail of a number when it follows a decimal point, or the head of one when an
# exponent follows it, and then it is not a digest.

@pytest.mark.parametrize("number", [
    "1.2345678e-3", "4.8765432e-05", "1.23456789E+10", "2.7182818e+2", "0.1234567e-2",
    "2345678e-3",
])
def test_scientific_notation_with_a_long_mantissa_is_one_literal(number):
    (lit,) = find_literals(f"the rate was {number} per day")
    assert lit.text == number
    assert lit.value == pytest.approx(float(number))
    (plain,) = find_text_literals(f"rate {number}")
    assert plain.text == number
    assert parse_literal_text(number).value == pytest.approx(float(number))


def test_a_long_mantissa_keeps_its_printed_precision():
    (lit,) = find_literals("1.2345678e-3")
    assert lit.decimals == 10


def test_a_digest_ending_in_e_before_a_hyphen_is_still_a_digest():
    # Only a run of digits then e/E is an exponent's mantissa; "3fa7c9b0e" is a code.
    assert texts("lot 3fa7c9b0e-3 shipped") == ["3"]


# --------------------------------------------------------------------------- #
# ISO-8601 date-times (the strings of run SPEC-BCFKOW-001's si.tex)
# --------------------------------------------------------------------------- #

SI_PROTOCOL_V1 = (
    r"Version 1 of the protocol was created at \texttt{2026-10-08T10:03:39Z}; its file has "
    r"SHA-256 \texttt{4fa76e47b3048258}\allowbreak\texttt{1e1fe74dc4d9b77c}\allowbreak"
    r"\texttt{a16a50d52c886585}\allowbreak\texttt{a9b399c5a767fa66}. The amendment (next "
    r"section) stores this checksum for the version it replaced.")
SI_AMENDMENT = (
    r"The amendment was recorded at \texttt{2026-10-08T14:05:17Z}; its file has SHA-256 "
    r"\texttt{9035bfa84e0e78f3}\allowbreak\texttt{4973036e14679fff}\allowbreak"
    r"\texttt{89e7fa3e4f31336a}\allowbreak\texttt{1e8b6bc7e2c4cbb4}.")
SI_RECORD_TIMES = (
    r"The checksums of the data file (original \texttt{d5f642bdaf3c69fa}\allowbreak"
    r"\texttt{1cf5de3679a5f6d5}\allowbreak\texttt{ed920d8ca68cc8bd}\allowbreak"
    r"\texttt{86aaece87dc7f8f0}, decrypted copy \texttt{1081e637f6bd39f9}\allowbreak"
    r"\texttt{ba86d0e005cf657e}\allowbreak\texttt{a054ad302fd57e5d}\allowbreak"
    r"\texttt{2e8d6841fd95c461}) were recorded at \texttt{2026-10-08T14:48:59Z}. The first "
    r"record selection on that file was recorded at \texttt{2026-10-08T14:49:19Z}, after "
    r"the amendment. The time-stamped description of that selection, a file with SHA-256 "
    r"\texttt{0aa8cb6baaad8231}\allowbreak\texttt{060ed879ceb7b931}\allowbreak"
    r"\texttt{7113302f4e1d7686}\allowbreak\texttt{4bc229fc3497500e}, was produced by the "
    r"script \texttt{s1\_select\_records.py} (SHA-256 \texttt{a5a9cab9c96805e3}\allowbreak"
    r"\texttt{1e27db0a0e902900}\allowbreak\texttt{b328d2226aa93ff6}\allowbreak"
    r"\texttt{87457bfccadcb68b}) from the decrypted copy. The sample for the code was "
    r"recorded at \texttt{2026-10-08T16:53:12Z} and the slope fit at "
    r"\texttt{2026-10-08T16:53:36Z}.")


def test_a_date_time_in_the_si_is_one_literal():
    # It used to split into 2026-10-08, 03, 39 -- and the draft helper matched 12 and 36
    # to unrelated recorded counts.
    assert texts(SI_PROTOCOL_V1) == ["1", "2026-10-08T10:03:39Z", "256"]
    assert texts(SI_AMENDMENT) == ["2026-10-08T14:05:17Z", "256"]
    assert texts(SI_RECORD_TIMES) == [
        "2026-10-08T14:48:59Z", "2026-10-08T14:49:19Z", "256", "256",
        "2026-10-08T16:53:12Z", "2026-10-08T16:53:36Z"]


@pytest.mark.parametrize("stamp", [
    "2026-10-08T10:03:39Z",
    "2026-10-08T10:03:39",
    "2026-10-08T10:03",
    "2026-10-08T10:03Z",
    "2026-10-08T10:03:39.125Z",
    "2026-10-08T10:03:39+09:00",
    "2026-10-08T10:03:39-05:00",
    "2026-10-08T10:03:39+09",
])
def test_every_iso_date_time_form_is_one_literal_with_no_value(stamp):
    (lit,) = find_literals(f"recorded at {stamp}, then 341 rows", "si.tex")[:1]
    assert lit.text == stamp
    assert lit.value is None and lit.decimals is None
    assert [x.text for x in find_literals(f"at {stamp}, then 341 rows")] == [stamp, "341"]
    assert [x.text for x in find_text_literals(f"created_at {stamp}")] == [stamp]
    assert parse_literal_text(stamp).text == stamp


def test_a_date_time_glued_to_a_word_is_not_one_and_reads_as_before():
    assert texts("tag 2026-10-08T10:03:39Zabc here") == ["2026-10-08", "03", "39"]


def test_a_bare_date_stays_one_joined_literal():
    assert texts("received on 2026-10-08 from the authors") == ["2026-10-08"]
    assert texts(r"received on \texttt{2026-10-08} and 2026-10-09") == [
        "2026-10-08", "2026-10-09"]


def test_is_date_time_names_the_literals_that_are_date_times():
    assert is_date_time("2026-10-08T10:03:39Z")
    assert is_date_time("2026-10-08T10:03:39.125+09:00")
    assert not is_date_time("2026-10-08")
    assert not is_date_time("0.769")
    assert not is_date_time("10:03")


# --------------------------------------------------------------------------- #
# \allowbreak chains: only typewriter-length pieces join
# --------------------------------------------------------------------------- #

def test_a_short_hex_word_does_not_pull_a_number_into_a_digest():
    # "abc" + "1234567" read as one run looks like a ten-character digest; "abc" is a
    # word and 1234567 a number. A piece shorter than four characters never joins a chain.
    assert texts(r"\texttt{abc}\allowbreak 1234567") == ["1234567"]
    assert texts(r"\texttt{abc}\allowbreak\texttt{1234567}") == ["1234567"]
    assert texts(r"1234567\allowbreak\texttt{ab}") == ["1234567"]


def test_a_piece_beside_a_short_piece_is_judged_on_its_own():
    # A short LAST piece after a hex piece of eight or more characters is the tail of the
    # split digest (tests/test_numbers_names_and_stale.py); after a shorter piece, or before
    # another piece, a short piece is read as it stands.
    assert texts(r"\texttt{1081e637f6bd39f9}\allowbreak\texttt{12}") == []
    assert texts(r"\texttt{4fa76e4}\allowbreak\texttt{12}") == ["12"]
    assert texts(r"\texttt{1234567}\allowbreak\texttt{ab}\allowbreak\texttt{89abcdef}") == [
        "1234567"]
