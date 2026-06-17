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

from typing import Sequence

from sci_adk.core.evidence import BearingDirection, EvidenceItem
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
        # Guard 3 item 2: a binding empirical verdict needs at least one measured item.
        # data_source=None counts as "not measured" (fail-closed). The rice failure
        # (all generated/synthetic, would-be SUPPORTED) stops here.
        if binding and not any(src == _MEASURED for src in sources):
            raise ValidityHalt(
                hypothesis.id,
                "empirical hypothesis would be "
                f"{verdict_direction.value} but no bearing Evidence is "
                "data_source='measured' (all generated/synthetic_proxy/None) -- an "
                "empirical claim cannot be affirmed without real measured data "
                "(acquire measured data, or restrict the hypothesis to a "
                "method/calibration claim). See design/evidence-validity.md Guard 3.",
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


__all__ = [
    "ValidityHalt",
    "check_evidence_adequacy",
]
