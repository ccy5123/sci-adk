"""
SPEC-SI-AUTHORING-001 Milestone M6 (RED-first): the authored ``si.tex`` (belief artifact ②)
gets its OWN ``references_SI.bib``, symmetric to how ``main.tex``/``draft.tex`` uses
``references.bib``.

Design source: design/si-bibliography.md (v1.1, FROZEN — the four confirmed decisions +
§2a mechanism clarifications). Pillar F requirements (REQ-SA-601..617), acceptance
scenarios AC-F1..F11 + edge cases EC-9..EC-12.

The four confirmed decisions this milestone encodes (design §2):
  1. cited-only subset from the SAME per-run pool (no separate SI acquisition);
  2. both compile paths (per-run + package), symmetric to ``main.tex``;
  3. a cite-resolution gate for ``si.tex`` vs ``references_SI.bib`` (REUSE the existing
     ``cite_resolution_problems`` checker — no new checker);
  4. design + SPEC first (done — this test file + the src change realize it).

All tests are PURE / deterministic / no-LLM (no Docker, no real compile).
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

# Reuse the established record + compiler fixtures (do not re-author them — the SI-bib
# wiring must hold over the SAME inputs the M1/M3 tests use).
from tests.test_si import _basic_record
from tests.test_render_merge_wiring import PROPOSAL as _PROPOSAL
from tests.test_render_merge_wiring import _point_experiment

from sci_adk.render.prose import AuthoredSI, SISection


# ---------------------------------------------------------------------------
# Helpers — a small literature pool + an authored SI citing a subset of it.
# ---------------------------------------------------------------------------

_POOL_BIB = (
    "@article{A2020, title={Alpha}, doi={10.1/a}}\n"
    "@article{B2021, title={Beta}, doi={10.1/b}}\n"
    "@article{C2022, title={Gamma}, doi={10.1/c}}\n"
)


def _seed_pool(run_dir: Path, bib: str = _POOL_BIB) -> None:
    """Place the run's ONE literature pool at artifacts/literature/references.bib.

    Mirrors tests/test_render_merge_wiring.py::test_compile_gathers_dois_from_manifest_and_wires_bib
    (the pool survives the compile loop when pre-created).
    """
    lit = run_dir / "artifacts" / "literature"
    lit.mkdir(parents=True, exist_ok=True)
    (lit / "references.bib").write_text(bib, encoding="utf-8")


def _si_citing(*keys: str, title: str = "Supplementary discussion") -> AuthoredSI:
    """An authored SI whose prose cites the given keys via ``\\citep{...}``."""
    if keys:
        body = "Extended discussion " + " ".join(f"\\citep{{{k}}}" for k in keys) + "."
    else:
        body = "Extended discussion with no citations."
    return AuthoredSI(title=title, sections=[SISection(title="Discussion", body=body)])


# ===========================================================================
# F.1 — Authored-SI renderer gains bib wiring (mirrors paper.py:831-834)
# ===========================================================================

# --- AC-F1: renderer emits \bibliography when a bib is supplied (REQ-SA-601/601a) ---

def test_renderer_accepts_bib_path_parameter():
    """REQ-SA-601: render_authored_si_latex gains an optional bib_path parameter."""
    from sci_adk.render.authored_si import render_authored_si_latex

    sig = inspect.signature(render_authored_si_latex)
    assert "bib_path" in sig.parameters
    # Optional (a default), symmetric to render_paper_latex's bib_path.
    assert sig.parameters["bib_path"].default is None


def test_renderer_emits_bibliography_when_bib_supplied():
    """AC-F1 / REQ-SA-601: a bib_path supplied -> \\bibliographystyle{plainnat} +
    \\bibliography{<stem>} before \\end{document}, so \\citep resolves not [?]."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = _si_citing("A2020")
    tex = render_authored_si_latex(
        si, spec, claims, evidence, bib_path="/somewhere/references_SI.bib"
    )
    assert r"\bibliographystyle{plainnat}" in tex
    assert r"\bibliography{references_SI}" in tex
    # emitted before \end{document}
    assert tex.index(r"\bibliography{references_SI}") < tex.index(r"\end{document}")


