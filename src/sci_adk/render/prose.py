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

    Each slot is **LaTeX body input**: the paper artifact is ``draft.tex`` (Overleaf
    default pdflatex), so author the text LaTeX-safe -- e.g. ``$\\geq$``, ``H$_2$O``,
    ``30\\textdegree{}C`` -- not unicode. The LaTeX renderer injects it (after LaTeX
    special-char escaping) verbatim into the document. A lightweight unicode safety
    net folds a stray ``≥`` / ``α`` / accent to a pdflatex-safe form, but it is a
    fallback, not a license to rely on unicode; the ``.tex`` is the source of truth.

    **Reference / citation commands are permitted in prose.** These specific commands
    pass through verbatim as real LaTeX -- ``\\ref{fig:<id>}``, ``\\eqref{eq:<id>}``,
    ``\\autoref{<id>}`` to cross-reference, and ``\\cite{<key>}`` / ``\\citep{<key>}`` /
    ``\\citet{<key>}`` to cite literature -- so an author can point at a figure or cite a
    paper in the narrative. (Authoring ``\\ref{fig:<id>}`` here is also what drives the
    body-reference figure numbering.) NO OTHER LaTeX passes: every other special
    (``&`` ``%`` ``_`` ``$`` ...) is still escaped, and a non-allowlisted command like
    ``\\textbf{...}`` is rendered as literal text -- so prose stays LaTeX-safe outside
    the ref/cite allowlist. See :func:`sci_adk.render.paper._latex_sanitize_prose`.

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


class SIProse(BaseModel):
    """Optional agent-authored narrative wrapping the Supporting Information record dump.

    The symmetric twin of :class:`PaperProse` for ``si.tex``
    (design/paper-figures-and-si.md D3, Phase 4: "an OPTIONAL agent SI-prose hook
    (mirrors prose.py) may add narrative around the record dump; the strict
    no-authoring record dump is the spine"). Two narrative slots, both optional (each
    defaults to ``None``). A present slot is injected by :func:`sci_adk.render.si.render_si_latex`;
    an absent slot emits nothing -- with ``prose=None`` (or both slots ``None``) the SI is
    byte-identical to the no-prose record dump (the regression invariant). Frozen and
    whitespace-stripping, consistent with :class:`PaperProse` and the core models.

    It NEVER replaces the deterministic record dump: ``overview`` precedes it and
    ``notes`` follows it, so the no-authoring Evidence/data/verdict spine is untouched.
    Like ``PaperProse``, the text is INPUT supplied by the in-session agent (or a
    ``--si-prose <json>`` file), never sci-adk-generated -- zero extra cost
    (design/tool-policy.md).

    Each slot is **LaTeX body input**: the SI artifact is ``si.tex`` (Overleaf default
    pdflatex), so author the text LaTeX-safe -- e.g. ``$\\geq$``, ``H$_2$O``,
    ``30\\textdegree{}C`` -- not unicode. The renderer injects it (after LaTeX
    special-char escaping) verbatim. A lightweight unicode safety net folds a stray
    ``≥`` / ``α`` / accent to a pdflatex-safe form, but it is a fallback, not a license
    to rely on unicode; the ``.tex`` is the source of truth.

    **Reference / citation commands are permitted in prose** (the same contract as
    :class:`PaperProse`): ``\\ref`` / ``\\eqref`` / ``\\autoref`` and ``\\cite`` /
    ``\\citep`` / ``\\citet`` pass through verbatim as real LaTeX so the narrative can
    cross-reference and cite; every other special is still escaped and a non-allowlisted
    command renders as literal text. The deterministic record dump that these slots wrap
    stays FULLY escaped (the plain ``_latex_sanitize``) -- only this narrative prose gets
    the ref/cite passthrough. See :func:`sci_adk.render.paper._latex_sanitize_prose`.

    Attributes:
        overview: a narrative intro, rendered near the TOP of ``si.tex`` (after the
            italic record-note, before ``\\section{Evidence record}``).
        notes: closing narrative, rendered at the BOTTOM (after ``\\section{Record
            integrity}``, before ``\\end{document}``).
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    overview: Optional[str] = Field(
        default=None,
        description="Narrative overview (rendered before the Evidence record section)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Closing narrative notes (rendered after Record integrity)",
    )


__all__ = ["PaperProse", "SIProse"]
