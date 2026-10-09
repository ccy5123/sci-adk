"""
RED-first: a verdict decided by a fixed pre-registered rule carries NO degree of belief.

The defect (a real run, 2026-10-09): for ``threshold`` and ``interval`` rules the
DecisionEngine wrote ``1 - exp(-|margin|)`` -- a monotone transform of a margin measured in
the statistic's own units -- under ``ConfidenceType.CREDENCE``, which the type defines as a
probability in [0, 1]. A SUPPORTED slope hypothesis recorded ``credence 0.0666`` (margin
0.0689) and a SUPPORTED correlation hypothesis ``credence 0.111`` (margin 0.1176): neither
number is a probability, and the two are not comparable. ``record.tex`` then printed
``Status: supported --- confidence 0.0666 (credence)``, and the paper session reads it.

The contract pinned here:

- threshold / interval verdicts carry ``ConfidenceType.RULE`` with no ``value`` and no
  ``level``; the margin (threshold) and the interval (interval rule) stay in ``basis``;
- a Bayesian verdict keeps its numeric posterior -- a probability the evidence carries;
- ``Confidence(type=RULE, value=...)`` is rejected, so the defect cannot be re-encoded;
- the record dump (``record.tex``) and the Markdown draft print no confidence number for a
  rule verdict, nor for a claim recorded BEFORE this change (a ``credence`` on a threshold /
  interval hypothesis) -- existing runs render cleanly without re-deriving;
- a pre-change claim still verifies REPRODUCED (verify compares status), and re-deriving it
  keeps the status and replaces the stale number with the value-less rule confidence.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pytest
from pydantic import ValidationError

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceLevel,
    ConfidenceType,
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
from sci_adk.loop.claim_updater import ClaimUpdater
from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
from sci_adk.loop.verify import REPRODUCED, verify_run
from sci_adk.render.paper import render_paper
from sci_adk.render.si import render_si_latex

_T0 = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 10, 8, 13, 0, 0, tzinfo=timezone.utc)
_SPEC_ID = "spec-rule-verdict"

_SLOPE_RULE = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="slope margin >= 0 => support",
    params={"statistic": "point", "op": ">=", "value": 0.0},
)
_CORRELATION_RULE = DecisionRule(
    kind=DecisionRuleKind.THRESHOLD,
    expression="rank correlation >= 0.5 => support",
    params={"statistic": "point", "op": ">=", "value": 0.5},
)
_INTERVAL_RULE = DecisionRule(
    kind=DecisionRuleKind.INTERVAL,
    expression="95% CI above 0 => support; below 0 => refute",
    params={"null_value": 0.0, "support_side": "above"},
)
_BAYES_RULE = DecisionRule(
    kind=DecisionRuleKind.BAYESIAN,
    expression="posterior odds >= 10 => support",
    params={"min_odds": 10.0},
)


# -- builders -----------------------------------------------------------------

def _hyp(hyp_id: str, rule: DecisionRule) -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        statement=f"the {hyp_id} effect is present",
        mode=HypothesisMode.CONFIRMATORY,
        decision_rule=rule,
    )


def _spec(*hyps: Hypothesis) -> Spec:
    return Spec(
        id=_SPEC_ID,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="method", expected_output="out"
        ),
        hypotheses=list(hyps),
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[
            TargetClaim(id=f"tc-{h.id}", statement="t", answers=h.id) for h in hyps
        ],
    )


def _measured(
    ev_id: str,
    hyp_id: str,
    *,
    point: Optional[float] = None,
    ci: Optional[List[float]] = None,
    posterior: Optional[float] = None,
    direction: BearingDirection = BearingDirection.SUPPORTS,
    created_at: datetime = _T0,
) -> EvidenceItem:
    """A measured-data result bearing on ``hyp_id`` (an empirical claim's honest input)."""
    return EvidenceItem(
        id=ev_id,
        created_at=created_at,
        spec_id=_SPEC_ID,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="analysis.py:1", data_source="measured"),
        result=Result(type="quantitative", point=point, ci=ci, posterior=posterior),
        bears_on=[Bearing(target_id=hyp_id, direction=direction)],
    )


