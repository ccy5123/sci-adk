"""
Contested surfacing in the compiler/run path (RED-first).

design/literature-acquisition.md §"Discovery trigger model" (Medium trigger): when a
claim is/becomes CONTESTED, the run/compiler path surfaces an OPEN contested checkpoint
(mirroring how the Spec-time prior_work checkpoint is surfaced). NO halt -- it is a
recording reminder only.

These tests drive a real compile that yields a CONTESTED claim (both a SUPPORTS and a
REFUTES bearing on one hypothesis) and assert the open contested checkpoint is surfaced
on the CompileResult; recording it then clears the surfaced set on re-compile.
"""

from __future__ import annotations

from pathlib import Path

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
from sci_adk.loop.compiler import ResearchCompiler


def _contested_spec(spec_id: str, hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="a claim with mixed evidence",
                mode=HypothesisMode.CONFIRMATORY,
                # threshold rule so the engine renders a binding verdict autonomously;
                # mixed raw bearings then drive the CONTESTED override.
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="formal",
                non_circularity="the verifier checks a property not baked into the generator",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _mixed_experiment(hyp_id: str = "hyp-1"):
    """Produce a SUPPORTS and a REFUTES bearing on the same hypothesis -> CONTESTED."""
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-sup", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.9),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="ev-ref", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.1),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.REFUTES)],
            ),
        ]
    return experiment


def test_compile_surfaces_open_contested_checkpoint(tmp_path):
    from sci_adk.loop.verdict import ContestedCheckpoint

    spec = _contested_spec("con-surf")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_mixed_experiment()
    )
    # the claim is CONTESTED
    assert any(c.status.value == "contested" for c in result.claims)
    # and an open contested checkpoint is surfaced for it
    surfaced = result.contested_checkpoints
    assert len(surfaced) == 1
    cp = surfaced[0]
    assert isinstance(cp, ContestedCheckpoint)
    assert cp.hypothesis_id == "hyp-1"
    assert cp.spec_id == "con-surf"


def test_compile_does_not_surface_contested_when_not_contested(tmp_path):
    """A clean SUPPORTED claim surfaces no contested checkpoint."""
    def supporting(s, w):
        return [
            EvidenceItem(
                id="ev-sup", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.9),
                bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
            ),
        ]

    spec = _contested_spec("con-clean")
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=supporting
    )
    assert result.contested_checkpoints == []


def test_recording_contested_clears_the_surfaced_checkpoint(tmp_path):
    """After ``record_contested``, a re-compile no longer surfaces the checkpoint (the
    decision is now explicit in the record)."""
    from sci_adk.loop.literature_triggers import record_contested

    spec = _contested_spec("con-clear")
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    first = compiler.compile("", spec=spec, experiment=_mixed_experiment())
    assert len(first.contested_checkpoints) == 1

    record_contested(spec, tmp_path, hypothesis_id="hyp-1",
                     reason_or_note="recorded the conflict")

    second = compiler.compile("", spec=spec, experiment=_mixed_experiment())
    assert second.contested_checkpoints == []


def test_compile_never_halts_on_contested(tmp_path):
    """Surfacing a contested checkpoint must not raise -- the contested trigger has no
    halt (record-only)."""
    spec = _contested_spec("con-nohalt-compile")
    # If this raised, the test would error -- the assertion is the clean return.
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        "", spec=spec, experiment=_mixed_experiment()
    )
    assert result is not None
