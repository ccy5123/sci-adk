"""
render-merge (RED-first): the prose hook on the Markdown ``render_paper``.

Two guarantees:
  1. A ``PaperProse`` with abstract/introduction/discussion injects those narrative
     sections into the Markdown draft (agent-authored text passed in -- never LLM).
  2. With ``prose=None`` the Markdown output is BYTE-IDENTICAL to the pre-change
     skeleton (a strict regression lock -- the existing draft must not move).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
    EvidenceLink,
    EvidenceLinkRole,
)
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
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
from sci_adk.render.paper import render_paper
from sci_adk.render.prose import PaperProse

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="point >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)


def _fixture():
    hyp = Hypothesis(
        id="hyp-1",
        statement="the encoding is injective on the tested set",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_THRESHOLD,
        referent="formal",
        non_circularity="collisions could occur; the verifier checks for them",
    )
    spec = Spec(
        id="t-prose-md",
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="An encoding", method="method", expected_output="out"
        ),
        hypotheses=[hyp],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp.id)],
    )
    claim = Claim(
        id="claim-1",
        spec_id="t-prose-md",
        answers="hyp-1",
        statement=hyp.statement,
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(
            type=ConfidenceType.CREDENCE, value=0.9, basis="threshold rule: met"
        ),
        evidence_set=[EvidenceLink(evidence_id="ev-1", role=EvidenceLinkRole.SUPPORTING)],
        mode=hyp.mode,
    )
    ev = EvidenceItem(
        id="ev-1",
        created_at=_T0,
        spec_id="t-prose-md",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(type="quantitative", point=0.9),
        bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
    )
    return spec, claim, ev


def test_prose_none_is_byte_identical_regression():
    """The keystone regression lock: render_paper(...) with no prose must equal
    render_paper(...) called the old way (positional spec/claims/evidence/pending).
    """
    spec, claim, ev = _fixture()
    # Old call signature (no prose / citations kwargs).
    old = render_paper(spec, [claim], [ev])
    # New call, explicitly prose=None.
    new = render_paper(spec, [claim], [ev], prose=None)
    assert new == old, "prose=None must not change the existing skeleton output"


def test_prose_injects_markdown_sections():
    spec, claim, ev = _fixture()
    prose = PaperProse(
        abstract="We present a Goedel-style encoding and test injectivity.",
        introduction="Serializing a molecular graph to one integer is attractive.",
        discussion="The supported claim is exploratory and sample-bounded.",
    )
    md = render_paper(spec, [claim], [ev], prose=prose, cited_dois=["10.1/x"])

    # Markdown headings for the agent-authored narrative.
    assert "## Abstract" in md
    assert "We present a Goedel-style encoding" in md
    assert "## Introduction" in md
    assert "Serializing a molecular graph" in md
    assert "## Discussion" in md
    assert "exploratory and sample-bounded" in md
    # Abstract appears before the structural Goal section; Discussion comes after the
    # Evidence trail but BEFORE the References section (the decided ordering).
    assert md.index("## Abstract") < md.index("## Goal")
    assert md.index("## Evidence") < md.index("## Discussion")
    assert md.index("## Discussion") < md.index("## References")


def test_partial_prose_only_present_slots_markdown():
    spec, claim, ev = _fixture()
    prose = PaperProse(introduction="Just an introduction.")
    md = render_paper(spec, [claim], [ev], prose=prose)
    assert "## Introduction" in md
    assert "Just an introduction." in md
    # Absent slots produce no heading.
    assert "## Abstract" not in md
    assert "## Discussion" not in md


def test_markdown_cited_dois_render_list():
    """The Markdown renderer also carries a References section (symmetry with LaTeX)."""
    spec, claim, ev = _fixture()
    md = render_paper(
        spec, [claim], [ev], cited_dois=["10.1021/c160017a018"]
    )
    assert "References" in md
    assert "10.1021/c160017a018" in md


def test_markdown_no_dois_says_none_cited():
    spec, claim, ev = _fixture()
    md = render_paper(spec, [claim], [ev], cited_dois=[])
    assert "No literature cited." in md
