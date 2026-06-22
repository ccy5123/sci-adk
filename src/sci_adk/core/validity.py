"""
sci-adk Evidence-validity gate (referent-typed adequacy enforcement).

This is the load-bearing fix for the rice-failure defect (design/evidence-validity.md):
a run on an EMPIRICAL proposal used SYNTHETIC data and the harness reported
"4/4 SUPPORTED". The gate makes evidence validity a HARD halt, not an advisory flag.

The line for whether generated/synthetic data is valid Evidence for a Claim is NOT
synthetic-vs-real. It is whether the data genuinely INSTANTIATES the claim's referent
(formal: generated instances are genuine evidence -- T-1) or PROXIES an external
referent it does not contain (empirical: needs measured data).

Three guards (design/evidence-validity.md §2):
  - Guard 1 (referent class): Hypothesis.referent in {formal, empirical}, default
    empirical (fail-closed). Frozen in the Spec (anti-HARKing).
  - Guard 2 (non-circularity): a formal hypothesis backed by generated Evidence
    must carry a non-empty non-circularity attestation; missing -> surfaced.
  - Guard 3 (proxy-ban): synthetic_proxy on empirical -> halt; an empirical binding
    verdict with no measured item -> halt; generated on formal -> allowed.

This module is KERNEL-side and holds NO LLM call and NO domain knowledge. It reads
the frozen ``Hypothesis.referent`` and the ``Provenance.data_source`` of the bearing
Evidence and decides adequacy -- nothing more. The verdict's direction (whether it is
binding) is supplied by the caller (the engine already computed it); the gate never
re-judges belief, it only refuses to let an inadequate record BECOME a Claim.

Reference: design/evidence-validity.md (authoritative), design/abstractions.md
(record vs belief), design/sci-adk-productization-plan.md §7 (no self-certification).
"""

from __future__ import annotations

from typing import Literal, Sequence

from sci_adk.core.claim import ClaimStatus
from sci_adk.core.evidence import BearingDirection, EvidenceItem, EvidenceKind
from sci_adk.core.spec import Hypothesis

# The data_source value that satisfies an empirical claim. A property of WHAT the
# data is about, recorded in Provenance.data_source (design/evidence-validity.md §3).
_MEASURED = "measured"
_GENERATED = "generated"
_SYNTHETIC_PROXY = "synthetic_proxy"

# Binding verdict directions: only these AFFIRM belief (SUPPORTS/REFUTES). A
# NEUTRAL/INCONCLUSIVE verdict yields a `proposed` Claim and affirms nothing, so the
# "no measured data" halt is scoped to binding verdicts only (belief is gated; the
# record is not -- design/evidence-validity.md §2 Guard 3).
_BINDING = frozenset({BearingDirection.SUPPORTS, BearingDirection.REFUTES})

# Digitized lifecycle states (design/figure-digitization.md §3). Only a VERIFIED
# digitized item is evidence-grade; a PROPOSED one is a candidate (excluded upstream).
_VERIFIED = "verified"


def _is_digitized(ev: EvidenceItem) -> bool:
    """True iff this EvidenceItem is the gated ``digitized`` kind with its payload."""
    return ev.kind == EvidenceKind.DIGITIZED and ev.digitized is not None


def _is_verified_independent_digitized(ev: EvidenceItem) -> bool:
    """True iff ``ev`` is a digitized item that is properly evidence-grade:
    ``state==verified`` AND an independent-verifier record (``verifier_id`` present and
    != the extractor).

    This is the single predicate that decides whether a digitized item is admissible as
    a counted, measured-grade item (design/figure-digitization.md §5). A proposed,
    unverified, or self-certified digitized item is NOT measured-grade.
    """
    if not _is_digitized(ev):
        return False
    d = ev.digitized
    if d.state != _VERIFIED:
        return False
    # Defense-in-depth (the extractor=None bypass): a digitized item with no recorded
    # extractor can NEVER count as independently verified -- without it, the
    # ``verifier_id != extractor`` check below would falsely pass (e.g. 'agent-B' != None
    # -> True). The schema makes this unreachable for constructed items, but a forged /
    # tampered / deserialized record must still be refused here. Fail-closed.
    if not (d.extractor or "").strip():
        return False
    verification = d.verification
    if verification is None or not (verification.verifier_id or "").strip():
        return False
    # Self-certification ban for this kind: the extractor may not certify their own read.
    return verification.verifier_id != d.extractor


