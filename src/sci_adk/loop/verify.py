"""
``sci-adk verify`` -- the headless, read-only belief audit (F6).

design/rigor-shell-architecture.md §6.2 / §7.1 / §8 F6: a third party re-derives the
belief from the *recorded* run and confirms it follows from the record -- WITHOUT
Claude Code. ``verify_run`` is the kernel-side function behind the CLI verb.

What it does, per hypothesis that has a recorded ``Claim``:

  1. Re-apply the FROZEN ``DecisionRule`` to the RECORDED Evidence via
     ``DecisionEngine.evaluate(rule, results)`` -- the SAME pure call ``ClaimUpdater``
     makes, but here with NO persistence and NO claim mutation:
       - numeric kinds (threshold/bayesian/interval) re-evaluate autonomously;
       - non-numeric kinds (proof/qualitative) get a ``RecordedJudge(run_dir)``
         injected, so the engine re-reads the recorded ``verdicts/*.json`` trail and
         re-applies the frozen rule + the F2 gate -- deterministic, NO LLM. A
         non-numeric hypothesis whose trail is absent -> the engine returns
         ``inconclusive`` (F2) -> reported UNRESOLVED ("not reproducible from record").
  2. Map the re-derived ``Verdict`` to a ``ClaimStatus`` through the SINGLE public
     source of truth ``claim_updater.status_for_verdict`` (the direction->status
     mapping + the CONTESTED override on the raw bearings) that ``ClaimUpdater`` also
     uses to persist -- so a faithful record reproduces exactly, with no duplicated
     derivation to drift.
  3. Compare the re-derived status to the recorded ``Claim.status``:
       - same binding status            -> REPRODUCED
       - re-derived inconclusive        -> UNRESOLVED (record does not re-derive)
       - any other mismatch             -> DIVERGED

The run is reproduced iff every recorded claim is REPRODUCED -- the verb's exit code.

Read-only invariants (any violation = failure):
  - re-runs NO experiment (no ``ExperimentFn`` is invoked),
  - calls NO LLM / capability (the only judge is the deterministic ``RecordedJudge``),
  - overwrites NO recorded file (re-derivation is entirely in memory).

The report also carries the :func:`sci_adk.provenance.record_digest` of the run, the
tamper-evidence companion a third party compares against a trusted baseline.

This module is KERNEL-side: it reads only the single append-only Evidence log + spec
+ verdict trails, and uses only deterministic deserialization (``RecordedJudge`` is
kernel-side pure JSON; no ``kernel -> adapter`` import).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import BearingDirection, EvidenceItem
from sci_adk.core.spec import Hypothesis, Spec
from sci_adk.core.validity import ValidityHalt, check_digitized_adequacy
from sci_adk.loop.claim_updater import counted_evidence, status_for_verdict
from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
from sci_adk.loop.recorded_judge import RecordedJudge
from sci_adk.provenance import record_digest

# Per-hypothesis audit results. Strings (not an enum) keep the report trivially
# printable/serializable; the set is closed and small.
REPRODUCED = "REPRODUCED"
DIVERGED = "DIVERGED"
UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class VerifyOutcome:
    """The audit result for one recorded Claim (one hypothesis).

    Attributes:
        hypothesis_id: the hypothesis the recorded Claim answers.
        recorded_status: the ``Claim.status`` read from ``claims/*.json``.
        rederived_status: the status re-derived from the frozen rule + recorded
            Evidence/trail (``None`` only if the engine could not produce one, which
            it always can -- inconclusive is a status-bearing verdict).
        result: ``REPRODUCED`` | ``DIVERGED`` | ``UNRESOLVED``.
        rederived_basis: the re-derived ``Verdict.confidence.basis`` (the audit's
            own justification, distinct from the recorded claim's basis).
    """

    hypothesis_id: str
    recorded_status: ClaimStatus
    rederived_status: Optional[ClaimStatus]
    result: str
    rederived_basis: str


@dataclass(frozen=True)
class VerifyReport:
    """The outcome of a headless verify over a run dir.

    Attributes:
        spec_id: the recorded Spec id.
        outcomes: one :class:`VerifyOutcome` per recorded Claim.
        digest: the record digest (tamper-evidence companion, §8 F6).
        all_reproduced: True iff every recorded claim REPRODUCED (the exit gate).
    """

    spec_id: str
    outcomes: List[VerifyOutcome]
    digest: str
    all_reproduced: bool = field(default=False)


def verify_run(run_dir: Path) -> VerifyReport:
    """Re-derive belief from the recorded run and compare it to the recorded Claims.

    PURE + READ-ONLY: re-applies the frozen ``DecisionRule`` to the recorded Evidence
    (numeric autonomously; non-numeric via ``RecordedJudge`` re-reading the recorded
    trails + the F2 gate), entirely in memory. No experiment is re-run, no LLM is
    called, and no recorded file is modified.

    Args:
        run_dir: an existing ``runs/<spec.id>/`` directory.

    Returns:
        A :class:`VerifyReport` -- inspect ``all_reproduced`` for the CI gate.

    Raises:
        FileNotFoundError: if ``spec.json`` is absent.
        ValueError: if a recorded artifact is malformed (RecordedJudge / loaders
            re-raise as a clear, file-naming ValueError).
    """
    # @MX:ANCHOR: [AUTO] the single headless re-derivation entry (F6) -- a third party
    #   re-derives belief from the record (numeric AND non-numeric) without Claude Code.
    # @MX:REASON: [AUTO] the CLI `verify` verb and the verify test suites call this; it
    #   owns the READ-ONLY + no-LLM + no-re-run audit contract and reuses the engine's
    #   pure evaluate() + ClaimUpdater's status mapping so a faithful record reproduces
    #   exactly. Persisting anything here, or diverging from the updater's mapping,
    #   would either mutate the audited record or produce false DIVERGED/REPRODUCED.
    run_dir = Path(run_dir)

    spec = _load_spec(run_dir)
    evidence = _load_evidence(run_dir)
    recorded_claims = _load_claims(run_dir)

    # The engine is pure and stateless; injecting RecordedJudge lets the non-numeric
    # kinds re-derive from the recorded trails (deterministic, no LLM). The numeric
    # kinds never touch the judge.
    engine = DecisionEngine(judge=RecordedJudge(run_dir))

    hyp_by_id: Dict[str, Hypothesis] = {h.id: h for h in spec.hypotheses}

    outcomes: List[VerifyOutcome] = []
    for hyp_id, claim in sorted(recorded_claims.items()):
        hypothesis = hyp_by_id.get(hyp_id)
        if hypothesis is None:
            # A recorded claim whose hypothesis is absent from the (frozen) Spec: the
            # record is internally inconsistent -- the belief cannot be re-derived from
            # this Spec version, so it does not reproduce.
            outcomes.append(
                VerifyOutcome(
                    hypothesis_id=hyp_id,
                    recorded_status=claim.status,
                    rederived_status=None,
                    result=DIVERGED,
                    rederived_basis=(
                        "recorded claim references a hypothesis absent from spec.json "
                        "(cannot re-derive belief from this Spec version)"
                    ),
                )
            )
            continue
        outcomes.append(_audit_hypothesis(engine, hypothesis, evidence, claim))

    all_reproduced = bool(outcomes) and all(o.result == REPRODUCED for o in outcomes)
    return VerifyReport(
        spec_id=spec.id,
        outcomes=outcomes,
        digest=record_digest(run_dir),
        all_reproduced=all_reproduced,
    )


# -- per-hypothesis re-derivation (mirrors ClaimUpdater, WITHOUT persistence) --

def _audit_hypothesis(
    engine: DecisionEngine,
    hypothesis: Hypothesis,
    evidence: List[EvidenceItem],
    recorded_claim: Claim,
) -> VerifyOutcome:
    """Re-derive one hypothesis's belief and compare it to its recorded Claim.

    Mirrors ``ClaimUpdater._evaluate_hypothesis`` (build ``EvidenceForHypothesis`` from
    the bearings on this hypothesis, call ``engine.evaluate``, then map the verdict via
    the shared public ``status_for_verdict``) but performs NO load-or-create and NO
    persistence -- it only re-derives and compares.

    To re-derive FAITHFULLY it applies the same belief-time filters the updater does:
    proposed digitized items are EXCLUDED (figure-digitization §5), and the digitized
    self-certification gate is re-checked over the COUNTED set. A recorded binding Claim
    whose only support is a proposed / unverified / self-certified digitized item
    therefore does NOT reproduce -- the audit reports it (UNRESOLVED when there is
    nothing left to count, DIVERGED when a counted digitized fails the verifier check).
    """
    relevant = [
        ev for ev in evidence
        if any(b.target_id == hypothesis.id for b in ev.bears_on)
    ]
    # Exclude non-evidence-grade items (proposed digitized) exactly as the persister
    # does (shared ``counted_evidence``) -- a faithful re-derivation must not count what
    # the updater would not have counted.
    counted = counted_evidence(relevant)
    results = EvidenceForHypothesis(
        pairs=[
            (ev, b)
            for ev in counted
            for b in ev.bears_on
            if b.target_id == hypothesis.id
        ]
    )

    verdict = engine.evaluate(hypothesis.decision_rule, results)

    # Re-apply the digitized self-certification gate over the counted set. If a counted
    # digitized item is unverified / self-certified, the recorded Claim could not have
    # been validly derived (the updater would have HALTED) -- so the record's belief does
    # NOT follow from a properly-verified record: report DIVERGED. This is read-only (no
    # raise escapes the audit) -- the gate is consulted, not enforced as a stop.
    try:
        check_digitized_adequacy(hypothesis, counted, verdict.direction)
    except ValidityHalt as halt:
        return VerifyOutcome(
            hypothesis_id=hypothesis.id,
            recorded_status=recorded_claim.status,
            rederived_status=None,
            result=DIVERGED,
            rederived_basis=(
                "recorded claim relies on a digitized item that fails the "
                f"independent-verification gate (not reproducible from record): {halt.reason}"
            ),
        )

    raw_directions = {b.direction for _, b in results.pairs}
    # SINGLE source of truth (Fix 1): the SAME public derivation ClaimUpdater uses to
    # persist -- mapping + CONTESTED override -- so a faithful record re-derives exactly
    # the status that was recorded (no replayed/duplicated logic to drift).
    rederived_status = status_for_verdict(verdict, raw_directions)

    result = _classify(verdict.direction, rederived_status, recorded_claim.status)
    return VerifyOutcome(
        hypothesis_id=hypothesis.id,
        recorded_status=recorded_claim.status,
        rederived_status=rederived_status,
        result=result,
        rederived_basis=verdict.confidence.basis,
    )


def _classify(
    direction: BearingDirection,
    rederived_status: ClaimStatus,
    recorded_status: ClaimStatus,
) -> str:
    """REPRODUCED / DIVERGED / UNRESOLVED for one hypothesis.

    UNRESOLVED is decided by the re-derived *direction* being ``inconclusive`` (the F2
    "no recorded trail / cannot re-derive" outcome for a non-numeric rule), reported
    distinctly even when the recorded claim is also PROPOSED -- because "the record
    does not let me re-derive this belief" is a different audit finding from "I
    re-derived the same belief". An inconclusive re-derivation is never REPRODUCED, so
    it fails the CI gate. Any non-inconclusive mismatch is DIVERGED.
    """
    if direction == BearingDirection.INCONCLUSIVE:
        return UNRESOLVED
    return REPRODUCED if rederived_status == recorded_status else DIVERGED


# -- read-only loaders -------------------------------------------------------

def _load_spec(run_dir: Path) -> Spec:
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"no spec.json found in run dir: {run_dir}")
    return Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))


def _load_evidence(run_dir: Path) -> List[EvidenceItem]:
    """Load the recorded append-only Evidence log (read-only)."""
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return []
    items: List[EvidenceItem] = []
    for path in sorted(evidence_dir.glob("*.json")):
        items.append(
            EvidenceItem.model_validate(json.loads(path.read_text(encoding="utf-8")))
        )
    return items


def _load_claims(run_dir: Path) -> Dict[str, Claim]:
    """Load recorded Claims keyed by the hypothesis id each answers (read-only)."""
    claims_dir = run_dir / "claims"
    if not claims_dir.is_dir():
        return {}
    claims: Dict[str, Claim] = {}
    for path in sorted(claims_dir.glob("*.json")):
        claim = Claim.model_validate(json.loads(path.read_text(encoding="utf-8")))
        claims[claim.answers] = claim
    return claims


__all__ = [
    "REPRODUCED",
    "DIVERGED",
    "UNRESOLVED",
    "VerifyOutcome",
    "VerifyReport",
    "verify_run",
]
