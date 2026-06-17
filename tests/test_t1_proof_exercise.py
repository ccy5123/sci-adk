"""
Unit 5 -- the T-1 PROOF exercise (the demonstration of the judge rail's value).

The shipped T-1 capability proves injectivity *on a tested set* via a numeric
``threshold`` rule (collision_count == 0 over the sample) -- empirical support, not
a universal claim. The UNIVERSAL statement "the Gödel encoding is injective/bijective
over ALL molecular graphs" is a ``proof``-kind claim: it can be REFUTED by a single
counterexample but cannot be SUPPORTED by any finite sample. This is exactly where
the qualitative/proof rail earns its keep.

This module makes the rail's behavior *evidence, not assertion*. Driving the real
``run_checkpoint_loop`` over a proof-kind T-1 Spec and a synthetic/fixture Evidence
finding (NO live Docker), it shows:

  * a written verdict trail that "verifies" the proof yields an INCONCLUSIVE claim
    pending a human spot-check -- the engine refuses to self-certify the universal
    claim, even with a confident, well-trailed chief verdict (record != belief;
    "agents propose, the engine judges");
  * a verdict trail reporting a COUNTEREXAMPLE yields a REFUTED claim -- a single
    counterexample is decisive for a universal proof.

Both are deterministic: the verdicts are authored to disk (the in-session agent's
role) and read back by ``RecordedJudge``; sci-adk's Python never calls an LLM here.
"""

from __future__ import annotations

import json
from pathlib import Path

from sci_adk.core.claim import ClaimStatus, ConfidenceLevel
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
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verdict import (
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)

# The UNIVERSAL T-1 claim, expressed as a proof rule (contrast: the shipped
# build_t1_spec uses a numeric threshold over a tested SAMPLE).
_T1_PROOF_HYP = "hyp-t1-universal"
_T1_PROOF_EXPR = (
    "the prime-Goedel encoding phi: G -> N is injective over ALL molecular graphs "
    "(equivalently bijective onto its image): a verified general derivation => "
    "support; a single colliding pair of non-isomorphic graphs => refute"
)


def _t1_proof_spec(spec_id: str) -> Spec:
    """A T-1 Spec whose hypothesis is the UNIVERSAL injectivity claim (proof kind)."""
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background=(
                "A prime-Goedel encoding packs a molecular graph into one integer. "
                "Injectivity on a tested sample is empirical; injectivity over ALL "
                "graphs is a universal mathematical claim."
            ),
            goal=(
                "Establish that the encoding is injective over every molecular graph "
                "(a universal bijectivity-onto-image claim), not merely on a sample."
            ),
            method=(
                "Attempt a general proof of injectivity; a single counterexample "
                "(two non-isomorphic graphs with equal codes) refutes it."
            ),
            expected_output=(
                "Either a verified general derivation of injectivity, or a "
                "counterexample pair that refutes the universal claim."
            ),
        ),
        hypotheses=[
            # referent='formal': a universal injectivity claim is about the encoding
            # map (a formal object). Its proof-step Evidence is 'generated' (computed),
            # and it carries a non-circularity attestation, so the evidence-validity
            # gate allows the binding (counterexample REFUTES) verdict under test.
            Hypothesis(
                id=_T1_PROOF_HYP,
                statement=(
                    "The prime-Goedel molecular encoding is injective over all "
                    "molecular graphs (universal)"
                ),
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.PROOF, expression=_T1_PROOF_EXPR
                ),
                referent="formal",
                non_circularity="a counterexample search probes collisions the "
                "construction does not preclude",
            )
        ],
        method=MethodPlan(approaches=["general injectivity proof"], tools=[]),
        target_claims=[
            TargetClaim(id="tc-t1-universal",
                        statement="The encoding is universally injective",
                        answers=_T1_PROOF_HYP)
        ],
    )


def _fixture_experiment(finding: str):
    """A deterministic, no-Docker Evidence producer (a proof-step finding)."""
    def fn(spec: Spec, workspace_dir: Path):
        return [
            EvidenceItem(
                id="ev-t1-proof",
                spec_id=spec.id,
                kind=EvidenceKind.PROOF_STEP,
                provenance=Provenance(code_ref="fixture:t1-proof-exercise",
                                      data_source="generated"),
                result=Result(type="qualitative", finding=finding),
                bears_on=[Bearing(target_id=_T1_PROOF_HYP,
                                  direction=BearingDirection.NEUTRAL)],
            )
        ]
    return fn


