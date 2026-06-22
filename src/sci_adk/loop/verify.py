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
from typing import Dict, List, Literal, Optional

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import BearingDirection, EvidenceItem, EvidenceKind
from sci_adk.core.spec import Hypothesis, Spec
from sci_adk.core.validity import (
    ValidityHalt,
    check_digitized_adequacy,
    derive_novelty_status,
)
from sci_adk.loop.claim_updater import counted_evidence, status_for_verdict
from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
from sci_adk.loop.recorded_judge import RecordedJudge
from sci_adk.provenance import record_digest
from sci_adk.render.consistency import (
    LatexRefReport,
    check_latex_ref_consistency,
)
from sci_adk.render.factref import find_unresolved_factrefs
from sci_adk.render.paper import check_paper_tool_vocabulary

# The rendered paper documents verify re-checks for internal \ref<->\label integrity
# (design/paper-figures-and-si.md D4, Phase 3). Both are checked WITHIN themselves; the
# cross-DOCUMENT main<->SI \ref is DEFERRED (it needs the LaTeX xr package + a
# compile-order dependency). A document absent from paper/ is simply skipped.
_PAPER_DOCS: tuple[str, ...] = ("draft.tex", "si.tex")

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
        all_reproduced: True iff every recorded claim REPRODUCED -- the CLAIMS-only
            signal. Its meaning is UNCHANGED by Phase 3 (existing callers read it as the
            belief-reproduction signal); the paper gate lives in the fields below.
        paper_consistency: per-paper-document (``draft.tex`` / ``si.tex``) internal
            ``\\ref``<->``\\label`` reports (D4, Phase 3), keyed by file name. EMPTY when
            the run has no ``paper/`` directory (or neither document is present).
        paper_consistent: True iff EVERY present paper document's report is ``ok`` --
            and True (vacuously) when there is no paper to check. The paper HARD gate.
        paper_factrefs: per-paper-document residual ``\\evval``/``\\status`` macros (the
            record-fidelity fact markup), keyed by file name. A rendered ``.tex`` should
            contain NONE -- the engine substitutes them all at render time -- so a residual
            means substitution was bypassed or the ``.tex`` was hand-edited (a fidelity
            divergence). EMPTY when clean / no paper.
        paper_factref_clean: True iff no paper document carries a residual factref macro
            (and True vacuously with no paper). Part of the HARD gate.
        paper_tool_vocab: tool-vocabulary leaks (§10) found in the PAPER (``draft.tex``
            only -- the SI is the record dump and is EXEMPT): phrases/words that name the
            sci-adk machinery instead of the science (``sci-adk``, ``frozen Spec``,
            ``verdict``, ``Evidence record``, ...). EMPTY when the paper reads as
            tool-agnostic science / no paper.
        paper_tool_clean: True iff the paper carries no tool-vocabulary leak (and True
            vacuously with no draft.tex). Part of the HARD gate.
        passed: the COMBINED exit gate -- ``all_reproduced and paper_consistent and
            paper_factref_clean and paper_tool_clean``. This is what the CLI exits on;
            ``all_reproduced`` alone is the claim signal.
    """

    spec_id: str
    outcomes: List[VerifyOutcome]
    digest: str
    all_reproduced: bool = field(default=False)
    paper_consistency: Dict[str, LatexRefReport] = field(default_factory=dict)
    paper_consistent: bool = field(default=True)
    paper_factrefs: Dict[str, List[str]] = field(default_factory=dict)
    paper_factref_clean: bool = field(default=True)
    paper_tool_vocab: List[str] = field(default_factory=list)
    paper_tool_clean: bool = field(default=True)
    passed: bool = field(default=False)


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

    # Novelty decisions (bears_on=[]) never enter the engine, but the novelty claim
    # re-derivation needs them: a SUPPORTED novelty claim re-derives only if the record
    # still holds a *found_nothing* prior-art decision (B-replace). Gather once.
    novelty_decisions = [
        ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
    ]

    outcomes: List[VerifyOutcome] = []
    for claim_id, claim in sorted(recorded_claims.items()):
        hyp_id = claim.answers
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
        if _is_novelty_claim(claim):
            # Novelty claim (B-replace, 2-kind): re-derive its status by RULE
            # (``derive_novelty_status`` over the recorded novelty decisions for the
            # claim's KIND), NOT via the experiment DecisionEngine. The kind is parsed from
            # the claim id (``claim-novelty-{result,method}-<hyp>``). A deleted/tampered
            # found_nothing decision for that kind makes the recorded SUPPORTED novelty
            # claim no longer re-derive -> DIVERGED.
            kind = _novelty_kind_of(claim)
            outcomes.append(
                _audit_novelty_claim(hypothesis, kind, claim, novelty_decisions)
            )
            continue
        outcomes.append(
            _audit_hypothesis(engine, hypothesis, evidence, claim)
        )

    all_reproduced = bool(outcomes) and all(o.result == REPRODUCED for o in outcomes)

    # Phase 3 (D4): re-check the RENDERED paper's internal \ref<->\label integrity, as a
    # third party would -- READ-ONLY (read each .tex; never recompile, never write, no
    # LLM). draft.tex AND si.tex, each WITHIN itself. A document not on disk is skipped;
    # a run with no paper/ -> empty map -> paper_consistent True (gate unchanged).
    paper_consistency = _check_paper_consistency(run_dir)
    paper_consistent = all(rep.ok for rep in paper_consistency.values())

    # Fidelity gate (the "moved line"): a rendered paper's record-derived facts are
    # written as \evval/\status macros that the engine substitutes at render time, so a
    # residual macro in the .tex means substitution was bypassed / the .tex was edited.
    # READ-ONLY, no recompile, no LLM -- the same third-party spirit as the ref/label check.
    paper_factrefs = _check_paper_factrefs(run_dir)
    paper_factref_clean = not any(paper_factrefs.values())

    # Tool-vocabulary gate (§10): the PAPER (draft.tex only -- the SI is exempt) must read
    # as tool-agnostic science. READ-ONLY, no recompile, no LLM.
    paper_tool_vocab = _check_paper_tool_vocab(run_dir)
    paper_tool_clean = not paper_tool_vocab

    return VerifyReport(
        spec_id=spec.id,
        outcomes=outcomes,
        digest=record_digest(run_dir),
        all_reproduced=all_reproduced,
        paper_consistency=paper_consistency,
        paper_consistent=paper_consistent,
        paper_factrefs=paper_factrefs,
        paper_factref_clean=paper_factref_clean,
        paper_tool_vocab=paper_tool_vocab,
        paper_tool_clean=paper_tool_clean,
        passed=(
            all_reproduced
            and paper_consistent
            and paper_factref_clean
            and paper_tool_clean
        ),
    )


# -- per-hypothesis re-derivation (mirrors ClaimUpdater, WITHOUT persistence) --

def _audit_hypothesis(
    engine: DecisionEngine,
    hypothesis: Hypothesis,
    evidence: List[EvidenceItem],
    recorded_claim: Claim,
) -> VerifyOutcome:
    """Re-derive one hypothesis's EXPERIMENT belief and compare it to its recorded Claim.

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

    Novelty is audited SEPARATELY (B-replace): the novelty claim ``claim-novelty-<hyp>``
    is re-derived by rule in :func:`_audit_novelty_claim`, not here -- this path is the
    EXPERIMENT claim only.
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


