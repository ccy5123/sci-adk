"""
The FROZEN publishing-requirements contract (F1, design/paper-publishing-requirements.md §1).

A ``PubReqs`` is, like a :class:`sci_adk.core.spec.Spec`, a FROZEN record: the conditions
the rendered paper must meet, elicited once at ``/sci publish`` time and frozen at
``runs/<id>/pubreqs.json`` (beside ``spec.json``, NOT inside the regenerated ``paper/``
dir so ``render`` never clobbers it). ``sci-adk verify`` then checks the rendered paper
AGAINST it -- the umbrella ``paper_requirements_clean`` gate (loop/verify.py) runs only the
deterministically-checkable requirements it declares.

Record/belief separation (design §0): this is a RECORD (a frozen contract), checked against
the rendered paper; it is never authored by an LLM at verify time and never injects a
sci-adk-internal noun into ``draft.tex``. All GATE-BEARING fields are frozen
(anti-moving-the-goalposts): you cannot relax ``image_min_dpi`` after seeing a figure fail
except by an explicit amendment that re-freezes a new contract with a new digest.

Unlike :class:`Spec` (whose digest is computed on demand by ``provenance.spec_digest``),
the design (§1.1) stores the PubReqs digest IN ``pubreqs.json`` -- it is tamper-evidence the
freeze step records once. :func:`sci_adk.provenance.pubreqs_digest` computes it; the CLI
``pubreqs freeze`` verb writes it into the ``digest`` field.

Reference: design/paper-publishing-requirements.md §1, design/abstractions.md (Spec freeze
discipline), src/sci_adk/core/spec.py (the mirrored frozen model).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

# The IMRaD default (design §6 OF-5; SPEC-PAPER-GATE-001 REQ-PG-105): the fixed
# required-sections set offered by the "use defaults" fast-path, INCLUDING Conclusion.
# Abstract is accepted as a \begin{abstract} environment OR a \section{Abstract}; the rest
# are \section{...} (see loop/verify._required_sections_problems).
DEFAULT_REQUIRED_SECTIONS: List[str] = [
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
]

# The default raster DPI floor (design §6 OF-3: 300 = print).
DEFAULT_IMAGE_MIN_DPI = 300


class PubReqs(BaseModel):
    """A FROZEN publishing-requirements contract (the F1 artifact, design §1.1).

    All gate-bearing fields are immutable after construction (``model_config frozen``),
    mirroring :class:`Spec`'s S1 freeze discipline: a requirement cannot be silently
    relaxed after a figure fails -- only an explicit amendment (a new contract + a new
    digest) can change it.

    Attributes:
        spec_id: the run's Spec id this contract governs (ties pubreqs.json to the run).
        frozen_at: ISO-8601 UTC freeze timestamp.
        digest: the tamper-evidence sha256 (hex) recorded at freeze time
            (:func:`sci_adk.provenance.pubreqs_digest`). Stored in the artifact, unlike the
            Spec's on-demand digest (design §1.1). Empty pre-freeze; the CLI fills it.
        venue: a free-text venue label ("arXiv" / "JOSS" / a journal name) or None.
        required_sections: section names that MUST be present in ``draft.tex`` (each as a
            ``\\section{...}``; "Abstract" also accepts ``\\begin{abstract}``). The IMRaD
            default is :data:`DEFAULT_REQUIRED_SECTIONS`.
        figure_font_policy: F2 font policy on/off -- when on, a figure-bearing paper must
            carry the F2 font preamble (newtxmath + helvet). Default True.
        image_min_dpi: the raster (image) figure minimum effective DPI; None disables the
            DPI gate. Default :data:`DEFAULT_IMAGE_MIN_DPI`.
        reference_style: the declared bib style (e.g. "natbib"/"plainnat"/"numeric") checked
            present in ``draft.tex`` (a ``\\bibliographystyle`` wiring), or None to skip.
        max_pages: ADVISORY only -- there is no deterministic page count without a compile,
            so this is surfaced, never gated (design §1.3).
        max_words: a deterministic word-count ceiling over the rendered prose; None to skip.
        reproduction_bundle: F3 bundle on/off -- when on, ``paper/reproduce.py`` must exist
            and reference the recorded ``code_ref``s (fail-open for pointer-only bundles,
            design §6 OF-4). Default True.
        advisory: free-form conditions surfaced in the verify report but NEVER gated.
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    spec_id: str = Field(..., min_length=1, description="The run's Spec id this governs")
    frozen_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Freeze timestamp (ISO-8601 UTC)",
    )
    digest: str = Field(
        default="",
        description="Tamper-evidence sha256 recorded at freeze (empty pre-freeze)",
    )
    venue: Optional[str] = Field(
        default=None, description="Free-text venue label (arXiv/JOSS/journal) or None"
    )
    required_sections: List[str] = Field(
        default_factory=list,
        description="Section names that must be present in draft.tex",
    )
    figure_font_policy: bool = Field(
        default=True, description="F2 font policy on/off (default on)"
    )
    image_min_dpi: Optional[int] = Field(
        default=DEFAULT_IMAGE_MIN_DPI,
        description="Raster figure min effective DPI (None disables the gate)",
    )
    reference_style: Optional[str] = Field(
        default=None, description="Declared bib style checked in draft.tex, or None"
    )
    max_pages: Optional[int] = Field(
        default=None, description="ADVISORY page limit (no deterministic page count)"
    )
    max_words: Optional[int] = Field(
        default=None, description="Deterministic word-count ceiling over prose, or None"
    )
    reproduction_bundle: bool = Field(
        default=True, description="F3 reproduction bundle on/off (default on)"
    )
    advisory: List[str] = Field(
        default_factory=list,
        description="Free-form conditions surfaced but NEVER gated",
    )

    # @MX:ANCHOR: [AUTO] the FROZEN publishing-requirements contract -- the F1 record the
    #   verify umbrella gate (paper_requirements_clean) checks the rendered paper against.
    # @MX:REASON: [AUTO] pubreqs freeze (cli), pubreqs_digest (provenance), and
    #   _check_paper_requirements (loop/verify) all read this typed contract; freezing the
    #   gate-bearing fields is what makes "no moving the goalposts" enforceable (a relaxed
    #   threshold after a failure would be a silent record edit, mirroring Spec S1).


__all__ = ["PubReqs", "DEFAULT_REQUIRED_SECTIONS", "DEFAULT_IMAGE_MIN_DPI"]
