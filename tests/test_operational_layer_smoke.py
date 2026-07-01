"""
End-to-end smoke regression for the operational layer: install the
research-workspace kit AND drive the standalone CLI verb chain to a passing
``verify`` gate, all from a fresh temp workspace -- with NO Docker and NO LLM.

Why this exists (the codified gap this closes):

  - ``tests/test_init_session.py`` proves the installer lands the full asset
    list (non-clobbering + idempotent), but never RUNS the installed surface.
  - ``tests/test_cli_verb_decomposition.py`` proves the verb chain is
    byte-identical to ``compile()``, but over a workspace it constructs by
    calling compiler stages directly -- it never exercises ``init-session``.

Neither test proves the two halves work TOGETHER from scratch. The prior
"step 9" did -- but only as a one-time live cycle, leaving no regression net.
This test is that net: a single function that (1) installs the kit, then
(2) drives ``init-spec`` (seed) -> ``append-evidence`` -> ``execute`` (F5
replay) -> ``derive-claim`` -> ``render`` via the real CLI ``main([...])``,
then (3) asserts the headless ``verify_run`` gate -- the SAME verdict the Stop
hook enforces -- passes with exit-0 semantics.

Docker-free / LLM-free by construction: the Evidence is injected as a
deterministic ``EvidenceItem`` (fixed id + created_at) via the
``append-evidence`` verb, and the numeric (threshold) Spec resolves its Claim
autonomously -- no experiment fn, no capability, no judge, no checkpoint. So it
runs in the default suite alongside everything else.

SCOPE: this file deliberately does NOT re-assert the full installed asset list
(``test_init_session.py`` owns that) nor any draft.tex byte-identity
(``test_cli_verb_decomposition.py`` owns that). Its unique value is the
install + operational-verb-surface + verify gate, end to end.
"""

from __future__ import annotations

import json

from sci_adk.cli import main
from sci_adk.core.spec import Spec
from sci_adk.init_session import install_session
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.verify import verify_run

# Reuse the canonical numeric-spec + deterministic-evidence fixtures verbatim from
# the verb-decomposition suite: the numeric THRESHOLD rule resolves autonomously
# (no agent checkpoint), and referent="formal" + non_circularity satisfy the
# evidence-validity gate for the generated EvidenceItem. The fixed id/timestamp make
# the run reproducible. Importing (not re-defining) keeps a single source of truth.
from tests.test_cli_verb_decomposition import (  # noqa: E402
    _HYP_ID,
    _deterministic_evidence,
    _numeric_spec,
)


