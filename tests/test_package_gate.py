"""
The workspace PACKAGE gate -- ``verify_package`` / ``package_requirements_clean``
(design/near-submission-package.md §3).

Builds a tiny 2-run fixture workspace, assembles the package, and asserts the umbrella gate is
green; then drives EACH deterministic fail mode (missing folder, unresolved cite, tool-vocab
leak in main.tex, missing required section, abstract over limit, a run that does not reproduce,
a residual fact macro, a missing traceability table) and the two vacuity cases (no package/ ->
vacuously clean; package but no pkgreqs.json -> the venue-format checks vacuous, the
layout/traceability checks still run). READ-ONLY, deterministic, no LLM.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.pkgreqs import DEFAULT_REQUIRED_SECTIONS, PackageReqs
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
from sci_adk.loop.verify import PackageVerifyReport, verify_package
from sci_adk.provenance import pkgreqs_digest
from sci_adk.render.package import assemble_package

_NON_CIRC = "the verifier checks a property not baked into the generator"


# -- fixture builders --------------------------------------------------------

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


def _seed_workspace(tmp_path: Path) -> Path:
    """A 2-run workspace, each run verify-green (a supported numeric claim)."""
    ws = tmp_path / "ws"
    for rid, val, pt in [("run-alpha", 0.9, 0.95), ("run-beta", 0.8, 0.85)]:
        run_checkpoint_loop(
            run_dir=ws / "runs" / rid, spec=_numeric_spec(rid, value=val),
            experiment=_numeric_experiment(pt), workspace_dir=ws,
        )
    return ws


def _freeze_pkgreqs(ws: Path, **kw) -> None:
    sections = kw.pop("required_sections", list(DEFAULT_REQUIRED_SECTIONS))
    pr = PackageReqs(required_sections=sections, **kw)
    frozen = pr.model_copy(update={"digest": pkgreqs_digest(pr)})
    (ws / "pkgreqs.json").write_text(frozen.model_dump_json(indent=2), encoding="utf-8")


def _assembled(tmp_path: Path, *, freeze=True, **freeze_kw) -> Path:
    ws = _seed_workspace(tmp_path)
    pkgreqs = None
    if freeze:
        _freeze_pkgreqs(ws, **freeze_kw)
        pkgreqs = PackageReqs.model_validate(
            json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
        )
    assemble_package(ws, pkgreqs)
    return ws


def _main_tex(ws: Path) -> Path:
    return ws / "package" / "01_manuscript" / "main.tex"


# -- (1) the pass case -------------------------------------------------------

def test_package_gate_passes_for_a_clean_assembled_package(tmp_path):
    ws = _assembled(tmp_path, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    report = verify_package(ws)
    assert isinstance(report, PackageVerifyReport)
    assert report.package_requirements_clean is True
    assert report.package_requirements_problems == []
    assert report.passed is True
    assert sorted(report.runs) == ["run-alpha", "run-beta"]
    assert all(report.runs_reproduced.values())


# -- (2) vacuity / backward compatibility ------------------------------------

def test_package_gate_no_package_is_vacuously_clean(tmp_path):
    ws = _seed_workspace(tmp_path)        # runs only, never assembled
    report = verify_package(ws)
    assert report.package_requirements_clean is True
    assert report.runs == []


def test_package_gate_no_pkgreqs_refuses_but_still_runs_layout_and_traceability(tmp_path):
    # SPEC-PAPER-GATE-001 P1 (OD-1 strict + OD-8 immediate): a package/ that exists at all is
    # conclusion-bearing, so the OLD "no pkgreqs.json -> vacuously clean for venue-format
    # checks" posture is OVERTURNED. A package with NO frozen pkgreqs.json now REFUSES with a
    # loud, actionable message naming what to freeze (REQ-PG-101/103/108) -- while the
    # layout/traceability/record-green checks still run alongside it (still additive).
    ws = _assembled(tmp_path, freeze=False)
    assert not (ws / "pkgreqs.json").exists()
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert report.passed is False
    joined = " ".join(report.package_requirements_problems).lower()
    assert "frozen" in joined or "freeze" in joined
    assert "pkgreqs" in joined
    # the traceability checks still ran -- the listed runs were audited (they reproduce).
    assert sorted(report.runs) == ["run-alpha", "run-beta"]
    assert all(report.runs_reproduced.values())


# -- (3) fail modes ----------------------------------------------------------

def test_package_gate_fails_on_missing_folder(tmp_path):
    ws = _assembled(tmp_path)
    shutil.rmtree(ws / "package" / "02_data")
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("02_data" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_unresolved_cite(tmp_path):
    ws = _assembled(tmp_path)
    main = _main_tex(ws)
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            r"\bibliography{references}", r"\citep{ghostkey}\bibliography{references}"
        ),
        encoding="utf-8",
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("ghostkey" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_tool_vocabulary_leak(tmp_path):
    ws = _assembled(tmp_path)
    main = _main_tex(ws)
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            r"\maketitle", r"\maketitle The frozen Spec and the sci-adk verdict say so."
        ),
        encoding="utf-8",
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("tool-vocabulary" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_missing_required_section(tmp_path):
    ws = _assembled(tmp_path)
    main = _main_tex(ws)
    main.write_text(
        main.read_text(encoding="utf-8").replace(r"\section{Methods}", "% removed methods"),
        encoding="utf-8",
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("Methods" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_abstract_over_limit(tmp_path):
    # A tiny abstract limit (5 words) the record-derived skeleton abstract exceeds.
    ws = _assembled(tmp_path, abstract_max_words=5)
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("abstract word count" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_unwired_reference_style(tmp_path):
    # The assembler honors the contract (wires the declared style), so to exercise the FAIL
    # mode we hand-strip the \bibliographystyle the contract declared (a divergent .tex).
    ws = _assembled(tmp_path, reference_style="apalike")
    main = _main_tex(ws)
    main.write_text(
        main.read_text(encoding="utf-8").replace(r"\bibliographystyle{apalike}", ""),
        encoding="utf-8",
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("reference style" in p for p in report.package_requirements_problems)


def test_package_gate_fails_when_a_run_does_not_reproduce(tmp_path):
    ws = _assembled(tmp_path)
    # Tamper a recorded claim so run-alpha no longer re-derives -> DIVERGED.
    claim = next((ws / "runs" / "run-alpha" / "claims").glob("*.json"))
    data = json.loads(claim.read_text(encoding="utf-8"))
    data["status"] = "refuted"
    claim.write_text(json.dumps(data), encoding="utf-8")
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("does not reproduce" in p for p in report.package_requirements_problems)
    assert report.runs_reproduced["run-alpha"] is False


def test_package_gate_fails_on_residual_fact_macro(tmp_path):
    # A residual \evval/\status macro (substitution bypassed / hand-edited) fails the fidelity
    # check (REUSED from the per-run reframe gate).
    ws = _assembled(tmp_path)
    main = _main_tex(ws)
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            r"\maketitle", r"\maketitle The value is \evval{ev-num}{point}."
        ),
        encoding="utf-8",
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("value fidelity" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_missing_claims_table(tmp_path):
    ws = _assembled(tmp_path)
    (ws / "package" / "02_data" / "claims_all.csv").unlink()
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("claims_all.csv" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_unbalanced_braces(tmp_path):
    ws = _assembled(tmp_path)
    main = _main_tex(ws)
    main.write_text(main.read_text(encoding="utf-8") + "\n{unbalanced\n", encoding="utf-8")
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("unbalanced braces" in p for p in report.package_requirements_problems)


def test_package_gate_fails_on_missing_submission_readiness(tmp_path):
    ws = _assembled(tmp_path)
    readme = ws / "package" / "README.md"
    # Strip the submission-readiness section heading (keep the file present).
    readme.write_text("# Near-submission package\n\nNo self-assessment here.\n", encoding="utf-8")
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("submission-readiness" in p.lower() for p in report.package_requirements_problems)


# -- (4) advisory is surfaced, never gated -----------------------------------

def test_package_gate_body_word_range_now_gates(tmp_path):
    # SPEC-PAPER-GATE-001 P4 / AC-3: the body word range GATES (was advisory). The tiny skeleton
    # body is far below 4000, so the declared range FAILS the gate and names the count.
    ws = _assembled(tmp_path, body_word_range=(4000, 7000))
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("body word count" in p for p in report.package_requirements_problems)
    # no longer surfaced as an advisory note (it gates now, not advises).
    assert not any("body word range" in note for note in report.advisory)


def test_package_gate_body_word_range_within_range_passes(tmp_path):
    # AC-3 (no false positive): a range the skeleton body fits raises no body-word failure.
    ws = _assembled(tmp_path, body_word_range=(0, 100000))
    report = verify_package(ws)
    assert not any("body word count" in p for p in report.package_requirements_problems)


# -- (4) P5 cross-run merge render (M3 / AC-7) -------------------------------

def test_package_merge_render_extracts_record_numbers_across_runs(tmp_path):
    # SPEC-PAPER-GATE-001 P5 / AC-7 (REQ-PG-501/502): the merged main.tex EXTRACTS each run's
    # recorded point statistic + pre-registered threshold from the record and writes them as
    # PLAIN literals (no macro). A 2-run workspace -> both runs' recorded values appear, and
    # the package gate is green because every literal traces to the record by construction.
    ws = _assembled(tmp_path, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    main = _main_tex(ws).read_text(encoding="utf-8")
    # run-alpha recorded point 0.95 / threshold 0.9; run-beta recorded point 0.85 / threshold 0.8.
    assert "0.95" in main and "0.9" in main      # run-alpha extracted into the manuscript
    assert "0.85" in main and "0.8" in main      # run-beta extracted into the manuscript
    # no reviewer-visible fact macro -- the numbers are plain literals (the user's clean-source
    # constraint + REQ-PG-502); the merge render owns the numbers, not a \evval-style command.
    assert "\\evval" not in main
    report = verify_package(ws)
    assert report.package_requirements_clean is True
    assert report.passed is True


def test_package_merge_render_hand_typed_value_fails_p2(tmp_path):
    # SPEC-PAPER-GATE-001 P5 / AC-7 (REQ-PG-503): a record-typed quantity hand-edited to a value
    # the record does not hold FAILS the deterministic package number-audit (no LLM verdict).
    ws = _assembled(tmp_path, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    main_path = _main_tex(ws)
    # 0.97 is not in the package pool {0.95, 0.9, 0.85, 0.8, ...}; the audit is exact-only here.
    main_path.write_text(
        main_path.read_text(encoding="utf-8").replace("0.95", "0.97"), encoding="utf-8"
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("0.97" in p for p in report.package_requirements_problems)


def test_package_merge_render_prose_is_free(tmp_path):
    # SPEC-PAPER-GATE-001 P5 / AC-7 (OD-7 boundary): agent-authored PROSE (no record-typed
    # number) is free -- authoring an Introduction prose slot leaves the gate green.
    ws = _assembled(tmp_path, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    main_path = _main_tex(ws)
    prose = (
        "The injectivity of the encoding is the property this synthesis examines, and the "
        "recorded results below bear on it directly."
    )
    main_path.write_text(
        main_path.read_text(encoding="utf-8").replace(
            "% (skeleton) author the Introduction section to the package spec; the manuscript "
            "names the science, not the toolchain.",
            prose,
        ),
        encoding="utf-8",
    )
    report = verify_package(ws)
    assert report.package_requirements_clean is True
    assert report.passed is True
