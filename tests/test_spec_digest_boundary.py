"""
§6.1 spec-digest boundary guard (design/sci-adk-as-moai.md §6.1).

Every worker prompt carries a ``[FROZEN SPEC REFERENCE]`` block with a ``spec_digest``.
When a worker invokes a record-advancing CLI verb (``append-evidence`` /
``derive-claim``), the CLI compares the passed ``--spec-digest`` against the on-disk
``runs/<id>/spec.json`` digest; a mismatch raises ``SpecDigestMismatch`` and the verb
exits non-zero -- so a worker cannot silently advance past a Spec it tampered with.

These tests pin three properties:

  - the ``spec_digest`` primitive: deterministic, cosmetic-JSON-invariant, content-
    sensitive; ``spec_digest_of_run`` loads spec.json (FileNotFoundError when absent).
  - the digest is EMITTED by ``init-spec`` / ``amend-spec`` (so the orchestrator can
    capture it) and an amendment CHANGES it.
  - the boundary on ``append-evidence`` / ``derive-claim``: correct digest -> succeeds;
    wrong digest -> exit 2 + nothing written; absent digest -> succeeds (backward-compat,
    NO check -- the lenient-when-absent rule).

All no-LLM / no-Docker: the numeric Spec resolves its Claim autonomously and the
Evidence is injected deterministically (fixtures reused from the verb-decomposition
suite -- single source of truth).
"""

from __future__ import annotations

import json

import pytest

from sci_adk.cli import main
from sci_adk.core.spec import Spec
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.provenance import (
    SpecDigestMismatch,
    spec_digest,
    spec_digest_of_run,
)

# Reuse the canonical numeric-spec + deterministic-evidence fixtures verbatim: the
# numeric THRESHOLD rule resolves autonomously (no agent checkpoint), referent='formal'
# + non_circularity satisfy the evidence-validity gate, and the fixed id/timestamp make
# the run reproducible. Importing (not re-defining) keeps a single source of truth.
from tests.test_cli_verb_decomposition import (  # noqa: E402
    _HYP_ID,
    _deterministic_evidence,
    _numeric_spec,
)


# -- helpers -----------------------------------------------------------------

def _seed_run(tmp_path, spec_id: str = "digest-spec"):
    """init-spec a numeric Spec into a fresh run dir; return (run_dir, spec)."""
    spec = _numeric_spec(spec_id)
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    return tmp_path / "runs" / spec_id, spec


