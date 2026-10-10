"""
Declared numbers: what the trial's paper session still had to work around.

  6a. A checksum split with ``\\allowbreak`` whose LAST piece is short
      (``\\texttt{4fa76e47b3048258}\\allowbreak\\texttt{7}``) left that piece as a number
      literal: pieces shorter than four characters never joined a chain. A short final
      piece now joins when the piece before it is hex-only and at least eight characters
      long.
  6b. ``numbers draft`` proposed the ``256`` of the algorithm name ``SHA-256`` and the
      ``005`` of the file name ``a06-005.xls`` as quantities (candidates: recorded counts
      that happen to equal 256 or 5). DECISION: the tokenizer is unchanged (``find_literals``
      is the one reading every numbers.json was written against; dropping literals would
      turn declared entries stale), and the draft helper proposes such a literal as an
      identifier -- a literal glued by a hyphen to a capitalised name (``SHA-256``) or to a
      code holding a digit (``a06-005``), or ending a file name (``x-2.csv``). When the same
      text is also a quantity elsewhere in the document, the identifier entry carries the
      name as its context and the quantity keeps its own proposal.
  7.  ``verify`` printed both "numbers[N] ... matches no number" and "identifier ...
      listed, not checked" for the same stale identifier entry. A stale entry is no longer
      listed as an identifier, and the stale line says it is a leftover that can be
      deleted.
"""

from __future__ import annotations

import json

from sci_adk.core.numbers import NumberList
from sci_adk.render.number_checks import (
    NumberRecord,
    coverage_problems,
    identifier_listing,
    number_list_checks,
    resolution_problems,
    stale_entries,
)
from sci_adk.render.number_draft import propose_numbers
from sci_adk.render.number_literals import find_literals
from tests.test_numbers_draft import _ev


def texts(tex: str) -> list[str]:
    return [lit.text for lit in find_literals(tex, "si.tex")]


# -- 6a. a short last piece of a split checksum --------------------------------------------


def test_a_short_last_piece_of_a_split_checksum_is_part_of_it():
    assert texts(r"SHA-256 \texttt{4fa76e47b3048258}\allowbreak\texttt{7}.") == ["256"]
    assert texts(r"\texttt{4fa76e47b3048258}\allowbreak 7 rows") == []


def test_a_short_piece_joins_only_after_a_long_hex_piece():
    # seven characters before it: too short a piece to vouch for a checksum
    assert texts(r"\texttt{4fa76e4}\allowbreak\texttt{7}") == ["7"]
    # a short hex word before a number is still two words
    assert texts(r"\texttt{abc}\allowbreak\texttt{7}") == ["7"]
    # digits only: the joined run is no checksum, so both stay numbers
    assert texts(r"\texttt{12345678}\allowbreak\texttt{9}") == ["12345678", "9"]
    # a space is not a join
    assert texts(r"\texttt{4fa76e47b3048258} 7 rows") == ["7"]


def test_only_the_last_piece_may_be_short():
    # after a short piece the chain ends: the next long piece is judged on its own
    tex = r"\texttt{4fa76e47b3048258}\allowbreak\texttt{7}\allowbreak\texttt{12345678}"
    assert texts(tex) == ["12345678"]


# -- 6b. names and file names are proposed as identifiers -----------------------------------

RECORD = NumberRecord(
    spec_json={"id": "sp-x"},
    evidence=[_ev("evi-n", point=256.0, finding=json.dumps({"summary": "s", "n": 5,
                                                              "k": 2}))],
)


def _proposals(tex: str) -> tuple[list[dict], dict]:
    draft, summary = propose_numbers({"draft.tex": tex}, RECORD, "sp-x")
    return draft["numbers"], summary


def test_an_algorithm_name_and_a_file_name_segment_are_proposed_as_identifiers():
    entries, summary = _proposals(
        "The file a06-005.xls (DOI 10.1139/a06-005) has SHA-256 checksum d5f642bd.")
    by = {e["text"]: e for e in entries}
    assert by["005"] == {"text": "005", "document": "draft.tex", "role": "identifier"}
    assert by["256"] == {"text": "256", "document": "draft.tex", "role": "identifier"}
    assert summary["identifier"] == 2


def test_a_text_that_is_also_a_quantity_keeps_its_proposal_beside_the_named_one():
    tex = "We kept 256 chemicals; the file has SHA-256 checksum d5f642bd."
    entries, _ = _proposals(tex)
    assert [e for e in entries if e["text"] == "256"] == [
        {"text": "256", "document": "draft.tex", "source": {"evidence": "evi-n",
                                                             "field": "point"}},
        {"text": "256", "document": "draft.tex", "role": "identifier",
         "context": "SHA-256"},
    ]
    numbers = NumberList.model_validate({"spec_id": "sp-x", "numbers": entries})
    assert coverage_problems(numbers, {"draft.tex": tex}) == []
    assert resolution_problems(numbers, RECORD) == []


def test_a_file_name_ending_in_a_number_is_an_identifier():
    entries, _ = _proposals("Values were read from table-2.csv.")
    assert entries == [{"text": "2", "document": "draft.tex", "role": "identifier"}]


def test_a_lower_case_word_glued_by_a_hyphen_is_still_a_quantity():
    # "criterion-5" names criterion 5: a number the record may hold, proposed as before
    entries, _ = _proposals("Records passing criterion-5 were kept.")
    assert entries == [{"text": "5", "document": "draft.tex",
                        "source": {"evidence": "evi-n", "field": "finding.n"}}]


# -- 7. a stale identifier entry is reported once, as a leftover ----------------------------


def _numbers(*entries: dict) -> NumberList:
    return NumberList.model_validate({"spec_id": "sp-x", "numbers": list(entries)})


def test_a_stale_identifier_is_not_also_listed_as_an_identifier():
    docs = {"draft.tex": "Registry number 17109-49-8."}
    numbers = _numbers({"text": "17109-49-8", "role": "identifier"},
                       {"text": "7.77", "role": "identifier"})
    _problems, advisory = number_list_checks(numbers, docs, RECORD)
    about_stale = [line for line in advisory if "7.77" in line]
    assert len(about_stale) == 1, advisory
    assert "matches no number" in about_stale[0]
    assert any("identifier 17109-49-8" in line for line in advisory)


def test_the_stale_line_says_the_entry_is_a_leftover_that_can_be_deleted():
    (line,) = stale_entries(_numbers({"text": "7.77", "role": "identifier"}),
                            {"draft.tex": "nothing here"})
    assert "leftover" in line and "delete" in line


def test_identifier_listing_without_documents_lists_every_identifier():
    numbers = _numbers({"text": "7.77", "role": "identifier"})
    assert len(identifier_listing(numbers)) == 1
    assert identifier_listing(numbers, {"draft.tex": "nothing here"}) == []
