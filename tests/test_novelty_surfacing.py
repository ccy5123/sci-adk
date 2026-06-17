"""
Novelty soft-checkpoint surfacing in the compiler/run path (RED-first, B-replace).

design/literature-acquisition.md §"Discovery trigger model" (High trigger, B-replace):
novelty no longer HALTs. Instead, while a ``novelty=True`` hypothesis's
``claim-novelty-<hyp>`` is PROPOSED, the run/compiler path surfaces a NON-HALT
``NoveltyCheckpoint`` (mirroring how the contested checkpoint is surfaced). The compile
PROCEEDS normally -- the checkpoint is collected and returned, nothing stops.

The checkpoint prompt is reason-tailored:
  - reason ``not_searched`` (no novelty decision, or a ``skipped`` one): "search prior
    art and record the outcome, or drop the novelty flag via a Spec amendment (F7)".
  - reason ``found_something``: "prior art was found; drop the novelty flag via a Spec
    amendment (F7)" -- it does NOT tell the agent to go search (the search is done).

When a found_nothing decision exists (novelty claim SUPPORTED), nothing is surfaced.
"""

from __future__ import annotations

from pathlib import Path

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
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
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verdict import NoveltyCheckpoint


_NON_CIRC = "the verifier checks a property not baked into the generator"


def _novelty_spec(spec_id: str, hyp_id: str = "hyp-1", novelty: bool = True) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
                novelty=novelty,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _supporting(hyp_id: str = "hyp-1", point: float = 0.9):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-sup", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
        ]
    return experiment


def _supporting_with_decision(outcome: str, hyp_id: str = "hyp-1", point: float = 0.9):
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-sup", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id=f"evi-nov-{outcome}", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref=f"novelty:{outcome}"),
                result=Result(type="qualitative", finding=f"{outcome}: ..."),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome=outcome, hypothesis_id=hyp_id),
            ),
        ]
    return experiment


# --------------------------------------------------------------------------- #
# surfaced while PROPOSED, NON-HALT, reason-tailored
# --------------------------------------------------------------------------- #

def test_compile_surfaces_novelty_checkpoint_when_not_searched(tmp_path):
    spec = _novelty_spec("nov-surf-notsearched")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_supporting()
    )
    surfaced = result.novelty_checkpoints
    assert len(surfaced) == 1
    cp = surfaced[0]
    assert isinstance(cp, NoveltyCheckpoint)
    assert cp.hypothesis_id == "hyp-1"
    assert cp.spec_id == "nov-surf-notsearched"
    # reason not_searched: prompt tells the agent to search and record (or amend away).
    prompt = cp.prompt.lower()
    assert "search" in prompt
    assert "amend" in prompt or "f7" in prompt


def test_compile_surfaces_novelty_checkpoint_when_skipped(tmp_path):
    """A skipped decision still leaves the claim PROPOSED -> surfaced as not_searched."""
    spec = _novelty_spec("nov-surf-skip")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_supporting_with_decision("skipped")
    )
    surfaced = result.novelty_checkpoints
    assert len(surfaced) == 1
    assert "search" in surfaced[0].prompt.lower()


def test_compile_surfaces_novelty_checkpoint_when_found_something(tmp_path):
    """found_something: the claim stays PROPOSED, but the prompt is the found_something
    variant -- it does NOT tell the agent to go search (the search is done)."""
    spec = _novelty_spec("nov-surf-found")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_supporting_with_decision("found_something")
    )
    surfaced = result.novelty_checkpoints
    assert len(surfaced) == 1
    prompt = surfaced[0].prompt.lower()
    # prior art was found; the escape is the F7 amendment, not "go search".
    assert "amend" in prompt or "f7" in prompt
    assert "prior art" in prompt or "found" in prompt
    # DISTINGUISHING (the bug LOW-1 missed): the found_something prompt must NOT be the
    # not_searched "go search" variant. "search prior art" appears ONLY in the
    # not_searched prompt; its presence here would mean the wrong variant was emitted
    # (e.g. because the reason was read from disk, where the in-memory found_something
    # decision is not yet persisted in a single-pass compile).
    assert "search prior art" not in prompt
    assert "do not search again" in prompt or "the search is done" in prompt


def test_compile_does_not_surface_when_found_nothing(tmp_path):
    """found_nothing -> the novelty claim is SUPPORTED -> nothing surfaced."""
    spec = _novelty_spec("nov-surf-found-nothing")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_supporting_with_decision("found_nothing")
    )
    assert result.novelty_checkpoints == []


def test_compile_does_not_surface_for_non_novelty_hypothesis(tmp_path):
    spec = _novelty_spec("nov-surf-off", novelty=False)
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_supporting()
    )
    assert result.novelty_checkpoints == []


def test_compile_never_halts_on_novelty(tmp_path):
    """Surfacing a novelty checkpoint must not raise -- B-replace removed the HALT."""
    spec = _novelty_spec("nov-nohalt-compile")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_supporting()
    )
    assert result is not None
    # the compile produced an experiment claim AND surfaced the (non-halt) checkpoint
    assert any(c.id == "claim-hyp-1" for c in result.claims)
    assert len(result.novelty_checkpoints) == 1
