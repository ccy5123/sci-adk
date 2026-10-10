"""
Every LaTeX preamble sci-adk emits loads the T1 font encoding and ONE text typeface, and loads
hyperref (where it loads it at all) with ``[hidelinks]``.

With ``\\usepackage[utf8]{inputenc}`` alone pdflatex runs in the OT1 encoding, and 22 characters
the LaTeX-safe bibliography keeps (« » ‹ › ‚ „ Ð Þ ð þ Ą ą Đ đ Ę ę Į į Ŋ ŋ Ų ų) stop the compile
there (measured with TeX Live 2026). ``\\usepackage[T1]{fontenc}`` makes them typeset.

The text typeface follows the figure font policy (design/paper-publishing-requirements.md F2):

- a document the policy applies to (a figure-bearing paper or SI, the package ``main.tex``
  skeleton) sets math in Times (``newtxmath``), so its text is Times too: ``newtxtext`` takes
  the place ``lmodern`` had, and the body and the equations are one typeface (the trial paper
  set Latin Modern text beside Times math);
- an authored SI submitted beside such a draft, and the package SI skeleton beside the package
  ``main.tex`` skeleton, take the same faces even without a figure, so a submission does not
  pair two body faces;
- every other document keeps ``lmodern`` (vector T1 fonts without cm-super; the Computer
  Modern design).

Order: the two lines come right after inputenc (right after ``\\documentclass`` where a
preamble has no inputenc), before the math and sans lines (``amsmath``, ``newtxmath``,
``[scaled]{helvet}``), so the F2 font-policy gate passes.

``[hidelinks]``: without it hyperref draws a coloured box around every citation and reference
(the trial paper's reference list and body had one on each).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sci_adk.render.authored_si import render_authored_si_latex
from sci_adk.render.figures import ImageFigureSpec
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import AuthoredSI, SISection
from sci_adk.render.pubreqs_checks import figure_font_policy_problems
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import _loadable, _render_preamble, _run, needs_tex
from tests.test_si import _basic_record

T1 = r"\usepackage[T1]{fontenc}"
LMODERN = r"\usepackage{lmodern}"
NEWTXTEXT = r"\usepackage{newtxtext}"
NEWTXMATH = r"\usepackage{newtxmath}"
HELVET = r"\usepackage[scaled]{helvet}"
HYPERREF = r"\usepackage[hidelinks]{hyperref}"
INPUTENC = r"\usepackage[utf8]{inputenc}"
DOCCLASS_PREFIX = r"\documentclass"


def _figure() -> ImageFigureSpec:
    return ImageFigureSpec(kind="image", id="fig-a", caption="A caption.", image="a.png")


def _preamble_lines(tex: str) -> list[str]:
    head = tex[: tex.index(r"\begin{document}")]
    return [line.strip() for line in head.splitlines() if line.strip()]


def _assert_fonts_in_place(tex: str, *, times: bool) -> None:
    """T1 then the text typeface right after inputenc: ``newtxtext`` where the font policy
    applies (``times``), else ``lmodern``; never both; math and sans lines after them."""
    lines = _preamble_lines(tex)
    text_font, other = (NEWTXTEXT, LMODERN) if times else (LMODERN, NEWTXTEXT)
    assert T1 in lines and text_font in lines, lines
    assert other not in lines, lines
    i_t1, i_text = lines.index(T1), lines.index(text_font)
    anchor = (
        lines.index(INPUTENC)
        if INPUTENC in lines
        else next(i for i, line in enumerate(lines) if line.startswith(DOCCLASS_PREFIX))
    )
    assert (i_t1, i_text) == (anchor + 1, anchor + 2), lines
    for later in (r"\usepackage{amsmath}", NEWTXMATH, HELVET):
        if later in lines:
            assert lines.index(later) > i_text, lines
    assert (NEWTXMATH in lines) == times, lines


def _assert_hyperref_hides_links(tex: str, *, loaded: bool = True) -> None:
    lines = _preamble_lines(tex)
    hyperref = [line for line in lines if "{hyperref}" in line]
    assert hyperref == ([HYPERREF] if loaded else []), hyperref


def _authored_si(*, with_figure: bool = False) -> AuthoredSI:
    return AuthoredSI(
        title="S",
        sections=[SISection(title="Notes", body="Plain notes.")],
        figures=[_figure()] if with_figure else [],
    )


# -- the per-run documents ------------------------------------------------------------------------


@pytest.mark.parametrize("with_figure", [False, True], ids=["figure-less", "figure-bearing"])
def test_paper_draft_preamble(with_figure):
    spec, claims, evidence = _basic_record()
    tex = render_paper_latex(
        spec, claims, evidence, figures=[_figure()] if with_figure else []
    )
    _assert_fonts_in_place(tex, times=with_figure)
    _assert_hyperref_hides_links(tex)
    assert figure_font_policy_problems(tex) == []


@pytest.mark.parametrize("with_figure", [False, True], ids=["figure-less", "figure-bearing"])
def test_record_preamble(with_figure):
    spec, claims, evidence = _basic_record()
    tex = render_si_latex(spec, claims, evidence, figures=[_figure()] if with_figure else None)
    _assert_fonts_in_place(tex, times=with_figure)
    _assert_hyperref_hides_links(tex)
    assert figure_font_policy_problems(tex) == []


@pytest.mark.parametrize("with_figure", [False, True], ids=["figure-less", "figure-bearing"])
def test_authored_si_preamble(with_figure):
    spec, claims, evidence = _basic_record()
    tex = render_authored_si_latex(_authored_si(with_figure=with_figure), spec, claims, evidence)
    _assert_fonts_in_place(tex, times=with_figure)
    _assert_hyperref_hides_links(tex)
    assert figure_font_policy_problems(tex) == []


# The authored SI is submitted beside draft.tex. A figure-bearing draft is set in Times (text
# and math, Helvetica sans); an SI without a figure of its own was set in Latin Modern, so the
# submission paired two body faces. The SI now takes the draft's faces.


def test_a_figure_less_authored_si_takes_the_faces_of_a_figure_bearing_draft():
    spec, claims, evidence = _basic_record()
    tex = render_authored_si_latex(
        _authored_si(), spec, claims, evidence, draft_font_policy=True
    )
    _assert_fonts_in_place(tex, times=True)
    assert HELVET in _preamble_lines(tex)
    assert figure_font_policy_problems(tex) == []
    # Still a figure-less document: no figure package.
    assert "pgfplots" not in tex and "graphicx" not in tex


def test_render_gives_the_si_the_faces_render_gives_the_draft(tmp_path: Path):
    from sci_adk.loop.compiler import ResearchCompiler
    from sci_adk.render.figures import FigureSpec, NativePlot, PlotPoint, PlotSeries
    from tests.test_verify import _numeric_experiment, _numeric_spec, _seed

    spec = _numeric_spec("fonts-si", value=0.9)
    _seed(tmp_path, spec, _numeric_experiment(0.95))
    native = FigureSpec(
        id="fig-n",
        caption="The recorded point.",
        plot=NativePlot(
            type="scatter", series=[PlotSeries(points=[PlotPoint(evidence_id="ev-num", x=1.0)])]
        ),
    )
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    for figures, times in (([native], True), ([], False)):
        paper_path, si_path, _record, _consistency = compiler.stage_render(
            spec, si=_authored_si(), figures=figures
        )
        _assert_fonts_in_place(paper_path.read_text(encoding="utf-8"), times=times)
        _assert_fonts_in_place(si_path.read_text(encoding="utf-8"), times=times)
        # `numbers draft` reads the SI exactly as render writes it.
        _draft_tex, si_tex = compiler.render_texts(spec, si=_authored_si(), figures=figures)
        assert si_tex == si_path.read_text(encoding="utf-8")


# -- the package documents ------------------------------------------------------------------------


def test_package_skeleton_si_preamble():
    # The package main.tex skeleton is set in Times (the figure font policy applies to it), so
    # the SI skeleton beside it is too: one body face across the submission.
    from sci_adk.render.package import _skeleton_si_tex

    tex = _skeleton_si_tex()
    _assert_fonts_in_place(tex, times=True)
    assert HELVET in _preamble_lines(tex)
    _assert_hyperref_hides_links(tex, loaded=False)


def test_package_main_record_and_si_preambles(tmp_path: Path):
    from tests.test_si_authoring_m6 import _assemble, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _assemble(ws)
    package = ws / "package"
    # (file, the figure font policy applies, hyperref loaded)
    for rel, times, hyperref in (
        ("01_manuscript/main.tex", True, False),
        ("01_manuscript/si.tex", True, False),
        ("06_provenance/record.tex", False, True),
    ):
        tex = (package / rel).read_text(encoding="utf-8")
        _assert_fonts_in_place(tex, times=times)
        _assert_hyperref_hides_links(tex, loaded=hyperref)
        assert figure_font_policy_problems(tex) == [], rel


@needs_tex
@pytest.mark.skipif(not shutil.which("pdffonts"), reason="pdffonts (poppler) not on PATH")
@pytest.mark.parametrize(
    "figure_bearing, body_face",
    [(False, "LMRoman10-Regular"), (True, "TeXGyreTermesX-Regular")],
    ids=["latin-modern", "times"],
)
def test_the_rendered_preamble_embeds_vector_fonts_of_one_text_face(
    tmp_path: Path, figure_bearing, body_face
):
    # The preamble a render emits, compiled with body text, a URL (typewriter) and math: every
    # font is embedded Type 1 (no Type 3 bitmap), and the body is set in the preamble's face.
    preamble, dropped = _render_preamble(figure_bearing)
    body = [
        r"\begin{document}",
        r"Body text, \url{https://doi.org/10.1021/ci050024v}, and $x^2 + \alpha \leq K$.",
        r"\end{document}",
    ]
    (tmp_path / "t.tex").write_text("\n".join(preamble + body) + "\n", encoding="utf-8")
    assert _run(["pdflatex", "-interaction=nonstopmode", "t.tex"], tmp_path) == 0, dropped
    fonts = subprocess.run(
        ["pdffonts", "t.pdf"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.splitlines()[2:]
    assert fonts, "no fonts listed"
    assert not [f for f in fonts if "Type 3" in f], fonts
    assert all(" yes " in f for f in fonts), fonts  # embedded
    assert any(body_face in f for f in fonts), fonts
    other_face = "TeXGyreTermesX" if body_face.startswith("LM") else "LMRoman"
    assert not any(other_face in f for f in fonts), fonts


@needs_tex
@pytest.mark.skipif(not shutil.which("pdffonts"), reason="pdffonts (poppler) not on PATH")
def test_a_native_pgfplots_figure_under_the_times_preamble_embeds_vector_fonts(tmp_path: Path):
    # A draft carrying a native (pgfplots) figure, compiled as render writes it: every font is
    # embedded Type 1, the body is Times (TeX Gyre Termes X) with no Latin Modern beside it, and
    # the axis labels (font=\sffamily) are in the Helvetica clone (Nimbus Sans: NimbusSanL-Regu
    # in TeX Live 2026, NimbusSans-Regular in other releases).
    # UNVERIFIED where it was written: that TeX Live has no pgfplots, so this skips there. The
    # face names were measured there with the same preamble and \sffamily text, without pgfplots.
    if not _loadable("pgfplots"):
        pytest.skip("this TeX install has no pgfplots")
    from sci_adk.render.figures import FigureSpec, NativePlot, PlotPoint, PlotSeries

    spec, claims, evidence = _basic_record()
    native = FigureSpec(
        id="fig-n",
        caption="Recorded points.",
        plot=NativePlot(
            type="scatter",
            xlabel="Dose",
            ylabel="Response",
            series=[PlotSeries(points=[PlotPoint(evidence_id="ev-1", x=1.0),
                                       PlotPoint(evidence_id="ev-2", x=2.0)])],
        ),
    )
    tex = render_paper_latex(spec, claims, evidence, figures=[native])
    assert r"\usepackage{pgfplots}" in tex and r"\begin{axis}[font=\sffamily" in tex
    (tmp_path / "draft.tex").write_text(tex, encoding="utf-8")
    assert _run(["pdflatex", "-interaction=nonstopmode", "draft.tex"], tmp_path) == 0
    fonts = subprocess.run(
        ["pdffonts", "draft.pdf"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.splitlines()[2:]
    assert fonts, "no fonts listed"
    assert not [f for f in fonts if "Type 3" in f], fonts
    assert all(" yes " in f for f in fonts), fonts  # embedded
    assert any("TeXGyreTermesX" in f for f in fonts), fonts
    assert any("NimbusSan" in f for f in fonts), fonts
    assert not any("LMRoman" in f for f in fonts), fonts


def test_the_package_main_skeleton_passes_the_font_gate_when_it_carries_a_figure(tmp_path: Path):
    # The skeleton has no figure, so the gate is vacuous on it as written; a writer who adds one
    # keeps the skeleton's preamble, which must then satisfy the policy.
    from tests.test_si_authoring_m6 import _assemble, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _assemble(ws)
    tex = (ws / "package" / "01_manuscript" / "main.tex").read_text(encoding="utf-8")
    with_figure = tex.replace(
        r"\end{document}", r"\includegraphics{figures/fig1.pdf}" "\n" r"\end{document}"
    )
    assert figure_font_policy_problems(with_figure) == []
