"""
End-to-end smoke for the workspace package layer (design/near-submission-package.md §C):
a tiny 2-run fixture workspace -> ``sci-adk package`` -> ``sci-adk verify <ws>`` reports
``package_requirements_clean`` green. Plus the assembler's structure + idempotence + no-new-
belief invariants, and the packaging lock that the three field-agnostic builders ship.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
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
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.render.package import PACKAGE_FOLDERS, assemble_package, discover_runs

_NON_CIRC = "the verifier checks a property not baked into the generator"


def _numeric_spec(spec_id: str, value: float = 0.9) -> Spec:
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id="hyp-n", statement="the encoder is injective on the tested set",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="point >= threshold => support",
                params={"statistic": "point", "op": ">=", "value": value},
            ),
            referent="formal", non_circularity=_NON_CIRC,
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-n")],
    )


def _numeric_experiment(point: float):
    def experiment(s, w):
        return [EvidenceItem(
            id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="abc123", data_source="generated"),
            result=Result(type="quantitative", point=point),
            bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
        )]
    return experiment


def _seed_two_run_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    for rid, val, pt in [("run-alpha", 0.9, 0.95), ("run-beta", 0.8, 0.85)]:
        run_checkpoint_loop(
            run_dir=ws / "runs" / rid, spec=_numeric_spec(rid, value=val),
            experiment=_numeric_experiment(pt), workspace_dir=ws,
        )
    return ws


# -- the headline smoke: package -> verify green -----------------------------

def test_cli_package_then_verify_reports_green(tmp_path, capsys):
    from sci_adk.cli import main

    ws = _seed_two_run_workspace(tmp_path)

    # freeze a contract, assemble + gate, then auto-detected verify <ws>.
    assert main(["pkgreqs", "freeze", str(ws), "--defaults", "--venue", "IEAM",
                 "--abstract-max-words", "300", "--reference-style", "plainnat"]) == 0
    assert main(["package", str(ws)]) == 0          # assemble + gate -> green

    capsys.readouterr()                              # clear
    rc = main(["verify", str(ws)])                   # auto-detect the package workspace
    assert rc == 0
    out = capsys.readouterr().out
    assert "package requirements: OK (declared requirements met)" in out
    assert "2/2 reproduce" in out


def test_cli_package_without_pkgreqs_refuses(tmp_path, capsys):
    # SPEC-PAPER-GATE-001 P1 (OD-1 strict + OD-8 immediate): `sci-adk package` with NO frozen
    # contract still ASSEMBLES the package, but the gate now REFUSES (exit non-zero) with a
    # loud, actionable message naming what to freeze -- the OLD "vacuously green" posture is
    # overturned (REQ-PG-103/108). Freezing a pkgreqs.json is now a completion step.
    from sci_adk.cli import main

    ws = _seed_two_run_workspace(tmp_path)
    rc = main(["package", str(ws)])
    assert rc != 0
    err = capsys.readouterr().err.lower()
    assert "pkgreqs" in err
    assert "frozen" in err or "freeze" in err


def test_cli_verify_workspace_without_package_is_clean(tmp_path):
    # A workspace with a frozen pkgreqs.json but no assembled package/: `verify <ws>` detects
    # the workspace (pkgreqs.json present) and reports nothing-to-gate (exit 0).
    from sci_adk.cli import main

    ws = _seed_two_run_workspace(tmp_path)
    assert main(["pkgreqs", "freeze", str(ws), "--defaults"]) == 0
    assert main(["verify", str(ws)]) == 0            # no package/ yet -> nothing to gate


# -- assembler structure + invariants ----------------------------------------

def test_assembler_lays_down_the_six_folders_and_index_files(tmp_path):
    ws = _seed_two_run_workspace(tmp_path)
    assembly = assemble_package(ws)
    pkg = assembly.package_dir
    for folder in PACKAGE_FOLDERS:
        assert (pkg / folder).is_dir(), f"missing folder {folder}"
    for f in ("MANIFEST.md", "README.md",
              "01_manuscript/main.tex", "01_manuscript/si.tex", "01_manuscript/references.bib",
              "02_data/claims_all.csv", "06_provenance/run_index.csv",
              "04_scripts/build_record_index.py", "04_scripts/make_si.py",
              "04_scripts/check_package.py", "05_inputs/README.md"):
        assert (pkg / f).is_file(), f"missing {f}"
    assert sorted(assembly.runs) == ["run-alpha", "run-beta"]
    assert assembly.main_tex_authored is False       # skeleton, not authored (Wave 1)


def test_assembler_is_idempotent(tmp_path):
    ws = _seed_two_run_workspace(tmp_path)
    assemble_package(ws)
    pkg = ws / "package"

    def snapshot() -> dict:
        return {
            p.relative_to(pkg).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in pkg.rglob("*") if p.is_file()
        }

    before = snapshot()
    assemble_package(ws)                             # re-run over the same record
    after = snapshot()
    assert before == after, "package assembly is not idempotent"


def test_assembler_readme_has_submission_readiness(tmp_path):
    ws = _seed_two_run_workspace(tmp_path)
    assemble_package(ws)
    readme = (ws / "package" / "README.md").read_text(encoding="utf-8")
    assert "Submission-readiness self-assessment" in readme


def test_assembler_preserves_an_author_supplied_main_tex(tmp_path):
    # An author manuscript dropped in <ws>/package_src/ is preserved verbatim (the Wave-2
    # writer's drop point); main_tex_authored flips True.
    ws = _seed_two_run_workspace(tmp_path)
    src = ws / "package_src"
    src.mkdir()
    authored = (
        r"\documentclass{article}\begin{document}"
        r"\begin{abstract}authored\end{abstract}\end{document}"
    )
    (src / "main.tex").write_text(authored, encoding="utf-8")
    assembly = assemble_package(ws)
    assert assembly.main_tex_authored is True
    assert (ws / "package" / "01_manuscript" / "main.tex").read_text(encoding="utf-8") == authored


def test_assembler_record_derived_no_new_belief(tmp_path):
    # The claims_all.csv statuses are copied verbatim from the recorded Claims (no new belief):
    # both runs recorded SUPPORTED, so the table carries 'supported' for each.
    ws = _seed_two_run_workspace(tmp_path)
    assemble_package(ws)
    csv_text = (ws / "package" / "02_data" / "claims_all.csv").read_text(encoding="utf-8")
    assert csv_text.count("supported") == 2          # one per run, verbatim from the record


def test_assembler_empty_workspace_raises(tmp_path):
    import pytest

    (tmp_path / "runs").mkdir()                       # runs/ but no run with spec.json
    with pytest.raises(ValueError):
        assemble_package(tmp_path)


def test_discover_runs_finds_only_spec_bearing_dirs(tmp_path):
    ws = _seed_two_run_workspace(tmp_path)
    (ws / "runs" / "not-a-run").mkdir()              # a stray dir with no spec.json
    assert discover_runs(ws) == ["run-alpha", "run-beta"]


# -- packaging lock: the three builders ship ---------------------------------

def test_package_builders_are_packaged():
    # The field-agnostic builders ride in the research-workspace kit (graft + package-data) so
    # the assembler can copy them into 04_scripts/ for both an editable install and a wheel.
    import importlib.resources

    root = (
        Path(str(importlib.resources.files("sci_adk")))
        / "templates" / "research-workspace" / "package" / "04_scripts"
    )
    for name in ("build_record_index.py", "make_si.py", "check_package.py"):
        assert (root / name).is_file(), f"packaged builder missing: {name}"
