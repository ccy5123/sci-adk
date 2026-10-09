"""
The declared NUMBER list (design/declared-numbers.md §4.1).

The problem it solves. A manuscript may state only numbers the record holds. The checker
that enforced this before guessed, for every digit run in the paper, whether it was a
reported quantity or something else (a year, a page, an identifier), and then looked the
quantities up in a pool of recorded values. Whether "47" is a quantity depends on the
sentence -- a page in "p. 47", a prime in "P 47", a count in "47 chemicals" -- and a
deterministic checker cannot read the sentence. Every rule added for one case moved
errors between rejecting real numbers and silently passing unchecked ones.

So the role of each number is STATED, not inferred -- the treatment the conclusion
declarations already get (:mod:`sci_adk.core.declarations`):

    the literal as written | its document | its role | where it comes from

The manuscript stays plain LaTeX. This file is never submitted. ``sci-adk verify`` checks it
against the record and the text (:mod:`sci_adk.render.number_checks`) and reads no meaning:

  1. every literal in ``draft.tex`` / ``si.tex`` is listed (coverage);
  2. every source exists, and its value -- rounded to the printed precision of the
     literal -- equals the literal; a derived entry is recomputed from its operands; a
     citation year equals the bib field (resolution).

Roles:
  - ``recorded``   -- equals a recorded value: an Evidence field, a numeric field of the
    frozen Spec, or a literal written inside a Spec text field;
  - ``derived``    -- computed from named recorded values by a stated formula;
  - ``citation``   -- a field of a cited reference (its year), checked against the bib;
  - ``identifier`` -- not a quantity (a registry number, a version, a label in prose).
    Checked against nothing, and LISTED by verify, so every exemption is visible.

NOT frozen. Like the declaration list it describes the current manuscript and is revised
with it. It lives at ``runs/<id>/numbers.json`` -- beside ``spec.json`` and
``declarations.json``, NOT inside the regenerated ``paper/`` directory, so ``render`` never
clobbers it. The helper ``sci-adk numbers draft`` writes its proposals to
``runs/<id>/numbers.draft.json`` and never touches this file.

Reference: design/declared-numbers.md, src/sci_adk/core/declarations.py (the sibling side
file), src/sci_adk/render/number_checks.py (the checks).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, Field, ValidationError, model_validator

# The manuscripts a number can be declared in -- the two documents verify tokenizes.
DEFAULT_DOCUMENT = "draft.tex"
NUMBERS_FILE = "numbers.json"
NUMBERS_DRAFT_FILE = "numbers.draft.json"

# The Evidence ``Result`` scalar fields a source may name (``ci`` is addressed by bound).
RESULT_SCALAR_FIELDS: tuple[str, ...] = (
    "point", "effect_size", "p_value", "posterior", "residual", "predictive_error",
)
CI_FIELDS: tuple[str, ...] = ("ci[0]", "ci[1]")
FINDING_PREFIX = "finding."

Role = Literal["recorded", "derived", "citation", "identifier"]
Document = Literal["draft.tex", "si.tex"]

# One JSON-path segment: a key (anything but '.', '[', ']') then zero or more [index].
_SEGMENT_RE = re.compile(r"([^.\[\]]+)((?:\[\d+\])*)")
_INDEX_RE = re.compile(r"\[(\d+)\]")


# -- JSON paths ---------------------------------------------------------------

def parse_json_path(path: str) -> List[Union[str, int]]:
    """Split ``hypotheses[1].decision_rule.params.value`` into keys and list indexes.

    Raises:
        ValueError: the path is empty or not of the form ``key[i].key...``.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("a JSON path cannot be empty")
    parts: List[Union[str, int]] = []
    for segment in path.split("."):
        m = _SEGMENT_RE.fullmatch(segment)
        if m is None:
            raise ValueError(
                f"malformed JSON path {path!r}: write keys joined by '.', with [N] for a "
                f"list index (e.g. hypotheses[0].decision_rule.params.value)"
            )
        parts.append(m.group(1))
        parts.extend(int(i) for i in _INDEX_RE.findall(m.group(2)))
    return parts


