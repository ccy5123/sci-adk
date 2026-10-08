"""
`sci-adk amend-spec --spec-json FILE`: content amendments + the frozen-version history.

1. A content amendment takes ``raw_proposal`` / ``hypotheses`` / ``method`` /
   ``target_claims`` from FILE and passes them to ``Spec.amend`` (which owns version+1,
   ``created_at``, ``prior_version_id``, ``amendment_rationale``). FILE must name the same
   Spec id; a ``version`` in FILE must be current+1; an ``amendment_rationale`` in FILE must
   equal ``--rationale``; identical content is refused ("nothing to amend").
2. Every amendment (content or rationale-only) first saves the current frozen spec.json
   byte-for-byte to ``spec_history/spec.v<version>.json`` and records its sha256 in the
   amendment receipt. A history file is never overwritten.
3. Unknown keys anywhere in the Spec JSON (not only at the top level) are refused with
   their JSON path, for both ``init-spec --spec-json`` and ``amend-spec --spec-json``;
   the free-form ``DecisionRule.params`` mapping is not walked.

The real-run fixture (``tests/fixtures/amend_bcfkow``) is a copy of a run whose v2 method
adds one record-selection sentence; ``proposed-v2.json`` was produced in memory by
``Spec.amend`` and so already holds version 2, created_at, prior_version_id and the
rationale.
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
from sci_adk.loop.amend_spec import AmendmentReceipt
from sci_adk.loop.compiler import ResearchCompiler

_FIXTURE = Path(__file__).parent / "fixtures" / "amend_bcfkow"
_ADDED_SENTENCE = (
    " For the Arnot & Gobas database, keep only ENDPOINT CATEGORY 2 (BCF from total water "
    "concentrations); exclude category 3 (BCFfd, BCF from freely dissolved water "
    "concentrations) as well as categories 1 and 4 (field and modelled BAF)."
)


def _spec(spec_id: str = "am-c") -> Spec:
    return Spec(
        id=spec_id,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        raw_proposal=RawProposal(
            background="Background pane.", goal="Goal pane.",
            method="Method pane.", expected_output="Expected output pane.",
        ),
        hypotheses=[
            Hypothesis(
                id="hyp-a", statement="The effect differs from zero",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.INTERVAL,
                    expression="95% CI excludes 0 => support",
                    params={"null_value": 0.0, "support_side": "excludes"},
                ),
            ),
            Hypothesis(
                id="hyp-b", statement="The slope is positive",
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD, expression="slope > 0 => support",
                    params={"statistic": "slope", "op": ">", "value": 0.0},
                ),
            ),
        ],
        method=MethodPlan(approaches=["Estimate the effect with a 95% CI"]),
        target_claims=[
            TargetClaim(id="claim-t1", statement="The effect is non-zero", answers="hyp-a")
        ],
    )


def _frozen_run(tmp_path: Path, spec_id: str = "am-c") -> Path:
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=_spec(spec_id))
    return tmp_path / "runs" / spec_id


def _current(run_dir: Path) -> dict:
    return json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict, name: str = "proposed.json") -> Path:
    path = tmp_path / "drafts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _next_version(run_dir: Path) -> dict:
    """A draft of the next version: a copy of the frozen spec.json, version bumped and the
    previous amendment's rationale removed (the new one comes from --rationale)."""
    payload = _current(run_dir)
    payload["version"] += 1
    payload.pop("amendment_rationale", None)
    return payload


def _proposal_with_method(run_dir: Path, approaches: list) -> dict:
    payload = _next_version(run_dir)
    payload["method"]["approaches"] = approaches
    return payload


def _snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _amend(run_dir: Path, rationale: str, spec_json: Path | None = None) -> int:
    argv = ["amend-spec", str(run_dir), "--rationale", rationale]
    if spec_json is not None:
        argv += ["--spec-json", str(spec_json)]
    return main(argv)


# --------------------------------------------------------------------------- #
# A -- content amendment
# --------------------------------------------------------------------------- #

