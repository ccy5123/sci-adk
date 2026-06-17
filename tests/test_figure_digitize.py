"""
RED-first: the deterministic figure digitizer (capability plugin, OUTSIDE the kernel).

design/figure-digitization.md §6 "Borrow" + §8 pull-list item 3: the digitization
*execution* (WebPlotDigitizer-style: axis calibration + pixel-position point extraction)
and the replot-*verification* execution live in ``sci_adk.search.figure_digitize`` --
a capability plugin. The kernel (core/loop/render) MUST NOT import it; the F4 seam test
(tests/test_kernel_adapter_seam.py) keeps that one-way.

These tests pin the PURE deterministic transform (no GUI, no figure file): given axis
calibration (two reference points per axis, with their known data values) and a list of
point pixel coordinates, ``digitize`` returns the data-space values + a read uncertainty.
Linear AND log10 axes are covered. ``record_digitized`` wraps the result into a
``proposed`` digitized EvidenceItem; ``verify_digitized`` performs the INDEPENDENT replot
check (recompute the data values back to pixel space, confirm within tolerance) and
records ``verifier_id`` (enforcing ``verifier_id != extractor``).

No Docker, no LLM: synthetic fixtures only (engineering-layer tests).
"""

from __future__ import annotations

import pytest

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    DigitizedData,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
from sci_adk.search.figure_digitize import (
    AxisCalibration,
    AxisRef,
    digitize,
    record_digitized,
    verify_digitized,
)


# ---------------------------------------------------------------------------
# A synthetic LINEAR axis calibration.
#
# x-axis: pixel 100 -> data 0.0 ; pixel 500 -> data 10.0  (40 px per unit)
# y-axis: pixel 400 -> data 0.0 ; pixel  100 -> data 100.0 (pixels DECREASE upward,
#         the usual screen convention -- y grows as the pixel row number shrinks).
# ---------------------------------------------------------------------------

def _linear_calib() -> AxisCalibration:
    return AxisCalibration(
        x=AxisRef(p1_pixel=100.0, p1_value=0.0, p2_pixel=500.0, p2_value=10.0, scale="linear"),
        y=AxisRef(p1_pixel=400.0, p1_value=0.0, p2_pixel=100.0, p2_value=100.0, scale="linear"),
    )


def _log_calib() -> AxisCalibration:
    # y-axis is LOG10: pixel 400 -> data 1.0 (10^0) ; pixel 100 -> data 1000.0 (10^3).
    # So the per-pixel step is in log10 space: 3 decades over 300 px.
    return AxisCalibration(
        x=AxisRef(p1_pixel=100.0, p1_value=0.0, p2_pixel=500.0, p2_value=10.0, scale="linear"),
        y=AxisRef(p1_pixel=400.0, p1_value=1.0, p2_pixel=100.0, p2_value=1000.0, scale="log"),
    )


# ---------------------------------------------------------------------------
# digitize(): the pure pixel -> data transform (linear).
# ---------------------------------------------------------------------------

def test_digitize_linear_reference_points_recover_exactly():
    """Feeding the calibration's own reference pixels back recovers their data values."""
    calib = _linear_calib()
    pts = digitize(calib, [(100.0, 400.0), (500.0, 100.0)])
    assert pts[0].value_x == pytest.approx(0.0)
    assert pts[0].value_y == pytest.approx(0.0)
    assert pts[1].value_x == pytest.approx(10.0)
    assert pts[1].value_y == pytest.approx(100.0)


def test_digitize_linear_midpoint():
    """A pixel halfway along each axis maps to the data midpoint (linear interpolation)."""
    calib = _linear_calib()
    # x pixel 300 is halfway 100..500 -> 5.0 ; y pixel 250 is halfway 400..100 -> 50.0
    (pt,) = digitize(calib, [(300.0, 250.0)])
    assert pt.value_x == pytest.approx(5.0)
    assert pt.value_y == pytest.approx(50.0)


def test_digitize_linear_extrapolates_beyond_reference():
    """Linear interpolation extends past the reference pixels (no clamping)."""
    calib = _linear_calib()
    # x pixel 700 is 600 px past origin at 40 px/unit -> 15.0
    (pt,) = digitize(calib, [(700.0, 400.0)])
    assert pt.value_x == pytest.approx(15.0)


def test_digitize_log_axis_recovers_decades():
    """A log10 y-axis maps pixels back to data via 10**(linear-in-log-space)."""
    calib = _log_calib()
    # y pixel 250 is halfway 400..100 -> halfway in log10 space between 10^0 and 10^3
    # -> 10^1.5 ~= 31.6227766
    (pt,) = digitize(calib, [(300.0, 250.0)])
    assert pt.value_x == pytest.approx(5.0)
    assert pt.value_y == pytest.approx(10 ** 1.5)