def test_renderer_bibliography_uses_the_bib_path_stem():
    """REQ-SA-601: the \\bibliography key is Path(bib_path).stem (like paper.py:832)."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = _si_citing("A2020")
    tex = render_authored_si_latex(
        si, spec, claims, evidence, bib_path="/x/y/custom_stem.bib"
    )
    assert r"\bibliography{custom_stem}" in tex


def test_renderer_stays_pure_no_filesystem_access(tmp_path):
    """REQ-SA-601a: the renderer is PURE — a bib_path that does NOT exist on disk is
    fine (the renderer never reads it; the caller supplies + co-locates the file)."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = _si_citing("A2020")
    missing = str(tmp_path / "does_not_exist" / "references_SI.bib")
    tex = render_authored_si_latex(si, spec, claims, evidence, bib_path=missing)
    assert r"\bibliography{references_SI}" in tex


def test_renderer_stays_fail_loud_on_unbacked_evval():
    """REQ-SA-601a: bib wiring adds NO new gate — an unbacked \\evval still FAILS LOUD."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = AuthoredSI(
        title="T",
        sections=[SISection(title="S", body=r"Value \evval{no-such-id}{point}.")],
    )
    with pytest.raises(ValueError):
        render_authored_si_latex(
            si, spec, claims, evidence, bib_path="/x/references_SI.bib"
        )


# --- AC-F2: no bib_path -> no \bibliography line (REQ-SA-602) ---

def test_renderer_no_bib_path_emits_no_bibliography():
    """AC-F2 / REQ-SA-602: no bib_path -> NO \\bibliography line (paper.py:835 branch)."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = _si_citing("A2020")  # cites, but no bib supplied
    tex = render_authored_si_latex(si, spec, claims, evidence)  # no bib_path
    assert r"\bibliography{" not in tex
    # natbib preamble line is present but harmless without a \bibliography.
    assert r"\usepackage{natbib}" in tex


# --- AC-F3: bib wiring preserves determinism + other slots (REQ-SA-603) ---