def _is_measured_grade(ev: EvidenceItem) -> bool:
    """True iff ``ev`` satisfies the empirical "needs >=1 measured item" requirement.

    Two ways to be measured-grade (design/evidence-validity.md §3 + figure-digitization
    §5): a real ``data_source=='measured'`` item, OR a VERIFIED digitized item with an
    independent verifier (figure-recovered value that has passed independent
    verification). A digitized item NEVER auto-promotes to ``measured`` -- it stays
    ``kind=digitized`` -- but a verified one COUNTS as measured-grade for this check.
    """
    if ev.provenance.data_source == _MEASURED:
        return True
    return _is_verified_independent_digitized(ev)


class ValidityHalt(Exception):
    """A HARD halt: the Evidence is inadequate for the Claim it would produce.

    Raised at the Evidence->Claim derivation chokepoint (the ClaimUpdater), caught by
    the CLI and turned into a friendly stderr message + non-zero exit. It is NOT an
    advisory flag and NOT recoverable by the pipeline: it stops the derivation before
    any Claim is written, so an ungrounded empirical result can never be
    self-certified. Because it fires inside claim derivation, it is impossible to
    route around by generating data -- generating data is exactly what trips it.

    Attributes:
        hypothesis_id: the hypothesis whose Evidence failed the gate.
        reason: a human-readable explanation (the CLI surfaces this verbatim).
    """

    def __init__(self, hypothesis_id: str, reason: str) -> None:
        self.hypothesis_id = hypothesis_id
        self.reason = reason
        super().__init__(f"evidence-validity halt on '{hypothesis_id}': {reason}")


def check_evidence_adequacy(
    hypothesis: Hypothesis,
    bearing_evidence: Sequence[EvidenceItem],
    verdict_direction: BearingDirection,
) -> None:
    """Enforce Guard 3 (proxy-ban) + Guard 2 (non-circularity) for one hypothesis.

    Raises ``ValidityHalt`` when the bearing Evidence is inadequate for the Claim that
    would be produced; returns ``None`` (silently passes) otherwise. This is the
    single adequacy decision; the caller (ClaimUpdater) calls it BEFORE persisting a
    Claim, so a halt means no Claim is written.

    Args:
        hypothesis: the hypothesis under evaluation (its frozen ``referent`` and
            ``non_circularity`` attestation drive the gate).
        bearing_evidence: the EvidenceItems whose bearings target this hypothesis
            (already pre-filtered by the caller). Their ``provenance.data_source``
            values decide adequacy.
        verdict_direction: the engine's verdict direction. Only a BINDING direction
            (SUPPORTS/REFUTES) triggers the "no measured data" / missing-attestation
            halts; a non-binding verdict affirms no belief and passes those checks.
    """
    # @MX:ANCHOR: [AUTO] the single evidence-adequacy decision (the rice-failure fix).
    # @MX:REASON: [AUTO] ClaimUpdater calls this for EVERY hypothesis before persisting
    #   a Claim; it is the one place referent-typed validity is enforced. Weakening it
    #   (e.g. dropping the synthetic_proxy->empirical halt, or scoping the measured-data
    #   requirement away) re-opens the exact self-certification of an ungrounded
    #   empirical result that design/evidence-validity.md exists to prevent.
    sources = [ev.provenance.data_source for ev in bearing_evidence]
    binding = verdict_direction in _BINDING

    if hypothesis.referent == "empirical":
        # Guard 3 item 1: a fabricated stand-in for an external referent is a category
        # error -- UNCONDITIONAL (even a non-binding bearing halts; the fabrication
        # itself is the error, not the verdict it would produce).
        if any(src == _SYNTHETIC_PROXY for src in sources):
            raise ValidityHalt(
                hypothesis.id,
                "synthetic_proxy Evidence bears on an empirical hypothesis -- a "
                "category error: a fabricated stand-in does not contain the external "
                "referent the empirical claim is about (declare data_source='measured' "
                "for real data, or mark the hypothesis referent='formal' only if the "
                "claim is genuinely about a formal/generated object). See "
                "design/evidence-validity.md Guard 3.",
            )
        # Guard 3 item 2: a binding empirical verdict needs at least one measured-grade
        # item. data_source=None counts as "not measured" (fail-closed). The rice failure
        # (all generated/synthetic, would-be SUPPORTED) stops here. A VERIFIED digitized
        # item (independent verifier) is measured-GRADE here (figure-digitization §5) --
        # it never becomes kind=measured, but a verified figure value satisfies the
        # requirement; a PROPOSED digitized item does NOT (and is excluded upstream).
        if binding and not any(_is_measured_grade(ev) for ev in bearing_evidence):
            raise ValidityHalt(
                hypothesis.id,
                "empirical hypothesis would be "
                f"{verdict_direction.value} but no bearing Evidence is "
                "data_source='measured' (or a verified digitized item) -- an "
                "empirical claim cannot be affirmed without real measured data "
                "(acquire measured data, verify a digitized figure value, or restrict "
                "the hypothesis to a method/calibration claim). See "
                "design/evidence-validity.md Guard 3 + design/figure-digitization.md §5.",
            )
        return

    # referent == "formal" (the only other value; spec.py constrains the Literal).
    # Guard 3 item 3: generated Evidence on a formal hypothesis is allowed (T-1).
    # Guard 2: a formal hypothesis reaching a BINDING verdict on generated Evidence
    # must carry a non-empty non-circularity attestation -- SURFACED, not auto-proven.
    # A non-binding verdict certifies nothing yet, so no attestation is required.
    if binding and any(src == _GENERATED for src in sources):
        if not (hypothesis.non_circularity or "").strip():
            raise ValidityHalt(
                hypothesis.id,
                "formal hypothesis would be "
                f"{verdict_direction.value} on generated Evidence but carries no "
                "non-circularity attestation -- the harness records (does not prove) "
                "what the verifier tests that is NOT baked into the generator. Add a "
                "non-empty Hypothesis.non_circularity statement (e.g. for T-1: "
                "'collisions could occur; the verifier independently checks for them'). "
                "See design/evidence-validity.md Guard 2.",
            )


