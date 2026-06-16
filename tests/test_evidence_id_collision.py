"""
Regression: evidence IDs must be collision-free even when many are generated
within the same wall-clock second.

Previously ``_generate_evidence_id`` used a second-resolution timestamp
(``evi-YYYYMMDD-HHMMSS``), so multiple evidence items created in one second got
identical IDs -- overwriting each other on disk and making
``test_phase4_evidence_generation.py::test_multiple_evidence_items`` flaky (it
asserts the two IDs differ, which held only when the two fast Docker runs
happened to straddle a second boundary). These tests reproduce the collision
deterministically (no Docker, no timing luck): generating many IDs in a tight
loop -- all inside one second -- must still yield all-distinct IDs.
"""

from datetime import datetime, timezone

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
from sci_adk.loop.experiment_runner import ExperimentRunner
from sci_adk.loop.literature_acquirer import LiteratureAcquirer

_HYP = "hyp-idcoll"
_N = 200  # all generated within one second -> stresses the collision


def _spec() -> Spec:
    return Spec(
        id="id-collision-test",
        created_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="e"),
        hypotheses=[
            Hypothesis(
                id=_HYP,
                statement="s",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= 1 => support",
                    params={"statistic": "point", "op": ">=", "value": 1.0},
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="c", answers=_HYP)],
    )


def test_experiment_runner_ids_unique_within_one_second(tmp_path):
    runner = ExperimentRunner(_spec(), workspace_dir=tmp_path)
    ids = [runner._generate_evidence_id() for _ in range(_N)]
    assert len(set(ids)) == _N, "evidence IDs collide within one second"


def test_literature_acquirer_ids_unique_within_one_second():
    ids = [LiteratureAcquirer._generate_evidence_id() for _ in range(_N)]
    assert len(set(ids)) == _N, "literature evidence IDs collide within one second"