def test_renderer_determinism_with_bib():
    """AC-F3 / REQ-SA-603: same authored input + same bib_path -> byte-identical."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = _si_citing("A2020")
    first = render_authored_si_latex(
        si, spec, claims, evidence, bib_path="/x/references_SI.bib"
    )
    second = render_authored_si_latex(
        si, spec, claims, evidence, bib_path="/x/references_SI.bib"
    )
    assert first == second


def test_renderer_bib_wiring_only_appends_bibliography():
    """AC-F3 / REQ-SA-603: the WITH-bib render == the NO-bib render PLUS the two
    bibliography lines — no other slot changes (fidelity, novelty, S-numbering)."""
    from sci_adk.render.authored_si import render_authored_si_latex

    spec, claims, evidence = _basic_record()
    si = _si_citing("A2020")
    no_bib = render_authored_si_latex(si, spec, claims, evidence)
    with_bib = render_authored_si_latex(
        si, spec, claims, evidence, bib_path="/x/references_SI.bib"
    )
    # Everything up to \end{document} in the no-bib render appears unchanged in the
    # with-bib render (the bibliography lines are inserted before \end{document}).
    body_no_bib = no_bib.rsplit(r"\end{document}", 1)[0]
    assert body_no_bib in with_bib
    # And the S-numbering + natbib slots are byte-identical between the two.
    assert r"\renewcommand{\thefigure}{S\arabic{figure}}" in with_bib
    assert r"\usepackage{natbib}" in with_bib


# ===========================================================================
# F.2 — Compiler builds + co-locates the cited-only per-run references_SI.bib
# ===========================================================================

def _compile(tmp_path: Path, spec_id: str, si, *, seed_pool=True, pool_bib=_POOL_BIB):
    """Compile a run with an authored SI (+ optional literature pool)."""
    from sci_adk.loop.compiler import ResearchCompiler

    run_dir = tmp_path / "runs" / spec_id
    if seed_pool:
        _seed_pool(run_dir, pool_bib)
    result = ResearchCompiler(workspace_dir=tmp_path).compile(
        _PROPOSAL, spec_id=spec_id, experiment=_point_experiment, si=si
    )
    return run_dir, result


# --- AC-F4: per-run references_SI.bib is the cited-only subset of the ONE pool ---

def test_per_run_references_si_bib_is_cited_only_subset(tmp_path):
    """AC-F4 / EC-9 / REQ-SA-604/605: pool {A,B,C}, si cites {A,C} -> references_SI.bib
    has exactly {A2020, C2022} (the uncited B2021 is ABSENT)."""
    from sci_adk.render.pkgreqs_checks import bib_keys

    run_dir, _ = _compile(tmp_path, "t-m6-subset", _si_citing("A2020", "C2022"))
    si_bib = run_dir / "paper" / "references_SI.bib"
    assert si_bib.is_file(), "paper/references_SI.bib must be written when the SI cites"
    assert set(bib_keys(si_bib.read_text(encoding="utf-8"))) == {"A2020", "C2022"}


def test_per_run_si_tex_wires_references_si(tmp_path):
    """REQ-SA-604: the rendered per-run si.tex wires \\bibliography{references_SI}."""
    run_dir, _ = _compile(tmp_path, "t-m6-wire", _si_citing("A2020"))
    si_tex = (run_dir / "paper" / "si.tex").read_text(encoding="utf-8")
    assert r"\bibliography{references_SI}" in si_tex


def test_per_run_main_and_si_cite_different_subsets_are_independent(tmp_path):
    """AC-F6 / EC-9/EC-10 / REQ-SA-607/609: references.bib (main, full pool) and
    references_SI.bib (cited-only) are independent files; the main bib is the full pool."""
    from sci_adk.render.pkgreqs_checks import bib_keys

    run_dir, _ = _compile(tmp_path, "t-m6-indep", _si_citing("C2022"))
    main_bib = run_dir / "paper" / "references.bib"
    si_bib = run_dir / "paper" / "references_SI.bib"
    # main references.bib is the FULL co-located pool (unchanged by M6).
    assert set(bib_keys(main_bib.read_text(encoding="utf-8"))) == {"A2020", "B2021", "C2022"}
    # SI bib is the cited-only subset (only C2022 here — a ref the main paper need not cite).
    assert set(bib_keys(si_bib.read_text(encoding="utf-8"))) == {"C2022"}


def test_per_run_main_bib_byte_unchanged_by_m6(tmp_path):
    """AC-F6 / REQ-SA-607: the main paper's references.bib co-location is byte-unchanged
    (a faithful full-pool copy) — M6 does not touch main.tex/references.bib wiring."""
    run_dir, _ = _compile(tmp_path, "t-m6-mainbib", _si_citing("A2020"))
    main_bib = (run_dir / "paper" / "references.bib").read_text(encoding="utf-8")
    assert main_bib == _POOL_BIB  # faithful full-pool copy, unchanged


# --- AC-F5: no pool / no SI citations -> NO references_SI.bib written (REQ-SA-606) ---

def test_no_si_citations_writes_no_references_si_bib(tmp_path):
    """AC-F5 / EC-11 / REQ-SA-606 (D6 ABSENCE): a citation-free SI -> NO
    references_SI.bib file, and si.tex emits no \\bibliography."""
    run_dir, _ = _compile(tmp_path, "t-m6-nocite", _si_citing())  # cites nothing
    si_bib = run_dir / "paper" / "references_SI.bib"
    assert not si_bib.exists()
    si_tex = (run_dir / "paper" / "si.tex").read_text(encoding="utf-8")
    assert r"\bibliography{" not in si_tex


def test_no_pool_writes_no_references_si_bib(tmp_path):
    """AC-F5 / EC-12 boundary / REQ-SA-606 (D6): no literature pool (_locate_bib_path ->
    None) even though the SI cites -> NO references_SI.bib file written."""
    run_dir, _ = _compile(
        tmp_path, "t-m6-nopool", _si_citing("A2020"), seed_pool=False
    )
    si_bib = run_dir / "paper" / "references_SI.bib"
    assert not si_bib.exists()
    si_tex = (run_dir / "paper" / "si.tex").read_text(encoding="utf-8")
    assert r"\bibliography{" not in si_tex


def test_si_cites_key_absent_from_pool_not_silently_dropped(tmp_path):
    """AC-F5 / EC-12 / REQ-SA-606: si cites Z (not in pool {A,B,C}) -> references_SI.bib
    holds only the resolvable subset (no Z), and Z is NOT in the SI bib (it surfaces in
    the F.4 gate, tested separately)."""
    from sci_adk.render.pkgreqs_checks import bib_keys

    run_dir, _ = _compile(tmp_path, "t-m6-danglecompile", _si_citing("A2020", "Z9999"))
    si_bib = run_dir / "paper" / "references_SI.bib"
    # A2020 resolves; Z9999 (not in the pool) cannot be in the SI bib.
    assert si_bib.is_file()
    keys = set(bib_keys(si_bib.read_text(encoding="utf-8")))
    assert "A2020" in keys
    assert "Z9999" not in keys


# --- AC-F6: stale comment "wired into BOTH documents" is grep-asserted absent (D3) ---

def test_stale_wired_into_both_documents_comment_absent():
    """AC-F6 / REQ-SA-607 (D3, grep-testable): the false phrase "wired into BOTH
    documents" no longer appears at the compiler.py:544 comment site."""
    compiler_mod = importlib.import_module("sci_adk.loop.compiler")
    source = Path(compiler_mod.__file__).read_text(encoding="utf-8")
    assert "wired into BOTH documents" not in source


