"""
render-merge (RED-first): the compiler/CLI wiring.

The compiler must emit ``runs/<id>/paper/draft.tex`` as THE paper artifact (via
``render_paper_latex``; ``draft.md`` is no longer auto-emitted), gather ``cited_dois``
from the run's LITERATURE EvidenceItem and/or its
``artifacts/literature/manifest.csv``, and -- when ``artifacts/literature/references.bib``
exists -- copy it into ``paper/`` and wire ``\bibliography{references}`` so the folder
uploads to Overleaf as-is. The CLI gains an optional ``--prose <json>`` that injects an
agent-authored ``PaperProse`` into the LaTeX renderer.

Network-free: a fake experiment hook stands in for the Docker run; literature DOIs
come from a recorded LITERATURE EvidenceItem (no acquisition runs here).
"""

from __future__ import annotations

import json

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.loop.compiler import ResearchCompiler

PROPOSAL = """# Background
Molecular graphs represent chemical structures as vertices and edges.

# Goal
A Goedel-style encoding of molecular graphs exists.

# Expected Output
A unique integer per molecule and a decoding algorithm.

# Method
Prime-factor encoding; test injectivity in a Docker sandbox.
"""


def _fake_experiment(spec, workspace_dir):
    items = []
    for i, h in enumerate(spec.hypotheses):
        items.append(
            EvidenceItem(
                id=f"ev-fake-{i}",
                spec_id=spec.id,
                kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fake:test", data_source="generated"),
                result=Result(type="qualitative", finding=f"finding for {h.id}"),
                bears_on=[Bearing(target_id=h.id, direction=BearingDirection.NEUTRAL)],
            )
        )
    return items


def _literature_experiment(spec, workspace_dir):
    """A fake experiment that also emits a LITERATURE EvidenceItem carrying DOIs
    in the same JSON-finding shape LiteratureAcquirer produces."""
    base = _fake_experiment(spec, workspace_dir)
    summary = {
        "acquired": [
            {"doi": "10.48550/arXiv.1301.1493", "source": "arxiv",
             "license": None, "filename": "McKay2013.pdf"},
            {"doi": "10.1186/s13321-020-00453-4", "source": "unpaywall",
             "license": "cc-by", "filename": "Krotko2020.pdf"},
        ],
        "failed": [{"doi": "10.1021/c160017a018", "error": "no OA PDF"}],
        "counts": {"succeeded": 2, "failed": 1},
    }
    lit = EvidenceItem(
        id="evi-lit-test",
        spec_id=spec.id,
        kind=EvidenceKind.LITERATURE,
        provenance=Provenance(data_ref="manifest.csv"),
        result=Result(type="qualitative",
                      finding=json.dumps(summary, ensure_ascii=False)),
        bears_on=[],
    )
    return [*base, lit]


def test_compile_emits_tex_only_not_md(tmp_path):
    # Overleaf-hardening: the .tex is THE paper artifact; the compiler no longer
    # emits draft.md (render_paper stays a library fn, just not auto-written here).
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex", experiment=_fake_experiment)

    run_dir = tmp_path / "runs" / "t-tex"
    tex_path = run_dir / "paper" / "draft.tex"
    md_path = run_dir / "paper" / "draft.md"
    assert tex_path.exists(), "draft.tex must be emitted as the paper artifact"
    assert not md_path.exists(), "draft.md must NOT be emitted (tex is the source of truth)"

    # result.paper_path points at the .tex.
    assert result.paper_path == tex_path
    assert result.paper_path.name == "draft.tex"

    tex = tex_path.read_text(encoding="utf-8")
    assert r"\documentclass{article}" in tex
    assert r"\end{document}" in tex