def check_digitized_adequacy(
    hypothesis: Hypothesis,
    bearing_evidence: Sequence[EvidenceItem],
    verdict_direction: BearingDirection,
) -> None:
    """Enforce the digitized self-certification ban for COUNTED digitized items.

    Composes WITH ``check_evidence_adequacy`` at the same chokepoint
    (design/figure-digitization.md §5): a digitized item that would COUNT (bears on a
    binding SUPPORTS/REFUTES verdict) MUST be ``state==verified`` AND carry an
    independent-verifier record (``verifier_id`` present and != the extractor). A
    proposed digitized item is EXCLUDED upstream (it is not evidence-grade and does not
    reach a binding verdict on its own), so it never trips this; a digitized item that
    DOES bind but is proposed / unverified / self-certified is refused here.

    This is the kernel-side, deterministic, no-LLM application of the
    "agents propose, the engine judges, no self-certification" rule
    (design/evidence-validity.md §7) to the digitized kind. It NEVER weakens the
    existing adequacy gate -- it only ADDS a refusal path for inadequate digitized
    items. Raises ``ValidityHalt`` on refusal; returns ``None`` otherwise.

    Args:
        hypothesis: the hypothesis under evaluation (only its ``id`` is used here).
        bearing_evidence: the EvidenceItems whose bearings target this hypothesis
            (already pre-filtered + proposed-digitized-excluded by the caller).
        verdict_direction: the engine's verdict direction. Only a BINDING direction
            (SUPPORTS/REFUTES) makes a digitized item "counted"; a non-binding verdict
            affirms nothing, so no digitized verifier requirement applies.
    """
    # @MX:ANCHOR: [AUTO] the digitized self-certification gate (figure-digitization §5).
    # @MX:REASON: [AUTO] ClaimUpdater calls this alongside check_evidence_adequacy for
    #   EVERY hypothesis before persisting a Claim. A COUNTED digitized value (one that
    #   moves a binding verdict) MUST carry an independent-verifier record (verifier_id
    #   present and != extractor). Weakening it -- letting a proposed/self-certified
    #   figure read count -- re-opens self-certification of a reconstruction, the exact
    #   thing the proposed->verified lifecycle exists to prevent.
    if verdict_direction not in _BINDING:
        return
    for ev in bearing_evidence:
        if not _is_digitized(ev):
            continue
        # This digitized item is part of a binding verdict (it survived the upstream
        # proposed-exclusion and reached a binding direction) -> it is COUNTED, so it
        # must be verified + independently certified.
        if _is_verified_independent_digitized(ev):
            continue
        d = ev.digitized
        if not (d.extractor or "").strip():
            # Defense-in-depth (the extractor=None bypass): no recorded extractor means
            # the self-certification ban cannot be enforced -- refuse with a precise
            # reason rather than the misleading "verifier == extractor" message.
            reason = (
                f"a counted digitized item ({ev.id}) has no recorded extractor identity "
                "-- the self-certification ban (verifier != extractor) cannot be "
                "enforced, so the item can never count as independently verified"
            )
        elif d.state != _VERIFIED:
            reason = (
                f"a counted digitized item ({ev.id}) is in state '{d.state}', not "
                "'verified' -- a figure-recovered value cannot count toward a binding "
                "verdict before independent verification"
            )
        elif d.verification is None or not (d.verification.verifier_id or "").strip():
            reason = (
                f"a counted digitized item ({ev.id}) is marked verified but carries no "
                "independent-verifier record (verification.verifier_id) -- a counted "
                "digitized value must record who certified it"
            )
        else:
            reason = (
                f"a counted digitized item ({ev.id}) is self-certified: its "
                f"verifier_id ('{d.verification.verifier_id}') equals the extractor -- "
                "the one who read the value off the plot may not also certify it"
            )
        raise ValidityHalt(
            hypothesis.id,
            reason + ". See design/figure-digitization.md §5 (no self-certification).",
        )


