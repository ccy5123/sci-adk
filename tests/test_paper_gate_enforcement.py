"""
RED-first: SPEC-PAPER-GATE-001 M1 -- P1 non-vacuous refusal + P2 number-audit wiring.

These exercise the verify-side wiring (loop/verify.py):

  - P1 (MP-4, REQ-PG-101/108, OD-1 strict + OD-8 immediate): a conclusion-bearing artifact
    (ANY ``paper/draft.tex`` per-run, OR ANY ``package/`` workspace) with NO frozen contract
    (``pubreqs.json`` / ``pkgreqs.json``) must REFUSE -- the gate reports a loud, actionable
    failure naming what to freeze, replacing the old silent vacuously-clean ``return []``.

  - P2 (MP-1, REQ-PG-201/202/204): with a frozen contract present, the number-audit FAILS
    (and names the unbacked token + location) for a manuscript containing a quantitative token
    absent from the recorded-value pool, and PASSES for an otherwise-identical manuscript whose
    every token is recorded.

All fixtures use NEUTRAL synthetic data (no domain/venue/study). Pure + deterministic + no LLM.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from sci_adk.core.claim import (
    Claim,
    ClaimStatus,
    Confidence,
    ConfidenceType,
)
from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.core.pkgreqs import PackageReqs
from sci_adk.core.pubreqs import PubReqs
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
from sci_adk.loop.verify import verify_package, verify_run

_NON_CIRC = "the verifier checks a property not baked into the generator"


# -- neutral synthetic run builder -------------------------------------------

def _spec(spec_id: str = "spec-x", hyp: str = "hyp-a") -> Spec:
    return Spec(
        id=spec_id, version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id=hyp, statement="a recorded statement",
            mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(
                kind=DecisionRuleKind.THRESHOLD,
                expression="point >= threshold => support",
                params={"statistic": "point", "op": ">=", "value": 0.5},
            ),
            referent="formal", non_circularity=_NON_CIRC,
        )],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers=hyp)],
    )


def _write_run(run_dir: Path, *, point: float = 0.61, hyp: str = "hyp-a") -> None:
    """A minimal recorded run: spec.json + one Evidence item + one reproducing Claim."""
    spec = _spec(hyp=hyp)
    (run_dir).mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(spec.model_dump_json(), encoding="utf-8")

    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(exist_ok=True)
    ev = EvidenceItem(
        id="ev-1", spec_id=spec.id, kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=point),
        bears_on=[Bearing(target_id=hyp, direction=BearingDirection.SUPPORTS)],
    )
    (ev_dir / "ev-1.json").write_text(ev.model_dump_json(), encoding="utf-8")

    cl_dir = run_dir / "claims"
    cl_dir.mkdir(exist_ok=True)
    claim = Claim(
        id=f"claim-{hyp}", spec_id=spec.id, answers=hyp,
        statement="a recorded statement", status=ClaimStatus.SUPPORTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (cl_dir / f"claim-{hyp}.json").write_text(claim.model_dump_json(), encoding="utf-8")


def _draft(run_dir: Path, body: str) -> None:
    paper = run_dir / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "draft.tex").write_text(body, encoding="utf-8")


def _freeze_pubreqs(run_dir: Path, **kw) -> None:
    pubreqs = PubReqs(spec_id="spec-x", digest="fixture-digest", **kw)
    (run_dir / "pubreqs.json").write_text(pubreqs.model_dump_json(), encoding="utf-8")


# ===========================================================================
# P1 -- non-vacuous refusal (MP-4, REQ-PG-101/108, OD-1 strict + OD-8 immediate)
# ===========================================================================

def test_per_run_draft_without_frozen_pubreqs_refuses(tmp_path):
    """A conclusion-bearing draft.tex + NO pubreqs.json -> loud refusal, gate FAILS."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    _draft(run_dir, r"\section{Results}The value is 0.61.")
    # NO pubreqs.json frozen.
    report = verify_run(run_dir)
    assert not report.paper_requirements_clean
    assert not report.passed
    joined = " ".join(report.paper_requirements_problems).lower()
    assert "frozen" in joined or "freeze" in joined
    assert "pubreqs" in joined


