"""
The P2 number-audit: a PURE deterministic checker that every quantitative literal in a
manuscript traces to the RECORDED-VALUE POOL (SPEC-PAPER-GATE-001 M1, OD-2 stage iii + OD-3).

Closes leak L2 ("fidelity is opt-in per number"): today only values authored through the
``\\evval``/``\\status`` macros (render/factref.py) or native-plot y-values pulled by
``evidence_id`` (render/figures.py) are record-bound -- a number typed as a bare literal in
prose or a hand-typed table cell is COMPLETELY outside the gate. This checker tokenizes EVERY
quantitative literal in ``main.tex`` + ``si.tex`` (prose decimals / percentages / ratios AND
table data cells) and FAILS on any token absent from the recorded-value pool.

Record vs belief (the FROZEN invariant): the audit compares tokens ONLY against RECORDED
values; it never fabricates, infers, or accepts a "seems-right" value, and a human/agent manual
spot-check does NOT substitute for the gate. The recorded-value pool (OD-2 stage iii) is:

  - Claim point statistics (the recorded ``Claim.confidence.value``),
  - Evidence ``Result`` scalars (point / effect_size / p_value / posterior / residual /
    predictive_error / ci bounds) AND scalar fields of the Evidence ``finding`` JSON (the same
    values ``\\evval`` can already resolve -- so a paper whose numbers come from the record
    audits clean), and
  - the per-figure CSV values the figures were rendered from (the package's ``02_data/*.csv``).

Derived-number policy (OD-2): a value that is recomputable from TWO recorded operands by a
ratio / difference / sum / product, within tolerance, is accepted (a reported ratio of two
recorded means is not "unbacked"). This bounds the false-positive risk R1 without admitting
arbitrary fabricated numbers (an unbacked literal with no recorded operand pair still fails).

Tokenizer scope (OD-3): audited = prose decimals / percentages / ratios and table data cells;
IGNORED = section / figure / table / equation / reference numbers (the arguments of
``\\ref``/``\\cite``/``\\label``/``\\section``/``\\eqref`` etc.), dates, page numbers, version
strings, and math-mode structural literals (the contents of ``$...$``).

This module is PURE (data in, verdict out): no LLM, no recompile, no network. Like
``render/factref.py`` and ``render/consistency.py`` it lives in ``render/`` (the kernel) and
imports ``sci_adk.core`` ONLY (the F4 seam). It is a deterministic checker over explicit
markup -- NOT NLP and no language model judges the manuscript (spec.md Exclusions).

Reference: design/paper-writing-enforcement.md (the three leaks + the OD resolutions),
design/render-architecture-reframe.md (the moved line + factref sibling), src/sci_adk/render/
factref.py (the per-macro fidelity gate this generalizes).
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from sci_adk.core.claim import Claim
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.spec import Spec

# The Evidence ``Result`` numeric scalar fields that enter the pool (mirrors the factref
# ``_RESULT_SCALARS`` set + the figure y-fields). ``ci`` is a 2-list handled separately.
_RESULT_SCALARS: tuple[str, ...] = (
    "point",
    "effect_size",
    "p_value",
    "posterior",
    "residual",
    "predictive_error",
)

# Absolute + relative tolerance for "this token equals a recorded value". A reported number is
# often a ROUNDED form of the recorded statistic (0.6123 -> 0.61), so the match is generous on
# the displayed precision while still distinguishing genuinely different values.
_ABS_TOL = 5e-3
_REL_TOL = 1e-2


def _close(a: float, b: float) -> bool:
    """True iff ``a`` and ``b`` agree within the audit tolerance (rounded-display friendly)."""
    return math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


# -- recorded-value pool -----------------------------------------------------

@dataclass(frozen=True)
class RecordedValuePool:
    """The frozen set of numeric values the engine can derive from the record (OD-2).

    A token is "backed" iff it equals a pool value within tolerance, OR is a derived ratio /
    difference / sum / product of two pool values within tolerance (the derived-number policy).
    The pool is built once per artifact and is the ONLY thing the audit compares against
    (record vs belief: never a fabricated or "seems-right" value).
    """

    values: tuple[float, ...]

    def contains(self, token: float) -> bool:
        """True iff ``token`` equals a recorded value within tolerance (no derivation)."""
        return any(_close(token, v) for v in self.values)

    def backs(self, token: float) -> bool:
        """True iff ``token`` is recorded OR a derived transform of two recorded operands.

        Derived policy (OD-2): a value recomputable from two recorded operands by a ratio /
        difference / sum / product (within tolerance) is accepted -- a reported ratio of two
        recorded means is not "unbacked". An unbacked literal with no such operand pair fails.
        """
        if self.contains(token):
            return True
        for i, a in enumerate(self.values):
            for b in self.values[i:]:
                if _close(token, a + b) or _close(token, abs(a - b)):
                    return True
                if _close(token, a * b):
                    return True
                if b != 0 and _close(token, a / b):
                    return True
                if a != 0 and _close(token, b / a):
                    return True
        return False

    @staticmethod
    def from_values(values: Iterable[float]) -> "RecordedValuePool":
        """Build a pool from raw numeric values (de-duplicated, sorted, finite only)."""
        seen: set[float] = set()
        for v in values:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(f):
                seen.add(f)
        return RecordedValuePool(values=tuple(sorted(seen)))

    @staticmethod
    def from_record(
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceItem],
        spec: Spec | None = None,
    ) -> "RecordedValuePool":
        """The per-run pool: Claim point statistics + Evidence Result scalars + finding JSON
        + the Spec's pre-registered DecisionRule numeric thresholds."""
        return pool_from_record(claims, evidence, spec)

    @staticmethod
    def from_data_csvs(data_dir: Path) -> "RecordedValuePool":
        """The package pool: every numeric cell of every ``02_data/*.csv`` (record-derived).

        PURE-ish (reads the shipped CSVs only). Collects every parseable numeric cell from
        every ``*.csv`` under ``data_dir`` -- ``claims_all.csv`` (point_statistic, threshold)
        plus any per-figure CSVs the figures were rendered from. A missing dir -> empty pool.
        """
        values: List[float] = []
        if not data_dir.is_dir():
            return RecordedValuePool(values=())
        for path in sorted(data_dir.glob("*.csv")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for row in csv.reader(text.splitlines()):
                for cell in row:
                    num = _parse_number(cell)
                    if num is not None:
                        values.append(num)
        return RecordedValuePool.from_values(values)


def pool_from_record(
    claims: Sequence[Claim],
    evidence: Sequence[EvidenceItem],
    spec: Spec | None = None,
) -> RecordedValuePool:
    """Build the per-run recorded-value pool from the recorded Claims + Evidence (OD-2 iii).

    Sources (each a RECORDED value -- never fabricated):
      - every Claim's ``confidence.value`` (the recorded point statistic of the belief);
      - every Evidence ``Result`` numeric scalar (point / effect_size / p_value / posterior /
        residual / predictive_error) and both ``ci`` bounds;
      - every scalar field of a structured Evidence ``finding`` JSON (the same values
        ``\\evval`` resolves), so a finding like ``{"ratio": 4.6}`` is citable;
      - every NUMERIC ``DecisionRule.params`` value of the frozen Spec's hypotheses (the
        pre-registered decision thresholds -- e.g. a ``threshold`` / ``min_odds`` / ``null
        value`` -- which a manuscript legitimately reports as the criterion it tested against).
    """
    values: List[float] = []
    if spec is not None:
        for hyp in spec.hypotheses:
            params = getattr(hyp.decision_rule, "params", None) or {}
            for value in params.values():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values.append(float(value))
    for claim in claims:
        if claim.confidence.value is not None:
            values.append(float(claim.confidence.value))
    for item in evidence:
        result = item.result
        for field in _RESULT_SCALARS:
            scalar = getattr(result, field, None)
            if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
                values.append(float(scalar))
        if result.ci:
            values.extend(float(b) for b in result.ci)
        finding = result.finding
        if finding:
            try:
                data = json.loads(finding)
            except (json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, dict):
                for value in data.values():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        values.append(float(value))
    return RecordedValuePool.from_values(values)


# -- tokenizer (OD-3) --------------------------------------------------------

@dataclass(frozen=True)
class QuantToken:
    """One audited quantitative literal: its numeric value + the raw text as it appeared."""

    value: float
    raw: str


# A number literal: optional sign, integer/decimal, optional scientific exponent. The leading
# guard ``(?<![\w.])`` rejects a number glued to a word/decimal on the LEFT (so ``sec3`` /
# ``v1.2`` fragments do not match). The trailing guard ``(?![\d])`` only rejects when a DIGIT
# follows -- a trailing sentence period (``7.3.``), a percent (``42%``), or a multiplier marker
# (``4.6x``) is allowed (the marker is not part of the captured value). ``\d+\.\d+`` is greedy,
# so ``7.3`` captures the full decimal before the period guard applies to what follows.
_NUMBER_RE = re.compile(
    r"(?<![\w.])(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?![\d]|\.\d)"
)

# Spans whose interior numbers are STRUCTURAL, not data, and are stripped before tokenizing
# (OD-3 ignore-list). Each removes the WHOLE construct (command + braced arg) so a label like
# ``sec:3`` or a cite key ``Author2020`` never contributes a token.
#   - reference/label/cite/section/eqref commands and their braced arguments;
#   - inline + display math ($...$, \(...\), \[...\]) -- math-mode structural literals;
#   - LaTeX comment lines.
_STRIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?m)(?<!\\)%.*$"),                       # comment to end of line
    re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref|cite[a-zA-Z]*"
               r"|label|section|subsection|subsubsection|paragraph|input|include"
               r"|includegraphics|bibliographystyle|usepackage|documentclass)"
               r"\*?(?:\[[^\]]*\])?\{[^{}]*\}"),
    # Verbatim / code / path / URL spans wrap IDENTIFIERS, not data: a folder label
    # (``\texttt{04_scripts}``), a record digest (``\texttt{<sha>}``), a file path, or a URL
    # carries digit groups that are provenance/structural literals, never a measured quantity
    # (OD-3 ignore-list: version strings + structural literals). Strip the whole span.
    re.compile(r"\\(?:texttt|verb|path|url|href|nolinkurl)\*?\{[^{}]*\}"),
    # Macro definitions are structural LaTeX, not data: ``\newcommand{\x}[3]{#3}`` carries an
    # arity ``[3]`` and an arg reference ``#3`` that are markup mechanics, never a measured
    # quantity. Strip the whole definition head + any ``#N`` argument references.
    re.compile(r"\\(?:newcommand|renewcommand|providecommand|def|newenvironment)"
               r"\*?(?:\{\\?[A-Za-z@]+\}|\\[A-Za-z@]+)(?:\[\d*\])*(?:\[[^\]]*\])?"),
    re.compile(r"#\d+"),                                  # macro arg reference (#1, #3, ...)
    re.compile(r"\$\$.*?\$\$", re.DOTALL),                # display math $$...$$
    re.compile(r"\$.*?\$", re.DOTALL),                    # inline math $...$
    re.compile(r"\\\[.*?\\\]", re.DOTALL),                # \[ ... \]
    re.compile(r"\\\(.*?\\\)", re.DOTALL),                # \( ... \)
    re.compile(r"\\begin\{(?:equation|align|gather|math|displaymath)\*?\}"
               r".*?\\end\{(?:equation|align|gather|math|displaymath)\*?\}", re.DOTALL),
)