# ===========================================================================
# F.3 — Package path symmetry (01_manuscript/references_SI.bib)
# ===========================================================================

# Package fixtures mirror tests/test_si_authoring_m5.py.
from sci_adk.core.pkgreqs import DEFAULT_REQUIRED_SECTIONS, PackageReqs
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
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.provenance import pkgreqs_digest
import json


def _numeric_spec(spec_id: str, value: float = 0.9) -> Spec:
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id="hyp-n", statement="the encoder is injective on the tested set",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="point >= threshold => support",
                params={"statistic": "point", "op": ">=", "value": value},
            ),
            referent="formal",
            non_circularity="the verifier checks a property not baked into the generator",
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-n")],
    )


def _numeric_experiment(point: float):
    def experiment(s, w):
        return [EvidenceItem(
            id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="abc123", data_source="generated"),
            result=Result(type="quantitative", point=point),
            bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
        )]
    return experiment


def _seed_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    for rid, val, pt in [("run-alpha", 0.9, 0.95), ("run-beta", 0.8, 0.85)]:
        run_checkpoint_loop(
            run_dir=ws / "runs" / rid, spec=_numeric_spec(rid, value=val),
            experiment=_numeric_experiment(pt), workspace_dir=ws,
        )
    return ws


def _freeze_pkgreqs(ws: Path, **kw) -> None:
    sections = kw.pop("required_sections", list(DEFAULT_REQUIRED_SECTIONS))
    pr = PackageReqs(required_sections=sections, **kw)
    frozen = pr.model_copy(update={"digest": pkgreqs_digest(pr)})
    (ws / "pkgreqs.json").write_text(frozen.model_dump_json(indent=2), encoding="utf-8")


def _pkgreqs_obj(ws: Path) -> PackageReqs:
    return PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )


def _assemble(ws: Path) -> None:
    from sci_adk.render.package import assemble_package

    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    assemble_package(ws, _pkgreqs_obj(ws))


def _pkg_si_bib(ws: Path) -> Path:
    return ws / "package" / "01_manuscript" / "references_SI.bib"


def _pkg_si_tex(ws: Path) -> Path:
    return ws / "package" / "01_manuscript" / "si.tex"


_AUTHOR_SI_HEAD = r"\documentclass{article}\usepackage{natbib}\begin{document}"


# --- AC-F7a: author si.tex + author references_SI.bib, both preserved verbatim ---

def test_pkg_author_si_and_bib_preserved_verbatim(tmp_path):
    """AC-F7a / REQ-SA-608/608a: an author package_src/si.tex (with its own
    \\bibliography line) AND package_src/references_SI.bib are BOTH preserved verbatim —
    the assembler injects NO wiring into the copied si.tex."""
    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    authored_si = (
        _AUTHOR_SI_HEAD
        + r"Supplementary discussion \citep{A2020}."
        + r"\bibliographystyle{plainnat}\bibliography{references_SI}\end{document}"
    )
    author_bib = "@article{A2020, title={Alpha}, doi={10.1/a}}\n"
    (src / "si.tex").write_text(authored_si, encoding="utf-8")
    (src / "references_SI.bib").write_text(author_bib, encoding="utf-8")

    from sci_adk.render.package import assemble_package
    assemble_package(ws, _pkgreqs_obj(ws))

    # si.tex copied byte-for-byte (no wiring injection).
    assert _pkg_si_tex(ws).read_text(encoding="utf-8") == authored_si
    # references_SI.bib preserved verbatim.
    assert _pkg_si_bib(ws).read_text(encoding="utf-8") == author_bib