def test_per_run_draft_with_frozen_pubreqs_does_not_refuse(tmp_path):
    """Same draft WITH a frozen pubreqs.json (and clean numbers) -> no refusal."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    # point=0.61 and confidence 0.9 are recorded; 0.5 is the threshold (recorded).
    _draft(run_dir, r"\section{Results}The value is 0.61 (confidence 0.9).")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    refusal = [p for p in report.paper_requirements_problems if "frozen" in p.lower()]
    assert refusal == []


def test_per_run_no_draft_is_not_conclusion_bearing(tmp_path):
    """A run with NO paper/draft.tex is NOT conclusion-bearing -> no refusal (EC-1 spirit)."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    # No draft.tex, no pubreqs.json.
    report = verify_run(run_dir)
    assert report.paper_requirements_clean
    assert report.passed


def test_package_without_frozen_pkgreqs_refuses(tmp_path):
    """ANY package/ + NO pkgreqs.json -> loud refusal (OD-1 strict), gate FAILS."""
    ws = tmp_path
    pkg = ws / "package"
    pkg.mkdir()
    (pkg / "01_manuscript").mkdir()
    (pkg / "01_manuscript" / "main.tex").write_text(
        r"\section{Results}A value.", encoding="utf-8"
    )
    # NO pkgreqs.json.
    report = verify_package(ws)
    assert not report.package_requirements_clean
    assert not report.passed
    joined = " ".join(report.package_requirements_problems).lower()
    assert "frozen" in joined or "freeze" in joined
    assert "pkgreqs" in joined


def test_no_package_is_not_conclusion_bearing(tmp_path):
    """No package/ at all -> vacuously clean (nothing to gate), no refusal."""
    report = verify_package(tmp_path)
    assert report.package_requirements_clean
    assert report.passed


def test_per_run_refusal_does_not_weaken_claim_reproduction(tmp_path):
    """REQ-PG-107: the new refusal is ADDITIVE -- a non-reproducing claim still FAILS."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    # Tamper: rewrite the claim to a status that does NOT re-derive (point >= 0.5 => supported,
    # so a recorded REFUTED claim diverges).
    claim = Claim(
        id="claim-hyp-a", spec_id="spec-x", answers="hyp-a",
        statement="s", status=ClaimStatus.REFUTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (run_dir / "claims" / "claim-hyp-a.json").write_text(
        claim.model_dump_json(), encoding="utf-8"
    )
    report = verify_run(run_dir)
    assert not report.all_reproduced  # the existing record-green gate still fires
    assert not report.passed


# ===========================================================================
# P2 -- number-audit wiring (MP-1, REQ-PG-201/202/204)
# ===========================================================================

def test_per_run_number_audit_fails_on_unbacked_token(tmp_path):
    """A draft with a number absent from the recorded pool FAILS verify and names it."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    _draft(run_dir, r"\section{Results}The value is 0.61 but baseline 0.42 is unrecorded.")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert not report.paper_requirements_clean
    assert not report.passed
    joined = " ".join(report.paper_requirements_problems)
    assert "0.42" in joined
    assert "draft.tex" in joined