def _is_novelty_claim(claim: Claim) -> bool:
    """True iff ``claim`` is a novelty claim (id ``claim-novelty-{result,method}-<hyp>``).

    Both 2-kind ids share the ``claim-novelty-`` prefix, so this prefix test still
    identifies a novelty claim of either kind. The specific kind is parsed by
    :func:`_novelty_kind_of`.
    """
    return claim.id.startswith("claim-novelty-")


def _novelty_kind_of(claim: Claim) -> Literal["result", "method"]:
    """Parse the novelty kind from a novelty claim id (``claim-novelty-{kind}-<hyp>``).

    Strips the ``claim-novelty-`` prefix and reads the kind token. Robust when the
    hypothesis id itself contains hyphens (the remainder is matched by its leading
    ``result-`` / ``method-`` token only). Precondition: ``_is_novelty_claim(claim)`` --
    a non-novelty id raises (the caller gates on ``_is_novelty_claim`` first).

    Raises:
        ValueError: if the id is not a recognised 2-kind novelty id.
    """
    remainder = claim.id[len("claim-novelty-"):]
    if remainder.startswith("result-"):
        return "result"
    if remainder.startswith("method-"):
        return "method"
    raise ValueError(
        f"unrecognised novelty claim id '{claim.id}': expected "
        "claim-novelty-result-<hyp> or claim-novelty-method-<hyp> (2-kind)"
    )