# --- AC-F7b: author si.tex, no author bib -> cited-only subset landed beside it ---

def test_pkg_author_si_no_bib_gets_cited_only_subset(tmp_path):
    """AC-F7b / REQ-SA-608: an author si.tex citing {A,C} but NO author
    references_SI.bib -> the assembler lands a cited-only {A2020,C2022} references_SI.bib
    BESIDE the verbatim author file (drawn from the package pool)."""
    from sci_adk.render.pkgreqs_checks import bib_keys

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    authored_si = (
        _AUTHOR_SI_HEAD
        + r"Discussion \citep{A2020} and \citep{C2022}."
        + r"\bibliography{references_SI}\end{document}"
    )
    (src / "si.tex").write_text(authored_si, encoding="utf-8")
    # The package pool (main references.bib) carries {A,B,C}.
    (src / "references.bib").write_text(_POOL_BIB, encoding="utf-8")

    from sci_adk.render.package import assemble_package
    assemble_package(ws, _pkgreqs_obj(ws))

    # author si.tex still verbatim (assembler did not touch its \bibliography line).
    assert _pkg_si_tex(ws).read_text(encoding="utf-8") == authored_si
    # cited-only subset landed beside it.
    assert _pkg_si_bib(ws).is_file()
    assert set(bib_keys(_pkg_si_bib(ws).read_text(encoding="utf-8"))) == {"A2020", "C2022"}


# --- AC-F7d: generated skeleton, citation-free -> no wiring, no bib file (D7) ---

def test_pkg_skeleton_no_citation_no_bib_no_wiring(tmp_path):
    """AC-F7d / EC-11 / REQ-SA-608b/610: no author package_src/si.tex -> the assembler
    emits the skeleton; a citation-free skeleton wires NO \\bibliography and writes NO
    references_SI.bib."""
    ws = _seed_workspace(tmp_path)
    _assemble(ws)  # no package_src/si.tex -> skeleton path
    assert not _pkg_si_bib(ws).exists()
    si_text = _pkg_si_tex(ws).read_text(encoding="utf-8")
    assert r"\bibliography{" not in si_text


# ===========================================================================
# F.4 — SI cite-resolution verify gate (per-run + package)
# ===========================================================================

# --- AC-F8: dangling si.tex cite fails, per-run + package (REQ-SA-611/612/613/614) ---

def test_si_cite_gate_uses_cite_resolution_problems():
    """AC-F10 / REQ-SA-611: the SI cite gate REUSES cite_resolution_problems — the
    problem-line shape matches the main.tex gate (pkgreqs_checks.py:141-143)."""
    from sci_adk.render.pkgreqs_checks import cite_resolution_problems

    si_tex = r"Discussion \citep{A2020} and \citep{Z9999}."
    si_bib = "@article{A2020, title={Alpha}}\n"
    problems = cite_resolution_problems(si_tex, si_bib)
    assert problems
    assert any("Z9999" in p for p in problems)


def test_per_run_verify_flags_dangling_si_cite(tmp_path):
    """AC-F8 (GREEN) / REQ-SA-612/614: per-run verify additionally runs
    cite_resolution_problems(si_tex, references_SI.bib) — a dangling si.tex cite Z FAILS
    and names Z."""
    from sci_adk.loop.verify import (
        _check_paper_requirements,
        _load_spec,
        _load_claims,
        _load_evidence,
    )
    from sci_adk.core.pubreqs import PubReqs

    # A per-run compile with an SI citing {A2020, Z9999}; Z9999 is absent from the pool
    # so references_SI.bib holds only A2020 -> Z dangles.
    run_dir, _ = _compile(tmp_path, "t-m6-perrun-gate", _si_citing("A2020", "Z9999"))

    # Freeze a minimal pubreqs so _check_paper_requirements runs its checks (not the
    # OD-8 refusal). draft.tex already exists from the compile.
    (run_dir / "pubreqs.json").write_text(
        PubReqs(spec_id="t-m6-perrun-gate", digest="fixture-digest").model_dump_json(),
        encoding="utf-8",
    )

    spec = _load_spec(run_dir)
    claims = list(_load_claims(run_dir).values())
    evidence = _load_evidence(run_dir)

    problems, _warnings = _check_paper_requirements(run_dir, evidence, claims, spec)
    assert any("Z9999" in p for p in problems), (
        "the per-run SI cite gate must flag the dangling si.tex cite Z9999"
    )