def walk_json(data: Any, path: str) -> Any:
    """The value at ``path`` in ``data``.

    Raises:
        ValueError: the path is malformed.
        KeyError: the path does not exist in ``data`` (the message names the first
            missing step).
    """
    node = data
    walked = ""
    for part in parse_json_path(path):
        if isinstance(part, int):
            if not isinstance(node, list) or part >= len(node):
                raise KeyError(f"{walked or '(root)'} has no item [{part}]")
            node = node[part]
            walked += f"[{part}]"
        else:
            if not isinstance(node, dict) or part not in node:
                raise KeyError(f"{walked or '(root)'} has no key {part!r}")
            node = node[part]
            walked = f"{walked}.{part}" if walked else part
    return node


# -- the formula of a derived entry ---------------------------------------------

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


def _formula_tree(formula: str) -> ast.expr:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"formula {formula!r} does not parse: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, *_ALLOWED_BINOPS, ast.USub)):
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
            continue
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            continue
        if isinstance(node, ast.Name):
            continue
        if (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool)):
            continue
        raise ValueError(
            f"formula {formula!r} may use only + - * /, unary -, parentheses, numbers "
            f"and operand names (found {type(node).__name__})"
        )
    return tree.body


def formula_names(formula: str) -> set[str]:
    """The operand names a formula uses (validating that it is plain arithmetic)."""
    return {n.id for n in ast.walk(_formula_tree(formula)) if isinstance(n, ast.Name)}


def evaluate_formula(formula: str, values: Mapping[str, float]) -> float:
    """Evaluate a derived entry's formula over its resolved operands.

    A SAFE evaluator: it walks the parsed tree itself and allows only the four
    arithmetic operators, unary minus, numeric constants and operand names -- no calls,
    no attributes, no ``eval``.

    Raises:
        ValueError: the formula is not plain arithmetic, names an unknown operand, or
            divides by zero.
    """

    def _eval(node: ast.expr) -> float:
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ValueError(f"formula names {node.id!r}, which is not an operand")
            return float(values[node.id])
        if isinstance(node, ast.UnaryOp):
            return -_eval(node.operand)
        assert isinstance(node, ast.BinOp)
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ValueError(f"formula {formula!r} divides by zero")
        return left / right

    return _eval(_formula_tree(formula))


# -- the schema ---------------------------------------------------------------

def _valid_evidence_field(field: str) -> bool:
    if field in RESULT_SCALAR_FIELDS or field in CI_FIELDS:
        return True
    if field.startswith(FINDING_PREFIX):
        try:
            parse_json_path(field[len(FINDING_PREFIX):])
        except ValueError:
            return False
        return True
    return False


