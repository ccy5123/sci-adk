"""
SPEC-SI-AUTHORING-001 Milestone M2 (RED-first): the deposit-completeness gate -- the ONE
new RECORD-side gate (design/si-belief-record-split.md v0.4, Pillar C).

`sci-adk verify` carries a PURE, presence-only deposit-completeness check that confirms the
deposit contains (a) the retained record artifact (located via `deposit_record_path`, the M1
single source of truth -- never hard-coded here) AND (b) a "Data & code availability"
statement. It is ADDITIVE: it EXTENDS the report's problem channel and never weakens or
replaces the existing record-green / claim-reproduction audit (REQ-SA-305 / AC-C5).

Pillar C requirements pinned here at the verify-wiring level:
  - REQ-SA-301 (AC-C1): a complete deposit reports no deposit-completeness problems.
  - REQ-SA-302 (AC-C2): a deposit missing the record artifact FAILS LOUD, naming it.
  - REQ-SA-303 (AC-C3): a deposit missing the availability statement FAILS LOUD, naming it.
  - REQ-SA-305 (AC-C5): the check is ADDITIVE -- the existing claim-reproduction /
    record-green audit (`all_reproduced`) is unchanged and still gates.

The PURE checker itself (presence-only, deterministic, no LLM -- REQ-SA-304/AC-C4) is unit
tested in tests/test_pkgreqs.py alongside its `readme_submission_readiness_problems` precedent.
"""

from __future__ import annotations

from sci_adk.loop.compiler import deposit_record_path
from sci_adk.loop.verify import verify_run

# Reuse the established verify harness: _seed compiles a real run (the compiler writes the
# deposit record.tex per M1), and the numeric spec/experiment reproduce green.
from tests.test_verify import _numeric_experiment, _numeric_spec, _seed

_AVAILABILITY = (
    r"\section{Data \& code availability}"
    "\nThe full record is deposited; run \\texttt{sci-adk verify <run>} to re-derive it.\n"
)


def _append_availability(run_dir) -> None:
    """Author a "Data & code availability" statement into the deposit's record.tex (the
    deposit-side text spine the M1 compiler already wrote). Read via deposit_record_path --
    the single source of truth, never a hard-coded path."""
    record = deposit_record_path(run_dir)
    record.write_text(record.read_text(encoding="utf-8") + "\n" + _AVAILABILITY, encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-C1 [RECORD-SIDE] -- a complete deposit reports no deposit-completeness problems.
# ---------------------------------------------------------------------------

def test_verify_complete_deposit_has_no_deposit_problems(tmp_path):
    spec = _numeric_spec("m2-complete", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # compiler writes record.tex
    _append_availability(run_dir)  # deposit now carries BOTH elements

    report = verify_run(run_dir)
    assert report.deposit_problems == []
    assert report.deposit_complete is True


# ---------------------------------------------------------------------------
# AC-C2 [RECORD-SIDE] -- missing record artifact FAILS LOUD, naming it (REQ-SA-302).
# ---------------------------------------------------------------------------

def test_verify_missing_record_artifact_fails_loud(tmp_path):
    spec = _numeric_spec("m2-no-record", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    deposit_record_path(run_dir).unlink()  # remove the deposit's record artifact

    report = verify_run(run_dir)
    assert report.deposit_complete is False
    assert any("record.tex" in p for p in report.deposit_problems)


# ---------------------------------------------------------------------------
# AC-C3 [RECORD-SIDE] -- missing availability statement FAILS LOUD, naming it (REQ-SA-303).
# ---------------------------------------------------------------------------

def test_verify_missing_availability_statement_fails_loud(tmp_path):
    spec = _numeric_spec("m2-no-avail", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    # record.tex exists (compiler wrote it) but no availability statement was authored.

    report = verify_run(run_dir)
    assert report.deposit_complete is False
    assert any("availability" in p.lower() for p in report.deposit_problems)


# ---------------------------------------------------------------------------
# AC-C5 [RECORD-SIDE] -- ADDITIVE: the existing record-green audit is unchanged and still
# gates (REQ-SA-305). The deposit check only EXTENDS the report; all_reproduced is untouched.
# ---------------------------------------------------------------------------

def test_deposit_check_is_additive_to_record_green_audit(tmp_path):
    spec = _numeric_spec("m2-additive", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))  # green record reproduction
    # An INCOMPLETE deposit (no availability statement) does NOT weaken the claim-
    # reproduction signal -- the record still re-derives. The deposit check is a separate,
    # additive channel.
    report = verify_run(run_dir)
    assert report.all_reproduced is True            # record-green audit UNCHANGED
    assert report.deposit_complete is False         # the additive deposit channel fired
    assert report.deposit_problems                  # ... and surfaced its problem line(s)


# ---------------------------------------------------------------------------
# AC-C4 (CLI surface) -- the deposit channel is not just a report field; `sci-adk verify`
# actually SURFACES it to the user. A complete deposit prints the "deposit complete" line
# on stdout; an incomplete one is surfaced on stderr as an ADVISORY that does NOT flip the
# exit code while the record reproduces. Characterization of the per-run CLI wiring.
# ---------------------------------------------------------------------------

def test_cli_verify_surfaces_complete_deposit(tmp_path, capsys):
    from sci_adk.cli import main

    spec = _numeric_spec("m2-cli-complete", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _append_availability(run_dir)  # deposit carries record.tex + availability statement

    main(["verify", str(run_dir)])
    out = capsys.readouterr().out
    assert "deposit complete" in out  # the user actually sees the deposit-completeness result


def test_cli_verify_surfaces_incomplete_deposit_as_advisory(tmp_path, capsys):
    from sci_adk.cli import main

    spec = _numeric_spec("m2-cli-incomplete", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    # record.tex exists but no availability statement -> deposit INCOMPLETE. Surfaced on stderr
    # as an ADVISORY that says "not gated" -- the user is warned. (The exit code is decided by
    # the record-green/consistency gates, NOT this channel; its non-gating nature is pinned at
    # the report level in test_deposit_check_is_additive_to_record_green_audit above.)
    main(["verify", str(run_dir)])
    err = capsys.readouterr().err
    assert "deposit INCOMPLETE" in err
    assert "advisory -- not gated" in err
    assert "availability" in err.lower()  # the missing element is named