def _write_evidence_file(tmp_path, spec):
    """Serialize the deterministic EvidenceItem to a JSON file for append-evidence."""
    item = _deterministic_evidence(spec)
    ev_file = tmp_path / "evidence_in.json"
    ev_file.write_text(
        json.dumps(item.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return ev_file


# -- (a) the spec_digest primitive -------------------------------------------

def test_spec_digest_is_deterministic():
    """Same Spec -> same digest across repeated calls (a pure function of the Spec)."""
    spec = _numeric_spec("s")
    assert spec_digest(spec) == spec_digest(spec)


def test_spec_digest_invariant_to_cosmetic_json():
    """Re-serializing the SAME Spec through a round-trip leaves the digest unchanged.

    Canonicalization goes through the typed Spec model with sorted keys, so the digest
    ignores on-disk key order / whitespace -- a Spec reloaded from any cosmetic JSON
    rendering yields the identical digest.
    """
    spec = _numeric_spec("s")
    # A reordered-keys, re-indented JSON rendering of the SAME Spec.
    payload = spec.model_dump(mode="json")
    cosmetic = json.dumps(payload, sort_keys=False, indent=4)
    reordered = json.dumps(json.loads(cosmetic), sort_keys=True)  # different byte layout
    reloaded = Spec.model_validate(json.loads(reordered))
    assert spec_digest(reloaded) == spec_digest(spec)


def test_spec_digest_sensitive_to_content_change():
    """Any content change (here: the version field) changes the digest."""
    spec = _numeric_spec("s")
    bumped = spec.model_copy(update={"version": spec.version + 1})
    assert spec_digest(bumped) != spec_digest(spec)


def test_two_different_specs_have_different_digests():
    """Two Specs that differ (here: the id) hash differently."""
    assert spec_digest(_numeric_spec("a")) != spec_digest(_numeric_spec("b"))


def test_spec_digest_of_run_matches_spec_digest(tmp_path):
    """``spec_digest_of_run`` loads spec.json and equals ``spec_digest`` of that Spec."""
    run_dir, spec = _seed_run(tmp_path)
    assert spec_digest_of_run(run_dir) == spec_digest(spec)


def test_spec_digest_of_run_missing_spec_raises(tmp_path):
    """A run dir with no spec.json -> FileNotFoundError (mirrors record_digest)."""
    empty = tmp_path / "runs" / "nope"
    empty.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        spec_digest_of_run(empty)


# -- (b) init-spec / amend-spec emit the digest ------------------------------

def test_init_spec_cli_prints_spec_digest(tmp_path, capsys):
    """The real ``sci-adk init-spec`` verb prints a ``spec_digest:`` line on stdout."""
    rc = main(["init-spec", "--t1-demo", "-o", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "spec_digest:" in out, "init-spec did not print a spec_digest line"
    # the printed digest is the real 64-hex digest of the frozen Spec on disk.
    digest = _extract_digest_line(out)
    # find the run dir the verb just created (single runs/* dir).
    run_dir = next((tmp_path / "runs").iterdir())
    assert digest == spec_digest_of_run(run_dir)


def test_amend_spec_changes_the_digest(tmp_path, capsys):
    """``amend-spec`` prints a ``spec_digest:`` line that DIFFERS from the pre-amend one."""
    rc = main(["init-spec", "--t1-demo", "-o", str(tmp_path)])
    assert rc == 0
    before = _extract_digest_line(capsys.readouterr().out)
    run_dir = next((tmp_path / "runs").iterdir())

    rc = main(["amend-spec", str(run_dir), "--rationale", "tighten the threshold"])
    assert rc == 0
    after = _extract_digest_line(capsys.readouterr().out)
    assert after != before, "an amendment must change the spec digest"
    assert after == spec_digest_of_run(run_dir), "printed digest != on-disk digest"


def _extract_digest_line(out: str) -> str:
    """Pull the 64-hex sha256 from the first ``spec_digest:`` line of CLI output."""
    for line in out.splitlines():
        if "spec_digest:" in line:
            return line.split("spec_digest:", 1)[1].strip()
    raise AssertionError(f"no spec_digest line in output:\n{out}")


# -- (c) the boundary check on append-evidence -------------------------------

def test_append_evidence_correct_digest_succeeds(tmp_path):
    """A correct ``--spec-digest`` passes the boundary and writes the Evidence (exit 0)."""
    run_dir, spec = _seed_run(tmp_path)
    ev_file = _write_evidence_file(tmp_path, spec)
    rc = main([
        "append-evidence", str(run_dir), "--evidence", str(ev_file),
        "--spec-digest", spec_digest(spec),
    ])
    assert rc == 0
    assert (run_dir / "evidence" / "evi-fixed-0001.json").exists()


def test_append_evidence_wrong_digest_blocks_and_writes_nothing(tmp_path, capsys):
    """A wrong ``--spec-digest`` exits 2 and writes NO Evidence (the boundary holds)."""
    run_dir, spec = _seed_run(tmp_path)
    ev_file = _write_evidence_file(tmp_path, spec)
    rc = main([
        "append-evidence", str(run_dir), "--evidence", str(ev_file),
        "--spec-digest", "0" * 64,  # deliberately wrong
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "error:" in err and "digest" in err.lower()
    assert not (run_dir / "evidence" / "evi-fixed-0001.json").exists(), (
        "Evidence was written despite a spec-digest mismatch (check ran too late)"
    )


def test_append_evidence_absent_digest_skips_check(tmp_path):
    """No ``--spec-digest`` -> NO check (backward-compat lenient-when-absent), exit 0."""
    run_dir, spec = _seed_run(tmp_path)
    ev_file = _write_evidence_file(tmp_path, spec)
    rc = main(["append-evidence", str(run_dir), "--evidence", str(ev_file)])
    assert rc == 0
    assert (run_dir / "evidence" / "evi-fixed-0001.json").exists()


def test_append_evidence_uppercase_digest_passes(tmp_path):
    """A CORRECT digest passed UPPER-CASED still passes the boundary (exit 0, written).

    sha256 hexdigest is lowercase and init/amend emit lowercase, but a frozen-reference
    value injected as text could arrive upper-cased or padded; the check normalizes the
    passed digest (case + whitespace) so a correct-but-shouty value is not a false block.
    """
    run_dir, spec = _seed_run(tmp_path)
    ev_file = _write_evidence_file(tmp_path, spec)
    rc = main([
        "append-evidence", str(run_dir), "--evidence", str(ev_file),
        "--spec-digest", f"  {spec_digest(spec).upper()}  ",  # upper + padded
    ])
    assert rc == 0
    assert (run_dir / "evidence" / "evi-fixed-0001.json").exists()


# -- (c) the boundary check on derive-claim ----------------------------------

def _seed_run_with_evidence(tmp_path, spec_id: str = "digest-spec"):
    """init-spec + append the deterministic Evidence so derive-claim has a record."""
    run_dir, spec = _seed_run(tmp_path, spec_id)
    ev_file = _write_evidence_file(tmp_path, spec)
    assert main(["append-evidence", str(run_dir), "--evidence", str(ev_file)]) == 0
    return run_dir, spec


def test_derive_claim_correct_digest_succeeds(tmp_path):
    """A correct ``--spec-digest`` passes the boundary and derives the Claim (exit 0)."""
    run_dir, spec = _seed_run_with_evidence(tmp_path)
    rc = main([
        "derive-claim", str(run_dir), "--no-strict-science",
        "--spec-digest", spec_digest(spec),
    ])
    assert rc == 0
    assert (run_dir / "claims" / f"claim-{_HYP_ID}.json").exists()


def test_derive_claim_wrong_digest_blocks_and_writes_nothing(tmp_path, capsys):
    """A wrong ``--spec-digest`` exits 2 and derives NO Claim (the boundary holds)."""
    run_dir, _spec = _seed_run_with_evidence(tmp_path)
    rc = main([
        "derive-claim", str(run_dir), "--no-strict-science",
        "--spec-digest", "0" * 64,  # deliberately wrong
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "error:" in err and "digest" in err.lower()
    assert not (run_dir / "claims" / f"claim-{_HYP_ID}.json").exists(), (
        "a Claim was derived despite a spec-digest mismatch (check ran too late)"
    )


def test_derive_claim_absent_digest_skips_check(tmp_path):
    """No ``--spec-digest`` -> NO check (backward-compat lenient-when-absent), exit 0."""
    run_dir, _spec = _seed_run_with_evidence(tmp_path)
    rc = main(["derive-claim", str(run_dir), "--no-strict-science"])
    assert rc == 0
    assert (run_dir / "claims" / f"claim-{_HYP_ID}.json").exists()


def test_derive_claim_uppercase_digest_passes(tmp_path):
    """A CORRECT digest passed UPPER-CASED still passes the boundary (exit 0, derived).

    Same normalization guarantee as append-evidence: a correct-but-shouty/padded
    frozen-reference value must not be a false block at the derive-claim boundary.
    """
    run_dir, spec = _seed_run_with_evidence(tmp_path)
    rc = main([
        "derive-claim", str(run_dir), "--no-strict-science",
        "--spec-digest", f"  {spec_digest(spec).upper()}  ",  # upper + padded
    ])
    assert rc == 0
    assert (run_dir / "claims" / f"claim-{_HYP_ID}.json").exists()


# -- the integration tamper scenario -----------------------------------------

def test_tampered_spec_on_disk_is_caught_by_the_boundary(tmp_path, capsys):
    """Freeze a Spec, capture its digest, edit spec.json on disk, then append-evidence
    with the OLD digest -> exit 2.

    This is the §6.1 threat directly: the worker holds the frozen digest, the Spec on
    disk was silently revised, and the next record-advancing verb refuses to proceed.
    """
    run_dir, spec = _seed_run(tmp_path)
    frozen_digest = spec_digest(spec)  # what the worker's [FROZEN SPEC REFERENCE] holds
    ev_file = _write_evidence_file(tmp_path, spec)

    # Silently revise spec.json on disk (a tampered goal -- exactly what §6.1 guards).
    spec_path = run_dir / "spec.json"
    on_disk = json.loads(spec_path.read_text(encoding="utf-8"))
    on_disk["raw_proposal"]["goal"] = "a different, silently-revised goal"
    spec_path.write_text(json.dumps(on_disk, indent=2), encoding="utf-8")

    # The on-disk digest now differs from the frozen one the worker carries.
    assert spec_digest_of_run(run_dir) != frozen_digest

    rc = main([
        "append-evidence", str(run_dir), "--evidence", str(ev_file),
        "--spec-digest", frozen_digest,  # the worker's now-stale frozen digest
    ])
    assert rc == 2, "the boundary did not catch a silently-revised Spec"
    assert not (run_dir / "evidence" / "evi-fixed-0001.json").exists()


def test_spec_digest_mismatch_carries_spec_id_and_truncated_digests():
    """``SpecDigestMismatch`` exposes spec_id + expected/actual and a readable message."""
    exc = SpecDigestMismatch(spec_id="s", expected="a" * 64, actual="b" * 64)
    assert exc.spec_id == "s"
    assert exc.expected == "a" * 64
    assert exc.actual == "b" * 64
    msg = str(exc)
    # the message names the Spec and hints the remedy without dumping full 64-char hashes.
    assert "s" in msg
    assert "a" * 64 not in msg and "b" * 64 not in msg  # truncated for readability
    # ...but it DOES surface the 12-char prefix of each digest (so the message is
    # diagnostic, not a degenerate empty __str__ that trivially satisfies the asserts above).
    assert "a" * 12 in msg, "message omits the expected-digest prefix"
    assert "b" * 12 in msg, "message omits the actual-digest prefix"
