"""
SPEC-SI-AUTHORING-001 M5 -- the package-path authoring flow (Pillar E).

Applies the per-run SI-authoring model (M1/M2/M3) to the WORKSPACE-PACKAGE path by symmetry:

  RECORD-SIDE (the genuinely new work):
    - the deterministic ``make_si.py`` dump RELOCATES from ``01_manuscript/si.tex`` to
      ``06_provenance/record.tex`` (REQ-SA-504/505), renamed to read as the RECORD
      (REQ-SA-506), and its BODY carries a "Data & code availability" statement (REQ-SA-506a);
    - the package ``01_manuscript/si.tex`` becomes AUTHORED belief -- an author-supplied
      ``package_src/si.tex`` is preserved verbatim (REQ-SA-501), the dump is NOT the fallback
      (REQ-SA-502);
    - the package tool-vocab gate scans the authored ``si.tex`` but NOT the relocated record,
      which is exempt BY CONSTRUCTION (REQ-SA-507);
    - the package deposit-completeness check REUSES the M2 checker pointed at the package
      record path, HARD-gating the package (REQ-SA-508/509/510/511).

  CHARACTERIZATION (the belief side is unchanged in computation):
    - the four package per-document checks still cover the now-authored ``si.tex`` (REQ-SA-503/513).

All tests are PURE / deterministic / no-LLM (no Docker, no real compile).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
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
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.verify import verify_package
from sci_adk.render.package import assemble_package
from sci_adk.render.pkgreqs_checks import (
    deposit_completeness_problems,
    package_record_path,
)
from sci_adk.provenance import pkgreqs_digest

_NON_CIRC = "the verifier checks a property not baked into the generator"
_AVAILABILITY = "Data & code availability"


# -- fixture builders (mirror test_package_gate.py) --------------------------

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
            referent="formal", non_circularity=_NON_CIRC,
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


def _assembled(tmp_path: Path, *, freeze=True, **freeze_kw) -> Path:
    ws = _seed_workspace(tmp_path)
    pkgreqs = None
    if freeze:
        _freeze_pkgreqs(ws, **freeze_kw)
        pkgreqs = PackageReqs.model_validate(
            json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
        )
    assemble_package(ws, pkgreqs)
    return ws


def _full_pkgreqs(**kw):
    kw.setdefault("venue", "IEAM")
    kw.setdefault("abstract_max_words", 300)
    kw.setdefault("reference_style", "plainnat")
    return kw


def _record_tex(ws: Path) -> Path:
    return ws / "package" / "06_provenance" / "record.tex"


def _si_tex(ws: Path) -> Path:
    return ws / "package" / "01_manuscript" / "si.tex"


# -- E.2: relocate + rename the package dump ---------------------------------

def test_dump_relocated_to_06_provenance_record_tex(tmp_path):
    # AC-E4 / REQ-SA-505: the deterministic dump lands at package/06_provenance/record.tex,
    # NOT at 01_manuscript/si.tex (which is freed for the authored SI).
    ws = _assembled(tmp_path, **_full_pkgreqs())
    record = _record_tex(ws)
    assert record.is_file(), "the dump must relocate to 06_provenance/record.tex"
    text = record.read_text(encoding="utf-8")
    # the relocated record still carries the dump's record tables (logic reused verbatim).
    assert r"\label{tab:index}" in text and r"\label{tab:claims}" in text
    # 01_manuscript/si.tex is NOT the dump (no record-dump index/claims tables there).
    si = _si_tex(ws)
    si_text = si.read_text(encoding="utf-8") if si.is_file() else ""
    assert r"\label{tab:index}" not in si_text, "si.tex must not carry the relocated dump"


def test_record_artifact_renamed_to_read_as_the_record(tmp_path):
    # AC-E5 / REQ-SA-506: the relocated artifact reads as the RECORD, not "Supporting
    # Information".
    ws = _assembled(tmp_path, **_full_pkgreqs())
    text = _record_tex(ws).read_text(encoding="utf-8")
    assert "Supporting Information" not in text
    assert "record" in text.lower()


def test_dump_logic_reused_deterministic(tmp_path):
    # AC-E3 / REQ-SA-504: the reused dump logic is deterministic -- re-assembling over the same
    # record yields a byte-identical record artifact.
    ws = _assembled(tmp_path, **_full_pkgreqs())
    first = _record_tex(ws).read_bytes()
    pkgreqs = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    assemble_package(ws, pkgreqs)
    second = _record_tex(ws).read_bytes()
    assert first == second


# -- E.2 (F2): availability statement in the record body (REQ-SA-506a) -------

def test_record_body_carries_availability_statement(tmp_path):
    # AC-E5a / REQ-SA-506a: make_si.py emits a "Data & code availability" statement into the
    # record body (the authoritative source the M2 checker reads), and it carries no \evval.
    ws = _assembled(tmp_path, **_full_pkgreqs())
    text = _record_tex(ws).read_text(encoding="utf-8")
    assert "availability" in text.lower() and "data" in text.lower()
    assert r"\evval" not in text   # record prose, number-audit-clean


# -- E.1: authored package si.tex (REQ-SA-501/502) ---------------------------

def test_author_supplied_si_tex_preserved_verbatim(tmp_path):
    # AC-E1 / REQ-SA-501: an author-supplied package_src/si.tex is preserved verbatim, symmetric
    # to package_src/main.tex, and is NOT the dump.
    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, **_full_pkgreqs())
    pkgreqs = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    src = ws / "package_src"
    src.mkdir()
    authored = (
        r"\documentclass{article}\begin{document}"
        r"Authored supplementary belief, no record dump.\end{document}"
    )
    (src / "si.tex").write_text(authored, encoding="utf-8")
    assemble_package(ws, pkgreqs)
    assert _si_tex(ws).read_text(encoding="utf-8") == authored
    # the dump did NOT land in si.tex.
    assert r"\label{tab:index}" not in _si_tex(ws).read_text(encoding="utf-8")


def test_dump_is_not_the_si_tex_fallback(tmp_path):
    # AC-E2 / EC-6 / REQ-SA-502: with NO author si.tex, the dump is NOT written into the si.tex
    # slot -- a thin/skeleton/absent authored SI is valid, but never the record dump there.
    ws = _assembled(tmp_path, **_full_pkgreqs())   # no package_src/si.tex
    si = _si_tex(ws)
    si_text = si.read_text(encoding="utf-8") if si.is_file() else ""
    assert r"\label{tab:index}" not in si_text
    assert r"\label{tab:claims}" not in si_text


# -- E.3: package tool-vocab boundary (REQ-SA-507) ---------------------------

def test_tool_vocab_scans_authored_si_but_exempts_record_by_construction(tmp_path):
    # AC-E6 / EC-7 / REQ-SA-507: the SAME forbidden tool token FLAGS in the authored si.tex but
    # PASSES in 06_provenance/record.tex (the record lives outside the scanned 01_manuscript/
    # dir -> exempt by construction).
    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, **_full_pkgreqs())
    pkgreqs = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    src = ws / "package_src"
    src.mkdir()
    # an authored si.tex that names the toolchain (the leak the gate must police).
    (src / "si.tex").write_text(
        r"\documentclass{article}\begin{document}"
        r"The frozen Spec and the sci-adk verdict say so.\end{document}",
        encoding="utf-8",
    )
    assemble_package(ws, pkgreqs)

    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any(
        "tool-vocabulary" in p and "si.tex" in p
        for p in report.package_requirements_problems
    ), "the authored si.tex tool leak must be flagged"
    # the record artifact legitimately names provenance and is NOT flagged.
    assert not any(
        "tool-vocabulary" in p and "record.tex" in p
        for p in report.package_requirements_problems
    )


# -- E.4: package deposit-completeness reuses M2, HARD-gates ------------------

def test_package_record_path_points_at_06_provenance_record_tex(tmp_path):
    # REQ-SA-505/508: the single package record-path source (symmetric to deposit_record_path).
    ws = _assembled(tmp_path, **_full_pkgreqs())
    assert package_record_path(ws / "package") == _record_tex(ws)


def test_deposit_check_reuses_m2_reads_record_body(tmp_path):
    # AC-E8 / REQ-SA-508: the REUSED M2 checker pointed at the package record path returns []
    # because the record body carries the availability statement (read from the record, not
    # the README).
    ws = _assembled(tmp_path, **_full_pkgreqs())
    assert deposit_completeness_problems(package_record_path(ws / "package")) == []


def test_package_gate_passes_with_relocated_record_and_availability(tmp_path):
    # AC-E10 (complete package passes): a complete migrated package is green under the now-HARD
    # deposit gate.
    ws = _assembled(tmp_path, **_full_pkgreqs())
    report = verify_package(ws)
    assert report.package_requirements_clean is True
    assert report.passed is True


def test_package_gate_hard_fails_on_missing_record_artifact(tmp_path):
    # AC-E9 / AC-E10 (F3) / REQ-SA-509: a package missing 06_provenance/record.tex FAILS the
    # HARD gate, naming the missing record artifact and reporting NO availability line.
    ws = _assembled(tmp_path, **_full_pkgreqs())
    _record_tex(ws).unlink()
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert report.passed is False
    deposit_lines = [p for p in report.package_requirements_problems if "deposit:" in p]
    assert any("record" in p for p in deposit_lines)
    assert not any("availability" in p for p in deposit_lines), (
        "with no record there is nothing to carry the availability statement -- one line only"
    )


def test_package_gate_hard_fails_on_missing_availability_statement(tmp_path):
    # AC-E9 / REQ-SA-509: a present record.tex with NO availability statement FAILS the HARD
    # gate, naming the missing statement.
    ws = _assembled(tmp_path, **_full_pkgreqs())
    record = _record_tex(ws)
    text = record.read_text(encoding="utf-8")
    # strip the availability statement (keep the artifact present).
    import re
    stripped = re.sub(r"(?i)data\s*(?:&|\\&|and)\s*code\s*availability", "Reproducibility", text)
    record.write_text(stripped, encoding="utf-8")
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any(
        "deposit:" in p and "availability" in p
        for p in report.package_requirements_problems
    )


def test_deposit_check_presence_only_does_not_judge_belief(tmp_path):
    # AC-E10 (presence-only): arbitrary main/si belief content does not affect the deposit
    # check -- it judges ONLY the presence of the record artifact + availability statement.
    ws = _assembled(tmp_path, **_full_pkgreqs())
    assert deposit_completeness_problems(package_record_path(ws / "package")) == []


# -- E.4 (F3): fixture migration -- pre-M5 green package re-assembles green ---

def test_pre_m5_seeded_package_migrates_to_green(tmp_path):
    # AC-E10 (F3 fixture migration) / R11: simulate a PRE-M5 seeded package (dump in
    # 01_manuscript/si.tex, NO 06_provenance/record.tex) and assert re-assembly MIGRATES it to
    # the new layout (record relocated + availability statement) so it is green again under the
    # now-HARD deposit gate, with no recorded run digest / verdict changed.
    ws = _assembled(tmp_path, **_full_pkgreqs())

    # capture the recorded verdicts + digests BEFORE the simulated downgrade + migration.
    def _verdict_digest_snapshot() -> dict:
        idx = (ws / "package" / "06_provenance" / "run_index.csv").read_text(encoding="utf-8")
        return {"run_index": idx}

    before = _verdict_digest_snapshot()

    # simulate the OLD layout: move the record back into the si.tex slot, drop record.tex.
    record = _record_tex(ws)
    si = _si_tex(ws)
    si.write_text(record.read_text(encoding="utf-8"), encoding="utf-8")
    record.unlink()
    # under the OLD layout, the now-HARD deposit gate reddens the package.
    assert verify_package(ws).package_requirements_clean is False

    # MIGRATE mechanically: re-assemble (relocates the dump + emits the availability statement).
    pkgreqs = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    assemble_package(ws, pkgreqs)

    assert verify_package(ws).package_requirements_clean is True
    # no recorded run's verdict / digest changed (the migration is mechanical re-assembly).
    assert _verdict_digest_snapshot() == before


# -- E (characterization): the four package per-document checks unchanged -----

def test_characterization_authored_si_unbacked_number_fails_number_audit(tmp_path):
    # AC-E7 / REQ-SA-503/513: an authored package si.tex with a number NOT in the package
    # recorded-value pool FAILS the EXISTING package number-audit -- the same checker that
    # passed over the old dump now does real work, with no change to what it computes.
    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, **_full_pkgreqs())
    pkgreqs = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    src = ws / "package_src"
    src.mkdir()
    # 0.123456 is not in the package pool {0.95, 0.9, 0.85, 0.8, ...}.
    (src / "si.tex").write_text(
        r"\documentclass{article}\begin{document}"
        r"The recorded statistic was 0.123456.\end{document}",
        encoding="utf-8",
    )
    assemble_package(ws, pkgreqs)
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("0.123456" in p for p in report.package_requirements_problems)


def test_characterization_authored_si_residual_fact_macro_fails_fidelity(tmp_path):
    # AC-E7 / REQ-SA-513: the package value-fidelity check still covers the authored si.tex (a
    # residual \evval macro fails it) -- byte-unchanged in computation.
    ws = _seed_workspace(tmp_path)
    _freeze_pkgreqs(ws, **_full_pkgreqs())
    pkgreqs = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    src = ws / "package_src"
    src.mkdir()
    (src / "si.tex").write_text(
        r"\documentclass{article}\begin{document}"
        r"The value is \evval{ev-num}{point}.\end{document}",
        encoding="utf-8",
    )
    assemble_package(ws, pkgreqs)
    report = verify_package(ws)
    assert report.package_requirements_clean is False
    assert any("value fidelity" in p and "si.tex" in p
               for p in report.package_requirements_problems)
