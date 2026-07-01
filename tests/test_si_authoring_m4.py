"""
SPEC-SI-AUTHORING-001 Milestone M4 (RED-first): belief-side CHARACTERIZATION + the
end-to-end integration (the DoD). Design source: design/si-belief-record-split.md v0.4
(Pillar D + the §5 three-artifact compile path ① main.tex / ② si.tex / ③ record.tex).

Pillar D is CHARACTERIZATION -- it PROVES the FOUR already-covering belief-side checkers
are UNCHANGED in computation now that ``si.tex`` is AUTHORED belief (M3), not a dump:

  - REQ-SA-401 (AC-D1): ``si.tex`` is still audited as a manuscript by the SAME four
    checkers as ``draft.tex`` -- P2 number-audit, value-fidelity residual scan,
    ref-consistency, novelty -- with NO new gate computation for those four.
  - REQ-SA-402 (AC-D2): the EXISTING P2 number-audit now does REAL work on AUTHORED
    numbers -- an authored ``si.tex`` with an UNBACKED number FAILS the existing P2
    (the same checker that passed trivially over the old dump), no change to what P2
    computes (only its now-authored input differs).
  - REQ-SA-403 (AC-D3): the cross-doc S-ref gate (``check_cross_doc_s_refs``) still
    guards linkage between ``draft.tex`` and ``si.tex``; NO ``xr``/``zref-xr`` is
    introduced (no compile-coupling).
  - REQ-SA-404 (AC-D4): the ONLY belief-side computation change is the authorized M1
    per-run tool-vocab extension to ``si.tex`` (``record.tex`` exempt); the four
    characterization checkers iterate exactly ``("draft.tex", "si.tex")`` and add no
    new computation -- byte-unchanged in what they compute.
  - REQ-SA-205 (AC-B5): the relocation dropped NO audit from ``si.tex`` -- all four gates
    still cover the now-authored ``si.tex``.

End-to-end (the DoD, plan.md M4 exit): the full compile path runs -- the per-run
``stage_render``/``compile`` emits ① ``paper/draft.tex`` (authored) AND ② ``paper/si.tex``
(the AUTHORED overflow via ``render_authored_si_latex``), and the compiler emits ③ the
deposit ``record.tex``. ``sci-adk verify`` exits 0 on a complete, consistent deposit
(① + ② + ③ + a "Data & code availability" statement).

These tests are PURE/deterministic (no Docker, no LLM) unless a test explicitly compiles.
"""

from __future__ import annotations

from pathlib import Path

from sci_adk.loop.compiler import ResearchCompiler, deposit_record_path
from sci_adk.loop.verify import (
    _PAPER_DOCS,
    _check_cross_doc_refs,
    _check_paper_consistency,
    _check_paper_factrefs,
    _check_paper_novelty,
    verify_run,
)

# Reuse the established verify harness (a real compile + green numeric reproduction) and the
# record fixtures -- the characterization must hold over the SAME inputs the existing gate
# tests use, not a bespoke one.
from tests.test_verify import (
    _freeze_minimal_pubreqs,
    _numeric_experiment,
    _numeric_spec,
    _seed,
    _write_paper,
)


_AVAILABILITY = (
    r"\section{Data \& code availability}"
    "\nThe full record is deposited; run \\texttt{sci-adk verify <run>} to re-derive it.\n"
)


def _append_availability(run_dir: Path) -> None:
    """Author the deposit's "Data & code availability" statement into ``record.tex`` (the
    deposit-side text spine the compiler wrote). Read via ``deposit_record_path`` -- the M1
    single source of truth, never a hard-coded path (matches M2's test helper)."""
    record = deposit_record_path(run_dir)
    record.write_text(
        record.read_text(encoding="utf-8") + "\n" + _AVAILABILITY, encoding="utf-8"
    )


# ===========================================================================
# REQ-SA-401 / AC-D1 [CHARACTERIZATION] -- the FOUR checkers still cover si.tex,
# no new computation. The four read-only checkers iterate _PAPER_DOCS and include
# si.tex; an authored si.tex is scanned by the SAME four checkers as draft.tex.
# ===========================================================================

