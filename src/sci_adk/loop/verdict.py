"""
Typed checkpoint + verdict-trail schema (the non-numeric on-disk contract).

design/rigor-shell-architecture.md §4.3/§4.4 (F1/F2) demote ``checkpoints.md`` to
a generated human *view* and make typed JSON the contract:

  - ``checkpoints/<hyp-id>.json``  -> :class:`CheckpointModel`
  - ``verdicts/<hyp-id>.json``     -> :class:`VerdictTrail`

The verdict trail is **mandatory and schematized**: a binding (SUPPORTS/REFUTES)
non-numeric verdict is accepted by the engine only when it arrives with a
well-formed trail (§2.3, F2). The trail carries

  - the frozen rubric R **copied for replay** (``rubric_expression`` =
    ``rule.expression``; ``rubric_params`` = ``rule.params``), so the verdict is
    self-contained against the Spec version it judged;
  - ``panel``: the N independent ``JudgeVerdict``-shaped opinions (chief-over-N,
    Step-3 §3.1 (C)), N >= 1;
  - ``chief``: the single adjudication whose ``basis`` states which panel reasoning
    is decisive under R (the chief has no free discretion);
  - ``provenance``: spec version + timestamp + optional per-verdict agent/cost ids.

This module lives in the KERNEL (``loop/``) because it is pure JSON
(de)serialization -- no LLM, no Claude-Code-ness (the adapter-side concern is only
the agent's *act of writing* the file with its chief-over-N reasoning, not the code
that reads it). Round-trippable via Pydantic v2.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Discriminator, Field, Tag, field_validator

from sci_adk.core.claim import ConfidenceLevel
from sci_adk.core.evidence import BearingDirection

# The two non-numeric rule kinds a checkpoint/verdict can be about. Kept as a local
# literal set (not an import of DecisionRuleKind) so the on-disk ``kind`` string is
# validated structurally without coupling the schema to the enum's other members.
_NON_NUMERIC_KINDS = ("proof", "qualitative")


class JudgeCheckpoint(BaseModel):
    """Typed contract behind a judge ``checkpoints/<hyp-id>.json`` (§4.3).

    The machine-readable form of a proof/qualitative hypothesis awaiting an
    in-session agent verdict. ``checkpoints.md`` is rendered *from* these (the
    inverse of the milestone-1 layout, where the prose was primary).

    This is the ``"judge"`` arm of the :data:`Checkpoint` discriminated union. The
    ``checkpoint_type`` discriminator defaults to ``"judge"`` (additive: the prior
    on-disk shape is preserved -- older judge files without the key still load,
    new ones gain a single defaulted field).

    Attributes:
        checkpoint_type: the union tag (always ``"judge"`` here).
        hypothesis_id: the hypothesis this checkpoint is for.
        kind: ``"proof"`` | ``"qualitative"`` (numeric kinds are never checkpoints).
        expression: the rule's prose criterion (``rule.expression``).
        finding: any evidence finding bearing on the hypothesis, for the agent.
        spec_version: the Spec version this checkpoint was raised against (replay).
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    checkpoint_type: Literal["judge"] = Field(
        default="judge", description="Discriminator for the Checkpoint union"
    )
    hypothesis_id: str = Field(..., min_length=1, description="Hypothesis id")
    kind: str = Field(..., description="proof | qualitative")
    expression: str = Field(..., min_length=1, description="The rule's prose criterion")
    finding: str = Field(default="", description="Evidence finding for the agent to judge")
    spec_version: int = Field(..., ge=1, description="Spec version this was raised against")

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, v: str) -> str:
        if v not in _NON_NUMERIC_KINDS:
            raise ValueError(
                f"checkpoint kind must be one of {_NON_NUMERIC_KINDS}, got {v!r}"
            )
        return v


# Backwards-compatible name: the historical ``CheckpointModel`` IS the judge arm.
CheckpointModel = JudgeCheckpoint


