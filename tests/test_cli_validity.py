"""
CLI behavior for the evidence-validity halt (design/evidence-validity.md E3).

The ValidityHalt raised at the Evidence->Claim chokepoint must surface through the
CLI as a FRIENDLY stderr message + a non-zero exit code -- never a raw traceback,
and never a "compiled ... supported" success line. This is what makes the halt
load-bearing at the user boundary (it is impossible to route around by generating
data: generating data is exactly what trips it).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
from sci_adk.loop.compiler import ResearchCompiler

_T0 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)


def _empirical_spec(spec_id: str) -> Spec:
    return Spec(
        id=spec_id,
        created_at=_T0,
        version=1,
        raw_proposal=RawProposal(
            background="bg", goal="goal", method="method", expected_output="out"
        ),
        hypotheses=[
            Hypothesis(
                id="hyp-e",
                statement="an empirical phenomenon holds",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= 0.5 => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="empirical",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-e")],
    )


def _synthetic_experiment(spec: Spec, workspace_dir: Path):
    return [
        EvidenceItem(
            id="ev-syn",
            created_at=_T0,
            spec_id=spec.id,
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="synthetic", data_source="synthetic_proxy"),
            result=Result(type="quantitative", point=0.9),
            bears_on=[Bearing(target_id="hyp-e", direction=BearingDirection.SUPPORTS)],
        )
    ]


def test_compiler_propagates_validity_halt(tmp_path):
    """The compiler does not swallow the halt: a synthetic->empirical run raises."""
    from sci_adk.core.validity import ValidityHalt
    import pytest

    compiler = ResearchCompiler(workspace_dir=tmp_path)
    with pytest.raises(ValidityHalt):
        compiler.compile(
            "", spec=_empirical_spec("cli-halt"), experiment=_synthetic_experiment
        )


def test_cli_run_synthetic_on_empirical_exits_nonzero_friendly(tmp_path, capsys, monkeypatch):
    """`sci-adk run` over a capability that produces synthetic->empirical Evidence
    exits non-zero with a friendly stderr message (no traceback, no success line).

    Driven by monkeypatching the compiler used inside _cmd_run so we exercise the
    CLI's halt handling without needing a real synthetic-on-empirical capability.
    """
    import sci_adk.cli as cli_mod

    class _HaltingCompiler:
        def __init__(self, *a, **k):
            pass

        def compile(self, *a, **k):
            compiler = ResearchCompiler(workspace_dir=tmp_path)
            return compiler.compile(
                "", spec=_empirical_spec("cli-run-halt"),
                experiment=_synthetic_experiment,
            )

    # The CLI needs a proposal/capability to reach compile(); give it a proposal file
    # and swap the compiler for one that runs the synthetic-on-empirical path.
    monkeypatch.setattr(cli_mod, "ResearchCompiler", _HaltingCompiler)
    proposal = tmp_path / "p.md"
    proposal.write_text("# Goal\nsomething\n", encoding="utf-8")

    rc = main(["run", str(proposal), "-o", str(tmp_path)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "error:" in err
    # Mentions the validity problem, not a Python traceback.
    assert "synthetic_proxy" in err or "empirical" in err.lower()