def test_compile_gathers_cited_dois_from_literature_evidence(tmp_path):
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex-lit", experiment=_literature_experiment)

    tex = (tmp_path / "runs" / "t-tex-lit" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    # All three cited DOIs (acquired + failed) appear as \url entries in References.
    assert r"\url{https://doi.org/10.48550/arXiv.1301.1493}" in tex
    assert r"\url{https://doi.org/10.1186/s13321-020-00453-4}" in tex
    assert r"\url{https://doi.org/10.1021/c160017a018}" in tex


def test_compile_gathers_dois_from_manifest_and_wires_bib(tmp_path):
    """The t1-godel shape: no LITERATURE EvidenceItem, but an
    artifacts/literature/manifest.csv + references.bib are present on disk."""
    run_dir = tmp_path / "runs" / "t-tex-manifest"
    lit_dir = run_dir / "artifacts" / "literature"
    lit_dir.mkdir(parents=True, exist_ok=True)
    (lit_dir / "manifest.csv").write_text(
        "index,doi,status,source,license,filename,origin,error\n"
        "1,10.1021/c160017a018,failed,,,,cli,no OA PDF\n"
        "2,10.48550/arXiv.1301.1493,success,arxiv,,McKay2013.pdf,cli,\n"
        "3,10.1186/s13321-020-00453-4,success,unpaywall,cc-by,Krotko2020.pdf,cli,\n",
        encoding="utf-8",
    )
    (lit_dir / "references.bib").write_text(
        "@article{morgan1965, doi={10.1021/c160017a018}}\n", encoding="utf-8"
    )

    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex-manifest", experiment=_fake_experiment)

    tex = (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8")
    # The existing references.bib is wired (NOT generated) as the SINGLE reference source:
    # natbib + plainnat + \bibliography, never a manual \url DOI list and never \nocite{*}.
    assert r"\bibliography{references}" in tex
    assert r"\bibliographystyle{plainnat}" in tex
    assert r"\nocite{*}" not in tex
    assert r"\url{https://doi.org/" not in tex


def test_compile_copies_references_bib_into_paper_dir(tmp_path):
    """Overleaf self-containment: when a references.bib exists for the run, the
    compiler copies it NEXT TO draft.tex (runs/<id>/paper/references.bib), so
    uploading the paper/ folder to Overleaf as-is resolves \\bibliography{references}."""
    run_dir = tmp_path / "runs" / "t-bib-colocate"
    lit_dir = run_dir / "artifacts" / "literature"
    lit_dir.mkdir(parents=True, exist_ok=True)
    bib_content = "@article{morgan1965, doi={10.1021/c160017a018}, title={Algorithm}}\n"
    (lit_dir / "references.bib").write_text(bib_content, encoding="utf-8")
    (lit_dir / "manifest.csv").write_text(
        "index,doi,status,source,license,filename,origin,error\n"
        "1,10.1021/c160017a018,success,arxiv,,X.pdf,cli,\n",
        encoding="utf-8",
    )

    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-bib-colocate", experiment=_fake_experiment)

    paper_dir = run_dir / "paper"
    co_located = paper_dir / "references.bib"
    # The .bib is co-located next to draft.tex ...
    assert co_located.exists(), "references.bib must be copied into paper/ for Overleaf"
    # ... with identical content (a faithful copy, not a regeneration) ...
    assert co_located.read_text(encoding="utf-8") == bib_content
    # ... and the stem the .tex references is 'references' (resolves in paper/).
    tex = (paper_dir / "draft.tex").read_text(encoding="utf-8")
    assert r"\bibliography{references}" in tex
    assert r"\nocite{*}" not in tex


def test_compile_no_bib_does_not_create_paper_bib(tmp_path):
    """No references.bib for the run -> nothing copied into paper/, no \\bibliography."""
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-bib-none", experiment=_fake_experiment)
    paper_dir = tmp_path / "runs" / "t-bib-none" / "paper"
    assert not (paper_dir / "references.bib").exists()
    tex = (paper_dir / "draft.tex").read_text(encoding="utf-8")
    assert r"\bibliography{" not in tex


def test_compile_without_literature_says_none_cited(tmp_path):
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex-nolit", experiment=_fake_experiment)
    tex = (tmp_path / "runs" / "t-tex-nolit" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    # No literature at all -> no References section and no \bibliography (the manual
    # "No literature cited." line is gone -- there is simply nothing to cite).
    assert "No literature cited." not in tex
    assert r"\section{References}" not in tex
    assert r"\bibliography{" not in tex


def test_compile_missing_references_bib_emits_no_bibliography(tmp_path):
    """Compiler-level coverage of the 'missing references.bib -> no \\bibliography'
    case (moved here from the renderer, which is now pure and does no fs check):
    a manifest.csv exists with DOIs but there is NO references.bib on disk, so
    _locate_bib_path returns None and the renderer emits no bibliography -- while the
    DOIs still appear as a References list."""
    run_dir = tmp_path / "runs" / "t-tex-nobib"
    lit_dir = run_dir / "artifacts" / "literature"
    lit_dir.mkdir(parents=True, exist_ok=True)
    (lit_dir / "manifest.csv").write_text(
        "index,doi,status,source,license,filename,origin,error\n"
        "1,10.1/x,success,arxiv,,X.pdf,cli,\n",
        encoding="utf-8",
    )
    # Deliberately NO references.bib written.

    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex-nobib", experiment=_fake_experiment)

    tex = (run_dir / "paper" / "draft.tex").read_text(encoding="utf-8")
    # The DOI is still cited ...
    assert r"\url{https://doi.org/10.1/x}" in tex
    # ... but with no references.bib on disk, no bibliography is wired.
    assert r"\bibliography{" not in tex
    assert r"\nocite{*}" not in tex


# ---------------------------------------------------------------------------
# CLI: --prose <json> injects narrative into both renderers.
# ---------------------------------------------------------------------------

def test_cli_run_emits_tex(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    rc = main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "t-cli-tex"])
    assert rc == 0
    tex_path = tmp_path / "runs" / "t-cli-tex" / "paper" / "draft.tex"
    assert tex_path.exists()
    assert r"\documentclass{article}" in tex_path.read_text(encoding="utf-8")


def test_cli_run_prose_injects_into_both_renderers(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    prose_json = tmp_path / "prose.json"
    prose_json.write_text(
        json.dumps({
            "abstract": "An offline abstract for the draft.",
            "introduction": "An offline introduction.",
            "discussion": "An offline discussion of limits.",
        }),
        encoding="utf-8",
    )

    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-prose", "--prose", str(prose_json),
    ])
    assert rc == 0

    paper_dir = tmp_path / "runs" / "t-cli-prose" / "paper"
    tex = (paper_dir / "draft.tex").read_text(encoding="utf-8")

    # Only the .tex is emitted now; the prose is injected into it.
    assert not (paper_dir / "draft.md").exists()
    assert r"\begin{abstract}" in tex
    assert "An offline abstract for the draft." in tex
    assert "Discussion" in tex
    assert "An offline introduction." in tex


def test_cli_run_without_prose_has_no_abstract(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    rc = main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "t-cli-noprose"])
    assert rc == 0
    tex = (tmp_path / "runs" / "t-cli-noprose" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    # No prose -> skeleton only, no abstract environment.
    assert r"\begin{abstract}" not in tex


# ---------------------------------------------------------------------------
# Figures hook (paper-figures Phase 1): compiler threads figures + surfaces the
# non-blocking prose<->figure consistency report; the CLI gains --figures <json>.
# ---------------------------------------------------------------------------

def _figures_json(fig_id: str, evidence_id: str) -> dict:
    """A PaperFigures payload plotting one point from `evidence_id`."""
    return {
        "figures": [
            {
                "id": fig_id,
                "caption": "Recorded finding across runs.",
                "plot": {
                    "type": "line",
                    "xlabel": "run",
                    "ylabel": "point",
                    "series": [
                        {
                            "y_field": "point",
                            "points": [{"evidence_id": evidence_id, "x": 1.0}],
                        }
                    ],
                },
            }
        ]
    }


def _point_experiment(spec, workspace_dir):
    """A fake experiment whose Evidence carries a numeric point (plottable)."""
    items = []
    for i, h in enumerate(spec.hypotheses):
        items.append(
            EvidenceItem(
                id=f"ev-pt-{i}",
                spec_id=spec.id,
                kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fake:pt", data_source="generated"),
                result=Result(type="quantitative", point=float(i + 1)),
                bears_on=[Bearing(target_id=h.id, direction=BearingDirection.SUPPORTS)],
            )
        )
    return items


def test_compile_threads_figures_into_tex(tmp_path):
    from sci_adk.render.figures import PaperFigures

    figs = PaperFigures.model_validate(_figures_json("growth", "ev-pt-0")).figures
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-fig", experiment=_point_experiment, figures=figs)

    tex = (tmp_path / "runs" / "t-fig" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    # pgfplots preamble + the figure float inside Results + the stable label, y pulled
    # from ev-pt-0 (the reframe places main figures in Results, no \section{Figures}).
    assert r"\usepackage{pgfplots}" in tex
    assert r"\section{Results}" in tex
    assert r"\section{Figures}" not in tex
    assert r"\label{fig:growth}" in tex
    assert "(1, 1)" in tex  # ev-pt-0 point=1.0 at x=1

    # The non-blocking consistency report is surfaced. growth is never \ref'd in the
    # skeleton body -> an orphan, but NOT a hard failure.
    fc = result.figure_consistency
    assert fc is not None
    assert "fig:growth" in fc.orphan
    assert fc.dangling == []
    assert fc.ok is False  # orphan -> not ok, but the compile still succeeded


def test_compile_no_figures_byte_identical_and_no_pgfplots(tmp_path):
    # figures omitted -> no pgfplots, no Figures section; the consistency report is ok.
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-nofig", experiment=_point_experiment)
    tex = (tmp_path / "runs" / "t-nofig" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    assert r"\usepackage{pgfplots}" not in tex
    assert r"\section{Figures}" not in tex
    assert result.figure_consistency is not None
    assert result.figure_consistency.ok is True  # no figures, no refs -> ok


def test_compile_figures_render_y_from_evidence(tmp_path):
    """End-to-end through the compiler: an agent-authored FigureSpec renders into
    draft.tex with the pgfplots preamble, the stable label, and y pulled from the
    recorded Evidence point (the CLI cannot inject an experiment hook, so the
    figure-rendering path is exercised here; the --figures FLAG parse/normalize/error
    paths are exercised through ``main()`` below)."""
    from sci_adk.render.figures import PaperFigures

    figs = PaperFigures.model_validate(_figures_json("encoding", "ev-pt-0")).figures
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-comp-fig", experiment=_point_experiment, figures=figs)

    tex = (tmp_path / "runs" / "t-comp-fig" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    assert r"\usepackage{pgfplots}" in tex
    assert r"\label{fig:encoding}" in tex
    assert r"\begin{axis}" in tex
    assert "(1, 1)" in tex  # ev-pt-0 point=1.0


# ---------------------------------------------------------------------------
# IMAGE figures (paper-figures Phase 4-1): the compiler co-locates the source image
# into paper/figures/<id><ext>; draft.tex/si.tex reference it. A missing source fails
# loud (record fidelity).
# ---------------------------------------------------------------------------

def _image_figure(fig_id: str, image_path: str) -> dict:
    """A PaperFigures payload carrying ONE image figure spec."""
    return {
        "figures": [
            {
                "kind": "image",
                "id": fig_id,
                "caption": "Reaction scheme.",
                "image": image_path,
            }
        ]
    }


def test_compile_colocates_image_figure_into_paper_figures(tmp_path):
    from sci_adk.render.figures import PaperFigures

    # A real source image (relative to the workspace dir, resolved by the compiler).
    src = tmp_path / "art" / "scheme.png"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x89PNG\r\n\x1a\n fake png bytes")

    figs = PaperFigures.model_validate(
        _image_figure("scheme", "art/scheme.png")
    ).figures
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-img", experiment=_point_experiment, figures=figs)

    paper_dir = tmp_path / "runs" / "t-img" / "paper"
    # The source bytes landed at paper/figures/fig<N><ext> -- the GENERIC, domain-free
    # figure-NUMBER filename (this is the only figure, so N=1), NOT the agent id.
    dest = paper_dir / "figures" / "fig1.png"
    assert dest.is_file(), "image source must be co-located into paper/figures/fig<N>"
    assert dest.read_bytes() == src.read_bytes()
    # The id is NEVER used as the filename.
    assert not (paper_dir / "figures" / "scheme.png").exists()

    # draft.tex references fig1 via graphicx (NOT pgfplots -- image-only render); the
    # \label keeps the SEMANTIC id so the body's \ref{fig:scheme} would resolve.
    draft = (paper_dir / "draft.tex").read_text(encoding="utf-8")
    assert r"\usepackage{graphicx}" in draft
    assert r"\usepackage{pgfplots}" not in draft  # no native figure here
    assert r"\includegraphics[width=\linewidth]{figures/fig1.png}" in draft
    assert r"\label{fig:scheme}" in draft

    # si.tex does NOT re-render the MAIN figure (the reframe: main figures live ONLY in
    # the paper's Results; the SI carries only supplementary si_figures, none here). So a
    # main figure is never duplicated across draft.tex + si.tex (design feedback 5.2).
    si = (paper_dir / "si.tex").read_text(encoding="utf-8")
    assert "{figures/fig1.png}" not in si
    assert r"\label{fig:scheme}" not in si


def test_compile_image_figure_absolute_path(tmp_path):
    from sci_adk.render.figures import PaperFigures

    # An ABSOLUTE source path is used verbatim (not re-rooted at the workspace dir).
    src = tmp_path / "outside" / "diagram.pdf"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"%PDF-1.4 fake")

    figs = PaperFigures.model_validate(
        _image_figure("diag", str(src))
    ).figures
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-img-abs", experiment=_point_experiment, figures=figs)

    # Co-located by figure NUMBER (fig1), source extension preserved; the id "diag" is
    # not the filename.
    dest = tmp_path / "runs" / "t-img-abs" / "paper" / "figures" / "fig1.pdf"
    assert dest.is_file()
    assert dest.read_bytes() == src.read_bytes()


def test_compile_missing_image_source_raises(tmp_path):
    import pytest

    from sci_adk.render.figures import PaperFigures

    # No file at art/missing.png -> co-location fails loud (record fidelity); the
    # paper/ folder must never be silently produced with a broken \includegraphics.
    figs = PaperFigures.model_validate(
        _image_figure("gone", "art/missing.png")
    ).figures
    with pytest.raises(ValueError):
        ResearchCompiler(workspace_dir=tmp_path).compile(
            PROPOSAL, spec_id="t-img-missing", experiment=_point_experiment,
            figures=figs)


def test_compile_mixed_native_and_image_figures(tmp_path):
    from sci_adk.render.figures import PaperFigures

    src = tmp_path / "scheme.pdf"
    src.write_bytes(b"%PDF-1.4 fake")

    payload = {
        "figures": [
            _figures_json("growth", "ev-pt-0")["figures"][0],          # native
            _image_figure("scheme", "scheme.pdf")["figures"][0],       # image
        ]
    }
    figs = PaperFigures.model_validate(payload).figures
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-img-mixed", experiment=_point_experiment, figures=figs)

    draft = (tmp_path / "runs" / "t-img-mixed" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    # BOTH packages present (one native + one image figure).
    assert r"\usepackage{pgfplots}" in draft
    assert r"\usepackage{graphicx}" in draft
    assert r"\label{fig:growth}" in draft
    assert r"\label{fig:scheme}" in draft
    # Neither figure is \ref'd in the skeleton body, so supply order holds: growth=fig1
    # (native, no file), scheme=fig2 (image -> co-located fig2.pdf, NOT scheme.pdf).
    figures_dir = tmp_path / "runs" / "t-img-mixed" / "paper" / "figures"
    assert (figures_dir / "fig2.pdf").is_file()
    assert not (figures_dir / "scheme.pdf").exists()
    assert r"\includegraphics[width=\linewidth]{figures/fig2.pdf}" in draft


# ---------------------------------------------------------------------------
# Body-reference figure numbering (Part B): a figure's number + co-located filename
# follow the order the figure is FIRST \ref'd in the body, and the SI shares that
# numbering with the main paper. (A \ref authored in a PROSE slot is now preserved by the
# prose-only sanitizer and DOES drive ordering through the compiler -- proven in
# tests/test_prose_refs.py and test_compile_prose_ref_drives_figure_numbering below. With
# NO prose ref, the body carries no live ref and numbering falls to supply order, which is
# what the first test below exercises.)
# ---------------------------------------------------------------------------

def test_compile_shares_figure_numbering_and_filenames_main_and_si(tmp_path):
    """End-to-end shared numbering: two image figures supplied [alpha, beta]. No prose ref
    reaches the body, so numbering is supply order: alpha=fig1 / beta=fig2 -- and CRUCIALLY
    the SI reuses the SAME fig<N> identity + the SAME co-located file set the main paper
    uses (one shared set for both standalone documents)."""
    from sci_adk.render.figures import PaperFigures

    a = tmp_path / "alpha.png"
    a.write_bytes(b"\x89PNG alpha")
    b = tmp_path / "beta.png"
    b.write_bytes(b"\x89PNG beta")

    payload = {
        "figures": [
            _image_figure("alpha", "alpha.png")["figures"][0],   # supplied first
            _image_figure("beta", "beta.png")["figures"][0],     # supplied second
        ]
    }
    figs = PaperFigures.model_validate(payload).figures
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-order", experiment=_point_experiment, figures=figs)

    paper_dir = tmp_path / "runs" / "t-order" / "paper"
    draft = (paper_dir / "draft.tex").read_text(encoding="utf-8")
    si = (paper_dir / "si.tex").read_text(encoding="utf-8")
    figures_dir = paper_dir / "figures"

    # Supply order (no live ref in the body): alpha=fig1, beta=fig2. The co-located bytes
    # and the \includegraphics paths agree (shared numbering, single name-builder).
    assert (figures_dir / "fig1.png").read_bytes() == a.read_bytes()  # alpha
    assert (figures_dir / "fig2.png").read_bytes() == b.read_bytes()  # beta
    assert r"\includegraphics[width=\linewidth]{figures/fig1.png}" in draft
    assert r"\includegraphics[width=\linewidth]{figures/fig2.png}" in draft
    # ONE shared file set -- no id-named or extra files.
    assert sorted(p.name for p in figures_dir.iterdir()) == ["fig1.png", "fig2.png"]

    # The SI does NOT re-render the MAIN figures (the reframe: main figures live ONLY in
    # the paper's Results; the SI carries only supplementary si_figures, none here), so
    # they are never duplicated across draft.tex + si.tex (design feedback 5.2).
    assert "{figures/fig1.png}" not in si
    assert "{figures/fig2.png}" not in si
    assert r"\label{fig:alpha}" not in si and r"\label{fig:beta}" not in si
    # The semantic labels survive in the PAPER so a body \ref{fig:<id>} resolves there.
    assert r"\label{fig:alpha}" in draft and r"\label{fig:beta}" in draft


def test_compile_prose_ref_drives_figure_numbering(tmp_path):
    """The payoff THROUGH the full compiler: prose discussion \\ref's fig:beta then
    fig:alpha; figures supplied [alpha, beta]. The prose-only sanitizer preserves the refs
    into the rendered body, so order_figures_by_reference numbers beta=fig1 / alpha=fig2 --
    BODY reference order, not supply order -- and the co-located paper/figures/fig1<ext> is
    BETA's image (the gap, closed end-to-end)."""
    from sci_adk.render.figures import PaperFigures
    from sci_adk.render.prose import PaperProse

    a = tmp_path / "alpha.png"
    a.write_bytes(b"\x89PNG alpha-bytes")
    b = tmp_path / "beta.png"
    b.write_bytes(b"\x89PNG beta-bytes")

    payload = {
        "figures": [
            _image_figure("alpha", "alpha.png")["figures"][0],   # supplied FIRST
            _image_figure("beta", "beta.png")["figures"][0],     # supplied SECOND
        ]
    }
    figs = PaperFigures.model_validate(payload).figures
    # Discussion \ref's beta BEFORE alpha -> body-reference order is beta, then alpha.
    prose = PaperProse(discussion=r"First \ref{fig:beta}, then \ref{fig:alpha}.")
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-prose-order", experiment=_point_experiment,
        figures=figs, prose=prose)

    paper_dir = tmp_path / "runs" / "t-prose-order" / "paper"
    draft = (paper_dir / "draft.tex").read_text(encoding="utf-8")
    figures_dir = paper_dir / "figures"

    # The prose \ref reached the body as REAL LaTeX (not escaped).
    assert r"\ref{fig:beta}" in draft
    assert r"\textbackslash{}ref" not in draft

    # Numbering is BODY-REFERENCE order: beta first-\ref'd -> fig1, alpha -> fig2. So the
    # co-located fig1<ext> is BETA's image (supply order would have made it alpha's).
    assert (figures_dir / "fig1.png").read_bytes() == b.read_bytes()  # beta = fig1
    assert (figures_dir / "fig2.png").read_bytes() == a.read_bytes()  # alpha = fig2
    assert r"\includegraphics[width=\linewidth]{figures/fig1.png}" in draft
    assert r"\includegraphics[width=\linewidth]{figures/fig2.png}" in draft
    assert sorted(p.name for p in figures_dir.iterdir()) == ["fig1.png", "fig2.png"]


def test_render_paper_orders_figures_by_body_reference(tmp_path):
    """At the renderer boundary (where a raw \\ref CAN be present), the Figures section is
    emitted in body-reference order: a body that \\ref's beta before alpha numbers beta=1.
    This pins the live-ref behavior the compiler shares; we drive a raw \\ref by calling
    order_figures_by_reference directly against a hand-built body and asserting
    render_image_figure agrees on fig<N>."""
    from sci_adk.render.figures import (
        PaperFigures,
        order_figures_by_reference,
        render_image_figure,
    )

    figs = PaperFigures.model_validate({
        "figures": [
            _image_figure("alpha", "alpha.png")["figures"][0],
            _image_figure("beta", "beta.png")["figures"][0],
        ]
    }).figures
    body = r"As \ref{fig:beta} shows, before \ref{fig:alpha}."
    ordered = order_figures_by_reference(figs, body)
    # beta first-\ref'd -> Figure 1 (file fig1), alpha -> Figure 2 (file fig2).
    assert [(n, f.id) for n, f in ordered] == [(1, "beta"), (2, "alpha")]
    # The image renderer emits the matching figures/fig<N> path for each number.
    assert "{figures/fig1.png}" in render_image_figure(ordered[0][1], ordered[0][0])
    assert "{figures/fig2.png}" in render_image_figure(ordered[1][1], ordered[1][0])


def test_cli_run_figures_flag_renders_figure(tmp_path, monkeypatch):
    """The --figures flag, through ``main()``, parses the file and renders the figure.

    The CLI has no experiment-hook argument; the only built-in CLI experiment
    (--t1-demo) mints non-deterministic ids and needs Docker. So we monkeypatch
    ``ResearchCompiler.compile`` to inject a deterministic fake experiment, then assert
    the parsed ``figures`` reach the compile and the rendered .tex carries the figure.
    """
    import json as _json

    from sci_adk.cli import main
    from sci_adk.loop.compiler import ResearchCompiler as _RC

    real_compile = _RC.compile

    def _patched_compile(self, proposal_text, **kwargs):
        # The CLI passes experiment=None explicitly on the proposal path; override it
        # with the deterministic fake hook so the run yields plottable evidence.
        if kwargs.get("experiment") is None:
            kwargs["experiment"] = _point_experiment
        return real_compile(self, proposal_text, **kwargs)

    monkeypatch.setattr(_RC, "compile", _patched_compile)

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    figures_json = tmp_path / "figures.json"
    figures_json.write_text(
        _json.dumps(_figures_json("encoding", "ev-pt-0")), encoding="utf-8"
    )

    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-fig", "--figures", str(figures_json),
    ])
    assert rc == 0
    tex = (tmp_path / "runs" / "t-cli-fig" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    assert r"\usepackage{pgfplots}" in tex
    assert r"\label{fig:encoding}" in tex
    assert r"\begin{axis}" in tex


def test_cli_run_figures_bare_list_accepted(tmp_path, monkeypatch):
    """The --figures file may be a bare list of FigureSpecs (not only a PaperFigures);
    the CLI normalizes both forms to a figure list."""
    import json as _json

    from sci_adk.cli import main
    from sci_adk.loop.compiler import ResearchCompiler as _RC

    real_compile = _RC.compile

    def _patched_compile(self, proposal_text, **kwargs):
        # The CLI passes experiment=None explicitly on the proposal path; override it
        # with the deterministic fake hook so the run yields plottable evidence.
        if kwargs.get("experiment") is None:
            kwargs["experiment"] = _point_experiment
        return real_compile(self, proposal_text, **kwargs)

    monkeypatch.setattr(_RC, "compile", _patched_compile)

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    bare_list = _figures_json("panelA", "ev-pt-0")["figures"]  # the inner list only
    figures_json = tmp_path / "figures_list.json"
    figures_json.write_text(_json.dumps(bare_list), encoding="utf-8")

    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-figlist", "--figures", str(figures_json),
    ])
    assert rc == 0
    tex = (tmp_path / "runs" / "t-cli-figlist" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    assert r"\label{fig:panelA}" in tex


def test_cli_run_figures_missing_file_errors(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-fig-missing", "--figures", str(tmp_path / "nope.json"),
    ])
    assert rc == 2


