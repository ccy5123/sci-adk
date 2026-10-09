"""
`sci-adk render <run> --record-only`: the deposit without a manuscript.

The publish protocol is two sessions. Session A freezes ``pubreqs.json`` and deposits the
deterministic record (``runs/<id>/record.tex``); Session B writes the paper from it. A
prose-less ``render`` also writes a skeleton ``paper/draft.tex`` (title + reference list),
and ``verify`` judges ANY ``paper/draft.tex`` as the conclusion-bearing manuscript -- so with
a frozen contract it fails (no IMRaD sections) and the workspace Stop hook blocks the end of
Session A. ``--record-only`` writes the record and nothing under ``paper/``.

Covered here:
  - the reproduction: the old Session A steps (freeze + prose-less render) cannot pass verify;
  - the fix: freeze + ``render --record-only`` -> verify exits 0, no ``paper/`` at all;
  - record.tex is byte-identical to the one a full render writes (one source for the record);
  - ``--record-only`` refuses the manuscript flags (argparse error, exit 2);
  - a stale ``paper/`` from an earlier render is left untouched and named;
  - verify names the likely cause when a draft carries none of the required sections.

No Docker, no LLM: a deterministic injected experiment (fixed id + created_at).
"""

from __future__ import annotations

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
from sci_adk.loop.compiler import ResearchCompiler, deposit_record_path
from sci_adk.loop.verify import verify_run

_AT = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
_HYP = "hyp-r"


def _spec(spec_id: str) -> Spec:
    """A numeric threshold Spec that resolves autonomously (no judge, no checkpoint)."""
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
                non_circularity=(
                    "the generator does not guarantee a zero metric; the verifier checks "
                    "it independently"
                ),
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="the metric is zero", answers=_HYP)],
    )


def _seed(workspace: Path, spec_id: str, code_ref: str = "fixture") -> Path:
    """Freeze the Spec, record one SUPPORTS Evidence item, derive the Claim (on disk)."""
    spec = _spec(spec_id)
    item = EvidenceItem(
        id="evi-rec-0001",
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


def _freeze_defaults(run_dir: Path) -> None:
    assert main(["pubreqs", "freeze", str(run_dir), "--defaults"]) == 0


# -- the reproduction ----------------------------------------------------------------


def test_documented_session_a_with_prose_less_render_cannot_pass_verify(tmp_path, capsys):
    """The bug: freeze the contract, render without prose -> a skeleton paper/draft.tex
    that verify judges as the manuscript, so Session A can never end green. (Unchanged:
    the default render keeps writing the skeleton -- the fix is a separate flag.)"""
    run_dir = _seed(tmp_path, "rec-repro")
    _freeze_defaults(run_dir)
    assert main(["render", str(run_dir)]) == 0
    assert (run_dir / "paper" / "draft.tex").is_file()
    capsys.readouterr()
    assert main(["verify", str(run_dir)]) == 1


# -- the fix -------------------------------------------------------------------------


def test_session_a_record_only_render_then_verify_exits_zero(tmp_path, capsys):
    run_dir = _seed(tmp_path, "rec-ok")
    _freeze_defaults(run_dir)
    assert main(["render", str(run_dir), "--record-only"]) == 0
    out = capsys.readouterr().out
    assert deposit_record_path(run_dir).is_file()
    assert "record.tex" in out
    # Nothing under paper/ at all: no draft.tex, no si.tex, no bundle, no copied bib.
    assert not (run_dir / "paper").exists()
    assert main(["verify", str(run_dir)]) == 0


def test_record_only_record_tex_is_byte_identical_to_full_render(tmp_path):
    """One source for the record: --record-only writes exactly the record.tex a full
    render writes (bibliography line and inlined reproduction code included)."""
    run_dir = _seed(tmp_path, "rec-same", code_ref="code/gen.py")
    script = run_dir / "code" / "gen.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('regenerate')\n", encoding="utf-8")
    lit = run_dir / "artifacts" / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    (lit / "references.bib").write_text(
        "@article{Doe2020,\n  title={A title},\n  year={2020},\n  doi={10.1/x}\n}\n",
        encoding="utf-8",
    )

    assert main(["render", str(run_dir), "--record-only"]) == 0
    record_only = deposit_record_path(run_dir).read_text(encoding="utf-8")
    assert not (run_dir / "paper").exists()
    assert r"\bibliography{references}" in record_only
    assert "print('regenerate')" in record_only

    assert main(["render", str(run_dir)]) == 0
    assert (run_dir / "paper" / "draft.tex").is_file()  # default render unchanged
    assert deposit_record_path(run_dir).read_text(encoding="utf-8") == record_only


def test_stage_render_record_writes_only_the_record(tmp_path):
    run_dir = _seed(tmp_path, "rec-stage")
    spec = Spec.model_validate_json((run_dir / "spec.json").read_text(encoding="utf-8"))
    record_path = ResearchCompiler(workspace_dir=tmp_path).stage_render_record(spec)
    assert record_path == deposit_record_path(run_dir)
    assert record_path.is_file()
    assert not (run_dir / "paper").exists()


@pytest.mark.parametrize(
    "flag",
    ["--prose", "--si", "--si-prose", "--figures"],
)
def test_record_only_refuses_manuscript_flags(tmp_path, capsys, flag):
    run_dir = _seed(tmp_path, "rec-clash")
    with pytest.raises(SystemExit) as exc:
        main(["render", str(run_dir), "--record-only", flag, str(tmp_path / "x.json")])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--record-only" in err
    assert flag in err
    assert not deposit_record_path(run_dir).exists()  # refused before anything ran


def test_record_only_leaves_an_earlier_paper_untouched_and_says_so(tmp_path, capsys):
    run_dir = _seed(tmp_path, "rec-stale")
    assert main(["render", str(run_dir)]) == 0
    draft = run_dir / "paper" / "draft.tex"
    before = draft.read_text(encoding="utf-8")
    capsys.readouterr()

    assert main(["render", str(run_dir), "--record-only"]) == 0
    err = capsys.readouterr().err
    assert draft.read_text(encoding="utf-8") == before  # never deleted or rewritten
    assert "paper/draft.tex" in err
    assert "verify" in err


# -- verify names the likely cause ---------------------------------------------------


def test_verify_names_prose_less_skeleton_when_no_required_section_is_present(tmp_path):
    run_dir = _seed(tmp_path, "rec-hint")
    _freeze_defaults(run_dir)
    assert main(["render", str(run_dir)]) == 0  # the skeleton

    report = verify_run(run_dir)
    assert report.passed is False
    hints = [p for p in report.paper_requirements_problems if "skeleton" in p]
    assert len(hints) == 1
    assert "--record-only" in hints[0]
    assert "--prose" in hints[0]
    # The per-section lines are unchanged.
    assert "missing required section: Methods" in report.paper_requirements_problems


def test_verify_does_not_blame_a_skeleton_when_some_sections_are_present(tmp_path):
    run_dir = _seed(tmp_path, "rec-partial")
    _freeze_defaults(run_dir)
    assert main(["render", str(run_dir)]) == 0
    draft = run_dir / "paper" / "draft.tex"
    draft.write_text(
        draft.read_text(encoding="utf-8").replace(
            r"\end{document}", "\\section{Introduction}\nText.\n\\end{document}"
        ),
        encoding="utf-8",
    )

    report = verify_run(run_dir)
    assert "missing required section: Methods" in report.paper_requirements_problems
    assert not any("skeleton" in p for p in report.paper_requirements_problems)
