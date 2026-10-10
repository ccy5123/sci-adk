"""
The reproduction bundle in ``paper/`` (F3): ``paper/code/`` + ``paper/reproduce.py``.

What a real run (lit-search-trial-2, SPEC-BCFKOW-001) exposed, rendered with the old
compiler:

  * ``paper/code/`` held 31 files for 14 distinct scripts -- one copy per Evidence item, so
    ``s3_build_chemicals.py`` shipped as seven identical files ``_1`` .. ``_6``;
  * a script named second in a ``code_ref`` (``s0_kow_columns.py`` after
    ``s3_build_chemicals.py``) was never copied;
  * ``reproduce.py`` promised to regenerate the results "FROM THE RECORD" but called the
    executor with no arguments and no input data, so every script stopped at once; and its
    comments carried internal evidence ids;
  * a re-render never removed the stale duplicates.

The fixed bundle: one copy per distinct script content, named by its own file name (a name
shared by different contents gets a hash suffix); every script a ``code_ref`` names is
shipped, its sha256 checked against the ``code_ref``; ``reproduce.py`` is a manifest and a
hash check that runs nothing; and a re-render removes the files the previous render wrote
that this one does not, never anything else. The scripts here are fixtures; the
``code_ref`` / ``data_ref`` / finding strings are the real run's shapes.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
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
from sci_adk.core.pubreqs import PubReqs
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.loop.code_ref import parse_code_ref_scripts, resolve_code_ref_scripts
from sci_adk.loop.compiler import ResearchCompiler, deposit_record_path
from sci_adk.loop.prior_work import record_prior_work_skip
from sci_adk.loop.verify import verify_run
from sci_adk.provenance import pubreqs_digest
from sci_adk.render.reproduction import reader_summary

_AT = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
_HYP = "H1"
_ANALYSIS = "analysis/SPEC-BCFKOW-001"
_NO_GIT = "no git commit (the workspace repository has no commits)"

# Fixture script bodies. s1 has CRLF line ends: the shipped copy must keep the exact bytes,
# or its hash no longer matches the code_ref.
_BODIES = {
    "s0_kow_columns.py": "print('kow columns')\n",
    "s1_select_records.py": "import sys\r\nprint('select', sys.argv)\r\n",
    "s2_fetch_comptox.py": "print('fetch')\n",
    "s3_build_chemicals.py": "print('build chemicals')\n",
    "s4_h1_fit.py": "print('fit')\n",
}
_DATA_REF = (
    "Arnot & Gobas 2006 SI (DOI 10.1139/a06-005), decrypted copy a06-005.decrypted.xls "
    "sha256 1081e637f6bd39f9ba86d0e005cf657ea054ad302fd57e5d2e8d6841fd95c461; CompTox "
    "QSAR-ready SMILES retrieved 2026-10-08"
)
_ID_AGG = "evi-obs-20261008-filter-approach5-6-logkow-aggregation"
_ID_VALUES_AGG = "evi-obs-20261009-values-approach5-6-logkow-aggregation"


def _sha(name: str) -> str:
    return hashlib.sha256(_BODIES[name].encode("utf-8")).hexdigest()


def _ref(*names: str) -> str:
    """The real shape: '<path> sha256=<hex>; <path> sha256=<hex>; no git commit (...)'."""
    parts = [f"{_ANALYSIS}/{n} sha256={_sha(n)}" for n in names]
    return "; ".join(parts) + f"; {_NO_GIT}"


def _fit_ref() -> str:
    """The real h1-primary-fit shape: the third script is named WITHOUT its directory."""
    return (
        f"{_ANALYSIS}/s4_h1_fit.py sha256={_sha('s4_h1_fit.py')} (input built by "
        f"{_ANALYSIS}/s1_select_records.py sha256={_sha('s1_select_records.py')} and "
        f"s3_build_chemicals.py sha256={_sha('s3_build_chemicals.py')}); {_NO_GIT}"
    )


def _write_scripts(workspace: Path) -> None:
    d = workspace / _ANALYSIS
    d.mkdir(parents=True, exist_ok=True)
    for name, body in _BODIES.items():
        (d / name).write_bytes(body.encode("utf-8"))


def _spec(spec_id: str) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="m", expected_output="o"
        ),
        hypotheses=[
            Hypothesis(
                id=_HYP,
                statement="the tested metric is zero on the designed set",
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="metric == 0 => support; > 0 => refute",
                    params={"statistic": "metric", "op": "==", "value": 0.0},
                ),
                referent="formal",
                non_circularity="the verifier checks a property the generator does not fix",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="the metric is zero", answers=_HYP)],
    )


def _obs(eid: str, code_ref: str, finding: str, data_ref: str = _DATA_REF) -> EvidenceItem:
    return EvidenceItem(
        id=eid,
        created_at=_AT,
        spec_id="",  # set by _seed
        kind=EvidenceKind.OBSERVATION,
        provenance=Provenance(code_ref=code_ref, data_ref=data_ref, data_source="measured"),
        result=Result(
            type="qualitative",
            finding=finding,
            artifact_ref=f"{_ANALYSIS}/out/s3_counts.json",
        ),
        bears_on=[],
    )


def _trial_evidence() -> list[EvidenceItem]:
    """Seven items in the real run's code_ref shapes: s3 named by five of them."""
    fit = EvidenceItem(
        id="evi-run-20261008-h1-primary-fit",
        created_at=_AT,
        spec_id="",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref=_fit_ref(), data_ref=_DATA_REF, data_source="generated"),
        result=Result(
            type="quantitative",
            point=0.0,
            finding=(
                "H1 primary fit (approach [7]). H1 analysis set: the 404 chemicals passing "
                "approaches [1]-[6] restricted to measured log Kow in [1, 6] inclusive."
            ),
            artifact_ref=f"{_ANALYSIS}/out/s4_h1_fit.json",
        ),
        bears_on=[Bearing(target_id=_HYP, direction=BearingDirection.SUPPORTS)],
    )
    return [
        _obs(
            "evi-obs-20261008-filter-approach2-structure",
            _ref("s2_fetch_comptox.py", "s3_build_chemicals.py"),
            "Approach [2] chemical structure. The data set provides no SMILES, so each "
            "chemical's CAS RN was resolved to the QSAR-ready SMILES of the US EPA CompTox "
            "Chemicals Dashboard.",
        ),
        _obs(
            "evi-obs-20261008-filter-approach3-organic",
            _ref("s3_build_chemicals.py"),
            "Approach [3] organic-structure filter, applied with RDKit 2025.09.4 to the "
            "CompTox QSAR-ready SMILES.",
        ),
        _obs(
            "evi-obs-20261008-filter-approach4-neutral",
            _ref("s3_build_chemicals.py"),
            "Approach [4] neutral-chemical filter on the QSAR-ready SMILES as given.",
            # The real run's data_refs also point at other record entries by id.
            data_ref=(
                "input data/raw/arnot-gobas-2006/a06-005.decrypted.xls (decrypted from "
                "a06-005.xls; see evi-obs-20261008-filter-approach2-structure)"
            ),
        ),
        _obs(
            _ID_AGG,
            _ref("s3_build_chemicals.py", "s0_kow_columns.py"),
            "Approach [5] measured log Kow and approach [6] aggregation. Which data-set "
            "columns are measured: the SI has five log Kow columns.",
        ),
        _obs(
            _ID_VALUES_AGG,
            _ref("s3_build_chemicals.py", "s0_kow_columns.py"),
            '{"summary": "Named values for ' + _ID_AGG + ', read from s3_counts.json: '
            'chemicals whose measured log Kow came from the database.", '
            '"final_chemicals": 404}',
        ),
        fit,
        EvidenceItem(
            id="evi-pw-decision-20261008-100739-df0f7348",
            created_at=_AT,
            spec_id="",
            kind=EvidenceKind.PRIOR_WORK_DECISION,
            provenance=Provenance(code_ref="prior_work:searched"),
            result=Result(type="qualitative", finding="searched: DOIs=['10.1139/f79-146']"),
            bears_on=[],
        ),
    ]