# A date (ISO ``YYYY-MM-DD`` / ``YYYY/MM/DD``) or a dotted version string (``v1.2.3`` /
# ``1.2.3``) -- their digit groups are NOT data. Replaced with a space before tokenizing.
_DATE_RE = re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b")
_VERSION_RE = re.compile(r"\bv?\d+\.\d+\.\d+\b")
# A bare 4-digit year token (``2024``) in prose is a date component, not a measured quantity.
_YEAR_RE = re.compile(r"(?<![\w.])\d{4}(?![\w.\d])")
# "page 12" / "pp. 12-15" / "p. 7" -- page numbers are bibliographic, not data.
_PAGE_RE = re.compile(r"\b(?:pp?\.?|pages?)\s*\d+(?:\s*[-–]\s*\d+)?", re.IGNORECASE)


def _strip_structural(tex: str) -> str:
    """Remove the OD-3 ignore-list spans, leaving the prose + table data for tokenizing."""
    text = tex
    for pat in _STRIP_PATTERNS:
        text = pat.sub(" ", text)
    text = _DATE_RE.sub(" ", text)
    text = _VERSION_RE.sub(" ", text)
    text = _PAGE_RE.sub(" ", text)
    text = _YEAR_RE.sub(" ", text)
    return text


def tokenize_quantitative(tex: str) -> List[QuantToken]:
    """Every audited quantitative literal in ``tex`` (prose + table cells), OD-3 scope.

    PURE + deterministic. Strips the OD-3 ignore-list (ref/cite/label/section args, math-mode
    literals, dates, version strings, page numbers, comments), then extracts every remaining
    number literal. A percent (``42\\%``) or multiplier (``4.6x``) keeps its numeric value; the
    marker is not part of the value. Returns tokens in source order (stable report).
    """
    stripped = _strip_structural(tex)
    tokens: List[QuantToken] = []
    for match in _NUMBER_RE.finditer(stripped):
        raw = match.group(1)
        try:
            value = float(raw)
        except ValueError:
            continue
        tokens.append(QuantToken(value=value, raw=raw))
    return tokens


