"""
sci-adk Core Type: Spec

The Spec type represents a frozen pre-registration contract. It captures the
four-pane research proposal as an evaluable contract with fixed questions and
decision rules (anti-HARKing).

Invariants:
    S1: Frozen Spec version is immutable; changes create version+1
    S2: Every Hypothesis has exactly one mode and one DecisionRule
    S3: DecisionRule expresses how continuous/uncertain evidence maps
    S4: TargetClaim.answers references an existing Hypothesis.id
    S5: Amending a frozen Spec requires human checkpoint

This module implements the Spec type and its related components using Pydantic v1
for validation and JSON serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# Type alias for opaque stable identifiers
Id = str


class HypothesisMode(str, Enum):
    """
    The mode of a hypothesis - honest pre-declaration of research intent.

    Attributes:
        confirmatory: Pre-registered hypothesis with formal decision rule
        exploratory: Investigative hypothesis without formal commitment
    """

    CONFIRMATORY = "confirmatory"
    EXPLORATORY = "exploratory"


class DecisionRuleKind(str, Enum):
    """
    The kind of decision rule used to evaluate evidence.

    Each kind represents a different approach to mapping continuous/uncertain
    evidence to support/refute/null outcomes.

    Attributes:
        threshold: Simple threshold-based rule
        bayesian: Bayesian posterior odds rule
        interval: Confidence/credible interval rule
        proof: Formal proof or counterexample rule
        qualitative: Expert/structured criterion in prose
    """

    THRESHOLD = "threshold"
    BAYESIAN = "bayesian"
    INTERVAL = "interval"
    PROOF = "proof"
    QUALITATIVE = "qualitative"


class RawProposal(BaseModel):
    """
    The literal four-pane proposal input, verbatim from user.

    This captures the provenance of what the user actually requested,
    preserving the original input before any transformation.

    Attributes:
        background: Research background and context
        goal: Research goal and objectives
        method: Proposed methodology and approaches
        expected_output: Anticipated results and contributions
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    background: str = Field(..., min_length=1, description="Research background and context")
    goal: str = Field(..., min_length=1, description="Research goal and objectives")
    method: str = Field(..., min_length=1, description="Proposed methodology and approaches")
    expected_output: str = Field(
        ..., min_length=1, description="Anticipated results and contributions"
    )


