"""The renderer must find literature where the acquirer writes it.

LiteratureAcquirer writes ``runs/<id>/literature/{references.bib,manifest.csv}``, but the
compiler looked only in ``runs/<id>/artifacts/literature/`` -- the layout the test fixtures
seed -- so a run acquired by the real verbs rendered a paper with no bibliography at all
(found on the second trial run, 2026-10-09). The legacy layout must keep working.
"""

from __future__ import annotations

from pathlib import Path

from sci_adk.loop.compiler import ResearchCompiler

_BIB = "@article{Smith2001,\n  title = {A},\n  doi = {10.1/a},\n  year = {2001}\n}\n"
_MANIFEST = "index,doi,status,source,license,filename,origin,bib,error\n1,10.1/a,failed,,,,cli,ok,no OA PDF\n"


def _seed(run_dir: Path, subdir: str) -> None:
    lit = run_dir / subdir
    lit.mkdir(parents=True)
    (lit / "references.bib").write_text(_BIB, encoding="utf-8")
    (lit / "manifest.csv").write_text(_MANIFEST, encoding="utf-8")


def test_bib_is_found_where_the_acquirer_writes_it(tmp_path):
    _seed(tmp_path, "literature")
    located = ResearchCompiler._locate_bib_path(tmp_path)
    assert located is not None
    assert Path(located) == tmp_path / "literature" / "references.bib"


def test_cited_dois_are_read_from_the_acquirer_manifest(tmp_path):
    _seed(tmp_path, "literature")
    assert ResearchCompiler._gather_cited_dois([], tmp_path) == ["10.1/a"]


def test_legacy_artifacts_layout_still_works(tmp_path):
    _seed(tmp_path, "artifacts/literature")
    located = ResearchCompiler._locate_bib_path(tmp_path)
    assert located is not None and Path(located).parent.name == "literature"
    assert ResearchCompiler._gather_cited_dois([], tmp_path) == ["10.1/a"]


def test_acquirer_layout_wins_when_both_exist(tmp_path):
    _seed(tmp_path, "literature")
    _seed(tmp_path, "artifacts/literature")
    located = ResearchCompiler._locate_bib_path(tmp_path)
    assert Path(located) == tmp_path / "literature" / "references.bib"
