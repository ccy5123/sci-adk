"""
The LaTeX-safe copy of a run's bibliography, and which characters pdflatex can typeset.

Render copies the run's literature pool (``literature/references.bib``, as paperforge or a manual
ingest wrote it) into ``paper/references.bib`` and the cited-only ``paper/references_SI.bib``.
Registrar BibTeX (Crossref's metadata is XML-rooted) can carry HTML entities (``&amp;``), HTML
markup (``<i>K</i>``) and characters pdflatex cannot typeset (U+2212 MINUS SIGN).
:func:`latex_safe_bib` writes that copy in LaTeX. The pool itself is never rewritten here: its
keys never change and the merge keeps old entries verbatim (``search/literature_merge.py``).

Only field values change; entry headers (keys), field names and the text between entries are
copied as they are, except that a bare month name BibTeX does not define (``month = June``,
``month = sept``: BibTeX warns and leaves the month out of the reference list) becomes its
three-letter macro (``jun``, ``sep``).

Three kinds of field are left alone or nearly so:

- ``url`` and ``doi`` values are never escaped: plainnat prints them through ``\\url`` /
  ``\\Url``, which typeset their argument verbatim, so an escape there prints its backslash
  (measured: ``AID\\_JBM1`` for ``\\_`` in a doi). XML's own escapes in them (``&amp;``,
  ``&lt;``, ``&gt;``, ``&quot;``, ``&apos;``, numeric) are decoded; any other entity-shaped text
  (``?a&copy;b``) is part of the URL.
- fields no BibTeX style prints (:data:`UNPRINTED_FIELDS`: ``abstract``, ``keywords``, ``file``,
  ``annote``, ``timestamp`` ... -- what Zotero, JabRef, Mendeley and BibDesk write) are copied as
  acquired. Their text never reaches the ``.bbl``, so it cannot stop pdflatex, and verify does
  not check them either.

Inside a printed value the copy distinguishes running text, math (``$...$``, ``$$...$$``,
``\\(...\\)``) and verbatim arguments (``\\url{...}``, left alone). Markup is read only in text:
known HTML/XML tags (:data:`HTML_TAG_RE`) become LaTeX or are stripped, and any other ``<`` or
``>`` is text (``\\textless{}`` / ``\\textgreater{}``; in math they stay comparisons).

Character policy, shared with the verify-side check (``pkgreqs_checks.bib_latex_safety_problems``
via :func:`typesettable`). It assumes the preamble every sci-adk render emits: ``utf8`` inputenc,
``T1`` fontenc and Latin Modern (``paper.T1_FONT_LINES``):

- printable ASCII, Latin-1 (U+00A0..U+00FF), Latin Extended-A up to ``paper._ACCENT_HI``
  (U+017E) except the few letters LaTeX defines no glyph for, and a short list of typographic
  punctuation are typeset by pdflatex, and are left as they are in text; :data:`T1_ONLY_CHARS`
  are the ones among them that need T1 (OT1 stops on them);
- a non-ASCII space becomes an ASCII space; an invisible format character is dropped;
- any other character goes through render's curated prose map (``paper._UNICODE_MAP``), inside
  a brace group when the replacement is a command or math, so BibTeX's title case change cannot
  turn ``$\\Delta$`` into ``$\\delta$``; inside math the map's math form is written without its
  ``$`` (``$x ≥ 3$`` -> ``$x \\geq 3$``), braced only when the command has a capital letter;
- a letter with combining marks (precomposed, or followed by marks that compose with nothing)
  is decomposed fully and becomes LaTeX accent commands, nested innermost-first in a brace group
  BibTeX reads as one letter (``ǚ`` -> ``{\\v{\\"{u}}}``, ``ȩ́`` -> ``{\\'{\\c{e}}}``, ``Ș`` ->
  ``{\\textcommabelow{S}}``); inside math the group goes in an ``\\mbox`` (an accent command in
  math mode stops pdflatex);
- a compatibility character (a ligature, a width variant) is folded when the fold typesets;
- a character with no LaTeX form -- a letter carrying a mark LaTeX has no standard command for
  (hook above, horn), an accent on a non-Latin letter, CJK -- is KEPT, never replaced by a
  placeholder or stripped of a mark: a reference must not silently lose a letter or an accent,
  so verify names it instead.

PURE (string in, string out): stdlib plus sibling render helpers, no I/O.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterator

from sci_adk.render.paper import _ACCENT_HI, _UNICODE_MAP, _latex_escape

# An entry header ``@type{KEY,``. A value never runs past one unless its braces say so.
_HEADER_RE = re.compile(r"@\w+\s*\{\s*[^,\s}]+\s*,")

# A well-formed HTML entity (named, decimal or hex, ending in ';') not preceded by a backslash:
# ``\&amp;`` is LaTeX already -- an escaped ampersand followed by the letters "amp;".
HTML_ENTITY_RE = re.compile(r"(?<!\\)&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")
# XML's predefined entities and numeric references: the only escapes XML-rooted metadata puts
# into a URL. Other entity-shaped text in a url or doi value is part of the URL.
_XML_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|#[0-9]+|#[xX][0-9A-Fa-f]+);")

# The markup read as a tag: HTML face markup, Crossref's face markup (scp, tt, ovl, font) and
# the namespaced MathML / JATS elements registrars deposit, with attributes written
# name="value". Anything else between < and > is text ("if n<k and m>j"), and a SICI DOI
# fragment such as ``<1175:BOPACB>`` is not a tag.
_TAG_NAMES = (
    "i", "b", "em", "strong", "sub", "sup", "span", "sc", "scp", "u", "br", "p", "div",
    "tt", "ovl", "font",
)
_TAG_NAME = (
    r"(?:(?:mml|jats):[A-Za-z][\w.-]*|"
    + "|".join(sorted(_TAG_NAMES, key=len, reverse=True))
    + r")(?![\w:.-])"
)
_TAG_ATTRS = r"""(?:\s+[A-Za-z_][\w:.-]*\s*=\s*(?:"[^"<>]*"|'[^'<>]*'))*"""
HTML_TAG_RE = re.compile(r"</?" + _TAG_NAME + _TAG_ATTRS + r"\s*/?>", re.IGNORECASE)

# Markup with a LaTeX equivalent; every other tag is stripped and its text kept.
_MARKUP_CMD = {
    "i": "textit",
    "em": "textit",
    "b": "textbf",
    "strong": "textbf",
    "sub": "textsubscript",
    "sup": "textsuperscript",
}
_MARKUP_PAIR_RE = re.compile(
    r"<(?P<tag>" + "|".join(sorted(_MARKUP_CMD, key=len, reverse=True)) + r")(?![\w:.-])"
    + _TAG_ATTRS + r"\s*>(?P<body>.*?)</(?P=tag)\s*>",
    re.DOTALL | re.IGNORECASE,
)

# A decoded entity's character in LaTeX: < and > as commands, so they never read as a tag (and
# print as themselves in any font encoding); braces as commands, so the field stays balanced;
# a double quote braced, so it cannot end a quote-delimited field.
_ENTITY_LATEX = {
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "{": r"\textbraceleft{}",
    "}": r"\textbraceright{}",
    '"': '{"}',
}

# Field values whose command typesets them verbatim (plainnat: \url{url}, \doi{doi} -> \Url).
VERBATIM_FIELDS = frozenset({"url", "doi"})

# @MX:NOTE: [AUTO] An exclusion list on purpose: a field not named here is assumed printed (a
# style may print note, language, urldate ...), so an unknown field is still copied and checked.
# Fields no BibTeX style prints: what reference managers write beside the reference (Zotero:
# abstract, keywords, file, annote; JabRef: owner, timestamp, groups, comment; Mendeley:
# mendeley-tags, mendeley-groups; BibDesk: date-added, date-modified, bdsk-*; biblatex's
# langid). The copy leaves their values as acquired and verify does not check them.
UNPRINTED_FIELDS = frozenset(
    {
        "abstract", "annotation", "annote", "comment", "copyright", "date-added",
        "date-modified", "file", "groups", "keywords", "langid", "language",
        "mendeley-groups", "mendeley-tags", "owner", "shorttitle", "timestamp", "urldate",
    }
)
_UNPRINTED_PREFIXES = ("bdsk-",)

_FIELD_NAME_RE = re.compile(r"([A-Za-z][\w:.+-]*)\s*=\s*")
_STRING_DEF_RE = re.compile(r"@string\s*[{(]\s*([A-Za-z][\w:.+-]*)\s*=", re.IGNORECASE)
_BARE_TOKEN_RE = re.compile(r"[^\s,#}]*")

# BibTeX predefines jan..dec (case-insensitive); a full month name or "sept" is an undefined
# macro, and the field is dropped. "may" is both, so it is never rewritten.
_MONTH_ABBR = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
)
_MONTH_MACRO = {
    name: abbr for name, abbr in zip(_MONTH_NAMES, _MONTH_ABBR) if name != abbr
} | {"sept": "sep"}

