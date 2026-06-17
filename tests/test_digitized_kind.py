"""
RED-first: the ``digitized`` Evidence KIND + its typed sub-model (kernel schema).

design/figure-digitization.md §2-§4: ``digitized`` is a NEW Evidence kind (asymmetric
adoption -- ``measured``/``reported`` are untouched). It carries a typed Pydantic v2
sub-model on ``EvidenceItem`` with the §4 fields:

    quantity, value, unit, source, method (deterministic|vlm), axis_calib,
    read_uncert, state (proposed|verified), verification, extractor

Lifecycle (§3): ``proposed`` (extracted, NOT evidence-grade) -> ``verified``.
``method="vlm"`` is a RESERVED enum value -- v1 implements ``deterministic`` only;
constructing/operating a vlm item is allowed as a *reserved* value but the digitizer
refuses to *produce* one (the unimplemented path raises -- tested in the digitizer).

These tests pin the kernel-side type only (no digitizer, no gate): construction,
defaults, round-trip, and the value/unit -> Result mapping affordance.

No Docker, no LLM (engineering-layer tests).
"""

from __future__ import annotations

import pytest

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    DigitizedData,
    DigitizedVerification,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)


def _digitized_item(
    *,
    state: str = "proposed",
    verification: DigitizedVerification | None = None,
    method: str = "deterministic",
    data_source=None,
) -> EvidenceItem:
    return EvidenceItem(
        id="dig-1",
        spec_id="spec-x",
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1", data_source=data_source),
        result=Result(type="quantitative", point=50.0),
        bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
        digitized=DigitizedData(
            quantity="dry_weight",
            value=50.0,
            unit="g",
            source="Fig 2 / 10.1234/abc",
            method=method,
            axis_calib={"x": [100.0, 0.0, 500.0, 10.0], "y": [400.0, 0.0, 100.0, 100.0]},
            read_uncert=0.05,
            state=state,
            verification=verification,
            extractor="agent-A",
        ),
    )


# ---------------------------------------------------------------------------
# EvidenceKind.DIGITIZED exists and is distinct.
# ---------------------------------------------------------------------------

def test_digitized_kind_exists():
    assert EvidenceKind.DIGITIZED.value == "digitized"
    # It is distinct from the trustworthy-grade kinds (asymmetric adoption).
    assert EvidenceKind.DIGITIZED != EvidenceKind.EXPERIMENT_RUN


# ---------------------------------------------------------------------------
# DigitizedData sub-model: fields, defaults, round-trip.
# ---------------------------------------------------------------------------

def test_digitized_item_constructs_with_all_fields():
    item = _digitized_item()
    d = item.digitized
    assert d is not None
    assert d.quantity == "dry_weight"
    assert d.value == 50.0
    assert d.unit == "g"
    assert d.source == "Fig 2 / 10.1234/abc"
    assert d.method == "deterministic"
    assert d.state == "proposed"
    assert d.read_uncert == 0.05
    assert d.verification is None
    assert d.extractor == "agent-A"


def test_digitized_defaults_to_proposed_state():
    item = EvidenceItem(
        id="dig-1",
        spec_id="spec-x",
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1"),
        result=Result(type="quantitative", point=1.0),
        bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
        digitized=DigitizedData(
            quantity="q", value=1.0, unit="u", source="Fig 1", extractor="agent-A"
        ),
    )
    # state and method carry sensible defaults (proposed; deterministic).
    assert item.digitized.state == "proposed"
    assert item.digitized.method == "deterministic"


def test_digitized_method_accepts_reserved_vlm_enum_value():
    """``vlm`` is a RESERVED method value: the schema accepts it (the gate/digitizer
    govern whether it can be produced/counted), so the type is not future-foreclosed."""
    item = _digitized_item(method="vlm")
    assert item.digitized.method == "vlm"


def test_digitized_method_rejects_unknown_value():
    with pytest.raises(Exception):
        DigitizedData(
            quantity="q", value=1.0, unit="u", source="Fig 1",
            method="ocr-magic", extractor="agent-A",
        )


def test_digitized_state_rejects_unknown_value():
    with pytest.raises(Exception):
        DigitizedData(
            quantity="q", value=1.0, unit="u", source="Fig 1",
            state="approved", extractor="agent-A",
        )


def test_digitized_rejects_missing_extractor():
    """fail-closed: a digitized item CANNOT be constructed without an extractor identity.
    ``extractor`` is required (no default) -- the self-certification ban depends on a
    recorded extractor, so an item with none can never exist (design/figure-digitization
    §5; the extractor=None bypass the gate exists to prevent)."""
    with pytest.raises(Exception):
        DigitizedData(quantity="q", value=1.0, unit="u", source="Fig 1")


def test_digitized_rejects_none_extractor():
    """An explicit ``extractor=None`` is rejected (no None) -- the bypass where
    'verifier_id != None' falsely reads as independent is structurally impossible."""
    with pytest.raises(Exception):
        DigitizedData(
            quantity="q", value=1.0, unit="u", source="Fig 1", extractor=None
        )


def test_digitized_rejects_empty_extractor():
    """An empty/whitespace ``extractor`` is rejected (min_length=1, stripped) -- an
    empty extractor must not slip past the != verifier_id check."""
    with pytest.raises(Exception):
        DigitizedData(
            quantity="q", value=1.0, unit="u", source="Fig 1", extractor=""
        )
    with pytest.raises(Exception):
        DigitizedData(
            quantity="q", value=1.0, unit="u", source="Fig 1", extractor="   "
        )


def test_digitized_verification_carries_required_fields():
    v = DigitizedVerification(
        method="replot", verifier_id="agent-B", result="reproduced",
        artifact="overlay.png",
    )
    assert v.method == "replot"
    assert v.verifier_id == "agent-B"
    assert v.result == "reproduced"
    assert v.artifact == "overlay.png"


def test_digitized_verification_method_rejects_unknown():
    with pytest.raises(Exception):
        DigitizedVerification(method="vibes", verifier_id="agent-B", result="reproduced")


def test_digitized_item_round_trips_proposed():
    item = _digitized_item()
    back = EvidenceItem.model_validate(item.model_dump(mode="json"))
    assert back == item
    assert back.digitized.state == "proposed"


def test_digitized_item_round_trips_verified():
    v = DigitizedVerification(
        method="replot", verifier_id="agent-B", result="reproduced", artifact="overlay.png"
    )
    item = _digitized_item(state="verified", verification=v)
    back = EvidenceItem.model_validate(item.model_dump(mode="json"))
    assert back == item
    assert back.digitized.state == "verified"
    assert back.digitized.verification.verifier_id == "agent-B"


def test_non_digitized_item_has_no_digitized_field():
    """measured/reported/experiment_run items leave the digitized field None
    (asymmetric adoption -- the new sub-model attaches only to the digitized kind)."""
    item = EvidenceItem(
        id="e1",
        spec_id="spec-x",
        kind=EvidenceKind.EXPERIMENT_RUN,
        provenance=Provenance(code_ref="x", data_source="measured"),
        result=Result(type="quantitative", point=1.0),
        bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
    )
    assert item.digitized is None
