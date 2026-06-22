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
from sci_adk.core.spec import DecisionRuleKind, Hypothesis

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


# ---------------------------------------------------------------------------
# Science guards (design/science-guards.md) -- the verdict-gate HALTS that refuse to
# stamp a SUPPORTED verdict for WEAK science: a constructively-true claim packaged as an
# empirical finding (G1), a pass over a non-discriminating test set (G2), or an
# apparatus that cannot report FAIL (G3 -- the most important). They COMPOSE with
# check_evidence_adequacy at the SAME chokepoint (ClaimUpdater, before any Claim is
# persisted) and never weaken it -- they only ADD refusal paths. All are PURE, no-LLM,
# no-domain; they read frozen Spec fields + recorded Evidence and decide adequacy.
#
# SCOPE (deliberate, fail-OPEN for cases the guards do not understand): the three
# verdict-gate halts fire ONLY on a ``formal`` hypothesis with a ``threshold`` (the
# deterministic, no-RNG) decision rule reaching a binding SUPPORTS. This is the
# analytic/computational claim class the guards reason about (T-1's shape). An
# ``empirical`` claim (gated separately by check_evidence_adequacy's measured-data
# requirement), a non-threshold rule (bayesian/interval/proof/qualitative, whose
# falsification is not a single mutated re-run), or a non-binding verdict is OUT of
# scope here -- so the guards never block a legitimate empirical or judged result.

# The deterministic numeric rule kind the science guards reason about (no RNG: a single
# comparison of a recorded statistic). bayesian/interval consume distributions and
# proof/qualitative are judged, so "mutate and re-run for FAIL" does not transfer.
_DETERMINISTIC = frozenset({DecisionRuleKind.THRESHOLD})


def _is_deterministic_formal(hypothesis: Hypothesis) -> bool:
    """True iff this hypothesis is the analytic class the science guards reason about:
    a ``formal`` referent with a deterministic (``threshold``) decision rule. Empirical,
    bayesian/interval, and proof/qualitative hypotheses are OUT of scope (fail-open)."""
    return (
        hypothesis.referent == "formal"
        and hypothesis.decision_rule.kind in _DETERMINISTIC
    )


def check_analyticity(
    hypothesis: Hypothesis,
    bearing_evidence: Sequence[EvidenceItem],
    verdict_direction: BearingDirection,
) -> None:
    """G1 (analyticity): refuse to stamp a constructively-true claim AS an empirical finding.

    A ``formal`` + deterministic hypothesis backed by ``generated`` Evidence, asserting NO
    novelty (its result is already known in prior art -> a known theorem), still labelled
    ``epistemic_kind=="finding"``, may not reach a binding SUPPORTS framed as an empirical
    discovery. The author must either RECLASSIFY it (``epistemic_kind`` ->
    ``capability_check`` / ``unit_test`` -- the verdict framing becomes "capability verified
    / implementation correct", not "hypothesis SUPPORTED") or ASSERT novelty
    (``novelty_result`` / ``novelty_method`` with a recorded found_nothing prior-art search,
    making it a genuinely open question whose example-verification IS legitimate science --
    "no counterexample up to N"). Recorded as a Spec amendment, exactly like Guard 2.

    The nuance that keeps legitimate science passing: an OPEN conjecture (a hypothesis that
    ASSERTS novelty) is NOT triggered -- verifying an open conjecture by examples is valid.
    Only a known-result (novelty both False) unit-tested while framed as a finding is
    refused. Raises ``ValidityHalt`` on refusal; returns ``None`` otherwise.

    Scope note (fail-closed): the trigger does NOT depend on ``data_source``. An earlier
    draft additionally required ``data_source == generated`` (matching the prose trigger in
    design/science-guards.md), but that left a hole -- a known-result ``finding`` whose
    Evidence had ``data_source`` unset/``None`` (or any non-generated value) would slip past
    the verdict gate while the always-on spec gate flagged it. A ``formal`` hypothesis's
    Evidence is generated by construction, so dropping the condition blocks no legitimate
    case and makes the verdict-gate trigger IDENTICAL to the spec-gate G1 trigger
    (``audit_spec_science``) -- consistent and fail-closed. ``bearing_evidence`` is retained
    in the signature for caller/sibling parity (and future evidence-side checks).
    """
    # @MX:ANCHOR: [AUTO] the G1 analyticity gate -- a constructively-true / known-result
    #   claim cannot be stamped as an empirical finding (it must be reclassified or assert
    #   novelty). PURE: reads frozen Spec fields only (data_source-independent, fail-closed).
    # @MX:REASON: [AUTO] ClaimUpdater (persist) and loop/verify.py (re-derive) both consult
    #   this before a binding SUPPORTS; weakening the trigger (e.g. letting a novelty-False
    #   formal/threshold 'finding' pass, or re-adding the data_source==generated escape) re-
    #   opens packaging a known theorem as a discovery -- the exact mis-framing G1 prevents.
    #   The novelty-asserted bypass is load-bearing: it is what keeps open-conjecture
    #   example-verification ('no counterexample up to N') legitimate.
    if verdict_direction != BearingDirection.SUPPORTS:
        return
    if not _is_deterministic_formal(hypothesis):
        return
    if hypothesis.epistemic_kind != "finding":
        return  # already reclassified (capability_check / unit_test) -> resolved
    if hypothesis.novelty_result or hypothesis.novelty_method:
        return  # asserts an open/novel question -> example-verification is legitimate
    raise ValidityHalt(
        hypothesis.id,
        "a formal, deterministic (threshold) hypothesis asserting no novelty would be "
        "SUPPORTED while still framed as an empirical finding "
        "(epistemic_kind='finding') -- a constructively-true / already-known result cannot "
        "be packaged as a discovery. Either reclassify it (set epistemic_kind to "
        "'unit_test' for a property true by construction, or 'capability_check' for a "
        "capability assertion -- the verdict reads 'capability verified', not 'hypothesis "
        "SUPPORTED'), or assert novelty (novelty_result/novelty_method with a recorded "
        "found_nothing prior-art search, making it a genuinely open question). See "
        "design/science-guards.md G1.",
    )