# Inside a field value: arguments typeset verbatim (left alone) and math.
_VERBATIM_ARG = r"\\(?:url|href|path|doi)\s*\{[^{}]*\}"
_VALUE_SEGMENT_RE = re.compile(
    r"(?P<verbatim>" + _VERBATIM_ARG + r")"
    r"|(?P<math>\$\$.*?\$\$|(?<!\\)\$(?:[^$\\]|\\.)*\$|\\\(.*?\\\))",
    re.DOTALL,
)
# What the copy escapes: in text a bare & % # _ ^ and every < >; in math a bare & % #.
_TEXT_ESCAPE_RE = re.compile(r"(?<!\\)[&%#_^]|[<>]")
_TEXT_ESCAPE = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "^": r"\textasciicircum{}",  # measured: prints U+005E; \^{} prints a raised accent
    "<": r"\textless{}",
    ">": r"\textgreater{}",
}
_MATH_ESCAPE_RE = re.compile(r"(?<!\\)[&%#]")
# What verify calls bare: the same, except a & that starts an entity (named by its own line).
_NOT_ENTITY = r"(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);)"
_BARE_IN_TEXT_RE = re.compile(r"(?<!\\)(?:[%#_^]|&" + _NOT_ENTITY + ")")
_BARE_IN_MATH_RE = re.compile(r"(?<!\\)(?:[%#]|&" + _NOT_ENTITY + ")")

