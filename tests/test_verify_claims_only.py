"""``sci-adk verify --claims-only``: the claim audit without the paper-side checks.

The workspace Stop hook must tell two kinds of failure apart: a recorded claim that no
longer re-derives from its record (it blocks every time) and a failing paper-side check
(manuscript, numbers, publishing requirements, deposit files -- it blocks once, because
the session that hits it may not be the one that owns the paper). ``--claims-only``
gives the hook the first signal on its own:

  - exit 0 iff every recorded claim REPRODUCES and every recorded ``found_nothing``
    novelty decision rests on a sound search log (the record behind the novelty claims);
  - the paper-side checks are NOT run, so neither a failing one nor an unreadable
    manuscript can make it fail;
  - the default ``verify`` (no flag) is unchanged and stays the verdict.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sci_adk.cli import main
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    LiteratureDecision,
    Provenance,
    Result,
)
from sci_adk.core.search_log import SearchLogRecord
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
from sci_adk.loop.verify import verify_run

_NON_CIRC = "the verifier checks a property not baked into the generator"
_SOUND_LOG = SearchLogRecord(
    searched_at=["2020-01-01T00:00:00Z"],
    queries=[{"index": "openalex", "query": "first to show Z", "status": "ok"},
             {"index": "crossref", "query": "first to show Z", "status": "ok"}],
)
_ONE_INDEX_LOG = SearchLogRecord(
    searched_at=["2020-01-01T00:00:00Z"],
    queries=[{"index": "openalex", "query": "first to show Z", "status": "ok"}],
)


def _spec(spec_id: str) -> Spec:
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id="hyp-n", statement="first to show Z",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
                novelty_result=True,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-n")],
    )


def _seed_run(tmp_path: Path, spec_id: str, *, search_log: SearchLogRecord = _SOUND_LOG,
              keep_paper: bool = True) -> Path:
    """A recorded run whose claims reproduce; ``run_checkpoint_loop`` also renders a paper.

    The rendered skeleton ``paper/draft.tex`` has no frozen ``pubreqs.json`` beside it, so
    the default ``verify`` fails it on the paper side -- the situation ``--claims-only``
    exists to tell apart from a claim failure.
    """
    # the search logs above are dated 2020: before the freeze, as a pre-registered search is
    spec = _spec(spec_id)

    def experiment(s, w):
        return [
            EvidenceItem(
                id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
                provenance=Provenance(code_ref="fixture", data_source="generated"),
                result=Result(type="quantitative", point=0.95),
                bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
            ),
            EvidenceItem(
                id="evi-nov-decision", spec_id=s.id,
                kind=EvidenceKind.NOVELTY_DECISION,
                provenance=Provenance(code_ref="novelty:result:found_nothing",
                                      search_log=search_log),
                result=Result(type="qualitative", finding="result found_nothing"),
                bears_on=[],
                literature_decision=LiteratureDecision(
                    outcome="found_nothing", hypothesis_id="hyp-n", kind="result",
                    literature_evidence_id="evi-lit-x"),
            ),
        ]

    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=tmp_path)
    if not keep_paper:
        shutil.rmtree(run_dir / "paper", ignore_errors=True)
    return run_dir


def _demote_experiment_claim(run_dir: Path) -> None:
    """Hand-edit the recorded experiment claim so it no longer re-derives (DIVERGED)."""
    claim_path = next(p for p in (run_dir / "claims").glob("*.json")
                      if "novelty" not in p.name)
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["status"] = "contested"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")


# --------------------------------------------------------------------------- #
# the CLI flag
# --------------------------------------------------------------------------- #

def test_paper_side_failure_fails_verify_but_not_claims_only(tmp_path, capsys):
    run_dir = _seed_run(tmp_path, "co-paper")
    # precondition: the claims reproduce and the default verify fails on the paper side
    report = verify_run(run_dir)
    assert report.all_reproduced is True
    assert report.passed is False
    assert report.paper_requirements_clean is False

    assert main(["verify", str(run_dir)]) == 1
    capsys.readouterr()

    assert main(["verify", "--claims-only", str(run_dir)]) == 0
    out = capsys.readouterr()
    assert "REPRODUCED" in out.out
    assert "all recorded claims reproduced from the record" in out.out
    # the reader is told what was left out, and where the full gate is
    assert "--claims-only" in out.out
    assert "paper-side checks not judged" in out.out
    # no paper-side verdict is printed in this mode
    assert "publishing requirements" not in out.out + out.err


def test_claims_only_fails_when_a_recorded_claim_diverges(tmp_path, capsys):
    run_dir = _seed_run(tmp_path, "co-diverged", keep_paper=False)
    _demote_experiment_claim(run_dir)

    assert main(["verify", "--claims-only", str(run_dir)]) == 1
    out = capsys.readouterr()
    assert "DIVERGED" in out.out
    assert "NOT reproduced" in out.err


def test_claims_only_fails_on_an_unsound_novelty_search_log(tmp_path, capsys):
    """A found_nothing resting on one index is record-side: the novelty claim's backing."""
    run_dir = _seed_run(tmp_path, "co-searchlog", search_log=_ONE_INDEX_LOG,
                        keep_paper=False)
    assert verify_run(run_dir).all_reproduced is True  # the re-derivation itself passes

    assert main(["verify", "--claims-only", str(run_dir)]) == 1
    out = capsys.readouterr()
    assert "search log FAILED" in out.err
    assert "hyp-n" in out.err


