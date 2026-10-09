"""
The declared NUMBER list -- the type and its loader (design/declared-numbers.md §4.1).

``runs/<id>/numbers.json`` lists every number literal the paper states and where it comes
from. The machine never infers a number's role; the author states it, and verify checks
the statement against the record and the text. This file covers the schema: what an
entry may say, and that a malformed list fails loudly, naming the entry.
"""

from __future__ import annotations

import json

import pytest

from sci_adk.core.numbers import (
    NumberEntry,
    NumberList,
    evaluate_formula,
    formula_names,
    load_numbers,
    parse_json_path,
    walk_json,
)


def _write(tmp_path, numbers, **top):
    payload = {"spec_id": "sp-x", "numbers": numbers, **top}
    (tmp_path / "numbers.json").write_text(json.dumps(payload), encoding="utf-8")


def _error(tmp_path, numbers, **top) -> str:
    _write(tmp_path, numbers, **top)
    with pytest.raises(ValueError) as exc:
        load_numbers(tmp_path)
    return str(exc.value)


EV = {"evidence": "evi-1", "field": "effect_size"}


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def test_absent_file_means_the_run_has_not_adopted_the_list(tmp_path):
    assert load_numbers(tmp_path) is None


def test_a_valid_list_loads_with_defaults(tmp_path):
    _write(tmp_path, [{"text": "0.769", "source": EV}])
    numbers = load_numbers(tmp_path)
    assert isinstance(numbers, NumberList)
    (entry,) = numbers.numbers
    assert entry.document == "draft.tex"
    assert entry.role == "recorded"
    assert entry.source.kind == "evidence"


def test_malformed_json_is_loud(tmp_path):
    (tmp_path / "numbers.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_numbers(tmp_path)
    assert "numbers.json" in str(exc.value)


def test_unknown_top_level_key_is_rejected(tmp_path):
    msg = _error(tmp_path, [], surprise=1)
    assert "surprise" in msg


def test_unknown_entry_key_is_rejected_naming_the_entry(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "role": "identifier"},
                            {"text": "341", "source": EV, "candidates": []}])
    assert "numbers[1]" in msg and "341" in msg and "candidates" in msg


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("field", [
    "point", "effect_size", "p_value", "posterior", "residual", "predictive_error",
    "ci[0]", "ci[1]", "finding.n_chemicals", "finding.counts.total",
])
def test_every_documented_evidence_field_is_accepted(field):
    entry = NumberEntry(text="1", source={"evidence": "e", "field": field})
    assert entry.source.field == field


def test_an_unknown_evidence_field_is_rejected(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "source": {"evidence": "e", "field": "slope"}}])
    assert "numbers[0]" in msg and "slope" in msg


def test_an_evidence_source_needs_a_field(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "source": {"evidence": "e"}}])
    assert "numbers[0]" in msg and "field" in msg


def test_a_source_names_exactly_one_kind(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "source": {
        "spec": "hypotheses[0].decision_rule.params.value",
        "spec_text": "hypotheses[0].statement"}}])
    assert "numbers[0]" in msg and "exactly one" in msg


def test_spec_and_spec_text_take_no_field(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "source": {"spec": "a.b", "field": "x"}}])
    assert "numbers[0]" in msg


def test_a_bib_source_reads_the_year_only(tmp_path):
    entry = NumberEntry(text="2006", source={"bib": "Arnot2006", "field": "year"})
    assert entry.role == "citation"   # inferred from the bib source
    msg = _error(tmp_path, [{"text": "14", "source": {"bib": "Arnot2006",
                                                       "field": "volume"}}])
    assert "numbers[0]" in msg and "year" in msg


def test_a_malformed_json_path_is_rejected(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "source": {"spec": "hypotheses[x].a"}}])
    assert "numbers[0]" in msg and "path" in msg


# --------------------------------------------------------------------------- #
# roles
# --------------------------------------------------------------------------- #