def _evaluate(rule: DecisionRule, *items: EvidenceItem):
    pairs = [(ev, b) for ev in items for b in ev.bears_on]
    return DecisionEngine().evaluate(rule, EvidenceForHypothesis(pairs=pairs))


def _legacy_claim_json(
    hyp_id: str, ev_id: str, credence: float, basis: str
) -> dict:
    """A claim exactly as the engine wrote it BEFORE this change (the real run's shape)."""
    return {
        "id": f"claim-{hyp_id}",
        "spec_id": _SPEC_ID,
        "answers": hyp_id,
        "statement": f"the {hyp_id} effect is present",
        "status": "supported",
        "confidence": {
            "type": "credence",
            "value": credence,
            "level": None,
            "basis": basis,
        },
        "evidence_set": [{"evidence_id": ev_id, "role": "supporting"}],
        "scope_limitations": "",
        "mode": "confirmatory",
        "renders_to": None,
        "history": [
            {
                "at": "2026-10-09T03:53:56.230033Z",
                "from_status": "proposed",
                "to_status": "supported",
                "triggered_by": ev_id,
                "note": "Initial evaluation via DecisionEngine",
            }
        ],
    }


# The two real pre-change records: (hyp id, rule, recorded point, legacy credence,
# its 3-significant-figure rendering, the basis the engine wrote).
_LEGACY_CASES = [
    (
        "H1", _SLOPE_RULE, 0.068932, 0.06660985782888929, "0.0666",
        "threshold rule: statistic 'point'=0.068932 >= 0 is met "
        "(combine='latest', margin=0.068932)",
    ),
    (
        "H2", _CORRELATION_RULE, 0.617646, 0.11098897941358987, "0.111",
        "threshold rule: statistic 'point'=0.617646 >= 0.5 is met "
        "(combine='latest', margin=0.117646)",
    ),
]
_LEGACY_IDS = ["slope-0.0666", "correlation-0.111"]


def _status_line(tex: str) -> str:
    lines = [ln for ln in tex.splitlines() if "Status: supported" in ln]
    assert len(lines) == 1, f"expected exactly one status line, got {lines}"
    return lines[0]


# -- engine: deterministic rules emit a value-less RULE confidence --------------

def test_threshold_supported_verdict_carries_no_degree_of_belief():
    verdict = _evaluate(_SLOPE_RULE, _measured("ev-1", "H1", point=0.068932))

    assert verdict.direction == BearingDirection.SUPPORTS
    assert verdict.confidence.type == ConfidenceType.RULE
    assert verdict.confidence.value is None
    assert verdict.confidence.level is None
    # The margin is still reported -- in the statistic's own units, in the basis.
    assert "margin=0.068932" in verdict.confidence.basis


def test_threshold_refuted_verdict_carries_no_degree_of_belief():
    verdict = _evaluate(_CORRELATION_RULE, _measured("ev-1", "H2", point=0.31))

    assert verdict.direction == BearingDirection.REFUTES
    assert verdict.confidence.type == ConfidenceType.RULE
    assert verdict.confidence.value is None
    assert verdict.confidence.level is None
    assert "margin=0.19" in verdict.confidence.basis


@pytest.mark.parametrize(
    "ci, direction",
    [
        ([0.2, 0.8], BearingDirection.SUPPORTS),
        ([-0.8, -0.2], BearingDirection.REFUTES),
        ([-0.3, 0.5], BearingDirection.NEUTRAL),
    ],
    ids=["above-null", "below-null", "contains-null"],
)
def test_interval_verdict_carries_no_degree_of_belief(ci, direction):
    verdict = _evaluate(_INTERVAL_RULE, _measured("ev-1", "H3", ci=ci))

    assert verdict.direction == direction
    assert verdict.confidence.type == ConfidenceType.RULE
    assert verdict.confidence.value is None
    assert verdict.confidence.level is None
    # The interval itself is the reported uncertainty, in the basis.
    assert f"CI=[{ci[0]:.6g}, {ci[1]:.6g}]" in verdict.confidence.basis