def _audit_novelty_claim(
    hypothesis: Hypothesis,
    kind: Literal["result", "method"],
    recorded_claim: Claim,
    novelty_decisions: List[EvidenceItem],
) -> VerifyOutcome:
    """Re-derive one {hypothesis, kind} novelty claim status by RULE and compare to the
    recorded one (2-kind).

    B-replace (design/literature-acquisition.md): the novelty claim is rule-derived
    (``derive_novelty_status(hyp, kind, ...)`` over the recorded NOVELTY_DECISIONs of that
    kind), decoupled from the experiment verdict. A recorded SUPPORTED novelty claim is
    faithful only if the record still holds a *found_nothing* decision for THIS {hyp,
    kind}; if that decision was deleted (or a found_something was tampered to found_nothing,
    or the only found_nothing was bound to the OTHER kind), the re-derived status diverges
    from the recorded one. READ-ONLY: no persist, no LLM.

    Classification: matching status -> REPRODUCED; any mismatch -> DIVERGED (novelty has
    no inconclusive/UNRESOLVED state -- the rule always yields PROPOSED or SUPPORTED).
    """
    rederived = derive_novelty_status(hypothesis, kind, novelty_decisions)
    result = REPRODUCED if rederived == recorded_claim.status else DIVERGED
    basis = (
        f"{kind}-novelty re-derived from the recorded prior-art decisions"
        if result == REPRODUCED
        else (
            f"recorded {kind}-novelty claim does not re-derive from the record: recorded "
            f"{recorded_claim.status.value}, re-derived {rederived.value} (a "
            f"found_nothing {kind} prior-art decision was deleted or tampered)"
        )
    )
    return VerifyOutcome(
        hypothesis_id=hypothesis.id,
        recorded_status=recorded_claim.status,
        rederived_status=rederived,
        result=result,
        rederived_basis=basis,
    )


# -- read-only paper-consistency check (Phase 3, D4) -------------------------

def _check_paper_consistency(run_dir: Path) -> Dict[str, LatexRefReport]:
    """Re-check each rendered paper document's internal ``\\ref``<->``\\label`` integrity.

    READ-ONLY: reads ``run_dir/paper/<doc>.tex`` for each of ``_PAPER_DOCS`` that EXISTS
    and runs the pure :func:`check_latex_ref_consistency` over it. No recompile, no LLM,
    no write -- this is the same headless, third-party spirit as the claim re-derivation.

    Returns a map keyed by file name (``draft.tex`` / ``si.tex``) -> its
    :class:`LatexRefReport`. EMPTY when the run has no ``paper/`` directory or neither
    document is present -- the caller treats an empty map as "nothing to gate" (vacuously
    consistent), preserving the pre-Phase-3 exit behavior for runs without a paper.
    """
    paper_dir = run_dir / "paper"
    reports: Dict[str, LatexRefReport] = {}
    if not paper_dir.is_dir():
        return reports
    for name in _PAPER_DOCS:
        doc = paper_dir / name
        if doc.is_file():
            reports[name] = check_latex_ref_consistency(
                doc.read_text(encoding="utf-8")
            )
    return reports


def _check_paper_factrefs(run_dir: Path) -> Dict[str, List[str]]:
    """Re-scan each rendered paper document for RESIDUAL ``\\evval``/``\\status`` macros.

    READ-ONLY (mirrors :func:`_check_paper_consistency`): a rendered ``.tex`` should carry
    NONE -- :func:`sci_adk.render.factref.substitute_factrefs` substitutes every fidelity
    macro at render time -- so a residual is a fidelity divergence (substitution bypassed /
    the .tex hand-edited). Returns a map keyed by file name -> the residual macros found
    (only for documents that have any); an empty map means clean / no paper.
    """
    paper_dir = run_dir / "paper"
    residuals: Dict[str, List[str]] = {}
    if not paper_dir.is_dir():
        return residuals
    for name in _PAPER_DOCS:
        doc = paper_dir / name
        if doc.is_file():
            found = find_unresolved_factrefs(doc.read_text(encoding="utf-8"))
            if found:
                residuals[name] = found
    return residuals


def _check_paper_tool_vocab(run_dir: Path) -> List[str]:
    """Re-scan ``draft.tex`` for §10 tool-vocabulary leaks (READ-ONLY; the SI is EXEMPT).

    Only the belief-narrative PAPER is checked -- ``si.tex`` is openly the record dump and
    legitimately uses sci-adk vocabulary, so it is never scanned. Returns the distinct
    forbidden terms found (empty = clean / no draft.tex), via the pure
    :func:`sci_adk.render.paper.check_paper_tool_vocabulary`.
    """
    draft = run_dir / "paper" / "draft.tex"
    if not draft.is_file():
        return []
    return check_paper_tool_vocabulary(draft.read_text(encoding="utf-8"))


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
    """Load recorded Claims keyed by their unique Claim ``id`` (read-only).

    Keyed by ``claim.id`` (not ``claim.answers``) because the two-claim model
    (B-replace) means a hypothesis can have BOTH an experiment claim ``claim-<hyp>`` and
    a novelty claim ``claim-novelty-<hyp>`` answering the SAME hypothesis id -- keying by
    ``answers`` would silently drop one. The audit routes each by id.
    """
    claims_dir = run_dir / "claims"
    if not claims_dir.is_dir():
        return {}
    claims: Dict[str, Claim] = {}
    for path in sorted(claims_dir.glob("*.json")):
        claim = Claim.model_validate(json.loads(path.read_text(encoding="utf-8")))
        claims[claim.id] = claim
    return claims


__all__ = [
    "REPRODUCED",
    "DIVERGED",
    "UNRESOLVED",
    "VerifyOutcome",
    "VerifyReport",
    "verify_run",
]
