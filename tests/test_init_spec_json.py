"""
`sci-adk init-spec`: the frozen-Spec overwrite guard and the `--spec-json` freeze path.

1. A frozen Spec is never re-frozen through `init-spec` -- on any input path (proposal,
   capability demo, --spec-json). A second freeze of the same id exits 2, points to
   `amend-spec`, and writes nothing (spec.json and the checkpoints stay byte-identical).
2. `init-spec --spec-json FILE` freezes a pre-built Spec (e.g. numeric interval
   DecisionRules the Markdown parser cannot author) through the same stage function.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sci_adk.cli import main
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

_PROPOSAL_A = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"
_PROPOSAL_B = "# Background\nother\n# Goal\nother goal\n# Expected Output\nx\n# Method\ny\n"


def _interval_spec(spec_id: str = "sj-interval") -> Spec:
    """A Spec whose single hypothesis carries a numeric INTERVAL DecisionRule."""
    rule = DecisionRule(
        kind=DecisionRuleKind.INTERVAL,
        expression="95% CI excludes 0 => support",
        params={"null_value": 0.0, "support_side": "excludes", "confidence_level": 0.95},
    )
    return Spec(
        id=spec_id,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        version=1,
        raw_proposal=RawProposal(
            background="Background pane.",
            goal="Goal pane.",
            method="Method pane.",
            expected_output="Expected output pane.",
        ),
        hypotheses=[
            Hypothesis(
                id="hyp-interval",
                statement="The effect differs from zero",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=rule,
            )
        ],
        method=MethodPlan(approaches=["Estimate the effect with a 95% CI"]),
        target_claims=[
            TargetClaim(id="claim-t1", statement="The effect is non-zero",
                        answers="hyp-interval")
        ],
    )


def _write_spec_json(tmp_path: Path, payload: dict, name: str = "spec.json") -> Path:
    path = tmp_path / "drafts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload(spec_id: str = "sj-interval") -> dict:
    return _interval_spec(spec_id).model_dump(mode="json")


def _snapshot(run_dir: Path) -> dict:
    """{relative path: (bytes, mtime_ns)} for every file under the run dir."""
    return {
        str(p.relative_to(run_dir)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(run_dir.rglob("*"))
        if p.is_file()
    }


# --------------------------------------------------------------------------- #
# Change 1 -- a frozen Spec is never overwritten by init-spec
# --------------------------------------------------------------------------- #

def test_init_spec_refuses_to_refreeze_same_proposal(tmp_path, capsys):
    proposal = tmp_path / "p.md"
    proposal.write_text(_PROPOSAL_A, encoding="utf-8")
    argv = ["init-spec", str(proposal), "-o", str(tmp_path), "--spec-id", "X"]
    assert main(argv) == 0
    run_dir = tmp_path / "runs" / "X"
    before = _snapshot(run_dir)
    capsys.readouterr()

    rc = main(argv)
    err = capsys.readouterr().err
    assert rc == 2
    assert "amend-spec" in err
    assert _snapshot(run_dir) == before


def test_init_spec_refuses_to_refreeze_different_proposal_same_id(tmp_path, capsys):
    proposal_a = tmp_path / "a.md"
    proposal_a.write_text(_PROPOSAL_A, encoding="utf-8")
    proposal_b = tmp_path / "b.md"
    proposal_b.write_text(_PROPOSAL_B, encoding="utf-8")
    assert main(["init-spec", str(proposal_a), "-o", str(tmp_path), "--spec-id", "X"]) == 0
    run_dir = tmp_path / "runs" / "X"
    before = _snapshot(run_dir)
    capsys.readouterr()

    rc = main(["init-spec", str(proposal_b), "-o", str(tmp_path), "--spec-id", "X"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "amend-spec" in err
    assert _snapshot(run_dir) == before
    frozen = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    assert frozen["raw_proposal"]["goal"] == "g"


def test_init_spec_refuses_to_refreeze_capability_demo(tmp_path, capsys):
    assert main(["init-spec", "--t1-demo", "-o", str(tmp_path)]) == 0
    run_dir = tmp_path / "runs" / "t1-godel"
    before = _snapshot(run_dir)
    capsys.readouterr()

    rc = main(["init-spec", "--t1-demo", "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "amend-spec" in err
    assert _snapshot(run_dir) == before


def test_init_spec_refuses_to_refreeze_spec_json(tmp_path, capsys):
    path = _write_spec_json(tmp_path, _payload())
    assert main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)]) == 0
    run_dir = tmp_path / "runs" / "sj-interval"
    before = _snapshot(run_dir)
    capsys.readouterr()

    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "amend-spec" in err
    assert _snapshot(run_dir) == before


# --------------------------------------------------------------------------- #
# Change 2 -- init-spec --spec-json FILE
# --------------------------------------------------------------------------- #

def test_spec_json_freezes_interval_rule_round_trip(tmp_path, capsys):
    path = _write_spec_json(tmp_path, _payload())
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "froze Spec 'sj-interval'" in out
    assert "spec_digest:" in out
    run_dir = tmp_path / "runs" / "sj-interval"
    assert (run_dir / "checkpoints" / "prior_work.json").exists()

    frozen = Spec.model_validate(
        json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    )
    expected = _interval_spec()
    assert frozen.hypotheses[0].decision_rule == expected.hypotheses[0].decision_rule
    assert frozen.hypotheses[0].decision_rule.kind == DecisionRuleKind.INTERVAL
    # Everything except created_at is carried over verbatim.
    assert frozen.model_dump(exclude={"created_at"}) == expected.model_dump(
        exclude={"created_at"}
    )


def test_spec_json_replaces_supplied_created_at_and_notes_it(tmp_path, capsys):
    path = _write_spec_json(tmp_path, _payload())  # carries created_at = 2020-01-01
    before_call = datetime.now(timezone.utc)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "created_at" in out and "ignored" in out
    frozen = Spec.model_validate(
        json.loads((tmp_path / "runs" / "sj-interval" / "spec.json").read_text(
            encoding="utf-8"))
    )
    assert frozen.created_at >= before_call


def test_spec_json_without_created_at_prints_no_note(tmp_path, capsys):
    payload = _payload()
    payload.pop("created_at")
    path = _write_spec_json(tmp_path, payload)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ignored" not in out


def test_spec_json_unknown_top_level_key_rejected(tmp_path, capsys):
    payload = _payload()
    payload["hypothesis"] = []  # typo of "hypotheses"
    path = _write_spec_json(tmp_path, payload)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "hypothesis" in err
    assert not (tmp_path / "runs").exists()


def test_spec_json_version_2_rejected(tmp_path, capsys):
    payload = _payload()
    payload["version"] = 2
    path = _write_spec_json(tmp_path, payload)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "amend-spec" in err
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize(
    "field, value",
    [("prior_version_id", "spec-old"), ("amendment_rationale", "tightened")],
)
def test_spec_json_amendment_fields_rejected(tmp_path, capsys, field, value):
    payload = _payload()
    payload[field] = value
    path = _write_spec_json(tmp_path, payload)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert field in err
    assert not (tmp_path / "runs").exists()


def test_spec_json_spec_id_mismatch_rejected(tmp_path, capsys):
    path = _write_spec_json(tmp_path, _payload())
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path),
               "--spec-id", "other-id"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "other-id" in err and "sj-interval" in err
    assert not (tmp_path / "runs").exists()


def test_spec_json_spec_id_match_accepted(tmp_path, capsys):
    path = _write_spec_json(tmp_path, _payload())
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path),
               "--spec-id", "sj-interval"])
    assert rc == 0


@pytest.mark.parametrize(
    "extra",
    [["proposal.md"], ["--t1-demo"], ["--capability", "t1-molecular-godel"]],
)
def test_spec_json_exclusive_with_other_inputs(tmp_path, extra):
    path = _write_spec_json(tmp_path, _payload())
    with pytest.raises(SystemExit) as exc:
        main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path), *extra])
    assert exc.value.code == 2
    assert not (tmp_path / "runs").exists()


def test_spec_json_malformed_json_rejected(tmp_path, capsys):
    path = tmp_path / "drafts" / "spec.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "Traceback" not in err
    assert not (tmp_path / "runs").exists()


def test_spec_json_schema_violation_rejected_with_pydantic_message(tmp_path, capsys):
    payload = _payload()
    payload["hypotheses"] = []  # Spec requires at least one hypothesis
    path = _write_spec_json(tmp_path, payload)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "at least one hypothesis" in err
    assert not (tmp_path / "runs").exists()


def test_spec_json_missing_file_rejected(tmp_path, capsys):
    rc = main(["init-spec", "--spec-json", str(tmp_path / "nope.json"),
               "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err