def test_bayesian_verdict_keeps_its_numeric_posterior():
    """A posterior IS a probability the evidence carries -- it stays numeric."""
    verdict = _evaluate(_BAYES_RULE, _measured("ev-1", "H4", posterior=0.95))

    assert verdict.direction == BearingDirection.SUPPORTS
    assert verdict.confidence.type == ConfidenceType.POSTERIOR
    assert verdict.confidence.value == pytest.approx(0.95)


def test_unevaluable_threshold_rule_stays_graded_none():
    """An inconclusive verdict (the rule could not be applied) keeps GRADED/NONE."""
    verdict = _evaluate(_SLOPE_RULE, _measured("ev-1", "H1", point=None))

    assert verdict.direction == BearingDirection.INCONCLUSIVE
    assert verdict.confidence.type == ConfidenceType.GRADED
    assert verdict.confidence.level == ConfidenceLevel.NONE


@pytest.mark.parametrize(
    "kind, expected",
    [
        (DecisionRuleKind.THRESHOLD, "rule"),
        (DecisionRuleKind.INTERVAL, "rule"),
        (DecisionRuleKind.BAYESIAN, "posterior"),
        (DecisionRuleKind.PROOF, "graded"),
        (DecisionRuleKind.QUALITATIVE, "graded"),
    ],
    ids=lambda v: getattr(v, "value", v),
)
def test_intended_confidence_type_per_kind(kind, expected):
    assert DecisionEngine().intended_confidence_type(kind).value == expected


def test_rule_kinds_constant_matches_the_engine_mapping():
    """Render's legacy suppression keys on the same kinds the engine emits RULE for."""
    from sci_adk.core.claim import RULE_CONFIDENCE_KINDS

    engine = DecisionEngine()
    emits_rule = {
        k for k in DecisionRuleKind
        if engine.intended_confidence_type(k) == ConfidenceType.RULE
    }
    assert emits_rule == set(RULE_CONFIDENCE_KINDS)


# -- the Confidence model: RULE carries neither a value nor a level ------------

def test_rule_confidence_is_valid_without_value_or_level():
    c = Confidence(type=ConfidenceType.RULE, basis="threshold rule: met (margin=0.07)")
    assert c.value is None and c.level is None
    dumped = c.model_dump(mode="json")
    assert dumped["type"] == "rule"
    assert Confidence.model_validate(dumped) == c


def test_rule_confidence_rejects_a_numeric_value():
    with pytest.raises(ValidationError, match="no degree of belief"):
        Confidence(type=ConfidenceType.RULE, value=0.0666, basis="threshold rule: met")


def test_rule_confidence_rejects_a_graded_level():
    with pytest.raises(ValidationError, match="no degree of belief"):
        Confidence(
            type=ConfidenceType.RULE, level=ConfidenceLevel.STRONG, basis="threshold rule"
        )


# -- render: no confidence number for a rule verdict, old or new ----------------

@pytest.mark.parametrize(
    "hyp_id, rule, point, credence, shown, basis", _LEGACY_CASES, ids=_LEGACY_IDS
)
def test_record_dump_of_a_pre_change_claim_prints_no_confidence_number(
    hyp_id, rule, point, credence, shown, basis
):
    """An existing run renders cleanly WITHOUT re-deriving: the stale credence on a
    threshold-rule claim is not printed; the basis (with the margin) still is."""
    spec = _spec(_hyp(hyp_id, rule))
    ev = _measured("ev-1", hyp_id, point=point)
    claim = Claim.model_validate(_legacy_claim_json(hyp_id, "ev-1", credence, basis))

    tex = render_si_latex(spec, [claim], [ev])

    assert "confidence" not in _status_line(tex)
    assert shown not in tex
    assert "credence" not in tex
    assert "margin=" in tex  # the basis line is still there


