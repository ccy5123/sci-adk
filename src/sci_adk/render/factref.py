"""
Record-fidelity fact substitution for agent-authored paper prose (the fidelity gate
of the "moved line", design/render-architecture-reframe.md).

The reframe shrinks the deterministic render spine to the record-fidelity essentials and
hands the paper's NARRATIVE to the in-session agent (rigor-shell-architecture.md §2.4:
"Writing paper prose" is OUT of the kernel). The one thing that must NOT move with the
narrative is the paper's record-derived FACTS -- the measured values and the Claim
verdicts. So an author does not write those as free literals; they write two markup
macros that the engine substitutes FROM THE RECORD at render time:

    \\evval{<evidence-id>}{<field>}   -> the recorded value (a Result scalar, or a
                                         scalar field of the Evidence finding JSON)
    \\status{<hypothesis-id>}         -> the experiment Claim's status (e.g. supported)

So the agent decides WHERE a fact goes; the engine fills WHAT it is, from the record.
A paper therefore cannot state a measured number or a verdict that is not in the record:
:func:`substitute_factrefs` is PURE, deterministic, and FAIL-LOUD -- an unknown evidence
id / field / hypothesis id raises ``ValueError`` (the same record-fidelity spirit as
``figures._y_value``), so the substitution either yields the true recorded value or
refuses to render.

This is the markup-based fidelity gate that keeps rigor while the narrative moves to the
agent. It is the same design language sci-adk already uses elsewhere -- a deterministic
checker over explicit markup, not NLP (the figure ``\\ref``<->``\\label`` gate, the
``\\novelty`` markup). It lives in ``render/`` (the kernel) and imports ``sci_adk.core``
ONLY (the F4 seam -- no adapter, no loop, no LLM, no fs/network).

Honest limit (documented, like consistency.py's line-comment rule): the gate guarantees
that every fact written VIA a macro is record-faithful; it cannot force an author to use
the macro for every number -- a bare literal typed in prose is outside the gate (the same
bound as the ``\\novelty`` markup). Authors write record-derived facts via the macros;
:func:`find_unresolved_factrefs` lets ``sci-adk verify`` flag a macro that somehow survived
into the rendered ``.tex`` (substitution bypassed / the .tex hand-edited).

Reference: design/render-architecture-reframe.md, design/rigor-shell-architecture.md (§2.4
the moved line), design/abstractions.md, src/sci_adk/render/figures.py (the sibling
record-fidelity, fail-loud renderer).
"""

from __future__ import annotations

import json
import math
import re
from typing import Sequence

from sci_adk.core.claim import Claim
from sci_adk.core.evidence import EvidenceItem

# ``\evval{<evidence-id>}{<field>}`` -- two single-argument brace groups, neither
# containing a nested brace (an id / field is a plain slug, never braced). ``\status
# {<hypothesis-id>}`` -- one such group. Both are anchored on the literal command name
# followed by ``{`` so ``\evvalue`` / ``\statusbar`` cannot match.
_EVVAL_RE = re.compile(r"\\evval\{([^{}]+)\}\{([^{}]+)\}")
_STATUS_RE = re.compile(r"\\status\{([^{}]+)\}")

# Any factref macro START -- used by the verify re-scan to catch a macro that survived
# into the rendered ``.tex`` (it never should: substitution removes them at render time).
_ANY_FACTREF_RE = re.compile(r"\\(?:evval|status)\{[^{}]*\}(?:\{[^{}]*\})?")

# The numeric Result scalar fields resolvable directly off ``item.result``. Mirrors the
# numeric scalars of ``sci_adk.core.evidence.Result`` (kept in sync with figures.YField +
# the SI quantitative fields). A field NOT in this set is looked up in the finding JSON.
_RESULT_SCALARS: tuple[str, ...] = (
    "point",
    "effect_size",
    "p_value",
    "posterior",
    "residual",
    "predictive_error",
)


