"""
verify (F6) re-checks a SUPPORTED novelty claim against the record (RED-first).

design/literature-acquisition.md §"Discovery trigger model" + design/rigor-shell-
architecture.md §6.2/§8 F6: ``verify_run`` re-derives belief from the RECORDED run. A
SUPPORTED novelty claim is faithful ONLY if the record shows the prior-art search was
done. So if the run holds a SUPPORTED claim for a ``novelty=True`` hypothesis but no
``NOVELTY_DECISION`` with ``outcome=="searched"`` for it exists (e.g. the decision was
deleted/tampered), verify reports it as DIVERGED/UNRESOLVED -- the audit's
faithfulness re-check, mirroring the digitized self-certification re-check already in
``_audit_hypothesis``. READ-ONLY: no persist, no LLM, no capability.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.core.claim import ClaimStatus
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
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verify import verify_run


_NON_CIRC = "the verifier checks a property not baked into the generator"


def _novelty_spec(spec_id: str, hyp_id: str = "hyp-n", value: float = 0.9) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id=hyp_id, statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": value},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
                novelty=True,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _experiment_with_searched_decision(point: float, hyp_id: str = "hyp-n"):
    """Seed a SUPPORTS bearing AND a searched NOVELTY_DECISION (so seeding's gate
    passes and a SUPPORTED claim is recorded)."""
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-searched", spec_id=s.id, kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:searched"),
                result=Result(type="qualitative", finding="searched: DOIs=['10.1/x']"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="searched", hypothesis_id=hyp_id,
                    literature_evidence_id="evi-lit-x"),
            ),
        ]
    return experiment


def _seed(workspace: Path, spec: Spec, experiment) -> Path:
    run_dir = workspace / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=workspace)
    return run_dir


# --------------------------------------------------------------------------- #
# (a) SUPPORTED novelty claim WITH a searched decision -> REPRODUCED
# --------------------------------------------------------------------------- #

def test_verify_supported_novelty_with_searched_decision_reproduced(tmp_path):
    spec = _novelty_spec("nv-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_searched_decision(0.95))
    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert by_hyp["hyp-n"].recorded_status == ClaimStatus.SUPPORTED
    assert by_hyp["hyp-n"].result == "REPRODUCED"
    assert report.all_reproduced is True


# --------------------------------------------------------------------------- #
# (b) the searched decision removed -> NOT reproduced (DIVERGED/UNRESOLVED)
# --------------------------------------------------------------------------- #

def test_verify_supported_novelty_without_searched_decision_not_reproduced(tmp_path):
    """Tamper: delete the searched NOVELTY_DECISION from the recorded log. The
    SUPPORTED novelty claim no longer follows from the record -> verify flags it."""
    spec = _novelty_spec("nv-tampered", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_searched_decision(0.95))

    # The recorded claim is SUPPORTED.
    claim_path = run_dir / "claims" / "claim-hyp-n.json"
    assert json.loads(claim_path.read_text(encoding="utf-8"))["status"] == "supported"

    # Remove the novelty searched decision from the record (tamper / deletion).
    nov_path = run_dir / "evidence" / "evi-nov-searched.json"
    assert nov_path.exists()
    nov_path.unlink()

    report = verify_run(run_dir)
    by_hyp = {o.hypothesis_id: o for o in report.outcomes}
    assert by_hyp["hyp-n"].recorded_status == ClaimStatus.SUPPORTED
    # not a clean reproduction -- the audit caught the missing search.
    assert by_hyp["hyp-n"].result in ("DIVERGED", "UNRESOLVED")
    assert report.all_reproduced is False


def test_verify_is_read_only_for_novelty(tmp_path):
    """The faithfulness re-check writes nothing: the recorded files are byte-identical
    before/after a verify_run over a novelty run."""
    spec = _novelty_spec("nv-readonly", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_searched_decision(0.95))

    before = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((run_dir).rglob("*.json"))
    }
    verify_run(run_dir)
    after = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((run_dir).rglob("*.json"))
    }
    assert before == after