def test_operational_layer_install_then_verb_chain_to_passing_verify(tmp_path):
    """Install the kit, drive the CLI verb chain, and pass the verify gate -- no Docker/LLM.

    Three acts, all from a fresh ``tmp_path`` research workspace:

      1. install_session(tmp_path): the installer succeeds (non-empty report) and a
         representative kit asset is physically on disk (a hook + a Skill). The full
         asset list is asserted elsewhere; here we only confirm the install ran.
      2. The standalone CLI verb chain, in-process via ``main([...])``, Docker-free:
         init-spec (seed) -> append-evidence -> execute (F5 replay) -> derive-claim
         -> render. Each verb returns exit 0; Claims are produced; paper/ is rendered.
      3. verify_run(run_dir).passed is True -- the SAME combined gate (all claims
         reproduce AND the paper is internally consistent) the Stop hook enforces,
         and the CLI ``verify`` verb exits 0 on. We assert the CLI exit-0 too.
    """
    # ---- Act 1: install the operational-layer kit into the fresh workspace. ----
    report = install_session(tmp_path)
    # The install did real work (not all-skipped): a fresh dir installs every asset.
    assert report.installed, "install_session reported nothing installed into a fresh dir"
    assert not report.skipped, "a fresh dir should have nothing to skip (non-clobber)"
    # A representative kit asset from each major group is physically present on disk:
    # an enforcement hook (the Stop verify gate the verify_run gate backs) and a Skill.
    assert (tmp_path / ".claude" / "hooks" / "sci-adk" / "stop-verify-gate.sh").is_file()
    assert (tmp_path / ".claude" / "skills" / "sci" / "SKILL.md").is_file()

    # ---- Act 2: drive the standalone CLI verb chain (Docker-free, LLM-free). ----
    spec_id = "ops-smoke"

    # init-spec: the CLI ``init-spec`` verb only resolves a Spec from a proposal or a
    # capability (no Spec-injection flag), and a capability demo would pull in the
    # experiment path. So we seed the numeric Spec the same way test_cli_verb_
    # decomposition's _seed_spec_and_evidence does -- via the real stage_init_spec(spec=)
    # serialization. This writes spec.json + the prior-work checkpoint to the run dir,
    # exactly as the CLI ``init-spec`` stage does, keeping the rest of the chain CLI-driven.
    spec = _numeric_spec(spec_id)
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    run_dir = tmp_path / "runs" / spec_id
    assert (run_dir / "spec.json").exists()
    assert (run_dir / "checkpoints" / "prior_work.json").exists()

    # append-evidence: inject the deterministic EvidenceItem via the CLI verb (the
    # Docker-free Evidence path -- a JSON file holding one EvidenceItem, the exact shape
    # _cmd_append_evidence loads via EvidenceItem.model_validate).
    item = _deterministic_evidence(spec)
    ev_file = tmp_path / "evidence_in.json"
    ev_file.write_text(
        json.dumps(item.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    assert main(["append-evidence", str(run_dir), "--evidence", str(ev_file)]) == 0
    assert (run_dir / "evidence" / "evi-fixed-0001.json").exists()

    # execute (F5 replay): with recorded Evidence already on disk and NO capability,
    # _cmd_execute hits the F5 reuse path -- it REPLAYS the recorded Evidence rather than
    # running any experiment (no Docker, no capability). _cmd_execute only errors when
    # there is neither a capability NOR recorded Evidence (test_execute_no_experiment_
    # no_evidence_errors); here append-evidence supplied the Evidence, so this exits 0.
    assert main(["execute", str(run_dir)]) == 0
    # F5 reuse appends nothing: still exactly the one injected Evidence file.
    assert {p.name for p in (run_dir / "evidence").glob("*.json")} == {
        "evi-fixed-0001.json"
    }

    # derive-claim: apply the frozen DecisionRule to the recorded Evidence -> Claims.
    # --no-strict-science: this smoke test exercises the install + verb-chain PLUMBING with a
    # minimal formal+threshold spec that carries no falsifying negative control; a strict
    # derive (the default) would correctly HALT it (design/science-guards.md G3). The strict
    # science enforcement has its own coverage in test_science_guards.
    assert main(["derive-claim", str(run_dir), "--no-strict-science"]) == 0
    claim_path = run_dir / "claims" / f"claim-{_HYP_ID}.json"
    assert claim_path.exists(), "derive-claim produced no Claim for the hypothesis"

    # render: compile the paper artifacts from the recorded spec/evidence/claims.
    assert main(["render", str(run_dir)]) == 0
    assert (run_dir / "paper" / "draft.tex").exists()
    # SPEC-SI-AUTHORING-001 M1: the deterministic dump is the deposit record.tex (the
    # paper/si.tex slot is freed for the authored overflow path).
    from sci_adk.loop.compiler import deposit_record_path
    assert deposit_record_path(run_dir).exists()

    # SPEC-PAPER-GATE-001 P1 (OD-1 strict + OD-8 immediate): a rendered draft.tex is a
    # conclusion-bearing artifact, so freezing a publishing contract is now a completion step
    # (REQ-PG-102) -- without it verify REFUSES. The skeleton paper carries no quantitative
    # literal beyond the record, so a minimal contract (sub-checks off) gates green.
    from sci_adk.core.pubreqs import PubReqs as _PubReqs
    from sci_adk.provenance import pubreqs_digest as _pubreqs_digest

    _pr = _PubReqs(
        spec_id=spec_id, required_sections=[], figure_font_policy=False,
        image_min_dpi=None, reference_style=None, max_words=None,
        reproduction_bundle=False,
    )
    _pr = _pr.model_copy(update={"digest": _pubreqs_digest(_pr)})
    (run_dir / "pubreqs.json").write_text(_pr.model_dump_json(indent=2), encoding="utf-8")

    # ---- Act 3: the verify gate -- the SAME verdict the Stop hook enforces. ----
    # verify_run is the kernel function behind the ``verify`` verb: re-derive belief from
    # the recorded run (no re-run, no LLM) and confirm it follows from the record AND the
    # rendered paper is internally consistent. .passed is the COMBINED exit gate.
    vreport = verify_run(run_dir)
    assert vreport.all_reproduced, (
        "verify: a recorded claim DIVERGED or is UNRESOLVED -- the record does not "
        "re-derive its own belief"
    )
    assert vreport.paper_consistent, "verify: the rendered paper failed \\ref<->\\label"
    assert vreport.passed, "verify combined gate (claims + paper) did not pass"
    # The Stop hook keys off the CLI verb's exit code: assert exit-0 semantics directly.
    assert main(["verify", str(run_dir)]) == 0

    # ---- The run dir structure is complete (spec + evidence + claims + paper). ----
    assert (run_dir / "spec.json").exists()
    assert list((run_dir / "evidence").glob("*.json")), "no Evidence log in the run dir"
    assert list((run_dir / "claims").glob("*.json")), "no Claims in the run dir"
    assert (run_dir / "paper").is_dir(), "no paper/ in the run dir"
    # spec.json round-trips through the real Spec serialization (the record is well-formed).
    reloaded = Spec.model_validate(
        json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    )
    assert reloaded.id == spec_id
