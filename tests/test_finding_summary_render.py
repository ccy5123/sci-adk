"""
How a structured Evidence finding reads in the deposited record (design/declared-numbers.md
§4.4).

The experiment stage now records the values a paper may state as named numbers in the
finding JSON: ``{"summary": "<prose>", "n_chemicals": 341, ...}``. The paper session reads
``record.tex``, so those values must be readable there: the summary as text, then each
value as ``key = value``. The stored finding is never changed; only its rendering.
"""

from __future__ import annotations

import json

from sci_adk.core.evidence import EvidenceItem, EvidenceKind, Provenance, Result
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.render.paper import _summarize_finding, check_paper_tool_vocabulary
from sci_adk.render.si import render_si_latex

_SUMMARY = ("Record selection on the curated database: quality acceptable, fish only, "
            "whole-body tissue and a wet-weight value, in that order")


def test_a_summary_finding_reads_as_text_then_named_values():
    finding = json.dumps({"summary": _SUMMARY, "n_records_input": 6973,
                          "n_chemicals_input": 842, "slope_se": 0.0288})
    line = _summarize_finding(finding)
    assert _SUMMARY in line                      # not cut at a short cap
    assert "n_records_input = 6973" in line
    assert "n_chemicals_input = 842" in line
    assert "slope_se = 0.0288" in line
    assert "{" not in line                       # no raw JSON


def test_a_finding_without_a_summary_renders_as_before():
    assert _summarize_finding('{"collision_count": 0}') == "finding=(collision_count=0)"
    assert _summarize_finding("plain prose") == "finding=plain prose"


def test_the_record_carries_the_named_values_and_the_stored_finding_is_untouched():
    finding = json.dumps({"summary": "counts after each filter", "n_kept": 341})
    ev = EvidenceItem(
        id="evi-counts", spec_id="sp", kind=EvidenceKind.OBSERVATION,
        provenance=Provenance(code_ref="x"),
        result=Result(type="qualitative", finding=finding), bears_on=[],
    )
    spec = Spec(
        id="sp", version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id="h", statement="s", mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(kind=DecisionRuleKind.THRESHOLD, expression="e",
                                       params={"statistic": "point", "op": ">=",
                                               "value": 0.5}),
            referent="formal", non_circularity="n",
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="h")],
    )
    record = render_si_latex(spec, [], [ev])
    assert "counts after each filter" in record
    assert "n\\_kept = 341" in record
    assert ev.result.finding == finding


def test_the_number_list_file_is_not_a_word_for_the_paper():
    assert "numbers.json" in check_paper_tool_vocabulary("as listed in numbers.json")