def test_role_is_inferred_from_what_the_entry_carries():
    assert NumberEntry(text="1", source=EV).role == "recorded"
    assert NumberEntry(text="1", formula="a", operands={"a": EV}).role == "derived"
    assert NumberEntry(text="1", role="identifier").role == "identifier"


def test_an_entry_with_nothing_to_check_is_rejected(tmp_path):
    msg = _error(tmp_path, [{"text": "4"}])
    assert "numbers[0]" in msg and "identifier" in msg


def test_an_identifier_carries_no_source(tmp_path):
    msg = _error(tmp_path, [{"text": "4", "role": "identifier", "source": EV}])
    assert "numbers[0]" in msg


def test_a_recorded_entry_cannot_take_a_bib_source(tmp_path):
    msg = _error(tmp_path, [{"text": "2006", "role": "recorded",
                             "source": {"bib": "A2006", "field": "year"}}])
    assert "numbers[0]" in msg


def test_a_derived_entry_needs_formula_and_operands(tmp_path):
    assert "numbers[0]" in _error(tmp_path, [{"text": "1", "role": "derived",
                                              "formula": "a"}])
    assert "numbers[0]" in _error(tmp_path, [{"text": "1", "role": "derived",
                                              "operands": {"a": EV}}])


def test_formula_names_must_be_the_operands(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "formula": "a - b", "operands": {"a": EV}}])
    assert "numbers[0]" in msg and "b" in msg
    msg = _error(tmp_path, [{"text": "1", "formula": "a",
                             "operands": {"a": EV, "c": EV}}])
    assert "numbers[0]" in msg and "c" in msg


@pytest.mark.parametrize("formula", [
    "a ** 2", "abs(a)", "__import__('os')", "a.real", "a if a else 1", "a < 1", "[a]",
    "a // 2", "a % 2", "True", "+a",
])
def test_only_plain_arithmetic_is_a_formula(tmp_path, formula):
    msg = _error(tmp_path, [{"text": "1", "formula": formula, "operands": {"a": EV}}])
    assert "numbers[0]" in msg


def test_operands_are_evidence_or_spec_values(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "formula": "a",
                             "operands": {"a": {"spec_text": "hypotheses[0].statement"}}}])
    assert "numbers[0]" in msg


def test_document_is_draft_or_si(tmp_path):
    msg = _error(tmp_path, [{"text": "1", "role": "identifier", "document": "main.tex"}])
    assert "numbers[0]" in msg


def test_context_cannot_be_empty(tmp_path):
    assert "numbers[0]" in _error(
        tmp_path, [{"text": "1", "role": "identifier", "context": ""}])


# --------------------------------------------------------------------------- #
# the safe arithmetic and the JSON paths
# --------------------------------------------------------------------------- #

def test_formula_evaluation():
    assert formula_names("100 * a") == {"a"}
    assert evaluate_formula("100 * a", {"a": 0.6944}) == pytest.approx(69.44)
    assert evaluate_formula("(a - b) / 2", {"a": 3.0, "b": 1.0}) == pytest.approx(1.0)
    assert evaluate_formula("-a", {"a": 2.0}) == pytest.approx(-2.0)
    with pytest.raises(ValueError):
        evaluate_formula("a / b", {"a": 1.0, "b": 0.0})


def test_json_paths():
    assert parse_json_path("hypotheses[1].decision_rule.params.value") == [
        "hypotheses", 1, "decision_rule", "params", "value"]
    data = {"hypotheses": [{"x": 1}, {"decision_rule": {"params": {"value": 0.5}}}]}
    assert walk_json(data, "hypotheses[1].decision_rule.params.value") == 0.5
    with pytest.raises(KeyError):
        walk_json(data, "hypotheses[2].x")
    with pytest.raises(KeyError):
        walk_json(data, "hypotheses[0].y")
    with pytest.raises(ValueError):
        parse_json_path("a..b")
