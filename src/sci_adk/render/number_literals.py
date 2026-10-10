"""
Find the number literals in a rendered manuscript (design/declared-numbers.md §4.2).

The tokenizer of the declared-number checks. It FINDS literals and never judges them:
whether "47" is a page, a prime or a count is declared in ``runs/<id>/numbers.json``
(:mod:`sci_adk.core.numbers`), not guessed here. So, unlike the pattern audit it replaces
(:mod:`sci_adk.render.number_audit`, kept unchanged for runs without a list), it has NO
year, page, date or version rule, and it does not strip math.

What it keeps out are only the spans LaTeX itself defines as non-prose:
  - comments;
  - the arguments of ``\\ref``-like, ``\\cite``-like, ``\\label``, ``\\input``,
    ``\\include``, ``\\includegraphics``, ``\\bibliography(style)``, ``\\usepackage``,
    ``\\documentclass`` and ``\\pgfplotsset`` (with up to two ``[...]`` options);
  - the verbatim spans ``\\path``, ``\\url``, ``\\nolinkurl``, ``\\verb`` and the URL
    argument of ``\\href`` (its text argument is prose). ``\\texttt`` is NOT one of them: it
    is a font, its argument is prose (it needs ``\\_`` like any prose), so a seed or a
    sample size written as code (``default\\_rng(20261008)``, ``size=50``) is a literal;
  - macro definition heads and ``#N`` argument references;
  - the two identifier arguments of ``\\novelty{kind}{hyp}{text}`` (the text is prose);
  - the ``coordinates {...}`` of a pgfplots ``\\addplot`` (figure data drawn from the record
    by Evidence id, not a number the prose states);
  - superscripts and subscripts: ``^``/``_`` targets inside math, ``\\textsuperscript``,
    ``\\textsubscript`` (``R$^2$``, ``H$_2$O`` -- the renderer's form of ``R²``, ``H₂O``).
Section titles, captions and every other number inside math ARE literals.

And these lexical rules, none of which depends on the field:
  - digits joined by single hyphens with no spaces are ONE literal (``17109-49-8``,
    ``2026-10-08``); it is not one number, so it has no value;
  - digit groups joined by two or more dots are one literal too (``2025.09.4``);
  - an en dash, ``--`` or ``---`` between two numbers separates a range;
  - a minus (``-``, U+2212, or a ``$-$`` before the digits) negates only when it is
    unary: not after a digit, a letter, an underscore or a closing bracket. So
    ``n - 2`` and ``criterion-5`` hold the literals 2 and 5;
  - a digit run that continues a word is part of that word (``log10``, ``CO2``, ``s3``),
    as in the pattern audit; a number glued to letters only by a hyphen is a literal. So
    a version written after a letter (``v2.9.5``) holds no literal at all -- consistently
    in the checks, the draft helper and the pattern audit -- while a bare ``2.9.5`` is one
    dotted literal;
  - an ISO-8601 date-time -- a date, ``T``, ``hh:mm[:ss[.fff]]``, then optionally ``Z`` or
    ``+hh[:mm]`` / ``-hh[:mm]`` (``2026-10-08T10:03:39Z``) -- is ONE literal with no value,
    which the checks accept only as an identifier; split at ``:`` its pieces read as
    numbers that a recorded count could match by coincidence. A bare date stays
    hyphen-joined digit groups (above);
  - a digest is a word, not a number: a maximal alphanumeric run of seven or more hex
    characters, all letters in one case, holding a digit and a letter, and not itself
    digits-e-digits (``12345e6`` is an exponent). The SHA-256
    ``1081e637f6bd...`` holds no literal (it used to read as ``1081e637``, 10^640). A run
    that belongs to a number in scientific notation is not a digest: the digit-led tail
    of a decimal (``2345678e`` in ``1.2345678e-3``) or a digits-then-``e`` run followed by
    a signed exponent (``2345678e-3``). Pieces joined by ``\\allowbreak`` --
    ``\\texttt{1081e637f6bd39f9}\\allowbreak\\texttt{ba86...}`` -- are judged as one run when
    each is at least four characters long (a split digest's typewriter-width pieces), and
    a shorter LAST piece joins too when the piece before it is at least eight characters
    long (``\\texttt{4fa76e47b3048258}\\allowbreak\\texttt{7}``); any other shorter piece,
    or a space between two runs, separates them, so ``\\texttt{abc}`` before ``1234567``
    leaves the number a number. Digests and date-times are
    overwritten with letters, not blanks, so a neighbour reads as it did beside the word;
  - ``95\\%`` is the literal 95; a comma followed by exactly three digits after one to
    three digits is a thousands separator (``6,973`` is one literal, value 6973);
  - a leading-dot decimal (``.76``) and an exponent (``1.2e-3``) are part of the number.

Each literal carries its text, numeric value (``None`` for a joined literal, a date-time,
and a literal beyond a float such as ``1081e637`` -- declared, if it ever occurs, as an
identifier), printed decimals, document, offsets into the document, and a snippet of the
surrounding text. Masked spans are replaced by blanks of the same length, so every offset is
an offset into the original document -- which is what lets an entry's ``context`` locate
occurrences.

The patterns mirror those of the pattern audit but are deliberately copied, not imported:
that module must stay byte-for-byte for runs without a list, and it is retired once the
list is required, while this one has to keep working.

PURE (text in, literals out), deterministic, no LLM. Imports nothing from sci_adk.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

# -- the literal ----------------------------------------------------------------


@dataclass(frozen=True)
class NumberLiteral:
    """One number literal found in a document.

    Attributes:
        text: the literal as the tokenizer reads it -- an optional ``-`` (any minus
            form normalized to ASCII), then the number as written (thousands commas,
            decimal point, exponent, or hyphen/dot-joined digit groups) -- or an ISO-8601
            date-time as written (``2026-10-08T10:03:39Z``).
        value: its numeric value; ``None`` when it is not one number (``17109-49-8``, a
            date-time) or not a finite one (``1081e637`` overflows a float).
        decimals: the printed precision in absolute decimal places (``0.769`` -> 3,
            ``341`` -> 0, ``1.2e-3`` -> 4); ``None`` when ``value`` is ``None``.
        document: the document it was found in (``draft.tex`` / ``si.tex``).
        start, end: offsets of the literal (its minus sign included) in the document.
        snippet: the surrounding text, whitespace collapsed, for messages.
    """

    text: str
    value: Optional[float]
    decimals: Optional[int]
    document: str
    start: int
    end: int
    snippet: str


# -- masking -------------------------------------------------------------------

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")

# Commands whose ONE braced argument (after optional [..] options) is a name, key, file or
# package -- never prose. The whole command is masked.
_ARG_COMMANDS = frozenset({
    "ref", "eqref", "autoref", "cref", "Cref", "pageref", "nocite", "label", "input",
    "include", "includegraphics", "bibliographystyle", "bibliography", "usepackage",
    "documentclass", "pgfplotsset", "path", "url", "nolinkurl",
    "textsuperscript", "textsubscript",
})
# NOT here: \texttt. It is a font, not verbatim (its argument needs \_ like any prose), and
# masking it let a seed or a sample size written as code escape the list unseen; a digest
# written in it is removed by the digest rule instead.
# \href{url}{text}: only the URL argument is masked; the text argument is prose.
_HREF = "href"
# Macro definitions are markup mechanics, not data (mirrors number_audit's pattern).
_MACRO_DEF_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|def|newenvironment)"
    r"\*?(?:\{\\?[A-Za-z@]+\}|\\[A-Za-z@]+)(?:\[\d*\])*(?:\[[^\]]*\])?"
)
# An escaped ``\#`` is a literal hash in prose ("sample \#3"), not an argument reference.
_MACRO_ARG_RE = re.compile(r"(?<!\\)#\d+")
# \novelty{kind}{hyp}{text}: the first two arguments are identifiers (mirrors number_audit).
_NOVELTY_IDS_RE = re.compile(r"\\novelty\s*\{[^{}]*\}\s*\{[^{}]*\}\s*(?=\{)")
_VERB_RE = re.compile(r"\\verb\*?([^\sA-Za-z*])(.*?)\1", re.DOTALL)
_COORDINATES_RE = re.compile(r"\bcoordinates\s*(?=\{)")
_BEGIN_MATH_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|math|displaymath)(\*?)\}"
)


def _is_cite(name: str) -> bool:
    return name.startswith("cite") or name.startswith("Cite")


def _group_end(text: str, open_idx: int, limit: Optional[int] = None) -> int:
    """Index just past the ``}`` closing the ``{`` at ``open_idx`` (escapes honoured).

    An unbalanced group runs to ``limit`` (or the end of the text) rather than raising:
    the tokenizer is total.
    """
    limit = len(text) if limit is None else limit
    depth = 0
    i = open_idx
    while i < limit:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return limit


def _skip_options(text: str, i: int, max_options: int = 2) -> int:
    """Skip whitespace, an optional ``*`` and up to ``max_options`` ``[...]`` groups."""
    n = len(text)
    if i < n and text[i] == "*":
        i += 1
    for _ in range(max_options):
        j = i
        while j < n and text[j] in " \t\n":
            j += 1
        if j < n and text[j] == "[":
            close = text.find("]", j + 1)
            if close < 0:
                return n
            i = close + 1
        else:
            break
    while i < n and text[i] in " \t\n":
        i += 1
    return i


def _blank(chars: List[str], start: int, end: int) -> None:
    for k in range(start, min(end, len(chars))):
        if chars[k] != "\n":
            chars[k] = " "


def _mask_command_arguments(text: str, chars: List[str]) -> None:
    for m in _COMMAND_RE.finditer(text):
        if m.start() > 0 and text[m.start() - 1] == "\\":
            continue  # "\\name" is a line break followed by text, not a command
        name = m.group(1)
        if name in _ARG_COMMANDS or _is_cite(name):
            i = _skip_options(text, m.end())
            if i < len(text) and text[i] == "{":
                _blank(chars, m.start(), _group_end(text, i))
        elif name == _HREF:
            i = _skip_options(text, m.end(), max_options=0)
            if i < len(text) and text[i] == "{":
                _blank(chars, m.start(), _group_end(text, i))


def _math_spans(text: str) -> List[Tuple[int, int]]:
    """``(start, end)`` of the CONTENT of every math region: ``$..$``, ``$$..$$``,
    ``\\(..\\)``, ``\\[..\\]`` and the display-math environments. An escaped ``\\$`` is a
    literal dollar, not a delimiter."""
    spans: List[Tuple[int, int]] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\\":
            if text.startswith("\\(", i) or text.startswith("\\[", i):
                closer = "\\)" if text[i + 1] == "(" else "\\]"
                j = text.find(closer, i + 2)
                end = n if j < 0 else j
                spans.append((i + 2, end))
                i = n if j < 0 else j + 2
                continue
            m = _BEGIN_MATH_RE.match(text, i)
            if m:
                closer = f"\\end{{{m.group(1)}{m.group(2)}}}"
                j = text.find(closer, m.end())
                end = n if j < 0 else j
                spans.append((m.end(), end))
                i = n if j < 0 else j + len(closer)
                continue
            i += 2
            continue
        if ch == "$":
            if text.startswith("$$", i):
                j = text.find("$$", i + 2)
                end = n if j < 0 else j
                spans.append((i + 2, end))
                i = n if j < 0 else j + 2
                continue
            j = i + 1
            while j < n and text[j] != "$":
                j += 2 if text[j] == "\\" else 1
            end = min(j, n)
            spans.append((i + 1, end))
            i = end + 1
            continue
        i += 1
    return spans


def _mask_scripts(text: str, chars: List[str], start: int, end: int) -> None:
    """Blank every superscript / subscript (the ``^``/``_`` and its target) in a math span.

    TeX semantics: the target is a braced group, a control sequence, or ONE character.
    """
    i = start
    while i < end:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch in "^_":
            j = i + 1
            while j < end and text[j] in " \t\n":
                j += 1
            if j < end and text[j] == "{":
                stop = _group_end(text, j, end)
            elif j < end and text[j] == "\\":
                cm = re.match(r"\\(?:[A-Za-z]+|.)", text[j:end])
                stop = j + (len(cm.group(0)) if cm else 1)
            else:
                stop = min(j + 1, end)
            _blank(chars, i, stop)
            i = stop
            continue
        i += 1


def _mask_latex(tex: str) -> str:
    """``tex`` with every non-prose span blanked (same length, newlines kept)."""
    chars = list(tex)
    for m in _COMMENT_RE.finditer(tex):
        _blank(chars, m.start(), m.end())
    masked = "".join(chars)
    for m in _VERB_RE.finditer(masked):
        _blank(chars, m.start(), m.end())
    masked = "".join(chars)
    _mask_command_arguments(masked, chars)
    masked = "".join(chars)
    for pattern in (_MACRO_DEF_RE, _MACRO_ARG_RE, _NOVELTY_IDS_RE):
        for m in pattern.finditer(masked):
            _blank(chars, m.start(), m.end())
    masked = "".join(chars)
    for m in _COORDINATES_RE.finditer(masked):
        _blank(chars, m.start(), _group_end(masked, m.end()))
    masked = "".join(chars)
    for start, end in _math_spans(masked):
        _mask_scripts(masked, chars, start, end)
    return "".join(chars)


# -- scanning --------------------------------------------------------------------

# A number: thousands-grouped or plain integer part, optional dotted groups, or a
# leading-dot decimal; then an optional exponent. The left guard keeps a digit run that
# continues a word or a decimal out (log10, CO2, the 5 of 1.5).
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"(?:(?P<int>[0-9]{1,3}(?:,[0-9]{3})+(?![0-9])|[0-9]+)(?P<frac>(?:\.[0-9]+)*)"
    r"|(?P<lead>\.[0-9]+))"
    r"(?P<exp>[eE][+-]?[0-9]+)?"
)
_MINUS = ("-", "\u2212")
_OPERAND_END = re.compile(r"[A-Za-z0-9_)\]}]")

# A digest (a checksum, a commit, any hex-encoded code) is a word, not a number: a maximal
# alphanumeric run of >= 7 hex characters, one letter case, with a digit and a letter, that
# is not itself digits-e-digits (an exponent). Pieces joined by ``\allowbreak`` (inside or
# between ``\texttt`` groups) are one run. Read as numbers, its fragments were "1081e637"
# (10^640, beyond a float) and the "9" of "9dc5...".
_ALNUM_RUN_RE = re.compile(r"[A-Za-z0-9]+")
_HEX_RUN_RE = re.compile(r"[0-9A-Fa-f]+")
_ONE_CASE_HEX_RE = re.compile(r"[0-9a-f]+|[0-9A-F]+")
_NUMBER_FORM_RE = re.compile(r"[0-9]+(?:[eE][+-]?[0-9]+)?")
_DIGEST_MIN_LENGTH = 7
_GLUE_RE = re.compile(r"\\allowbreak(?![A-Za-z])|\\texttt(?![A-Za-z])|[{}\s]")
# A piece shorter than this never joins an \allowbreak chain: a split digest is broken into
# typewriter-width pieces, and a short hex WORD ("abc") beside a number ("1234567") would
# otherwise read as one ten-character digest and hide the number.
_CHAIN_MIN_PIECE = 4
# ...except the LAST piece of a chain, which may be shorter (a 17-character code split
# 16 + 1) when the piece before it is at least this long: a long hex piece then a short
# one is the tail of a split digest, never a word beside a number.
_SHORT_TAIL_AFTER = 8
# A run of digits then an exponent marker ("2345678e") followed by a signed exponent is the
# mantissa of a number in scientific notation ("2345678e-3"), not a digest.
_MANTISSA_RE = re.compile(r"[0-9]+[eE]")
_SIGNED_EXPONENT_RE = re.compile(r"[+-][0-9]")
# What a digest (or a date-time, below) is overwritten with before numbers are scanned. A
# letter, not a blank: a neighbour reads exactly as it did beside the word (``<digest>-5``
# stays the hyphen-glued 5, not -5).
_WORD_MASK = "x"


def _is_digest(run: str) -> bool:
    return (len(run) >= _DIGEST_MIN_LENGTH
            and _ONE_CASE_HEX_RE.fullmatch(run) is not None
            and any(c.isdigit() for c in run)
            and any(c.isalpha() for c in run)
            and _NUMBER_FORM_RE.fullmatch(run) is None)


def _part_of_a_number(text: str, piece: re.Match) -> bool:
    """True iff the run belongs to a number in scientific notation: it is the tail of a
    decimal (a digit-led run right after ``.``: the ``2345678e`` of ``1.2345678e-3``), or
    a mantissa whose signed exponent follows it (``2345678e`` before ``-3``). A maximal run
    is never preceded by a digit, so the ``.`` is the only way in."""
    run = piece.group()
    if piece.start() > 0 and text[piece.start() - 1] == "." and run[0].isdigit():
        return True
    return (_MANTISSA_RE.fullmatch(run) is not None
            and _SIGNED_EXPONENT_RE.match(text, piece.end()) is not None)


def _glues(gap: str) -> bool:
    """True iff ``gap`` only joins two pieces: ``\\allowbreak``, ``\\texttt``, braces and
    whitespace, with at least one ``\\allowbreak`` (a bare space separates two words)."""
    return "\\allowbreak" in gap and not _GLUE_RE.sub("", gap)


def _mask_digests(text: str) -> str:
    """``text`` with every digest (see ``_is_digest``) overwritten by ``_WORD_MASK``.

    A chain of ``\\allowbreak``-joined pieces, each at least ``_CHAIN_MIN_PIECE`` long --
    the last may be shorter after a piece of at least ``_SHORT_TAIL_AFTER`` -- is judged as
    one run; any other piece is judged on its own.
    """
    pieces = [m for m in _ALNUM_RUN_RE.finditer(text)
              if _HEX_RUN_RE.fullmatch(m.group()) and not _part_of_a_number(text, m)]
    chains: List[List[re.Match]] = []
    for piece in pieces:
        prev = chains[-1][-1] if chains else None
        joins = prev is not None and len(prev.group()) >= _CHAIN_MIN_PIECE and (
            len(piece.group()) >= _CHAIN_MIN_PIECE
            or len(prev.group()) >= _SHORT_TAIL_AFTER  # a short last piece
        )
        if joins and _glues(text[prev.end():piece.start()]):
            chains[-1].append(piece)
        else:
            chains.append([piece])
    chars: Optional[List[str]] = None
    for chain in chains:
        if len(chain) > 1 and _is_digest("".join(p.group() for p in chain)):
            digests = chain
        else:
            digests = [p for p in chain if _is_digest(p.group())]
        for piece in digests:
            if chars is None:
                chars = list(text)
            chars[piece.start():piece.end()] = _WORD_MASK * (piece.end() - piece.start())
    return text if chars is None else "".join(chars)


# An ISO-8601 date-time -- a date, ``T``, ``hh:mm[:ss[.fff]]``, then ``Z`` or ``+hh[:mm]`` /
# ``-hh[:mm]`` -- is ONE literal (split at ':' its pieces read as numbers, and a recorded
# count could match one by coincidence). It must not continue a word or a number on either
# side; a bare date is not one (it stays hyphen-joined digit groups).
_DATE_TIME_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}(?::[0-9]{2})?)?"
)
_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9_]")


def _date_times(text: str) -> List[re.Match]:
    """Every date-time of ``text`` not glued to a following word character (one that is
    -- ``...39Zabc`` -- is no date-time and reads as it did before the rule)."""
    return [m for m in _DATE_TIME_RE.finditer(text)
            if not _WORD_CHAR_RE.match(text, m.end())]


def _unary_minus_at(text: str, start: int) -> Optional[int]:
    """The offset of a unary minus immediately before ``start``, or ``None``.

    Unary: the minus is not part of a dash run (``--``) and does not follow an operand (a
    digit, a letter, an underscore or a closing bracket) -- after an operand it is a
    hyphen, a join or a subtraction. ``$-$`` directly before the digits counts too.
    """
    if start >= 3 and text[start - 3:start] == "$-$":
        before = text[start - 4] if start >= 4 else ""
        return start - 3 if not (before and _OPERAND_END.match(before)) else None
    if start < 1 or text[start - 1] not in _MINUS:
        return None
    before = text[start - 2] if start >= 2 else ""
    if before in _MINUS or (before and _OPERAND_END.match(before)):
        return None
    return start - 1


def _shape(m: re.Match) -> Tuple[Optional[float], Optional[int]]:
    """``(value, decimals)`` of one scanned number (``(None, None)`` for dotted groups and
    for a value beyond a float, such as ``1081e637``)."""
    frac = m.group("frac") or ""
    if frac.count(".") >= 2:
        return None, None
    raw = m.group(0).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None, None
    if not math.isfinite(value):
        return None, None
    if m.group("lead"):
        decimals = len(m.group("lead")) - 1
    else:
        decimals = len(frac) - 1 if frac else 0
    exp = m.group("exp")
    if exp:
        decimals -= int(exp[1:])
    return value, decimals


def _snippet(text: str, start: int, end: int, width: int = 40) -> str:
    return " ".join(text[max(0, start - width):min(len(text), end + width)].split())


def _scan(original: str, masked: str, document: str) -> List[NumberLiteral]:
    # Date-times first: each becomes one literal, and its span is overwritten with a letter
    # (as a digest is) so that none of its digits is scanned again.
    stamps = [NumberLiteral(m.group(), None, None, document, m.start(), m.end(), "")
              for m in _date_times(masked)]
    if stamps:
        chars = list(masked)
        for lit in stamps:
            chars[lit.start:lit.end] = _WORD_MASK * (lit.end - lit.start)
        masked = "".join(chars)
    masked = _mask_digests(masked)
    raw: List[NumberLiteral] = []
    for m in _NUMBER_RE.finditer(masked):
        value, decimals = _shape(m)
        start = m.start()
        sign_at = _unary_minus_at(masked, start)
        text = m.group(0)
        if sign_at is not None:
            text = "-" + text
            value = -value if value is not None else None
            start = sign_at
        raw.append(NumberLiteral(text, value, decimals, document, start, m.end(), ""))

    # Join digit groups separated by ONE ascii hyphen and nothing else (17109-49-8).
    joined: List[NumberLiteral] = []
    for lit in raw:
        prev = joined[-1] if joined else None
        if (prev is not None and not lit.text.startswith("-") and lit.start == prev.end + 1
                and masked[prev.end] == "-"):
            joined[-1] = NumberLiteral(f"{prev.text}-{lit.text}", None, None, document,
                                       prev.start, lit.end, "")
            continue
        joined.append(lit)
    if stamps:
        joined = sorted(joined + stamps, key=lambda lit: lit.start)
    return [replace(lit, snippet=_snippet(original, lit.start, lit.end)) for lit in joined]


# @MX:ANCHOR: [AUTO] the one reading of "which number literals does this paper state".
# @MX:REASON: [AUTO] verify's coverage/stale checks, `numbers draft`, and its repeat hint all
#   call it and must see the SAME literals: a changed lexical rule changes what every
#   numbers.json has to declare, so it fails runs that were green (design/declared-numbers.md
#   §4.2 keeps it to LaTeX's own exemptions + field-independent rules for that reason).
def find_literals(tex: str, document: str = "draft.tex") -> List[NumberLiteral]:
    """Every number literal of a rendered LaTeX document, in source order.

    PURE + deterministic. Masks the spans LaTeX defines as non-prose (see the module
    docstring), then scans what is left. Offsets are into ``tex`` itself.
    """
    return _scan(tex, _mask_latex(tex), document)


def find_text_literals(text: str, document: str = "") -> List[NumberLiteral]:
    """Every number literal of PLAIN text (a Spec text field) -- no LaTeX masking."""
    return _scan(text, text, document)


def is_date_time(text: str) -> bool:
    """True iff ``text`` is one ISO-8601 date-time literal (``2026-10-08T10:03:39Z``).

    Such a literal can only be declared an identifier: no recorded field holds a time of
    day, so a value matching one of its pieces is a coincidence. A bare date
    (``2026-10-08``) is not a date-time; it is joined digit groups.
    """
    return _DATE_TIME_RE.fullmatch(canonical_text(text)) is not None


def canonical_text(text: str) -> str:
    """A literal's text with any minus form written as ASCII ``-`` (for comparisons)."""
    return text.strip().replace("\u2212", "-")


def parse_literal_text(text: str) -> Optional[NumberLiteral]:
    """The ONE literal ``text`` is, or ``None`` if it is not exactly one literal.

    ``"0.769"``, ``"-0.806"``, ``"6,973"`` and ``"17109-49-8"`` are literals; ``"95%"`` is
    not (its literal is ``95``), nor is ``"0.7 to 1.0"``.
    """
    stripped = canonical_text(text)
    literals = find_text_literals(stripped)
    if len(literals) != 1:
        return None
    lit = literals[0]
    if lit.start != 0 or lit.end != len(stripped):
        return None
    return lit


__all__ = [
    "NumberLiteral",
    "canonical_text",
    "find_literals",
    "find_text_literals",
    "is_date_time",
    "parse_literal_text",
]
