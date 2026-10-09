"""
The checks over a declared number list (design/declared-numbers.md §4.3).

  1. Coverage (FAIL): every literal in draft.tex / si.tex is covered by an entry with the
     same text and document (and inside its ``context``, when the entry has one).
  2. Resolution (FAIL): every source exists, and the value it resolves to, rounded to the
     literal's printed precision, equals the literal. A derived entry is recomputed from
     its operands; a citation year must equal the bib field.
  3. Stale entries (ADVISORY): an entry whose text no longer occurs in its document.
  4. Identifiers (ADVISORY): every identifier entry is listed, so each exemption is seen.

Nothing in the list is trusted on its own: a source must resolve to the record, and only
identifier entries skip the record -- visibly.
"""

from __future__ import annotations

import json

import pytest

from sci_adk.core.evidence import EvidenceItem, EvidenceKind, Provenance, Result
from sci_adk.core.numbers import NumberList
from sci_adk.render.number_checks import (
    NumberRecord,
    coverage_problems,
    identifier_listing,
    number_list_checks,
    printed_match,
    resolution_problems,
    stale_entries,
)
from sci_adk.render.number_literals import parse_literal_text

SPEC = {
    "id": "sp-x",
    "hypotheses": [{
        "id": "H1",
        "statement": "The slope lies between 0.7 and 1.0 for log Kow 1 to 6.",
        "decision_rule": {
            "kind": "threshold",
            "expression": "the 95% interval is reported beside the estimate",
            "params": {"value": 0.5, "band_lower": 0.7, "statistic": "slope"},
        },
    }],
    "method": {"approaches": ["exclude chemicals with 3 or more halogens",
                              "permute with seed 20261009",
                              "structures retrieved 2026-10-08"]},
}


def _ev(ev_id: str, **result) -> EvidenceItem:
    kind = "quantitative" if any(k != "finding" for k in result) else "qualitative"
    return EvidenceItem(
        id=ev_id, spec_id="sp-x", kind=EvidenceKind.OBSERVATION,
        provenance=Provenance(code_ref="x"), result=Result(type=kind, **result),
        bears_on=[],
    )


EVIDENCE = [
    _ev("evi-fit", point=0.068932, effect_size=0.768932,
        ci=[0.7123415910062878, 0.8255224224484004],
        finding=json.dumps({"summary": "H1 primary fit", "n_chemicals": 341,
                            "intercept": -0.806328, "slope_prev": 0.612,
                            "frac_ordered": 0.6944, "zero": 0, "label": "x",
                            "counts": {"total": 404}})),
    _ev("evi-prose", finding="Input: 6973 records for 842 chemicals."),
]
RECORD = NumberRecord(spec_json=SPEC, evidence=EVIDENCE, bib_years={"Arnot2006": "2006"})


def _numbers(*entries: dict) -> NumberList:
    return NumberList.model_validate({"spec_id": "sp-x", "numbers": list(entries)})


def ev(field: str, evidence: str = "evi-fit") -> dict:
    return {"evidence": evidence, "field": field}


# --------------------------------------------------------------------------- #
# printed precision
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value,text,ok", [
    (0.768932, "0.769", True),
    (0.768932, "0.77", True),
    (0.768932, "0.768", False),
    (341, "341", True),
    (342, "341", False),
    (340.6, "341", True),     # an integer literal is a rounding to 0 decimals
    (6973, "6,973", True),
    (-0.806328, "-0.806", True),
    (0.806328, "-0.806", False),
    (3.4e-12, "1.2e-12", False),  # tiny values are not swallowed by an absolute slack
    (1.24e-12, "1.2e-12", True),
])
def test_printed_match(value, text, ok):
    assert printed_match(value, parse_literal_text(text)) is ok


# --------------------------------------------------------------------------- #
# 1. coverage
# --------------------------------------------------------------------------- #

def test_an_undeclared_literal_fails_coverage_naming_it():
    docs = {"draft.tex": "The slope over these chemicals was 0.769 here."}
    (problem,) = coverage_problems(_numbers(), docs)
    assert "0.769" in problem and "draft.tex" in problem
    assert "chemicals was 0.769" in problem      # a snippet locates it
    assert "numbers.json" in problem             # and the remedy names the file


def test_a_declared_literal_is_covered():
    docs = {"draft.tex": "The slope was 0.769."}
    assert coverage_problems(_numbers({"text": "0.769", "source": ev("effect_size")}),
                             docs) == []


def test_an_entry_covers_only_its_own_document():
    docs = {"draft.tex": "The slope was 0.769.", "si.tex": "No numbers here."}
    numbers = _numbers({"text": "0.769", "document": "si.tex",
                        "source": ev("effect_size")})
    assert len(coverage_problems(numbers, docs)) == 1


def test_repeated_occurrences_are_reported_once_per_text():
    docs = {"draft.tex": "First 0.42, then 0.42 again, then 0.42."}
    (problem,) = coverage_problems(_numbers(), docs)
    assert "3" in problem  # the occurrence count


