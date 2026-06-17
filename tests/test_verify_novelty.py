"""
verify (F6) re-derives the novelty claim from the record (RED-first, B-replace).

design/literature-acquisition.md §"Discovery trigger model" + design/rigor-shell-
architecture.md §6.2/§8 F6: ``verify_run`` re-derives belief from the RECORDED run.

For each ``novelty=True`` hypothesis, verify RE-DERIVES the novelty status via
``derive_novelty_status(hyp, recorded novelty_decisions)`` and compares it to the
RECORDED ``claim-novelty-<hyp>``:

  - recorded SUPPORTED, re-derivation SUPPORTED (the found_nothing decision is intact)
        -> REPRODUCED
  - recorded SUPPORTED, re-derivation PROPOSED (the found_nothing decision was deleted
        or tampered found_something->found_nothing) -> DIVERGED.

The record digest covers evidence, so tampering is also caught there. READ-ONLY: no
persist, no LLM, no capability.
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


def _experiment_with_found_nothing(point: float, hyp_id: str = "hyp-n"):
    """Seed a SUPPORTS bearing AND a found_nothing NOVELTY_DECISION (so the recorded
    novelty claim is SUPPORTED)."""
    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=point),
                bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-found-nothing", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:found_nothing"),
                result=Result(type="qualitative", finding="found_nothing: DOIs=['10.1/x']"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id=hyp_id,
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
# (a) SUPPORTED novelty claim WITH the found_nothing decision -> REPRODUCED
# --------------------------------------------------------------------------- #

def test_verify_supported_novelty_with_found_nothing_reproduced(tmp_path):
    spec = _novelty_spec("nv-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_found_nothing(0.95))

    # the recorded novelty claim is SUPPORTED
    nov_claim = run_dir / "claims" / "claim-novelty-hyp-n.json"
    assert json.loads(nov_claim.read_text(encoding="utf-8"))["status"] == "supported"

    report = verify_run(run_dir)
    # the novelty claim is among the audited outcomes and REPRODUCED
    nov_outcomes = [
        o for o in report.outcomes
        if o.recorded_status == ClaimStatus.SUPPORTED and o.result == "REPRODUCED"
    ]
    assert any(o.hypothesis_id == "hyp-n" for o in nov_outcomes)
    assert report.all_reproduced is True


# --------------------------------------------------------------------------- #
# (b) the found_nothing decision removed -> DIVERGED
# --------------------------------------------------------------------------- #

def test_verify_supported_novelty_without_found_nothing_diverged(tmp_path):
    """Tamper: delete the found_nothing NOVELTY_DECISION from the recorded log. The
    SUPPORTED novelty claim no longer re-derives -> verify flags DIVERGED."""
    spec = _novelty_spec("nv-tampered", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_found_nothing(0.95))

    nov_claim = run_dir / "claims" / "claim-novelty-hyp-n.json"
    assert json.loads(nov_claim.read_text(encoding="utf-8"))["status"] == "supported"

    # Remove the found_nothing decision from the record (tamper / deletion).
    nov_path = run_dir / "evidence" / "evi-nov-found-nothing.json"
    assert nov_path.exists()
    nov_path.unlink()

    report = verify_run(run_dir)
    # the SUPPORTED novelty claim now DIVERGES (re-derivation yields PROPOSED).
    diverged = [
        o for o in report.outcomes
        if o.recorded_status == ClaimStatus.SUPPORTED and o.result == "DIVERGED"
    ]
    assert any(o.hypothesis_id == "hyp-n" for o in diverged)
    assert report.all_reproduced is False


def test_verify_tampered_found_something_to_found_nothing_diverged(tmp_path):
    """Tamper the other way: a recorded found_something decision is edited to
    found_nothing on disk to fake support. But the recorded novelty claim is PROPOSED
    (it was derived honestly), so re-derivation now yields SUPPORTED while the record
    says PROPOSED -> DIVERGED. (The digest also catches the byte edit.)"""
    spec = _novelty_spec("nv-fake-support", value=0.9)

    def exp(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-found-something", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:found_something"),
                result=Result(type="qualitative", finding="found_something: prior art"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_something", hypothesis_id="hyp-n"),
            ),
        ]

    run_dir = _seed(tmp_path, spec, exp)
    nov_claim = run_dir / "claims" / "claim-novelty-hyp-n.json"
    # honestly derived -> PROPOSED
    assert json.loads(nov_claim.read_text(encoding="utf-8"))["status"] == "proposed"

    # Tamper the decision on disk: found_something -> found_nothing.
    dec_path = run_dir / "evidence" / "evi-nov-found-something.json"
    blob = json.loads(dec_path.read_text(encoding="utf-8"))
    blob["literature_decision"]["outcome"] = "found_nothing"
    blob["result"]["finding"] = "found_nothing: tampered"
    dec_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")

    report = verify_run(run_dir)
    # The recorded PROPOSED novelty claim now re-derives SUPPORTED -> DIVERGED.
    # (Two outcomes share hyp-n: the experiment claim + the novelty claim; the novelty
    # one is the recorded-PROPOSED outcome.)
    nov_outcomes = [
        o for o in report.outcomes
        if o.hypothesis_id == "hyp-n" and o.recorded_status == ClaimStatus.PROPOSED
    ]
    assert any(o.result == "DIVERGED" for o in nov_outcomes)
    assert report.all_reproduced is False


def test_verify_is_read_only_for_novelty(tmp_path):
    """The novelty faithfulness re-check writes nothing: the recorded files are
    byte-identical before/after a verify_run over a novelty run."""
    spec = _novelty_spec("nv-readonly", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_found_nothing(0.95))

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