def test_content_amendment_changes_method_and_keeps_everything_else(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    before = Spec.model_validate(_current(run_dir))
    path = _write(tmp_path, _proposal_with_method(
        run_dir, ["Estimate the effect with a 95% CI", "Drop records with no measured value"]
    ))

    rc = _amend(run_dir, "add a record filter", path)
    out = capsys.readouterr().out
    assert rc == 0

    after = Spec.model_validate(_current(run_dir))
    assert after.version == 2
    assert after.prior_version_id
    assert after.amendment_rationale == "add a record filter"
    assert after.method.approaches[1] == "Drop records with no measured value"
    assert after.raw_proposal == before.raw_proposal
    assert after.hypotheses == before.hypotheses
    assert after.target_claims == before.target_claims
    # The human approving the amendment sees which field changed.
    assert "method.approaches[1]" in out


def test_change_summary_names_the_changed_hypothesis(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    payload = _next_version(run_dir)
    payload["hypotheses"][1]["decision_rule"]["params"]["value"] = 0.5
    rc = _amend(run_dir, "raise the slope threshold", _write(tmp_path, payload))
    out = capsys.readouterr().out
    assert rc == 0
    assert "hypotheses[hyp-b].decision_rule.params.value" in out
    assert "hyp-a" not in out


def test_history_file_holds_the_pre_amendment_bytes_and_receipt_has_its_sha(tmp_path):
    run_dir = _frozen_run(tmp_path)
    v1_bytes = (run_dir / "spec.json").read_bytes()
    path = _write(tmp_path, _proposal_with_method(run_dir, ["A different approach"]))

    assert _amend(run_dir, "change approach", path) == 0

    history = run_dir / "spec_history" / "spec.v1.json"
    assert history.read_bytes() == v1_bytes
    receipt = AmendmentReceipt.model_validate_json(
        (run_dir / "checkpoints" / "amendment-v2.json").read_text(encoding="utf-8")
    )
    assert receipt.prior_spec_sha256 == hashlib.sha256(v1_bytes).hexdigest()


def test_second_amendment_saves_v2_and_leaves_v1_untouched(tmp_path):
    run_dir = _frozen_run(tmp_path)
    assert _amend(run_dir, "first", _write(
        tmp_path, _proposal_with_method(run_dir, ["Approach v2"]), "p2.json")) == 0
    v1_hist = (run_dir / "spec_history" / "spec.v1.json").read_bytes()
    v2_bytes = (run_dir / "spec.json").read_bytes()

    assert _amend(run_dir, "second", _write(
        tmp_path, _proposal_with_method(run_dir, ["Approach v3"]), "p3.json")) == 0

    assert (run_dir / "spec_history" / "spec.v1.json").read_bytes() == v1_hist
    assert (run_dir / "spec_history" / "spec.v2.json").read_bytes() == v2_bytes
    assert _current(run_dir)["version"] == 3
    receipt = json.loads(
        (run_dir / "checkpoints" / "amendment-v3.json").read_text(encoding="utf-8")
    )
    assert receipt["prior_spec_sha256"] == hashlib.sha256(v2_bytes).hexdigest()


def test_identical_content_is_nothing_to_amend(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    before = _snapshot(run_dir)
    rc = _amend(run_dir, "no change", _write(tmp_path, _next_version(run_dir)))
    err = capsys.readouterr().err
    assert rc == 2
    assert "nothing to amend" in err
    assert _snapshot(run_dir) == before


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda p: p.update(id="other-spec"), "other-spec"),
        (lambda p: p.update(version=3), "version"),
        (lambda p: p.update(version=1), "version"),
        (lambda p: p.update(amendment_rationale="a different reason"), "rationale"),
    ],
    ids=["id-mismatch", "version-skip", "version-same", "rationale-mismatch"],
)
def test_mismatched_proposal_is_refused_and_nothing_written(tmp_path, capsys, mutate, needle):
    run_dir = _frozen_run(tmp_path)
    payload = _proposal_with_method(run_dir, ["Approach v2"])
    mutate(payload)
    before = _snapshot(run_dir)
    rc = _amend(run_dir, "the real reason", _write(tmp_path, payload))
    err = capsys.readouterr().err
    assert rc == 2
    assert needle in err
    assert "Traceback" not in err
    assert _snapshot(run_dir) == before


def test_rationale_in_file_equal_after_strip_is_accepted(tmp_path):
    run_dir = _frozen_run(tmp_path)
    payload = _proposal_with_method(run_dir, ["Approach v2"])
    payload["version"] = 2
    payload["amendment_rationale"] = "the real reason\n"
    assert _amend(run_dir, "  the real reason ", _write(tmp_path, payload)) == 0
    assert _current(run_dir)["version"] == 2


