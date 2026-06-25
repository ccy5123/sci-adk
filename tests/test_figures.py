"""
paper-figures Phase 1 (RED-first): an agent-authored figure-spec hook + a
deterministic LaTeX-NATIVE (pgfplots) data-plot renderer + stable figure labels +
a prose<->figure ref consistency check (design/paper-figures-and-si.md, D1/D4).

Record fidelity is the spine: the AGENT authors WHAT to plot (the spec -- caption,
plot kind, which Evidence ids, the x of each point), and the ENGINE pulls the y
value FROM the Evidence record (no invented/silently-dropped points). The renderer
is PURE (data in, string out), deterministic (re-render byte-identical), and emits
NO image/external-file ref (native = text-only, so the paper/ folder stays
self-contained).

These pin the behavior before any implementation exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.render.figures import (
    FigureConsistencyReport,
    FigureSpec,
    ImageFigureSpec,
    NativePlot,
    PaperFigures,
    PlotPoint,
    PlotSeries,
    check_figure_consistency,
    figure_labels,
    image_figure_filename,
    order_figures_by_reference,
    render_figure,
    render_image_figure,
    render_native_figure,
)

_T0 = datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)


def _ev(
    ev_id: str,
    *,
    point=None,
    effect_size=None,
    p_value=None,
    finding=None,
    hyp_id: str = "hyp-1",
):
    """An EvidenceItem whose Result carries the scalar(s) under test."""
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id="t-fig",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(
            type="quantitative",
            point=point,
            effect_size=effect_size,
            p_value=p_value,
            finding=finding,
        ),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
    )


def _series_evidence():
    """Three items contributing one (x, y=point) point each: a SERIES across items."""
    return [
        _ev("ev-a", point=1.0),
        _ev("ev-b", point=4.0),
        _ev("ev-c", point=9.0),
    ]


def _line_spec(fig_id: str = "growth") -> FigureSpec:
    return FigureSpec(
        id=fig_id,
        caption="Point estimate across runs.",
        plot=NativePlot(
            type="line",
            xlabel="run index",
            ylabel="point estimate",
            series=[
                PlotSeries(
                    name="point",
                    y_field="point",
                    points=[
                        PlotPoint(evidence_id="ev-a", x=1.0),
                        PlotPoint(evidence_id="ev-b", x=2.0),
                        PlotPoint(evidence_id="ev-c", x=3.0),
                    ],
                )
            ],
        ),
    )


# ---------------------------------------------------------------------------
# render_native_figure: a pgfplots figure env pulled FROM the Evidence record.
# ---------------------------------------------------------------------------

class TestRenderNativeFigure:
    def test_emits_figure_axis_caption_label(self):
        spec = _line_spec("growth")
        tex = render_native_figure(spec, _series_evidence())

        assert r"\begin{figure}" in tex
        assert r"\end{figure}" in tex
        assert r"\begin{axis}" in tex
        assert r"\end{axis}" in tex
        assert r"\begin{tikzpicture}" in tex
        # Caption + stable label.
        assert r"\caption{Point estimate across runs.}" in tex
        assert r"\label{fig:growth}" in tex

    def test_addplot_coordinates_pulled_from_evidence(self):
        spec = _line_spec()
        tex = render_native_figure(spec, _series_evidence())
        # y comes from the EVIDENCE point (1, 4, 9), paired with the spec x (1, 2, 3).
        assert r"\addplot" in tex
        assert "(1, 1)" in tex
        assert "(2, 4)" in tex
        assert "(3, 9)" in tex

    def test_y_comes_from_record_not_spec(self):
        """Change the EVIDENCE value -> the rendered coordinate changes (the engine
        pulls y from the record, the spec only supplies x + which id)."""
        spec = _line_spec()
        ev_low = [_ev("ev-a", point=1.0), _ev("ev-b", point=4.0), _ev("ev-c", point=9.0)]
        ev_high = [_ev("ev-a", point=1.0), _ev("ev-b", point=4.0), _ev("ev-c", point=99.0)]

        tex_low = render_native_figure(spec, ev_low)
        tex_high = render_native_figure(spec, ev_high)

        assert "(3, 9)" in tex_low
        assert "(3, 99)" in tex_high
        assert tex_low != tex_high

    def test_xlabel_ylabel_present(self):
        spec = _line_spec()
        tex = render_native_figure(spec, _series_evidence())
        assert "xlabel=" in tex
        assert "ylabel=" in tex
        assert "run index" in tex
        assert "point estimate" in tex

    def test_xlabel_with_specials_is_escaped(self):
        spec = FigureSpec(
            id="esc",
            caption="A 100% pass & cost $5.",
            plot=NativePlot(
                type="line",
                xlabel="cost $ per 100%",
                ylabel="effect_size",
                series=[
                    PlotSeries(
                        y_field="point",
                        points=[PlotPoint(evidence_id="ev-a", x=1.0)],
                    )
                ],
            ),
        )
        tex = render_native_figure(spec, [_ev("ev-a", point=1.0)])
        # Caption + labels are sanitized (LaTeX specials neutralized).
        assert r"100\%" in tex
        assert r"\&" in tex
        assert r"\$5" in tex
        # No raw underscore leaked from "effect_size".
        assert "_" not in tex.replace(r"\_", "")


class TestYFieldSelection:
    def test_point_vs_effect_size(self):
        ev = [
            _ev("ev-a", point=1.0, effect_size=0.5),
            _ev("ev-b", point=2.0, effect_size=0.8),
        ]
        spec_point = FigureSpec(
            id="p",
            caption="c",
            plot=NativePlot(
                type="line",
                series=[PlotSeries(
                    y_field="point",
                    points=[PlotPoint(evidence_id="ev-a", x=0.0),
                            PlotPoint(evidence_id="ev-b", x=1.0)],
                )],
            ),
        )
        spec_eff = FigureSpec(
            id="e",
            caption="c",
            plot=NativePlot(
                type="line",
                series=[PlotSeries(
                    y_field="effect_size",
                    points=[PlotPoint(evidence_id="ev-a", x=0.0),
                            PlotPoint(evidence_id="ev-b", x=1.0)],
                )],
            ),
        )
        tex_point = render_native_figure(spec_point, ev)
        tex_eff = render_native_figure(spec_eff, ev)
        # point series uses 1, 2; effect_size series uses 0.5, 0.8.
        assert "(0, 1)" in tex_point and "(1, 2)" in tex_point
        assert "0.5" in tex_eff and "0.8" in tex_eff
        assert "(0, 1)" not in tex_eff  # did not fall back to point


class TestPlotTypeMapping:
    def test_line_default_addplot(self):
        spec = _line_spec()
        tex = render_native_figure(spec, _series_evidence())
        # line -> a plain \addplot (no only-marks / ybar option block).
        assert r"\addplot" in tex
        assert "only marks" not in tex
        assert "ybar" not in tex

    def test_scatter_only_marks(self):
        spec = _line_spec()
        spec = spec.model_copy(update={"plot": spec.plot.model_copy(update={"type": "scatter"})})
        tex = render_native_figure(spec, _series_evidence())
        assert "only marks" in tex

    def test_bar_ybar(self):
        spec = _line_spec()
        spec = spec.model_copy(update={"plot": spec.plot.model_copy(update={"type": "bar"})})
        tex = render_native_figure(spec, _series_evidence())
        assert "ybar" in tex


# ---------------------------------------------------------------------------
# Record fidelity: never silently invent or drop a point.
# ---------------------------------------------------------------------------

class TestRecordFidelity:
    def test_missing_evidence_id_raises(self):
        spec = FigureSpec(
            id="m",
            caption="c",
            plot=NativePlot(
                type="line",
                series=[PlotSeries(
                    y_field="point",
                    points=[PlotPoint(evidence_id="ev-NOPE", x=1.0)],
                )],
            ),
        )
        with pytest.raises(ValueError):
            render_native_figure(spec, [_ev("ev-a", point=1.0)])

    def test_none_y_field_raises(self):
        # The item exists but its effect_size is None -> must not silently drop.
        spec = FigureSpec(
            id="n",
            caption="c",
            plot=NativePlot(
                type="line",
                series=[PlotSeries(
                    y_field="effect_size",
                    points=[PlotPoint(evidence_id="ev-a", x=1.0)],
                )],
            ),
        )
        with pytest.raises(ValueError):
            render_native_figure(spec, [_ev("ev-a", point=3.0, effect_size=None)])

    def test_nan_y_raises(self):
        # pydantic accepts float('nan') and isinstance(nan, float) is True, so the
        # numeric guard passes -- but '%g' emits the literal 'nan' into the coordinate,
        # which pgfplots refuses to compile (defeating the folder-upload goal). A
        # non-finite y must fail loud, like the None/unknown-id record-fidelity errors.
        spec = _line_spec("nanfig")
        spec = spec.model_copy(update={"plot": spec.plot.model_copy(update={
            "series": [PlotSeries(
                y_field="point", points=[PlotPoint(evidence_id="ev-a", x=1.0)],
            )],
        })})
        with pytest.raises(ValueError):
            render_native_figure(spec, [_ev("ev-a", point=float("nan"))])

    def test_inf_y_raises(self):
        # float('inf') / -inf are the same trap: '%g' emits 'inf'/'-inf', which
        # pgfplots cannot draw -> the figure point is not a plottable coordinate.
        spec = _line_spec("inffig")
        spec = spec.model_copy(update={"plot": spec.plot.model_copy(update={
            "series": [PlotSeries(
                y_field="point", points=[PlotPoint(evidence_id="ev-a", x=1.0)],
            )],
        })})
        with pytest.raises(ValueError):
            render_native_figure(spec, [_ev("ev-a", point=float("inf"))])
        with pytest.raises(ValueError):
            render_native_figure(spec, [_ev("ev-a", point=float("-inf"))])


# ---------------------------------------------------------------------------
# Self-containment: native = text-only, NO image / external-file ref.
# ---------------------------------------------------------------------------

class TestSelfContainment:
    def test_no_includegraphics_or_external_file(self):
        spec = _line_spec()
        tex = render_native_figure(spec, _series_evidence())
        assert r"\includegraphics" not in tex
        assert ".pdf" not in tex
        assert ".png" not in tex


# ---------------------------------------------------------------------------
# Determinism + stable labels.
# ---------------------------------------------------------------------------

class TestDeterminismAndLabels:
    def test_render_is_byte_identical(self):
        spec = _line_spec()
        ev = _series_evidence()
        a = render_native_figure(spec, ev)
        b = render_native_figure(spec, ev)
        assert a == b

    def test_label_is_stable_across_renders(self):
        spec = _line_spec("stable_id")
        ev = _series_evidence()
        assert r"\label{fig:stable_id}" in render_native_figure(spec, ev)
        assert r"\label{fig:stable_id}" in render_native_figure(spec, ev)

    def test_figure_labels_returns_fig_prefixed_ids(self):
        figs = [_line_spec("a"), _line_spec("b")]
        assert figure_labels(figs) == ["fig:a", "fig:b"]

    def test_duplicate_figure_id_raises(self):
        figs = [_line_spec("dup"), _line_spec("dup")]
        with pytest.raises(ValueError):
            figure_labels(figs)


# ---------------------------------------------------------------------------
# FigureSpec id validation: must be a LaTeX-safe label slug.
# ---------------------------------------------------------------------------

class TestFigureSpecValidation:
    def test_empty_id_rejected(self):
        with pytest.raises(ValueError):
            FigureSpec(
                id="",
                caption="c",
                plot=NativePlot(
                    type="line",
                    series=[PlotSeries(points=[PlotPoint(evidence_id="ev-a", x=1.0)])],
                ),
            )

    def test_unsafe_id_rejected(self):
        # A space / brace / backslash would break \label{fig:<id>}.
        for bad in ["has space", "with{brace", "back\\slash", "_leading"]:
            with pytest.raises(ValueError):
                FigureSpec(
                    id=bad,
                    caption="c",
                    plot=NativePlot(
                        type="line",
                        series=[PlotSeries(points=[PlotPoint(evidence_id="ev-a", x=1.0)])],
                    ),
                )

    def test_safe_ids_accepted(self):
        for ok in ["growth", "fig_2", "panel-A", "A1"]:
            FigureSpec(
                id=ok,
                caption="c",
                plot=NativePlot(
                    type="line",
                    series=[PlotSeries(points=[PlotPoint(evidence_id="ev-a", x=1.0)])],
                ),
            )

    def test_series_requires_at_least_one_point(self):
        with pytest.raises(ValueError):
            PlotSeries(points=[])

    def test_plot_requires_at_least_one_series(self):
        with pytest.raises(ValueError):
            NativePlot(type="line", series=[])


# ---------------------------------------------------------------------------
# PaperFigures: the top-level hook (mirrors PaperProse).
# ---------------------------------------------------------------------------

class TestPaperFiguresHook:
    def test_empty_default(self):
        pf = PaperFigures()
        assert pf.figures == []

    def test_holds_specs(self):
        pf = PaperFigures(figures=[_line_spec("a")])
        assert len(pf.figures) == 1
        assert pf.figures[0].id == "a"

    def test_roundtrips_json(self):
        pf = PaperFigures(figures=[_line_spec("rt")])
        rt = PaperFigures.model_validate_json(pf.model_dump_json())
        assert rt.figures[0].id == "rt"
        assert rt.figures[0].plot.series[0].points[0].evidence_id == "ev-a"


# ---------------------------------------------------------------------------
# check_figure_consistency: dangling \ref + orphan figure (a report, not a gate).
# ---------------------------------------------------------------------------

class TestFigureConsistency:
    def test_known_ref_is_ok(self):
        body = r"As shown in Fig.~\ref{fig:known}, the trend holds."
        report = check_figure_consistency(["fig:known"], body)
        assert isinstance(report, FigureConsistencyReport)
        assert report.ok is True
        assert report.dangling == []
        assert report.orphan == []

    def test_dangling_ref(self):
        body = r"See \ref{fig:missing}."
        report = check_figure_consistency(["fig:known"], body)
        assert report.ok is False
        assert "fig:missing" in report.dangling
        # fig:known is defined but never referenced -> also an orphan.
        assert "fig:known" in report.orphan

    def test_orphan_figure(self):
        body = r"No references at all here."
        report = check_figure_consistency(["fig:lonely"], body)
        assert report.ok is False
        assert "fig:lonely" in report.orphan
        assert report.dangling == []

    def test_ignores_non_fig_refs(self):
        # A \ref to a non-figure label (e.g. a section) is not a figure dangling ref.
        body = r"Section~\ref{sec:intro} and Fig.~\ref{fig:known}."
        report = check_figure_consistency(["fig:known"], body)
        assert report.ok is True
        assert report.dangling == []

    def test_is_pure(self):
        body = r"\ref{fig:a}"
        a = check_figure_consistency(["fig:a"], body)
        b = check_figure_consistency(["fig:a"], body)
        assert a == b


# ---------------------------------------------------------------------------
# IMAGE figures (Phase 4-1): \includegraphics of a co-located source image.
# ---------------------------------------------------------------------------

def _image_spec(
    fig_id: str = "scheme", image: str = "diagram.pdf", width: str = ""
) -> ImageFigureSpec:
    return ImageFigureSpec(
        kind="image",
        id=fig_id,
        caption="Reaction scheme (diagram).",
        image=image,
        width=width,
    )


class TestNativeKindBackwardCompat:
    """An existing native spec WITHOUT a `kind` key still parses as native and renders
    byte-identical (the pre-image regression invariant -- the default discriminator)."""

    def test_native_spec_without_kind_parses_as_native(self):
        # The _figures_json-style payload (no "kind" key) the agent authored before the
        # image kind existed must still validate as a native FigureSpec.
        payload = {
            "id": "growth",
            "caption": "Point estimate across runs.",
            "plot": {
                "type": "line",
                "xlabel": "run index",
                "ylabel": "point estimate",
                "series": [{
                    "y_field": "point",
                    "points": [{"evidence_id": "ev-a", "x": 1.0}],
                }],
            },
        }
        spec = FigureSpec.model_validate(payload)
        assert spec.kind == "native"

    def test_native_render_byte_identical_with_default_kind(self):
        # A spec built without passing kind (defaulting to "native") renders byte-for-byte
        # the same tex as today -- the native path is unchanged by the discriminator. The
        # dispatcher's `number` is ignored for native (native = inline text, no file).
        spec = _line_spec("growth")
        assert spec.kind == "native"
        a = render_native_figure(spec, _series_evidence())
        b = render_figure(spec, _series_evidence(), 1)
        assert a == b  # dispatcher routes native -> render_native_figure verbatim


class TestRenderImageFigure:
    def test_emits_includegraphics_caption_label(self):
        # The included path is the GENERIC figure NUMBER fig<N> (here 1), ext from the
        # source; the \label keeps the SEMANTIC id so the body's \ref{fig:<id>} resolves.
        tex = render_image_figure(_image_spec("scheme", "art/diagram.pdf"), 1)
        assert r"\begin{figure}" in tex
        assert r"\centering" in tex
        assert r"\includegraphics[width=\linewidth]{figures/fig1.pdf}" in tex
        assert r"\caption{Reaction scheme (diagram).}" in tex
        assert r"\label{fig:scheme}" in tex
        assert r"\end{figure}" in tex

    def test_filename_is_the_assigned_number_not_the_id(self):
        # The co-located filename is fig<N> (the body-reference number), NEVER the id.
        tex = render_image_figure(_image_spec("scheme", "art/diagram.pdf"), 3)
        assert "{figures/fig3.pdf}" in tex
        assert "{figures/scheme.pdf}" not in tex  # the id is NOT the filename

    def test_extension_derived_from_source_suffix(self):
        tex = render_image_figure(_image_spec("panel", "/abs/path/photo.png"), 2)
        # The file extension follows the SOURCE suffix (.png); the stem is fig<N>.
        assert "{figures/fig2.png}" in tex

    def test_explicit_width_is_used(self):
        tex = render_image_figure(
            _image_spec("w", "d.pdf", width=r"0.8\textwidth"), 1
        )
        assert r"\includegraphics[width=0.8\textwidth]{figures/fig1.pdf}" in tex

    def test_empty_width_defaults_to_linewidth(self):
        tex = render_image_figure(_image_spec("d", "d.pdf", width=""), 1)
        assert r"width=\linewidth" in tex

    def test_caption_is_sanitized(self):
        spec = ImageFigureSpec(
            kind="image", id="esc", caption="100% & cost $5", image="d.pdf"
        )
        tex = render_image_figure(spec, 1)
        assert r"100\%" in tex
        assert r"\&" in tex
        assert r"\$5" in tex

    def test_extensionless_image_raises(self):
        # \includegraphics needs a resolvable file ending; an extensionless source is an
        # authoring error (fail-loud, like the native record-fidelity errors).
        with pytest.raises(ValueError):
            render_image_figure(_image_spec("noext", image="diagram"), 1)

    def test_image_render_is_pure(self):
        spec = _image_spec("p", "d.pdf")
        assert render_image_figure(spec, 1) == render_image_figure(spec, 1)

    def test_unsafe_id_rejected(self):
        # The same LaTeX-safe slug rule as FigureSpec.
        for bad in ["has space", "with{brace", "_leading"]:
            with pytest.raises(ValueError):
                ImageFigureSpec(kind="image", id=bad, caption="c", image="d.pdf")


class TestImageFigureFilename:
    def test_filename_is_fig_number_with_source_ext(self):
        # The single name-builder the renderer + compiler share: fig<N><ext>.
        assert image_figure_filename(_image_spec("a", "art/x.png"), 1) == "fig1.png"
        assert image_figure_filename(_image_spec("b", "/abs/y.pdf"), 7) == "fig7.pdf"

    def test_filename_matches_renderer_includegraphics(self):
        # The compiler's co-located filename MUST match the renderer's \includegraphics
        # path for the SAME number (the shared-numbering invariant).
        spec = _image_spec("scheme", "art/diagram.pdf")
        name = image_figure_filename(spec, 2)
        tex = render_image_figure(spec, 2)
        assert f"{{figures/{name[:-4]}.pdf}}" in tex  # figures/fig2.pdf
        assert f"figures/{name}" in tex

    def test_extensionless_raises(self):
        with pytest.raises(ValueError):
            image_figure_filename(_image_spec("noext", image="diagram"), 1)


class TestRenderFigureDispatch:
    def test_dispatches_native(self):
        spec = _line_spec("growth")
        # native ignores `number` (no file); dispatcher == render_native_figure.
        assert render_figure(spec, _series_evidence(), 1) == render_native_figure(
            spec, _series_evidence()
        )

    def test_dispatches_image(self):
        spec = _image_spec("scheme", "d.pdf")
        # The image path ignores evidence; the dispatcher matches render_image_figure for
        # the SAME number.
        assert render_figure(spec, _series_evidence(), 4) == render_image_figure(spec, 4)

    def test_image_dispatch_ignores_evidence(self):
        spec = _image_spec("scheme", "d.pdf")
        a = render_figure(spec, _series_evidence(), 1)
        b = render_figure(spec, [], 1)  # no evidence at all
        assert a == b


class TestFigureLabelsMixedKinds:
    def test_labels_over_native_and_image(self):
        figs = [_line_spec("nat"), _image_spec("img", "d.pdf")]
        assert figure_labels(figs) == ["fig:nat", "fig:img"]

    def test_duplicate_id_across_kinds_fails_loud(self):
        # A native and an image figure sharing an id would emit two \label{fig:dup}.
        figs = [_line_spec("dup"), _image_spec("dup", "d.pdf")]
        with pytest.raises(ValueError):
            figure_labels(figs)


class TestPaperFiguresMixedUnion:
    def test_paper_figures_holds_both_kinds(self):
        pf = PaperFigures(figures=[_line_spec("nat"), _image_spec("img", "d.pdf")])
        assert pf.figures[0].kind == "native"
        assert pf.figures[1].kind == "image"

    def test_paper_figures_discriminates_from_json(self):
        payload = {
            "figures": [
                {
                    "id": "nat",
                    "caption": "c",
                    "plot": {
                        "type": "line",
                        "series": [{
                            "y_field": "point",
                            "points": [{"evidence_id": "ev-a", "x": 1.0}],
                        }],
                    },
                },
                {"kind": "image", "id": "img", "caption": "c", "image": "d.pdf"},
            ]
        }
        pf = PaperFigures.model_validate(payload)
        assert isinstance(pf.figures[0], FigureSpec)
        assert isinstance(pf.figures[1], ImageFigureSpec)


# ---------------------------------------------------------------------------
# order_figures_by_reference (Part B): a main-paper figure's NUMBER is the order it is
# first \ref'd in the body; unreferenced figures appended after; deterministic.
# ---------------------------------------------------------------------------

class TestOrderFiguresByReference:
    def test_number_follows_first_reference_order_not_supply_order(self):
        # Supplied [a, b, c] but the body references c, then a (b never) -> c=1, a=2,
        # then the unreferenced b=3 (appended after the referenced ones).
        figs = [_line_spec("a"), _line_spec("b"), _line_spec("c")]
        body = r"First see \ref{fig:c}, then \ref{fig:a}."
        ordered = order_figures_by_reference(figs, body)
        assert [(n, f.id) for n, f in ordered] == [(1, "c"), (2, "a"), (3, "b")]

    def test_first_reference_wins_for_repeated_refs(self):
        # A figure \ref'd multiple times is numbered by its FIRST appearance only.
        figs = [_line_spec("a"), _line_spec("b")]
        body = r"\ref{fig:b} ... \ref{fig:a} ... \ref{fig:b} again."
        ordered = order_figures_by_reference(figs, body)
        assert [(n, f.id) for n, f in ordered] == [(1, "b"), (2, "a")]

    def test_unreferenced_figures_keep_supply_order_after_referenced(self):
        # None referenced -> all kept in supply order, numbered 1..N.
        figs = [_line_spec("a"), _line_spec("b"), _line_spec("c")]
        ordered = order_figures_by_reference(figs, "no refs here")
        assert [(n, f.id) for n, f in ordered] == [(1, "a"), (2, "b"), (3, "c")]

    def test_mixed_referenced_then_unreferenced(self):
        # b referenced (=1); a and c unreferenced -> appended in supply order (a=2, c=3).
        figs = [_line_spec("a"), _line_spec("b"), _line_spec("c")]
        ordered = order_figures_by_reference(figs, r"only \ref{fig:b}")
        assert [(n, f.id) for n, f in ordered] == [(1, "b"), (2, "a"), (3, "c")]

    def test_dangling_ref_ignored_does_not_number_a_missing_figure(self):
        # A \ref to a figure that does not exist contributes no number (it is reported by
        # check_figure_consistency, not numbered here).
        figs = [_line_spec("a")]
        ordered = order_figures_by_reference(figs, r"\ref{fig:ghost} \ref{fig:a}")
        assert [(n, f.id) for n, f in ordered] == [(1, "a")]

    def test_numbers_are_contiguous_and_one_based(self):
        figs = [_line_spec("a"), _image_spec("b", "d.pdf"), _line_spec("c")]
        ordered = order_figures_by_reference(figs, r"\ref{fig:c}")
        assert [n for n, _ in ordered] == [1, 2, 3]

    def test_is_deterministic(self):
        figs = [_line_spec("a"), _line_spec("b"), _line_spec("c")]
        body = r"\ref{fig:b} \ref{fig:a}"
        a = order_figures_by_reference(figs, body)
        b = order_figures_by_reference(figs, body)
        assert [(n, f.id) for n, f in a] == [(n, f.id) for n, f in b]

    def test_empty_figures_is_empty(self):
        assert order_figures_by_reference([], r"\ref{fig:x}") == []

    def test_duplicate_id_fails_loud(self):
        figs = [_line_spec("dup"), _image_spec("dup", "d.pdf")]
        with pytest.raises(ValueError):
            order_figures_by_reference(figs, r"\ref{fig:dup}")


def test_native_figure_axis_uses_sans_font_policy():
    # F2 (design/paper-publishing-requirements.md): figure TEXT (axis labels, ticks,
    # legend) is set in the Arial-compatible sans via ``font=\sffamily``; inline math in a
    # label stays in the Times-compatible serif (newtxmath, emitted in the preamble).
    tex = render_native_figure(_line_spec("growth"), _series_evidence())
    assert r"font=\sffamily" in tex
