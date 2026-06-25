"""
sci-adk Core Type: Evidence

The Evidence type represents the accumulated record of research activities.
It is immutable and append-only - the audit trail of the research process.

Core principle: The record of what happened is monotone and append-only.
You never unmake an experiment. Null and negative results are part of the record.

Invariants:
    E1: Append-only - EvidenceItem is never mutated or deleted
    E2: Null results (refutes/inconclusive/neutral) are valid outcomes
    E3: Every EvidenceItem carries sufficient Provenance for reproduction
    E4: bears_on.target_id references an existing Hypothesis or Claim

This module uses frozen dataclasses to enforce immutability at the type level.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .spec import Id


class EvidenceKind(str, Enum):
    """
    The kind of evidence item.

    Each represents a different type of research activity or finding.

    Attributes:
        experiment_run: A computational or physical experiment execution
        proof_step: A step in a formal proof derivation
        literature: A finding from the literature review
        counterexample: A counterexample to a claim
        observation: A general observation or note
        prior_work_decision: A recorded Spec-time prior-work decision. Used for the
            *not-searched* outcome of the discovery trigger: a recorded null (the
            reason for skipping prior-art search). The *searched* outcome is a
            LITERATURE item, not this. Kept distinct so the decision is never
            confused with an acquisition in the single append-only log
            (design/literature-acquisition.md, Invariant E2).
        novelty_decision: A recorded novelty/priority discovery decision (the High
            trigger, design/literature-acquisition.md). Carries a ``LiteratureDecision``
            payload (searched -> references the LITERATURE artifact; skipped -> a
            recorded null with a reason). SEPARATE from ``PRIOR_WORK_DECISION`` -- whose
            closing-kind set is a load-bearing anchor that must stay unchanged -- so a
            novelty decision never spuriously satisfies the Spec-time prior-art check.
        contested_record: A recorded post-conflict literature decision (the Medium
            trigger, design/literature-acquisition.md). Made explicit AFTER a claim
            becomes CONTESTED so literature that arrived after the conflict stays visible
            (anti post-hoc-rationalization; the append-only ``created_at`` is the
            timestamp). Carries a ``LiteratureDecision`` payload; never gates/halts.
    """

    EXPERIMENT_RUN = "experiment_run"
    PROOF_STEP = "proof_step"
    LITERATURE = "literature"
    COUNTEREXAMPLE = "counterexample"
    OBSERVATION = "observation"
    PRIOR_WORK_DECISION = "prior_work_decision"
    NOVELTY_DECISION = "novelty_decision"
    CONTESTED_RECORD = "contested_record"
    DIGITIZED = "digitized"
    # @MX:NOTE: [AUTO] figure-digitization (design/figure-digitization.md §2): a value
    #   recovered from a published FIGURE (last-resort fidelity; author-raw and
    #   in-text/table numbers are preferred). Asymmetric adoption -- this is the ONLY
    #   kind that is gated through the proposed->verified lifecycle (DigitizedData) and
    #   may NEVER auto-promote to measured. measured/reported carry no such obligation.
    NEGATIVE_CONTROL = "negative_control"
    # @MX:NOTE: [AUTO] science-guards G3 (falsifiability): a recorded run of a DELIBERATELY
    #   MUTATED apparatus (a method broken in a way that MUST violate the hypothesis), whose
    #   recorded outcome is that the decision rule returned NOT-SUPPORTED on the mutant. It
    #   demonstrates the test apparatus can report FAIL (mutation testing for science).
    #   Carries a ``NegativeControl`` payload + ``bears_on=[]`` (like NOVELTY_DECISION): a
    #   meta-record about the APPARATUS, NOT evidence about the hypothesis, so it NEVER enters
    #   the DecisionEngine. The G3 verdict gate requires one (failing on the declared
    #   discriminating cases, with real execution provenance) before a deterministic+formal
    #   hypothesis may be stamped SUPPORTED.


class BearingDirection(str, Enum):
    """
    The direction of evidence bearing on a hypothesis or claim.

    All directions are first-class - none is "failure" or "stuck".
    Null results are valid and complete outcomes (Invariant E2).

    Attributes:
        supports: Evidence supports the hypothesis/claim
        refutes: Evidence refutes the hypothesis/claim
        neutral: Evidence is neutral or inconclusive
        inconclusive: Evidence is insufficient to draw a conclusion
    """

    SUPPORTS = "supports"
    REFUTES = "refutes"
    NEUTRAL = "neutral"
    INCONCLUSIVE = "inconclusive"


class Cost(BaseModel):
    """
    Resource cost information for evidence generation.

    Captures telemetry for reproducibility and resource tracking.

    Attributes:
        tokens: Language model tokens consumed (if applicable)
        wallclock_seconds: Wall-clock time taken
        cpu_seconds: CPU time consumed
        memory_mb: Peak memory usage in MB
    """

    model_config = {"frozen": True}

    tokens: Optional[int] = Field(default=None, ge=0, description="LLM tokens consumed")
    wallclock_seconds: Optional[float] = Field(default=None, ge=0, description="Wall-clock time")
    cpu_seconds: Optional[float] = Field(default=None, ge=0, description="CPU time")
    memory_mb: Optional[float] = Field(default=None, ge=0, description="Peak memory MB")


class Provenance(BaseModel):
    """
    Reproducibility information for an evidence item.

    Invariant E3: Every EvidenceItem carries enough Provenance to attempt
    reproduction, or explicitly marks what is missing.

    Evidence-validity (design/evidence-validity.md E2): ``data_source`` records WHAT
    the data is about, which the adequacy gate uses to decide whether the Evidence can
    bear on a Claim:
      - ``measured``        -- real empirical data (the only kind that satisfies an
                               empirical claim).
      - ``generated``       -- an in-silico/computed GENUINE instance of a formal
                               referent (T-1's molecule set).
      - ``synthetic_proxy`` -- a FABRICATED stand-in for an external referent the data
                               does not contain (the rice numbers).
      - ``None``            -- unstated; the gate treats it as "not measured"
                               (fail-closed).

    Attributes:
        code_ref: Commit/worktree/script path + line reference
        data_ref: Dataset id + version reference
        data_source: measured | generated | synthetic_proxy | None (evidence-validity)
        seed: RNG seed for stochastic reproducibility
        environment: Toolchain/container/library versions
        cost: Resource cost telemetry
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    code_ref: Optional[str] = Field(default=None, description="Commit/worktree/script reference")
    data_ref: Optional[str] = Field(default=None, description="Dataset id + version")
    data_source: Optional[Literal["measured", "generated", "synthetic_proxy"]] = Field(
        default=None,
        description="What the data is about: measured (real empirical), generated "
        "(genuine in-silico instance), synthetic_proxy (fabricated stand-in). None = "
        "not measured (fail-closed in the adequacy gate).",
    )
    seed: Optional[int] = Field(default=None, ge=0, description="RNG seed")
    environment: Optional[str] = Field(default=None, description="Toolchain/container versions")
    cost: Optional[Cost] = Field(default=None, description="Resource cost telemetry")

    @model_validator(mode="before")
    def validate_reproducibility_information(self) -> "EvidenceItem":
        """
        Invariant E3: Validate that sufficient provenance is recorded.

        At minimum, some provenance information should be present.
        """
        # Note: This is a simplified check - full validation would check all fields
        # We don't raise to allow purely observational evidence
        return self


class Result(BaseModel):
    """
    The result of an evidence item.

    Results may be continuous/probabilistic OR qualitative.
    The type accommodates both quantitative and qualitative findings.

    Attributes:
        type: Result type (quantitative or qualitative)
        point: Point estimate/statistic (quantitative)
        effect_size: Effect size measure (quantitative)
        ci: Confidence/credible interval (quantitative)
        p_value: P-value (quantitative)
        posterior: Posterior probability or reference (quantitative)
        residual: Residual from model fit (quantitative)
        predictive_error: Predictive error measure (quantitative)
        finding: Qualitative finding text (qualitative)
        artifact_ref: Reference to produced figure/table/file (qualitative)
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    type: str = Field(..., description="Result type discriminator")

    # Quantitative fields
    point: Optional[float] = Field(default=None, description="Point estimate")
    effect_size: Optional[float] = Field(default=None, description="Effect size")
    ci: Optional[List[float]] = Field(
        default=None, description="Confidence/credible interval (lower, upper)"
    )
    p_value: Optional[float] = Field(default=None, ge=0, le=1, description="P-value")
    posterior: Optional[float] = Field(default=None, ge=0, le=1, description="Posterior probability")
    residual: Optional[float] = Field(default=None, description="Residual")
    predictive_error: Optional[float] = Field(default=None, description="Predictive error")

    # Qualitative fields
    finding: Optional[str] = Field(default=None, description="Qualitative finding text")
    artifact_ref: Optional[str] = Field(default=None, description="Reference to produced artifact")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Ensure type is one of the allowed values."""
        allowed = {"quantitative", "qualitative"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}, got '{v}'")
        return v

    @field_validator("ci")
    @classmethod
    def validate_ci_interval(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        """Validate confidence interval ordering."""
        if v:
            if len(v) != 2:
                raise ValueError(f"CI must have exactly 2 values, got {len(v)}")
            lower, upper = v
            if lower > upper:
                raise ValueError(f"CI lower bound ({lower}) exceeds upper ({upper})")
        return v


class Bearing(BaseModel):
    """
    A bearing describes how evidence relates to a hypothesis or claim.

    Invariant E4: target_id must reference an existing Hypothesis or Claim.
    (Validation happens at EvidenceItem level with full context.)

    Attributes:
        target_id: Reference to a Hypothesis or Claim id
        direction: supports/refutes/neutral/inconclusive
        weight: Optional strength/weight of this bearing
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    target_id: Id = Field(..., description="Hypothesis or Claim id this bears on")
    direction: BearingDirection = Field(..., description="Bearing direction")
    weight: Optional[float] = Field(default=None, ge=0, description="Optional strength weight")

    # @MX:NOTE: All bearing directions are first-class outcomes
    # Null results (refutes/inconclusive/neutral) are valid science


class DigitizedVerification(BaseModel):
    """
    The independent-verification record for a digitized value.

    design/figure-digitization.md §4: a digitized value is not evidence-grade until an
    INDEPENDENT party re-confirms it. This records WHO certified it and HOW. The
    ``verifier_id`` is load-bearing for the gate's self-certification ban: a counted
    digitized item must record a ``verifier_id`` that differs from the extractor (the
    one who read the value off the plot may not also certify it).

    Attributes:
        method: how the value was verified -- ``replot`` (recompute the extracted value
            back to pixel space and overlay on the original), ``human`` (a human
            re-read), or ``judge`` (an LLM-judge spot-check). v1 produces ``replot``.
        verifier_id: identity of the independent verifier (MUST differ from the
            extractor for the item to count -- enforced by the gate, not this model).
        result: outcome of the check (e.g. ``reproduced`` | ``diverged``).
        artifact: optional reference to the verification artifact (e.g. the overlay).
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    method: Literal["replot", "human", "judge"] = Field(
        ..., description="Verification method: replot | human | judge"
    )
    verifier_id: Optional[str] = Field(
        default=None,
        description="Independent verifier identity (must differ from the extractor to "
        "count -- the self-certification ban is enforced by the gate).",
    )
    result: Optional[str] = Field(
        default=None, description="Verification outcome (e.g. reproduced | diverged)"
    )
    artifact: Optional[str] = Field(
        default=None, description="Reference to the verification artifact (e.g. overlay)"
    )


class DigitizedData(BaseModel):
    """
    The typed payload of a ``digitized`` EvidenceItem (design/figure-digitization.md §4).

    A value RECONSTRUCTED from a published figure carries obligations the trustworthy
    kinds (measured/reported) do not: it must never auto-promote to measured, it cannot
    be counted before independent verification, and it carries reconstruction
    uncertainty intrinsically. This sub-model holds those digitized-specific fields on
    ``EvidenceItem``; it is round-trippable (plain Pydantic v2 model).

    Lifecycle (§3): ``proposed`` (extracted, NOT evidence-grade) -> ``verified``.

    ``method="vlm"`` is a RESERVED enum value: v1 implements ``deterministic`` ONLY (the
    digitizer refuses to PRODUCE a vlm item). The gate is method-agnostic, so a future
    vlm method can plug in behind the same gate without a schema change.

    Attributes:
        quantity: what value this is (e.g. "leaf_dry_weight").
        value: the extracted measurement (the recovered figure number).
        unit: the measurement unit.
        source: provenance of ORIGIN -- the figure + DOI / run (e.g. "Fig 2 / 10.x/y").
        method: ``deterministic`` (v1) | ``vlm`` (reserved, unimplemented).
        axis_calib: axis-calibration values (the deterministic path's reconstruction
            basis); a plain JSON-able mapping so it round-trips without importing the
            digitizer's typed calibration (kernel must not depend on search/).
        read_uncert: read uncertainty (marker size / resolution / log-axis effects).
        state: ``proposed`` (default) | ``verified``.
        verification: the independent-verification record (None until verified).
        extractor: identity of the agent that extracted the value (REQUIRED, non-empty --
            fail-closed). The gate requires the verifier to differ from this, so an
            absent/empty extractor would bypass the self-certification ban.
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    quantity: str = Field(..., min_length=1, description="What value this is")
    value: float = Field(..., description="Extracted measurement (recovered figure number)")
    unit: str = Field(..., description="Measurement unit")
    source: str = Field(..., min_length=1, description="Origin provenance: Fig X / DOI / run")
    method: Literal["deterministic", "vlm"] = Field(
        default="deterministic",
        description="Extraction method: deterministic (v1) | vlm (reserved, unimplemented)",
    )
    axis_calib: Optional[Dict[str, Any]] = Field(
        default=None, description="Axis-calibration values (deterministic path)"
    )
    read_uncert: Optional[float] = Field(
        default=None, ge=0, description="Read uncertainty (marker/resolution/log effects)"
    )
    state: Literal["proposed", "verified"] = Field(
        default="proposed",
        description="Lifecycle: proposed (extracted, not evidence-grade) | verified",
    )
    verification: Optional[DigitizedVerification] = Field(
        default=None, description="Independent-verification record (None until verified)"
    )
    extractor: str = Field(
        ...,
        min_length=1,
        description="Identity of the extractor (REQUIRED, non-empty -- fail-closed). The "
        "self-certification ban (verifier_id != extractor) depends on a recorded "
        "extractor; an absent/empty one would let 'verifier_id != None/\"\"' falsely read "
        "as independent, so a digitized item cannot exist without it.",
    )


class LiteratureDecision(BaseModel):
    """
    The typed payload of a discovery-trigger decision EvidenceItem
    (design/literature-acquisition.md §"Discovery trigger model").

    Mirrors :class:`DigitizedData`'s style (a small frozen sub-model carried on
    ``EvidenceItem``), present ONLY on the ``NOVELTY_DECISION`` (High trigger) and
    ``CONTESTED_RECORD`` (Medium trigger) kinds -- the two hypothesis-bound triggers.
    It records the *decision* the agent made, not a belief: the parent item always
    carries ``bears_on=[]`` (it asserts no support/refute direction and never enters
    the DecisionEngine).

    The Spec-creation prior-art trigger does NOT use this payload -- it is Spec-bound
    (per Spec, not per hypothesis) and its ``PRIOR_WORK_DECISION`` item carries no
    ``LiteratureDecision``. Keeping the prior-art path untouched preserves its
    load-bearing closing-kind anchor (see :func:`sci_adk.loop.prior_work.prior_work_open`).

    Attributes:
        outcome: ``searched`` (prior_work: a prior-art search was performed -> flows
            into the existing acquisition + a ``LITERATURE`` item), ``skipped`` (a
            recorded null with a reason -- prior_work or a novelty skip), ``recorded``
            (a post-conflict contested record), ``found_nothing`` (a novelty prior-art
            search that returned nothing -> supports the novelty claim), or
            ``found_something`` (a novelty prior-art search that found prior art -> does
            NOT support the novelty claim).
        hypothesis_id: the hypothesis this decision is bound to (REQUIRED, non-empty --
            these triggers are hypothesis-bound, unlike the Spec-time prior-art check).
        kind: ``result`` | ``method`` -- which novelty axis this NOVELTY_DECISION serves
            (design/literature-acquisition.md §"Novelty -- definition (2-kind)"). The two
            axes are orthogonal: a {hyp, result} decision derives only the result-novelty
            claim, a {hyp, method} decision only the method-novelty claim. REQUIRED on
            every NOVELTY_DECISION (the recorders always set it); ``None`` on the kindless
            CONTESTED_RECORD (and prior-work, which carries no LiteratureDecision at all).
        reason: why the search was skipped, or a contested note (optional).
        literature_evidence_id: the id of the ``LITERATURE`` EvidenceItem this decision
            references, when a search was performed (None for a pure skip).
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    outcome: Literal[
        "searched", "skipped", "recorded", "found_nothing", "found_something"
    ] = Field(
        ...,
        description="The recorded decision outcome. prior_work uses searched|skipped; "
        "contested uses recorded; a novelty *search* uses found_nothing (prior art "
        "search returned nothing -> supports the novelty claim) | found_something "
        "(prior art exists -> does not); a novelty *skip* uses skipped.",
    )
    hypothesis_id: str = Field(
        ..., min_length=1,
        description="Hypothesis this decision is bound to (REQUIRED, non-empty)",
    )
    kind: Optional[Literal["result", "method"]] = Field(
        default=None,
        description="The novelty axis this NOVELTY_DECISION serves (result|method); set "
        "by the recorders on every NOVELTY_DECISION. None on CONTESTED_RECORD.",
    )
    reason: Optional[str] = Field(
        default=None, description="Why skipped, or a contested note (optional)"
    )
    literature_evidence_id: Optional[str] = Field(
        default=None,
        description="Referenced LITERATURE EvidenceItem id when a search was performed",
    )


class NegativeControl(BaseModel):
    """
    The typed payload of a ``negative_control`` EvidenceItem (design/science-guards.md G3 --
    falsifiability).

    A negative control records that a DELIBERATELY MUTATED apparatus -- the method broken
    in a way that MUST violate the hypothesis -- was run, and the decision rule correctly
    returned NOT-SUPPORTED. This is mutation testing applied to scientific verification: if
    a method that should fail the test still passes, the test cannot report FAIL and a
    SUPPORTED verdict carries no information. It mirrors :class:`LiteratureDecision`'s style
    (a small frozen sub-model carried on ``EvidenceItem``), present ONLY on the
    ``NEGATIVE_CONTROL`` kind, whose parent item always carries ``bears_on=[]`` (it is a
    record ABOUT the apparatus, not a belief about the hypothesis, and never enters the
    DecisionEngine).

    The G3 gate (``check_falsifiability_adequacy``) admits a control only when ALL hold:
      - ``outcome == "not_supported"`` (the mutant correctly FAILED the apparatus);
      - ``discriminating_cases_covered`` covers the hypothesis's declared
        ``discriminating_cases`` (G2): the mutant fails ON THE HARD CASES, not on a trivial
        one -- a mutant that only fails an easy case proves nothing;
      - the parent EvidenceItem carries REAL execution provenance (a non-empty
        ``Provenance.code_ref`` or ``environment``): the control was actually RUN, not merely
        asserted (the gate reads the parent's provenance, enforced there, not in this model).

    Attributes:
        hypothesis_id: the hypothesis whose apparatus this control falsifies (REQUIRED,
            non-empty -- the gate binds the control to the hypothesis by this id, since
            ``bears_on`` is empty).
        mutant: a description of the deliberate mutation -- what was broken so the hypothesis
            MUST be violated (e.g. for T-1 H1: "removed one tie-breaking invariant from the
            canonicalizer so distinct graphs can share a label").
        outcome: the decision rule's verdict on the mutant. MUST be ``not_supported`` for the
            control to count (a ``supported`` mutant means the test did not detect the
            deliberate break -- the apparatus is unfalsifiable on this mutation).
        discriminating_cases_covered: the ``DiscriminatingCase.case`` keys the mutant was run
            against and failed on. Must cover the hypothesis's declared discriminating cases
            (G3<->G2 coupling); empty = the control demonstrates nothing about the hard cases.
        statistic: which statistic the mutant moved (the same one the DecisionRule judges),
            for the audit trail (optional).
        observed_value: the mutant's measured statistic value (e.g. ``collision_count`` > 0),
            recording HOW the mutant failed (optional, audit).
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    hypothesis_id: str = Field(
        ..., min_length=1,
        description="Hypothesis whose apparatus this control falsifies (REQUIRED, non-empty)",
    )
    mutant: str = Field(
        ..., min_length=1,
        description="The deliberate mutation that MUST violate the hypothesis",
    )
    outcome: Literal["not_supported", "supported"] = Field(
        ...,
        description="The decision rule's verdict on the mutant. The G3 gate counts a control "
        "ONLY when this is ``not_supported`` (the mutant correctly FAILED). ``supported`` is "
        "deliberately a legal value -- NOT a footgun: it records the HONEST, important "
        "negative finding that a method which SHOULD have failed still passed, i.e. the "
        "apparatus is UNFALSIFIABLE on this mutation. Per record/belief separation the record "
        "holds what happened; the gate then refuses to let such a control ground a SUPPORTED "
        "belief (a ``supported`` mutant does not demonstrate the test can report FAIL).",
    )
    discriminating_cases_covered: List[str] = Field(
        default_factory=list,
        description="DiscriminatingCase.case keys the mutant failed on (must cover the "
        "hypothesis's declared discriminating_cases -- G3<->G2 coupling).",
    )
    statistic: Optional[str] = Field(
        default=None, description="Statistic the mutant moved (audit)"
    )
    observed_value: Optional[float] = Field(
        default=None, description="The mutant's measured statistic value (audit)"
    )


class EvidenceItem(BaseModel):
    """
    A single evidence item in the append-only evidence log.

    Invariant E1: EvidenceItem is never mutated or deleted after creation.
    Corrections are NEW items that reference the superseded one.

    The Evidence log is the source of truth for "what happened" in research.
    It is monotone and append-only - the scientific record.

    Attributes:
        id: Unique evidence item identifier
        created_at: ISO-8601 UTC timestamp
        spec_id: Reference to the Spec this run serves
        kind: Type of evidence item
        provenance: Reproducibility information
        result: The result (quantitative or qualitative)
        bears_on: Which hypotheses/claims this relates to and how
        supersedes: Optional reference to superseded evidence id (for corrections)
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    id: Id = Field(..., description="Unique evidence identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp (ISO-8601 UTC)",
    )
    spec_id: Id = Field(..., description="Reference to governing Spec")
    kind: EvidenceKind = Field(..., description="Type of evidence")
    provenance: Provenance = Field(..., description="Reproducibility information")
    result: Result = Field(..., description="The result")
    bears_on: List[Bearing] = Field(
        default_factory=list, description="Relationships to hypotheses/claims"
    )
    supersedes: Optional[Id] = Field(
        default=None, description="Supersedes prior evidence id (for corrections)"
    )
    digitized: Optional[DigitizedData] = Field(
        default=None,
        description="Digitized-specific payload, present ONLY when kind==DIGITIZED "
        "(design/figure-digitization.md §4). None for every other kind (asymmetric "
        "adoption -- measured/reported carry no digitized obligations).",
    )
    literature_decision: Optional[LiteratureDecision] = Field(
        default=None,
        description="Discovery-trigger decision payload, present ONLY when "
        "kind in {NOVELTY_DECISION, CONTESTED_RECORD} "
        "(design/literature-acquisition.md §\"Discovery trigger model\"). None for every "
        "other kind. The parent item is a recorded decision, not a belief (bears_on=[]).",
    )
    negative_control: Optional[NegativeControl] = Field(
        default=None,
        description="Negative-control payload, present ONLY when kind==NEGATIVE_CONTROL "
        "(design/science-guards.md G3). None for every other kind. The parent item is a "
        "record ABOUT the apparatus (a mutant run), not a belief about the hypothesis "
        "(bears_on=[]); it never enters the DecisionEngine.",
    )

    # @MX:ANCHOR: Evidence is append-only audit trail
    # @MX:REASON: Invariant E1 - enforces monotone scientific record

    @model_validator(mode="before")
    def validate_bears_on_not_empty(self) -> "EvidenceItem":
        """
        Validate that at least one bearing is specified for non-observational evidence.

        Evidence should relate to at least one hypothesis or claim.
        """
        if hasattr(self, 'kind') and self.kind != EvidenceKind.OBSERVATION and not self.bears_on:
            # We don't raise to allow flexible evidence entry
            pass
        return self

    def with_correction(
        self,
        result: Optional[Result] = None,
        provenance: Optional[Provenance] = None,
        bears_on: Optional[List[Bearing]] = None,
        note: str = "",
    ) -> EvidenceItem:
        """
        Create a correction evidence item that supersedes this one.

        Invariant E1: Corrections create NEW items, never mutate existing ones.
        The new evidence item references the old one via `supersedes`.

        Args:
            result: New result (or keep existing)
            provenance: New provenance (or keep existing)
            bears_on: New bearings (or keep existing)
            note: Explanation of the correction

        Returns:
            New EvidenceItem with supersedes pointing to this item
        """
        return EvidenceItem(
            id=f"{self.id}-corr-{int(datetime.now(timezone.utc).timestamp())}",
            created_at=datetime.now(timezone.utc),
            spec_id=self.spec_id,
            kind=self.kind,
            provenance=provenance or self.provenance,
            result=result or self.result,
            bears_on=bears_on or self.bears_on,
            supersedes=self.id,
            digitized=self.digitized,
            literature_decision=self.literature_decision,
            negative_control=self.negative_control,
        )

    def supports_target(self, target_id: Id) -> bool:
        """
        Check if this evidence supports the given target.

        Args:
            target_id: Hypothesis or Claim id to check

        Returns:
            True if any bearing has direction=SUPPORTS for this target
        """
        return any(
            b.target_id == target_id and b.direction == BearingDirection.SUPPORTS
            for b in self.bears_on
        )

    def refutes_target(self, target_id: Id) -> bool:
        """
        Check if this evidence refutes the given target.

        Args:
            target_id: Hypothesis or Claim id to check

        Returns:
            True if any bearing has direction=REFUTES for this target
        """
        return any(
            b.target_id == target_id and b.direction == BearingDirection.REFUTES
            for b in self.bears_on
        )


__all__ = [
    "Id",
    "EvidenceKind",
    "BearingDirection",
    "Cost",
    "Provenance",
    "Result",
    "Bearing",
    "DigitizedVerification",
    "DigitizedData",
    "LiteratureDecision",
    "NegativeControl",
    "EvidenceItem",
]