def _format_value(value: object, evidence_id: str, field: str) -> str:
    """Deterministic, compile-safe rendering of one recorded scalar fact.

    A bool renders its text (``True``/``False``); an int/float via ``%g`` (drops trailing
    zeros, byte-stable -- ``100.0 -> 100``, ``0 -> 0``, ``0.61 -> 0.61``); a string is
    returned verbatim (it is sanitized downstream by the prose escaper, so a stray ``_``
    survives as text). A non-finite float (NaN/inf) is NOT a citable fact -- fail loud,
    the same record-fidelity rule as ``figures._y_value`` (a paper cannot state ``nan``).
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(
                f"\\evval{{{evidence_id}}}{{{field}}}: value is {value} (NaN/infinite) "
                f"-- not a citable fact (record fidelity)"
            )
        return f"{value:g}"
    return str(value)


def _resolve_evval(
    evidence_id: str, field: str, by_id: dict[str, EvidenceItem]
) -> str:
    """Resolve one ``\\evval{<id>}{<field>}`` to its recorded value (fail-loud).

    Resolution order: (1) a known Result scalar attribute that is not None; (2) a scalar
    field of the Evidence ``finding`` JSON (so a structured finding like
    ``{"n_distinct_noniso_pairs": 73, ...}`` is citable, not only the typed Result
    scalars). Anything else -- unknown id, field absent from both, a non-scalar finding
    value -- raises ``ValueError`` (record fidelity: a paper cannot cite a value the
    record does not hold).
    """
    item = by_id.get(evidence_id)
    if item is None:
        raise ValueError(
            f"\\evval cites unknown evidence id '{evidence_id}' -- a paper fact must "
            f"reference a real Evidence item (record fidelity)"
        )

    # (1) typed Result scalar.
    if field in _RESULT_SCALARS:
        scalar = getattr(item.result, field, None)
        if scalar is not None:
            return _format_value(scalar, evidence_id, field)

    # (2) a scalar field of the finding JSON.
    finding = item.result.finding
    if finding:
        try:
            data = json.loads(finding)
        except (json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict) and field in data:
            value = data[field]
            if isinstance(value, (bool, int, float, str)):
                return _format_value(value, evidence_id, field)
            raise ValueError(
                f"\\evval{{{evidence_id}}}{{{field}}}: finding value is non-scalar "
                f"({type(value).__name__}) -- not a citable fact"
            )

    raise ValueError(
        f"\\evval cites evidence '{evidence_id}' field '{field}', which is in neither "
        f"its Result scalars nor its finding JSON (record fidelity)"
    )


def _resolve_status(hypothesis_id: str, claim_by_hyp: dict[str, Claim]) -> str:
    """Resolve one ``\\status{<hyp-id>}`` to that hypothesis's experiment Claim status.

    Keyed on the EXPERIMENT claim (``claim-<hyp>``); the novelty claims
    (``claim-novelty-{result,method}-<hyp>``) are excluded by the caller so ``\\status``
    means the headline verdict, not a novelty sub-verdict. Fail-loud when no experiment
    Claim answers the hypothesis (a paper cannot state a verdict the record never derived).
    """
    claim = claim_by_hyp.get(hypothesis_id)
    if claim is None:
        raise ValueError(
            f"\\status cites hypothesis '{hypothesis_id}' with no experiment Claim -- "
            f"a paper cannot state a verdict the record never derived (record fidelity)"
        )
    return claim.status.value if hasattr(claim.status, "value") else str(claim.status)


def substitute_factrefs(
    text: str,
    evidence: Sequence[EvidenceItem],
    claims: Sequence[Claim],
) -> str:
    """Substitute every ``\\evval``/``\\status`` macro in ``text`` with its recorded value.

    PURE + deterministic + FAIL-LOUD. Run on RAW agent prose BEFORE the prose escaper:
    the substituted value is a number / status string (or a finding string), which the
    downstream :func:`paper._latex_sanitize_prose` then escapes as ordinary text -- so a
    string fact with a ``_`` is escaped correctly and ``\\ref``/``\\cite`` in the same
    prose are untouched (this function only matches ``\\evval``/``\\status``).

    Args:
        text: the raw agent prose slot (may contain ``\\evval``/``\\status`` macros).
        evidence: the run's Evidence record (each ``\\evval`` id is resolved here).
        claims: the run's Claims (each ``\\status`` hyp id resolves to its experiment
            Claim; novelty claims are excluded so ``\\status`` is the headline verdict).

    Returns:
        ``text`` with every factref macro replaced by its recorded value.

    Raises:
        ValueError: on an unknown evidence id / hypothesis id, a field absent from both
            the Result scalars and the finding JSON, a non-scalar / non-finite value, or
            a hypothesis with no experiment Claim (record fidelity -- never invent a fact).
    """
    by_id = {ev.id: ev for ev in evidence}
    # Experiment claim per hypothesis (exclude novelty claims -- \status is the headline).
    claim_by_hyp = {
        c.answers: c for c in claims if not c.id.startswith("claim-novelty-")
    }

    def _ev(match: re.Match) -> str:
        return _resolve_evval(match.group(1).strip(), match.group(2).strip(), by_id)

    def _st(match: re.Match) -> str:
        return _resolve_status(match.group(1).strip(), claim_by_hyp)

    text = _EVVAL_RE.sub(_ev, text)
    text = _STATUS_RE.sub(_st, text)
    return text


def find_unresolved_factrefs(tex: str) -> list[str]:
    """Return every factref macro that survived into a rendered ``.tex`` (should be none).

    PURE. :func:`substitute_factrefs` removes all macros at render time, so a residual
    ``\\evval``/``\\status`` in the emitted ``.tex`` means substitution was bypassed or the
    ``.tex`` was hand-edited -- a broken paper. ``sci-adk verify`` surfaces this as a
    fidelity divergence. De-duplicated, sorted for a stable report.
    """
    return sorted({m.group(0) for m in _ANY_FACTREF_RE.finditer(tex)})


__all__ = ["substitute_factrefs", "find_unresolved_factrefs"]