def test_paper_docs_includes_si_tex_unchanged():
    # The four characterization checkers all iterate this tuple. It is EXACTLY the two
    # submission documents -- si.tex is in scope, no third doc, record.tex is NOT here.
    assert _PAPER_DOCS == ("draft.tex", "si.tex")


def test_four_checkers_scan_authored_si_tex(tmp_path):
    """AC-D1: an authored si.tex on disk is scanned by the SAME four read-only checkers as
    draft.tex (ref-consistency, value-fidelity residual, novelty) -- the same wiring, no
    new computation. (P2 is exercised separately in AC-D2.)"""
    spec = _numeric_spec("m4-d1", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    # A clean authored si.tex with an internal \ref/\label pair.
    _write_paper(run_dir, "si.tex", r"\label{tab:s1} See Table~\ref{tab:s1}.")

    # ref-consistency: si.tex is a key in the per-document report map.
    consistency = _check_paper_consistency(run_dir)
    assert "si.tex" in consistency
    assert consistency["si.tex"].ok is True

    # value-fidelity residual scan: a clean si.tex carries no residual \evval/\status.
    factrefs = _check_paper_factrefs(run_dir)
    assert "si.tex" not in factrefs  # clean -> not in the residual map

    # novelty: a novelty-free si.tex contributes no problems.
    novelty = _check_paper_novelty(run_dir, spec, [])
    assert "si.tex" not in novelty


def test_value_fidelity_residual_still_catches_si_tex(tmp_path):
    """AC-D1 (value-fidelity): a RESIDUAL \\evval in an authored si.tex (substitution
    bypassed / hand-edited) is still caught -- the SAME residual scan that covers draft.tex,
    no new computation."""
    spec = _numeric_spec("m4-d1-resid", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    # A residual fidelity macro that should never survive a real render.
    _write_paper(run_dir, "si.tex", r"The value is \evval{ev-x}{point}.")
    factrefs = _check_paper_factrefs(run_dir)
    assert "si.tex" in factrefs
    assert any("evval" in r for r in factrefs["si.tex"])


# ===========================================================================
# REQ-SA-402 / AC-D2 [CHARACTERIZATION] -- the EXISTING P2 does REAL work on the
# AUTHORED si.tex: an unbacked number FAILS the existing P2 number-audit.
# ===========================================================================

def test_existing_p2_fails_on_unbacked_number_in_authored_si(tmp_path):
    """AC-D2: an authored si.tex stating a quantitative token with NO backing in the
    recorded-value pool FAILS the EXISTING P2 number-audit (the same checker that passed
    trivially over the old dump now does real work). No change to what P2 computes."""
    spec = _numeric_spec("m4-d2", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _freeze_minimal_pubreqs(run_dir)  # a conclusion-bearing draft.tex needs a contract
    # draft.tex is clean (the compiler-rendered one stays). Author an si.tex stating a
    # number the record does not hold (0.95 is the recorded point; 7.77 is unbacked).
    _write_paper(run_dir, "si.tex", r"\label{tab:s1} The supplementary value is 7.77.")
    report = verify_run(run_dir)
    # The EXISTING P2 number-audit (already wired over si.tex) flags the unbacked token.
    assert any(
        "7.77" in p and "si.tex" in p for p in report.paper_requirements_problems
    ), report.paper_requirements_problems
    assert report.paper_requirements_clean is False
    assert report.passed is False  # the belief-side gate does real work on authored numbers


def test_p2_passes_when_authored_si_only_states_recorded_numbers(tmp_path):
    """AC-D2 boundary: an authored si.tex that states ONLY recorded numbers (the threshold
    0.9 and the recorded point 0.95) passes the existing P2 -- the gate is not over-eager."""
    spec = _numeric_spec("m4-d2-ok", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _freeze_minimal_pubreqs(run_dir)
    _write_paper(
        run_dir, "si.tex",
        r"\label{tab:s1} Threshold 0.9; recorded point 0.95.",
    )
    report = verify_run(run_dir)
    # No si.tex number-audit problem (every token traces to the recorded pool).
    assert not any("si.tex" in p for p in report.paper_requirements_problems), \
        report.paper_requirements_problems


# ===========================================================================
# REQ-SA-403 / AC-D3 [CHARACTERIZATION] -- the cross-doc S-ref gate still guards
# linkage; NO xr/zref-xr compile coupling introduced.
# ===========================================================================

def test_cross_doc_s_ref_gate_still_flags_dangling(tmp_path):
    """AC-D3: a draft.tex citing "Figure S5" while the authored si.tex has only N SI figures
    is flagged by the cross-doc S-ref gate -- the linkage guard is unchanged."""
    spec = _numeric_spec("m4-d3", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    # draft cites Figure S5; the authored si.tex defines only a single SI figure float.
    _write_paper(run_dir, "draft.tex", r"As shown in Figure S5, the property holds.")
    _write_paper(
        run_dir, "si.tex",
        "\\begin{figure}\n\\caption{only one SI figure}\n\\end{figure}\n",
    )
    dangling = _check_cross_doc_refs(run_dir)
    assert "Figure S5" in dangling


def test_no_xr_or_zref_xr_introduced():
    """AC-D3: NO cross-document compile-coupling package is introduced anywhere in the
    render layer -- linkage stays plain-text S-refs + the cross-doc gate (design §6)."""
    render_dir = Path(__file__).resolve().parents[1] / "src" / "sci_adk" / "render"
    offenders = []
    for py in render_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        # A LaTeX cross-reference package would be emitted as \usepackage{xr} / {zref-xr}.
        if r"\usepackage{xr}" in text or r"\usepackage{zref-xr}" in text:
            offenders.append(py.name)
    assert offenders == [], f"xr/zref-xr compile coupling found in: {offenders}"


# ===========================================================================
# REQ-SA-404 / AC-D4 [CHARACTERIZATION] -- the ONLY belief-side computation change is
# the authorized M1 per-run tool-vocab extension; the four checkers add no new computation.
# ===========================================================================

def test_four_checkers_iterate_only_the_two_submission_docs(tmp_path):
    """AC-D4: the four characterization checkers (ref-consistency, value-fidelity, novelty,
    plus P2's _PAPER_DOCS loop) operate over EXACTLY ("draft.tex", "si.tex") -- they neither
    drop si.tex nor reach for a third document, so their computation is unchanged in scope."""
    spec = _numeric_spec("m4-d4", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a}")
    _write_paper(run_dir, "si.tex", r"\label{tab:s1}\ref{tab:s1}")
    # The per-document report keys are a SUBSET of _PAPER_DOCS (only present files), never a
    # superset -- no checker invented a third document or a new axis.
    consistency = _check_paper_consistency(run_dir)
    assert set(consistency).issubset(set(_PAPER_DOCS))
    assert set(consistency) == {"draft.tex", "si.tex"}


# ===========================================================================
# REQ-SA-205 / AC-B5 [CHARACTERIZATION] -- the relocation dropped NO audit from si.tex.
# All four gates still cover the now-authored si.tex (the relocation freed the slot but
# kept the coverage).
# ===========================================================================

def test_relocation_dropped_no_audit_from_si_tex(tmp_path):
    """AC-B5: after the dump moved out of the si.tex slot (M1), the now-authored si.tex is
    STILL covered by fidelity (residual), ref-consistency, novelty, AND P2 -- a broken
    si.tex fails the combined gate exactly as a broken draft would."""
    spec = _numeric_spec("m4-b5", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _freeze_minimal_pubreqs(run_dir)
    _write_paper(run_dir, "draft.tex", r"\label{fig:a}\ref{fig:a}")  # draft clean
    # An si.tex with a dangling \ref (ref-consistency) -- a coverage that the relocation
    # must NOT have dropped.
    _write_paper(run_dir, "si.tex", r"Table~\ref{tab:ghost}.")
    report = verify_run(run_dir)
    assert report.paper_consistency["si.tex"].ok is False
    assert report.paper_consistency["si.tex"].unresolved_refs == ["tab:ghost"]
    assert report.paper_consistent is False
    assert report.passed is False  # the si.tex coverage still gates


# ===========================================================================
# END-TO-END INTEGRATION (the DoD) -- the full ①+②+③ compile path on a REAL run,
# and sci-adk verify exits 0 on a complete, consistent deposit.
# ===========================================================================

def test_compile_emits_authored_si_tex_alongside_record(tmp_path):
    """The DoD wiring: stage_render/compile, given an AuthoredSI, emits ② paper/si.tex via
    render_authored_si_latex (NOT the record dump) AND ③ the deposit record.tex, while ①
    paper/draft.tex stays the authored main paper. The three artifacts co-exist."""
    from sci_adk.render.prose import AuthoredSI, SISection

    spec = _numeric_spec("m4-e2e", value=0.9)
    workspace = tmp_path
    run_dir = _seed(workspace, spec, _numeric_experiment(0.95))  # ① + ③ already on disk

    si = AuthoredSI(
        title="Supplementary information",
        sections=[
            SISection(
                title="Supplementary Notes",
                body="The overflow detail. The recorded point is "
                     r"\evval{ev-num}{point}.",
            )
        ],
    )
    compiler = ResearchCompiler(workspace_dir=workspace)
    paper_path, si_path_ret, record_path, _fc = compiler.stage_render(spec, si=si)

    # ① the authored main paper.
    assert paper_path == run_dir / "paper" / "draft.tex"
    assert paper_path.is_file()
    # ② the AUTHORED si.tex (overflow) -- produced by the prose pipeline, NOT the dump.
    si_path = run_dir / "paper" / "si.tex"
    assert si_path_ret == si_path
    assert si_path.is_file()
    si_text = si_path.read_text(encoding="utf-8")
    assert r"\section{Supplementary Notes}" in si_text
    # \evval was substituted to the recorded value (fidelity), not left as a macro.
    assert r"\evval" not in si_text
    assert "0.95" in si_text  # the recorded point, faithfully substituted
    # It is NOT the record dump (no type-sorted record sections).
    assert r"\section{Evidence record}" not in si_text
    # ③ the deposit record.tex (the relocated dump) is still emitted separately.
    assert record_path == deposit_record_path(run_dir)
    assert record_path.is_file()
    assert r"\section{Evidence record}" in record_path.read_text(encoding="utf-8")


def test_compile_with_no_si_emits_no_si_tex(tmp_path):
    """REQ-SA-107 / EC-1: a thin/absent SI is permitted -- with no AuthoredSI supplied, the
    compiler emits ① + ③ and NO paper/si.tex (backward compatible with M1)."""
    spec = _numeric_spec("m4-thin", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    paper_path, si_path_ret, record_path, _fc = compiler.stage_render(spec)  # no si=
    assert paper_path.is_file()
    assert si_path_ret is None
    assert not (run_dir / "paper" / "si.tex").exists()
    assert record_path.is_file()


def test_compile_records_si_path_when_authored(tmp_path):
    """The compile() result carries si_path when an AuthoredSI is supplied (M1 set it to
    None; M4 fills it when ② is authored)."""
    from sci_adk.render.prose import AuthoredSI, SISection

    spec = _numeric_spec("m4-sipath", value=0.9)
    compiler = ResearchCompiler(workspace_dir=tmp_path)
    si = AuthoredSI(sections=[SISection(title="Notes", body="overflow.")])
    result = compiler.compile(
        "", spec=spec, experiment=_numeric_experiment(0.95), si=si
    )
    assert result.si_path is not None
    assert result.si_path.is_file()
    assert result.si_path == result.run_dir / "paper" / "si.tex"
    assert result.record_path is not None


def test_cli_run_si_flag_emits_authored_si_tex(tmp_path):
    """The CLI `run --si <json>` flag (the /sci publish path) loads an AuthoredSI and the
    compiler emits ② paper/si.tex through render_authored_si_latex (NOT the dump). A
    free-text proposal (no recorded numbers) + a plain authored SI keeps the test
    self-contained -- it exercises the FLAG -> emit wiring end to end through main()."""
    import json as _json

    from sci_adk.cli import main
    from tests.test_render_merge_wiring import PROPOSAL

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    si_json = tmp_path / "si.json"
    si_json.write_text(
        _json.dumps({
            "title": "Supplementary information",
            "sections": [
                {"title": "Supplementary Notes", "body": "An offline overflow note."}
            ],
        }),
        encoding="utf-8",
    )

    rc = main([
        "run", str(proposal), "-o", str(tmp_path),
        "--spec-id", "t-cli-si", "--si", str(si_json),
    ])
    assert rc == 0

    si_path = tmp_path / "runs" / "t-cli-si" / "paper" / "si.tex"
    assert si_path.exists()
    si_text = si_path.read_text(encoding="utf-8")
    # Authored (prose pipeline) -> the agent's section, NOT the dump's record sections.
    assert r"\section{Supplementary Notes}" in si_text
    assert "An offline overflow note." in si_text
    assert r"\section{Evidence record}" not in si_text  # not the dump
    # ③ the deposit record dump is still emitted separately (the dump's sections live there).
    record = (tmp_path / "runs" / "t-cli-si" / "record.tex").read_text(encoding="utf-8")
    assert r"\section{Evidence record}" in record


def test_cli_run_without_si_emits_no_si_tex(tmp_path):
    """Backward compatible: `run` with NO --si emits no paper/si.tex (thin/absent SI)."""
    from sci_adk.cli import main
    from tests.test_render_merge_wiring import PROPOSAL

    proposal = tmp_path / "proposal.md"
    proposal.write_text(PROPOSAL, encoding="utf-8")
    rc = main(["run", str(proposal), "-o", str(tmp_path), "--spec-id", "t-cli-nosi"])
    assert rc == 0
    assert not (tmp_path / "runs" / "t-cli-nosi" / "paper" / "si.tex").exists()
    assert (tmp_path / "runs" / "t-cli-nosi" / "record.tex").exists()


def test_end_to_end_verify_exits_zero_on_complete_deposit(tmp_path):
    """The DoD exit: a full compile (① authored, ② authored, ③ record deposit) + a complete
    deposit (availability statement present) -> sci-adk verify exits 0 (report.passed True
    AND deposit_complete True)."""
    from sci_adk.render.prose import AuthoredSI, SISection

    spec = _numeric_spec("m4-verify0", value=0.9)
    workspace = tmp_path
    run_dir = _seed(workspace, spec, _numeric_experiment(0.95))

    # ② authored si.tex -- internally consistent + every number recorded (the threshold 0.9
    # and the recorded point 0.95) so P2 + ref-consistency + cross-doc all pass.
    si = AuthoredSI(
        title="Supplementary information",
        sections=[
            SISection(
                title="Supplementary Notes",
                body=(
                    "The recorded point estimate is "
                    r"\evval{ev-num}{point} against threshold 0.9."
                ),
            )
        ],
    )
    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_render(spec, si=si)

    # The publishing contract (P1) + the deposit availability statement (M2) complete the
    # deposit so verify's combined gate passes.
    _freeze_minimal_pubreqs(run_dir)
    _append_availability(run_dir)

    report = verify_run(run_dir)
    # ① + ② both present and consistent; ③ + availability statement present.
    assert (run_dir / "paper" / "draft.tex").is_file()
    assert (run_dir / "paper" / "si.tex").is_file()
    assert deposit_record_path(run_dir).is_file()
    assert report.all_reproduced is True
    assert report.paper_consistent is True
    assert report.paper_tool_clean is True
    assert report.paper_factref_clean is True
    assert report.paper_cross_doc_clean is True
    assert report.paper_requirements_clean is True
    assert report.passed is True            # the combined belief-side exit gate
    assert report.deposit_complete is True  # the record-side deposit channel
