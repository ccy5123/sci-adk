"""
The deposited code carries a README that maps scripts to inputs, outputs and paper numbers.

On a real run the reproduction bundle shipped seventeen scripts under ``paper/code/`` and a
``paper/reproduce.py`` that checks their hashes and runs nothing. Nothing told the paper's
reader which script produced which number, which inputs each read, or which of those inputs
the paper distributes; and two of the run's output files carried absolute paths under the
author's home directory, which nothing would have noticed had they been shipped.

The contract tested here:

  - render writes ``paper/code/README.md`` (English, ASCII) whenever scripts ship: what
    ``reproduce.py`` does and why it runs nothing, what the record does not hold, and per
    script -- in the order its first result was recorded -- its SHA-256, the input files its
    results name (distributed with the paper or not, with the cited source), the files they
    wrote, the numbers in the paper that come from them (``numbers.json``) and the figures
    drawn from them; recorded-result ids only as cross-references into the record;
  - a file has one writer when the record identifies one ("written by <script>" in a data
    description, else the earliest result naming it as output): a file another script
    wrote is an input, even where a result also names it as output; a contradictory record
    is said to be one; a result naming several scripts is listed under the first only;
    each file is named by its fullest recorded path;
  - ``verify`` (with a reproduction-bundle contract) fails a README that is not the one
    render writes for the current record, and asks for a re-render;
  - render warns when a shipped text file holds an absolute local path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.numbers import NumberList
from sci_adk.core.spec import Spec
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run
from sci_adk.render.code_readme import (
    CODE_README_MARKER,
    DepositedFile,
    FigureLink,
    ReadmeScript,
    files_named,
    local_path_warnings,
    render_code_readme,
    strip_figure_lines,
)
from tests.test_reproduction_bundle import _freeze_bundle_contract, _seed

BS = chr(92)
_DIR = "analysis/x"
_BODIES = {
    "a_prepare.py": "print('prepare')\n",
    "b_fit.py": "print('fit')\n",
    "z_plot.py": "print('plot')\n",
}
_CLEAN = b"id,value\n1,2.5\n2,3.5\n"
_VENDOR = b"vendor workbook bytes"
_TABLE = b"raw table bytes"


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _s(name: str) -> str:
    return _h(_BODIES[name].encode("utf-8"))


def _at(day: int) -> datetime:
    return datetime(2026, 10, day, 10, 0, 0, tzinfo=timezone.utc)


def _evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id="evi-obs-prepare", created_at=_at(2), spec_id="",
            kind=EvidenceKind.OBSERVATION,
            provenance=Provenance(
                code_ref=f"{_DIR}/a_prepare.py sha256={_s('a_prepare.py')}",
                data_ref=(f"raw table data/raw/table.csv sha256 {_h(_TABLE)}; vendor file "
                          f"vendor.xls sha256 {_h(_VENDOR)}"),
                data_source="measured",
            ),
            result=Result(type="qualitative", finding='{"n_rows": 120}',
                          artifact_ref=f"{_DIR}/out/clean.csv sha256={_h(_CLEAN)}"),
            bears_on=[],
        ),
        EvidenceItem(
            id="evi-run-fit", created_at=_at(3), spec_id="",
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(
                code_ref=(f"{_DIR}/b_fit.py sha256={_s('b_fit.py')} (reads "
                          f"{_DIR}/out/clean.csv sha256={_h(_CLEAN)})"),
                data_source="measured",
            ),
            result=Result(type="quantitative", point=0.0, finding="the fitted metric",
                          artifact_ref=f"{_DIR}/out/fit.json"),
            bears_on=[Bearing(target_id="H1", direction=BearingDirection.SUPPORTS)],
        ),
        EvidenceItem(
            id="evi-obs-both", created_at=_at(4), spec_id="",
            kind=EvidenceKind.OBSERVATION,
            provenance=Provenance(
                code_ref=(f"{_DIR}/a_prepare.py sha256={_s('a_prepare.py')}; "
                          f"{_DIR}/b_fit.py sha256={_s('b_fit.py')}"),
                data_source="measured",
            ),
            result=Result(type="qualitative", finding='{"k": 7}'),
            bears_on=[],
        ),
        EvidenceItem(
            id="evi-obs-plot", created_at=_at(1), spec_id="",
            kind=EvidenceKind.OBSERVATION,
            provenance=Provenance(code_ref=f"{_DIR}/z_plot.py sha256={_s('z_plot.py')}",
                                  data_source="measured"),
            result=Result(type="qualitative", finding="a plot"),
            bears_on=[],
        ),
    ]


def _scripts() -> list[ReadmeScript]:
    # evi-obs-both's code reference names a_prepare.py first, then b_fit.py.
    return [
        ReadmeScript("a_prepare.py", _s("a_prepare.py"), ("evi-obs-prepare", "evi-obs-both")),
        ReadmeScript("b_fit.py", _s("b_fit.py"), ("evi-run-fit", "evi-obs-both"),
                     also_named_ids=("evi-obs-both",)),
        ReadmeScript("z_plot.py", _s("z_plot.py"), ("evi-obs-plot",)),
    ]


_NUMBERS = {
    "spec_id": "S",
    "numbers": [
        {"text": "120", "source": {"evidence": "evi-obs-prepare", "field": "finding.n_rows"}},
        {"text": "0", "source": {"evidence": "evi-run-fit", "field": "point"}},
        {"text": "0", "document": "si.tex",
         "source": {"evidence": "evi-run-fit", "field": "point"}},
        {"text": "700", "formula": "100 * a",
         "operands": {"a": {"evidence": "evi-obs-both", "field": "finding.k"}}},
        {"text": "2026", "role": "identifier"},
    ],
}
_DEPOSITED = [
    DepositedFile("data/clean.csv", _h(_CLEAN), ()),
    DepositedFile("", _h(_VENDOR), ("Vendor2020",)),
]


def _readme(**kw) -> str:
    args = dict(
        deposited=_DEPOSITED,
        numbers=NumberList.model_validate(_NUMBERS),
        dois={"Vendor2020": "10.1234/vendor"},
    )
    args.update(kw)
    return render_code_readme(_scripts(), [e.model_copy(update={"spec_id": "S"})
                                           for e in _evidence()], **args)


def _block(text: str, name: str) -> str:
    start = text.index(f". {name}\n")
    nxt = text.find("\n## ", start)
    return text[start:] if nxt < 0 else text[start:nxt]


def _line(block: str, prefix: str) -> str:
    return next(line for line in block.split("\n") if line.startswith(prefix))


# =========================================================================== #
# the README text                                                              #
# =========================================================================== #

class TestReadmeText:
    def test_it_is_ascii_and_opens_with_the_marker(self):
        text = _readme()
        assert text.isascii()
        assert text.splitlines()[0] == CODE_README_MARKER

    def test_header_says_what_reproduce_py_does_and_what_the_record_lacks(self):
        head = " ".join(_readme().split("\n## ", 1)[0].split())
        assert "reproduce.py" in head and "runs none" in head
        assert "cannot be redistributed" in head
        assert "command lines" in head
        assert "deposit/record.tex" in head
        # Record ids are explained once, at the top, and appear only as cross-references.
        assert head.count("identify recorded results") == 1
        assert not any(ev.id in head for ev in _evidence())

    def test_scripts_follow_the_order_of_their_first_recorded_result(self):
        text = _readme()
        order = [text.index(f". {n}\n") for n in ("z_plot.py", "a_prepare.py", "b_fit.py")]
        assert order == sorted(order)

    def test_each_script_gives_its_sha256(self):
        assert _s("b_fit.py") in _block(_readme(), "b_fit.py")

    def test_inputs_are_marked_distributed_or_not_with_their_source(self):
        block = _block(_readme(), "a_prepare.py")
        assert f"`data/raw/table.csv`, SHA-256 {_h(_TABLE)}: not distributed with the paper" in block
        assert (f"`vendor.xls`, SHA-256 {_h(_VENDOR)}: not distributed with the paper; "
                "source: references.bib entry Vendor2020 (doi:10.1234/vendor)") in block

    def test_an_input_named_by_a_code_ref_and_written_by_another_script(self):
        block = _block(_readme(), "b_fit.py")
        assert (f"`{_DIR}/out/clean.csv`, SHA-256 {_h(_CLEAN)}: written by a_prepare.py; "
                "distributed with the paper as deposit/data/clean.csv") in block

    def test_outputs_with_and_without_a_recorded_hash(self):
        assert (f"`{_DIR}/out/clean.csv`, SHA-256 {_h(_CLEAN)}; distributed with the paper "
                "as deposit/data/clean.csv") in _block(_readme(), "a_prepare.py")
        assert f"`{_DIR}/out/fit.json` (no SHA-256 recorded)" in _block(_readme(), "b_fit.py")

    def test_numbers_are_listed_under_the_result_they_come_from(self):
        a = _block(_readme(), "a_prepare.py")
        b = _block(_readme(), "b_fit.py")
        assert "evi-obs-prepare: 120 (finding.n_rows)" in a
        assert "evi-run-fit: 0 (point)" in b
        assert "evi-run-fit, supplementary information: 0 (point)" in b
        assert "evi-obs-both: 700 (derived from finding.k)" in a
        assert "120 (" not in b and "2026 (" not in a + b

    def test_a_file_named_as_both_input_and_output_says_so(self):
        # One result names the same bytes as what it read and what it wrote, and no other
        # result says who wrote them: the README says so instead of picking one.
        ev = _evidence()
        ev[0] = ev[0].model_copy(update={"provenance": ev[0].provenance.model_copy(
            update={"data_ref": f"table out/clean.csv sha256={_h(_CLEAN)}"})})
        block = _block(render_code_readme(_scripts(), ev), "a_prepare.py")
        assert "none recorded" not in _line(block, "- Input files")
        both = "recorded as both an input and an output of these results"
        assert f"  - `{_DIR}/out/clean.csv`, SHA-256 {_h(_CLEAN)}: {both}" in block
        assert f"  - `{_DIR}/out/clean.csv`, SHA-256 {_h(_CLEAN)}; {both}" in block

    def test_a_result_naming_two_scripts_is_listed_under_the_first_only(self):
        # evi-obs-both names a_prepare.py first: its results and numbers are listed there,
        # and b_fit.py says which result also names it and where that result is listed.
        text = _readme()
        a, b = _block(text, "a_prepare.py"), _block(text, "b_fit.py")
        assert "evi-obs-both" in _line(a, "- Recorded results:")
        assert "evi-obs-both" not in _line(b, "- Recorded results:")
        assert "700 (" in a and "700 (" not in b
        assert ("- Also named by recorded results listed under the script their code "
                "reference names first: evi-obs-both (a_prepare.py)") in b
        assert "Also named" not in a

    def test_a_script_only_ever_named_second_points_to_where_its_results_are(self):
        extra = ReadmeScript("y_extra.py", _h(b"extra"), ("evi-obs-both",),
                             also_named_ids=("evi-obs-both",))
        text = render_code_readme(_scripts() + [extra], _evidence())
        block = _block(text, "y_extra.py")
        assert "- Recorded results: none listed under this script" in block
        assert "first: evi-obs-both (a_prepare.py)" in block
        assert "Input files" not in block and "Numbers in the paper" not in block

    def test_a_number_printed_twice_is_listed_once(self):
        numbers = dict(_NUMBERS, numbers=_NUMBERS["numbers"] + [_NUMBERS["numbers"][0]])
        block = _block(_readme(numbers=NumberList.model_validate(numbers)), "a_prepare.py")
        assert block.count("120 (finding.n_rows)") == 1

    def test_nothing_recorded_says_so(self):
        block = _block(_readme(), "z_plot.py")
        assert "Input files these results name: none recorded" in block
        assert "Numbers in the paper from these results: none" in block

    def test_without_deposit_rows_every_input_is_not_distributed(self):
        block = _block(_readme(deposited=[]), "a_prepare.py")
        assert f"`vendor.xls`, SHA-256 {_h(_VENDOR)}: not distributed with the paper\n" in block

    def test_figures_are_listed_and_strippable(self):
        figs = [FigureLink("Figure 2", "fig:scatter", ("evi-run-fit",))]
        with_figs = _readme(figures=figs)
        assert "Figure 2 (fig:scatter): evi-run-fit" in _block(with_figs, "b_fit.py")
        assert strip_figure_lines(with_figs) == strip_figure_lines(_readme())
        assert strip_figure_lines(with_figs) == _readme()

    def test_non_ascii_names_are_folded(self):
        ev = _evidence()
        ev[0] = ev[0].model_copy(update={"provenance": ev[0].provenance.model_copy(
            update={"data_ref": f"caf{chr(233)}.csv sha256 {_h(_TABLE)}"})})
        text = render_code_readme(_scripts(), ev)
        assert text.isascii() and "`cafe.csv`" in text


_COUNT = "c_count.py"
_COUNT_SHA = _h(b"print('count')\n")
_FIT = b"fit bytes"
_COUNTS = b'{"rows": 2}'


def _count_item(data_ref, artifact_ref, *, day=5, item_id="evi-obs-count") -> EvidenceItem:
    """A result of a fourth script, c_count.py, recorded on ``day``."""
    return EvidenceItem(
        id=item_id, created_at=_at(day), spec_id="", kind=EvidenceKind.OBSERVATION,
        provenance=Provenance(code_ref=f"{_DIR}/{_COUNT} sha256={_COUNT_SHA}",
                              data_ref=data_ref, data_source="measured"),
        result=Result(type="qualitative", finding='{"rows": 2}', artifact_ref=artifact_ref),
        bears_on=[],
    )


def _with_count(*items: EvidenceItem, evidence=None) -> str:
    scripts = _scripts() + [ReadmeScript(_COUNT, _COUNT_SHA, tuple(i.id for i in items))]
    return render_code_readme(scripts, (evidence or _evidence()) + list(items),
                              deposited=_DEPOSITED)


_CLEAN_PATH = f"{_DIR}/out/clean.csv"
_WRITTEN_BY_PREPARE = f"(written by a_prepare.py sha256={_s('a_prepare.py')})"


class TestWhoWroteAFile:
    """A file has one writer when the record identifies one: a result's data description
    saying "written by <script>", else the earliest result naming it as an output."""

    def test_a_file_another_script_wrote_is_an_input_even_when_named_as_output(self):
        # The record names the file in both places and says a_prepare.py wrote it.
        text = _with_count(_count_item(
            f"{_CLEAN_PATH} sha256={_h(_CLEAN)} {_WRITTEN_BY_PREPARE}",
            f"{_CLEAN_PATH} sha256={_h(_CLEAN)}",
        ))
        block = _block(text, _COUNT)
        assert (f"  - `{_CLEAN_PATH}`, SHA-256 {_h(_CLEAN)}: written by a_prepare.py; "
                "distributed with the paper as deposit/data/clean.csv") in block
        assert "- Files these results wrote: none recorded" in block
        # Every other mention of the file names one writer.
        for line in text.split("\n"):
            if "out/clean.csv" in line and "written by" in line:
                assert "written by a_prepare.py;" in line, line

    def test_the_output_of_an_earlier_result_of_another_script_is_an_input(self):
        # No "written by": a_prepare.py's earlier result named the file as its output.
        block = _block(_with_count(_count_item(
            f"the cleaned table sha256 {_h(_CLEAN)}", f"{_CLEAN_PATH} sha256={_h(_CLEAN)}",
        )), _COUNT)
        assert f"  - `{_CLEAN_PATH}`, SHA-256 {_h(_CLEAN)}: written by a_prepare.py;" in block
        assert "- Files these results wrote: none recorded" in block

    def test_named_only_as_an_output_but_written_earlier_by_another_script(self):
        block = _block(_with_count(_count_item(None, f"{_CLEAN_PATH} sha256={_h(_CLEAN)}")),
                       _COUNT)
        assert f"  - `{_CLEAN_PATH}`, SHA-256 {_h(_CLEAN)}: written by a_prepare.py;" in block
        assert "- Files these results wrote: none recorded" in block

    def test_a_stated_writer_wins_over_an_earlier_output(self):
        # c_count.py's result of day 1 names the file as its output, but a later result says
        # a_prepare.py wrote it: a_prepare.py is the writer, c_count.py read it.
        text = _with_count(
            _count_item(None, f"{_CLEAN_PATH} sha256={_h(_CLEAN)}", day=1),
            _count_item(f"{_CLEAN_PATH} sha256={_h(_CLEAN)} {_WRITTEN_BY_PREPARE}", None,
                        day=6, item_id="evi-obs-count-2"),
        )
        assert f"`{_CLEAN_PATH}`, SHA-256 {_h(_CLEAN)}; distributed" in _block(text, "a_prepare.py")
        count = _block(text, _COUNT)
        assert f"  - `{_CLEAN_PATH}`, SHA-256 {_h(_CLEAN)}: written by a_prepare.py;" in count
        assert "- Files these results wrote: none recorded" in count

    def test_data_naming_only_files_the_script_wrote_is_not_none_recorded(self):
        out = f"{_DIR}/out/count.json sha256={_h(_COUNTS)}"
        block = _block(_with_count(
            _count_item(None, out),
            _count_item(f"{out} (written by {_COUNT} sha256={_COUNT_SHA})", None, day=6,
                        item_id="evi-obs-count-2"),
        ), _COUNT)
        assert ("- Input files these results name: none besides files these results wrote "
                "(listed below)") in block
        assert f"  - `{_DIR}/out/count.json`, SHA-256 {_h(_COUNTS)}" in block

    def test_an_output_written_by_another_script_the_result_names_is_marked(self):
        # evi-obs-both (a_prepare.py first, then b_fit.py) names fit.json as its output, and
        # so does b_fit.py's own result: b_fit.py is the one script every result naming it
        # names, so it is the writer; the shared result stays under a_prepare.py.
        ev = _evidence()
        both = ev[2]
        ev[2] = both.model_copy(update={"result": both.result.model_copy(
            update={"artifact_ref": f"{_DIR}/out/fit.json"})})
        text = render_code_readme(_scripts(), ev)
        assert (f"  - `{_DIR}/out/fit.json` (no SHA-256 recorded); written by b_fit.py"
                in _block(text, "a_prepare.py"))
        assert f"  - `{_DIR}/out/fit.json` (no SHA-256 recorded)\n" in _block(text, "b_fit.py") + "\n"

    def test_a_file_is_named_by_its_fullest_recorded_path_everywhere(self):
        # Named only by its hash, or by its base name, here; by a full path elsewhere.
        block = _block(_with_count(_count_item(
            f"the raw table sha256 {_h(_TABLE)}; fit.json sha256 {_h(_FIT)}", None,
        )), _COUNT)
        assert f"  - `data/raw/table.csv`, SHA-256 {_h(_TABLE)}:" in block
        assert f"  - `{_DIR}/out/fit.json`, SHA-256 {_h(_FIT)}: written by b_fit.py;" in block
        assert "names only by its SHA-256" not in block


class TestFilesNamed:
    def test_hash_with_and_without_a_name(self):
        assert files_named(f"x/y.csv sha256={'a' * 64}; copy sha256 {'b' * 64}") == [
            ("x/y.csv", "a" * 64), (None, "b" * 64),
        ]

    def test_paths_without_hashes_and_noise(self):
        text = "out/a.json; out/b.csv (DOI 10.1139/abc-1, v2.9.5, see https://e.org/x.csv)"
        assert files_named(text) == [("out/a.json", None), ("out/b.csv", None)]


# =========================================================================== #
# render writes it, verify checks it                                           #
# =========================================================================== #

def _write_files(ws: Path) -> None:
    d = ws / _DIR
    (d / "out").mkdir(parents=True, exist_ok=True)
    for name, body in _BODIES.items():
        (d / name).write_bytes(body.encode("utf-8"))
    (d / "out" / "clean.csv").write_bytes(_CLEAN)
    (ws / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (ws / "data" / "raw" / "vendor.xls").write_bytes(_VENDOR)


def _run(tmp_path: Path) -> Path:
    _write_files(tmp_path)
    run_dir = _seed(tmp_path, "rb-readme", _evidence())
    lit = run_dir / "literature"
    lit.mkdir(exist_ok=True)
    (lit / "references.bib").write_text(
        "@misc{Vendor2020,\n  title={Vendor data},\n  year={2020},\n  doi={10.1234/vendor}\n}\n",
        encoding="utf-8")
    (run_dir / "numbers.json").write_text(
        json.dumps({**_NUMBERS, "spec_id": run_dir.name}), encoding="utf-8")
    (run_dir / "deposit.json").write_text(json.dumps({
        "spec_id": run_dir.name,
        "files": [
            {"source": f"{_DIR}/out/clean.csv", "name": "clean.csv", "origin": "recorded",
             "evidence": "evi-obs-prepare", "description": "The cleaned table."},
            {"source": "data/raw/vendor.xls", "origin": "external",
             "evidence": "evi-obs-prepare", "cite": ["Vendor2020"],
             "description": "The vendor workbook."},
        ],
    }), encoding="utf-8")
    return run_dir


def _render(run_dir: Path) -> ResearchCompiler:
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    compiler = ResearchCompiler(workspace_dir=run_dir.parent.parent)
    compiler.stage_render(spec)
    return compiler


def _readme_problems(run_dir: Path) -> list[str]:
    report = verify_run(run_dir)
    return [p for p in report.paper_requirements_problems if "README" in p]


class TestRenderAndVerify:
    def test_render_writes_the_readme_and_verify_accepts_it(self, tmp_path):
        run_dir = _run(tmp_path)
        _render(run_dir)
        readme = (run_dir / "paper" / "code" / "README.md").read_text(encoding="utf-8")
        assert readme.isascii()
        assert "distributed with the paper as deposit/data/clean.csv" in readme
        assert "source: references.bib entry Vendor2020 (doi:10.1234/vendor)" in readme
        assert "evi-obs-prepare: 120 (finding.n_rows)" in readme
        # Render and verify both find the script a result's code reference names first.
        assert "first: evi-obs-both (a_prepare.py)" in _block(readme, "b_fit.py")
        assert "evi-obs-both: 700" in _block(readme, "a_prepare.py")
        _freeze_bundle_contract(run_dir)
        assert _readme_problems(run_dir) == []

    def test_a_result_goes_under_the_script_its_code_reference_names_first(self, tmp_path):
        # evi-run-fit names b_fit.py first, then a_prepare.py, which ships first (the record
        # names it first): render and verify both list the result under b_fit.py.
        run_dir = _run(tmp_path)
        path = run_dir / "evidence" / "evi-run-fit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["provenance"]["code_ref"] = (
            f"{_DIR}/b_fit.py sha256={_s('b_fit.py')}; {_DIR}/a_prepare.py "
            f"sha256={_s('a_prepare.py')} (reads {_DIR}/out/clean.csv sha256={_h(_CLEAN)})")
        path.write_text(json.dumps(data), encoding="utf-8")
        _render(run_dir)
        readme = (run_dir / "paper" / "code" / "README.md").read_text(encoding="utf-8")
        a, b = _block(readme, "a_prepare.py"), _block(readme, "b_fit.py")
        assert "evi-run-fit: 0 (point)" in b and "evi-run-fit: 0" not in a
        assert "first: evi-run-fit (b_fit.py)" in a
        _freeze_bundle_contract(run_dir)
        assert _readme_problems(run_dir) == []

    def test_an_edited_readme_fails_verify_until_re_rendered(self, tmp_path):
        run_dir = _run(tmp_path)
        _render(run_dir)
        _freeze_bundle_contract(run_dir)
        path = run_dir / "paper" / "code" / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
        problems = _readme_problems(run_dir)
        assert problems and "re-run sci-adk render" in problems[0]
        _render(run_dir)
        assert _readme_problems(run_dir) == []

    def test_a_changed_number_list_makes_the_readme_stale(self, tmp_path):
        run_dir = _run(tmp_path)
        _render(run_dir)
        _freeze_bundle_contract(run_dir)
        numbers = dict(_NUMBERS, spec_id=run_dir.name, numbers=_NUMBERS["numbers"][1:])
        (run_dir / "numbers.json").write_text(json.dumps(numbers), encoding="utf-8")
        assert _readme_problems(run_dir)

    def test_a_missing_readme_fails_verify(self, tmp_path):
        run_dir = _run(tmp_path)
        _render(run_dir)
        _freeze_bundle_contract(run_dir)
        (run_dir / "paper" / "code" / "README.md").unlink()
        assert any("missing" in p for p in _readme_problems(run_dir))

    def test_a_hand_written_readme_is_left_and_named(self, tmp_path):
        run_dir = _run(tmp_path)
        code = run_dir / "paper" / "code"
        code.mkdir(parents=True)
        (code / "README.md").write_text("my own notes\n", encoding="utf-8")
        compiler = _render(run_dir)
        assert (code / "README.md").read_text(encoding="utf-8") == "my own notes\n"
        assert any("README.md" in w for w in compiler.bundle_warnings)
        _freeze_bundle_contract(run_dir)
        assert _readme_problems(run_dir)

    def test_a_native_figure_is_linked_and_verify_still_accepts_the_readme(self, tmp_path):
        from sci_adk.render.figures import FigureSpec

        run_dir = _run(tmp_path)
        spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
        fig = FigureSpec.model_validate({
            "id": "fit", "caption": "The fitted metric.",
            "plot": {"type": "scatter", "xlabel": "x", "ylabel": "y",
                     "series": [{"points": [{"evidence_id": "evi-run-fit", "x": 1.0}]}]},
        })
        ResearchCompiler(workspace_dir=tmp_path).stage_render(spec, figures=[fig])
        readme = (run_dir / "paper" / "code" / "README.md").read_text(encoding="utf-8")
        assert "  - Figure 1 (fig:fit): evi-run-fit" in _block(readme, "b_fit.py")
        _freeze_bundle_contract(run_dir)
        assert _readme_problems(run_dir) == []

    def test_no_shipped_script_no_readme_and_a_stale_one_goes(self, tmp_path):
        run_dir = _run(tmp_path)
        _render(run_dir)
        assert (run_dir / "paper" / "code" / "README.md").is_file()
        for name in _BODIES:
            (tmp_path / _DIR / name).unlink()
        _render(run_dir)
        assert not (run_dir / "paper" / "code" / "README.md").exists()


# =========================================================================== #
# absolute local paths in shipped text files                                   #
# =========================================================================== #

class TestLocalPaths:
    def test_home_and_user_paths_are_counted_per_file(self):
        lines = local_path_warnings({
            "paper/code/a.py": b"x = '/home/alice/data.csv'\ny = '/Users/bob/z.txt'\nz = 1\n",
            "paper/deposit/data/t.csv": ("p," + "C:" + BS + "Users" + BS + "carol" + BS
                                         + "t.csv\n").encode(),
            "paper/code/b.py": b"see https://example.org/home/page and data/home/x\n",
        })
        assert len(lines) == 2
        assert lines[0].startswith("paper/code/a.py has 2 lines")
        assert lines[1].startswith("paper/deposit/data/t.csv has 1 line ")

    def test_the_authors_own_home_directory_is_caught(self):
        lines = local_path_warnings({"paper/code/a.py": b"open('/srv/me/x')\n"}, home="/srv/me")
        assert len(lines) == 1

    def test_binary_files_are_skipped(self):
        assert local_path_warnings({"paper/deposit/data/a.bin": b"\x00/home/alice/x"}) == []

    def test_render_warns_about_a_shipped_script(self, tmp_path):
        run_dir = _run(tmp_path)
        body = "OUT = '/home/alice/project/out.csv'\nprint(OUT)\n"
        _BODIES_PATCH = dict(_BODIES, **{"z_plot.py": body})
        (tmp_path / _DIR / "z_plot.py").write_text(body, encoding="utf-8")
        ev = run_dir / "evidence" / "evi-obs-plot.json"
        data = json.loads(ev.read_text(encoding="utf-8"))
        data["provenance"]["code_ref"] = (
            f"{_DIR}/z_plot.py sha256={_h(_BODIES_PATCH['z_plot.py'].encode())}")
        ev.write_text(json.dumps(data), encoding="utf-8")
        compiler = _render(run_dir)
        assert any(w.startswith("paper/code/z_plot.py has 1 line ")
                   for w in compiler.bundle_warnings), compiler.bundle_warnings

    def test_render_warns_about_shipped_data(self, tmp_path):
        run_dir = _run(tmp_path)
        _CLEAN_HOME = b"id,path\n1,/home/alice/x.csv\n"
        (tmp_path / _DIR / "out" / "clean.csv").write_bytes(_CLEAN_HOME)
        compiler = _render(run_dir)
        assert any(w.startswith("paper/deposit/data/clean.csv has 1 line ")
                   for w in compiler.bundle_warnings), compiler.bundle_warnings
