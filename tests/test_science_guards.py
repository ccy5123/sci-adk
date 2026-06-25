"""
Tests for the science guards (design/science-guards.md G1-G5).

Two enforcement points, one family (no parallel verifier):
  - spec gate  : ``core.spec_science.audit_spec_science`` -- ALWAYS on, NEVER halts
                 (surfaces G1/G2/G4/G5 + a G3 reminder).
  - verdict gate: ``core.validity.check_{analyticity,discriminating_power,
                 falsifiability_adequacy}`` -- HARD halts, ENFORCED only under
                 ``strict_science`` (lenient primitive / strict entrypoint).

Coverage: legitimate vs illegitimate per guard, the ClaimUpdater strict/lenient
integration, the verify strict tamper-evidence re-check, and the real t1-godel(v4)
spec as a regression case.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    NegativeControl,
    Provenance,
    Result,
)
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    DiscriminatingCase,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.core.spec_science import audit_spec_science
from sci_adk.core.validity import (
    ValidityHalt,
    check_analyticity,
    check_discriminating_power,
    check_falsifiability_adequacy,
)
from sci_adk.loop.claim_updater import ClaimUpdater
from sci_adk.loop.verify import DIVERGED, REPRODUCED, verify_run

SUPPORTS = BearingDirection.SUPPORTS
REFUTES = BearingDirection.REFUTES

# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #


def _threshold_rule(statistic: str = "collision_count", value: float = 0.0) -> DecisionRule:
    return DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression=f"{statistic} == {value} => support",
        params={"statistic": statistic, "op": "==", "value": value},
    )


def _formal_hyp(
    hyp_id: str = "hyp-x",
    *,
    statement: str = "the encoding maps every input to a distinct value on the tested set",
    mode: HypothesisMode = HypothesisMode.CONFIRMATORY,
    rule: DecisionRule | None = None,
    epistemic_kind: str = "finding",
    discriminating_cases: list[DiscriminatingCase] | None = None,
    novelty_result: bool = False,
    novelty_method: bool = False,
    cost_metrics: list[str] | None = None,
) -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement=statement,
        mode=mode,
        decision_rule=rule or _threshold_rule(),
        referent="formal",
        non_circularity="an independent oracle checks the property, not the generator",
        epistemic_kind=epistemic_kind,
        discriminating_cases=discriminating_cases,
        novelty_result=novelty_result,
        novelty_method=novelty_method,
        cost_metrics=cost_metrics,
    )


def _spec(hyps: list[Hypothesis], *, spec_id: str = "sg-test") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="b", goal="g", method="m", expected_output="e"
        ),
        hypotheses=hyps,
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[
            TargetClaim(id=f"tc-{h.id}", statement=h.statement, answers=h.id)
            for h in hyps
        ],
    )


def _generated_evidence(
    spec_id: str,
    hyp_id: str,
    *,
    direction: BearingDirection = SUPPORTS,
    point: float = 0.0,
    data_source: str | None = "generated",
) -> EvidenceItem:
    return EvidenceItem(
        id=f"evi-{hyp_id}",
        created_at=datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc),
        spec_id=spec_id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="commit:abc@main:enc.py:1", data_source=data_source),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=hyp_id, direction=direction)],
    )


def _negative_control(
    spec_id: str,
    hyp_id: str,
    *,
    covered: list[str],
    outcome: str = "not_supported",
    provenance: Provenance | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        id=f"nc-{hyp_id}",
        created_at=datetime(2026, 6, 22, 12, 5, 0, tzinfo=timezone.utc),
        spec_id=spec_id,
        kind=EvidenceKind.NEGATIVE_CONTROL,
        provenance=provenance
        if provenance is not None
        else Provenance(code_ref="commit:abc@main:mutant.py:1", environment="docker:img"),
        result=Result(type="quantitative", point=3.0),
        bears_on=[],  # a record ABOUT the apparatus -- never enters the engine
        negative_control=NegativeControl(
            hypothesis_id=hyp_id,
            mutant="removed one tie-breaking invariant from the canonicalizer",
            outcome=outcome,
            discriminating_cases_covered=covered,
            statistic="collision_count",
            observed_value=3.0,
        ),
    )


_CASES = [
    DiscriminatingCase(case="cospectral-pair-A", why="cospectral non-isomorphic graphs"),
    DiscriminatingCase(case="ec-degenerate-B", why="EC-degenerate non-isomorphic pair"),
]
_COVERED = ["cospectral-pair-A", "ec-degenerate-B"]


# --------------------------------------------------------------------------- #
# G1 -- analyticity (verdict gate)
# --------------------------------------------------------------------------- #


def test_g1_halts_known_result_finding_stamped_supported():
    # ILLEGITIMATE: formal + threshold + no novelty + epistemic 'finding' + generated +
    # SUPPORTS -> a known/constructively-true result packaged as a discovery -> HALT.
    h = _formal_hyp(novelty_result=False, epistemic_kind="finding")
    with pytest.raises(ValidityHalt):
        check_analyticity(h, [_generated_evidence("s", h.id)], SUPPORTS)


def test_g1_passes_open_conjecture_with_novelty():
    # LEGITIMATE: an OPEN conjecture (asserts novelty) -- example-verification is valid
    # science ("no counterexample up to N"). The novelty bypass is the G1 nuance.
    h = _formal_hyp(novelty_result=True)
    check_analyticity(h, [_generated_evidence("s", h.id)], SUPPORTS)  # no raise


def test_g1_passes_when_reclassified_unit_test():
    # LEGITIMATE: reclassified -> the claim is framed as a capability, not a finding.
    h = _formal_hyp(epistemic_kind="unit_test")
    check_analyticity(h, [_generated_evidence("s", h.id)], SUPPORTS)  # no raise


@pytest.mark.parametrize("data_source", [None, "measured", "synthetic_proxy", "generated"])
def test_g1_halts_regardless_of_data_source(data_source):
    # Fail-closed (closed after the 2026-06-22 review): G1 fires for a known-result finding
    # independent of data_source -- an unset/None/measured data_source must NOT slip past the
    # verdict gate (it would otherwise, while the spec gate flagged it).
    h = _formal_hyp(novelty_result=False, epistemic_kind="finding")
    ev = _generated_evidence("s", h.id, data_source=data_source)
    with pytest.raises(ValidityHalt):
        check_analyticity(h, [ev], SUPPORTS)


def test_g1_passes_on_refutes_and_empirical():
    # Out of scope: a REFUTES verdict needs no reclassification; an empirical hypothesis is
    # gated by check_evidence_adequacy, not by G1.
    h = _formal_hyp(epistemic_kind="finding")
    check_analyticity(h, [_generated_evidence("s", h.id, direction=REFUTES)], REFUTES)
    emp = Hypothesis(
        id="hyp-e", statement="rice yields rise", mode=HypothesisMode.CONFIRMATORY,
        decision_rule=_threshold_rule(), referent="empirical",
    )
    check_analyticity(emp, [], SUPPORTS)  # no raise


# --------------------------------------------------------------------------- #
# G2 -- test-power (verdict gate)
# --------------------------------------------------------------------------- #


def test_g2_halts_without_discriminating_cases():
    h = _formal_hyp(discriminating_cases=None)
    with pytest.raises(ValidityHalt):
        check_discriminating_power(h, SUPPORTS)


def test_g2_passes_with_discriminating_cases():
    h = _formal_hyp(discriminating_cases=_CASES)
    check_discriminating_power(h, SUPPORTS)  # no raise


# --------------------------------------------------------------------------- #
# G3 -- falsifiability (verdict gate) -- the most important
# --------------------------------------------------------------------------- #


def test_g3_halts_without_negative_control():
    h = _formal_hyp(discriminating_cases=_CASES)
    with pytest.raises(ValidityHalt):
        check_falsifiability_adequacy(h, [], SUPPORTS)


def test_g3_passes_with_qualifying_control():
    h = _formal_hyp(discriminating_cases=_CASES)
    nc = _negative_control("s", h.id, covered=_COVERED)
    check_falsifiability_adequacy(h, [nc], SUPPORTS)  # no raise


def test_g3_halts_control_without_real_provenance():
    # Q3 requirement: the mutant must have been actually RUN (real provenance). A control with
    # an empty provenance is merely ASSERTED -> does not count.
    h = _formal_hyp(discriminating_cases=_CASES)
    nc = _negative_control("s", h.id, covered=_COVERED, provenance=Provenance())
    with pytest.raises(ValidityHalt):
        check_falsifiability_adequacy(h, [nc], SUPPORTS)


def test_g3_halts_control_with_supported_outcome():
    # A mutant the apparatus did NOT catch (outcome 'supported') proves the test is
    # unfalsifiable on that mutation -> does not count.
    h = _formal_hyp(discriminating_cases=_CASES)
    nc = _negative_control("s", h.id, covered=_COVERED, outcome="supported")
    with pytest.raises(ValidityHalt):
        check_falsifiability_adequacy(h, [nc], SUPPORTS)


def test_g3_halts_control_misses_discriminating_cases():
    # Q3 requirement: the mutant must FAIL on the declared discriminating cases (G2<->G3). A
    # control covering only an easy/other case does not qualify.
    h = _formal_hyp(discriminating_cases=_CASES)
    nc = _negative_control("s", h.id, covered=["some-easy-case"])
    with pytest.raises(ValidityHalt):
        check_falsifiability_adequacy(h, [nc], SUPPORTS)


def test_g3_passes_when_not_supports():
    h = _formal_hyp(discriminating_cases=_CASES)
    check_falsifiability_adequacy(h, [], REFUTES)  # no raise (out of scope)


# --------------------------------------------------------------------------- #
# spec-gate audit (always-on, never halts)
# --------------------------------------------------------------------------- #


def test_audit_surfaces_g1_g2_g3_g4_for_weak_formal_threshold():
    # An exploratory formal+threshold finding with no discriminating cases trips G1, G2, the
    # G3 reminder, and G4 (exploratory + frozen threshold).
    h = _formal_hyp(mode=HypothesisMode.EXPLORATORY, epistemic_kind="finding")
    findings = audit_spec_science(_spec([h]))
    guards = {f.guard for f in findings}
    assert {"G1", "G2", "G3", "G4"} <= guards


def test_audit_g5_flags_practical_property_term():
    h = _formal_hyp(
        statement="a compact molecular index assigning one integer per molecule",
        discriminating_cases=_CASES, epistemic_kind="unit_test",
    )
    findings = audit_spec_science(_spec([h]))
    g5 = [f for f in findings if f.guard == "G5"]
    assert len(g5) == 1
    assert "index" in g5[0].message


def test_audit_g5_satisfied_by_declared_cost_metric():
    h = _formal_hyp(
        statement="a compact molecular index assigning one integer per molecule",
        discriminating_cases=_CASES, epistemic_kind="unit_test",
        cost_metrics=["encoded integer bit-length"],
    )
    findings = audit_spec_science(_spec([h]))
    assert not [f for f in findings if f.guard == "G5"]


@pytest.mark.parametrize(
    "term, statement",
    [
        ("tractable", "a tractable canonical form computable for every input"),
        ("real-time", "a real-time lookup that resolves each query on demand"),
        ("latency", "a low latency decoder returning the structure per query"),
        ("concise", "a concise integer code, one per molecule"),
    ],
)
def test_audit_g5_flags_curated_high_precision_terms(term, statement):
    # The curated reinforcement (tractable/real-time/latency/concise) each commits the
    # author to a cost measurement -- with none declared, G5 must surface, naming the term.
    h = _formal_hyp(
        statement=statement, discriminating_cases=_CASES, epistemic_kind="unit_test",
    )
    g5 = [f for f in audit_spec_science(_spec([h])) if f.guard == "G5"]
    assert len(g5) == 1
    assert term in g5[0].message


def test_audit_g5_curated_term_silenced_by_declared_cost_metric():
    # The same override path as the original keywords: declaring the metric closes G5.
    h = _formal_hyp(
        statement="a tractable canonical form computable for every input",
        discriminating_cases=_CASES, epistemic_kind="unit_test",
        cost_metrics=["worst-case time complexity"],
    )
    assert not [f for f in audit_spec_science(_spec([h])) if f.guard == "G5"]


def test_audit_compliant_hypothesis_is_quiet():
    # A confirmatory, reclassified, discriminating, cost-declared formal hypothesis trips only
    # the forward G3 reminder (a negative control is still required for a strict SUPPORTED).
    h = _formal_hyp(
        mode=HypothesisMode.CONFIRMATORY, epistemic_kind="unit_test",
        discriminating_cases=_CASES, cost_metrics=["bit-length"],
    )
    findings = audit_spec_science(_spec([h]))
    assert {f.guard for f in findings} == {"G3"}


def test_audit_never_raises_and_is_pure():
    h = _formal_hyp(mode=HypothesisMode.EXPLORATORY)
    spec = _spec([h])
    before = spec.model_dump()
    audit_spec_science(spec)
    assert spec.model_dump() == before  # pure -- no mutation


# --------------------------------------------------------------------------- #
# ClaimUpdater integration -- lenient primitive / strict entrypoint
# --------------------------------------------------------------------------- #


def _compliant_spec() -> Spec:
    h = _formal_hyp(
        hyp_id="hyp-ok", epistemic_kind="unit_test", discriminating_cases=_CASES,
        cost_metrics=["bit-length"],
    )
    return _spec([h], spec_id="sg-strict")


def test_claimupdater_lenient_stamps_supported_without_artifacts(tmp_path):
    # The PRIMITIVE is lenient by default: a bare formal+threshold SUPPORTS is stamped (the
    # weakness is surfaced at the spec gate + verify, not blocked here).
    h = _formal_hyp(hyp_id="hyp-l", epistemic_kind="finding")
    spec = _spec([h], spec_id="sg-lenient")
    ev = _generated_evidence(spec.id, h.id, point=0.0)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert claims[0].status.value == "supported"


def test_claimupdater_strict_halts_without_negative_control(tmp_path):
    spec = _compliant_spec()
    h = spec.hypotheses[0]
    ev = _generated_evidence(spec.id, h.id, point=0.0)
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path, strict_science=True).update_claims_from_evidence([ev])


def test_claimupdater_strict_stamps_supported_with_full_artifacts(tmp_path):
    spec = _compliant_spec()
    h = spec.hypotheses[0]
    ev = _generated_evidence(spec.id, h.id, point=0.0)
    nc = _negative_control(spec.id, h.id, covered=_COVERED)
    claims = ClaimUpdater(
        spec, tmp_path, strict_science=True
    ).update_claims_from_evidence([ev, nc])
    assert claims[0].status.value == "supported"


def test_claimupdater_strict_g2_is_the_specific_halt(tmp_path):
    # G1 bypassed (epistemic_kind unit_test), G2 fires (no discriminating cases): the strict
    # ClaimUpdater halt reason is specifically the test-power one, isolating G2 at the
    # integration layer (not only the primitive).
    h = _formal_hyp(hyp_id="hyp-g2", epistemic_kind="unit_test", discriminating_cases=None)
    spec = _spec([h], spec_id="sg-g2")
    ev = _generated_evidence(spec.id, h.id, point=0.0)
    with pytest.raises(ValidityHalt) as exc:
        ClaimUpdater(spec, tmp_path, strict_science=True).update_claims_from_evidence([ev])
    assert "discriminating" in exc.value.reason.lower()


# --------------------------------------------------------------------------- #
# verify strict re-check -- tamper-evidence
# --------------------------------------------------------------------------- #


def _persist_strict_run(tmp_path: Path) -> tuple[Path, str]:
    """Persist a strict, guard-compliant SUPPORTED run to disk; return (run_dir, nc_filename)."""
    spec = _compliant_spec()
    h = spec.hypotheses[0]
    run_dir = tmp_path / "runs" / spec.id
    (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    ev = _generated_evidence(spec.id, h.id, point=0.0)
    nc = _negative_control(spec.id, h.id, covered=_COVERED)
    for item in (ev, nc):
        (run_dir / "evidence" / f"{item.id}.json").write_text(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
        )
    # Strict derive writes the SUPPORTED claim (passes because the control is present).
    ClaimUpdater(spec, tmp_path, strict_science=True).update_claims_from_evidence([ev, nc])
    return run_dir, f"{nc.id}.json"


def test_verify_lenient_reproduces_then_strict_diverges_when_control_deleted(tmp_path):
    run_dir, nc_file = _persist_strict_run(tmp_path)

    # Lenient verify: the recorded SUPPORTED re-derives (the science re-check is skipped).
    rep = verify_run(run_dir)
    assert all(o.result == REPRODUCED for o in rep.outcomes)

    # TAMPER: delete the falsifying negative control from the append-only record.
    (run_dir / "evidence" / nc_file).unlink()

    # Strict verify now DIVERGES -- the SUPPORTED no longer re-derives without its control.
    strict = verify_run(run_dir, strict_science=True)
    assert any(o.result == DIVERGED for o in strict.outcomes)
    # Lenient verify still reproduces (faithful re-derivation, science re-check off).
    assert all(o.result == REPRODUCED for o in verify_run(run_dir).outcomes)


def test_verify_strict_diverges_when_discriminating_cases_tampered(tmp_path):
    # G2 tamper-evidence: strip the declared discriminating_cases from the recorded spec.json
    # after a strict SUPPORTED was stamped -> strict verify can no longer re-derive (G2 halts
    # the re-check) -> DIVERGED. Lenient verify is unaffected.
    run_dir, _nc = _persist_strict_run(tmp_path)
    assert all(o.result == REPRODUCED for o in verify_run(run_dir).outcomes)

    spec_path = run_dir / "spec.json"
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    raw["hypotheses"][0]["discriminating_cases"] = None  # TAMPER
    spec_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    strict = verify_run(run_dir, strict_science=True)
    assert any(o.result == DIVERGED for o in strict.outcomes)
    assert all(o.result == REPRODUCED for o in verify_run(run_dir).outcomes)


# --------------------------------------------------------------------------- #
# t1-godel(v4) regression -- the real recorded spec (~/research/t1-godel v4)
# --------------------------------------------------------------------------- #

# A faithful reconstruction of ~/research/t1-godel/runs/t1-godel/spec.json (version 4):
# two formal+threshold hypotheses (H1 injectivity, H2 recoverability), both exploratory,
# both with non_circularity attestations, novelty flags False, and (predating these guards)
# NO epistemic_kind / discriminating_cases / cost_metrics. The statements are verbatim.
_T1_GODEL_V4 = {
    "id": "t1-godel",
    "version": 4,
    "raw_proposal": {
        "background": "Molecular graphs can be serialized to integers. A Godel-style "
        "prime-power encoding promises an injective, recoverable mapping.",
        "goal": "H1 injectivity and H2 recoverability of a prime-power molecular encoding.",
        "method": "Canonically label, encode as prime-power factors, verify collisions + "
        "round-trip.",
        "expected_output": "Zero collisions (H1) and 100% round-trip (H2).",
    },
    "hypotheses": [
        {
            "id": "hyp-001",
            "statement": "H1 (injectivity): the Godel-style prime-power encoding assigns a "
            "distinct integer to every non-isomorphic molecule in the designed test set, so "
            "that the measured collision count over all canonically-labelled pairs equals "
            "exactly zero",
            "mode": "exploratory",
            "decision_rule": {
                "kind": "threshold",
                "expression": "SUPPORTED iff collision_count == 0",
                "params": {"statistic": "collision_count", "op": "==", "value": 0},
            },
            "referent": "formal",
            "non_circularity": "isomorphism decided by an independent brute-force permutation "
            "oracle, separate from the encoding under test",
            "novelty_result": False,
            "novelty_method": False,
        },
        {
            "id": "hyp-002",
            "statement": "H2 (recoverability): the decode procedure recovers the canonical "
            "graph from the integer for every molecule in the designed test set, so that the "
            "measured exact round-trip decode accuracy equals 100 percent",
            "mode": "exploratory",
            "decision_rule": {
                "kind": "threshold",
                "expression": "SUPPORTED iff roundtrip_decode_accuracy_pct == 100",
                "params": {"statistic": "roundtrip_decode_accuracy_pct", "op": "==", "value": 100},
            },
            "referent": "formal",
            "non_circularity": "decoded graph's isomorphism to input checked by the same "
            "independent oracle, not assumed by the decoder",
            "novelty_result": False,
            "novelty_method": False,
        },
    ],
    "method": {"approaches": ["prime-power graph encoding"], "tools": []},
    "target_claims": [
        {"id": "claim-001", "statement": "A unique integer per non-isomorphic molecule "
         "(supporting H1)", "answers": "hyp-001"},
        {"id": "claim-002", "statement": "A decode that recovers the canonical graph "
         "(supporting H2)", "answers": "hyp-002"},
    ],
}


def _t1_godel_v4_spec() -> Spec:
    return Spec.model_validate(_T1_GODEL_V4)


def test_t1_godel_v4_spec_gate_flags_g1_g2_g3_g4_on_both_hypotheses():
    spec = _t1_godel_v4_spec()
    findings = audit_spec_science(spec)
    by_hyp: dict[str, set[str]] = {}
    for f in findings:
        by_hyp.setdefault(f.hypothesis_id, set()).add(f.guard)
    # Both H1 and H2: formal+threshold+finding(default)+no-novelty -> G1; no discriminating
    # cases -> G2; the G3 reminder; exploratory+threshold -> G4.
    for hyp_id in ("hyp-001", "hyp-002"):
        assert {"G1", "G2", "G3", "G4"} <= by_hyp[hyp_id], hyp_id


def test_t1_godel_v4_strict_verdict_gate_halts_each_hypothesis(tmp_path):
    # H2 (round-trip == 100%) is decided by unique factorization -- a known theorem -> G1
    # would demote it to unit_test; both H1 and H2 lack discriminating cases (G2) and a
    # negative control (G3). A strict derive over a SUPPORTS evidence HALTS.
    spec = _t1_godel_v4_spec()
    h1 = spec.hypotheses[0]
    ev = _generated_evidence(spec.id, h1.id, point=0.0)  # collision_count == 0 -> SUPPORTS
    with pytest.raises(ValidityHalt):
        ClaimUpdater(spec, tmp_path, strict_science=True).update_claims_from_evidence([ev])


def test_t1_godel_v4_lenient_still_stamps_supported(tmp_path):
    # The lenient PRIMITIVE keeps producing the (under-powered) SUPPORTED -- backward compat.
    spec = _t1_godel_v4_spec()
    h1 = spec.hypotheses[0]
    ev = _generated_evidence(spec.id, h1.id, point=0.0)
    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])
    assert claims[0].status.value == "supported"


def test_t1_godel_v4_g5_fires_on_index_restatement_not_on_literal_statement():
    # Honest result: the LITERAL v4 statements are narrowly worded (collision_count /
    # round-trip), so G5 does NOT fire -- correct, the spec claims no practical size property.
    spec = _t1_godel_v4_spec()
    assert not [f for f in audit_spec_science(spec) if f.guard == "G5"]
    # The natural "molecular index" restatement (which the proposal implies) DOES trip G5,
    # surfacing the prime-power bit-length blowup.
    restated = Hypothesis(
        id="hyp-001",
        statement="the prime-power encoding yields a compact molecular index: one integer "
        "per non-isomorphic molecule",
        mode=HypothesisMode.EXPLORATORY,
        decision_rule=_threshold_rule(),
        referent="formal",
        non_circularity="independent oracle",
    )
    g5 = [f for f in audit_spec_science(_spec([restated])) if f.guard == "G5"]
    assert len(g5) == 1 and "index" in g5[0].message