# A control word at the end of the output so far: a letter after it would run into its name.
_CONTROL_WORD_END_RE = re.compile(r"\\[A-Za-z]+$")
_MATH_FORM_RE = re.compile(r"\$([^$]+)\$")
_MASK_RE = re.compile("\x00([0-9]+)\x01")

# In math: a brace group that switches back to text, and verbatim arguments, for the $ scan.
_TEXT_IN_MATH_RE = re.compile(r"\\(?:mbox|hbox|text[a-z]*)\s*\{")
_VERBATIM_ARG_RE = re.compile(_VERBATIM_ARG)

# Typographic punctuation outside Latin-1 that inputenc defines and pdflatex typesets in T1
# (TeX Live utf8enc.dfu / t1enc.dfu / ts1enc.dfu): hyphens and dashes, curly and low quotes,
# daggers, bullet, ellipsis, per mille, single guillemets, euro, trade mark.
_TYPESET_PUNCTUATION = frozenset(
    "‐‑‒–—―‘’‚“”„"
    "†‡•…‰‹›€™"
)
# Latin Extended-A letters with no definition in those files (H/T with stroke, kra, L with
# middle dot, n preceded by apostrophe): pdflatex stops on them like on any undefined character.
_UNDEFINED_LATIN_A = frozenset("ĦħĸĿŀŉŦŧ")
# The characters typesettable() accepts that pdflatex typesets only in T1: in OT1 (inputenc
# without fontenc) each stops the compile (measured, TeX Live 2026; a test pins the set). So
# does the ogonek accent command \k, which the copy writes for a letter with an ogonek.
T1_ONLY_CHARS = frozenset("«»‹›‚„ÐÞðþĄąĐđĘęĮįŊŋŲų")