class NumberSource(BaseModel):
    """Where a declared number comes from. Exactly ONE of the four kinds:

    - ``{"evidence": <id>, "field": <f>}`` -- an Evidence ``Result`` field: ``point``,
      ``effect_size``, ``p_value``, ``posterior``, ``residual``, ``predictive_error``,
      ``ci[0]``, ``ci[1]``, or ``finding.<key>`` for a key of a JSON finding;
    - ``{"spec": <path>}`` -- a numeric field of the frozen ``spec.json``;
    - ``{"spec_text": <path>}`` -- a TEXT field of ``spec.json`` in which the literal is
      written as a standalone number (that field, not anywhere in the Spec);
    - ``{"bib": <key>, "field": "year"}`` -- a reference's year in ``references.bib``.
    """

    model_config = {"extra": "forbid"}

    evidence: Optional[str] = Field(default=None, min_length=1)
    field: Optional[str] = Field(default=None, min_length=1)
    spec: Optional[str] = Field(default=None, min_length=1)
    spec_text: Optional[str] = Field(default=None, min_length=1)
    bib: Optional[str] = Field(default=None, min_length=1)

    @property
    def kind(self) -> str:
        """``evidence`` | ``spec`` | ``spec_text`` | ``bib``."""
        for name in ("evidence", "spec", "spec_text", "bib"):
            if getattr(self, name) is not None:
                return name
        raise AssertionError("unreachable: validated to name exactly one kind")

    @model_validator(mode="after")
    def _one_kind(self) -> "NumberSource":
        kinds = [k for k in ("evidence", "spec", "spec_text", "bib")
                 if getattr(self, k) is not None]
        if len(kinds) != 1:
            raise ValueError(
                "a source names exactly one of evidence / spec / spec_text / bib "
                f"(got {', '.join(kinds) or 'none'})"
            )
        kind = kinds[0]
        if kind == "evidence":
            if self.field is None:
                raise ValueError(
                    "an evidence source needs a field (point, effect_size, ci[0], "
                    "finding.<key>, ...)"
                )
            if not _valid_evidence_field(self.field):
                raise ValueError(
                    f"unknown evidence field {self.field!r}: use one of "
                    f"{', '.join(RESULT_SCALAR_FIELDS + CI_FIELDS)} or finding.<key>"
                )
        elif kind == "bib":
            if self.field is None:
                self.field = "year"
            elif self.field != "year":
                raise ValueError(
                    f"a bib source reads the year only (got field {self.field!r})"
                )
        else:
            if self.field is not None:
                raise ValueError(f"a {kind} source takes no field; the path says it all")
            parse_json_path(self.spec if kind == "spec" else self.spec_text)
        return self


class NumberEntry(BaseModel):
    """One number literal the paper states, and why it may state it.

    Attributes:
        text: the literal as the tokenizer reads it in the rendered document: an optional
            minus, digits, decimal point, thousands commas, an exponent, or hyphen-joined
            digit groups (``17109-49-8``) -- never a unit or ``%`` (``95%`` is ``95``).
        document: ``draft.tex`` (default) or ``si.tex``.
        role: ``recorded`` | ``derived`` | ``citation`` | ``identifier``. When omitted it
            follows from what the entry carries: a bib source -> citation, any other
            source -> recorded, a formula -> derived.
        source: where a recorded / citation value comes from.
        formula, operands: a derived value, e.g. ``"100 * a"`` with ``{"a": <source>}``.
            Only ``+ - * /``, unary minus, parentheses, numbers and operand names.
        context: a fragment quoted from the document. Needed only when the same text has
            two roles in one document: the entry then covers just the occurrences inside
            a match of this fragment (whitespace-insensitive, as declaration quotes are).
    """

    model_config = {"extra": "forbid"}

    text: str = Field(min_length=1, description="the literal as written")
    document: Document = Field(default=DEFAULT_DOCUMENT, description="manuscript file")
    role: Optional[Role] = Field(default=None, description="what kind of number it is")
    source: Optional[NumberSource] = Field(default=None, description="where it comes from")
    formula: Optional[str] = Field(default=None, min_length=1, description="derived value")
    operands: Optional[Dict[str, NumberSource]] = Field(default=None,
                                                       description="formula operands")
    context: Optional[str] = Field(default=None, min_length=1,
                                   description="fragment locating the covered occurrences")

    @model_validator(mode="after")
    def _role_consistent(self) -> "NumberEntry":
        role = self.role
        if role is None:
            if self.source is not None:
                role = "citation" if self.source.kind == "bib" else "recorded"
            elif self.formula is not None or self.operands is not None:
                role = "derived"
            else:
                raise ValueError(
                    "an entry needs a source, a formula with operands, or role "
                    "'identifier' (a number that is not a quantity)"
                )
        if role in ("recorded", "citation"):
            if self.source is None:
                raise ValueError(f"a {role} entry needs a source")
            if self.formula is not None or self.operands is not None:
                raise ValueError(f"a {role} entry takes no formula or operands")
            if role == "recorded" and self.source.kind == "bib":
                raise ValueError("a bib source makes a citation entry, not a recorded one")
            if role == "citation" and self.source.kind != "bib":
                raise ValueError("a citation entry takes a bib source")
        elif role == "derived":
            if self.source is not None:
                raise ValueError("a derived entry takes operands, not a source")
            if self.formula is None or not self.operands:
                raise ValueError("a derived entry needs a formula and its operands")
            names = formula_names(self.formula)
            unknown = sorted(names - set(self.operands))
            if unknown:
                raise ValueError(f"the formula uses {', '.join(unknown)}, which are not "
                                 f"operands")
            unused = sorted(set(self.operands) - names)
            if unused:
                raise ValueError(f"operand(s) {', '.join(unused)} are not used in the "
                                 f"formula")
            for name, operand in self.operands.items():
                if operand.kind not in ("evidence", "spec"):
                    raise ValueError(
                        f"operand {name!r} must be an evidence or spec value (a "
                        f"{operand.kind} source has no single numeric value)"
                    )
        else:  # identifier
            if (self.source is not None or self.formula is not None
                    or self.operands is not None):
                raise ValueError("an identifier entry carries no source, formula or "
                                 "operands -- it is listed, not checked")
        self.role = role
        return self


