"""
Agent-authored figure specs + a deterministic LaTeX-NATIVE (pgfplots) data-plot
renderer (design/paper-figures-and-si.md, Phase 1: D1/D4).

Same agent/engine split as the prose hook (``render/prose.py``): the AGENT authors
WHAT to plot -- which Evidence series, the plot kind, the caption, a stable label,
and the x of each point -- as *input*; the ENGINE renders deterministically FROM
THE RECORD, pulling each y value off the cited ``EvidenceItem`` (no LLM at render
time). A figure is only as honest as the Evidence behind it; the y it draws is the
recorded value, never an invented or silently-dropped one.

Why a SERIES ACROSS Evidence items (not an array inside one item): a ``Result`` is
scalar (one ``point`` / ``effect_size`` / ... per item, design/abstractions.md), so a
data plot is built from MANY items -- each ``PlotPoint`` cites one ``EvidenceItem`` and
contributes one ``(x, y)`` coordinate, with x supplied by the spec and y pulled from
that item's ``Result``.

Why LaTeX-native (pgfplots) and not an image: pgfplots is a LaTeX package Overleaf
ships -- the figure is emitted as *text* inside the ``.tex`` (no Python plotting
dependency, no image files), so the ``paper/`` folder stays trivially self-contained
for an Overleaf folder-upload and determinism is automatic (it is text).

This module lives in ``render/`` (the kernel) and -- like the rest of the kernel --
imports ``sci_adk.core`` ONLY (F4 seam; no adapter, no loop, no LLM, no fs/network).
The renderers are PURE (data in, string out) and deterministic (same spec + Evidence
-> byte-identical string).

Reference: design/paper-figures-and-si.md, design/directory-structure.md (render/),
design/rigor-shell-architecture.md (kernel/adapter seam, F4).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Annotated, List, Literal, Sequence, Tuple, Union

from pydantic import BaseModel, Discriminator, Field, Tag

from sci_adk.core.evidence import EvidenceItem

# The Result scalar fields a figure may plot as y. Restricted to the numeric scalars
# (the qualitative ``finding``/``artifact_ref`` are not plottable); keep in sync with
# the numeric fields of ``sci_adk.core.evidence.Result``.
YField = Literal[
    "point", "effect_size", "p_value", "posterior", "residual", "predictive_error"
]

# A figure id must be a LaTeX-safe label slug: it becomes ``\label{fig:<id>}`` and is
# referenced by ``\ref{fig:<id>}`` in the body. Anchored, ASCII-only, no spaces/braces/
# backslashes, and not starting with ``_`` or ``-`` (so the label reads cleanly).
_FIG_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class PlotPoint(BaseModel):
    """One ``(x, y)`` coordinate: the agent supplies ``x`` + which Evidence item to
    pull ``y`` from; the engine reads ``y`` off that item's ``Result`` at render time.

    Attributes:
        evidence_id: the ``EvidenceItem.id`` whose ``Result`` supplies this point's y.
        x: the abscissa (agent-authored -- e.g. a run index / dose / size).
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    evidence_id: str = Field(..., min_length=1, description="EvidenceItem id supplying y")
    x: float = Field(..., description="Abscissa (agent-authored)")


class PlotSeries(BaseModel):
    """One plotted series: a ``y_field`` selector + the points that make it up.

    Every point's y is read from the named ``y_field`` of its cited item's ``Result``
    (the same field for the whole series, so a series is one comparable quantity).

    Attributes:
        name: an optional legend/label name for the series.
        y_field: which numeric ``Result`` scalar to read as y (default ``point``).
        points: at least one ``PlotPoint`` (a series with no points is meaningless).
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    name: str = Field(default="", description="Optional series name (legend)")
    y_field: YField = Field(
        default="point", description="Result scalar read as y for every point"
    )
    points: List[PlotPoint] = Field(
        ..., min_length=1, description="The series points (>=1)"
    )


class NativePlot(BaseModel):
    """A LaTeX-native (pgfplots) plot: a kind + axis labels + one-or-more series.

    Attributes:
        type: pgfplots mapping -- ``line`` (plain ``\\addplot``), ``scatter``
            (``\\addplot[only marks]``), ``bar`` (``\\addplot[ybar]``).
        xlabel / ylabel: axis labels (rendered LaTeX-safe via the paper sanitizer).
        series: at least one ``PlotSeries``.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    type: Literal["line", "scatter", "bar"] = Field(..., description="Plot kind")
    xlabel: str = Field(default="", description="x-axis label")
    ylabel: str = Field(default="", description="y-axis label")
    series: List[PlotSeries] = Field(
        ..., min_length=1, description="Plotted series (>=1)"
    )