def check_discriminating_power(
    hypothesis: Hypothesis,
    verdict_direction: BearingDirection,
) -> None:
    """G2 (test-power): refuse a binding pass over a test set with NO declared hard cases.

    A pass over an easy test set is low-information: a plausibly-broken method would pass it
    too. A ``formal`` + deterministic hypothesis reaching a binding SUPPORTS must declare at
    least one ``discriminating_cases`` entry -- a hard case that SEPARATES a correct method
    from a broken one, with the reason it does. Missing/empty -> the pass is
    non-discriminating and is refused (the author declares the hard cases via a Spec
    amendment). This is the G2<->G3 anchor: the G3 negative control must FAIL on exactly
    these declared cases, so a missing declaration also makes falsifiability undemonstrable.

    Raises ``ValidityHalt`` when no discriminating case is declared; returns ``None``
    otherwise. (Honest limit, §5 spirit: the gate enforces that hard cases are DECLARED, not
    that they are genuinely hard -- that judgment is the author's, recorded for audit.)
    """
    # @MX:ANCHOR: [AUTO] the G2 test-power gate -- a binding formal/threshold pass needs a
    #   declared discriminating case set (else the pass is non-discriminating). Anchors the
    #   G2<->G3 coupling (the negative control must fail ON these cases).
    # @MX:REASON: [AUTO] ClaimUpdater + verify consult this before a binding SUPPORTS;
    #   dropping it lets an easy-test-set pass be stamped SUPPORTED with no power, the exact
    #   non-discriminating pass G2 exists to refuse.
    if verdict_direction != BearingDirection.SUPPORTS:
        return
    if not _is_deterministic_formal(hypothesis):
        return
    if hypothesis.discriminating_cases:  # non-empty list of declared hard cases
        return
    raise ValidityHalt(
        hypothesis.id,
        "a formal, deterministic (threshold) hypothesis would be SUPPORTED but declares no "
        "discriminating_cases -- a pass over an undeclared/easy test set is "
        "non-discriminating (a plausibly-broken method would pass it too). Declare the hard "
        "cases that make a pass informative (e.g. for a graph canonicalizer: "
        "cospectral / EC-degenerate non-isomorphic pairs), each with the reason it "
        "separates a correct method from a broken one. See design/science-guards.md G2.",
    )