# Combining marks with a standard LaTeX accent command (all defined for T1 by the kernel).
_ACCENT_CMD = {
    "̀": "`",  # grave
    "́": "'",  # acute
    "̂": "^",  # circumflex
    "̃": "~",  # tilde
    "̄": "=",  # macron
    "̆": "u",  # breve
    "̇": ".",  # dot above
    "̈": '"',  # diaeresis
    "̊": "r",  # ring above
    "̋": "H",  # double acute
    "̌": "v",  # caron
    "̣": "d",  # dot below
    "̦": "textcommabelow",  # comma below (LaTeX kernel, T1)
    "̧": "c",  # cedilla
    "̨": "k",  # ogonek
    "̱": "b",  # macron below
}
_BELOW_MARKS = frozenset("̧̨̣̦̱")


# @MX:ANCHOR: [AUTO] The one character policy the bib copy, its verify check and the compile
# test share; it assumes the preamble render emits (utf8 inputenc + T1 + lmodern).
# @MX:REASON: callers: _char_to_latex here, pkgreqs_checks.bib_latex_safety_problems (verify),
# the pdflatex tests that compile every character it accepts (T1) and pin T1_ONLY_CHARS (OT1)
# -- widening it unmeasured breaks compiles that verify passed.
def typesettable(ch: str) -> bool:
    """True iff pdflatex typesets ``ch`` with the preamble sci-adk emits (utf8 inputenc, T1,
    Latin Modern). PURE.

    Every character accepted here is compiled by a test with the real render preamble; the ones
    that need T1 rather than OT1 are :data:`T1_ONLY_CHARS`. ASCII control characters other than
    tab, line feed and carriage return are refused: LaTeX reads them as invalid input.
    """
    cp = ord(ch)
    if cp < 0x80:
        return 0x20 <= cp < 0x7F or ch in "\t\n\r"
    if 0xA0 <= cp <= _ACCENT_HI:
        return ch not in _UNDEFINED_LATIN_A
    return ch in _TYPESET_PUNCTUATION


def printed_field(name: str) -> bool:
    """False for a field no BibTeX style prints (:data:`UNPRINTED_FIELDS`). PURE."""
    name = name.lower()
    return name not in UNPRINTED_FIELDS and not name.startswith(_UNPRINTED_PREFIXES)


def _group(latex: str) -> str:
    """A command or math replacement in braces (protected from BibTeX's case change)."""
    return "{" + latex + "}" if ("\\" in latex or "$" in latex) else latex


def _box(latex: str) -> str:
    """Text-mode LaTeX made usable inside math."""
    return "\\mbox{" + latex + "}"


def _math_form(ch: str) -> str | None:
    """The prose map's math form of ``ch`` without its ``$`` (``≥`` -> ``\\geq``), in braces
    when the command has a capital letter (BibTeX's title case change lowercases a command at
    brace level 0, ``\\Delta`` -> ``\\delta``, but not inside a brace group); None when the map
    has no math form for ``ch``."""
    m = _MATH_FORM_RE.fullmatch(_UNICODE_MAP.get(ch, ""))
    if m is None:
        return None
    inner = m.group(1)
    return "{" + inner + "}" if any(c.isupper() for c in inner) else inner