def test_cli_run_figures_invalid_json_errors(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-fig-badjson", "--figures", str(bad),
    ])
    assert rc == 2


def test_cli_run_figures_invalid_spec_errors(tmp_path):
    from sci_adk.cli import main

    import json as _json

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    # An unsafe figure id (space) -> FigureSpec validation rejects it -> rc 2.
    bad_spec = {"figures": [_figures_json("bad id", "ev-x")["figures"][0]]}
    bad_spec["figures"][0]["id"] = "bad id"
    f = tmp_path / "badspec.json"
    f.write_text(_json.dumps(bad_spec), encoding="utf-8")
    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-fig-badspec", "--figures", str(f),
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Supporting Information (paper-figures Phase 2, D3): the compiler also emits a
# standalone si.tex next to draft.tex; CompileResult.si_path points at it.
# ---------------------------------------------------------------------------

def test_compile_emits_si_next_to_draft(tmp_path):
    """The compiler writes paper/si.tex next to paper/draft.tex; si.tex is a
    standalone compilable document and CompileResult.si_path points at it."""
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-si-wire", experiment=_point_experiment)

    paper_dir = tmp_path / "runs" / "t-si-wire" / "paper"
    si_path = paper_dir / "si.tex"
    draft_path = paper_dir / "draft.tex"
    assert si_path.exists(), "paper/si.tex must be emitted next to draft.tex"
    assert draft_path.exists()

    # CompileResult.si_path points at the standalone SI.
    assert result.si_path == si_path
    assert result.si_path.name == "si.tex"

    si = si_path.read_text(encoding="utf-8")
    # Standalone doc: parses on its own (own \documentclass + \end{document}).
    assert r"\documentclass{article}" in si
    assert r"\end{document}" in si
    assert "Supporting Information" in si
    # The record dump carries the run's evidence id.
    assert "ev-pt-0" in si