def test_record_dump_of_a_pre_change_interval_claim_prints_no_confidence_number():
    spec = _spec(_hyp("H3", _INTERVAL_RULE))
    ev = _measured("ev-1", "H3", ci=[0.2, 0.8])
    claim = Claim.model_validate(
        _legacy_claim_json(
            "H3", "ev-1", 0.2834687,
            "interval rule: CI=[0.2, 0.8] above null_value=0 "
            "(support_side='above', combine='latest')",
        )
    )

    tex = render_si_latex(spec, [claim], [ev])

    assert "confidence" not in _status_line(tex)
    assert "0.283" not in tex
    assert "credence" not in tex


def test_record_dump_of_a_rule_verdict_prints_no_confidence():
    spec = _spec(_hyp("H1", _SLOPE_RULE))
    ev = _measured("ev-1", "H1", point=0.068932)
    verdict = _evaluate(_SLOPE_RULE, ev)
    claim = Claim(
        id="claim-H1", spec_id=_SPEC_ID, answers="H1", statement="the H1 effect is present",
        status=ClaimStatus.SUPPORTED, confidence=verdict.confidence,
        mode=HypothesisMode.CONFIRMATORY,
    )

    tex = render_si_latex(spec, [claim], [ev])

    assert "confidence" not in _status_line(tex)
    assert "(rule)" not in tex
    assert "margin=0.068932" in tex


def test_record_dump_still_shows_a_genuine_posterior():
    spec = _spec(_hyp("H4", _BAYES_RULE))
    ev = _measured("ev-1", "H4", posterior=0.92)
    claim = Claim(
        id="claim-H4", spec_id=_SPEC_ID, answers="H4", statement="the H4 effect is present",
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(
            type=ConfidenceType.POSTERIOR, value=0.92, basis="bayesian rule: odds 11.5"
        ),
        mode=HypothesisMode.CONFIRMATORY,
    )

    tex = render_si_latex(spec, [claim], [ev])

    assert "confidence 0.92 (posterior)" in _status_line(tex)


def test_record_dump_shows_a_zero_posterior():
    """A posterior of 0 is a real probability, not an empty default: it is shown. (The old
    suppression of any 0 rested on the premise that a 0 was a deterministic verdict's
    placeholder; rule verdicts are now recognized by type and rule kind instead.)"""
    spec = _spec(_hyp("H4", _BAYES_RULE))
    ev = _measured("ev-1", "H4", posterior=0.0, direction=BearingDirection.REFUTES)
    claim = Claim(
        id="claim-H4", spec_id=_SPEC_ID, answers="H4", statement="the H4 effect is present",
        status=ClaimStatus.REFUTED,
        confidence=Confidence(
            type=ConfidenceType.POSTERIOR, value=0.0, basis="bayesian rule: posterior=0"
        ),
        mode=HypothesisMode.CONFIRMATORY,
    )

    tex = render_si_latex(spec, [claim], [ev])

    status = [ln for ln in tex.splitlines() if "Status: refuted" in ln]
    assert status and "confidence 0 (posterior)" in status[0]


def test_markdown_draft_follows_the_same_display_rule():
    """The library Markdown draft prints the same status line policy as the record dump."""
    legacy = Claim.model_validate(
        _legacy_claim_json("H1", "ev-1", _LEGACY_CASES[0][3], _LEGACY_CASES[0][5])
    )
    posterior = Claim(
        id="claim-H4", spec_id=_SPEC_ID, answers="H4", statement="the H4 effect is present",
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(
            type=ConfidenceType.POSTERIOR, value=0.92, basis="bayesian rule: odds 11.5"
        ),
        mode=HypothesisMode.CONFIRMATORY,
    )
    spec = _spec(_hyp("H1", _SLOPE_RULE), _hyp("H4", _BAYES_RULE))
    evidence = [
        _measured("ev-1", "H1", point=0.068932),
        _measured("ev-2", "H4", posterior=0.92),
    ]

    md = render_paper(spec, [legacy, posterior], evidence)

    assert "0.0666" not in md
    assert "credence" not in md
    assert "confidence 0.92 (posterior)" in md