def check_falsifiability_adequacy(
    hypothesis: Hypothesis,
    negative_controls: Sequence[EvidenceItem],
    verdict_direction: BearingDirection,
) -> None:
    """G3 (falsifiability, the most important): a binding SUPPORTS requires a NEGATIVE CONTROL.

    Mutation testing for science: a ``formal`` + deterministic hypothesis cannot be stamped
    SUPPORTED unless the record holds a ``NEGATIVE_CONTROL`` Evidence item proving the
    apparatus CAN report FAIL -- a deliberately MUTATED method (broken so the hypothesis MUST
    be violated) on which the decision rule returned NOT-SUPPORTED. Without it, a passing
    verdict is "supported (apparatus unfalsified)": the test never demonstrated it can fail,
    so a pass carries no information.

    A qualifying control (>=1 required) must satisfy ALL of:
      - ``negative_control.hypothesis_id == hypothesis.id`` (bound to THIS hypothesis);
      - ``negative_control.outcome == "not_supported"`` (the mutant correctly FAILED);
      - REAL execution provenance on the parent item -- a non-empty ``provenance.code_ref``
        or ``provenance.environment`` (the mutant was actually RUN, not merely asserted);
      - ``discriminating_cases_covered`` covers the hypothesis's declared
        ``discriminating_cases`` (G2<->G3): the mutant fails ON THE HARD CASES, not on a
        trivial one. When no discriminating case is declared (G2 already halts first), a
        control with a non-empty covered set still demonstrates SOMETHING and passes here;
        an empty covered set proves nothing and does not qualify.

    Raises ``ValidityHalt`` when no qualifying control exists; returns ``None`` otherwise.
    Like the other gates this is PURE + read-only over the recorded Evidence.
    """
    # @MX:ANCHOR: [AUTO] the G3 falsifiability gate -- a deterministic+formal SUPPORTED is
    #   refused without a negative control whose mutant FAILS on the declared discriminating
    #   cases, with real execution provenance. The strongest science guard (mutation testing).
    # @MX:REASON: [AUTO] ClaimUpdater (persist) and loop/verify.py (re-derive) both consult
    #   this before a binding SUPPORTS; weakening it -- accepting an asserted (no-provenance)
    #   control, a 'supported' mutant, or one that fails only an easy case -- re-opens
    #   stamping an UNFALSIFIED apparatus as SUPPORTED, the exact defect G3 exists to prevent.
    if verdict_direction != BearingDirection.SUPPORTS:
        return
    if not _is_deterministic_formal(hypothesis):
        return

    declared = {dc.case for dc in (hypothesis.discriminating_cases or [])}
    for ev in negative_controls:
        nc = ev.negative_control
        if nc is None or nc.hypothesis_id != hypothesis.id:
            continue
        if nc.outcome != "not_supported":
            continue
        # Real execution provenance: the mutant was actually RUN (fail-closed -- an asserted
        # control with no code_ref/environment does not count).
        prov = ev.provenance
        if not ((prov.code_ref or "").strip() or (prov.environment or "").strip()):
            continue
        covered = {c for c in nc.discriminating_cases_covered if (c or "").strip()}
        # The mutant must fail ON the declared hard cases (G2<->G3). When cases are declared,
        # the covered set must include them all; when none are declared (G2 halts first), a
        # non-empty covered set still demonstrates a real failure -- an empty one proves nothing.
        if declared:
            if not declared.issubset(covered):
                continue
        elif not covered:
            continue
        return  # a qualifying negative control exists -> falsifiability demonstrated
    raise ValidityHalt(
        hypothesis.id,
        "a formal, deterministic (threshold) hypothesis would be SUPPORTED but carries no "
        "qualifying negative control -- 'supported (apparatus unfalsified)'. Record a "
        "NEGATIVE_CONTROL Evidence item: a deliberately mutated method (broken so the "
        "hypothesis MUST be violated) that was actually RUN (real provenance) and on which "
        "the decision rule returned NOT-SUPPORTED, failing on the declared discriminating "
        "cases (e.g. for T-1 H1: remove one tie-breaking invariant from the canonicalizer "
        "and confirm collision_count > 0; for H2: corrupt the decoder and confirm "
        "round-trip < 100%). See design/science-guards.md G3.",
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
    "check_analyticity",
    "check_discriminating_power",
    "check_falsifiability_adequacy",
    "derive_novelty_status",
]
