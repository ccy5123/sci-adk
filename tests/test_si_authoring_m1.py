"""
SPEC-SI-AUTHORING-001 Milestone M1 (RED-first): the deterministic dump is RELOCATED
into the deposit as ``record.tex`` and re-named from "Supporting Information" to the
"record", reusing ``render_si_latex`` VERBATIM (design/si-belief-record-split.md v0.4).

Pillar B requirements pinned here (renderer + compiler relocation level):
  - REQ-SA-201 (AC-B1): ``render_si_latex`` reused verbatim; determinism preserved
    (same inputs -> byte-identical output), logic unchanged except the identity wording.
  - REQ-SA-202 (AC-B2): the compiler writes the dump to the deposit as ``record.tex``,
    and the ``paper/si.tex`` slot is NO LONGER occupied by the dump (freed for M3).
  - REQ-SA-203 (AC-B3): the artifact's title/author/identity wording reads as the
    RECORD/provenance, not as an "Supporting Information" sibling of the paper.

The per-run tool-vocab extension (REQ-SA-204 / AC-B4) and the ``record.tex`` exemption
(REQ-SA-206 / AC-B6) are verify-level behaviors and are pinned in ``tests/test_verify.py``
(where the verify harness + helpers live).
"""

from __future__ import annotations

import importlib

from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.render.si import render_si_latex

# Reuse the established record fixtures from the existing SI test module (do not
# re-author them -- the M1 rename must hold over the SAME inputs the dump tests use).
from tests.test_si import _basic_record


# ---------------------------------------------------------------------------
# AC-B1 [RECORD-SIDE] -- render_si_latex reused verbatim, determinism preserved
# (REQ-SA-201). The relocation/rename must not touch the deterministic dump logic.
# ---------------------------------------------------------------------------

def test_record_dump_is_deterministic_byte_identical():
    spec, claims, evidence = _basic_record()
    first = render_si_latex(spec, claims, evidence)
    second = render_si_latex(spec, claims, evidence)
    assert first == second  # same inputs -> byte-identical (determinism unchanged)


def test_record_dump_logic_unchanged_modulo_identity_wording():
    """R3: the rename is presentation-only. Every record-bearing line of the dump (the
    Evidence record, the data table, the verdicts, the integrity line) is byte-identical
    to the dump body -- ONLY the title/author identity wording changed."""
    spec, claims, evidence = _basic_record()
    dump = render_si_latex(spec, claims, evidence)
    # The record SPINE is intact (these are the dump's load-bearing sections).
    assert r"\section{Evidence record}" in dump
    assert r"\section{Quantitative data}" in dump
    assert r"\section{Claims and verdicts}" in dump
    assert r"\section{Record integrity}" in dump
    # Every evidence id still appears (no record content lost in the rename).
    for ev in evidence:
        assert ev.id in dump


# ---------------------------------------------------------------------------
# AC-B3 [RECORD-SIDE] -- renamed "Supporting Information" -> the record (REQ-SA-203).
# The identity wording reads as the RECORD/provenance, not an SI sibling of the paper.
# ---------------------------------------------------------------------------

def test_record_dump_title_is_not_supporting_information():
    spec, claims, evidence = _basic_record()
    dump = render_si_latex(spec, claims, evidence)
    # The title no longer presents the artifact as "Supporting Information: ...".
    assert "Supporting Information" not in dump


def test_record_dump_author_line_is_not_an_si_sibling():
    spec, claims, evidence = _basic_record()
    dump = render_si_latex(spec, claims, evidence)
    # The author identity reads as the record/provenance, not "deterministic record
    # dump" framed as an SI -- the artifact is THE record.
    assert r"\author{sci-adk (deterministic record dump)}" not in dump


# ---------------------------------------------------------------------------
# AC-B2 [RECORD-SIDE] -- dump relocated to the deposit as record.tex (REQ-SA-202).
# The compiler writes the dump to the deposit's record.tex; the paper/si.tex slot is
# no longer occupied by the dump.
# ---------------------------------------------------------------------------

# Reuse the proper section-bearing proposal + the (spec, workspace_dir)-signed experiment
# the established compiler wiring tests use -- the relocation must hold over the SAME
# compile path, not a bespoke one.
from tests.test_render_merge_wiring import PROPOSAL as _PROPOSAL  # noqa: E402
from tests.test_render_merge_wiring import _point_experiment  # noqa: E402


def _deposit_record_path(run_dir):
    """The SINGLE SOURCE of the deposit record path -- imported from the compiler module
    so this test reads the relocation target, never hard-codes it (F4: one source of
    truth the M2 deposit-completeness checker also references)."""
    compiler_mod = importlib.import_module("sci_adk.loop.compiler")
    return compiler_mod.deposit_record_path(run_dir)


def test_compile_writes_record_to_the_deposit(tmp_path):
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        _PROPOSAL, spec_id="t-m1-record", experiment=_point_experiment)

    run_dir = tmp_path / "runs" / "t-m1-record"
    record_path = _deposit_record_path(run_dir)
    assert record_path.exists(), "the deterministic dump must land as the deposit record.tex"
    assert record_path.name == "record.tex"

    record = record_path.read_text(encoding="utf-8")
    # It IS the record dump (carries the run's evidence id + the standalone preamble).
    assert r"\documentclass{article}" in record
    assert r"\end{document}" in record
    assert "ev-pt-0" in record
    # And it reads as the record, not "Supporting Information".
    assert "Supporting Information" not in record


def test_compile_frees_the_si_tex_slot(tmp_path):
    """The paper/si.tex slot is freed for the authored overflow path (M3). After M1 the
    compiler relocates the dump to record.tex, so paper/si.tex is NOT the dump anymore."""
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        _PROPOSAL, spec_id="t-m1-free", experiment=_point_experiment)

    run_dir = tmp_path / "runs" / "t-m1-free"
    si_path = run_dir / "paper" / "si.tex"
    record_path = _deposit_record_path(run_dir)

    # The record dump is at the deposit, NOT at paper/si.tex.
    assert record_path.exists()
    if si_path.exists():
        # If a si.tex exists at all, it must NOT be the record dump (the dump moved out).
        si = si_path.read_text(encoding="utf-8")
        assert "deterministic dump of every Evidence item" not in si
    # The relocated dump path the compiler reports points at the deposit record.tex.
    assert result.record_path == record_path