def _author_verdict(run_dir: Path, *, direction, counterexample, basis):
    """Write the chief-over-N trail the in-session agent would author (§4.4)."""
    trail = VerdictTrail(
        hypothesis_id=_T1_PROOF_HYP,
        rule_kind="proof",
        rubric_expression=_T1_PROOF_EXPR,  # judged THIS rule (gate: must match)
        rubric_params=None,
        panel=[
            PanelVerdict(direction=direction, level=ConfidenceLevel.STRONG,
                         basis="panelist 1 reviewed the derivation",
                         counterexample=counterexample),
            PanelVerdict(direction=direction, level=ConfidenceLevel.MODERATE,
                         basis="panelist 2 concurred",
                         counterexample=counterexample),
        ],
        chief=ChiefVerdict(direction=direction, level=ConfidenceLevel.STRONG,
                           basis=basis, counterexample=counterexample),
        provenance=VerdictProvenance(spec_version=1,
                                     timestamp="2026-06-16T00:00:00Z"),
    )
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{_T1_PROOF_HYP}.json").write_text(
        json.dumps(trail.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def test_t1_universal_proof_verified_trail_yields_inconclusive_pending_spotcheck(tmp_path):
    """A 'verified' trail does NOT self-certify the universal T-1 claim.

    Even with a confident, well-formed chief verdict claiming the derivation is
    verified, the engine refuses to mark the universal injectivity claim SUPPORTED:
    it returns an INCONCLUSIVE claim whose basis demands a human spot-check (the
    anti-self-certification rail). The record (a 'verified' verdict) is real; the
    belief (a supported universal claim) is withheld.
    """
    spec = _t1_proof_spec("t1-universal-verified")
    run_dir = tmp_path / "runs" / spec.id
    # Lay down the run (spec + evidence + checkpoint) first.
    run_checkpoint_loop(run_dir=run_dir, spec=spec,
                        experiment=_fixture_experiment("a general derivation sketch"),
                        workspace_dir=tmp_path)
    # The in-session agent authors a confident "verified" verdict.
    _author_verdict(run_dir, direction=BearingDirection.SUPPORTS,
                    counterexample=False,
                    basis="panelist 1's general induction is decisive under R; "
                          "the derivation appears verified")
    # Re-enter the loop.
    result = run_checkpoint_loop(run_dir=run_dir, spec=spec, workspace_dir=tmp_path)

    claim = result.claims[0]
    # DEMONSTRATION 1: not supported, despite a confident verified trail.
    assert claim.status != ClaimStatus.SUPPORTED
    assert claim.status == ClaimStatus.PROPOSED  # inconclusive -> PROPOSED
    assert "spot-check" in claim.confidence.basis.lower()
    # The universal claim stays an OPEN checkpoint (the engine raised the spot-check).
    assert _T1_PROOF_HYP in result.unresolved


def test_t1_universal_proof_counterexample_trail_yields_refuted(tmp_path):
    """A counterexample trail REFUTES the universal T-1 claim decisively.

    A single colliding pair of non-isomorphic graphs is decisive for a universal
    injectivity proof: the engine marks the claim REFUTED (no human spot-check
    needed for a refutation), and the checkpoint is resolved.
    """
    spec = _t1_proof_spec("t1-universal-counterexample")
    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec,
                        experiment=_fixture_experiment("searched for collisions"),
                        workspace_dir=tmp_path)
    # The agent authors a counterexample verdict.
    _author_verdict(run_dir, direction=BearingDirection.REFUTES,
                    counterexample=True,
                    basis="panelist 1 exhibited two non-isomorphic graphs with the "
                          "same code -- a decisive counterexample under R")
    result = run_checkpoint_loop(run_dir=run_dir, spec=spec, workspace_dir=tmp_path)

    claim = result.claims[0]
    # DEMONSTRATION 2: a counterexample refutes the universal claim.
    assert claim.status == ClaimStatus.REFUTED
    assert "counterexample" in claim.confidence.basis.lower()
    assert _T1_PROOF_HYP not in result.unresolved  # decisively resolved


def test_t1_universal_proof_verified_without_trail_is_refused_for_trail(tmp_path):
    """Without a trail, even a confident 'verified' verdict cannot move the claim.

    This is the F2 gate at the T-1 layer: a binding verdict with no
    verdicts/<hyp-id>.json on disk is refused -- the engine will not bind on the
    judge's say-so alone. The claim stays unresolved.
    """
    spec = _t1_proof_spec("t1-universal-no-trail")
    run_dir = tmp_path / "runs" / spec.id
    # Run the loop with NO verdict authored -> RecordedJudge finds nothing.
    result = run_checkpoint_loop(
        run_dir=run_dir, spec=spec,
        experiment=_fixture_experiment("a derivation sketch"), workspace_dir=tmp_path)
    claim = result.claims[0]
    assert claim.status != ClaimStatus.SUPPORTED
    assert _T1_PROOF_HYP in result.unresolved