def _seed(workspace: Path, spec_id: str, evidence: list[EvidenceItem]) -> Path:
    spec = _spec(spec_id)
    items = [ev.model_copy(update={"spec_id": spec.id}) for ev in evidence]
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_init_spec(spec=spec)
    compiler.stage_execute(spec, experiment=lambda _s, _w: items)
    compiler.stage_derive_claim(spec)
    return workspace / "runs" / spec_id


def _render(workspace: Path, run_dir: Path) -> ResearchCompiler:
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_render(spec)
    return compiler


def _trial(tmp_path: Path, spec_id: str = "rb-trial") -> Path:
    _write_scripts(tmp_path)
    run_dir = _seed(tmp_path, spec_id, _trial_evidence())
    _render(tmp_path, run_dir)
    return run_dir


def _run_reproduce(run_dir: Path) -> subprocess.CompletedProcess:
    paper = run_dir / "paper"
    return subprocess.run(
        [sys.executable, "-I", str(paper / "reproduce.py")],
        cwd=str(paper), capture_output=True, text=True, timeout=60,
    )


def _evidence_ids() -> list[str]:
    return [ev.id for ev in _trial_evidence()]


def _freeze_bundle_contract(run_dir: Path) -> None:
    pr = PubReqs(
        spec_id=run_dir.name, required_sections=[], figure_font_policy=False,
        image_min_dpi=None, reference_style=None, max_words=None,
        reproduction_bundle=True,
    )
    pr = pr.model_copy(update={"digest": pubreqs_digest(pr)})
    (run_dir / "pubreqs.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    record_prior_work_skip(spec, run_dir.parent.parent, reason="not under test here")


# -- reading every script a code_ref names ----------------------------------------------


def test_parse_lists_every_script_a_multi_script_code_ref_names():
    assert parse_code_ref_scripts(_ref("s3_build_chemicals.py", "s0_kow_columns.py")) == [
        (f"{_ANALYSIS}/s3_build_chemicals.py", _sha("s3_build_chemicals.py")),
        (f"{_ANALYSIS}/s0_kow_columns.py", _sha("s0_kow_columns.py")),
    ]


def test_parse_follows_hashed_scripts_inside_free_text():
    assert parse_code_ref_scripts(_fit_ref()) == [
        (f"{_ANALYSIS}/s4_h1_fit.py", _sha("s4_h1_fit.py")),
        (f"{_ANALYSIS}/s1_select_records.py", _sha("s1_select_records.py")),
        ("s3_build_chemicals.py", _sha("s3_build_chemicals.py")),
    ]


def test_parse_a_wrapped_leading_path_is_listed_once():
    h = "c" * 64
    assert parse_code_ref_scripts(f"(code/run.py sha256={h}) by hand") == [("code/run.py", h)]


def test_parse_does_not_follow_unhashed_words_after_the_leading_path():
    assert parse_code_ref_scripts("code/run.py then helper.py; no git commit") == [
        ("code/run.py", None)
    ]


def test_parse_bare_commit_and_empty():
    commit = "6800c510f53eb912fcc1a459059d9ac633db2d11"
    assert parse_code_ref_scripts(commit) == [(commit, None)]
    assert parse_code_ref_scripts("  ") == []


def test_resolve_finds_a_bare_name_beside_the_leading_script_when_its_hash_matches(tmp_path):
    _write_scripts(tmp_path)
    named = resolve_code_ref_scripts(_fit_ref(), tmp_path / "runs" / "r", tmp_path)
    assert [n.resolution.script for n in named] == [
        tmp_path / _ANALYSIS / "s4_h1_fit.py",
        tmp_path / _ANALYSIS / "s1_select_records.py",
        tmp_path / _ANALYSIS / "s3_build_chemicals.py",
    ]
    assert not any(n.resolution.hash_mismatch for n in named)


def test_resolve_a_bare_name_beside_the_script_with_another_hash_is_not_that_file(tmp_path):
    _write_scripts(tmp_path)
    ref = (
        f"{_ANALYSIS}/s4_h1_fit.py sha256={_sha('s4_h1_fit.py')} (input built by "
        f"s3_build_chemicals.py sha256={'0' * 64})"
    )
    named = resolve_code_ref_scripts(ref, tmp_path / "runs" / "r", tmp_path)
    assert named[1].path == "s3_build_chemicals.py"
    assert named[1].resolution.script is None
    # A guessed location is not the named file, so it is not reported as a changed file.
    assert not named[1].resolution.hash_mismatch


# -- paper/code: one copy per distinct script, every named script shipped ----------------


def test_each_distinct_script_is_shipped_once_under_its_own_name(tmp_path):
    run_dir = _trial(tmp_path)
    code = run_dir / "paper" / "code"
    assert sorted(p.name for p in code.iterdir()) == sorted(_BODIES)


def test_shipped_copies_are_byte_identical_to_the_recorded_scripts(tmp_path):
    run_dir = _trial(tmp_path)
    code = run_dir / "paper" / "code"
    for name, body in _BODIES.items():
        assert (code / name).read_bytes() == body.encode("utf-8"), name
        assert hashlib.sha256((code / name).read_bytes()).hexdigest() == _sha(name)


def test_a_name_shared_by_different_contents_gets_a_deterministic_hash_suffix(tmp_path):
    a, b = "print('a')\n", "print('b')\n"
    for sub, body in (("a", a), ("b", b)):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "run.py").write_text(body, encoding="utf-8")
    ha = hashlib.sha256(a.encode()).hexdigest()
    hb = hashlib.sha256(b.encode()).hexdigest()
    evidence = [
        _obs("ev-b", f"b/run.py sha256={hb}", "Second variant."),
        _obs("ev-a", f"a/run.py sha256={ha}", "First variant."),
    ]
    fit = _trial_evidence()[5].model_copy(
        update={"provenance": Provenance(code_ref="a/run.py", data_source="generated")}
    )
    run_dir = _seed(tmp_path, "rb-collide", evidence + [fit])
    _render(tmp_path, run_dir)
    names = sorted(p.name for p in (run_dir / "paper" / "code").iterdir())
    assert names == sorted([f"run_{ha[:8]}.py", f"run_{hb[:8]}.py"])
    first = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    _render(tmp_path, run_dir)
    assert (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8") == first


def test_record_inlines_each_distinct_script_once(tmp_path):
    run_dir = _trial(tmp_path)
    record = deposit_record_path(run_dir).read_text(encoding="utf-8")
    assert record.count(r"\begin{lstlisting}") == len(_BODIES)
    assert record.count("print('build chemicals')") == 1
    # The record (the exempt dump) names which recorded items each script backs.
    assert "evi-obs-20261008-filter-approach3-organic" in record


def test_decision_records_are_not_reproduction_entries(tmp_path):
    run_dir = _trial(tmp_path)
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    assert "prior_work:searched" not in driver
    assert "prior_work:searched" not in deposit_record_path(run_dir).read_text(encoding="utf-8")


# -- reproduce.py: a manifest and a hash check that runs nothing --------------------------


def test_reproduce_runs_nothing_and_says_so(tmp_path):
    run_dir = _trial(tmp_path)
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    compile(driver, "reproduce.py", "exec")
    for forbidden in ("sci_adk", "DockerExecutor", "execute_python", "subprocess",
                      "exec(", "runpy", "os.system"):
        assert forbidden not in driver, forbidden
    doc = ast.get_docstring(ast.parse(driver)) or ""
    assert "runs none of" in doc
    assert "arguments" in doc and "input" in doc
    assert "FROM THE RECORD" not in driver
    assert "regenerat" not in driver.lower()


def test_reproduce_exits_zero_and_reports_every_hash_ok(tmp_path):
    run_dir = _trial(tmp_path)
    proc = _run_reproduce(run_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in _BODIES:
        line = next(ln for ln in proc.stdout.splitlines() if f"code/{name}" in ln)
        assert line.rstrip().endswith("ok"), line
    assert f"{len(_BODIES)} of {len(_BODIES)} scripts match" in proc.stdout


def test_reproduce_fails_on_a_changed_or_missing_shipped_script(tmp_path):
    run_dir = _trial(tmp_path)
    code = run_dir / "paper" / "code"
    (code / "s3_build_chemicals.py").write_text("print('edited')\n", encoding="utf-8")
    proc = _run_reproduce(run_dir)
    assert proc.returncode == 1
    assert any("s3_build_chemicals.py" in ln and "DIFFERS" in ln
               for ln in proc.stdout.splitlines())
    (code / "s0_kow_columns.py").rename(code.parent / "moved-aside.py")
    proc = _run_reproduce(run_dir)
    assert proc.returncode == 1
    assert any("s0_kow_columns.py" in ln and "MISSING" in ln for ln in proc.stdout.splitlines())


def test_reproduce_lists_what_each_script_backs_and_the_data_it_names(tmp_path):
    run_dir = _trial(tmp_path)
    out = _run_reproduce(run_dir).stdout
    s3 = out.split("code/s3_build_chemicals.py", 1)[1].split("code/", 1)[0]
    # Named by six items: four lead with it, one names it second, one by bare file name.
    assert "6 recorded results" in s3
    assert "Organic-structure filter, applied with RDKit" in s3
    assert "a06-005.decrypted.xls" in s3              # the data the results name
    assert f"{_ANALYSIS}/out/s3_counts.json" in s3   # the output they record
    s0 = out.split("code/s0_kow_columns.py", 1)[1].split("code/", 1)[0]
    assert "2 recorded results" in s0


def test_reader_facing_text_carries_no_record_ids(tmp_path):
    run_dir = _trial(tmp_path)
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    out = _run_reproduce(run_dir).stdout
    doc = ast.get_docstring(ast.parse(driver)) or ""
    comments = [ln for ln in driver.splitlines() if ln.lstrip().startswith("#")]
    for eid in _evidence_ids():
        assert eid not in out, eid
        assert eid not in doc, eid
        assert not any(eid in c for c in comments), eid
    # The ids live in the machine section only, which the gate and tools read.
    machine = driver.split("Machine section", 1)[1]
    assert "evi-obs-20261008-filter-approach3-organic" in machine
    for ev in _trial_evidence()[:-1]:
        assert repr(ev.provenance.code_ref) in machine


def test_reader_summary_takes_the_first_sentence_and_drops_record_ids():
    assert reader_summary(
        "Approach [4] neutral-chemical filter on the QSAR-ready SMILES as given. More.",
    ) == "Neutral-chemical filter on the QSAR-ready SMILES as given."
    summary = reader_summary(
        '{"summary": "Named values for ' + _ID_AGG + ', read from s3_counts.json.", "n": 4}',
        known_ids=[_ID_AGG],
    )
    assert _ID_AGG not in summary
    assert summary == "Named values, read from s3_counts.json."
    assert reader_summary("", fallback="an observation") == "an observation"
    assert len(reader_summary("word " * 100)) <= 160


def test_a_script_recorded_without_a_hash_is_checked_against_its_rendered_hash(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "encode.py").write_text("print('encode')\n", encoding="utf-8")
    fit = _trial_evidence()[5].model_copy(
        update={"provenance": Provenance(code_ref="code/encode.py", data_source="generated")}
    )
    run_dir = _seed(tmp_path, "rb-nohash", [fit])
    _render(tmp_path, run_dir)
    proc = _run_reproduce(run_dir)
    assert proc.returncode == 0, proc.stdout
    line = next(ln for ln in proc.stdout.splitlines() if "code/encode.py" in ln)
    assert "computed when this bundle was rendered" in line
    assert line.rstrip().endswith("ok")


def test_pointer_only_bundle_checks_nothing_and_exits_zero(tmp_path):
    fit = _trial_evidence()[5].model_copy(
        update={"provenance": Provenance(
            code_ref="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4", data_source="generated"
        )}
    )
    run_dir = _seed(tmp_path, "rb-pointer", [fit])
    _render(tmp_path, run_dir)
    assert not (run_dir / "paper" / "code").exists()
    proc = _run_reproduce(run_dir)
    assert proc.returncode == 0
    assert "No script is shipped" in proc.stdout
    assert "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4" in proc.stdout


# -- re-render removes the stale files it owns, and nothing else -------------------------


def test_rerender_removes_stale_duplicates_from_an_old_render_only(tmp_path):
    run_dir = _trial(tmp_path)
    code = run_dir / "paper" / "code"
    # What the OLD compiler left: one numbered copy per Evidence item, listed in the old
    # driver's SCRIPTS = [(evidence_id, code_ref, filename), ...].
    old_names = ["s3_build_chemicals.py"] + [f"s3_build_chemicals_{i}.py" for i in range(1, 7)]
    for n in old_names:
        (code / n).write_text(_BODIES["s3_build_chemicals.py"], encoding="utf-8")
    old_driver = '"""Auto-emitted by sci-adk (design/paper-publishing-requirements.md F3)."""\n'
    old_driver += "SCRIPTS = [\n" + "".join(
        f"    ('ev-{i}', 'code_ref {i}', {n!r}),\n" for i, n in enumerate(old_names)
    ) + "]\nPOINTERS = []\n"
    (run_dir / "paper" / "reproduce.py").write_text(old_driver, encoding="utf-8")
    (code / "notes.txt").write_text("the author's own file\n", encoding="utf-8")

    _render(tmp_path, run_dir)
    assert sorted(p.name for p in code.iterdir()) == sorted([*_BODIES, "notes.txt"])


def test_rerender_removes_a_file_its_previous_render_wrote_that_is_no_longer_named(tmp_path):
    run_dir = _trial(tmp_path)
    code = run_dir / "paper" / "code"
    # The previous (new-format) render listed a file this render no longer ships.
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    driver = driver.replace(
        "SCRIPTS = [\n", "SCRIPTS = [\n    ('old_helper.py', '" + "f" * 64 + "', True),\n", 1
    )
    (run_dir / "paper" / "reproduce.py").write_text(driver, encoding="utf-8")
    (code / "old_helper.py").write_text("print('old')\n", encoding="utf-8")
    _render(tmp_path, run_dir)
    assert not (code / "old_helper.py").exists()
    assert sorted(p.name for p in code.iterdir()) == sorted(_BODIES)


def test_rerender_never_follows_a_listed_name_outside_paper_code(tmp_path):
    run_dir = _trial(tmp_path)
    outside = run_dir / "paper" / "draft.tex"
    assert outside.is_file()
    (run_dir / "paper" / "reproduce.py").write_text(
        '"""Auto-emitted by sci-adk."""\n'
        "SCRIPTS = [('ev', 'ref', '../draft.tex')]\nPOINTERS = []\n", encoding="utf-8"
    )
    _render(tmp_path, run_dir)
    assert outside.is_file()


# -- verify: the F3 gate checks the shipped copies against the recorded hashes -----------


def test_verify_passes_a_rendered_multi_script_bundle(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    report = verify_run(run_dir)
    assert report.paper_requirements_problems == []
    assert report.passed is True


def test_verify_fails_when_a_shipped_copy_differs_from_the_recorded_hash(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    (run_dir / "paper" / "code" / "s0_kow_columns.py").write_text("x = 1\n", encoding="utf-8")
    report = verify_run(run_dir)
    assert report.passed is False
    lines = [p for p in report.paper_requirements_problems if "s0_kow_columns.py" in p]
    assert len(lines) == 1
    assert lines[0].startswith("reproduction bundle: paper/code/ holds no copy of")
    assert _sha("s0_kow_columns.py") in lines[0]
    assert lines[0].endswith("re-run sci-adk render to refresh paper/")


def test_verify_fails_when_a_second_named_script_changed_in_the_workspace(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    (tmp_path / _ANALYSIS / "s0_kow_columns.py").write_text("x = 2\n", encoding="utf-8")
    report = verify_run(run_dir)
    assert report.passed is False
    mismatch = [p for p in report.paper_requirements_problems
                if "s0_kow_columns.py" in p and "now hashes to" in p]
    assert {_ID_AGG, _ID_VALUES_AGG} == {
        eid for eid in (_ID_AGG, _ID_VALUES_AGG) if any(eid in p for p in mismatch)
    }


def test_verify_fails_an_old_render_that_did_not_ship_a_second_named_script(tmp_path):
    run_dir = _trial(tmp_path)
    _freeze_bundle_contract(run_dir)
    (run_dir / "paper" / "code" / "s0_kow_columns.py").rename(tmp_path / "aside.py")
    report = verify_run(run_dir)
    assert report.passed is False
    assert any("holds no copy of" in p and "s0_kow_columns.py" in p
               for p in report.paper_requirements_problems)