class NumberList(BaseModel):
    """The per-run number list (``runs/<id>/numbers.json``).

    Attributes:
        spec_id: the run's Spec id (ties the list to the run, like ``Declarations``).
        numbers: one entry per distinct literal (and per role, with ``context``).
    """

    model_config = {"extra": "forbid"}

    spec_id: str = Field(description="the run's Spec id")
    numbers: List[NumberEntry] = Field(default_factory=list)


def _readable_errors(exc: ValidationError, raw: Any) -> str:
    """One line per validation error, naming the entry index (and its text) it is in."""
    lines: List[str] = []
    entries = raw.get("numbers") if isinstance(raw, dict) else None
    for err in exc.errors():
        loc = list(err.get("loc", ()))
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        if err.get("type") == "extra_forbidden" and loc:
            msg = f"unknown key {loc[-1]!r}"
            loc = loc[:-1]
        where = "numbers.json"
        if len(loc) >= 2 and loc[0] == "numbers" and isinstance(loc[1], int):
            index = loc[1]
            where = f"numbers[{index}]"
            if isinstance(entries, list) and index < len(entries):
                text = entries[index].get("text") if isinstance(entries[index], dict) else None
                if text is not None:
                    where += f" (text {text!r})"
            loc = loc[2:]
        elif loc:
            where = ".".join(str(p) for p in loc)
            loc = []
        rest = ".".join(str(p) for p in loc)
        lines.append(f"{where}{': ' + rest if rest else ''}: {msg}")
    return "\n  ".join(lines)


def load_numbers(run_dir: Path) -> Optional[NumberList]:
    """Read ``runs/<id>/numbers.json``, or ``None`` when the run has not adopted the list.

    PURE-ish (one read, no writes). An ABSENT file keeps the run on the pattern-based
    number audit (design/declared-numbers.md §5: opt-in per run), so no existing run is
    retro-broken.

    Raises:
        ValueError: the file exists but is not valid JSON or does not validate. Like a
            malformed declaration list this is a loud failure, never a silent skip: a run
            that HAS the file has adopted the mechanism. The message names every bad entry
            by index (``numbers[3] (text '341'): source: ...``).
    """
    path = Path(run_dir) / NUMBERS_FILE
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} exists but is not readable JSON: {exc}") from exc
    try:
        return NumberList.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(
            f"{path} is not a valid number list:\n  {_readable_errors(exc, raw)}"
        ) from exc


__all__ = [
    "CI_FIELDS",
    "DEFAULT_DOCUMENT",
    "FINDING_PREFIX",
    "NUMBERS_DRAFT_FILE",
    "NUMBERS_FILE",
    "NumberEntry",
    "NumberList",
    "NumberSource",
    "RESULT_SCALAR_FIELDS",
    "evaluate_formula",
    "formula_names",
    "load_numbers",
    "parse_json_path",
    "walk_json",
]