def _accent_commands(base: str, marks: str) -> str | None:
    """``base`` with combining ``marks`` as nested LaTeX accent commands in one brace group,
    or None when the base is not a letter pdflatex has or a mark has no standard command."""
    if not (base.isalpha() and typesettable(base)):
        return None
    if any(m not in _ACCENT_CMD for m in marks):
        return None
    latex = base
    if base in "ij" and any(m not in _BELOW_MARKS for m in marks):
        latex = "\\" + base  # a mark above sits on the dotless i / j
    for mark in marks:  # canonical order: the innermost mark first
        latex = "\\" + _ACCENT_CMD[mark] + "{" + latex + "}"
    return "{" + latex + "}"


def _accented(cluster: str, math: bool) -> str | None:
    """A letter and its marks, fully decomposed, as accent commands (boxed in math), or None."""
    decomposed = unicodedata.normalize("NFD", cluster)
    latex = _accent_commands(decomposed[0], decomposed[1:])
    if latex is None:
        return None
    return _box(latex) if math else latex


def _char_to_latex(ch: str, math: bool = False) -> str:
    """One character of a bib field in a form pdflatex typesets (in math or text mode), or
    itself when it has none."""
    if ord(ch) < 0x80:
        return ch
    category = unicodedata.category(ch)
    if category == "Zs":
        return " "
    if math and (form := _math_form(ch)) is not None:
        return form  # ± in math is \pm, not a text-mode sign
    if typesettable(ch):
        return ch
    if category == "Cf":
        return ""
    if ch in _UNICODE_MAP:
        latex = _UNICODE_MAP[ch]
        if not math:
            return _group(latex)
        return _box(latex) if "\\" in latex else latex
    if unicodedata.normalize("NFD", ch) != ch:  # an accented letter: accent commands, or kept
        accented = _accented(ch, math)
        return accented if accented is not None else ch
    folded = unicodedata.normalize("NFKC", ch)
    if folded != ch:  # a compatibility character (ligature, width variant, ...)
        form = _chars_to_latex(folded, math)
        if all(typesettable(c) for c in form):
            return form
    return ch


def _clusters(text: str) -> Iterator[str]:
    """``text`` as a letter (or any character) followed by its combining marks, in order."""
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and unicodedata.combining(text[j]):
            j += 1
        yield text[i:j]
        i = j


def _cluster_to_latex(cluster: str, math: bool) -> str:
    if len(cluster) == 1:
        return _char_to_latex(cluster, math)
    accented = _accented(cluster, math)
    return accented if accented is not None else cluster


def _chars_to_latex(text: str, math: bool = False) -> str:
    """``text`` with each character, or letter plus its combining marks, made typesettable."""
    out = ""
    previous_converted = False
    for cluster in _clusters(text):
        latex = _cluster_to_latex(cluster, math)
        converted = latex != cluster
        if (
            math
            and (converted or previous_converted)
            and latex[:1].isascii()
            and latex[:1].isalpha()
            and _CONTROL_WORD_END_RE.search(out)
        ):
            latex = " " + latex  # "\alpha x", never the undefined "\alphax"
        out += latex
        previous_converted = converted
    return out


def _decode_entity(m: re.Match) -> str:
    raw = m.group(0)
    text = html.unescape(raw)
    if text == raw:
        return raw  # not an entity HTML knows: left for the ampersand escape below
    return "".join(_ENTITY_LATEX.get(c) or _latex_escape(c) for c in text)


def _decode_entity_verbatim(m: re.Match) -> str:
    raw = m.group(0)
    text = html.unescape(raw)
    if any(c in '{}\\"' for c in text):
        return raw  # would unbalance or end the value: left for verify to name
    return text


def _convert_markup(text: str) -> str:
    def _sub(m: re.Match) -> str:
        return "\\" + _MARKUP_CMD[m.group("tag").lower()] + "{" + m.group("body") + "}"

    for _ in range(10):  # each pass converts the outermost pairs; nesting is shallow
        converted = _MARKUP_PAIR_RE.sub(_sub, text)
        if converted == text:
            break
        text = converted
    return text


