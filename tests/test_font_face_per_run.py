"""
The text face is decided ONCE per run, from the figures of the draft AND of the SI.

``draft.tex`` took Times only when the draft itself carried a figure, while the authored
``si.tex`` took Times when the SI carried one or the draft did. A run whose only figure sat
in the SI therefore submitted a Latin Modern draft beside a Times SI -- two body faces in
one submission. Both documents now share the same ``text_font_lines``, in both directions,
and ``numbers draft`` (``render_texts``) reads exactly what render writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.render.figures import FigureSpec, NativePlot, PlotPoint, PlotSeries
from sci_adk.render.paper import (
    T1_FONT_LINES,
    TIMES_FONT_LINES,
    render_paper_latex,
    run_font_policy,
)
from sci_adk.render.prose import AuthoredSI, SISection
from tests.test_preamble_t1 import _assert_fonts_in_place
from tests.test_si import _basic_record
from tests.test_verify import _numeric_experiment, _numeric_spec, _seed


def _native(fig_id: str) -> FigureSpec:
    return FigureSpec(
        id=fig_id,
        caption="The recorded point.",
        plot=NativePlot(
            type="scatter", series=[PlotSeries(points=[PlotPoint(evidence_id="ev-num", x=1.0)])]
        ),
    )


def _si(figures: list) -> AuthoredSI:
    return AuthoredSI(title="S", sections=[SISection(title="Notes", body="Plain notes.")],
                      figures=figures)


def test_the_run_policy_is_the_union_of_draft_and_si_figures():
    assert run_font_policy([], []) is False
    assert run_font_policy([_native("fig-a")], []) is True
    assert run_font_policy([], [_native("fig-s")]) is True


def test_render_paper_latex_takes_the_run_policy_when_given():
    spec, claims, evidence = _basic_record()
    tex = render_paper_latex(spec, claims, evidence, figures=[], font_policy=True)
    _assert_fonts_in_place(tex, times=True)
    assert r"\usepackage[scaled]{helvet}" in tex
    assert render_paper_latex(spec, claims, evidence, figures=[]) == render_paper_latex(
        spec, claims, evidence, figures=[], font_policy=False
    )


@pytest.mark.parametrize(
    ("draft_figures", "si_figures", "times"),
    [
        ([], [_native("fig-s")], True),      # the SI's figure decides for the draft too
        ([_native("fig-a")], [], True),      # the draft's figure decides for the SI too
        ([], [], False),
    ],
    ids=["si-figure-only", "draft-figure-only", "no-figure"],
)
def test_draft_and_si_share_one_text_face(tmp_path: Path, draft_figures, si_figures, times):
    spec = _numeric_spec("fonts-run", value=0.9)
    _seed(tmp_path, spec, _numeric_experiment(0.95))
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    paper_path, si_path, _record, _consistency = compiler.stage_render(
        spec, si=_si(si_figures), figures=draft_figures
    )
    draft_tex = paper_path.read_text(encoding="utf-8")
    si_tex = si_path.read_text(encoding="utf-8")
    _assert_fonts_in_place(draft_tex, times=times)
    _assert_fonts_in_place(si_tex, times=times)
    lines = TIMES_FONT_LINES if times else T1_FONT_LINES
    for tex in (draft_tex, si_tex):
        assert all(line in tex for line in lines)
    # `numbers draft` reads both documents exactly as render writes them.
    texts = compiler.render_texts(spec, si=_si(si_figures), figures=draft_figures)
    assert texts == (draft_tex, si_tex)
