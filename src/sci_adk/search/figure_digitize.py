"""
Deterministic figure digitizer -- a CAPABILITY PLUGIN (outside the rigor kernel).

design/figure-digitization.md §6 "Borrow": digitization *execution* (a
WebPlotDigitizer-style deterministic transform: axis calibration by a human/agent,
point extraction by pixel position) and replot-*verification* execution live here, in
``sci_adk.search`` -- NEVER reimplemented in the kernel. The kernel (core/loop/render)
MUST NOT import this module; the F4 seam test keeps that one-way (this module imports
the kernel's ``EvidenceItem`` types, which is the allowed direction).

What this module is (v1, MVP):
  - ``digitize(axis_calib, point_pixels, *, ...)`` -- the PURE pixel -> data transform
    (linear interpolation; log10-axis support), with ``read_uncert`` derived from the
    marker/resolution input. Fully testable, no GUI, no figure file.
  - ``record_digitized(...)`` -- wrap the agent-supplied pixel coords + computed values
    into a ``proposed`` digitized ``EvidenceItem`` (kind=DIGITIZED, state=proposed).
  - ``verify_digitized(item, *, verifier_id)`` -- the INDEPENDENT replot check: recompute
    the extracted value back to pixel space and confirm it sits within tolerance of the
    recorded point, recorded with ``verifier_id`` (enforcing ``verifier_id != extractor``).

What this module is NOT (design/figure-digitization.md "Out of scope"):
  - NOT a GUI / WebPlotDigitizer integration -- v1 takes agent-PROVIDED pixel coords.
    WHICH points to read stays agent-driven (no automatic point detection).
  - NOT the ``vlm`` method -- ``method="vlm"`` is a reserved enum value; ``digitize`` /
    ``record_digitized`` refuse to PRODUCE one (the unimplemented path raises).
  - NOT pdffigures2 figure-location.

No heavy dependencies: stdlib ``math`` only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, model_validator

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

# Default replot tolerance (pixels): how close the recomputed pixel must be to the
# recorded pixel for the independent check to count as "reproduced". This is a
# verification-fidelity scalar of the BORROW layer, NOT a metric/decision threshold
# (no DecisionRule consumes it); the kernel's no-hardcoded-metric rule governs decision
# constants, which all come from DecisionRule.params -- this is not one.
_DEFAULT_REPLOT_TOL_PX = 1.0


class AxisRef(BaseModel):
    """
    A single axis calibration: two reference points with known pixel + data values.

    Two distinct reference points fix an affine (linear) OR log10 mapping between pixel
    position and data value along one axis. ``scale="linear"`` interpolates in data
    space; ``scale="log"`` interpolates in log10 space (so a fixed pixel step is a fixed
    multiplicative data step) and requires strictly positive reference values.

    Attributes:
        p1_pixel, p1_value: first reference point (pixel coordinate, known data value).
        p2_pixel, p2_value: second reference point.
        scale: ``linear`` | ``log`` -- the axis scale.
    """

    model_config = {"frozen": True}

    p1_pixel: float = Field(..., description="First reference pixel coordinate")
    p1_value: float = Field(..., description="Data value at the first reference pixel")
    p2_pixel: float = Field(..., description="Second reference pixel coordinate")
    p2_value: float = Field(..., description="Data value at the second reference pixel")
    scale: Literal["linear", "log"] = Field(default="linear", description="Axis scale")

    @model_validator(mode="after")
    def _validate(self) -> "AxisRef":
        if self.p1_pixel == self.p2_pixel:
            raise ValueError(
                "degenerate axis: the two reference pixels coincide -- they cannot "
                "define a scale (divide-by-zero)"
            )
        if self.scale == "log":
            if self.p1_value <= 0 or self.p2_value <= 0:
                raise ValueError(
                    "log axis requires strictly positive reference values "
                    f"(got p1_value={self.p1_value}, p2_value={self.p2_value})"
                )
            if self.p1_value == self.p2_value:
                raise ValueError(
                    "degenerate log axis: the two reference data values coincide"
                )
        return self

    def pixel_to_value(self, pixel: float) -> float:
        """Map a pixel coordinate to a data value along this axis.

        Linear: affine interpolation in data space. Log: affine interpolation in log10
        space, then ``10 ** result`` (a fixed pixel step is a fixed multiplicative step).
        Interpolation EXTENDS past the reference pixels (no clamping) -- the calibration
        defines a line, not a segment.
        """
        frac = (pixel - self.p1_pixel) / (self.p2_pixel - self.p1_pixel)
        if self.scale == "linear":
            return self.p1_value + frac * (self.p2_value - self.p1_value)
        # log: interpolate in log10 space.
        log1, log2 = math.log10(self.p1_value), math.log10(self.p2_value)
        return 10.0 ** (log1 + frac * (log2 - log1))

    def value_to_pixel(self, value: float) -> float:
        """Inverse of :meth:`pixel_to_value` (used by the replot verification).

        Linear: invert the affine map. Log: take log10 of the value, invert in log10
        space. Raises on a non-positive value for a log axis (undefined).
        """
        if self.scale == "linear":
            frac = (value - self.p1_value) / (self.p2_value - self.p1_value)
        else:
            if value <= 0:
                raise ValueError(f"log axis value must be positive, got {value}")
            log1, log2 = math.log10(self.p1_value), math.log10(self.p2_value)
            frac = (math.log10(value) - log1) / (log2 - log1)
        return self.p1_pixel + frac * (self.p2_pixel - self.p1_pixel)

    def units_per_pixel_at(self, pixel: float) -> float:
        """Local data-units-per-pixel at ``pixel`` (for read uncertainty).

        Linear: constant slope ``(value_span)/(pixel_span)``. Log: the derivative of
        ``10 ** (linear-in-log)`` at the pixel -- ``value * ln(10) * log_slope`` -- so a
        fixed pixel error is MULTIPLICATIVE in data space (uncertainty grows with value).
        Returned as a positive magnitude.
        """
        pixel_span = self.p2_pixel - self.p1_pixel
        if self.scale == "linear":
            return abs((self.p2_value - self.p1_value) / pixel_span)
        log1, log2 = math.log10(self.p1_value), math.log10(self.p2_value)
        log_slope = (log2 - log1) / pixel_span
        value = self.pixel_to_value(pixel)
        return abs(value * math.log(10.0) * log_slope)


class AxisCalibration(BaseModel):
    """Calibration for both axes of a figure (x and y :class:`AxisRef`)."""

    model_config = {"frozen": True}

    x: AxisRef = Field(..., description="X-axis calibration")
    y: AxisRef = Field(..., description="Y-axis calibration")

    def to_jsonable(self) -> dict:
        """A plain JSON-able snapshot for ``DigitizedData.axis_calib``.

        Stored as plain data (not the typed model) so the kernel's ``DigitizedData``
        round-trips the calibration WITHOUT importing this module (the F4 seam stays
        one-way: kernel never imports search/).
        """
        return {
            "x": [self.x.p1_pixel, self.x.p1_value, self.x.p2_pixel, self.x.p2_value, self.x.scale],
            "y": [self.y.p1_pixel, self.y.p1_value, self.y.p2_pixel, self.y.p2_value, self.y.scale],
        }


@dataclass(frozen=True)
class DigitizedPoint:
    """One digitized data point: the recovered (x, y) values + per-axis read uncertainty.

    Attributes:
        value_x, value_y: the recovered data-space coordinates.
        read_uncert_x, read_uncert_y: read uncertainty per axis (data units), derived
            from the marker radius via the local data-units-per-pixel.
        pixel: the source pixel coordinate (kept for the replot verification).
    """

    value_x: float
    value_y: float
    read_uncert_x: Optional[float]
    read_uncert_y: Optional[float]
    pixel: Tuple[float, float]


def digitize(
    calib: AxisCalibration,
    point_pixels: Sequence[Tuple[float, float]],
    *,
    axis_type: Optional[str] = None,
    marker_radius_px: float = 0.0,
) -> List[DigitizedPoint]:
    """Transform agent-supplied pixel coordinates into data-space values (PURE).

    Linear interpolation by default; log10 support per axis via the calibration's
    ``scale``. ``read_uncert`` is derived from ``marker_radius_px`` (the marker/resolution
    read error in pixels) times the local data-units-per-pixel -- additive on a linear
    axis, multiplicative (grows with value) on a log axis.

    Args:
        calib: the two-axis calibration (each axis carries its own ``scale``).
        point_pixels: the ``(x_pixel, y_pixel)`` coordinates to digitize (agent-picked;
            WHICH points to read stays agent-driven -- no auto-detection in v1).
        axis_type: optional override; when given, must be ``"linear"`` or ``"log"`` and
            is applied to BOTH axes (a convenience for same-scale figures). When None
            (default), each axis uses its own ``AxisRef.scale``.
        marker_radius_px: the marker radius / read resolution in pixels (>= 0). 0 leaves
            ``read_uncert`` at 0 (no read-error model requested).

    Returns:
        One :class:`DigitizedPoint` per input pixel.

    Raises:
        ValueError: on a degenerate axis (handled by ``AxisRef``), an unknown
            ``axis_type``, or a negative ``marker_radius_px``.
    """
    if marker_radius_px < 0:
        raise ValueError(f"marker_radius_px must be >= 0, got {marker_radius_px}")
    x_axis, y_axis = calib.x, calib.y
    if axis_type is not None:
        if axis_type not in ("linear", "log"):
            raise ValueError(f"axis_type must be 'linear' or 'log', got {axis_type!r}")
        x_axis = x_axis.model_copy(update={"scale": axis_type})
        y_axis = y_axis.model_copy(update={"scale": axis_type})

    points: List[DigitizedPoint] = []
    for px, py in point_pixels:
        vx = x_axis.pixel_to_value(px)
        vy = y_axis.pixel_to_value(py)
        ux = x_axis.units_per_pixel_at(px) * marker_radius_px if marker_radius_px else None
        uy = y_axis.units_per_pixel_at(py) * marker_radius_px if marker_radius_px else None
        points.append(
            DigitizedPoint(
                value_x=vx, value_y=vy, read_uncert_x=ux, read_uncert_y=uy, pixel=(px, py)
            )
        )
    return points


def record_digitized(
    *,
    ev_id: str,
    spec_id: str,
    quantity: str,
    unit: str,
    calib: AxisCalibration,
    point_pixel: Tuple[float, float],
    source: str,
    target_id: str,
    extractor: str,
    direction: BearingDirection = BearingDirection.SUPPORTS,
    metric_point: Optional[float] = None,
    method: str = "deterministic",
) -> EvidenceItem:
    """Build a ``proposed`` digitized ``EvidenceItem`` from one agent-picked pixel.

    The recovered Y data value is the digitized VALUE (the figure number), recorded in
    ``DigitizedData.value`` (with ``unit``). The ``Result.point`` carries the statistic
    the DecisionRule reads -- ``metric_point`` when given (a normalized test metric),
    else the recovered value itself (so a bare digitization is still evaluable). The item
    is state=``proposed`` (NOT evidence-grade): it must pass ``verify_digitized`` before
    it can count (figure-digitization §3/§5).

    Args:
        ev_id, spec_id, target_id: identifiers (the bearing targets ``target_id``).
        quantity, unit, source: digitized schema fields (§4).
        calib: the axis calibration (snapshotted into ``axis_calib`` for round-trip).
        point_pixel: the agent-picked ``(x_pixel, y_pixel)`` of the data point.
        extractor: identity of the extractor (the verifier must differ).
        direction: bearing direction of this evidence on the hypothesis.
        metric_point: optional normalized statistic for ``Result.point`` (defaults to the
            recovered Y value).
        method: must be ``"deterministic"`` in v1; ``"vlm"`` is reserved + UNIMPLEMENTED.

    Raises:
        ValueError: if ``method`` is not ``"deterministic"`` (vlm is unimplemented).
    """
    if method != "deterministic":
        raise ValueError(
            f"method={method!r} is not implemented in v1; only 'deterministic' is "
            "supported ('vlm' is a reserved enum value, deferred per "
            "design/figure-digitization.md §7)"
        )
    # Fail-closed at the borrow layer too: a digitization must record WHO extracted it,
    # or the downstream self-certification ban (verifier != extractor) cannot be
    # enforced (design/figure-digitization.md §5).
    if not (extractor or "").strip():
        raise ValueError(
            "extractor identity is required and must be non-empty -- a digitization "
            "must record who extracted it (the self-certification ban depends on it)"
        )
    (pt,) = digitize(calib, [point_pixel], marker_radius_px=_marker_radius_for(calib))
    value = pt.value_y
    read_uncert = pt.read_uncert_y
    point_for_rule = metric_point if metric_point is not None else value

    # Snapshot the calibration AND the agent-picked source pixel. Storing the source
    # pixel makes the replot check sensitive to TAMPERING of the value: verification
    # inverts the recorded value through the calibration and compares to this stored
    # pixel, so a value edited away from its pixel fails the overlay (not a tautology).
    axis_calib = calib.to_jsonable()
    axis_calib["point"] = [float(point_pixel[0]), float(point_pixel[1])]

    return EvidenceItem(
        id=ev_id,
        spec_id=spec_id,
        kind=EvidenceKind.DIGITIZED,
        provenance=Provenance(code_ref=f"figure_digitize:{source}"),
        result=Result(type="quantitative", point=point_for_rule),
        bears_on=[Bearing(target_id=target_id, direction=direction)],
        digitized=DigitizedData(
            quantity=quantity,
            value=value,
            unit=unit,
            source=source,
            method="deterministic",
            axis_calib=axis_calib,
            read_uncert=read_uncert,
            state="proposed",
            verification=None,
            extractor=extractor,
        ),
    )


def verify_digitized(
    item: EvidenceItem,
    *,
    verifier_id: str,
    tolerance_px: float = _DEFAULT_REPLOT_TOL_PX,
    artifact: Optional[str] = None,
) -> EvidenceItem:
    """Independently verify a digitized item by REPLOT, promoting it to ``verified``.

    The replot check recomputes the recorded data value back to pixel space (via the
    recorded ``axis_calib``) and confirms it sits within ``tolerance_px`` of the recorded
    point pixel. A value that no longer corresponds to its pixel (tampered) FAILS the
    check (raises). On success, returns a NEW EvidenceItem (the input is frozen) with
    ``state="verified"`` and a :class:`DigitizedVerification` record naming
    ``verifier_id`` -- which MUST differ from the extractor (the self-certification ban).

    Args:
        item: a ``proposed`` (or re-verifiable) digitized EvidenceItem.
        verifier_id: the INDEPENDENT verifier's identity (!= the extractor).
        tolerance_px: max pixel distance for the replot to count as reproduced.
        artifact: optional reference to the overlay artifact.

    Raises:
        ValueError: if ``item`` is not a digitized item; if ``verifier_id`` equals the
            extractor (self-certification); if the calibration is missing; or if the
            replot diverges beyond ``tolerance_px`` (DIVERGED, not reproduced).
    """
    if item.kind != EvidenceKind.DIGITIZED or item.digitized is None:
        raise ValueError("verify_digitized requires a digitized EvidenceItem")
    d = item.digitized
    # Defense-in-depth (the extractor=None bypass): without a recorded extractor the
    # self-certification ban cannot be enforced -- refuse to verify rather than let
    # 'verifier_id != None' falsely certify a self-read (design/figure-digitization §5).
    if not (d.extractor or "").strip():
        raise ValueError(
            "extractor identity not recorded -- cannot enforce the self-certification "
            "ban (verifier != extractor), so verification must not proceed"
        )
    if verifier_id == d.extractor:
        raise ValueError(
            f"self-certification refused: verifier_id ({verifier_id!r}) equals the "
            "extractor -- the one who read the value off the plot may not certify it "
            "(design/figure-digitization.md §5)"
        )
    calib = _calib_from_jsonable(d.axis_calib)
    # Replot: recompute the recorded VALUE back to a y-pixel, compare to the recorded
    # pixel. (Only the y-axis is checked here -- record_digitized records the y value;
    # the x coordinate is the independent variable / category position.)
    recorded_pixel = _recorded_y_pixel(d)
    replot_pixel = calib.y.value_to_pixel(d.value)
    divergence = abs(replot_pixel - recorded_pixel)
    if divergence > tolerance_px:
        raise ValueError(
            f"replot verification DIVERGED: recomputing value={d.value} back to pixel "
            f"gives {replot_pixel:.6g}, which is {divergence:.6g}px from the recorded "
            f"pixel {recorded_pixel:.6g} (> tolerance {tolerance_px}px) -- the recorded "
            "value does not correspond to its pixel coordinate"
        )
    verification = DigitizedVerification(
        method="replot",
        verifier_id=verifier_id,
        result="reproduced",
        artifact=artifact or "replot-overlay",
    )
    return item.model_copy(
        update={"digitized": d.model_copy(update={"state": "verified", "verification": verification})}
    )


# -- internals ---------------------------------------------------------------

def _marker_radius_for(calib: AxisCalibration) -> float:
    """The read-uncertainty marker radius used at recording time.

    A single, explicit default (in pixels) so ``record_digitized`` always derives a
    positive ``read_uncert`` (reconstruction carries uncertainty intrinsically,
    figure-digitization §2). Callers needing a different value can call ``digitize``
    directly with their own ``marker_radius_px``.
    """
    return 2.0


def _recorded_y_pixel(d: DigitizedData) -> float:
    """The agent-picked source y-pixel stored at record time (``axis_calib['point']``).

    ``record_digitized`` stores the source pixel alongside the calibration snapshot. The
    replot check compares the calibration's inverse of the recorded VALUE against this
    independently-stored pixel, so a value tampered away from its pixel diverges -- the
    check is sensitive to value edits, not a tautology.
    """
    point = (d.axis_calib or {}).get("point")
    if point is None or len(point) != 2:
        raise ValueError(
            "digitized item is missing its recorded source pixel (axis_calib['point']) "
            "-- cannot replot-verify"
        )
    return float(point[1])


def _calib_from_jsonable(blob: Optional[dict]) -> AxisCalibration:
    """Reconstruct an :class:`AxisCalibration` from a ``DigitizedData.axis_calib`` snapshot."""
    if not blob or "x" not in blob or "y" not in blob:
        raise ValueError("digitized item is missing its axis_calib -- cannot replot-verify")

    def _axis(vals) -> AxisRef:
        p1_pixel, p1_value, p2_pixel, p2_value, scale = vals
        return AxisRef(
            p1_pixel=p1_pixel, p1_value=p1_value, p2_pixel=p2_pixel, p2_value=p2_value,
            scale=scale,
        )

    return AxisCalibration(x=_axis(blob["x"]), y=_axis(blob["y"]))


__all__ = [
    "AxisRef",
    "AxisCalibration",
    "DigitizedPoint",
    "digitize",
    "record_digitized",
    "verify_digitized",
]
