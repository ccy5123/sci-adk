"""
RED-first: the P2 number-audit pure checker (SPEC-PAPER-GATE-001 M1, OD-2 stage iii + OD-3).

The number-audit tokenizes EVERY quantitative literal in a manuscript's prose and table cells
and FAILS on any token absent from the RECORDED-VALUE POOL (Claim point statistics + Evidence
Result scalars + the per-figure CSV values the figures were rendered from). It honors the
record-vs-belief invariant: it compares ONLY against recorded values, never fabricates, and a
derived value (a ratio/transform of two recorded values within tolerance) is accepted.

These are pure, deterministic, no-LLM, no-network checks over explicit markup -- the same
design language sci-adk already uses (the ref/label gate, the \\novelty gate, factref). All
fixtures use NEUTRAL synthetic data (no domain/venue/study).
"""

from __future__ import annotations

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
from sci_adk.core.spec import HypothesisMode
from sci_adk.render.number_audit import (
    RecordedValuePool,
    number_audit_problems,
    pool_from_record,
    tokenize_quantitative,
)


# -- neutral synthetic record builders --------------------------------------

def _evidence(ev_id: str, *, point: float, hyp: str = "hyp-a", **scalars) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        spec_id="spec-x",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="fixture", data_source="generated"),
        result=Result(type="quantitative", point=point, **scalars),
        bears_on=[Bearing(target_id=hyp, direction=BearingDirection.SUPPORTS)],
    )


def _claim(claim_id: str, *, value: float, hyp: str = "hyp-a") -> Claim:
    return Claim(
        id=claim_id,
        spec_id="spec-x",
        answers=hyp,
        statement="a recorded statement",
        status=ClaimStatus.SUPPORTED,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=value, basis="b"),
        mode=HypothesisMode.CONFIRMATORY,
    )


# -- tokenizer (OD-3) --------------------------------------------------------

def test_tokenizer_extracts_prose_decimals_percentages_and_ratios():
    tex = r"The mean was 0.61, a 42\% gain, and a 4.6x speedup over baseline."
    tokens = {t.value for t in tokenize_quantitative(tex)}
    assert 0.61 in tokens
    assert 42 in tokens
    assert 4.6 in tokens


def test_tokenizer_ignores_section_figure_table_ref_numbers():
    # \section/\ref/\cite/\label numbering and float numbers are STRUCTURAL, not data.
    tex = (
        r"\section{Results}\label{sec:3}"
        r"See Figure~\ref{fig:1} and Table~\ref{tab:2} and Equation~\eqref{eq:4}."
        r"As shown in \cite{Author2020}, the value is 7.3."
    )
    tokens = {t.value for t in tokenize_quantitative(tex)}
    # Only the genuine data literal survives -- the structural numbers are ignored.
    assert tokens == {7.3}


def test_tokenizer_ignores_math_mode_structural_literals():
    # Math-mode structural literals (exponents, subscripts) are not audited.
    tex = r"The function is $x^2 + 3x$ and the reported value is 0.88 outside math."
    tokens = {t.value for t in tokenize_quantitative(tex)}
    assert 0.88 in tokens
    assert 2 not in tokens
    assert 3 not in tokens


def test_tokenizer_ignores_dates_and_version_strings():
    tex = r"Accessed 2024-03-15 (v1.2.3). The measured ratio is 2.5."
    tokens = {t.value for t in tokenize_quantitative(tex)}
    assert 2.5 in tokens
    assert 2024 not in tokens
    assert 2023 not in tokens  # no spurious date components


def test_tokenizer_extracts_table_data_cells():
    tex = (
        r"\begin{tabular}{lr}"
        r"label & 0.71 \\"
        r"other & 1.45 \\"
        r"\end{tabular}"
    )
    tokens = {t.value for t in tokenize_quantitative(tex)}
    assert 0.71 in tokens
    assert 1.45 in tokens


# -- recorded-value pool (OD-2) ----------------------------------------------