def test_compile_si_figures_render_in_si_only(tmp_path):
    """The SI carries only SUPPLEMENTARY si_figures (the reframe: main figures live only
    in the paper, 5.2). A si_figure renders into si.tex with the pgfplots preamble; y
    pulled from the recorded Evidence. A MAIN figure does NOT appear in the SI."""
    from sci_adk.render.figures import PaperFigures

    main = PaperFigures.model_validate(_figures_json("main", "ev-pt-0")).figures
    supp = PaperFigures.model_validate(_figures_json("supp", "ev-pt-0")).figures
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-si-fig", experiment=_point_experiment,
        figures=main, si_figures=supp)

    si = (tmp_path / "runs" / "t-si-fig" / "paper" / "si.tex").read_text(
        encoding="utf-8")
    assert r"\usepackage{pgfplots}" in si
    assert r"\label{fig:supp}" in si      # the supplementary figure is in the SI
    assert r"\label{fig:main}" not in si  # the main figure is NOT duplicated into the SI
    assert "(1, 1)" in si  # ev-pt-0 point=1.0 at x=1


def test_compile_si_integrity_points_to_verify(tmp_path):
    """Phase 2 passes digest=None at compile time (evidence not yet persisted), so the
    SI's integrity section points to ``sci-adk verify`` rather than a fake digest."""
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-si-verify", experiment=_point_experiment)
    si = (tmp_path / "runs" / "t-si-verify" / "paper" / "si.tex").read_text(
        encoding="utf-8")
    assert "sci-adk verify" in si
    assert "Record digest (sha256):" not in si