def _segments(value: str) -> Iterator[tuple[str, str]]:
    """``(kind, text)`` pieces of one field value, in order; ``kind`` is ``"text"``,
    ``"math"`` or ``"verbatim"`` (an argument typeset verbatim, ``\\url{...}``)."""
    pos = 0
    for m in _VALUE_SEGMENT_RE.finditer(value):
        if m.start() > pos:
            yield "text", value[pos : m.start()]
        yield ("verbatim" if m.group("verbatim") else "math"), m.group(0)
        pos = m.end()
    if pos < len(value):
        yield "text", value[pos:]


def _finish_text(text: str) -> str:
    text = _TEXT_ESCAPE_RE.sub(lambda m: _TEXT_ESCAPE[m.group(0)], text)
    return _chars_to_latex(unicodedata.normalize("NFC", text))  # NFC again: decoded entities


def _finish_math(math: str) -> str:
    math = HTML_ENTITY_RE.sub(_decode_entity, math)
    math = math.replace(r"\textless{}", "<").replace(r"\textgreater{}", ">")
    math = _MATH_ESCAPE_RE.sub(r"\\\g<0>", math)
    return _chars_to_latex(unicodedata.normalize("NFC", math), math=True)


def _latex_safe_text(value: str) -> str:
    """One printed, non-verbatim field value in LaTeX (see the module docstring)."""
    value = unicodedata.normalize("NFC", value.replace("\x00", "").replace("\x01", ""))
    # Markup is read in running text only: math and verbatim pieces are masked while tags are
    # converted, so "$a<i>b$" stays a comparison and "<i>a $x$ b</i>" still becomes \textit.
    held: list[tuple[str, str]] = []
    masked: list[str] = []
    for kind, piece in _segments(value):
        if kind == "text":
            masked.append(HTML_ENTITY_RE.sub(_decode_entity, piece))
        else:
            masked.append(f"\x00{len(held)}\x01")
            held.append((kind, piece))
    joined = HTML_TAG_RE.sub("", _convert_markup("".join(masked)))
    out = []
    pos = 0
    for m in _MASK_RE.finditer(joined):
        out.append(_finish_text(joined[pos : m.start()]))
        kind, piece = held[int(m.group(1))]
        if kind == "math":
            out.append(_finish_math(piece))
        else:
            out.append(_XML_ENTITY_RE.sub(_decode_entity_verbatim, piece))
        pos = m.end()
    out.append(_finish_text(joined[pos:]))
    return "".join(out)


