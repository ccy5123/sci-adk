"""
The FROZEN package-requirements contract (design/near-submission-package.md §2).

A ``PackageReqs`` is the WORKSPACE-level companion to :class:`sci_adk.core.pubreqs.PubReqs`:
where ``PubReqs`` freezes the conditions a single ``runs/<id>/paper/`` must meet, a
``PackageReqs`` freezes the conditions the ONE merged submission package (a workspace-level
``package/`` -- main.tex + si.tex + figures + the 6-folder reproduction bundle) must meet. It
is elicited once at ``/sci package`` time and frozen at ``<ws>/pkgreqs.json`` (at the
workspace ROOT, beside ``runs/`` -- NOT inside the regenerated ``package/`` dir, so re-running
``package`` never clobbers it). ``sci-adk verify <ws>`` then checks the assembled package
AGAINST it -- the umbrella ``package_requirements_clean`` gate (loop/verify.py) runs only the
deterministically-checkable requirements it declares.

Record/belief separation (design §0): this is a RECORD (a frozen contract), checked against
the assembled package; it is never authored by an LLM at verify time and never injects a
sci-adk-internal noun into ``main.tex``. All GATE-BEARING fields are frozen
(anti-moving-the-goalposts): you cannot relax ``abstract_max_words`` after seeing the abstract
fail except by an explicit amendment that re-freezes a new contract with a new digest.

Like ``PubReqs`` (and unlike :class:`Spec`, whose digest is computed on demand), the design
(§2) stores the PackageReqs digest IN ``pkgreqs.json`` -- it is tamper-evidence the freeze
step records once. :func:`sci_adk.provenance.pkgreqs_digest` computes it; the CLI
``pkgreqs freeze`` verb writes it into the ``digest`` field.

Reference: design/near-submission-package.md §2, design/paper-publishing-requirements.md §1
(the per-run PubReqs sibling), src/sci_adk/core/pubreqs.py (the mirrored frozen model),
src/sci_adk/core/spec.py (the Spec freeze discipline).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple, Union

from pydantic import BaseModel, Field

# The IMRaD default (mirrors PubReqs.DEFAULT_REQUIRED_SECTIONS; SPEC-PAPER-GATE-001
# REQ-PG-105): the fixed required-sections set offered by the "use defaults" fast-path,
# INCLUDING Conclusion. Abstract is accepted as a \begin{abstract} environment OR a
# \section{Abstract}; the rest are \section{...} (see the gate's required_sections check,
# which reuses render.pubreqs_checks.required_sections_problems).
DEFAULT_REQUIRED_SECTIONS: List[str] = [
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
]

# The default raster DPI floor (mirrors PubReqs.DEFAULT_IMAGE_MIN_DPI: 300 = print).
DEFAULT_IMAGE_MIN_DPI = 300

# The sentinel for "synthesize ALL runs in the workspace" (design §2 ``runs: list | "all"``).
# The model normalizes a bare ``"all"`` string to this literal so callers can test
# ``pkgreqs.runs == ALL_RUNS`` uniformly.
ALL_RUNS = "all"


class PackageReqs(BaseModel):
    """A FROZEN package-requirements contract (the workspace-level artifact, design §2).

    All gate-bearing fields are immutable after construction (``model_config frozen``),
    mirroring :class:`sci_adk.core.pubreqs.PubReqs`'s freeze discipline (which mirrors
    :class:`Spec`'s S1): a requirement cannot be silently relaxed after the package fails --
    only an explicit amendment (a new contract + a new digest) can change it.

    Attributes:
        frozen_at: ISO-8601 UTC freeze timestamp.
        digest: the tamper-evidence sha256 (hex) recorded at freeze time
            (:func:`sci_adk.provenance.pkgreqs_digest`). Stored in the artifact, unlike the
            Spec's on-demand digest (design §2). Empty pre-freeze; the CLI fills it.
        venue: a free-text venue label (reuses ``PubReqs.venue`` semantics) or None.
        required_sections: section names that MUST be present in ``main.tex`` (each as a
            ``\\section{...}``; "Abstract" also accepts ``\\begin{abstract}``). The IMRaD
            default is :data:`DEFAULT_REQUIRED_SECTIONS`.
        figure_font_policy: F2 font policy on/off -- when on, a figure-bearing package
            ``main.tex`` must carry the F2 font preamble (newtxmath + helvet). Mirrors
            :class:`sci_adk.core.pubreqs.PubReqs`. Default True.
        image_min_dpi: the raster (image) figure minimum effective DPI checked over the
            package ``main.tex`` figures; None disables the DPI gate. Mirrors PubReqs.
            Default :data:`DEFAULT_IMAGE_MIN_DPI`.
        reference_style: the declared bib style (e.g. "natbib"/"plainnat") checked present in
            ``main.tex`` (a ``\\bibliographystyle`` wiring), or None to skip.
        abstract_max_words: the venue abstract word limit (e.g. 300); None disables the
            abstract word-count gate.
        body_word_range: an ADVISORY ``(min, max)`` body word range (e.g. (4000, 7000));
            SURFACED in the verify report, NEVER gated (design §3) -- a thin or long draft is
            an author concern, not a mechanical failure.
        runs: which runs the package synthesizes -- the literal ``"all"`` (default) for every
            ``runs/<id>/`` in the workspace, or an explicit list of run ids.
        advisory: free-form conditions surfaced in the verify report but NEVER gated.
    """

    model_config = {
        "frozen": True,
        "str_strip_whitespace": True,
    }

    frozen_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Freeze timestamp (ISO-8601 UTC)",
    )
    digest: str = Field(
        default="",
        description="Tamper-evidence sha256 recorded at freeze (empty pre-freeze)",
    )
    venue: Optional[str] = Field(
        default=None, description="Free-text venue label (reuses PubReqs.venue semantics)"
    )
    required_sections: List[str] = Field(
        default_factory=list,
        description="Section names that must be present in main.tex",
    )
    figure_font_policy: bool = Field(
        default=True, description="F2 font policy on/off (default on); mirrors PubReqs"
    )
    image_min_dpi: Optional[int] = Field(
        default=DEFAULT_IMAGE_MIN_DPI,
        description="Raster figure min effective DPI (None disables the gate); mirrors PubReqs",
    )
    reference_style: Optional[str] = Field(
        default=None, description="Declared bib style checked in main.tex, or None"
    )
    abstract_max_words: Optional[int] = Field(
        default=None,
        description="Abstract word-count ceiling (venue limit, e.g. 300); None disables",
    )
    body_word_range: Optional[Tuple[int, int]] = Field(
        default=None,
        description="ADVISORY (min, max) body word range -- surfaced, NEVER gated",
    )
    runs: Union[List[str], str] = Field(
        default=ALL_RUNS,
        description='Which runs to synthesize: "all" (default) or an explicit list of run ids',
    )
    advisory: List[str] = Field(
        default_factory=list,
        description="Free-form conditions surfaced but NEVER gated",
    )

    # @MX:ANCHOR: [AUTO] the FROZEN package-requirements contract -- the workspace-level
    #   record the verify umbrella gate (package_requirements_clean) checks the assembled
    #   package against.
    # @MX:REASON: [AUTO] pkgreqs freeze (cli), pkgreqs_digest (provenance), and
    #   _check_package_requirements (loop/verify) all read this typed contract; freezing the
    #   gate-bearing fields is what makes "no moving the goalposts" enforceable (a relaxed
    #   abstract limit after a failure would be a silent record edit, mirroring PubReqs/Spec).


__all__ = [
    "PackageReqs",
    "DEFAULT_REQUIRED_SECTIONS",
    "DEFAULT_IMAGE_MIN_DPI",
    "ALL_RUNS",
]