def test_claims_only_passes_a_clean_run(tmp_path, capsys):
    run_dir = _seed_run(tmp_path, "co-clean", keep_paper=False)
    assert main(["verify", "--claims-only", str(run_dir)]) == 0
    assert main(["verify", str(run_dir)]) == 0  # control: nothing fails on either side


def test_claims_only_never_reads_the_manuscript(tmp_path, capsys):
    """An unreadable draft.tex is a paper-side problem; it cannot fail the claim audit."""
    run_dir = _seed_run(tmp_path, "co-unreadable")
    (run_dir / "paper" / "draft.tex").write_bytes(b"\\section{Results}\n\xff\xfe broken\n")

    assert main(["verify", str(run_dir)]) == 1           # the full gate still fails
    capsys.readouterr()
    assert main(["verify", "--claims-only", str(run_dir)]) == 0


def test_claims_only_forwards_strict_science(tmp_path, capsys):
    """The flags combine: --strict-science still re-applies the science guards."""
    run_dir = _seed_run(tmp_path, "co-strict", keep_paper=False)
    lenient = main(["verify", "--claims-only", str(run_dir)])
    strict = main(["verify", "--claims-only", "--strict-science", str(run_dir)])
    full_strict = main(["verify", "--strict-science", str(run_dir)])
    assert lenient == 0
    # no paper -> strict claims-only and strict full verify judge the same thing
    assert strict == full_strict


def test_claims_only_refuses_a_workspace_target(tmp_path, capsys):
    """The package gate is paper-side; --claims-only audits one run dir."""
    (tmp_path / "runs").mkdir()
    (tmp_path / "package").mkdir()
    assert main(["verify", "--claims-only", str(tmp_path)]) == 2
    assert "--claims-only" in capsys.readouterr().err


def test_claims_only_missing_spec_is_still_an_error(tmp_path, capsys):
    run_dir = tmp_path / "runs" / "nope"
    run_dir.mkdir(parents=True)
    assert main(["verify", "--claims-only", str(run_dir)]) == 2
    assert "no spec.json" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# the library entry
# --------------------------------------------------------------------------- #

def test_verify_run_claims_only_skips_the_paper_side(tmp_path):
    run_dir = _seed_run(tmp_path, "co-api")
    full = verify_run(run_dir)
    claims = verify_run(run_dir, claims_only=True)

    assert full.paper_side_checked is True
    assert claims.paper_side_checked is False
    # same record, same claim audit
    assert claims.digest == full.digest
    assert [o.result for o in claims.outcomes] == [o.result for o in full.outcomes]
    assert claims.all_reproduced is full.all_reproduced is True
    # in claims-only mode the exit gate is the claim signal
    assert claims.passed is True
    assert claims.passed is claims.claims_passed
    assert full.passed is False


def test_claims_passed_is_reproduction_and_search_log(tmp_path):
    clean = verify_run(_seed_run(tmp_path / "a", "co-cp-clean", keep_paper=False))
    weak = verify_run(_seed_run(tmp_path / "b", "co-cp-weak", search_log=_ONE_INDEX_LOG,
                                keep_paper=False))
    paper = verify_run(_seed_run(tmp_path / "c", "co-cp-paper"))

    assert clean.claims_passed is True
    assert weak.all_reproduced is True and weak.claims_passed is False
    # a paper-side failure does not touch the claim signal
    assert paper.passed is False and paper.claims_passed is True