def test_per_run_number_audit_passes_on_fully_backed_manuscript(tmp_path):
    """The otherwise-identical manuscript whose every token is recorded PASSES (no false +)."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    # 0.61 (point), 0.9 (claim confidence), 0.5 (threshold) all recorded.
    _draft(run_dir, r"\section{Results}The value is 0.61 (confidence 0.9, threshold 0.5).")
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=False,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert report.paper_requirements_clean
    assert report.passed


def test_package_number_audit_fails_on_unbacked_token(tmp_path):
    """MP-1: a package main.tex with an unbacked number FAILS verify_package and names it."""
    ws = tmp_path
    pkg = ws / "package"
    (pkg / "01_manuscript").mkdir(parents=True)
    (pkg / "01_manuscript" / "main.tex").write_text(
        r"\section{Results}The recorded value 0.61, but 0.42 is unbacked.",
        encoding="utf-8",
    )
    data = pkg / "02_data"
    data.mkdir()
    (data / "claims_all.csv").write_text(
        "run_id,hyp_id,status,point_statistic,threshold\n"
        "r1,h1,supported,0.61,0.5\n",
        encoding="utf-8",
    )
    pkgreqs = PackageReqs(digest="fixture-digest")
    (ws / "pkgreqs.json").write_text(pkgreqs.model_dump_json(), encoding="utf-8")
    report = verify_package(ws)
    joined = " ".join(report.package_requirements_problems)
    assert "0.42" in joined
    assert "main.tex" in joined
    assert not report.package_requirements_clean


def test_package_number_audit_passes_on_backed_manuscript(tmp_path):
    """No false positive: a package whose every main.tex token is in 02_data passes the audit."""
    ws = tmp_path
    pkg = ws / "package"
    (pkg / "01_manuscript").mkdir(parents=True)
    (pkg / "01_manuscript" / "main.tex").write_text(
        r"\section{Results}The recorded value 0.61 over threshold 0.5.",
        encoding="utf-8",
    )
    data = pkg / "02_data"
    data.mkdir()
    (data / "claims_all.csv").write_text(
        "run_id,hyp_id,status,point_statistic,threshold\n"
        "r1,h1,supported,0.61,0.5\n",
        encoding="utf-8",
    )
    pkgreqs = PackageReqs(digest="fixture-digest")
    (ws / "pkgreqs.json").write_text(pkgreqs.model_dump_json(), encoding="utf-8")
    report = verify_package(ws)
    audit = [p for p in report.package_requirements_problems if "number audit" in p]
    assert audit == []


# -- PNG fixture helper (stdlib only -- NO Pillow); the DPI checker reads only the IHDR width.

def _make_png(width: int, height: int = 10) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def _chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IEND", b"")


def _package_main(ws: Path, body: str, *, pkgreqs: PackageReqs) -> None:
    """Lay down a minimal conclusion-bearing package: 01_manuscript/main.tex + pkgreqs.json."""
    (ws / "package" / "01_manuscript").mkdir(parents=True, exist_ok=True)
    (ws / "package" / "01_manuscript" / "main.tex").write_text(body, encoding="utf-8")
    (ws / "pkgreqs.json").write_text(pkgreqs.model_dump_json(), encoding="utf-8")


# ===========================================================================
# AC-1 -- F2 wiring gap closed: the package gate applies font-policy + raster-DPI (REQ-PG-106)
# ===========================================================================

def test_package_font_policy_fails_on_figure_bearing_main_without_preamble(tmp_path):
    """AC-1: a figure-bearing package main.tex missing the F2 font preamble FAILS the gate."""
    pkgreqs = PackageReqs(digest="fixture-digest", figure_font_policy=True, image_min_dpi=None)
    _package_main(
        tmp_path,
        r"\section{Results}" "\n" r"\includegraphics[width=\linewidth]{figures/fig1.pdf}",
        pkgreqs=pkgreqs,
    )
    report = verify_package(tmp_path)
    joined = " ".join(report.package_requirements_problems).lower()
    assert "font policy" in joined
    assert "newtxmath" in joined or "helvet" in joined
    assert not report.package_requirements_clean


def test_package_font_policy_off_skips_the_check(tmp_path):
    """AC-1 (no false positive): figure_font_policy off -> no font-policy failure surfaced."""
    pkgreqs = PackageReqs(digest="fixture-digest", figure_font_policy=False, image_min_dpi=None)
    _package_main(
        tmp_path,
        r"\section{Results}" "\n" r"\includegraphics[width=\linewidth]{figures/fig1.pdf}",
        pkgreqs=pkgreqs,
    )
    report = verify_package(tmp_path)
    font = [p for p in report.package_requirements_problems if "font policy" in p.lower()]
    assert font == []


def test_package_image_dpi_fails_below_floor(tmp_path):
    """AC-1: a raster figure below the declared image_min_dpi floor FAILS the package gate."""
    pkgreqs = PackageReqs(digest="fixture-digest", figure_font_policy=False, image_min_dpi=300)
    _package_main(
        tmp_path,
        r"\section{Results}" "\n" r"\includegraphics[width=\textwidth]{figures/fig1.png}",
        pkgreqs=pkgreqs,
    )
    figs = tmp_path / "package" / "01_manuscript" / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    (figs / "fig1.png").write_bytes(_make_png(500))  # ~77 DPI over a 6.5in textwidth
    report = verify_package(tmp_path)
    joined = " ".join(report.package_requirements_problems).lower()
    assert "dpi" in joined
    assert "fig1.png" in joined
    assert not report.package_requirements_clean


# ===========================================================================
# AC-2 -- Conclusion in the IMRaD defaults (REQ-PG-105)
# ===========================================================================

def test_default_required_sections_include_conclusion():
    """AC-2: the 'use defaults' IMRaD set includes Conclusion (both per-run and package)."""
    from sci_adk.core.pkgreqs import DEFAULT_REQUIRED_SECTIONS as PKG_DEFAULTS
    from sci_adk.core.pubreqs import DEFAULT_REQUIRED_SECTIONS as PUB_DEFAULTS

    assert "Conclusion" in PUB_DEFAULTS
    assert "Conclusion" in PKG_DEFAULTS


def test_per_run_defaults_require_conclusion_section(tmp_path):
    """AC-2: with the IMRaD defaults frozen, a draft lacking Conclusion FAILS and names it."""
    from sci_adk.core.pubreqs import DEFAULT_REQUIRED_SECTIONS

    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir)
    _draft(
        run_dir,
        r"\begin{abstract}x\end{abstract}\section{Introduction}a"
        r"\section{Methods}b\section{Results}c\section{Discussion}d",  # no Conclusion
    )
    _freeze_pubreqs(run_dir, required_sections=list(DEFAULT_REQUIRED_SECTIONS),
                    figure_font_policy=False, image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert not report.paper_requirements_clean
    assert any("Conclusion" in p for p in report.paper_requirements_problems)


# ===========================================================================
# AC-5 -- record vs belief: the audit compares ONLY against recorded values (REQ-PG-203)
# ===========================================================================

def test_number_audit_compares_to_record_not_plausibility(tmp_path):
    """AC-5: a plausible but UNRECORDED number still FAILS -- the gate is record, not belief."""
    _package_main(
        tmp_path,
        r"\section{Results}The recorded point is 0.61; a reported value 0.99 is unrecorded.",
        pkgreqs=PackageReqs(digest="fixture-digest", figure_font_policy=False, image_min_dpi=None),
    )
    data = tmp_path / "package" / "02_data"
    data.mkdir(parents=True)
    (data / "claims_all.csv").write_text(
        "run_id,hyp_id,status,point_statistic\nr1,h1,supported,0.61\n", encoding="utf-8"
    )
    report = verify_package(tmp_path)
    joined = " ".join(report.package_requirements_problems)
    assert "0.99" in joined  # plausible, but absent from the recorded pool -> FAILS
    assert not report.package_requirements_clean


# ===========================================================================
# AC-6 -- the new gates are ADDITIVE: a passing paper never masks a reproduction failure
# ===========================================================================

def test_compliant_paper_does_not_mask_reproduction_failure(tmp_path):
    """AC-6 (REQ-PG-107): a fully paper-compliant run STILL FAILS if its claim does not reproduce."""
    run_dir = tmp_path / "runs" / "spec-x"
    _write_run(run_dir, point=0.61)
    # tamper: a REFUTED claim does NOT re-derive (point 0.61 >= 0.5 => supported).
    claim = Claim(
        id="claim-hyp-a", spec_id="spec-x", answers="hyp-a",
        statement="s", status=ClaimStatus.REFUTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.9, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (run_dir / "claims" / "claim-hyp-a.json").write_text(
        claim.model_dump_json(), encoding="utf-8"
    )
    # an otherwise-clean, backed, font-on draft (the paper gate would pass on its own).
    _draft(
        run_dir,
        r"\usepackage{newtxmath}" "\n" r"\usepackage[scaled]{helvet}" "\n"
        r"\begin{abstract}x\end{abstract}\section{Results}The value is 0.61.",
    )
    _freeze_pubreqs(run_dir, required_sections=[], figure_font_policy=True,
                    image_min_dpi=None, reproduction_bundle=False)
    report = verify_run(run_dir)
    assert not report.all_reproduced  # the existing record-green gate still fires
    assert not report.passed