def test_context_locates_the_occurrences_an_entry_covers():
    docs = {"draft.tex": ("Over the 50 sampled chemicals the code ranked well, and the "
                          "mean residual was 0.12 for the 50 with log Kow from 1 to 2.")}
    sampled = {"text": "50", "context": "the 50 sampled", "source": ev("finding.zero")}
    low = {"text": "50", "context": "the 50 with log Kow", "role": "identifier"}
    covering = _numbers(sampled, low, {"text": "0.12", "role": "identifier"},
                        {"text": "1", "role": "identifier"},
                        {"text": "2", "role": "identifier"})
    assert coverage_problems(covering, docs) == []

    partial = _numbers(sampled, {"text": "0.12", "role": "identifier"},
                       {"text": "1", "role": "identifier"},
                       {"text": "2", "role": "identifier"})
    (problem,) = coverage_problems(partial, docs)
    assert "50" in problem and "50 with log Kow" in problem


def test_context_tolerates_line_wrapping_and_may_be_quoted_from_the_prose():
    docs = {"draft.tex": "the fit had R$^2$ =\n  0.678, while 0.678 elsewhere is a rate"}
    numbers = _numbers({"text": "0.678", "context": "R² = 0.678",
                        "role": "identifier"})
    (problem,) = coverage_problems(numbers, docs)
    assert "elsewhere" in problem   # only the second occurrence is uncovered


def test_minus_sign_variants_match_one_text():
    docs = {"draft.tex": "intercept -0.806"}
    numbers = _numbers({"text": "−0.806", "source": ev("finding.intercept")})
    assert coverage_problems(numbers, docs) == []


# --------------------------------------------------------------------------- #
# 2. resolution
# --------------------------------------------------------------------------- #

def _problems(*entries: dict) -> list[str]:
    return resolution_problems(_numbers(*entries), RECORD)


def test_recorded_values_resolve_at_printed_precision():
    assert _problems(
        {"text": "0.769", "source": ev("effect_size")},
        {"text": "0.77", "source": ev("effect_size")},
        {"text": "0.069", "source": ev("point")},
        {"text": "0.712", "source": ev("ci[0]")},
        {"text": "0.826", "source": ev("ci[1]")},
        {"text": "341", "source": ev("finding.n_chemicals")},
        {"text": "404", "source": ev("finding.counts.total")},
        {"text": "-0.806", "source": ev("finding.intercept")},
    ) == []


def test_a_wrong_printed_value_fails_naming_the_recorded_one():
    (problem,) = _problems({"text": "0.768", "source": ev("effect_size")})
    assert "numbers[0]" in problem and "0.768" in problem
    assert "0.768932" in problem and "evi-fit" in problem


def test_integers_must_match_exactly_at_zero_decimals():
    (problem,) = _problems({"text": "342", "source": ev("finding.n_chemicals")})
    assert "342" in problem


@pytest.mark.parametrize("source,needle", [
    ({"evidence": "evi-missing", "field": "point"}, "evi-missing"),
    ({"evidence": "evi-fit", "field": "p_value"}, "p_value"),
    ({"evidence": "evi-prose", "field": "finding.n"}, "JSON"),
    ({"evidence": "evi-fit", "field": "finding.absent"}, "absent"),
    ({"evidence": "evi-fit", "field": "finding.label"}, "number"),
    ({"spec": "hypotheses[0].decision_rule.params.missing"}, "missing"),
    ({"spec": "hypotheses[0].decision_rule.params.statistic"}, "number"),
])
def test_a_source_that_does_not_resolve_fails(source, needle):
    (problem,) = _problems({"text": "1", "source": source})
    assert "numbers[0]" in problem and needle in problem


def test_spec_numeric_field():
    assert _problems({"text": "0.5",
                      "source": {"spec": "hypotheses[0].decision_rule.params.value"}}) == []


def test_spec_text_literal_must_occur_in_the_named_field():
    assert _problems(
        {"text": "95", "source": {"spec_text": "hypotheses[0].decision_rule.expression"}},
        {"text": "3", "source": {"spec_text": "method.approaches[0]"}},
        {"text": "20261009", "source": {"spec_text": "method.approaches[1]"}},
    ) == []
    # "3" occurs in the Spec -- but not in the field this entry names.
    (problem,) = _problems({"text": "3", "source": {"spec_text": "hypotheses[0].statement"}})
    assert "numbers[0]" in problem and "hypotheses[0].statement" in problem


def test_spec_text_must_name_a_text_field():
    (problem,) = _problems({"text": "3", "source": {"spec_text": "method.approaches"}})
    assert "numbers[0]" in problem and "text" in problem


