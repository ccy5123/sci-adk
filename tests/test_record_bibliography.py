"""
The record (``runs/<id>/record.tex`` and its copy ``paper/deposit/record.tex``) loads a
bibliography only when it cites (design/deposit-files.md §7 Q12, resolved).

The record renderer wrote ``\\bibliographystyle{plainnat}`` + ``\\bibliography{references}``
whenever the run had a ``references.bib``, but ``paper/deposit/`` holds no ``references.bib``:
built from that folder, ``bibtex record`` exits 2 ("I couldn't open database file
references.bib"). The record normally cites nothing -- the record dump is fully escaped, so
the only real ``\\cite`` it can carry is one written in the SIProse overview or notes. The two
lines are now written only when one of those slots cites (``\\cite``, ``\\citep``, ``\\citet``);
a record that cites nothing compiles with pdflatex alone, and its byte copy stays the D5
check's subject unchanged. A literal ``\\cite{..}`` in a recorded finding (escaped) or in an
inlined reproduction script (an ``lstlisting``, never executed) is not a citation.

The package's ``06_provenance/record.tex`` is built by ``make_si.py`` and never carried a
bibliography; it is unchanged.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.loop.compiler import deposit_record_path
from sci_adk.render.prose import SIProse
from sci_adk.render.reproduction import ReproListing
from sci_adk.render.si import render_si_latex
from tests.test_bib_latex_copy import _log_errors, _run, needs_tex
from tests.test_render_record_only import _seed
from tests.test_render_reframe import _experiment, _hyp, _spec

_BIB = "/x/references.bib"
_BIB_LINES = (r"\bibliographystyle{plainnat}", r"\bibliography{references}")


def _record(**kwargs) -> str:
    hyp = _hyp()
    evidence = kwargs.pop("evidence", [_experiment("evi-c", 0.0, '{"collision_count": 0}')])
    return render_si_latex(_spec(hyp), [], evidence, **kwargs)


def _has_bibliography(tex: str) -> bool:
    return all(line in tex for line in _BIB_LINES)


def test_a_record_that_cites_nothing_loads_no_bibliography():
    tex = _record(bib_path=_BIB)
    assert r"\bibliography" not in tex
    assert r"\usepackage{natbib}" in tex  # natbib stays: the preamble is unchanged


@pytest.mark.parametrize(
    "prose",
    [
        SIProse(overview=r"The method follows \citet{Doe2020}."),
        SIProse(notes=r"Values as in \citep{Doe2020}."),
        SIProse(notes=r"See \cite{Doe2020,Roe2021}."),
    ],
    ids=["overview-citet", "notes-citep", "notes-cite"],
)
def test_a_record_whose_prose_cites_loads_the_bibliography(prose):
    tex = _record(bib_path=_BIB, prose=prose)
    assert _has_bibliography(tex)
    assert tex.rstrip().endswith(r"\end{document}")
    assert tex.index(_BIB_LINES[1]) < tex.index(r"\end{document}")


def test_a_citing_record_without_a_bibliography_file_loads_none():
    tex = _record(prose=SIProse(notes=r"See \citep{Doe2020}."))
    assert r"\bibliography" not in tex


def test_prose_without_a_citation_loads_no_bibliography():
    tex = _record(bib_path=_BIB, prose=SIProse(overview=r"See Table~\ref{tab:s1}."))
    assert r"\bibliography" not in tex


def test_a_cite_command_in_a_recorded_finding_is_not_a_citation():
    ev = _experiment("evi-c", 0.0, r"the script printed \cite{Doe2020}")
    tex = _record(bib_path=_BIB, evidence=[ev])
    assert r"\textbackslash{}cite" in tex
    assert r"\bibliography" not in tex


def test_a_cite_command_in_inlined_reproduction_code_is_not_a_citation():
    listing = ReproListing(
        evidence_id="evi-c", code_ref="code/gen.py", kind="script",
        text="print(r'\\cite{Doe2020}')\n", filename="gen.py",
    )
    tex = _record(bib_path=_BIB, repro_listings=[listing])
    assert r"\cite{Doe2020}" in tex  # verbatim inside the lstlisting
    assert r"\bibliography" not in tex


def test_the_rendered_record_and_its_copy_load_no_bibliography(tmp_path, capsys):
    run_dir = _seed(tmp_path, "rec-bib")
    lit = run_dir / "artifacts" / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    (lit / "references.bib").write_text(
        "@article{Doe2020,\n  title={A title},\n  year={2020},\n  doi={10.1/x}\n}\n",
        encoding="utf-8",
    )
    assert main(["render", str(run_dir)]) == 0
    record = deposit_record_path(run_dir).read_text(encoding="utf-8")
    copy = (run_dir / "paper" / "deposit" / "record.tex").read_text(encoding="utf-8")
    assert copy == record
    assert r"\bibliography" not in record
    # The paper keeps its bibliography (it is the paper that cites).
    assert r"\bibliography{references}" in (run_dir / "paper" / "draft.tex").read_text(
        encoding="utf-8"
    )
    # The copy is still the D5 check's subject: byte-identical, listed, checked.
    capsys.readouterr()
    main(["verify", str(run_dir)])
    assert "deposit files: OK" in capsys.readouterr().out


def test_a_record_whose_si_prose_cites_keeps_its_bibliography(tmp_path):
    run_dir = _seed(tmp_path, "rec-bib-cite")
    lit = run_dir / "artifacts" / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    (lit / "references.bib").write_text(
        "@article{Doe2020,\n  title={A title},\n  year={2020},\n  doi={10.1/x}\n}\n",
        encoding="utf-8",
    )
    si_prose = tmp_path / "si_prose.json"
    si_prose.write_text(
        SIProse(notes=r"The method follows \citet{Doe2020}.").model_dump_json(),
        encoding="utf-8",
    )
    assert main(["render", str(run_dir), "--si-prose", str(si_prose)]) == 0
    record = deposit_record_path(run_dir).read_text(encoding="utf-8")
    assert _has_bibliography(record)


@needs_tex
def test_the_deposit_copy_builds_with_pdflatex_alone(tmp_path):
    work = tmp_path / "ws"
    run_dir = _seed(work, "rec-build")
    lit = run_dir / "artifacts" / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    (lit / "references.bib").write_text(
        "@article{Doe2020,\n  title={A title},\n  year={2020},\n  doi={10.1/x}\n}\n",
        encoding="utf-8",
    )
    assert main(["render", str(run_dir)]) == 0
    build = tmp_path / "build"
    shutil.copytree(run_dir / "paper" / "deposit", build)
    status = 0
    for _ in range(2):
        status = _run(["pdflatex", "-interaction=nonstopmode", "record.tex"], build)
    log = (build / "record.log").read_text(encoding="utf-8", errors="replace")
    assert status == 0, _log_errors(log)
    assert _log_errors(log) == []
    assert "Citation" not in log and "undefined" not in log
    assert "\\bibdata" not in (build / "record.aux").read_text(encoding="utf-8")
    assert Path(build / "record.pdf").is_file()
