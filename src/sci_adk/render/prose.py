"""
Agent-authored narrative input for the paper renderers (render-merge).

``PaperProse`` is the typed hook through which the in-session agent supplies the
three narrative slots a structural draft cannot synthesize -- abstract,
introduction, discussion -- as *input* (the same spirit as the ``pending``
parameter ``render_paper`` already takes). It is NOT autonomous generation: sci-adk
never calls an LLM to write these; the text arrives from the agent already running
(zero extra cost, design/tool-policy.md) or from a ``--prose <json>`` file.

It lives in ``render/`` (not ``core/``) deliberately: the three core abstractions
(Spec/Evidence/Claim) stay clean of presentation concerns -- prose is a render-time
input, not part of the scientific record.

Reference: design/directory-structure.md (render/), design/abstractions.md.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PaperProse(BaseModel):
    """Optional agent-authored narrative sections for a paper draft.

    Exactly three narrative slots, all optional (each defaults to ``None``). A
    present slot is injected as its section by both renderers; an absent slot falls
    back to the structural skeleton (no section emitted). Frozen and
    whitespace-stripping, consistent with the core models.

    Attributes:
        abstract: the paper abstract (rendered after the title / ``\\maketitle``).
        introduction: the Introduction section body.
        discussion: the Discussion section body (rendered before References).
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    abstract: Optional[str] = Field(
        default=None, description="Abstract narrative (rendered after the title)"
    )
    introduction: Optional[str] = Field(
        default=None, description="Introduction section body"
    )
    discussion: Optional[str] = Field(
        default=None, description="Discussion section body (rendered before References)"
    )


__all__ = ["PaperProse"]
