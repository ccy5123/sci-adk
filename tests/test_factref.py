"""
Tests for render/factref.py -- the record-fidelity fact-substitution gate of the
"moved line" (design/render-architecture-reframe.md).

The contract: an agent-authored paper writes record-derived facts as ``\\evval``/``\\status``
markup; the engine substitutes the TRUE recorded value at render time, FAIL-LOUD on any
fact the record does not hold. So a paper can never state a measured number or a verdict
that is not in the record, even though the narrative is agent-authored.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
from sci_adk.render.factref import (
    find_unresolved_factrefs,
    substitute_factrefs,
)

_T0 = datetime(2026, 6, 22, 9, 0, 0, tzinfo=timezone.utc)


def _evidence(
    ev_id: str,
    *,
    point=None,
    finding: str | None = None,
    hyp_id: str = "hyp-001",
) -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        created_at=_T0,
        spec_id="t1-godel",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="generated"),
        result=Result(type="quantitative", point=point, finding=finding),
        bears_on=[Bearing(target_id=hyp_id, direction=BearingDirection.SUPPORTS)],
    )


def _claim(claim_id: str, hyp_id: str, status: ClaimStatus) -> Claim:
    return Claim(
        id=claim_id,
        spec_id="t1-godel",
        answers=hyp_id,
        statement="s",
        status=status,
        confidence=Confidence(type=ConfidenceType.CREDENCE, value=0.0, basis="b"),
        mode=HypothesisMode.EXPLORATORY,
    )


# -- \evval: Result scalar -----------------------------------------------------

def test_evval_result_scalar_point():
    ev = _evidence("evi-collision", point=0.0)
    out = substitute_factrefs(r"\evval{evi-collision}{point} collisions", [ev], [])
    assert out == "0 collisions"


def test_evval_float_drops_trailing_zero():
    ev = _evidence("evi-rt", point=100.0)
    out = substitute_factrefs(r"\evval{evi-rt}{point} percent", [ev], [])
    assert out == "100 percent"


def test_evval_non_integer_float():
    ev = _evidence("evi-r2", point=0.61)
    out = substitute_factrefs(r"R2 = \evval{evi-r2}{point}", [ev], [])
    assert out == "R2 = 0.61"


# -- \evval: finding JSON scalar ----------------------------------------------

def test_evval_finding_json_scalar():
    ev = _evidence(
        "evi-collision",
        point=0.0,
        finding='{"collision_count": 0, "n_distinct_noniso_pairs": 73, "n_molecules": 13}',
    )
    out = substitute_factrefs(
        r"\evval{evi-collision}{n_distinct_noniso_pairs} pairs over "
        r"\evval{evi-collision}{n_molecules} molecules",
        [ev],
        [],
    )
    assert out == "73 pairs over 13 molecules"


def test_evval_result_scalar_preferred_over_finding():
    # point exists on the Result; even if the finding also had a 'point', the typed
    # scalar wins (it is the canonical Result value).
    ev = _evidence("evi-x", point=5.0, finding='{"point": 999}')
    out = substitute_factrefs(r"\evval{evi-x}{point}", [ev], [])
    assert out == "5"


def test_evval_finding_string_value_is_escapable_text():
    # A string fact is returned verbatim; the prose escaper (downstream) would escape it.
    ev = _evidence("evi-x", finding='{"statistic": "collision_count"}')
    out = substitute_factrefs(r"\evval{evi-x}{statistic}", [ev], [])
    assert out == "collision_count"  # the '_' is escaped later, by _latex_sanitize_prose


# -- \evval: fail-loud --------------------------------------------------------

def test_evval_unknown_evidence_id_raises():
    ev = _evidence("evi-x", point=0.0)
    with pytest.raises(ValueError, match="unknown evidence id"):
        substitute_factrefs(r"\evval{evi-missing}{point}", [ev], [])


def test_evval_field_absent_from_both_raises():
    ev = _evidence("evi-x", point=0.0, finding='{"a": 1}')
    with pytest.raises(ValueError, match="in neither"):
        substitute_factrefs(r"\evval{evi-x}{nope}", [ev], [])


def test_evval_non_scalar_finding_value_raises():
    ev = _evidence("evi-x", finding='{"list_field": [1, 2, 3]}')
    with pytest.raises(ValueError, match="non-scalar"):
        substitute_factrefs(r"\evval{evi-x}{list_field}", [ev], [])


def test_evval_nan_raises():
    ev = _evidence("evi-x", finding='{"v": NaN}')  # python json parses NaN
    with pytest.raises(ValueError, match="NaN/infinite"):
        substitute_factrefs(r"\evval{evi-x}{v}", [ev], [])


# -- \status ------------------------------------------------------------------

def test_status_resolves_experiment_claim():
    claim = _claim("claim-hyp-001", "hyp-001", ClaimStatus.SUPPORTED)
    out = substitute_factrefs(r"H1 is \status{hyp-001}.", [], [claim])
    assert out == "H1 is supported."


def test_status_excludes_novelty_claims():
    exp = _claim("claim-hyp-001", "hyp-001", ClaimStatus.SUPPORTED)
    nov = _claim("claim-novelty-result-hyp-001", "hyp-001", ClaimStatus.PROPOSED)
    # Even though the novelty claim also answers hyp-001, \status picks the experiment one.
    out = substitute_factrefs(r"\status{hyp-001}", [], [nov, exp])
    assert out == "supported"


def test_status_unknown_hypothesis_raises():
    with pytest.raises(ValueError, match="no experiment Claim"):
        substitute_factrefs(r"\status{hyp-999}", [], [])


# -- coexistence with \ref / \cite (untouched) --------------------------------

def test_substitution_leaves_ref_and_cite_untouched():
    ev = _evidence("evi-x", point=0.0)
    text = r"zero (\evval{evi-x}{point}) collisions \citep{Morgan1965} (Figure \ref{fig:c})"
    out = substitute_factrefs(text, [ev], [])
    assert out == r"zero (0) collisions \citep{Morgan1965} (Figure \ref{fig:c})"


def test_multiple_macros_one_pass():
    ev1 = _evidence("evi-a", point=0.0)
    ev2 = _evidence("evi-b", point=100.0)
    claim = _claim("claim-hyp-001", "hyp-001", ClaimStatus.SUPPORTED)
    text = r"\evval{evi-a}{point}/\evval{evi-b}{point} -> \status{hyp-001}"
    assert substitute_factrefs(text, [ev1, ev2], [claim]) == "0/100 -> supported"


def test_no_macros_is_identity():
    assert substitute_factrefs("plain prose, no macros", [], []) == "plain prose, no macros"


# -- find_unresolved_factrefs (verify re-scan) --------------------------------

def test_find_unresolved_factrefs_empty_when_substituted():
    ev = _evidence("evi-x", point=0.0)
    out = substitute_factrefs(r"\evval{evi-x}{point}", [ev], [])
    assert find_unresolved_factrefs(out) == []


def test_find_unresolved_factrefs_flags_residual():
    tex = r"a \evval{evi-x}{point} and \status{hyp-1} survived"
    found = find_unresolved_factrefs(tex)
    assert r"\evval{evi-x}{point}" in found
    assert r"\status{hyp-1}" in found