# ---------------------------------------------------------------------------
# SI prose hook (Phase 4-3): the compiler threads si_prose into render_si_latex; the
# CLI gains --si-prose <json>. The no-prose si.tex stays byte-identical (regression).
# ---------------------------------------------------------------------------

def test_compile_threads_si_prose_into_si_tex(tmp_path):
    from sci_adk.render.prose import SIProse

    prose = SIProse(
        overview="An overview of the complete record dump.",
        notes="Closing notes on reproducibility.",
    )
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-si-prose", experiment=_point_experiment, si_prose=prose)

    si = (tmp_path / "runs" / "t-si-prose" / "paper" / "si.tex").read_text(
        encoding="utf-8")
    assert r"\section{Overview}" in si
    assert "An overview of the complete record dump." in si
    assert r"\section{Notes}" in si
    assert "Closing notes on reproducibility." in si


def test_compile_without_si_prose_has_no_prose_sections(tmp_path):
    """No si_prose -> the record dump only, no Overview/Notes narrative sections."""
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-si-noprose", experiment=_point_experiment)
    si = (tmp_path / "runs" / "t-si-noprose" / "paper" / "si.tex").read_text(
        encoding="utf-8")
    assert r"\section{Overview}" not in si
    assert r"\section{Notes}" not in si


