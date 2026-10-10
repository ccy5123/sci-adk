"""
Every LaTeX preamble sci-adk emits loads the T1 font encoding and Latin Modern.

With ``\\usepackage[utf8]{inputenc}`` alone pdflatex runs in the OT1 encoding, and 22 characters
the LaTeX-safe bibliography keeps (« » ‹ › ‚ „ Ð Þ ð þ Ą ą Đ đ Ę ę Į į Ŋ ŋ Ų ų) stop the compile
there (measured with TeX Live 2026). ``\\usepackage[T1]{fontenc}`` makes them typeset;
``\\usepackage{lmodern}`` gives vector fonts for T1 without depending on cm-super (Latin Modern
is the Computer Modern design, so the body text looks the same).

Order: the two lines come right after inputenc (right after ``\\documentclass`` where a
preamble has no inputenc), before the figure font-policy lines, so ``[scaled]{helvet}`` still
sets the sans and ``newtxmath`` the math: the F2 font-policy gate must still pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sci_adk.render.authored_si import render_authored_si_latex
from sci_adk.render.figures import ImageFigureSpec
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import AuthoredSI, SISection
from sci_adk.render.pubreqs_checks import figure_font_policy_problems
from sci_adk.render.si import render_si_latex
from tests.test_si import _basic_record

T1 = r"\usepackage[T1]{fontenc}"
LMODERN = r"\usepackage{lmodern}"
INPUTENC = r"\usepackage[utf8]{inputenc}"
DOCCLASS_PREFIX = r"\documentclass"


def _figure() -> ImageFigureSpec:
    return ImageFigureSpec(kind="image", id="fig-a", caption="A caption.", image="a.png")


def _preamble_lines(tex: str) -> list[str]:
    head = tex[: tex.index(r"\begin{document}")]
    return [line.strip() for line in head.splitlines() if line.strip()]


def _assert_t1_lmodern_in_place(tex: str) -> None:
    lines = _preamble_lines(tex)
    assert T1 in lines and LMODERN in lines, lines
    i_t1, i_lm = lines.index(T1), lines.index(LMODERN)
    anchor = (
        lines.index(INPUTENC)
        if INPUTENC in lines
        else next(i for i, line in enumerate(lines) if line.startswith(DOCCLASS_PREFIX))
    )
    assert (i_t1, i_lm) == (anchor + 1, anchor + 2), lines
    for font_line in (r"\usepackage{newtxmath}", r"\usepackage[scaled]{helvet}"):
        if font_line in lines:
            assert lines.index(font_line) > i_lm, lines


def _authored_si() -> AuthoredSI:
    return AuthoredSI(title="S", sections=[SISection(title="Notes", body="Plain notes.")])


# -- the per-run documents ------------------------------------------------------------------------


@pytest.mark.parametrize("with_figure", [False, True], ids=["figure-less", "figure-bearing"])
def test_paper_draft_preamble(with_figure):
    spec, claims, evidence = _basic_record()
    tex = render_paper_latex(
        spec, claims, evidence, figures=[_figure()] if with_figure else []
    )
    _assert_t1_lmodern_in_place(tex)
    assert figure_font_policy_problems(tex) == []


@pytest.mark.parametrize("with_figure", [False, True], ids=["figure-less", "figure-bearing"])
def test_record_preamble(with_figure):
    spec, claims, evidence = _basic_record()
    tex = render_si_latex(spec, claims, evidence, figures=[_figure()] if with_figure else None)
    _assert_t1_lmodern_in_place(tex)
    assert figure_font_policy_problems(tex) == []


def test_authored_si_preamble():
    spec, claims, evidence = _basic_record()
    tex = render_authored_si_latex(_authored_si(), spec, claims, evidence)
    _assert_t1_lmodern_in_place(tex)


# -- the package documents ------------------------------------------------------------------------


def test_package_skeleton_si_preamble():
    from sci_adk.render.package import _skeleton_si_tex

    _assert_t1_lmodern_in_place(_skeleton_si_tex())


def test_package_main_record_and_si_preambles(tmp_path: Path):
    from tests.test_si_authoring_m6 import _assemble, _seed_workspace

    ws = _seed_workspace(tmp_path)
    _assemble(ws)
    package = ws / "package"
    for rel in ("01_manuscript/main.tex", "01_manuscript/si.tex", "06_provenance/record.tex"):
        tex = (package / rel).read_text(encoding="utf-8")
        _assert_t1_lmodern_in_place(tex)
        assert figure_font_policy_problems(tex) == [], rel