def test_package_verify_flags_dangling_si_cite(tmp_path):
    """AC-F8 (GREEN) / REQ-SA-613/614: package verify additionally runs
    cite_resolution_problems(si_tex, 01_manuscript/references_SI.bib) — a dangling
    package si.tex cite Z FAILS and names Z."""
    from sci_adk.loop.verify import _check_package_requirements

    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, venue="IEAM", abstract_max_words=300, reference_style="plainnat")
    src = ws / "package_src"
    src.mkdir()
    # An author si.tex citing Z9999, and a references_SI.bib that does NOT define Z9999.
    authored_si = (
        _AUTHOR_SI_HEAD
        + r"Discussion \citep{Z9999}."
        + r"\bibliography{references_SI}\end{document}"
    )
    (src / "si.tex").write_text(authored_si, encoding="utf-8")
    (src / "references_SI.bib").write_text(
        "@article{A2020, title={Alpha}}\n", encoding="utf-8"
    )
    (src / "references.bib").write_text(_POOL_BIB, encoding="utf-8")

    from sci_adk.render.package import assemble_package
    pkgreqs = _pkgreqs_obj(ws)
    assemble_package(ws, pkgreqs)

    problems, _warnings, _runs, _repro = _check_package_requirements(
        ws, ws / "package", pkgreqs
    )
    assert any("Z9999" in p for p in problems), (
        "the package SI cite gate must flag the dangling package si.tex cite Z9999"
    )


# --- AC-F9: SI cite gate vacuously clean for a thin/citation-free SI (REQ-SA-615) ---

def test_si_cite_gate_vacuous_for_citation_free_si():
    """AC-F9 / EC-11 / REQ-SA-615: a citation-free si.tex -> no \\cite* keys -> the SI
    cite gate returns [] (vacuously clean), matching cite_resolution_problems on empty."""
    from sci_adk.render.pkgreqs_checks import cite_resolution_problems

    si_tex = r"Discussion with no citations at all."
    assert cite_resolution_problems(si_tex, "") == []


def test_per_run_verify_clean_when_no_si(tmp_path):
    """AC-F9 / EC-1 / REQ-SA-615: a run with NO authored si.tex -> the per-run SI cite
    gate contributes no problems (thin/absent SI is vacuously clean)."""
    from sci_adk.loop.verify import (
        _check_paper_requirements,
        _load_spec,
        _load_claims,
        _load_evidence,
    )
    from sci_adk.core.pubreqs import PubReqs
    from sci_adk.loop.compiler import ResearchCompiler

    run_dir = tmp_path / "runs" / "t-m6-nosi"
    _seed_pool(run_dir)
    # Compile with NO si -> no paper/si.tex, no references_SI.bib.
    ResearchCompiler(workspace_dir=tmp_path).compile(
        _PROPOSAL, spec_id="t-m6-nosi", experiment=_point_experiment
    )
    assert not (run_dir / "paper" / "si.tex").exists()

    (run_dir / "pubreqs.json").write_text(
        PubReqs(spec_id="t-m6-nosi", digest="fixture-digest").model_dump_json(),
        encoding="utf-8",
    )

    spec = _load_spec(run_dir)
    claims = list(_load_claims(run_dir).values())
    evidence = _load_evidence(run_dir)

    problems, _warnings = _check_paper_requirements(run_dir, evidence, claims, spec)
    # No si.tex means no SI-cite problem line at all.
    assert not any("references_SI" in p for p in problems)


# ===========================================================================
# F.5 — Scope discipline / domain neutrality
# ===========================================================================

def test_m6_is_domain_neutral():
    """AC-F11 / REQ-SA-617: the M6 renderer + the new bib-subset helper name no domain,
    venue, or study."""
    from sci_adk.render import authored_si

    src = Path(authored_si.__file__).read_text(encoding="utf-8")
    forbidden = ("IEAM", "molecule", "ecotox", "BCF", "BAF", "T-1", "godel")
    for token in forbidden:
        assert token not in src, f"authored_si.py must not name '{token}' (domain leak)"