def derive_novelty_status(
    hypothesis: Hypothesis,
    kind: Literal["result", "method"],
    novelty_decisions: Sequence[EvidenceItem],
) -> ClaimStatus:
    """Derive the revisable novelty-claim status for one {hypothesis, kind} (2-kind).

    Novelty is two INDEPENDENT kinds (design/literature-acquisition.md §"Novelty --
    definition (2-kind)"): ``result`` (no prior work established the hypothesis's RESULT)
    and ``method`` (no prior work used its METHOD). They are orthogonal -- each is
    separately pre-registered (its ``novelty_result`` / ``novelty_method`` flag), searched,
    and derived. This rule decides ONE kind for ONE hypothesis.

    B-replace: novelty is not a run-HALT coupled to the experiment verdict. It is a
    1st-class revisable Claim derived by THIS PURE RULE -- decoupled from the experiment
    verdict and never raising. The kind's validity rests on a prior-art search of THAT
    {hyp, kind} that returned nothing. So:

      - returns ``ClaimStatus.SUPPORTED`` iff some ``NOVELTY_DECISION`` whose
        ``literature_decision.hypothesis_id == hypothesis.id`` AND
        ``literature_decision.kind == kind`` records ``outcome == "found_nothing"``;
      - returns ``ClaimStatus.PROPOSED`` otherwise -- no decision for this kind, a
        ``skipped`` decision (no search), or a ``found_something`` decision (prior art).

    SAFETY FLOOR (per kind): ``found_something``/skip/absent NEVER yields SUPPORTED, and a
    found_nothing on the OTHER kind never satisfies this one (the ``kind ==`` match is
    load-bearing -- result and method are independent claims). A hypothesis whose ``kind``
    flag is unset yields PROPOSED (the caller does not derive a claim for an unset kind;
    this is a defensive return -- a kind is novelty only when its own flag is set,
    anti-HARKing).

    Like the other gates, this takes the novelty DECISION items (kind ==
    ``NOVELTY_DECISION``), NOT bearing evidence -- the decisions carry ``bears_on=[]`` and
    never enter the DecisionEngine, so the caller passes them separately.

    Args:
        hypothesis: the hypothesis under evaluation (its ``id`` binds the decisions).
        kind: which novelty axis to derive (``result`` or ``method``).
        novelty_decisions: the ``NOVELTY_DECISION`` EvidenceItems (the caller may pass
            the full set -- this function matches by kind + payload hypothesis_id + kind).

    Returns:
        ``ClaimStatus.SUPPORTED`` iff a recorded found_nothing search exists for this
        {hypothesis, kind}, else ``ClaimStatus.PROPOSED``. Never raises.
    """
    # @MX:ANCHOR: [AUTO] the per-kind novelty status rule (2-kind, B-replace).
    # @MX:REASON: [AUTO] ClaimUpdater (persist the novelty claim) and the verify audit
    #   (re-derive it) both call this; it is the one place the "SUPPORTED iff a recorded
    #   found_nothing prior-art search of THIS {hyp, kind}" rule lives. Loosening it
    #   (letting found_something/skip yield SUPPORTED, or letting the other kind's
    #   found_nothing satisfy this one) re-opens the false-novelty claim the trigger exists
    #   to prevent -- the safety floor. It is PURE (no raise): the HALT was replaced by a
    #   non-HALT compile-time NoveltyCheckpoint surfaced while the claim is PROPOSED.
    # Defense-in-depth on the safety floor: a hypothesis whose ``kind`` flag is unset can
    # never produce a SUPPORTED novelty claim for that kind regardless of any (mis-bound)
    # found_nothing decision. The caller only derives a claim for a SET kind, so this guard
    # is belt-and-suspenders -- it keeps the single safety-floor predicate honest if a
    # future caller passes an unset kind.
    flag = hypothesis.novelty_result if kind == "result" else hypothesis.novelty_method
    if not flag:
        return ClaimStatus.PROPOSED
    found_nothing = any(
        ev.kind == EvidenceKind.NOVELTY_DECISION
        and ev.literature_decision is not None
        and ev.literature_decision.hypothesis_id == hypothesis.id
        and ev.literature_decision.kind == kind
        and ev.literature_decision.outcome == "found_nothing"
        for ev in novelty_decisions
    )
    return ClaimStatus.SUPPORTED if found_nothing else ClaimStatus.PROPOSED


__all__ = [
    "ValidityHalt",
    "check_evidence_adequacy",
    "check_digitized_adequacy",
    "derive_novelty_status",
]