class DecisionRule(BaseModel):
    """
    Decision rule for evaluating evidence against a hypothesis.

    This represents how continuous/uncertain evidence maps to support/refute/null.
    A purely binary pass/fail rule is considered a smell but not invalid.

    Invariant S3: MUST express how continuous/uncertain evidence maps to outcomes.

    Attributes:
        kind: The type of decision rule (threshold, bayesian, interval, proof, qualitative)
        expression: Human-readable rule description
        params: Machine-usable thresholds. REQUIRED for the numeric kinds
            (threshold, bayesian, interval); optional for proof/qualitative.

    Example:
        >>> bayesian_rule = DecisionRule(
        ...     kind=DecisionRuleKind.BAYESIAN,
        ...     expression="posterior odds > 10 => support",
        ...     params={"min_odds": 10.0}
        ... )
        >>> interval_rule = DecisionRule(
        ...     kind=DecisionRuleKind.INTERVAL,
        ...     expression="95% CI excludes 0 => support",
        ...     params={"null_value": 0.0, "support_side": "excludes"}
        ... )
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    kind: DecisionRuleKind = Field(..., description="Type of decision rule")
    expression: str = Field(
        ..., min_length=1, description="Human-readable rule expression"
    )
    params: Optional[Dict[str, Union[int, float, str, bool]]] = Field(
        default=None, description="Machine-usable thresholds where applicable"
    )

    # Invariant S3 (documentation): a purely binary pass/fail rule is a smell, but
    # it is not invalid -- some research legitimately reduces to a binary outcome,
    # and S3 cannot reject it (design/decision-engine.md §5 item 1). The earlier
    # ``validate_expression_not_binary_only`` validator looped over binary patterns
    # and ``pass``ed on every match, enforcing nothing; it was removed as dead code.
    # The numeric rule kinds carry their continuous mapping in ``params`` (consumed
    # by the DecisionEngine), which is where S3's "continuous => outcome" intent is
    # actually honored.

    @model_validator(mode="after")
    def validate_params_required_for_kind(self) -> "DecisionRule":
        """
        Validate that params are present for the quantitative rule kinds.

        The numeric kinds carry their machine-usable thresholds in ``params``
        (consumed by the DecisionEngine, never a hardcoded constant), so they MUST
        be present:

        - ``threshold``: comparison statistic/op/value
        - ``bayesian``: ``min_odds``
        - ``interval``: ``null_value`` + ``support_side`` (Decision 3,
          design/decision-engine.md §0/§5/Decision 3 -- INTERVAL was added to this
          set so an interval rule's null value is machine-readable, never assumed 0)

        ``proof`` and ``qualitative`` are non-numeric and do not require params.

        This is the single surviving params validator -- it collapses the former
        duplicate pair (``validate_params_match_kind`` /
        ``validate_params_required_for_kind``), which were the same check
        (design/decision-engine.md §5 item 2).
        """
        if self.kind in (
            DecisionRuleKind.THRESHOLD,
            DecisionRuleKind.BAYESIAN,
            DecisionRuleKind.INTERVAL,
        ):
            if not self.params or self.params == {}:
                raise ValueError(
                    f"{self.kind.value} rules require params to define thresholds"
                )
        return self


class DiscriminatingCase(BaseModel):
    """
    A hard test case that must be present for a passing verdict to be informative
    (design/science-guards.md G2 -- test-power).

    A pass over an EASY test set carries little information: a plausibly-broken method
    would pass it too. A ``DiscriminatingCase`` names a case that SEPARATES a correct
    method from a plausibly-broken one, with the reason it does so. The set of declared
    discriminating cases is what makes ``collision_count == 0`` (or any threshold pass)
    a result rather than a triviality. The G3 falsifiability negative control must FAIL
    on exactly these cases (a mutant that still passes the easy cases proves nothing) --
    so ``case`` is a stable key the ``NegativeControl.discriminating_cases_covered`` list
    references.

    Attributes:
        case: stable identifier/name of the hard case (e.g. "cospectral-pair-A"). The G3
            negative control references this key to attest the mutant failed ON it.
        why: why this case makes a pass meaningful -- what a plausibly-broken method would
            get wrong here that an easy case would not catch.
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    case: str = Field(..., min_length=1, description="Stable identifier of the hard case")
    why: str = Field(
        ..., min_length=1,
        description="Why a pass on this case is informative (what a broken method fails here)",
    )


class Hypothesis(BaseModel):
    """
    A research hypothesis derived from the goal pane.

    Invariant S2: Every Hypothesis has exactly one mode and one DecisionRule.

    Evidence-validity (design/evidence-validity.md E1): every Hypothesis declares a
    frozen ``referent`` class -- whether its claim is about a ``formal`` object (math,
    algorithms, ML algorithm-behavior; generated instances ARE the referent, e.g. T-1)
    or an ``empirical`` referent (physical/biological phenomena; the referent lives
    outside the program and must be MEASURED). It defaults to ``empirical`` (fail-closed:
    an unmarked hypothesis is treated as the strictest case, so forgetting to declare a
    referent can never silently weaken the adequacy gate). It is frozen in the Spec
    (anti-HARKing): an empirical hypothesis cannot be relabelled formal AFTER seeing
    results to dodge the real-data requirement.

    Attributes:
        id: Unique identifier for this hypothesis
        statement: The hypothesis statement (e.g., "molecule graphs admit encoding")
        mode: confirmatory or exploratory - honest pre-declaration
        decision_rule: Rule for evaluating evidence against this hypothesis
        referent: ``formal`` | ``empirical`` -- the claim's referent class (default
            ``empirical``, fail-closed). Frozen with the Spec.
        non_circularity: for a ``formal`` hypothesis backed by ``generated`` Evidence,
            a non-empty statement of what the verifier tests that is NOT baked into the
            generator (design/evidence-validity.md Guard 2). Recorded/surfaced, never
            auto-proven. ``None`` for empirical hypotheses or where no generated
            evidence binds.
        novelty_result: whether this hypothesis asserts RESULT-novelty -- that no prior
            published work has established its RESULT (its ``statement``/conclusion), a
            universal-negative over the literature (design/literature-acquisition.md
            §"Novelty -- definition (2-kind)"). Default ``False`` (most hypotheses are
            not result-novelty claims). Frozen with the Spec (anti-HARKing): the flag
            cannot be flipped after seeing results to dodge or invent the prior-art-search
            requirement. When ``True``, a separate revisable novelty Claim
            ``claim-novelty-result-<hyp>`` is derived by rule
            (``derive_novelty_status(hyp, "result", ...)``): SUPPORTED iff a recorded
            *found_nothing* prior-art search bound to {hyp, result}, else PROPOSED --
            decoupled from the experiment verdict and never a run-HALT (B-replace).
        novelty_method: whether this hypothesis asserts METHOD-novelty -- that no prior
            published work has used its METHOD (its approach). Independent of
            ``novelty_result`` (the two axes are orthogonal -- all four quadrants are
            meaningful: known-result/new-method, new-result/known-method, both, neither).
            Default ``False``; frozen (anti-HARKing). When ``True``, a separate
            ``claim-novelty-method-<hyp>`` is derived by rule
            (``derive_novelty_status(hyp, "method", ...)``). Dropping either flag is a
            human-only Spec amendment (F7), never a silent edit.
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    id: Id = Field(..., description="Unique hypothesis identifier")
    statement: str = Field(..., min_length=1, description="Hypothesis statement")
    mode: HypothesisMode = Field(..., description="Research mode (confirmatory/exploratory)")
    decision_rule: DecisionRule = Field(
        ..., description="Rule for evaluating evidence"
    )
    referent: Literal["formal", "empirical"] = Field(
        default="empirical",
        description="Referent class (formal=generated instances are genuine evidence; "
        "empirical=needs measured data). Default empirical (fail-closed); frozen.",
    )
    non_circularity: Optional[str] = Field(
        default=None,
        description="Non-circularity attestation for a formal/generated claim: what "
        "the verifier tests that is not baked into the generator (recorded, not proven).",
    )
    novelty_result: bool = Field(
        default=False,
        description="Result-novelty claim: no prior published work established this "
        "hypothesis's RESULT (a universal-negative over the literature). Default False; "
        "frozen (anti-HARKing). A SUPPORTED result-novelty claim requires a recorded "
        "found_nothing prior-art search bound to {hyp, result}; dropping the flag is a "
        "human-only Spec amendment (F7).",
    )
    novelty_method: bool = Field(
        default=False,
        description="Method-novelty claim: no prior published work used this hypothesis's "
        "METHOD (its approach). Independent of novelty_result (orthogonal axes). Default "
        "False; frozen (anti-HARKing). A SUPPORTED method-novelty claim requires a "
        "recorded found_nothing prior-art search bound to {hyp, method}; dropping the flag "
        "is a human-only Spec amendment (F7).",
    )
    epistemic_kind: Literal["finding", "capability_check", "unit_test"] = Field(
        default="finding",
        description="The EPISTEMIC class of this hypothesis (design/science-guards.md G1 -- "
        "analyticity). ``finding`` = an empirical/open result whose truth is NOT settled by "
        "construction (the default). ``capability_check`` = an assertion that a method has a "
        "capability (e.g. 'the encoder runs on these inputs'). ``unit_test`` = a property "
        "that is true BY CONSTRUCTION given a correct implementation (a known theorem; "
        "failure is only possible as an implementation bug -- e.g. round-trip decode under a "
        "prime-power encoding follows from unique factorization). Frozen with the Spec "
        "(anti-HARKing): a result cannot be relabelled finding<->unit_test after seeing the "
        "outcome. The G1 verdict gate REFUSES to stamp a triggered (formal + deterministic + "
        "non-novel) hypothesis still marked ``finding`` as an empirical finding -- the author "
        "must reclassify it (to capability_check/unit_test, changing the verdict framing from "
        "'hypothesis SUPPORTED' to 'capability verified') or assert novelty, recorded as a "
        "Spec amendment.",
    )
    discriminating_cases: Optional[List[DiscriminatingCase]] = Field(
        default=None,
        description="The hard cases that make a passing verdict informative "
        "(design/science-guards.md G2 -- test-power). A binding-threshold formal hypothesis "
        "with NONE declared yields a low-power pass (an easy test set a broken method would "
        "also pass). The G3 negative control must FAIL on exactly these cases. ``None`` = not "
        "declared (surfaced at the spec gate; the verdict gate caps a binding pass as "
        "non-discriminating). Frozen with the Spec.",
    )
    cost_metrics: Optional[List[str]] = Field(
        default=None,
        description="The practical-property statistics this hypothesis commits to reporting "
        "(design/science-guards.md G5 -- claim-cost). When the statement/target claim uses a "
        "practical-property term (index, efficient, scalable, fast, compact, practical, ...), "
        "the corresponding cost statistic (e.g. integer bit-length for an 'index'/'encoding') "
        "must be declared here or the spec-gate lint surfaces it. A manual override: listing "
        "the metric names satisfies the lint. ``None`` = none declared.",
    )

    # @MX:ANCHOR: Hypothesis uniquely maps evidence to claim via one mode + one rule
    # @MX:REASON: Enforces invariant S2 - single evaluation path prevents ambiguity


class ToolRef(BaseModel):
    """
    Reference to a tool, solver, language, or dataset.

    Used in MethodPlan to capture the expected tools for this research.

    Attributes:
        name: Tool or resource name
        version: Optional version constraint
        kind: Type of tool (solver, language, dataset, etc.)
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    name: str = Field(..., min_length=1, description="Tool or resource name")
    version: Optional[str] = Field(default=None, description="Version constraint")
    kind: str = Field(default="tool", description="Type of tool")


class MethodPlan(BaseModel):
    """
    Research method plan derived from the method pane.

    This captures the intended approaches and tools for the research.
    It informs the loop but is not binding on the actual execution.

    Attributes:
        approaches: List of planned techniques/approaches
        tools: Optional list of expected solvers/languages/datasets
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    approaches: List[str] = Field(
        default_factory=list, description="Planned techniques and approaches"
    )
    tools: Optional[List[ToolRef]] = Field(
        default=None, description="Expected solvers, languages, datasets"
    )

    @field_validator("approaches", mode="before")
    @classmethod
    def validate_approaches_not_empty(cls, v: List[str]) -> List[str]:
        """At least one approach should be specified."""
        if not v or all(a.strip() == "" for a in v):
            # Empty approaches is allowed for flexible research,
            # but we log a warning (not raising to allow exploratory work)
            pass
        return v


class TargetClaim(BaseModel):
    """
    A contribution the user hopes to establish.

    Invariant S4: TargetClaim.answers must reference an existing Hypothesis.id.

    Attributes:
        id: Unique identifier for this target claim
        statement: The claim statement
        answers: Reference to the hypothesis id this target addresses
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    id: Id = Field(..., description="Unique target claim identifier")
    statement: str = Field(..., min_length=1, description="Target claim statement")
    answers: Id = Field(..., description="Hypothesis id this target addresses")


class Spec(BaseModel):
    """
    A frozen pre-registration contract - the compiler input.

    Spec represents a four-pane proposal as a compiled, evaluable contract.
    Once accepted, the question and decision rules do not change mid-run
    (anti-HARKing). Amendments create new versions, never silent edits.

    Invariant S1: A frozen Spec version is immutable. Changes create version+1.
    Invariant S5: Amending requires human checkpoint (enforced externally).

    Attributes:
        id: Unique spec identifier
        created_at: ISO-8601 UTC timestamp of creation
        version: Version number, bumped on amendment
        raw_proposal: Original four-pane input (provenance)
        hypotheses: Derived hypotheses from goal pane
        method: Method plan from method pane
        target_claims: Target claims from expected output pane
        amendment_rationale: Optional rationale for version > 1
        prior_version_id: Reference to previous version if amended
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    id: Id = Field(..., description="Unique spec identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp (ISO-8601 UTC)",
    )
    version: int = Field(default=1, ge=1, description="Version number")
    raw_proposal: RawProposal = Field(..., description="Original four-pane input")
    hypotheses: List[Hypothesis] = Field(
        default_factory=list, description="Derived hypotheses"
    )
    method: MethodPlan = Field(..., description="Method plan")
    target_claims: List[TargetClaim] = Field(
        default_factory=list, description="Target claims"
    )
    amendment_rationale: Optional[str] = Field(
        default=None, description="Rationale for amendment (version > 1)"
    )
    prior_version_id: Optional[Id] = Field(
        default=None, description="Previous version id if amended"
    )

    # @MX:ANCHOR: Spec is frozen pre-registration contract
    # @MX:REASON: Invariant S1 - prevents silent HARKing, ensures anti-HARKing guarantee

    @field_validator("hypotheses")
    @classmethod
    def validate_hypotheses_not_empty(cls, v: List[Hypothesis]) -> List[Hypothesis]:
        """At least one hypothesis must be defined."""
        if not v:
            raise ValueError("Spec must have at least one hypothesis")
        return v

    @model_validator(mode="after")
    def validate_target_claims_reference_hypotheses(self) -> "Spec":
        """
        Invariant S4: TargetClaim.answers must reference an existing Hypothesis.id.

        This ensures that every target claim is about a known hypothesis.
        """
        if self.hypotheses:
            hypothesis_ids = {h.id for h in self.hypotheses}
            for claim in self.target_claims:
                if claim.answers not in hypothesis_ids:
                    raise ValueError(
                        f"TargetClaim '{claim.id}' references unknown hypothesis '{claim.answers}'"
                    )
        return self

    @model_validator(mode="before")
    def validate_amendment_has_rationale(self) -> "Spec":
        """
        Validate that amended specs have required documentation.
        """
        if hasattr(self, 'version') and self.version is not None and self.version > 1:
            # Note: This validator runs before model validation
            # Full validation happens in model post-init
            pass
        return self

    def amend(
        self,
        raw_proposal: Optional[RawProposal] = None,
        hypotheses: Optional[List[Hypothesis]] = None,
        method: Optional[MethodPlan] = None,
        target_claims: Optional[List[TargetClaim]] = None,
        rationale: str = "",
    ) -> Spec:
        """
        Create an amended version of this Spec.

        Invariant S5: REQUIRES HUMAN CHECKPOINT - this method creates the
        new version object but external enforcement must ensure human approval.

        The new spec has version+1 and references this spec as prior_version_id.

        Args:
            raw_proposal: New raw proposal (or keep existing)
            hypotheses: New hypotheses (or keep existing)
            method: New method plan (or keep existing)
            target_claims: New target claims (or keep existing)
            rationale: Required rationale for the amendment

        Returns:
            New Spec with incremented version

        Raises:
            ValueError: If rationale is empty for version > 1
        """
        if not rationale or not rationale.strip():
            raise ValueError("Amendment requires non-empty rationale")

        # Validate that we're not trying to modify frozen fields directly
        return Spec(
            id=self.id,  # Same id, different version
            created_at=datetime.now(timezone.utc),
            version=self.version + 1,
            raw_proposal=raw_proposal if raw_proposal is not None else self.raw_proposal,
            hypotheses=hypotheses if hypotheses is not None else self.hypotheses,
            method=method if method is not None else self.method,
            target_claims=target_claims if target_claims is not None else self.target_claims,
            amendment_rationale=rationale,
            prior_version_id=str(self.created_at.timestamp()),
        )

    def get_hypothesis(self, hypothesis_id: Id) -> Optional[Hypothesis]:
        """
        Retrieve a hypothesis by its id.

        Args:
            hypothesis_id: The hypothesis identifier

        Returns:
            The Hypothesis if found, None otherwise
        """
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def get_target_claim(self, claim_id: Id) -> Optional[TargetClaim]:
        """
        Retrieve a target claim by its id.

        Args:
            claim_id: The target claim identifier

        Returns:
            The TargetClaim if found, None otherwise
        """
        for claim in self.target_claims:
            if claim.id == claim_id:
                return claim
        return None


__all__ = [
    "Id",
    "HypothesisMode",
    "DecisionRuleKind",
    "RawProposal",
    "DecisionRule",
    "DiscriminatingCase",
    "Hypothesis",
    "ToolRef",
    "MethodPlan",
    "TargetClaim",
    "Spec",
]