def _validate_fig_id(v: str) -> str:
    """Validate (and strip) a figure id to a LaTeX-safe label slug.

    Shared by both figure kinds: the id becomes ``\\label{fig:<id>}`` and is referenced
    by ``\\ref{fig:<id>}`` in the body, so a space / brace / backslash would break the
    label. Module-level (not a per-class method) so the native and image specs validate
    the id identically.
    """
    v = v.strip()
    if not _FIG_ID_RE.match(v):
        raise ValueError(
            f"figure id {v!r} is not a LaTeX-safe slug "
            r"(must match ^[A-Za-z0-9][A-Za-z0-9_-]*$ so \label{fig:<id>} is safe)"
        )
    return v


class FigureSpec(BaseModel):
    """An agent-authored NATIVE figure spec (the figure analogue of ``PaperProse``).

    The agent authors WHAT (the caption, the plot, which Evidence ids, the x of each
    point + a stable id); the engine renders it deterministically FROM the Evidence.

    Attributes:
        kind: the union discriminator, fixed ``"native"``. It DEFAULTS to ``"native"``
            so an existing figure JSON authored before the image kind existed (no
            ``kind`` key) still parses as a native spec -- the byte-identical-output
            invariant for the pre-image native path.
        id: a LaTeX-safe slug -- becomes ``\\label{fig:<id>}`` so the body's
            ``\\ref{fig:<id>}`` resolves and numbering is automatic. Must be non-empty
            and match ``^[A-Za-z0-9][A-Za-z0-9_-]*$``.
        caption: the figure caption (rendered LaTeX-safe).
        plot: the native (pgfplots) plot to draw.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    kind: Literal["native"] = Field(
        default="native", description="Union discriminator (default native)"
    )
    id: str = Field(..., min_length=1, description="LaTeX-safe label slug for fig:<id>")
    caption: str = Field(..., description="Figure caption")
    plot: NativePlot = Field(..., description="The native (pgfplots) plot")

    def __init__(self, **data):  # noqa: D401 - pydantic init hook for id validation
        if "id" in data and isinstance(data["id"], str):
            data["id"] = _validate_fig_id(data["id"])
        super().__init__(**data)


class ImageFigureSpec(BaseModel):
    """An agent-authored IMAGE figure spec: an ``\\includegraphics`` of a co-located
    source image, for a diagram that cannot be expressed natively (D1).

    Domain-FREE: the agent/experiment produces the image with whatever tool fits its
    domain (a plotting library, a structure drawer, an exported diagram, ...); this spec
    only carries a path to that EXISTING file. The kernel never knows the domain.

    The agent authors WHAT (the caption, a stable semantic id, and the SOURCE path of an
    EXISTING image file); the compiler co-locates that source to ``paper/figures/fig<N>
    <ext>`` (the ONLY filesystem toucher, ``N`` = the body-reference number assigned to
    this figure) and this PURE renderer emits the matching
    ``\\includegraphics{figures/fig<N><ext>}``. The renderer never reads the file -- it
    derives ``<ext>`` from the source path's suffix as a string op; WHERE the image comes
    from is the experiment's concern, not the kernel's.

    Why ``fig<N>`` and not ``<id>`` as the filename: the saved file name follows the
    standard academic FIGURE NUMBER (the order the figure is first referenced in the
    paper body -- see :func:`order_figures_by_reference`), which is GENERIC and
    domain-free. The semantic ``id`` is kept only as the ``\\label{fig:<id>}`` so the
    body's ``\\ref{fig:<id>}`` still resolves -- the number is what the reader sees, the
    id is the internal anchor.

    Attributes:
        kind: the union discriminator, fixed ``"image"``.
        id: a LaTeX-safe slug -- the stable ``\\label{fig:<id>}`` so the body's
            ``\\ref{fig:<id>}`` resolves (NOT the filename -- the file is ``fig<N>``).
            Same validation as :class:`FigureSpec`.
        caption: the figure caption (rendered LaTeX-safe).
        image: the SOURCE path/ref of an existing image file (relative or absolute).
            Only its SUFFIX is used here (to build ``figures/fig<N><ext>``); the compiler
            resolves + copies the actual bytes.
        width: an optional LaTeX width spec for ``\\includegraphics[width=...]`` (e.g.
            ``0.8\\textwidth``). Empty (the default) -> ``\\linewidth``.
    """

    model_config = {"frozen": True, "str_strip_whitespace": True}

    kind: Literal["image"] = Field(..., description="Union discriminator (image)")
    id: str = Field(..., min_length=1, description="LaTeX-safe label slug for fig:<id>")
    caption: str = Field(..., description="Figure caption")
    image: str = Field(
        ..., min_length=1, description="Source path/ref of an existing image file"
    )
    width: str = Field(
        default="", description="LaTeX width spec (empty -> \\linewidth)"
    )

    def __init__(self, **data):  # noqa: D401 - pydantic init hook for id validation
        if "id" in data and isinstance(data["id"], str):
            data["id"] = _validate_fig_id(data["id"])
        super().__init__(**data)


def _figure_kind(value: object) -> str:
    """Extract the union tag for an :data:`AnyFigure` payload, defaulting to ``native``.

    A plain ``str``-valued ``Field(discriminator="kind")`` would reject a native payload
    that OMITS ``kind`` (pydantic does not apply a field default during tag extraction),
    breaking the byte-identical back-compat invariant for pre-image native JSON. A
    callable :class:`Discriminator` lets us map an absent / ``None`` / empty ``kind`` to
    ``"native"`` -- so an old native spec (no ``kind`` key) and an explicit
    ``kind:"image"`` both route correctly. Accepts a dict (JSON) or a model instance.
    """
    if isinstance(value, dict):
        kind = value.get("kind")
    else:
        kind = getattr(value, "kind", None)
    return kind or "native"


# The agent-authored figure union, discriminated on ``kind`` via a callable that
# defaults a missing tag to ``native``: a native (pgfplots) plot or an image
# (\includegraphics). Each member is ``Tag``-annotated so the callable's return value
# maps to it.
AnyFigure = Annotated[
    Union[
        Annotated[FigureSpec, Tag("native")],
        Annotated[ImageFigureSpec, Tag("image")],
    ],
    Discriminator(_figure_kind),
]


class PaperFigures(BaseModel):
    """The top-level figure hook (mirrors ``PaperProse``): a list of figure specs.

    Absent / empty -> no figures (the renderer emits nothing new, preserving the
    byte-identical skeleton, exactly like the prose hook). Each entry is an
    :data:`AnyFigure` -- a native or an image spec, discriminated on ``kind``.
    """

    model_config = {"frozen": True}

    figures: List[AnyFigure] = Field(
        default_factory=list, description="Agent-authored figure specs (empty -> none)"
    )


class FigureConsistencyReport(BaseModel):
    """The Phase-1 prose<->figure ref consistency REPORT (D4; not a hard gate here).

    Attributes:
        dangling: ``fig:<id>`` referenced via ``\\ref`` with no matching figure id.
        orphan: figure ids never referenced via ``\\ref`` in the body.
        ok: True iff there is no dangling ref and no orphan figure.
    """

    model_config = {"frozen": True}

    dangling: List[str] = Field(default_factory=list, description="Refs with no figure")
    orphan: List[str] = Field(default_factory=list, description="Figures never ref'd")
    ok: bool = Field(..., description="True iff no dangling ref and no orphan figure")


def _sanitize(s: str) -> str:
    """LaTeX-safe escaping for interpolated figure text (caption / axis labels).

    Reuses the paper renderer's :func:`sci_adk.render.paper._latex_sanitize` (the same
    escaper + unicode safety net the rest of the document uses, so a figure caption is
    sanitized identically to a section body). Imported lazily INSIDE the function to
    avoid a ``paper <-> figures`` import cycle: ``paper.py`` imports the figure renderer
    at module load, so ``figures.py`` must not import ``paper`` at module load.
    """
    from sci_adk.render.paper import _latex_sanitize

    return _latex_sanitize(s)


def _format_float(v: float) -> str:
    """Deterministic, compact float formatting for a coordinate.

    ``%g`` drops trailing zeros (``1.0 -> 1``, ``0.5 -> 0.5``) so the emitted
    coordinates read cleanly and are byte-stable across renders.
    """
    return f"{v:g}"


def _y_value(item: EvidenceItem, y_field: str, evidence_id: str) -> float:
    """Pull the ``y_field`` scalar off ``item.result`` -- record fidelity, fail-loud.

    Raises ``ValueError`` when the field is None, non-numeric, or non-finite (NaN /
    +-inf). A figure must not silently invent or drop a point, nor emit an
    uncompilable coordinate: a missing/unplottable recorded value is an authoring
    error, surfaced, not swallowed.
    """
    value = getattr(item.result, y_field, None)
    if value is None:
        raise ValueError(
            f"evidence '{evidence_id}': result.{y_field} is None -- a figure point "
            f"cannot be drawn from an unrecorded value (record fidelity)"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"evidence '{evidence_id}': result.{y_field} is non-numeric "
            f"({type(value).__name__}) -- not plottable"
        )
    # pydantic accepts NaN/inf and isinstance(nan, float) is True, so the numeric guard
    # above passes -- but '%g' would emit the literal 'nan'/'inf'/'-inf', which pgfplots
    # cannot compile (defeating the Overleaf folder-upload goal). Reject non-finite y
    # with the same fail-loud record-fidelity spirit as the None/unknown-id cases.
    if not math.isfinite(float(value)):
        raise ValueError(
            f"figure point cites evidence '{evidence_id}': result.{y_field} is {value} "
            f"(NaN/infinite) -- not a plottable coordinate (record fidelity)"
        )
    return float(value)


def _addplot_options(plot_type: str) -> str:
    """The pgfplots ``\\addplot`` option block for a plot kind (``[...]`` or empty)."""
    if plot_type == "scatter":
        return "[only marks]"
    if plot_type == "bar":
        return "[ybar]"
    return ""  # line: a plain \addplot


def render_native_figure(
    spec: FigureSpec, evidence: Sequence[EvidenceItem]
) -> str:
    """Render an agent-authored ``FigureSpec`` to a LaTeX ``figure`` env (pgfplots).

    PURE + deterministic: pulls each y FROM the cited ``EvidenceItem`` (never the
    spec), emits one ``\\addplot coordinates {...}`` per series, and a
    ``\\caption``+``\\label{fig:<id>}``. No fs/LLM/network, no ``\\includegraphics``
    (native = text-only, so the ``paper/`` folder stays self-contained).

    Args:
        spec: the figure spec (caption, plot kind, series, stable id).
        evidence: the Evidence record; each ``PlotPoint.evidence_id`` is looked up
            here and its ``Result`` supplies the point's y.

    Returns:
        A LaTeX ``figure`` environment string.

    Raises:
        ValueError: if a ``PlotPoint`` cites an unknown ``evidence_id``, or the
            selected ``y_field`` is None / non-numeric on the cited item (record
            fidelity -- a point is never silently invented or dropped).
    """
    by_id = {ev.id: ev for ev in evidence}
    plot = spec.plot
    options = _addplot_options(plot.type)

    lines: List[str] = []
    lines.append(r"\begin{figure}[htbp]")
    lines.append(r"\centering")
    lines.append(r"\begin{tikzpicture}")
    lines.append(
        f"\\begin{{axis}}[xlabel={{{_sanitize(plot.xlabel)}}}, "
        f"ylabel={{{_sanitize(plot.ylabel)}}}]"
    )

    for series in plot.series:
        coords: List[str] = []
        for pt in series.points:
            item = by_id.get(pt.evidence_id)
            if item is None:
                raise ValueError(
                    f"figure '{spec.id}': evidence id '{pt.evidence_id}' not found "
                    f"in the record -- a figure point must cite a real Evidence item "
                    f"(record fidelity)"
                )
            y = _y_value(item, series.y_field, pt.evidence_id)
            coords.append(f"({_format_float(pt.x)}, {_format_float(y)})")
        coord_str = " ".join(coords)
        lines.append(f"\\addplot{options} coordinates {{{coord_str}}};")

    lines.append(r"\end{axis}")
    lines.append(r"\end{tikzpicture}")
    lines.append(f"\\caption{{{_sanitize(spec.caption)}}}")
    lines.append(f"\\label{{fig:{spec.id}}}")
    lines.append(r"\end{figure}")
    return "\n".join(lines)


def render_image_figure(spec: ImageFigureSpec, number: int) -> str:
    """Render an agent-authored ``ImageFigureSpec`` to a LaTeX ``figure`` env.

    PURE: no Evidence is consulted (an image figure is a diagram, not a data plot) and
    NO filesystem access -- the ``<ext>`` is derived from ``spec.image``'s suffix as a
    string op only; the compiler co-locates the actual bytes. The included path is
    ALWAYS ``figures/fig<number><ext>`` -- the GENERIC, domain-free figure-NUMBER
    filename (``number`` = the body-reference order assigned by
    :func:`order_figures_by_reference`), so the saved file is ``fig1.png`` /
    ``fig2.pdf`` / ... never an agent-chosen id. The compiler co-locates the source to
    EXACTLY this ``figures/fig<number><ext>`` (shared numbering), so the ``.tex`` and
    the file agree and the ``paper/`` folder stays self-contained.

    The ``\\label{fig:<id>}`` keeps the agent's SEMANTIC id (not the number), so the
    body's ``\\ref{fig:<id>}`` resolves regardless of kind; LaTeX assigns the printed
    number from SOURCE ORDER, and the caller emits figures in body-reference order so
    "Figure ``<number>``" matches the file ``fig<number>`` exactly.

    Args:
        spec: the image figure spec (caption, stable id, source image path, width).
        number: the 1-based body-reference figure number (the file becomes
            ``fig<number><ext>``).

    Returns:
        A LaTeX ``figure`` environment string (``\\includegraphics`` + caption + label).

    Raises:
        ValueError: if ``spec.image`` has no extension. ``\\includegraphics`` needs a
            resolvable file ending; an extensionless source cannot name a graphic, so
            this fails loud (record fidelity -- never emit an uncompilable include).
    """
    ext = Path(spec.image).suffix
    if not ext:
        raise ValueError(
            f"figure '{spec.id}': image source {spec.image!r} has no file extension -- "
            r"\includegraphics needs a resolvable file (e.g. diagram.pdf / .png)"
        )
    # An empty width spec -> \linewidth (the figure spans the text column by default).
    width = spec.width or r"\linewidth"

    lines: List[str] = []
    lines.append(r"\begin{figure}[htbp]")
    lines.append(r"\centering")
    lines.append(f"\\includegraphics[width={width}]{{figures/fig{number}{ext}}}")
    lines.append(f"\\caption{{{_sanitize(spec.caption)}}}")
    lines.append(f"\\label{{fig:{spec.id}}}")
    lines.append(r"\end{figure}")
    return "\n".join(lines)


def image_figure_filename(spec: ImageFigureSpec, number: int) -> str:
    """The co-located filename an image figure resolves to: ``fig<number><ext>``.

    The SINGLE source of truth the compiler's ``_colocate_figures`` calls so the file it
    writes matches the ``\\includegraphics{figures/fig<number><ext>}`` that
    :func:`render_image_figure` emits for the SAME ``number`` -- the renderer and the
    compiler must never derive this name divergently. PURE: ``<ext>`` is the source
    suffix (a string op); the same extensionless-source guard as the renderer.

    Raises:
        ValueError: if ``spec.image`` has no extension (mirrors :func:`render_image_figure`).
    """
    ext = Path(spec.image).suffix
    if not ext:
        raise ValueError(
            f"figure '{spec.id}': image source {spec.image!r} has no file extension -- "
            r"\includegraphics needs a resolvable file (e.g. diagram.pdf / .png)"
        )
    return f"fig{number}{ext}"


def render_figure(spec: AnyFigure, evidence: Sequence[EvidenceItem], number: int) -> str:
    """Render any :data:`AnyFigure` to a LaTeX ``figure`` env, routing by ``spec.kind``.

    The single entry point the paper/SI renderers call so they need not branch on the
    figure kind: a ``native`` spec is plotted from the Evidence record
    (:func:`render_native_figure`, which ignores ``number`` -- native = inline text, no
    file), an ``image`` spec is an ``\\includegraphics`` of ``figures/fig<number><ext>``
    (:func:`render_image_figure`, which ignores ``evidence``). ``number`` is the figure's
    1-based body-reference position (see :func:`order_figures_by_reference`). PURE -- it
    dispatches only; the underlying renderers carry the purity/record-fidelity guarantees.
    """
    if spec.kind == "image":
        return render_image_figure(spec, number)
    return render_native_figure(spec, evidence)


def figure_labels(figs: Sequence[AnyFigure]) -> List[str]:
    """The ``fig:<id>`` labels of ``figs``, enforcing UNIQUE ids.

    A duplicate id would emit two ``\\label{fig:<id>}`` -- a LaTeX "multiply defined
    label" error and an ambiguous ``\\ref`` -- so it is rejected here (fail-loud, not
    silently de-duplicated).

    Raises:
        ValueError: on a duplicate figure id.
    """
    labels: List[str] = []
    seen: set[str] = set()
    for f in figs:
        if f.id in seen:
            raise ValueError(
                f"duplicate figure id '{f.id}' -- ids must be unique "
                r"(each becomes a \label{fig:<id>})"
            )
        seen.add(f.id)
        labels.append(f"fig:{f.id}")
    return labels


# Matches ``\ref{fig:<id>}`` (the only ref form the consistency check inspects). The
# id portion is the LaTeX-safe slug set; a ``\ref{sec:...}`` / ``\ref{tab:...}`` is
# deliberately NOT a figure ref and is ignored.
_FIG_REF_RE = re.compile(r"\\ref\{(fig:[A-Za-z0-9][A-Za-z0-9_-]*)\}")


def order_figures_by_reference(
    figures: Sequence[AnyFigure], body_latex: str
) -> List[Tuple[int, AnyFigure]]:
    """Assign each figure its body-reference NUMBER (the standard academic convention).

    A main-paper figure's number is the order it is FIRST referenced in the paper body:
    the first ``\\ref{fig:<id>}`` to appear -> Figure 1, the second DISTINCT one -> 2,
    and so on. A figure NEVER referenced still gets a stable number -- those are appended
    AFTER all referenced figures, in their given (supply) order, so every figure is
    numbered and saved deterministically (an unreferenced figure remains orphan-flagged
    by :func:`check_figure_consistency`, but it is not dropped).

    The renderer emits figure environments IN THIS ORDER so LaTeX's source-order auto-
    numbering yields Figure 1 = first-referenced, etc.; the semantic ``\\label{fig:<id>}``
    is preserved so the body's existing ``\\ref{fig:<id>}`` still resolves (no ref
    rewriting). This is also the SINGLE numbering the compiler reuses to name the
    co-located image files ``fig<N><ext>``, so the ``\\includegraphics`` path and the
    saved filename agree exactly (the number is computed ONCE and shared).

    PURE + deterministic: same ``figures`` + same ``body_latex`` -> same ordering. A
    duplicate figure id is rejected up front (it would make ``\\ref`` ambiguous and clobber
    one ``fig<N>`` file with another).

    Args:
        figures: the agent-authored figure specs (native and/or image), in supply order.
        body_latex: the rendered paper body to scan for ``\\ref{fig:<id>}`` appearance
            order. This MUST be the same canonical body the SI orders against, so both
            documents share one ``fig<N>`` numbering.

    Returns:
        A list of ``(number, figure)`` pairs in emission order: referenced figures first
        (by first-reference position, lowest number first), then unreferenced figures in
        supply order. ``number`` is 1-based and contiguous.

    Raises:
        ValueError: on a duplicate figure id (each id must be unique -- it is both a
            ``\\label`` anchor and, for images, tied to a distinct ``fig<N>`` file).
    """
    figs = list(figures)
    by_id: dict[str, AnyFigure] = {}
    for f in figs:
        if f.id in by_id:
            raise ValueError(
                f"duplicate figure id '{f.id}' -- ids must be unique "
                r"(each becomes a \label{fig:<id>} and an image fig<N> file)"
            )
        by_id[f.id] = f

    # First-reference order: walk the body's \ref{fig:...} in appearance, keeping the
    # FIRST occurrence of each id that names a real figure (a dangling \ref to no figure
    # is ignored here -- check_figure_consistency reports it).
    referenced: List[AnyFigure] = []
    seen: set[str] = set()
    for match in _FIG_REF_RE.finditer(body_latex):
        fig_id = match.group(1)[len("fig:"):]  # strip the "fig:" prefix
        if fig_id in seen or fig_id not in by_id:
            continue
        seen.add(fig_id)
        referenced.append(by_id[fig_id])

    # Unreferenced figures keep supply order, appended after the referenced ones.
    unreferenced = [f for f in figs if f.id not in seen]

    ordered = referenced + unreferenced
    return [(i + 1, f) for i, f in enumerate(ordered)]


def check_figure_consistency(
    figure_ids: Sequence[str], body_latex: str
) -> FigureConsistencyReport:
    """Scan ``body_latex`` for ``\\ref{fig:...}`` and report ref/figure integrity (D4).

    PURE. Two findings, both surfaced as a REPORT (the Phase-1 non-blocking channel --
    the hard verify-gate is Phase 3):
      - ``dangling``: a ``\\ref{fig:x}`` with no matching figure id.
      - ``orphan``: a figure id never referenced.

    Args:
        figure_ids: the defined figure label ids (``fig:<id>`` form, e.g. from
            :func:`figure_labels`).
        body_latex: the rendered document body to scan for ``\\ref{fig:...}``.

    Returns:
        A :class:`FigureConsistencyReport` (``ok`` iff no dangling and no orphan).
    """
    defined = set(figure_ids)
    referenced = set(_FIG_REF_RE.findall(body_latex))

    dangling = sorted(referenced - defined)
    orphan = sorted(defined - referenced)
    return FigureConsistencyReport(
        dangling=dangling, orphan=orphan, ok=not dangling and not orphan
    )


__all__ = [
    "PlotPoint",
    "PlotSeries",
    "NativePlot",
    "FigureSpec",
    "ImageFigureSpec",
    "AnyFigure",
    "PaperFigures",
    "FigureConsistencyReport",
    "render_native_figure",
    "render_image_figure",
    "image_figure_filename",
    "render_figure",
    "figure_labels",
    "order_figures_by_reference",
    "check_figure_consistency",
]