def test_citation_year_must_equal_the_bib_field():
    assert _problems({"text": "2006", "source": {"bib": "Arnot2006", "field": "year"}}) == []
    (wrong,) = _problems({"text": "2005", "source": {"bib": "Arnot2006", "field": "year"}})
    assert "2006" in wrong
    (unknown,) = _problems({"text": "2006", "source": {"bib": "Nobody2006", "field": "year"}})
    assert "Nobody2006" in unknown
    no_bib = NumberRecord(spec_json=SPEC, evidence=EVIDENCE, bib_years=None)
    (missing,) = resolution_problems(
        _numbers({"text": "2006", "source": {"bib": "Arnot2006", "field": "year"}}), no_bib)
    assert "references.bib" in missing


def test_derived_entries_are_recomputed_from_their_operands():
    assert _problems(
        {"text": "69.4", "formula": "100 * a", "operands": {"a": ev("finding.frac_ordered")}},
        {"text": "0.157", "formula": "a - b",
         "operands": {"a": ev("effect_size"), "b": ev("finding.slope_prev")}},
    ) == []
    (problem,) = _problems({"text": "69.5", "formula": "100 * a",
                            "operands": {"a": ev("finding.frac_ordered")}})
    assert "numbers[0]" in problem and "69.44" in problem


def test_a_derived_division_by_zero_is_a_problem():
    (problem,) = _problems({"text": "1", "formula": "a / b",
                            "operands": {"a": ev("effect_size"), "b": ev("finding.zero")}})
    assert "numbers[0]" in problem


def test_an_unresolvable_operand_is_a_problem():
    (problem,) = _problems({"text": "1", "formula": "a",
                            "operands": {"a": {"evidence": "evi-x", "field": "point"}}})
    assert "evi-x" in problem


def test_identifier_entries_skip_resolution():
    assert _problems({"text": "17109-49-8", "role": "identifier"}) == []


def test_a_hyphen_joined_literal_is_not_one_number():
    (problem,) = _problems({"text": "17109-49-8", "source": ev("point")})
    assert "identifier" in problem
    # ...but it can still be a literal written in a Spec text field.
    assert _problems({"text": "2026-10-08",
                      "source": {"spec_text": "method.approaches[2]"}}) == []


def test_entry_text_must_be_a_literal_as_the_tokenizer_reads_it():
    (problem,) = _problems({"text": "95%", "role": "identifier"})
    assert "numbers[0]" in problem and "95" in problem


# --------------------------------------------------------------------------- #
# 3. stale entries + 4. identifiers (advisory)
# --------------------------------------------------------------------------- #

def test_an_entry_no_longer_in_its_document_is_stale():
    docs = {"draft.tex": "The slope was 0.769."}
    numbers = _numbers({"text": "0.769", "source": ev("effect_size")},
                       {"text": "0.777", "source": ev("effect_size")})
    (line,) = stale_entries(numbers, docs)
    assert "0.777" in line and "draft.tex" in line


def test_an_entry_whose_context_matches_nothing_is_stale():
    docs = {"draft.tex": "The slope was 0.769."}
    numbers = _numbers({"text": "0.769", "context": "slope is 0.769",
                        "source": ev("effect_size")})
    (line,) = stale_entries(numbers, docs)
    assert "0.769" in line


def test_entries_for_an_absent_document_are_reported_once():
    numbers = _numbers({"text": "1", "document": "si.tex", "role": "identifier"},
                       {"text": "2", "document": "si.tex", "role": "identifier"})
    (line,) = stale_entries(numbers, {"draft.tex": "nothing"})
    assert "si.tex" in line and "2" in line


def test_every_identifier_is_listed():
    numbers = _numbers(
        {"text": "17109-49-8", "role": "identifier", "context": "CAS RN 17109-49-8"},
        {"text": "5", "role": "identifier", "document": "si.tex"},
        {"text": "0.769", "source": ev("effect_size")},
    )
    lines = identifier_listing(numbers)
    assert len(lines) == 2
    assert any("17109-49-8" in x and "draft.tex" in x and "CAS RN 17109-49-8" in x
               for x in lines)
    assert any("si.tex" in x for x in lines)


# --------------------------------------------------------------------------- #
# the entry point
# --------------------------------------------------------------------------- #

def test_number_list_checks_splits_failures_from_advisories():
    docs = {"draft.tex": "Slope 0.769 over 341 chemicals (CAS RN 17109-49-8); also 0.42."}
    numbers = _numbers(
        {"text": "0.769", "source": ev("effect_size")},
        {"text": "341", "source": ev("finding.n_chemicals")},
        {"text": "17109-49-8", "role": "identifier"},
        {"text": "9.99", "role": "identifier"},
    )
    problems, advisory = number_list_checks(numbers, docs, RECORD)
    assert len(problems) == 1 and "0.42" in problems[0]
    assert any("9.99" in x for x in advisory)          # stale
    assert any("17109-49-8" in x for x in advisory)    # identifier listing


def test_a_faithful_list_is_silent_except_for_identifiers():
    docs = {"draft.tex": "Slope 0.769 over 341 chemicals."}
    numbers = _numbers({"text": "0.769", "source": ev("effect_size")},
                       {"text": "341", "source": ev("finding.n_chemicals")})
    assert number_list_checks(numbers, docs, RECORD) == ([], [])