class PriorWorkCheckpoint(BaseModel):
    """Typed contract behind ``checkpoints/prior_work.json`` -- the prior_work arm.

    A *recording-type* reminder emitted at Spec creation so prior art is not
    forgotten (design/literature-acquisition.md §"Discovery trigger model"). It is
    NOT a judgment: it carries no verdict trail and is NOT hypothesis-bound. It
    stays "open" until a prior-work decision is recorded in the single Evidence log
    (a LITERATURE item for *searched*, or a PRIOR_WORK_DECISION item for
    *not searched*).

    ``model_config.extra = "forbid"`` keeps the union type-safe: a payload that
    carries judge-only keys (``hypothesis_id`` / ``expression``) is rejected here,
    not silently coerced -- the discriminator does the routing, this guards against
    a mis-tagged blob.

    Attributes:
        checkpoint_type: the union tag (always ``"prior_work"`` here).
        spec_id: the Spec this prior-work check is for (not a hypothesis).
        trigger: the firing trigger -- only ``"spec_creation"`` exists now; the
            contested / novelty / paper-render triggers are deferred (graded as
            incremental, never pegged at the Spec anchor's priority).
        spec_version: the Spec version this was raised against (replay).
        prompt: the human/agent-facing reminder text.
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
        "extra": "forbid",
    }

    checkpoint_type: Literal["prior_work"] = Field(
        default="prior_work", description="Discriminator for the Checkpoint union"
    )
    spec_id: str = Field(..., min_length=1, description="Spec id this check is for")
    trigger: Literal["spec_creation"] = Field(
        default="spec_creation",
        description="Firing trigger (only spec_creation now; others deferred)",
    )
    spec_version: int = Field(..., ge=1, description="Spec version this was raised against")
    prompt: str = Field(..., min_length=1, description="Reminder text for the agent")


def _checkpoint_tag(value: Any) -> str:
    """Discriminator callable for the :data:`Checkpoint` union.

    Maps a raw payload (dict or model instance) to its union tag. A payload with NO
    ``checkpoint_type`` key defaults to ``"judge"`` -- this is what lets legacy judge
    ``checkpoints/<hyp-id>.json`` files (written before the discriminator existed)
    still load through ``TypeAdapter(Checkpoint)``. Newer files carry the key
    explicitly. The judge on-disk shape is unchanged -- this only widens what the
    union accepts on the way in.
    """
    if isinstance(value, dict):
        return value.get("checkpoint_type", "judge")
    return getattr(value, "checkpoint_type", "judge")


# The on-disk Checkpoint contract is a discriminated union tagged by
# ``checkpoint_type``: judge checkpoints (per hypothesis) vs the single prior_work
# checkpoint (per Spec). Use ``pydantic.TypeAdapter(Checkpoint)`` to load either --
# including legacy judge files that predate the ``checkpoint_type`` key (a missing
# tag defaults to ``"judge"`` via :func:`_checkpoint_tag`).
Checkpoint = Annotated[
    Union[
        Annotated[JudgeCheckpoint, Tag("judge")],
        Annotated[PriorWorkCheckpoint, Tag("prior_work")],
    ],
    Discriminator(_checkpoint_tag),
]


class PanelVerdict(BaseModel):
    """One independent panelist opinion (a ``JudgeVerdict``-shaped entry, §4.4).

    These are the genuinely independent subagent opinions (Step-3 §3.1 (C)). The
    shape mirrors ``JudgeVerdict`` (direction/level/basis/counterexample) but is a
    persisted Pydantic model so the panel round-trips on disk.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    direction: BearingDirection = Field(..., description="The panelist's call")
    level: ConfidenceLevel = Field(..., description="Confidence strength of the call")
    basis: str = Field(..., min_length=1, description="The panelist's reasoning")
    counterexample: bool = Field(default=False, description="A counterexample was found")


class ChiefVerdict(BaseModel):
    """The single adjudication returned to the engine (§4.4).

    ``basis`` MUST state which panel reasoning is decisive under the frozen rubric R
    -- the chief has no free discretion. This is the ``JudgeVerdict`` content the
    engine actually binds on.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    direction: BearingDirection = Field(..., description="The chief's adjudicated call")
    level: ConfidenceLevel = Field(..., description="Confidence strength of the call")
    basis: str = Field(
        ..., min_length=1, description="Which panel reasoning is decisive under R"
    )
    counterexample: bool = Field(default=False, description="A counterexample was found")


class VerdictProvenance(BaseModel):
    """Replay/audit provenance for a verdict trail (E3, §4.4).

    Attributes:
        spec_version: the Spec version the verdict judged.
        timestamp: when the verdict was authored (ISO-8601 string).
        agent_ids: optional per-verdict agent ids (if subagents fanned out).
        cost_ids: optional per-verdict cost references.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    spec_version: int = Field(..., ge=1, description="Spec version the verdict judged")
    timestamp: str = Field(..., min_length=1, description="ISO-8601 authoring timestamp")
    agent_ids: Optional[List[str]] = Field(
        default=None, description="Per-verdict agent ids (subagent fan-out)"
    )
    cost_ids: Optional[List[str]] = Field(
        default=None, description="Per-verdict cost references"
    )


class VerdictTrail(BaseModel):
    """Typed contract behind ``verdicts/<hyp-id>.json`` -- the chief-over-N trail.

    Mandatory for a binding non-numeric verdict: the engine refuses a SUPPORTS /
    REFUTES verdict that lacks a well-formed trail (§2.3, F2). The structural check
    is presence + required fields + ``rubric_expression == rule.expression`` -- never
    N or the combination policy, so the kernel stays unaware of how the chief
    aggregates (the seam holds).

    Attributes:
        hypothesis_id: the hypothesis the verdict is about.
        rule_kind: ``"proof"`` | ``"qualitative"``.
        rubric_expression: the frozen rubric R (= ``rule.expression``), copied for
            replay so the trail is self-contained against the Spec it judged.
        rubric_params: the rule's params (= ``rule.params``), copied for replay.
        panel: the N independent panelist opinions (N >= 1).
        chief: the single adjudication actually returned to the engine.
        provenance: spec version + timestamp + optional agent/cost ids.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    hypothesis_id: str = Field(..., min_length=1, description="Hypothesis id")
    rule_kind: str = Field(..., description="proof | qualitative")
    rubric_expression: str = Field(
        ..., min_length=1, description="Frozen rubric R (rule.expression), for replay"
    )
    rubric_params: Optional[Dict[str, Union[int, float, str, bool]]] = Field(
        default=None, description="Frozen rule.params, copied for replay"
    )
    panel: List[PanelVerdict] = Field(
        ..., min_length=1, description="N independent panelist opinions (N >= 1)"
    )
    chief: ChiefVerdict = Field(..., description="The single adjudication under R")
    provenance: VerdictProvenance = Field(..., description="Replay/audit provenance")


__all__ = [
    "CheckpointModel",
    "JudgeCheckpoint",
    "PriorWorkCheckpoint",
    "Checkpoint",
    "PanelVerdict",
    "ChiefVerdict",
    "VerdictProvenance",
    "VerdictTrail",
]