def test_compile_si_prose_does_not_touch_paper_prose(tmp_path):
    """si_prose wraps si.tex ONLY; draft.tex (paper prose) is unaffected."""
    from sci_adk.render.prose import SIProse

    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-si-prose-iso", experiment=_point_experiment,
        si_prose=SIProse(overview="SI overview only."))
    paper_dir = tmp_path / "runs" / "t-si-prose-iso" / "paper"
    si = (paper_dir / "si.tex").read_text(encoding="utf-8")
    draft = (paper_dir / "draft.tex").read_text(encoding="utf-8")
    # The SI carries the overview; the main paper draft does not (no leakage).
    assert "SI overview only." in si
    assert "SI overview only." not in draft


def test_cli_run_si_prose_injects_into_si_tex(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    si_prose_json = tmp_path / "si_prose.json"
    si_prose_json.write_text(
        json.dumps({
            "overview": "An offline SI overview.",
            "notes": "An offline SI closing note.",
        }),
        encoding="utf-8",
    )

    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-si-prose", "--si-prose", str(si_prose_json),
    ])
    assert rc == 0

    paper_dir = tmp_path / "runs" / "t-cli-si-prose" / "paper"
    si = (paper_dir / "si.tex").read_text(encoding="utf-8")
    assert r"\section{Overview}" in si
    assert "An offline SI overview." in si
    assert r"\section{Notes}" in si
    assert "An offline SI closing note." in si


def test_cli_run_without_si_prose_has_no_prose_sections(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    rc = main([
        "run", str(proposal), "-o", str(tmp_path), "--spec-id", "t-cli-si-noprose",
    ])
    assert rc == 0
    si = (tmp_path / "runs" / "t-cli-si-noprose" / "paper" / "si.tex").read_text(
        encoding="utf-8")
    assert r"\section{Overview}" not in si
    assert r"\section{Notes}" not in si


def test_cli_run_si_prose_missing_file_errors(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-si-missing", "--si-prose", str(tmp_path / "nope.json"),
    ])
    assert rc == 2


def test_cli_run_si_prose_invalid_json_errors(tmp_path):
    from sci_adk.cli import main

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    bad = tmp_path / "bad_si.json"
    bad.write_text("{not valid json", encoding="utf-8")
    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-si-badjson", "--si-prose", str(bad),
    ])
    assert rc == 2