def test_digitize_log_reference_points_recover_exactly():
    calib = _log_calib()
    pts = digitize(calib, [(100.0, 400.0), (500.0, 100.0)])
    assert pts[0].value_y == pytest.approx(1.0)
    assert pts[1].value_y == pytest.approx(1000.0)


def test_digitize_read_uncert_is_computed_and_positive():
    """read_uncert is derived from the marker/resolution input (data units per pixel)."""
    calib = _linear_calib()
    # marker_radius_px=2 -> +-2 px of read error. On x at 40 px/unit that is 0.05 units.
    (pt,) = digitize(calib, [(300.0, 250.0)], marker_radius_px=2.0)
    assert pt.read_uncert_x is not None and pt.read_uncert_x > 0
    assert pt.read_uncert_y is not None and pt.read_uncert_y > 0
    # x: 2 px / (40 px/unit) = 0.05
    assert pt.read_uncert_x == pytest.approx(0.05)


def test_digitize_log_read_uncert_is_asymmetric_in_data_space():
    """On a log axis a fixed pixel error is multiplicative -> read_uncert grows with value."""
    calib = _log_calib()
    low = digitize(calib, [(300.0, 380.0)], marker_radius_px=2.0)[0]   # small y
    high = digitize(calib, [(300.0, 120.0)], marker_radius_px=2.0)[0]  # large y
    # Larger data value on a log axis -> larger absolute read uncertainty.
    assert high.read_uncert_y > low.read_uncert_y


def test_digitize_rejects_degenerate_axis():
    """Two reference pixels that coincide cannot define a scale -> error (no
    divide-by-zero). The calibration is rejected at construction (Pydantic
    ValidationError is a ValueError subclass), before any transform runs."""
    with pytest.raises(ValueError):
        AxisRef(p1_pixel=100.0, p1_value=0.0, p2_pixel=100.0, p2_value=10.0, scale="linear")


def test_digitize_rejects_nonpositive_log_value():
    """A log axis reference value <= 0 is undefined -> error at construction or transform."""
    with pytest.raises(ValueError):
        AxisCalibration(
            x=AxisRef(p1_pixel=100.0, p1_value=0.0, p2_pixel=500.0, p2_value=10.0, scale="linear"),
            y=AxisRef(p1_pixel=400.0, p1_value=0.0, p2_pixel=100.0, p2_value=1000.0, scale="log"),
        )


# ---------------------------------------------------------------------------
# record_digitized(): proposed EvidenceItem with all schema fields.
# ---------------------------------------------------------------------------

def test_record_digitized_produces_proposed_item():
    calib = _linear_calib()
    item = record_digitized(
        ev_id="dig-1",
        spec_id="spec-x",
        quantity="dry_weight",
        unit="g",
        calib=calib,
        point_pixel=(300.0, 250.0),
        source="Fig 2 / 10.1234/abc",
        target_id="hyp-1",
        extractor="agent-A",
    )
    assert isinstance(item, EvidenceItem)
    assert item.kind == EvidenceKind.DIGITIZED
    assert item.digitized is not None
    d = item.digitized
    assert d.state == "proposed"
    assert d.method == "deterministic"
    assert d.quantity == "dry_weight"
    assert d.unit == "g"
    assert d.value == pytest.approx(50.0)  # the y data value at pixel 250
    assert d.source == "Fig 2 / 10.1234/abc"
    assert d.extractor == "agent-A"
    assert d.read_uncert is not None and d.read_uncert > 0
    assert d.verification is None  # not yet verified
    # value/unit may also surface on Result (the design allows value/unit -> Result).
    assert item.result.point == pytest.approx(50.0)


def test_record_digitized_round_trips():
    """The digitized sub-model survives model_dump -> model_validate unchanged."""
    calib = _linear_calib()
    item = record_digitized(
        ev_id="dig-1", spec_id="spec-x", quantity="q", unit="u", calib=calib,
        point_pixel=(300.0, 250.0), source="Fig 1", target_id="hyp-1", extractor="agent-A",
    )
    blob = item.model_dump(mode="json")
    back = EvidenceItem.model_validate(blob)
    assert back == item
    assert back.digitized is not None
    assert back.digitized.state == "proposed"
    assert back.digitized.axis_calib is not None