# -- re-derivation: an old claim still reproduces; re-deriving drops the number ---

def _write_legacy_run(tmp_path: Path, hyp_id: str, rule: DecisionRule, point: float,
                      credence: float, basis: str):
    spec = _spec(_hyp(hyp_id, rule))
    ev = _measured("ev-1", hyp_id, point=point)
    run_dir = tmp_path / "runs" / _SPEC_ID
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "claims").mkdir()
    (run_dir / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    (run_dir / "evidence" / "ev-1.json").write_text(
        json.dumps(ev.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    (run_dir / "claims" / f"claim-{hyp_id}.json").write_text(
        json.dumps(_legacy_claim_json(hyp_id, "ev-1", credence, basis), indent=2),
        encoding="utf-8",
    )
    return spec, ev, run_dir


@pytest.mark.parametrize(
    "hyp_id, rule, point, credence, shown, basis", _LEGACY_CASES, ids=_LEGACY_IDS
)
def test_pre_change_claim_still_verifies_reproduced(
    tmp_path, hyp_id, rule, point, credence, shown, basis
):
    """verify compares STATUS: a claim recorded with the old credence still reproduces."""
    _, _, run_dir = _write_legacy_run(tmp_path, hyp_id, rule, point, credence, basis)

    report = verify_run(run_dir)

    assert [o.result for o in report.outcomes] == [REPRODUCED]
    assert report.all_reproduced


@pytest.mark.parametrize(
    "hyp_id, rule, point, credence, shown, basis", _LEGACY_CASES, ids=_LEGACY_IDS
)
def test_rederiving_a_pre_change_claim_keeps_status_and_drops_the_number(
    tmp_path, hyp_id, rule, point, credence, shown, basis
):
    spec, ev, run_dir = _write_legacy_run(tmp_path, hyp_id, rule, point, credence, basis)

    claims = ClaimUpdater(spec, tmp_path).update_claims_from_evidence([ev])

    claim = claims[0]
    assert claim.status == ClaimStatus.SUPPORTED
    assert len(claim.history) == 1  # same status -> no spurious StatusChange (D5)
    assert claim.confidence.type == ConfidenceType.RULE
    assert claim.confidence.value is None
    assert claim.confidence.basis == basis  # same rule, same record -> same basis
    on_disk = json.loads(
        (run_dir / "claims" / f"claim-{hyp_id}.json").read_text(encoding="utf-8")
    )
    assert on_disk["confidence"]["type"] == "rule"
    assert on_disk["confidence"]["value"] is None
    # ... and the re-derived record still verifies.
    assert verify_run(run_dir).all_reproduced


def test_a_new_rule_verdict_does_not_inherit_a_level_from_the_previous_one(tmp_path):
    """A claim that was inconclusive (GRADED/NONE) and is now decided by its rule must
    not carry the old level into the value-less RULE confidence."""
    spec = _spec(_hyp("H1", _SLOPE_RULE))
    updater = ClaimUpdater(spec, tmp_path)
    no_point = _measured("ev-0", "H1", point=None, created_at=_T0)
    first = updater.update_claims_from_evidence([no_point])[0]
    assert first.confidence.type == ConfidenceType.GRADED  # inconclusive

    decided = _measured("ev-1", "H1", point=0.068932, created_at=_T1)
    second = updater.update_claims_from_evidence([no_point, decided])[0]

    assert second.status == ClaimStatus.SUPPORTED
    assert second.confidence.type == ConfidenceType.RULE
    assert second.confidence.level is None
    assert second.confidence.value is None
