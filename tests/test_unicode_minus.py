"""A typographic minus (U+2212) must render as a minus, not as '?'.

The workspace instructions tell paper authors to type symbols as Unicode, and the
renderer's Unicode map had no entry for U+2212, so "−0.806" rendered as "?0.806"
(found while checking the second trial run's manuscript draft, 2026-10-09).
"""

from __future__ import annotations

from sci_adk.render.number_literals import find_literals
from sci_adk.render.paper import _latex_sanitize, _latex_sanitize_prose


def test_unicode_minus_renders_as_a_math_minus():
    assert "?" not in _latex_sanitize_prose("intercept −0.806")
    assert "?" not in _latex_sanitize("intercept −0.806")


def test_rendered_unicode_minus_is_read_as_a_negative_number():
    tex = _latex_sanitize_prose("intercept −0.806 and residual −1.86")
    values = sorted(lit.value for lit in find_literals(tex) if lit.value is not None)
    assert values == [-1.86, -0.806]