# ---------------------------------------------------------------------------
# verify_digitized(): the INDEPENDENT replot check + verifier_id (extractor != verifier).
# ---------------------------------------------------------------------------

def test_verify_digitized_promotes_to_verified_with_independent_verifier():
    calib = _linear_calib()
    proposed = record_digitized(
        ev_id="dig-1", spec_id="spec-x", quantity="q", unit="u", calib=calib,
        point_pixel=(300.0, 250.0), source="Fig 1", target_id="hyp-1", extractor="agent-A",
    )
    verified = verify_digitized(proposed, verifier_id="agent-B")
    assert verified.digitized is not None
    assert verified.digitized.state == "verified"
    assert verified.digitized.verification is not None
    v = verified.digitized.verification
    assert v.verifier_id == "agent-B"
    assert v.method == "replot"
    assert v.result == "reproduced"
    # extractor is preserved and is DIFFERENT from the verifier.
    assert verified.digitized.extractor == "agent-A"
    assert v.verifier_id != verified.digitized.extractor


def test_verify_digitized_rejects_self_certification():
    """verifier_id == extractor is the self-certification ban for this kind."""
    calib = _linear_calib()
    proposed = record_digitized(
        ev_id="dig-1", spec_id="spec-x", quantity="q", unit="u", calib=calib,
        point_pixel=(300.0, 250.0), source="Fig 1", target_id="hyp-1", extractor="agent-A",
    )
    with pytest.raises(ValueError):
        verify_digitized(proposed, verifier_id="agent-A")


def test_verify_digitized_rejects_missing_extractor():
    """DEFENSE-IN-DEPTH: ``verify_digitized`` refuses an item with no recorded extractor
    (here forged past the schema via ``model_construct``) -- without a recorded extractor
    the self-certification ban cannot be enforced, so verification must not proceed
    (otherwise 'verifier != None' would falsely certify a self-read)."""
    calib = _linear_calib()
    axis_calib = calib.to_jsonable()
    axis_calib["point"] = [300.0, 250.0]
    forged = DigitizedData.model_construct(
        quantity="q", value=50.0, unit="u", source="Fig 1", method="deterministic",
        axis_calib=axis_calib, read_uncert=0.05, state="proposed",
        verification=None, extractor=None,  # bypass: no recorded extractor
    )
    item = EvidenceItem(
        id="dig-1",
        spec_id="spec-x",
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref="fig.py:1"),
        result=Result(type="quantitative", point=50.0),
        bears_on=[Bearing(target_id="hyp-1", direction=BearingDirection.SUPPORTS)],
        digitized=forged,
    )
    with pytest.raises(ValueError) as exc:
        verify_digitized(item, verifier_id="agent-B")
    assert "extractor" in str(exc.value).lower()


def test_record_digitized_rejects_empty_extractor():
    """``record_digitized`` rejects an empty/whitespace extractor (fail-closed at the
    borrow layer too -- a digitization must record who extracted it)."""
    calib = _linear_calib()
    with pytest.raises(ValueError):
        record_digitized(
            ev_id="dig-1", spec_id="spec-x", quantity="q", unit="u", calib=calib,
            point_pixel=(300.0, 250.0), source="Fig 1", target_id="hyp-1", extractor="",
        )


def test_verify_digitized_replot_detects_tampered_value():
    """The replot check recomputes values back to pixel space; a value that no longer
    matches the recorded pixel (tampered) fails verification (DIVERGED, not reproduced)."""
    calib = _linear_calib()
    proposed = record_digitized(
        ev_id="dig-1", spec_id="spec-x", quantity="q", unit="u", calib=calib,
        point_pixel=(300.0, 250.0), source="Fig 1", target_id="hyp-1", extractor="agent-A",
    )
    # Tamper the recorded value so it no longer corresponds to its pixel coordinate.
    tampered = proposed.model_copy(
        update={"digitized": proposed.digitized.model_copy(update={"value": 999.0})}
    )
    with pytest.raises(ValueError):
        verify_digitized(tampered, verifier_id="agent-B")


def test_verify_digitized_round_trips():
    calib = _linear_calib()
    proposed = record_digitized(
        ev_id="dig-1", spec_id="spec-x", quantity="q", unit="u", calib=calib,
        point_pixel=(300.0, 250.0), source="Fig 1", target_id="hyp-1", extractor="agent-A",
    )
    verified = verify_digitized(proposed, verifier_id="agent-B")
    back = EvidenceItem.model_validate(verified.model_dump(mode="json"))
    assert back == verified
    assert back.digitized.verification.verifier_id == "agent-B"
