"""
How a recorded ``provenance.code_ref`` becomes (or does not become) runnable code in the F3
reproduction bundle.

A real run's experimentalist recorded code_refs like::

    analysis/SPEC-BCFKOW-001/s6_h2_rho.py sha256=<64 hex> (sample from
    analysis/SPEC-BCFKOW-001/s5_h2_sample.py sha256=<64 hex>); no git commit (...)

The compiler resolved the WHOLE string as a path, so every item became a POINTER, the
rendered ``paper/reproduce.py`` drove nothing, and the F3 gate passed by design (a
pointer-only bundle is fail-open). The fixed reading: a leading path token, optionally
followed by ``sha256=<64 hex>``, plus every later path followed by its own hash (see
test_reproduction_bundle.py); other free text is ignored. A matching hash ships the script;
a mismatching one is not shipped and is reported (render warning; F3 FAIL when the contract
declares the bundle). A bare commit or an unresolvable token stays a pointer. verify adds a
non-gating advisory when every code_ref of a rendered bundle is a pointer.

The scripts here are fixtures, so the hashes are computed from their content; the string
SHAPE is the real one (the real hashes are exercised end to end on a copy of the run).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sci_adk.cli import main
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
from sci_adk.loop.code_ref import parse_code_ref, resolve_code_ref
from sci_adk.loop.compiler import ResearchCompiler, deposit_record_path
from sci_adk.loop.prior_work import record_prior_work_skip
from sci_adk.loop.verify import verify_run
from sci_adk.provenance import pubreqs_digest

_AT = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
_HYP = "hyp-c"
_EV = "evi-run-0001"
_ANALYSIS = "analysis/SPEC-BCFKOW-001"
_S6 = "print('rho')\n"
_S5 = "print('sample')\n"
_NO_GIT = "no git commit (the workspace repository has no commits)"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _real_world_ref(h6: str, h5: str) -> str:
    return (
        f"{_ANALYSIS}/s6_h2_rho.py sha256={h6} (sample from {_ANALYSIS}/s5_h2_sample.py "
        f"sha256={h5}); {_NO_GIT}"
    )


def _write_scripts(workspace: Path) -> None:
    d = workspace / _ANALYSIS
    d.mkdir(parents=True, exist_ok=True)
    (d / "s6_h2_rho.py").write_text(_S6, encoding="utf-8")
    (d / "s5_h2_sample.py").write_text(_S5, encoding="utf-8")


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


def _seed(workspace: Path, spec_id: str, code_ref: str) -> Path:
    """Freeze the Spec, record one Evidence item carrying ``code_ref``, derive the Claim."""
    spec = _spec(spec_id)
    item = EvidenceItem(
        id=_EV,
        created_at=_AT,
        spec_id=spec.id,
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref=code_ref, data_source="generated"),
        result=Result(type="quantitative", point=0.0, finding="metric=0"),
        bears_on=[Bearing(target_id=_HYP, direction=BearingDirection.SUPPORTS)],
    )
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_init_spec(spec=spec)
    compiler.stage_execute(spec, experiment=lambda _s, _w: [item])
    compiler.stage_derive_claim(spec)
    return workspace / "runs" / spec_id


def _render(workspace: Path, run_dir: Path) -> ResearchCompiler:
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_render(spec)
    return compiler


def _freeze_bundle_contract(run_dir: Path) -> None:
    """A contract that declares ONLY the reproduction bundle, plus a recorded prior-work
    decision, so the bundle is the one publishing requirement under test."""
    pr = PubReqs(
        spec_id=run_dir.name, required_sections=[], figure_font_policy=False,
        image_min_dpi=None, reference_style=None, max_words=None,
        reproduction_bundle=True,
    )
    pr = pr.model_copy(update={"digest": pubreqs_digest(pr)})
    (run_dir / "pubreqs.json").write_text(pr.model_dump_json(indent=2), encoding="utf-8")
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    record_prior_work_skip(spec, run_dir.parent.parent, reason="not under test here")


def _pointer_advisories(report) -> list[str]:
    return [
        n for n in report.paper_advisory
        if n.startswith("the reproduction bundle ships no script")
    ]


# -- parsing (pure) -------------------------------------------------------------------


def test_parse_real_world_code_ref_takes_leading_path_and_its_hash():
    h6, h5 = "a" * 64, "b" * 64
    assert parse_code_ref(_real_world_ref(h6, h5)) == (f"{_ANALYSIS}/s6_h2_rho.py", h6)


def test_parse_hash_followed_by_semicolon():
    h = "c" * 64
    ref = f"{_ANALYSIS}/s9_negative_controls.py sha256={h}; {_NO_GIT}"
    assert parse_code_ref(ref) == (f"{_ANALYSIS}/s9_negative_controls.py", h)


def test_parse_path_followed_by_semicolon_and_no_hash():
    assert parse_code_ref(f"{_ANALYSIS}/s1.py; {_NO_GIT}") == (f"{_ANALYSIS}/s1.py", None)


def test_parse_uppercase_hash_is_normalized():
    assert parse_code_ref("x.py sha256=" + "AB" * 32) == ("x.py", "ab" * 32)


@pytest.mark.parametrize(
    "ref",
    [
        "x.py sha256=" + "a" * 65,          # too long: not a sha256
        "x.py sha256=" + "a" * 63,          # too short
        "x.py (built by y.py sha256=" + "a" * 64 + ")",  # the hash belongs to y.py
    ],
)
def test_parse_ignores_a_hash_that_is_not_the_paths_own(ref):
    assert parse_code_ref(ref) == ("x.py", None)


def test_parse_bare_commit_and_empty():
    commit = "6800c510f53eb912fcc1a459059d9ac633db2d11"
    assert parse_code_ref(commit) == (commit, None)
    assert parse_code_ref("   ") == ("", None)


# -- resolution against the filesystem ------------------------------------------------


def test_resolve_matching_hash_is_the_script(tmp_path):
    _write_scripts(tmp_path)
    res = resolve_code_ref(_real_world_ref(_sha(_S6), _sha(_S5)), tmp_path / "runs" / "r", tmp_path)
    assert res.script == tmp_path / _ANALYSIS / "s6_h2_rho.py"
    assert not res.hash_mismatch


def test_resolve_mismatching_hash_is_a_pointer_with_both_hashes(tmp_path):
    _write_scripts(tmp_path)
    stale = _sha("print('an older version')\n")
    res = resolve_code_ref(_real_world_ref(stale, _sha(_S5)), tmp_path / "runs" / "r", tmp_path)
    assert res.script is None
    assert res.hash_mismatch
    assert res.expected_sha256 == stale
    assert res.actual_sha256 == _sha(_S6)
    assert res.named_path == f"{_ANALYSIS}/s6_h2_rho.py"


def test_resolve_path_without_hash_followed_by_free_text_is_the_script(tmp_path):
    _write_scripts(tmp_path)
    res = resolve_code_ref(f"{_ANALYSIS}/s6_h2_rho.py; {_NO_GIT}", tmp_path / "runs" / "r", tmp_path)
    assert res.script == tmp_path / _ANALYSIS / "s6_h2_rho.py"


def test_resolve_whole_string_path_with_spaces_still_works(tmp_path):
    script = tmp_path / "my scripts" / "run.py"
    script.parent.mkdir(parents=True)
    script.write_text("print(1)\n", encoding="utf-8")
    res = resolve_code_ref("my scripts/run.py", tmp_path / "runs" / "r", tmp_path)
    assert res.script == script


def test_resolve_bare_commit_with_free_text_is_a_pointer(tmp_path):
    res = resolve_code_ref(
        "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4 (the t1 run)", tmp_path / "runs" / "r", tmp_path
    )
    assert res.script is None
    assert not res.hash_mismatch


def test_resolve_long_free_text_is_a_pointer_not_an_error(tmp_path):
    # One path component longer than the filesystem's name limit used to raise OSError
    # (ENAMETOOLONG) out of Path.is_file() and crash the render.
    res = resolve_code_ref("x" * 400, tmp_path / "runs" / "r", tmp_path)
    assert res.script is None


# -- the rendered bundle --------------------------------------------------------------


def test_real_world_code_ref_ships_every_script_it_names(tmp_path):
    _write_scripts(tmp_path)
    ref = _real_world_ref(_sha(_S6), _sha(_S5))
    run_dir = _seed(tmp_path, "rep-ship", ref)
    compiler = _render(tmp_path, run_dir)

    code_dir = run_dir / "paper" / "code"
    assert (code_dir / "s6_h2_rho.py").read_text(encoding="utf-8") == _S6
    # The second script, named with its hash in the free text, is shipped too.
    assert (code_dir / "s5_h2_sample.py").read_text(encoding="utf-8") == _S5
    assert sorted(p.name for p in code_dir.iterdir()) == ["s5_h2_sample.py", "s6_h2_rho.py"]
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    scripts_block = driver.split("SCRIPTS = [", 1)[1].split("]", 1)[0]
    assert "s6_h2_rho.py" in scripts_block and "s5_h2_sample.py" in scripts_block
    assert repr(ref) in driver  # the full recorded code_ref, embedded verbatim
    compile(driver, "reproduce.py", "exec")
    assert _S6.strip() in deposit_record_path(run_dir).read_text(encoding="utf-8")
    assert compiler.code_ref_warnings == []


def test_hash_mismatch_is_not_shipped_and_is_warned(tmp_path, capsys):
    _write_scripts(tmp_path)
    stale = _sha("print('an older version')\n")
    ref = _real_world_ref(stale, _sha(_S5))
    run_dir = _seed(tmp_path, "rep-mismatch", ref)

    assert main(["render", str(run_dir)]) == 0
    err = capsys.readouterr().err
    # The changed script is not shipped; the matching second script is.
    assert sorted(p.name for p in (run_dir / "paper" / "code").iterdir()) == ["s5_h2_sample.py"]
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    results_block = driver.split("RESULTS = [", 1)[1]
    assert repr(ref) in results_block
    # ...and the bundle lists it as named but not held.
    assert repr((f"{_ANALYSIS}/s6_h2_rho.py",)) in results_block
    assert _EV in err
    assert stale in err
    assert _sha(_S6) in err


def test_render_survives_a_long_free_text_code_ref(tmp_path):
    ref = "ran the fit by hand " + "x" * 300 + " then re-checked"
    run_dir = _seed(tmp_path, "rep-long", ref)
    _render(tmp_path, run_dir)
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    assert repr(ref) in driver.split("RESULTS = [", 1)[1]
    assert "SCRIPTS = [\n]" in driver


def test_bare_commit_stays_a_pointer(tmp_path):
    commit = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"
    run_dir = _seed(tmp_path, "rep-commit", commit)
    compiler = _render(tmp_path, run_dir)
    assert not (run_dir / "paper" / "code").exists()
    driver = (run_dir / "paper" / "reproduce.py").read_text(encoding="utf-8")
    assert repr(commit) in driver.split("RESULTS = [", 1)[1]
    assert "SCRIPTS = [\n]" in driver
    assert compiler.code_ref_warnings == []


# -- verify: the F3 gate and the pointer-only advisory -------------------------------


def test_verify_f3_fails_on_a_hash_mismatch(tmp_path):
    _write_scripts(tmp_path)
    stale = _sha("print('an older version')\n")
    run_dir = _seed(tmp_path, "rep-gate", _real_world_ref(stale, _sha(_S5)))
    _render(tmp_path, run_dir)
    _freeze_bundle_contract(run_dir)

    report = verify_run(run_dir)
    assert report.all_reproduced is True
    assert report.paper_requirements_clean is False
    assert report.passed is False
    lines = [p for p in report.paper_requirements_problems if _EV in p]
    assert len(lines) == 1
    assert stale in lines[0] and _sha(_S6) in lines[0]
    assert lines[0].startswith("reproduction bundle:")


def test_verify_f3_fails_when_the_script_changes_after_render(tmp_path):
    _write_scripts(tmp_path)
    run_dir = _seed(tmp_path, "rep-drift", _real_world_ref(_sha(_S6), _sha(_S5)))
    _render(tmp_path, run_dir)
    _freeze_bundle_contract(run_dir)
    assert verify_run(run_dir).passed is True

    (tmp_path / _ANALYSIS / "s6_h2_rho.py").write_text("print('edited')\n", encoding="utf-8")
    report = verify_run(run_dir)
    assert report.passed is False
    assert any(_EV in p and "sha256" in p for p in report.paper_requirements_problems)


def test_verify_matching_scripts_pass_with_no_pointer_advisory(tmp_path):
    _write_scripts(tmp_path)
    run_dir = _seed(tmp_path, "rep-clean", _real_world_ref(_sha(_S6), _sha(_S5)))
    _render(tmp_path, run_dir)
    _freeze_bundle_contract(run_dir)

    report = verify_run(run_dir)
    assert report.paper_requirements_clean is True
    assert report.passed is True
    assert _pointer_advisories(report) == []


def test_verify_all_pointer_bundle_is_advised_not_gated(tmp_path):
    run_dir = _seed(tmp_path, "rep-pointers", "fixture")
    _render(tmp_path, run_dir)
    _freeze_bundle_contract(run_dir)  # adds a prior-work decision: not generating code

    report = verify_run(run_dir)
    assert report.passed is True  # fail-open for a genuine pointer, as before
    advisories = _pointer_advisories(report)
    assert len(advisories) == 1
    assert advisories[0].startswith(
        "the reproduction bundle ships no script: all 1 code_refs are pointers"
    )


def test_verify_no_pointer_advisory_without_a_rendered_bundle(tmp_path):
    run_dir = _seed(tmp_path, "rep-deposit", "fixture")
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    ResearchCompiler(workspace_dir=tmp_path).stage_render_record(spec)
    assert not (run_dir / "paper").exists()
    assert _pointer_advisories(verify_run(run_dir)) == []


def test_cli_verify_prints_the_pointer_advisory(tmp_path, capsys):
    run_dir = _seed(tmp_path, "rep-cli", "fixture")
    _render(tmp_path, run_dir)
    _freeze_bundle_contract(run_dir)
    capsys.readouterr()
    assert main(["verify", str(run_dir)]) == 0
    assert "the reproduction bundle ships no script: all 1 code_refs are pointers" in (
        capsys.readouterr().out
    )
