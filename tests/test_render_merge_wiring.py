"""
render-merge (RED-first): the compiler/CLI wiring.

The compiler must emit ``runs/<id>/paper/draft.tex`` alongside ``draft.md`` (always,
via ``render_paper_latex``), gather ``cited_dois`` from the run's LITERATURE
EvidenceItem and/or its ``artifacts/literature/manifest.csv``, and set ``bib_path``
to ``artifacts/literature/references.bib`` when that file exists. The CLI gains an
optional ``--prose <json>`` that injects an agent-authored ``PaperProse`` into both
renderers.

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


def test_compile_emits_draft_tex_alongside_md(tmp_path):
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex", experiment=_fake_experiment)

    run_dir = tmp_path / "runs" / "t-tex"
    tex_path = run_dir / "paper" / "draft.tex"
    md_path = run_dir / "paper" / "draft.md"
    assert md_path.exists()
    assert tex_path.exists(), "draft.tex must be emitted alongside draft.md"

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
    # The three manifest DOIs appear.
    assert r"\url{https://doi.org/10.1021/c160017a018}" in tex
    assert r"\url{https://doi.org/10.48550/arXiv.1301.1493}" in tex
    assert r"\url{https://doi.org/10.1186/s13321-020-00453-4}" in tex
    # The existing references.bib is wired (NOT generated).
    assert r"\bibliography{references}" in tex
    assert r"\nocite{*}" in tex


def test_compile_without_literature_says_none_cited(tmp_path):
    ResearchCompiler(workspace_dir=tmp_path).compile(
        PROPOSAL, spec_id="t-tex-nolit", experiment=_fake_experiment)
    tex = (tmp_path / "runs" / "t-tex-nolit" / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    assert "No literature cited." in tex
    # No bib file -> no \bibliography wiring.
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
    md = (paper_dir / "draft.md").read_text(encoding="utf-8")
    tex = (paper_dir / "draft.tex").read_text(encoding="utf-8")

    # Markdown got the prose.
    assert "## Abstract" in md
    assert "An offline abstract for the draft." in md
    assert "## Discussion" in md
    # LaTeX got the prose.
    assert r"\begin{abstract}" in tex
    assert "An offline abstract for the draft." in tex
    assert "Discussion" in tex


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
