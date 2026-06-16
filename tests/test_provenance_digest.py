"""
RED-first: the provenance ``record_digest`` -- a deterministic tamper-evidence
primitive over the recorded run.

design/rigor-shell-architecture.md §8 F6: ``verify`` is the headless re-derivation
of belief from the record; the digest is the tamper-evidence companion -- a third
party compares it to a trusted/published baseline. It MUST cover the verdict trails
too (verify trusts the trails as given, so trail tampering must change the digest),
plus spec.json and the evidence log.

Scope is intentionally minimal (resist a broad provenance subsystem): a single
``record_digest(run_dir) -> str`` (sha256, hex) over a canonical serialization of
``spec.json`` + sorted ``evidence/*.json`` + sorted ``verdicts/*.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from sci_adk.loop.verdict import (
    ChiefVerdict,
    PanelVerdict,
    VerdictProvenance,
    VerdictTrail,
)
from sci_adk.provenance import record_digest


def _spec(spec_id: str = "dig", hyp_id: str = "hyp-1") -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="b", goal="g", method="m", expected_output="o"
        ),
        hypotheses=[
            Hypothesis(
                id=hyp_id,
                statement="claim under test",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= 0.9 => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp_id)],
    )


def _write_spec(run_dir: Path, spec: Spec) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_evidence(run_dir: Path, item: EvidenceItem) -> None:
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / f"{item.id}.json").write_text(
        json.dumps(item.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _evidence(item_id: str = "ev-1", point: float = 0.95, hyp_id: str = "hyp-1") -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        spec_id="dig",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
    )


def _write_verdict(run_dir: Path, hyp_id: str, *, basis: str = "decisive under R",
                   expr: str = "R") -> None:
    trail = VerdictTrail(
        hypothesis_id=hyp_id,
        rule_kind="proof",
        rubric_expression=expr,
        rubric_params=None,
        panel=[PanelVerdict(direction=BearingDirection.SUPPORTS,
                            level="strong", basis="panelist")],
        chief=ChiefVerdict(direction=BearingDirection.SUPPORTS,
                           level="strong", basis=basis),
        provenance=VerdictProvenance(spec_version=1, timestamp="2026-06-16T00:00:00Z"),
    )
    vdir = run_dir / "verdicts"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{hyp_id}.json").write_text(
        json.dumps(trail.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def test_record_digest_is_hex_sha256(tmp_path):
    run_dir = tmp_path / "runs" / "dig"
    _write_spec(run_dir, _spec())
    _write_evidence(run_dir, _evidence())
    digest = record_digest(run_dir)
    assert isinstance(digest, str)
    assert len(digest) == 64
    int(digest, 16)  # raises if not hex


def test_record_digest_is_deterministic(tmp_path):
    run_dir = tmp_path / "runs" / "dig"
    _write_spec(run_dir, _spec())
    _write_evidence(run_dir, _evidence())
    _write_verdict(run_dir, "hyp-1")
    assert record_digest(run_dir) == record_digest(run_dir)


def test_record_digest_independent_of_key_order_and_whitespace(tmp_path):
    # The digest canonicalizes via the typed models, so re-formatting the on-disk
    # JSON (whitespace / key order) must NOT change the digest -- only content does.
    a = tmp_path / "runs" / "a"
    b = tmp_path / "runs" / "b"
    spec = _spec()
    ev = _evidence()
    _write_spec(a, spec)
    _write_evidence(a, ev)
    # b: same content, but written compact + with shuffled top-level keys.
    b.mkdir(parents=True, exist_ok=True)
    spec_blob = spec.model_dump(mode="json")
    shuffled = {k: spec_blob[k] for k in reversed(list(spec_blob.keys()))}
    (b / "spec.json").write_text(json.dumps(shuffled), encoding="utf-8")
    (b / "evidence").mkdir(parents=True, exist_ok=True)
    ev_blob = ev.model_dump(mode="json")
    (b / "evidence" / "ev-1.json").write_text(
        json.dumps({k: ev_blob[k] for k in reversed(list(ev_blob.keys()))}),
        encoding="utf-8",
    )
    assert record_digest(a) == record_digest(b)


def test_record_digest_changes_when_evidence_changes(tmp_path):
    run_dir = tmp_path / "runs" / "dig"
    _write_spec(run_dir, _spec())
    _write_evidence(run_dir, _evidence(point=0.95))
    before = record_digest(run_dir)
    _write_evidence(run_dir, _evidence(point=0.10))  # tamper the recorded statistic
    after = record_digest(run_dir)
    assert before != after


def test_record_digest_changes_when_verdict_trail_changes(tmp_path):
    # The load-bearing requirement: the digest MUST cover the verdict trails, so a
    # tampered trail is caught (verify trusts the trails as given).
    run_dir = tmp_path / "runs" / "dig"
    _write_spec(run_dir, _spec())
    _write_evidence(run_dir, _evidence())
    _write_verdict(run_dir, "hyp-1", basis="original decisive reasoning")
    before = record_digest(run_dir)
    _write_verdict(run_dir, "hyp-1", basis="TAMPERED decisive reasoning")
    after = record_digest(run_dir)
    assert before != after


def test_record_digest_changes_when_spec_changes(tmp_path):
    run_dir = tmp_path / "runs" / "dig"
    _write_spec(run_dir, _spec())
    _write_evidence(run_dir, _evidence())
    before = record_digest(run_dir)
    # Tamper the frozen rule's threshold value on disk.
    spec2 = _spec()
    blob = spec2.model_dump(mode="json")
    blob["hypotheses"][0]["decision_rule"]["params"]["value"] = 0.1
    (run_dir / "spec.json").write_text(json.dumps(blob, indent=2), encoding="utf-8")
    after = record_digest(run_dir)
    assert before != after


def test_record_digest_missing_spec_raises(tmp_path):
    run_dir = tmp_path / "runs" / "empty"
    run_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises((FileNotFoundError, ValueError)):
        record_digest(run_dir)