def test_created_at_and_prior_version_id_in_file_are_ignored_with_a_note(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    payload = _proposal_with_method(run_dir, ["Approach v2"])
    payload["created_at"] = "1999-01-01T00:00:00Z"
    payload["prior_version_id"] = "made-up"
    rc = _amend(run_dir, "reason", _write(tmp_path, payload))
    out = capsys.readouterr().out
    assert rc == 0
    assert "ignored" in out and "created_at" in out and "prior_version_id" in out
    after = _current(run_dir)
    assert not after["created_at"].startswith("1999")
    assert after["prior_version_id"] != "made-up"


def test_blank_rationale_with_spec_json_writes_nothing(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    before = _snapshot(run_dir)
    rc = _amend(run_dir, "   ", _write(tmp_path, _proposal_with_method(run_dir, ["x"])))
    assert rc == 2
    assert "rationale" in capsys.readouterr().err.lower()
    assert _snapshot(run_dir) == before


def test_existing_history_file_with_other_bytes_is_never_overwritten(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    hist = run_dir / "spec_history" / "spec.v1.json"
    hist.parent.mkdir()
    hist.write_text("{\"something\": \"else\"}", encoding="utf-8")
    before = _snapshot(run_dir)
    rc = _amend(run_dir, "reason", _write(tmp_path, _proposal_with_method(run_dir, ["y"])))
    err = capsys.readouterr().err
    assert rc == 2
    assert "spec.v1.json" in err
    assert _snapshot(run_dir) == before


def test_rationale_only_amendment_still_works_and_keeps_history(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    v1_bytes = (run_dir / "spec.json").read_bytes()
    assert _amend(run_dir, "tighten the wording") == 0
    after = Spec.model_validate(_current(run_dir))
    assert after.version == 2
    assert (run_dir / "spec_history" / "spec.v1.json").read_bytes() == v1_bytes


def test_old_receipt_without_sha_still_loads():
    receipt = AmendmentReceipt.model_validate({
        "spec_id": "s", "prior_version": 1, "new_version": 2,
        "rationale": "r", "recorded_at": "2026-01-01T00:00:00+00:00",
    })
    assert receipt.prior_spec_sha256 is None


# --------------------------------------------------------------------------- #
# Real run (copy): the one-sentence method amendment
# --------------------------------------------------------------------------- #

def _real_run_copy(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "SPEC-BCFKOW-001"
    shutil.copytree(_FIXTURE / "run", run_dir)
    return run_dir


def test_real_proposed_v2_amends_a_copy_of_the_real_run(tmp_path, capsys):
    run_dir = _real_run_copy(tmp_path)
    v1 = Spec.model_validate(_current(run_dir))
    v1_bytes = (run_dir / "spec.json").read_bytes()
    proposed = tmp_path / "proposed-v2.json"
    shutil.copyfile(_FIXTURE / "proposed-v2.json", proposed)
    rationale = (_FIXTURE / "rationale.txt").read_text(encoding="utf-8")

    rc = _amend(run_dir, rationale, proposed)
    out = capsys.readouterr().out
    assert rc == 0, out

    v2 = Spec.model_validate(_current(run_dir))
    assert v2.version == 2
    assert v2.amendment_rationale == rationale.strip()
    old_a, new_a = v1.method.approaches, v2.method.approaches
    assert len(new_a) == len(old_a)
    changed = [i for i, (x, y) in enumerate(zip(old_a, new_a)) if x != y]
    assert changed == [1]
    assert _ADDED_SENTENCE.strip() in new_a[1]
    assert new_a[1].replace(_ADDED_SENTENCE, "") == old_a[1]
    assert v2.hypotheses == v1.hypotheses
    assert v2.raw_proposal == v1.raw_proposal
    assert v2.target_claims == v1.target_claims
    assert (run_dir / "spec_history" / "spec.v1.json").read_bytes() == v1_bytes
    assert "method.approaches[1]" in out


def _verify_findings(run_dir: Path) -> dict:
    """The verify report minus the fields an amendment is expected to change."""
    from sci_adk.loop.verify import verify_run

    report = vars(verify_run(run_dir)).copy()
    report.pop("digest", None)
    return {k: repr(v) for k, v in report.items()}


def test_verify_on_amended_real_run_has_no_new_findings(tmp_path):
    run_dir = _real_run_copy(tmp_path)
    before = _verify_findings(run_dir)
    proposed = tmp_path / "proposed-v2.json"
    shutil.copyfile(_FIXTURE / "proposed-v2.json", proposed)
    rationale = (_FIXTURE / "rationale.txt").read_text(encoding="utf-8")
    assert _amend(run_dir, rationale, proposed) == 0
    assert _verify_findings(run_dir) == before


# --------------------------------------------------------------------------- #
# D -- nested unknown-field rejection (init-spec and amend-spec)
# --------------------------------------------------------------------------- #

def _init_payload() -> dict:
    return _spec("sj-nested").model_dump(mode="json")


@pytest.mark.parametrize(
    "mutate, json_path",
    [
        (lambda p: p["hypotheses"][1]["decision_rule"].update(parms={}),
         "hypotheses[1].decision_rule.parms"),
        (lambda p: p["hypotheses"][0].update(statment="x"), "hypotheses[0].statment"),
        (lambda p: p["raw_proposal"].update(goals="x"), "raw_proposal.goals"),
        (lambda p: p["method"].update(tools=[{"name": "R", "versoin": "4"}]),
         "method.tools[0].versoin"),
        (lambda p: p["target_claims"][0].update(answer="hyp-a"), "target_claims[0].answer"),
        (lambda p: p["hypotheses"][0].update(
            discriminating_cases=[{"case": "c", "why": "w", "note": "n"}]),
         "hypotheses[0].discriminating_cases[0].note"),
    ],
)
def test_init_spec_rejects_nested_unknown_key_naming_its_path(
    tmp_path, capsys, mutate, json_path
):
    payload = _init_payload()
    mutate(payload)
    path = _write(tmp_path, payload)
    rc = main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert json_path in err
    assert not (tmp_path / "runs").exists()


def test_amend_spec_rejects_nested_unknown_key_naming_its_path(tmp_path, capsys):
    run_dir = _frozen_run(tmp_path)
    payload = _proposal_with_method(run_dir, ["Approach v2"])
    payload["hypotheses"][1]["decision_rule"]["parms"] = {"value": 1}
    before = _snapshot(run_dir)
    rc = _amend(run_dir, "reason", _write(tmp_path, payload))
    err = capsys.readouterr().err
    assert rc == 2
    assert "hypotheses[1].decision_rule.parms" in err
    assert _snapshot(run_dir) == before


def test_free_form_params_keys_are_not_walked(tmp_path):
    payload = _init_payload()
    payload["hypotheses"][0]["decision_rule"]["params"]["confidence_level"] = 0.95
    payload["hypotheses"][0]["decision_rule"]["params"]["any_custom_key"] = "ok"
    path = _write(tmp_path, payload)
    assert main(["init-spec", "--spec-json", str(path), "-o", str(tmp_path)]) == 0
    frozen = json.loads(
        (tmp_path / "runs" / "sj-nested" / "spec.json").read_text(encoding="utf-8")
    )
    assert frozen["hypotheses"][0]["decision_rule"]["params"]["any_custom_key"] == "ok"


def test_unknown_key_walker_is_derived_from_the_models():
    from sci_adk.core.spec import unknown_spec_keys

    payload = _init_payload()
    assert unknown_spec_keys(payload) == []
    payload["bogus"] = 1
    payload["hypotheses"][0]["decision_rule"]["params"]["free"] = 1
    payload["method"]["approachs"] = []
    # document order: method precedes the key appended last
    assert unknown_spec_keys(payload) == ["method.approachs", "bogus"]


# --------------------------------------------------------------------------- #
# C -- evidence recorded under v1, then a content amendment
# --------------------------------------------------------------------------- #

def test_v1_evidence_still_verifies_and_new_evidence_needs_the_v2_digest(tmp_path, capsys):
    from sci_adk.loop.verify import verify_run
    from sci_adk.provenance import spec_digest
    from tests.test_cli_verb_decomposition import _deterministic_evidence, _numeric_spec

    spec = _numeric_spec("am-ev")
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    run_dir = tmp_path / "runs" / "am-ev"
    v1_digest = spec_digest(spec)
    item = _deterministic_evidence(spec)
    ev1 = _write(tmp_path, item.model_dump(mode="json"), "ev1.json")
    assert main(["append-evidence", str(run_dir), "--evidence", str(ev1),
                 "--spec-digest", v1_digest]) == 0
    assert main(["derive-claim", str(run_dir), "--no-strict-science",
                 "--spec-digest", v1_digest]) == 0
    assert verify_run(run_dir).all_reproduced
    before = _verify_findings(run_dir)

    assert _amend(run_dir, "clarify the method", _write(
        tmp_path, _proposal_with_method(run_dir, ["m", "one more step"]))) == 0
    assert verify_run(run_dir).all_reproduced
    assert _verify_findings(run_dir) == before

    v2_digest = spec_digest(Spec.model_validate(_current(run_dir)))
    ev2 = _write(tmp_path, item.model_copy(update={"id": "evi-fixed-0002"})
                 .model_dump(mode="json"), "ev2.json")
    capsys.readouterr()
    assert main(["append-evidence", str(run_dir), "--evidence", str(ev2),
                 "--spec-digest", v1_digest]) == 2
    assert "digest" in capsys.readouterr().err.lower()
    assert not (run_dir / "evidence" / "evi-fixed-0002.json").exists()
    assert main(["append-evidence", str(run_dir), "--evidence", str(ev2),
                 "--spec-digest", v2_digest]) == 0