def test_pool_from_record_collects_claim_and_evidence_scalars():
    evidence = [_evidence("ev-1", point=0.61, effect_size=1.2, p_value=0.03)]
    claims = [_claim("claim-a", value=0.9)]
    pool = pool_from_record(claims, evidence)
    assert pool.contains(0.61)
    assert pool.contains(1.2)
    assert pool.contains(0.03)
    assert pool.contains(0.9)
    assert not pool.contains(7.77)


def test_pool_collects_finding_json_scalars():
    ev = _evidence("ev-2", point=0.5)
    # A structured finding JSON: its scalar fields are citable (same as \evval resolution).
    ev = ev.model_copy(
        update={
            "result": Result(
                type="quantitative", point=0.5,
                finding='{"n_distinct": 73, "ratio": 4.6}',
            )
        }
    )
    pool = pool_from_record([], [ev])
    assert pool.contains(73)
    assert pool.contains(4.6)


# -- the audit (REQ-PG-201/202/203/204) --------------------------------------

def test_audit_passes_when_every_token_is_backed():
    evidence = [_evidence("ev-1", point=0.61, effect_size=1.2)]
    claims = [_claim("claim-a", value=0.9)]
    pool = pool_from_record(claims, evidence)
    tex = r"The point estimate was 0.61 with effect size 1.2 (confidence 0.9)."
    assert number_audit_problems(tex, pool, source="main.tex") == []


def test_audit_fails_on_an_unbacked_number_and_names_it():
    evidence = [_evidence("ev-1", point=0.61)]
    pool = pool_from_record([], evidence)
    tex = r"The point estimate was 0.61 but the baseline was 0.42 (not recorded)."
    problems = number_audit_problems(tex, pool, source="main.tex")
    assert problems  # at least one failure
    joined = " ".join(problems)
    assert "0.42" in joined
    assert "main.tex" in joined


def test_audit_accepts_a_derived_ratio_of_two_recorded_values():
    # 1.2 / 0.6 == 2.0 -- a derived transform of two recorded operands within tolerance.
    evidence = [_evidence("ev-1", point=0.6, effect_size=1.2)]
    pool = pool_from_record([], evidence)
    tex = r"The improved value 1.2 is 2x the baseline 0.6 (a 2 fold gain)."
    assert number_audit_problems(tex, pool, source="main.tex") == []


def test_audit_accepts_a_derived_difference_of_two_recorded_values():
    # 1.5 - 0.5 == 1.0 -- a difference of two recorded operands.
    evidence = [_evidence("ev-1", point=0.5, effect_size=1.5)]
    pool = pool_from_record([], evidence)
    tex = r"The gain of 1 over the 0.5 baseline reached 1.5."
    assert number_audit_problems(tex, pool, source="main.tex") == []


def test_audit_tolerance_accepts_rounded_recorded_value():
    evidence = [_evidence("ev-1", point=0.6123)]
    pool = pool_from_record([], evidence)
    tex = r"The reported value 0.61 rounds the recorded statistic."
    assert number_audit_problems(tex, pool, source="main.tex") == []


def test_audit_is_deterministic_third_party_rerunnable():
    evidence = [_evidence("ev-1", point=0.61)]
    pool = pool_from_record([], evidence)
    tex = r"Two unbacked numbers: 0.42 and 0.99."
    first = number_audit_problems(tex, pool, source="main.tex")
    second = number_audit_problems(tex, pool, source="main.tex")
    assert first == second
    assert first == sorted(first)  # stable, sorted report


def test_pool_from_data_csvs_collects_numeric_cells(tmp_path):
    # The package recorded-value pool source: 02_data/*.csv numeric cells (claims_all.csv +
    # any per-figure CSVs). Domain-neutral synthetic CSV.
    data_dir = tmp_path / "02_data"
    data_dir.mkdir()
    (data_dir / "claims_all.csv").write_text(
        "run_id,hyp_id,status,point_statistic,threshold\n"
        "r1,h1,supported,0.61,0.5\n",
        encoding="utf-8",
    )
    (data_dir / "fig1.csv").write_text("x,y\n1,1.2\n2,3.4\n", encoding="utf-8")
    pool = RecordedValuePool.from_data_csvs(data_dir)
    assert pool.contains(0.61)
    assert pool.contains(0.5)
    assert pool.contains(1.2)
    assert pool.contains(3.4)
