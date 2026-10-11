"""
The deposit ships the bibliography its record names (design/deposit-files.md §7 Q12).

A record whose SI prose cites ends with ``\\bibliography{references}``, and ``paper/deposit/``
held only ``record.tex``: the deposited copy could not be built alone with bibtex ("I couldn't
open database file references.bib"). When the record carries that line, render now ships
``paper/deposit/references.bib``, a byte copy of the paper's ``paper/references.bib``, lists it
in the manifest (kind ``bibliography``), and ``verify`` checks it as it checks the record copy:
byte-identical to its source and listed. A record that cites nothing ships no bibliography.
The package's ``06_provenance/record.tex`` never names one, so the package is unchanged.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from sci_adk.cli import main
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.render.paper import check_paper_tool_vocabulary
from sci_adk.render.prose import PaperProse, SIProse
from tests.test_bib_latex_copy import _log_errors, _run, needs_tex
from tests.test_deposit_protocol import _deposit_problems, _manifest_rows, _spec_of
from tests.test_render_record_only import _seed

BS = chr(92)
_BIB = "@article{Doe2020,\n  title={A title},\n  author={Doe, Jane},\n  journal={J},\n" \
       "  year={2020},\n  doi={10.1/x}\n}\n"


def _citing_run(tmp_path: Path, name: str = "rec-bib-ship") -> Path:
    run_dir = _seed(tmp_path, name)
    lit = run_dir / "artifacts" / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    (lit / "references.bib").write_text(_BIB, encoding="utf-8")
    return run_dir


def _render(run_dir: Path, si_notes: str | None, methods: str = "M.") -> None:
    ResearchCompiler(workspace_dir=run_dir.parent.parent).stage_render(
        _spec_of(run_dir),
        prose=PaperProse(methods=methods),
        si_prose=SIProse(notes=si_notes) if si_notes else None,
    )


_CITES = "The method follows " + BS + "citet{Doe2020}."


def _shipped(run_dir: Path) -> Path:
    return run_dir / "paper" / "deposit" / "references.bib"


def test_record_bibliography_reads_the_line_the_record_carries():
    from sci_adk.render.deposit import record_bibliography

    # The closing lines render_si_latex writes (round 3: the line alone, e.g. in a listing,
    # does not count -- tests/test_latex_sanitize_round3.py).
    tail = (BS + "bibliographystyle{plainnat}\n" + BS + "bibliography{references}\n\n" + BS
            + "end{document}").encode()
    assert record_bibliography(b"x\n" + tail) == "references.bib"
    assert record_bibliography(b"x\n" + BS.encode() + b"bibliography{references}\n") is None
    assert record_bibliography(b"no bibliography here\n") is None
    assert record_bibliography(None) is None


def test_a_citing_record_ships_the_paper_bibliography_beside_it(tmp_path):
    run_dir = _citing_run(tmp_path)
    _render(run_dir, _CITES)
    paper_bib = (run_dir / "paper" / "references.bib").read_bytes()
    assert _shipped(run_dir).read_bytes() == paper_bib
    rows = {r[0]: r for r in _manifest_rows(run_dir)[1:] if r[0]}
    assert rows["references.bib"][:4] == [
        "references.bib", hashlib.sha256(paper_bib).hexdigest(), str(len(paper_bib)),
        "bibliography",
    ]
    assert [r[0] for r in _manifest_rows(run_dir)[1:]][-2:] == ["record.tex", "references.bib"]
    text = (run_dir / "paper" / "deposit" / "manifest.csv").read_text(encoding="utf-8")
    assert check_paper_tool_vocabulary(text) == []
    assert _deposit_problems(run_dir) == []


def test_a_record_that_cites_nothing_ships_no_bibliography(tmp_path):
    run_dir = _citing_run(tmp_path, "rec-bib-none")
    _render(run_dir, None)
    assert not _shipped(run_dir).exists()
    assert "references.bib" not in [r[0] for r in _manifest_rows(run_dir)[1:]]
    assert _deposit_problems(run_dir) == []


def test_a_rerender_that_no_longer_cites_removes_the_copy(tmp_path):
    run_dir = _citing_run(tmp_path, "rec-bib-drop")
    _render(run_dir, _CITES)
    assert _shipped(run_dir).is_file()
    _render(run_dir, None)
    assert not _shipped(run_dir).exists()
    assert _deposit_problems(run_dir) == []


def test_a_changed_copy_fails_verify(tmp_path):
    run_dir = _citing_run(tmp_path, "rec-bib-edit")
    _render(run_dir, _CITES)
    _shipped(run_dir).write_bytes(_shipped(run_dir).read_bytes() + b"% edited\n")
    problems = _deposit_problems(run_dir)
    assert "paper/deposit/references.bib differs from paper/references.bib -- re-render" in (
        problems
    ), problems


def test_a_missing_copy_fails_verify(tmp_path):
    run_dir = _citing_run(tmp_path, "rec-bib-gone")
    _render(run_dir, _CITES)
    _shipped(run_dir).unlink()
    problems = _deposit_problems(run_dir)
    assert any(p.startswith("paper/deposit/references.bib is missing") for p in problems), (
        problems
    )


def test_a_changed_paper_bibliography_fails_verify(tmp_path):
    # The copy's source is the paper's bibliography: edited after the render, the copy is stale.
    run_dir = _citing_run(tmp_path, "rec-bib-src")
    _render(run_dir, _CITES)
    source = run_dir / "paper" / "references.bib"
    source.write_bytes(source.read_bytes() + b"% edited\n")
    problems = _deposit_problems(run_dir)
    assert "paper/deposit/references.bib differs from paper/references.bib -- re-render" in (
        problems
    ), problems


def test_the_paper_may_name_the_shipped_bibliography(tmp_path):
    run_dir = _citing_run(tmp_path, "rec-bib-name")
    _render(run_dir, _CITES, methods="The references are in deposit/references.bib.")
    assert "deposit/references.bib" in (run_dir / "paper" / "draft.tex").read_text(
        encoding="utf-8")
    assert _deposit_problems(run_dir) == []


def test_render_and_verify_through_the_cli(tmp_path, capsys):
    run_dir = _citing_run(tmp_path, "rec-bib-cli")
    si_prose = tmp_path / "si_prose.json"
    si_prose.write_text(SIProse(notes=_CITES).model_dump_json(), encoding="utf-8")
    assert main(["render", str(run_dir), "--si-prose", str(si_prose)]) == 0
    assert _shipped(run_dir).is_file()
    capsys.readouterr()
    main(["verify", str(run_dir)])
    assert "deposit files: OK" in capsys.readouterr().out


@needs_tex
def test_the_deposit_folder_builds_alone_with_bibtex(tmp_path):
    work = tmp_path / "ws"
    run_dir = _citing_run(work, "rec-bib-build")
    _render(run_dir, _CITES)
    build = tmp_path / "build"
    shutil.copytree(run_dir / "paper" / "deposit", build)
    pdflatex = ["pdflatex", "-interaction=nonstopmode", "record.tex"]
    _run(pdflatex, build)
    bibtex_status = _run(["bibtex", "record"], build)
    _run(pdflatex, build)
    status = _run(pdflatex, build)
    log = (build / "record.log").read_text(encoding="utf-8", errors="replace")
    assert bibtex_status < 2, (build / "record.blg").read_text(encoding="utf-8")
    assert status == 0, _log_errors(log)
    assert _log_errors(log) == []
    assert "undefined" not in log
    assert "Doe" in (build / "record.bbl").read_text(encoding="utf-8")