def _value_end(bib: str, start: int) -> int:
    """The index of the delimiter closing the value that opens at ``start`` (``{`` or ``"``),
    brace-depth aware; when it never closes, the start of the next entry header (or the end)."""
    depth = 0
    quoted = bib[start] == '"'
    for i in range(start + (1 if quoted else 0), len(bib)):
        c = bib[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and not quoted:
                return i
            if depth < 0:
                break  # the entry closed inside a quoted value: malformed
        elif c == '"' and quoted and depth == 0:
            return i
    header = _HEADER_RE.search(bib, start + 1)
    return header.start() if header else len(bib)


def _field_parts(bib: str) -> list[tuple[str, int, int, bool]]:
    """``(field name in lower case, start, end, delimited)`` of every part of every field value
    in ``bib``: braced or quoted values (delimiters excluded, ``delimited`` True) and bare tokens
    (numbers, macro names such as ``jun``; ``delimited`` False), ``#``-concatenated parts each
    their own entry."""
    parts: list[tuple[str, int, int, bool]] = []
    pos = 0
    n = len(bib)
    while (m := _FIELD_NAME_RE.search(bib, pos)) is not None:
        name = m.group(1).lower()
        j = m.end()
        while True:
            if j < n and bib[j] in '{"':
                end = _value_end(bib, j)
                parts.append((name, j + 1, end, True))
                j = end + 1
            else:
                end = _BARE_TOKEN_RE.match(bib, j).end()
                if end > j:
                    parts.append((name, j, end, False))
                j = end
            k = j
            while k < n and bib[k].isspace():
                k += 1
            if k < n and bib[k] == "#":
                j = k + 1
                while j < n and bib[j].isspace():
                    j += 1
                continue
            break
        pos = max(j, m.end())
    return parts


def field_value_spans(bib: str) -> list[tuple[str, int, int]]:
    """``(field name in lower case, start, end)`` of every braced or quoted value in ``bib``,
    delimiters excluded, ``#``-concatenated parts each their own span. Bare tokens (numbers,
    ``@string`` macro names) carry no text and are not listed. PURE."""
    return [(name, start, end) for name, start, end, delimited in _field_parts(bib) if delimited]


def _string_macros(bib: str) -> set[str]:
    """Lower-cased names ``bib`` defines with ``@string`` (BibTeX macro names ignore case). PURE."""
    return {m.group(1).lower() for m in _STRING_DEF_RE.finditer(bib)}


def undefined_month_tokens(bib: str) -> list[tuple[str, str]]:
    """``(token, macro)`` for each bare ``month`` token in ``bib`` that BibTeX does not define
    but names a month (``June`` -> ``jun``, ``sept`` -> ``sep``); the copy writes the macro.
    A name the bib defines itself with ``@string`` is not undefined and is not listed. PURE."""
    own = _string_macros(bib)
    return [
        (bib[start:end], _MONTH_MACRO[bib[start:end].lower()])
        for name, start, end, delimited in _field_parts(bib)
        if name == "month"
        and not delimited
        and bib[start:end].lower() in _MONTH_MACRO
        and bib[start:end].lower() not in own
    ]


def bare_specials(value: str) -> set[str]:
    """The characters among ``&``, ``%``, ``#``, ``_``, ``^`` that ``value`` (one printed field
    value, not url/doi) holds unescaped where the copy would escape them: all five in text,
    ``&`` ``%`` ``#`` in math, none in a verbatim argument; a ``&`` that starts an HTML entity is
    not counted (it has its own problem line). PURE; verify's check uses it, so the check and
    the copy agree on what is bare."""
    found: set[str] = set()
    for kind, text in _segments(value):
        if kind == "text":
            found.update(m.group(0)[0] for m in _BARE_IN_TEXT_RE.finditer(text))
        elif kind == "math":
            found.update(m.group(0)[0] for m in _BARE_IN_MATH_RE.finditer(text))
    return found


def html_tags(value: str) -> list[str]:
    """The distinct markup tags (:data:`HTML_TAG_RE`) in the running text of ``value``; math is
    never read as markup. PURE."""
    return sorted(
        {t for kind, text in _segments(value) if kind == "text" for t in HTML_TAG_RE.findall(text)}
    )


def stray_math_dollar(value: str) -> bool:
    """True iff a ``$`` in ``value`` breaks math: one that would close math at a brace level
    other than the one the math opened at (``$x {$\\geq$} 3$``: pdflatex stops), a group opened
    before the math that closes inside it, or math left open (``Price in $US``). A ``\\mbox``,
    ``\\hbox`` or ``\\text...`` group inside math is text again; ``\\$`` and verbatim arguments
    are not math. PURE."""
    depth = 0
    stack: list[tuple[str, int, int]] = []  # ("math", open depth, width) / ("text", depth, 0)
    i, n = 0, len(value)
    while i < n:
        c = value[i]
        in_math = bool(stack) and stack[-1][0] == "math"
        if c == "\\":
            m = _VERBATIM_ARG_RE.match(value, i)
            if m is None and in_math:
                m = _TEXT_IN_MATH_RE.match(value, i)
                if m is not None:
                    depth += 1
                    stack.append(("text", depth, 0))
            i = m.end() if m is not None else i + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if stack and stack[-1][:2] == ("text", depth):
                stack.pop()
            elif in_math and depth == stack[-1][1]:
                return True
            depth -= 1
        elif c == "$":
            if in_math:
                width = stack[-1][2]
                if stack[-1][1] != depth or value[i : i + width] != "$" * width:
                    return True
                stack.pop()
            else:
                width = 2 if value.startswith("$$", i) else 1
                stack.append(("math", depth, width))
            i += width
            continue
        i += 1
    return any(kind == "math" for kind, _depth, _width in stack)


def untypesettable_chars(value: str, *, verbatim: bool = False) -> list[tuple[str, str | None]]:
    """``(character, LaTeX form or None)`` for each character of ``value`` (one printed field
    value) that pdflatex cannot typeset with the preamble sci-adk emits, in order. The form is
    what the copy writes for the letter or symbol it belongs to (math or text mode as it
    stands); None when there is none -- a mark with no LaTeX command, a character with no
    mapping -- and for everything in a ``url``/``doi`` value (``verbatim``) or a verbatim
    argument, which the copy leaves as it is. PURE."""
    found: list[tuple[str, str | None]] = []
    pieces = [("verbatim", value)] if verbatim else _segments(value)
    for kind, text in pieces:
        for cluster in _clusters(text):
            bad = [c for c in cluster if not typesettable(c)]
            if not bad:
                continue
            form = None
            if kind != "verbatim":
                latex = _chars_to_latex(unicodedata.normalize("NFC", cluster), kind == "math")
                if all(typesettable(c) for c in latex):
                    form = latex
            found.extend((c, form) for c in bad)
    return found


# @MX:NOTE: [AUTO] Writes only the paper/ copy; the literature store keeps the acquired bytes
# and its keys. Characters with no LaTeX form are kept so verify can name them.
def latex_safe_bib(bib: str) -> str:
    """``bib`` with every printed field value made LaTeX-safe; everything else untouched except
    a bare month name BibTeX does not define, which becomes its macro. PURE.

    In each printed value (not url/doi, not :data:`UNPRINTED_FIELDS`): HTML entities are decoded
    to LaTeX (``&amp;`` -> ``\\&``, ``&lt;`` -> ``\\textless{}``, ``&quot;`` -> ``{"}``; in math
    ``&lt;`` -> ``<``), ``<i>``/``<em>`` -> ``\\textit{}``, ``<b>``/``<strong>`` ->
    ``\\textbf{}``, ``<sub>``/``<sup>`` -> ``\\textsubscript{}``/``\\textsuperscript{}``, other
    known tags are stripped, a bare ``&``, ``%`` or ``#`` is escaped, and in text a bare ``_``,
    a bare ``^`` (``\\textasciicircum{}``) and any ``<`` / ``>`` (``\\textless{}`` /
    ``\\textgreater{}``); characters pdflatex cannot typeset follow the module's character
    policy. ``url`` and ``doi`` values only have XML's escapes decoded; unprinted fields are
    copied as they are. Idempotent: text that is already LaTeX-safe comes back byte for byte.
    """
    out = []
    pos = 0
    own = _string_macros(bib)
    for name, start, end, delimited in _field_parts(bib):
        out.append(bib[pos:start])
        value = bib[start:end]
        if not delimited:
            if name == "month" and value.lower() not in own:
                value = _MONTH_MACRO.get(value.lower(), value)
            out.append(value)
        elif not printed_field(name):
            out.append(value)
        elif name in VERBATIM_FIELDS:
            out.append(_XML_ENTITY_RE.sub(_decode_entity_verbatim, value))
        else:
            out.append(_latex_safe_text(value))
        pos = end
    out.append(bib[pos:])
    return "".join(out)


__all__ = [
    "HTML_ENTITY_RE",
    "HTML_TAG_RE",
    "T1_ONLY_CHARS",
    "UNPRINTED_FIELDS",
    "VERBATIM_FIELDS",
    "bare_specials",
    "field_value_spans",
    "html_tags",
    "latex_safe_bib",
    "printed_field",
    "stray_math_dollar",
    "typesettable",
    "undefined_month_tokens",
    "untypesettable_chars",
]
