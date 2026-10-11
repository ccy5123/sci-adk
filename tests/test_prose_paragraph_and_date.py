"""
Run-in paragraph headings in prose (``\\paragraph{...}``) and a reproducible document date.

S1. The main-text prose sanitizer (:func:`paper._latex_sanitize_prose`) let through only the
ref/cite allowlist, so a writer who gave Methods/Results lead-in labels as
``\\paragraph{Data.}`` got the literal text ``\\textbackslash{}paragraph\\{Data.\\}`` -- the
trial paper fell back to plain sentence fragments ("Data. BCF values were taken ...", "Slope.
341 chemicals ..."). ``\\paragraph{<text>}`` now passes as a real heading in every prose slot,
its braced text sanitized like any other prose (specials escaped, unicode folded), so it
cannot carry other LaTeX. The authored SI body is verbatim LaTeX and already carried
``\\paragraph`` (the trial SI uses it); both documents now render the same lead-in the same
way.

The checks that read the rendered documents still see the heading text: the tool-vocabulary
scan (a substring scan) and the declared-number tokenizer (section titles and captions are
literals there). The legacy pattern audit, used only by runs without a ``numbers.json``,
ignores ``\\paragraph`` arguments like ``\\section`` titles (OD-3) -- pinned below as its known
residual, unchanged because that module is kept byte-stable.

S4. Every render wrote ``\\date{\\today}``, so two compiles of the same source printed two
different dates. ``draft.tex``, the authored ``si.tex`` and the deposit's ``record.tex`` now
write ``\\date{}`` (no date line), as the package skeleton already did.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from sci_adk.render.authored_si import render_authored_si_latex
from sci_adk.render.number_audit import tokenize_quantitative
from sci_adk.render.number_checks import _context_spans
from sci_adk.render.number_literals import find_literals
from sci_adk.render.paper import (
    _latex_sanitize,
    _latex_sanitize_prose,
    check_paper_tool_vocabulary,
    render_paper_latex,
)
from sci_adk.render.prose import AuthoredSI, PaperProse, SIProse, SISection
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import _log_errors, _render_preamble, _run, needs_tex
from tests.test_si import _basic_record

# -- S1: the sanitizer unit --------------------------------------------------------------


def test_a_paragraph_heading_passes_through_prose_as_real_latex():
    out = _latex_sanitize_prose(r"\paragraph{Data.} BCF values were taken from the database.")
    assert out == r"\paragraph{Data.} BCF values were taken from the database."


def test_the_heading_text_is_sanitized_like_any_other_prose():
    # Specials inside the braces are escaped exactly as they would be outside them.
    assert _latex_sanitize_prose(r"\paragraph{Share 95% & a_b.} x") == (
        r"\paragraph{Share 95\% \& a\_b.} x"
    )
    # The unicode safety net applies inside the heading too.
    assert _latex_sanitize_prose("\\paragraph{\u03b1 test.} x") == r"\paragraph{$\alpha$ test.} x"


def test_a_heading_with_nested_braces_carries_no_latex_and_is_escaped_whole():
    # \paragraph admits brace-free text only: a command inside it would be LaTeX the prose
    # contract does not allow, so the whole construct stays literal text.
    s = r"\paragraph{A \textbf{bold} label.} x"
    assert _latex_sanitize_prose(s) == _latex_sanitize(s)
    assert r"\paragraph{" not in _latex_sanitize_prose(s)


@pytest.mark.parametrize(
    "command",
    [r"\paragraph*{X.} y", r"\subparagraph{X.} y", r"\paragraphs{X.} y", r"\section{X} y"],
    ids=["starred", "subparagraph", "longer-name", "section"],
)
def test_only_the_plain_paragraph_command_is_added(command):
    assert _latex_sanitize_prose(command) == _latex_sanitize(command)


def test_paragraph_headings_and_references_pass_together():
    s = r"\paragraph{Slope.} See Figure \ref{fig:h1} and \citet{Veith1979}; 50% kept."
    assert _latex_sanitize_prose(s) == (
        r"\paragraph{Slope.} See Figure \ref{fig:h1} and \citet{Veith1979}; 50\% kept."
    )


# -- S1: the rendered documents ----------------------------------------------------------

_METHODS = r"\paragraph{Data.} Values were taken from one database." "\n\n" + (
    r"\paragraph{Structures and filters.} Each record was resolved to a structure."
)
_RESULTS = r"\paragraph{Slope.} The effect was \evval{ev-1}{effect_size}."


def _draft(**slots: str) -> str:
    spec, claims, evidence = _basic_record()
    return render_paper_latex(spec, claims, evidence, prose=PaperProse(**slots))


def test_methods_and_results_lead_ins_render_as_paragraph_headings():
    tex = _draft(methods=_METHODS, results=_RESULTS)
    assert r"\paragraph{Data.} Values were taken from one database." in tex
    assert r"\paragraph{Structures and filters.} Each record" in tex
    assert r"\paragraph{Slope.} The effect was 1.5." in tex
    assert "textbackslash{}paragraph" not in tex


def test_a_record_value_inside_the_heading_is_substituted_before_sanitizing():
    tex = _draft(results=r"\paragraph{Effect \evval{ev-1}{effect_size}.} Text.")
    assert r"\paragraph{Effect 1.5.} Text." in tex


def test_the_vocabulary_check_reads_the_heading_text():
    tex = _draft(results=r"\paragraph{Verdict.} The slope lay inside the range.")
    assert r"\paragraph{Verdict.}" in tex
    assert "verdict" in check_paper_tool_vocabulary(tex)


def test_the_declared_number_tokenizer_reads_a_number_in_the_heading():
    tex = _draft(results=r"\paragraph{Experiment 7.} The slope lay inside the range.")
    assert any(lit.value == 7.0 for lit in find_literals(tex, "draft.tex"))


def test_a_declared_context_quoted_from_the_prose_json_finds_the_rendered_heading():
    # numbers.json contexts may be quoted from the prose JSON; they are tried as render
    # writes prose, which now keeps the heading command.
    tex = _draft(results=r"\paragraph{Share 95%.} of the records were kept.")
    assert _context_spans(r"\paragraph{Share 95%.} of the records", tex)


def test_the_legacy_pattern_audit_ignores_heading_text_like_a_section_title():
    # KNOWN RESIDUAL (OD-3, byte-stable module): runs without numbers.json audit with the
    # pattern audit, which strips \paragraph{...} as it strips \section{...}. A number in a
    # lead-in label is seen only by the declared-number checks.
    assert tokenize_quantitative(r"\paragraph{Experiment 7.} text") == []
    assert tokenize_quantitative(r"\section{Experiment 7} text") == []


def test_the_draft_and_the_authored_si_render_the_same_lead_in_identically():
    spec, claims, evidence = _basic_record()
    body = r"\paragraph{Analysis steps.} The records were filtered in order."
    draft = render_paper_latex(spec, claims, evidence, prose=PaperProse(methods=body))
    si = render_authored_si_latex(
        AuthoredSI(title="S", sections=[SISection(title="Protocol", body=body)]),
        spec,
        claims,
        evidence,
    )
    assert body in draft
    assert body in si


def test_the_record_prose_slots_take_the_same_heading():
    spec, claims, evidence = _basic_record()
    tex = render_si_latex(
        spec, claims, evidence, prose=SIProse(overview=r"\paragraph{Scope.} One run.")
    )
    assert r"\paragraph{Scope.} One run." in tex


# -- S1: it compiles ---------------------------------------------------------------------


def _compile(tmp_path: Path, tex: str, name: str) -> list[str]:
    """pdflatex ``tex`` with a preamble this TeX install loads (the render's own, minus any
    package it cannot load); returns the log errors (empty = compiled cleanly)."""
    preamble, _dropped = _render_preamble(figure_bearing=False)
    body = tex[tex.index(r"\begin{document}"):]
    (tmp_path / f"{name}.tex").write_text("\n".join(preamble) + "\n" + body, encoding="utf-8")
    status = _run(["pdflatex", "-interaction=nonstopmode", f"{name}.tex"], tmp_path)
    errors = _log_errors((tmp_path / f"{name}.log").read_text(encoding="utf-8", errors="replace"))
    if status != 0:
        errors.append(f"pdflatex exited {status}")
    return errors


@needs_tex
def test_a_draft_with_paragraph_headings_compiles_and_prints_them_run_in(tmp_path):
    tex = _draft(methods=_METHODS, results=_RESULTS)
    assert _compile(tmp_path, tex, "draft") == []
    if shutil.which("pdftotext"):
        text = subprocess.run(
            ["pdftotext", "draft.pdf", "-"], cwd=tmp_path, capture_output=True, text=True,
            check=True,
        ).stdout
        # The label is typeset as a heading before its paragraph (pdftotext puts the bold
        # run-in label on its own line), and no escaped command reaches the page.
        flat = " ".join(text.split())
        assert "Data. Values were taken" in flat
        assert "Slope. The effect was 1.5." in flat
        assert "paragraph" not in text


@needs_tex
def test_an_authored_si_with_paragraph_headings_compiles(tmp_path):
    spec, claims, evidence = _basic_record()
    si = render_authored_si_latex(
        AuthoredSI(title="S", sections=[SISection(title="Protocol", body=_METHODS)]),
        spec,
        claims,
        evidence,
    )
    assert _compile(tmp_path, si, "si") == []


# -- S4: no date ---------------------------------------------------------------------------


def _three_documents() -> dict[str, str]:
    spec, claims, evidence = _basic_record()
    return {
        "draft.tex": render_paper_latex(spec, claims, evidence, prose=PaperProse(methods="M.")),
        "si.tex": render_authored_si_latex(
            AuthoredSI(title="S", sections=[SISection(title="N", body="Notes.")]),
            spec,
            claims,
            evidence,
        ),
        "record.tex": render_si_latex(spec, claims, evidence),
    }


@pytest.mark.parametrize("name", ["draft.tex", "si.tex", "record.tex"])
def test_every_rendered_document_carries_no_date(name):
    tex = _three_documents()[name]
    assert r"\today" not in tex
    head = tex[: tex.index(r"\begin{document}")]
    assert head.count(r"\date{") == 1
    assert r"\date{}" in head.splitlines()


@needs_tex
def test_the_compiled_draft_does_not_print_the_compile_date(tmp_path):
    # \today printed the date of each compile ("October 11, 2026"), so the same source gave a
    # different first page every day; with \date{} the page depends on the source only.
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext (poppler) not on PATH")
    assert _compile(tmp_path, _three_documents()["draft.tex"], "draft") == []
    text = subprocess.run(
        ["pdftotext", "draft.pdf", "-"], cwd=tmp_path, capture_output=True, text=True,
        check=True,
    ).stdout
    today = date.today()
    assert f"{today:%B} {today.day}, {today.year}" not in text
    assert str(today.year) not in text