def _parse_number(cell: str) -> float | None:
    """Parse one CSV cell to a float (stripping a trailing ``%`` / ``x``), or None."""
    text = (cell or "").strip().rstrip("%xX")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


# -- the audit (REQ-PG-201/202/203/204) --------------------------------------

def number_audit_problems(
    tex: str, pool: RecordedValuePool, source: str
) -> List[str]:
    """Every quantitative token in ``tex`` NOT backed by the recorded-value pool (REQ-PG-202).

    PURE + deterministic + third-party re-runnable (REQ-PG-204). Tokenizes ``tex`` (OD-3
    scope), and for each token that is neither a recorded value nor a derived transform of two
    recorded operands (the derived-number policy), emits a problem line naming the unbacked
    token and its source document. Compares ONLY against the recorded pool -- never fabricates a
    value, never accepts a "seems-right" number (record vs belief, REQ-PG-203). De-duplicated +
    sorted for a stable report.
    """
    unbacked: set[str] = set()
    for token in tokenize_quantitative(tex):
        if not pool.backs(token.value):
            unbacked.add(
                f"number audit: {source} states {token.raw}, which is absent from the "
                f"recorded-value pool (no Claim/Evidence/figure-data value backs it)"
            )
    return sorted(unbacked)


__all__ = [
    "RecordedValuePool",
    "QuantToken",
    "pool_from_record",
    "tokenize_quantitative",
    "number_audit_problems",
]
