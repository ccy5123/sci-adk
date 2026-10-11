"""
The LaTeX-safe copy of a run's bibliography, and which characters pdflatex can typeset.

Render copies the run's literature pool (``literature/references.bib``, as paperforge or a manual
ingest wrote it) into ``paper/references.bib`` and the cited-only ``paper/references_SI.bib``.
Registrar BibTeX (Crossref's metadata is XML-rooted) can carry HTML entities (``&amp;``), HTML
markup (``<i>K</i>``) and characters pdflatex cannot typeset (U+2212 MINUS SIGN).
:func:`latex_safe_bib` writes that copy in LaTeX; :func:`paper_bib`, what render writes, adds
four changes to what plainnat prints (title case kept as acquired, no ISSN or URL repeating
the DOI, no stray period after a given name, name letters BibTeX sorts by their base letter).
The pool itself is never rewritten here: its keys never change and the merge keeps old entries
verbatim (``search/literature_merge.py``).

Only field values change; entry headers (keys), field names and the text between entries are
copied as they are, except that a bare month name BibTeX does not define (``month = June``,
``month = sept``: BibTeX warns and leaves the month out of the reference list) becomes its
three-letter macro (``jun``, ``sep``).

Three kinds of field are left alone or nearly so:

- ``url`` and ``doi`` values are never escaped: plainnat prints them through ``\\url`` /
  ``\\Url``, which print a special character as itself, so an escape there prints its backslash
  (measured: ``AID\\_JBM1`` for ``\\_`` in a doi). XML's own escapes in them (``&amp;``,
  ``&lt;``, ``&gt;``, ``&quot;``, ``&apos;``, numeric) are decoded; any other entity-shaped text
  (``?a&copy;b``) is part of the URL. They are NOT inert: hyperref reads a URL as TeX to make
  the link, so a backslash command in one runs (``\\csname @@input\\endcsname`` read a file)
  and ``^^5c`` spells a backslash; verify fails a backslash, ``^^``, a brace or a ``run:`` /
  ``file:`` link in a url or doi value and in the URL argument of ``\\url`` / ``\\href``
  (:func:`url_problems`).
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
``T1`` fontenc and Latin Modern (``paper.T1_FONT_LINES``) or, under the figure font policy,
Times (``paper.TIMES_FONT_LINES``: newtxtext); a test compiles every accepted character with
both:

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
- a compatibility character (a ligature, a width variant) is folded when the fold typesets,
  and the ASCII it folds to is written as text: a fullwidth ``\\`` ``{`` ``&`` ``%`` ...
  becomes ``\\textbackslash{}``, ``\\textbraceleft{}``, ``\\&``, ``\\%`` (boxed in math),
  never a live special;
- an ASCII control character other than tab, line feed and carriage return, and DEL, is
  dropped;
- a character with no LaTeX form -- a letter carrying a mark LaTeX has no standard command for
  (hook above, horn), an accent on a non-Latin letter, CJK -- is KEPT, never replaced by a
  placeholder or stripped of a mark: a reference must not silently lose a letter or an accent,
  so verify names it instead.

Commands are copied as acquired (a bib entry legitimately holds ``{\\"O}`` or
``\\textit{n}``); verify fails a command on :data:`DANGEROUS_COMMANDS` (one that can read or
write a file, define a macro, change how TeX reads its input or end the document) and TeX's
``^^`` character-code notation, which the copy writes in math as two printed carets (in text a
``^`` is escaped anyway); any other command outside :data:`SAFE_COMMANDS` (accents, letters,
markup, symbols, common math) is named in an advisory, and so is a math command in running text
(:data:`MATH_ONLY_COMMANDS`, :func:`math_commands_in_text`).

What BibTeX prints is read as BibTeX reads the file (:func:`bib_commands`): every ``@string``
value (printed wherever a field names the macro) and every ``@preamble`` (written into the
reference list as it is) as well as the entries, a parenthesised entry or ``@ article`` too. The
paper copy (:func:`paper_bib`) leaves every ``@preamble`` out; verify fails one.

PURE (string in, string out): stdlib plus sibling render helpers, no I/O.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterator, NamedTuple
from urllib.parse import unquote

from sci_adk.render.paper import _ACCENT_HI, _UNDEFINED_LATIN_A, _UNICODE_MAP, _latex_escape

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
# middle dot, n preceded by apostrophe) are ``paper._UNDEFINED_LATIN_A``, imported above: the
# prose sanitizer and this copy refuse the same eight letters.
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

# @MX:NOTE: [AUTO] The list is about what a command can do, not whether the paper loads its
#   package: none of these reads or writes a file, defines a macro or ends the document.
# The control words a printed bib value is known to carry (verify names any other that is not
# on :data:`DANGEROUS_COMMANDS` in an advisory, :func:`unknown_commands`): accents with a
# letter name (an accent written with a symbol, the acute or the umlaut, is not a control
# word), letters, text markup, the verbatim commands, text symbols and common math -- plus
# every command the copy itself writes (:data:`SAFE_COMMANDS`).
_SAFE_TEXT_COMMANDS = frozenset(
    "b c d H k r t u v textcommabelow "
    "i j o O l L ss SS ae AE oe OE aa AA dh DH th TH ng NG dj DJ "
    "textit textbf textsc textrm textsf texttt textup textsl textmd textnormal emph em it bf "
    "sc rm sf tt sl up mbox textsubscript textsuperscript underline "
    "url href path doi Url "
    "textbackslash textasciitilde textasciicircum textless textgreater textbraceleft "
    "textbraceright textbar textunderscore textdollar textendash textemdash textquoteleft "
    "textquoteright textquotedblleft textquotedblright textquotesingle textregistered "
    "texttrademark textcopyright copyright textdegree textperiodcentered textbullet "
    "textellipsis ldots dots dag ddag S P pounds textsection textparagraph textdagger "
    "textdaggerdbl guillemotleft guillemotright guilsinglleft guilsinglright quotedblbase "
    "quotesinglbase textexclamdown textquestiondown textmu textperthousand LaTeX LaTeXe TeX "
    "relax protect space nobreakspace thinspace enspace quad qquad newline allowbreak "
    "ensuremath".split()
)
_SAFE_MATH_COMMANDS = frozenset(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa varkappa "
    "lambda mu nu xi omicron pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi "
    "psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega "
    "pm mp times div cdot cdots vdots ddots leq geq le ge neq ne approx sim simeq cong equiv "
    "propto ll gg lesssim gtrsim leqslant geqslant infty partial nabla sum prod int oint "
    "sqrt surd frac dfrac tfrac binom left right big Big bigg Bigg bigl bigr Bigl Bigr middle "
    "prime circ to rightarrow leftarrow Rightarrow Leftarrow leftrightarrow Leftrightarrow "
    "longrightarrow longleftarrow uparrow downarrow mapsto rightleftharpoons in notin ni "
    "subset supset subseteq supseteq cup cap setminus emptyset varnothing forall exists neg "
    "lnot land lor wedge vee oplus otimes ominus odot langle rangle lfloor rfloor lceil "
    "rceil hbar ell Re Im aleph log ln lg exp sin cos tan cot sinh cosh tanh arcsin arccos "
    "arctan min max lim sup inf det dim ker deg arg gcd Pr hat bar tilde vec dot ddot check "
    "breve acute grave mathring widehat widetilde overline overrightarrow star ast dagger "
    "ddagger bullet perp parallel mid vert Vert lvert rvert backslash colon displaystyle "
    "textstyle scriptstyle scriptscriptstyle limits nolimits not angle triangle diamond "
    "mathrm mathit mathbf mathsf mathtt mathcal mathbb mathfrak mathscr boldsymbol text "
    "operatorname".split()
)
_COMMAND_NAME_RE = re.compile(r"\\([A-Za-z]+)")
SAFE_COMMANDS = frozenset(
    _SAFE_TEXT_COMMANDS
    | _SAFE_MATH_COMMANDS
    | {cmd for cmd in _ACCENT_CMD.values() if cmd.isalpha()}
    | set(_MARKUP_CMD.values())
    | {
        m.group(1)
        for latex in (*_UNICODE_MAP.values(), *_ENTITY_LATEX.values(), *_TEXT_ESCAPE.values())
        for m in _COMMAND_NAME_RE.finditer(latex)
    }
)
# @MX:NOTE: [AUTO] A deny-list on purpose: publisher and Crossref metadata carry many harmless
#   commands no closed list foresees (\texttimes, \MakeUppercase, \hspace ...), so verify fails
#   only these and names any other unknown command in an advisory.
# The control words a printed bib value must not carry (verify fails on each,
# :func:`dangerous_commands`): what can read or write a file (input, include, openin, write,
# the file and PDF-object primitives), define or redefine a macro (def, let, newcommand ...,
# the register-defining primitives and the prefixes long, outer, global, protected), change
# how TeX reads its input (catcode and the other code tables, endlinechar, csname,
# expandafter, scantokens, makeatletter), run code at a later point (the every- token lists,
# aftergroup, AtEndDocument ...), stop the run or swallow the rest of the document (end,
# endinput, stop, the conditionals and loop, which can hide everything after them), start
# another reference (bibitem), load a class or package, change the interaction mode, raise an
# error, or reach the engine (directlua, ShellEscape, primitive).
DANGEROUS_COMMANDS = frozenset(
    # files
    "input include includeonly InputIfFileExists IfFileExists openin openout closein "
    "closeout read readline write immediate newwrite newread includegraphics lstinputlisting "
    "verbatiminput VerbatimInput bibliography bibliographystyle nocite addbibresource "
    "special pdfliteral pdfobj pdfrefobj pdfannot pdfcatalog pdfinfo pdfnames pdftrailer "
    "pdfximage pdfrefximage pdffiledump pdfmdfivesum pdffilesize pdffilemoddate jobname "
    # macro definitions
    "def edef gdef xdef let futurelet global long outer protected chardef mathchardef "
    "countdef dimendef skipdef muskipdef toksdef newcount newdimen newskip newtoks newbox "
    "newif newcommand renewcommand providecommand DeclareRobustCommand DeclareTextCommand "
    "DeclareTextSymbol DeclareMathSymbol newenvironment renewenvironment NewDocumentCommand "
    "RenewDocumentCommand ProvideDocumentCommand DeclareDocumentCommand "
    # how TeX reads its input
    "catcode lccode uccode sfcode mathcode delcode endlinechar newlinechar escapechar "
    "makeatletter makeatother csname endcsname expandafter scantokens "
    # code run later
    "afterassignment aftergroup everypar everymath everydisplay everyhbox everyvbox everyjob "
    "everycr everyeof output shipout AtBeginDocument AtEndDocument "
    # stopping, swallowing, loading
    "begin end enddocument endinput stop bye dump usepackage RequirePackage documentclass "
    "LoadClass if ifx ifcat ifnum ifdim ifodd ifcase iftrue iffalse ifeof ifcsname "
    "ifdefined ifmmode ifvmode ifhmode ifinner ifvoid ifhbox ifvbox unless else or fi loop "
    "bibitem "
    # interaction, errors, the engine
    "batchmode nonstopmode scrollmode errorstopmode errmessage errhelp PackageError "
    "ClassError GenericError show showthe showbox showlists showtokens directlua latelua "
    "luaexec luadirect ShellEscape DelayedShellEscape primitive pdfprimitive".split()
)
# The commands pdflatex accepts only in math (measured: "Missing $ inserted", "\mathrm allowed
# only in math mode"): the math list and the math forms of the prose map, less what also works
# in running text (\ldots, \S, \text, \angle, \vdots and every command the copy writes in
# text; each of the rest stopped pdflatex in text, measured one by one with the render
# preamble). In running text verify names each in an advisory (:func:`math_commands_in_text`).
_MAP_TEXT_COMMANDS = frozenset(
    m.group(1)
    for latex in _UNICODE_MAP.values()
    for m in _COMMAND_NAME_RE.finditer(_MATH_FORM_RE.sub("", latex))
)
_MAP_MATH_COMMANDS = frozenset(
    m.group(1)
    for latex in _UNICODE_MAP.values()
    for inner in _MATH_FORM_RE.findall(latex)
    for m in _COMMAND_NAME_RE.finditer(inner)
)
MATH_ONLY_COMMANDS = frozenset(
    (_SAFE_MATH_COMMANDS | _MAP_MATH_COMMANDS)
    - _SAFE_TEXT_COMMANDS
    - _MAP_TEXT_COMMANDS
    - {"text", "angle", "vdots"}
)
# A TeX token that starts with a backslash: a control word (letters) or a control symbol
# (one other character, a second backslash included -- ``\\input`` is a line break and text).
_TEX_TOKEN_RE = re.compile(r"\\(?:([A-Za-z]+)|.)", re.DOTALL)
# Math ``^^`` as the copy writes it: two printed carets, never TeX's character-code notation.
_PRINTED_CARETS = r"\mbox{\textasciicircum{}\textasciicircum{}}"


# @MX:ANCHOR: [AUTO] The one character policy the bib copy, its verify check and the compile
# test share; it assumes the preambles render emits (utf8 inputenc + T1 + lmodern or newtxtext).
# @MX:REASON: callers: _char_to_latex here, pkgreqs_checks.bib_latex_safety_problems (verify),
# the pdflatex tests that compile every character it accepts (T1, both typefaces) and pin
# T1_ONLY_CHARS (OT1) -- widening it unmeasured breaks compiles that verify passed.
def typesettable(ch: str) -> bool:
    """True iff pdflatex typesets ``ch`` with the preambles sci-adk emits (utf8 inputenc, T1,
    Latin Modern or Times). PURE.

    Every character accepted here is compiled by a test with both real render preambles; the
    ones that need T1 rather than OT1 are :data:`T1_ONLY_CHARS`. ASCII control characters other than
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


def _text_char(c: str) -> str:
    """A character decoded from an entity or folded from a compatibility form, as text: a
    LaTeX special escaped (``\\`` -> ``\\textbackslash{}``), a brace, ``<``, ``>`` or ``"``
    as a command or a group (BibTeX counts every brace, so ``\\{`` would unbalance the
    field), anything else as it is."""
    return _ENTITY_LATEX.get(c) or _latex_escape(c)


def _folded_ascii(c: str, math: bool) -> str:
    """An ASCII character a compatibility fold produced, as text (:func:`_text_char`), boxed
    in math when it is not itself."""
    latex = _text_char(c)
    return _box(latex) if math and latex != c else latex


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
        return ch if typesettable(ch) else ""  # a C0 control or DEL: pdflatex refuses it
    category = unicodedata.category(ch)
    if category == "Zs":
        return " "
    if math and (form := _math_form(ch)) is not None:
        return form  # ± in math is \pm, not a text-mode sign
    if typesettable(ch):
        if math and unicodedata.normalize("NFD", ch) != ch:
            # inputenc writes an accented letter as a text accent command, which stops
            # pdflatex in math when the font has no glyph for it ("Please use \mathaccent
            # for accents in math mode": ū, ĉ, ŵ ...): accent commands in a box instead.
            accented = _accented(ch, True)
            if accented is not None:
                return accented
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
        # Its ASCII is text like any other: a fullwidth backslash or brace is a character to
        # print, never LaTeX to run (a fullwidth \input{x} was read from the .bbl).
        folded = "".join(_folded_ascii(c, math) if c.isascii() else c for c in folded)
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
    return "".join(_text_char(c) for c in text)


def _decode_entity_math(m: re.Match) -> str:
    """An entity inside math, decoded: each ASCII character it stands for as text, boxed when
    that is not the character itself (:func:`_folded_ascii`; ``&#92;`` -> ``\\mbox{
    \\textbackslash{}}``, since a text command stops pdflatex in math mode), except ``<`` and
    ``>``, which stay relations; a non-ASCII character as it is (the math pass maps it)."""
    raw = m.group(0)
    text = html.unescape(raw)
    if text == raw:
        return raw  # not an entity HTML knows: left for the ampersand escape below
    return "".join(
        c if c in "<>" or not c.isascii() else _folded_ascii(c, True) for c in text
    )


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
    math = HTML_ENTITY_RE.sub(_decode_entity_math, math)
    math = math.replace(r"\textless{}", "<").replace(r"\textgreater{}", ">")
    math = _MATH_ESCAPE_RE.sub(r"\\\g<0>", math)
    math = math.replace("^^", _PRINTED_CARETS)  # ^^5c would be a backslash to TeX
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


class _Field(NamedTuple):
    """One field of a bib: its name in lower case, where the name starts, where the field ends
    (just past the value's closing delimiter), and its value parts ``(start, end, delimited)``
    -- see :func:`_field_parts`."""

    name: str
    start: int
    end: int
    parts: tuple[tuple[int, int, bool], ...]


def _fields(bib: str) -> list[_Field]:
    """Every ``name = value`` field in ``bib``, in order (see :func:`_field_parts`)."""
    fields: list[_Field] = []
    pos = 0
    n = len(bib)
    while (m := _FIELD_NAME_RE.search(bib, pos)) is not None:
        name = m.group(1).lower()
        j = m.end()
        parts: list[tuple[int, int, bool]] = []
        while True:
            if j < n and bib[j] in '{"':
                end = _value_end(bib, j)
                parts.append((j + 1, end, True))
                j = end + 1
            else:
                end = _BARE_TOKEN_RE.match(bib, j).end()
                if end > j:
                    parts.append((j, end, False))
                j = end
            field_end = min(j, n)
            k = j
            while k < n and bib[k].isspace():
                k += 1
            if k < n and bib[k] == "#":
                j = k + 1
                while j < n and bib[j].isspace():
                    j += 1
                continue
            break
        fields.append(_Field(name, m.start(), field_end, tuple(parts)))
        pos = max(j, m.end())
    return fields


def _field_parts(bib: str) -> list[tuple[str, int, int, bool]]:
    """``(field name in lower case, start, end, delimited)`` of every part of every field value
    in ``bib``: braced or quoted values (delimiters excluded, ``delimited`` True) and bare tokens
    (numbers, macro names such as ``jun``; ``delimited`` False), ``#``-concatenated parts each
    their own entry."""
    return [
        (field.name, start, end, delimited)
        for field in _fields(bib)
        for start, end, delimited in field.parts
    ]


def field_value_spans(bib: str) -> list[tuple[str, int, int]]:
    """``(field name in lower case, start, end)`` of every braced or quoted value in ``bib``,
    delimiters excluded, ``#``-concatenated parts each their own span. Bare tokens (numbers,
    ``@string`` macro names) carry no text and are not listed. PURE."""
    return [(name, start, end) for name, start, end, delimited in _field_parts(bib) if delimited]


def field_values(body: str) -> dict[str, str]:
    """``{field name in lower case: value}`` for the first occurrence of each field in ``body``
    (one entry's fields): braced, quoted and bare values alike (``volume = 10``), delimiters
    excluded, ``#``-concatenated parts joined. A name written inside another field's value is
    text, not a field. PURE."""
    values: dict[str, str] = {}
    for field in _fields(body):
        values.setdefault(field.name, "".join(body[start:end] for start, end, _ in field.parts))
    return values


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


def _control_words(value: str) -> Iterator[str]:
    """The control-word names in the text and math of ``value`` (one printed field value, not
    url/doi), in order. A verbatim argument (``\\url{...}``) is not read, and a backslash pair
    is a line break, not the start of a command."""
    for kind, text in _segments(value):
        if kind == "verbatim":
            continue
        for m in _TEX_TOKEN_RE.finditer(text):
            if m.group(1) is not None:
                yield m.group(1)


def dangerous_commands(value: str) -> list[str]:
    """The control words of ``value`` on :data:`DANGEROUS_COMMANDS` (``\\input``, ``\\def``,
    ``\\end``), each once, in order. PURE; verify fails a bib that carries one."""
    return list(dict.fromkeys("\\" + n for n in _control_words(value) if n in DANGEROUS_COMMANDS))


def unknown_commands(value: str) -> list[str]:
    """The control words of ``value`` on neither :data:`SAFE_COMMANDS` nor
    :data:`DANGEROUS_COMMANDS` (``\\texttimes``, ``\\MakeUppercase``), each once, in order.
    PURE; verify names them in an advisory."""
    return list(dict.fromkeys(
        "\\" + n for n in _control_words(value)
        if n not in SAFE_COMMANDS and n not in DANGEROUS_COMMANDS
    ))


def caret_notation(value: str) -> bool:
    """True iff the text or math of ``value`` holds ``^^``: TeX reads ``^^`` and what follows as
    another character (``^^5c`` is a backslash, ``^^e`` a ``%``) wherever ``^`` is a
    superscript character, so it can spell a command no scan of backslashes sees. A verbatim
    argument (``\\url{...}``) is not read. PURE."""
    return any(kind != "verbatim" and "^^" in text for kind, text in _segments(value))


def _skip_group(text: str, start: int) -> int:
    """The index just past the brace group opening at ``text[start]`` (BibTeX counting)."""
    return _group_close(text, start) + 1


def math_commands_in_text(value: str) -> list[str]:
    """The commands of :data:`MATH_ONLY_COMMANDS` that ``value`` (one printed field value) uses
    in running text, outside math and outside the argument of ``\\ensuremath``, each once, in
    order: pdflatex stops on each there (``Decay of \\alpha particles``: "Missing $ inserted").
    PURE; verify names them in an advisory."""
    found: list[str] = []
    for kind, text in _segments(value):
        if kind != "text":
            continue
        i = 0
        while (m := _TEX_TOKEN_RE.search(text, i)) is not None:
            name = m.group(1)
            if name == "ensuremath":
                after = _SPACE_RUN_RE.match(text, m.end()).end()
                if text.startswith("{", after):
                    i = _skip_group(text, after)
                    continue
            if name in MATH_ONLY_COMMANDS and "\\" + name not in found:
                found.append("\\" + name)
            i = m.end()
    return found


def accented_letters_in_math(value: str) -> list[str]:
    """The accented letters (a character with a canonical decomposition, such as ``ū``) that
    ``value`` (one printed field value) holds raw inside math, each once, in order. pdflatex
    writes each as a text accent command and, in math, sets it wrongly or stops ("Please use
    \\mathaccent for accents in math mode"); the copy writes them as accent commands in an
    ``\\mbox`` (:func:`_char_to_latex`). PURE."""
    found: list[str] = []
    for kind, text in _segments(value):
        if kind != "math":
            continue
        for ch in unicodedata.normalize("NFC", text):
            if (
                not ch.isascii()
                and typesettable(ch)
                and unicodedata.normalize("NFD", ch) != ch
                and ch not in found
            ):
                found.append(ch)
    return found


# The URL arguments of the commands that typeset one (hyperref: \url, \href, \nolinkurl; url:
# \path, \Url; plainnat: \doi), in a printed field value.
_URL_COMMAND_RE = re.compile(r"\\(?:url|Url|href|nolinkurl|path|doi)(?![A-Za-z])\s*\{")
# hyperref turns a link of these schemes into an action that launches a program or opens a
# file (\href{run:calc.exe}{x} wrote /S /Launch /F (calc.exe) into the PDF).
_LAUNCHING_SCHEMES = ("run:", "file:", "launch:", "javascript:")


def url_arguments(value: str) -> list[str]:
    """The URL argument of each ``\\url``/``\\href``/``\\nolinkurl``/``\\path``/``\\Url``/
    ``\\doi`` in ``value`` (one printed field value), as written, braces included. PURE."""
    return [value[m.end() : _group_close(value, m.end() - 1)] for m in _URL_COMMAND_RE.finditer(value)]


def url_problems(url: str) -> list[str]:
    """What ``url`` (a ``url`` or ``doi`` value, or a URL argument) holds that no URL or DOI needs
    and that hyperref, which reads a URL as TeX to make the link, runs or acts on: a backslash
    (``\\url{http://a.org/\\input{f}}`` read the file), ``^^`` (TeX's character-code notation,
    which spells a backslash as ``^^5c``), a brace, or a scheme that launches a program or
    opens a file (``run:``, ``file:``). Empty when the URL is plain. PURE."""
    found: list[str] = []
    if "\\" in url:
        found.append("a backslash")
    if "^^" in url:
        found.append("'^^'")
    if "{" in url or "}" in url:
        found.append("a brace")
    scheme = url.strip().lower()
    found += [f"the {s} scheme" for s in _LAUNCHING_SCHEMES if scheme.startswith(s)]
    return found


# -- what BibTeX reads ------------------------------------------------------------------------
#
# BibTeX acts on every '@' of a .bib that is not inside a value it is reading (bibtex.web,
# get_bib_command_or_entry_and_process): '%' starts no comment, white space may follow the '@',
# an entry may be delimited by parentheses, '@comment' is a word and nothing more (the braces
# after it are read as text between entries, so an '@' inside them starts a command), and after
# a syntax error BibTeX skips to the next '@'. It prints each @preamble's text into the .bbl,
# and a @string macro wherever a printed field names it. :func:`bib_commands` reads a .bib the
# same way, so a check of what it returns sees what BibTeX prints. Measured against BibTeX
# 0.99e (TeX Live 2026) with \nocite{*}: the same entries and @preamble text, except that
# BibTeX drops what follows a @comment or a syntax error on the file's last line, which this
# reads (it checks more, never less).

_BIB_WHITE = frozenset(" \t\n\r")
# The characters an identifier (an entry type, a field or macro name) cannot hold.
_ID_ILLEGAL = frozenset('"#%\'(),={}')


class BibCommand(NamedTuple):
    """One ``@`` command BibTeX acts on: its name in lower case (``preamble``, ``string`` or an
    entry type), where the ``@`` is, where BibTeX stopped reading it (just past the closing
    delimiter, or where a syntax error stopped it), an entry's key, its fields (a @preamble's
    value is one field named ``""``, a @string's one field named after the macro), and whether
    BibTeX read it to its closing delimiter."""

    command: str
    start: int
    end: int
    key: str | None
    fields: tuple[_Field, ...]
    complete: bool


def _skip_bib_white(bib: str, i: int) -> int:
    while i < len(bib) and bib[i] in _BIB_WHITE:
        i += 1
    return i


def _identifier_end(bib: str, i: int) -> int:
    """The end of the BibTeX identifier at ``i`` (``i`` itself when there is none: an identifier
    does not start with a digit and holds no white space, control character or ``"#%'(),={}``)."""
    if i < len(bib) and "0" <= bib[i] <= "9":
        return i
    j = i
    while j < len(bib) and bib[j] not in _BIB_WHITE and bib[j] not in _ID_ILLEGAL and bib[j] >= " ":
        j += 1
    return j


def _adjacent(bib: str, j: int, allowed: str) -> bool:
    """True iff the identifier ending at ``j`` is followed by white space, the end of the text or
    one of ``allowed`` (BibTeX refuses any other character next to it)."""
    return j >= len(bib) or bib[j] in _BIB_WHITE or bib[j] in allowed


def _string_end(bib: str, i: int) -> tuple[int, bool]:
    """``(index of the delimiter closing the string that opens at bib[i], True)``, or the index
    where BibTeX gives up on it and False: a ``}`` that unbalances a quoted string, or the end
    of the text."""
    quoted = bib[i] == '"'
    depth = 0
    for j in range(i + 1, len(bib)):
        c = bib[j]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return j, not quoted
            depth -= 1
        elif c == '"' and quoted and depth == 0:
            return j, True
    return len(bib), False


def _read_value(bib: str, i: int, close: str) -> tuple[list[tuple[int, int, bool]], int, bool]:
    """A field value as BibTeX reads it from ``bib[i]``: ``(parts, position after it and the
    white space after it, ok)``; parts as in :func:`_fields`, ``#``-joined."""
    parts: list[tuple[int, int, bool]] = []
    n = len(bib)
    while True:
        if i >= n:
            return parts, n, False
        c = bib[i]
        if c in '{"':
            end, ok = _string_end(bib, i)
            parts.append((i + 1, end, True))
            if not ok:
                return parts, end, False
            i = end + 1
        elif "0" <= c <= "9":
            j = i
            while j < n and "0" <= bib[j] <= "9":
                j += 1
            parts.append((i, j, False))
            i = j
        else:
            j = _identifier_end(bib, i)
            if j == i or not _adjacent(bib, j, "," + close + "#"):
                return parts, j, False
            parts.append((i, j, False))
            i = j
        i = _skip_bib_white(bib, i)
        if i < n and bib[i] == "#":
            i = _skip_bib_white(bib, i + 1)
            continue
        return parts, i, True


def _field(name: str, start: int, parts: list[tuple[int, int, bool]], n: int) -> _Field:
    if not parts:
        return _Field(name, start, start, ())
    last_start, last_end, delimited = parts[-1]
    return _Field(name, start, min(last_end + (1 if delimited else 0), n), tuple(parts))


def _read_command(bib: str, at: int) -> tuple[BibCommand | None, int]:
    """The command BibTeX reads at the ``@`` ``bib[at]`` (None when it reads none), and where it
    goes on looking for the next ``@``."""
    n = len(bib)
    i = _skip_bib_white(bib, at + 1)
    j = _identifier_end(bib, i)
    if j == i or not _adjacent(bib, j, "{("):
        return None, max(j, at + 1)
    name = bib[i:j].lower()
    if name == "comment":
        return None, j
    k = _skip_bib_white(bib, j)
    if k >= n or bib[k] not in "{(":
        return None, k
    close = "}" if bib[k] == "{" else ")"
    k = _skip_bib_white(bib, k + 1)
    if name in ("preamble", "string"):
        macro, field_start = "", k
        if name == "string":
            m = _identifier_end(bib, k)
            if m == k or not _adjacent(bib, m, "="):
                return None, max(m, k)
            macro = bib[k:m].lower()
            k = _skip_bib_white(bib, m)
            if k >= n or bib[k] != "=":
                return None, k
            k = _skip_bib_white(bib, k + 1)
        parts, k, ok = _read_value(bib, k, close)
        complete = ok and k < n and bib[k] == close
        end = k + 1 if complete else k
        field = _field(macro, field_start, parts, n)
        return BibCommand(name, at, end, None, (field,), complete), end
    # An entry: the key runs to a comma or white space (or, in braces, a closing brace).
    stops = _BIB_WHITE | ({",", "}"} if close == "}" else {","})
    m = k
    while m < n and bib[m] not in stops:
        m += 1
    key = bib[k:m]
    fields: list[_Field] = []

    def stopped(position: int) -> tuple[BibCommand, int]:
        return BibCommand(name, at, position, key, tuple(fields), False), position

    k = _skip_bib_white(bib, m)
    if k >= n or bib[k] not in "," + close:
        return stopped(min(k, n))
    while bib[k] != close:
        if bib[k] != ",":
            return stopped(k)
        k = _skip_bib_white(bib, k + 1)
        if k >= n:
            return stopped(n)
        if bib[k] == close:
            break
        field_start = k
        m = _identifier_end(bib, k)
        if m == k or not _adjacent(bib, m, "="):
            return stopped(max(m, k))
        field_name = bib[k:m].lower()
        k = _skip_bib_white(bib, m)
        if k >= n or bib[k] != "=":
            return stopped(min(k, n))
        k = _skip_bib_white(bib, k + 1)
        parts, k, ok = _read_value(bib, k, close)
        fields.append(_field(field_name, field_start, parts, n))
        if not ok or k >= n:
            return stopped(min(k, n))
    return BibCommand(name, at, k + 1, key, tuple(fields), True), k + 1


# @MX:ANCHOR: [AUTO] The one reading of a .bib as BibTeX reads it: the verify bib checks scan
#   what it returns, and the paper copy drops each @preamble it finds.
# @MX:REASON: callers: pkgreqs_checks (bib_command_problems, bib_command_advisories,
#   bib_latex_safety_problems), latex_safe_bib and paper_bib here; a reading that differs from
#   BibTeX's lets text BibTeX prints go unchecked (a @string, a @preamble, '@ article(...)').
def bib_commands(bib: str) -> list[BibCommand]:
    """Every ``@`` command BibTeX acts on in ``bib``, in order, read as BibTeX reads it (see the
    note above :data:`_BIB_WHITE`): ``@preamble``, ``@string`` and entries (``@comment`` is not
    a command, and neither is an ``@`` inside a value BibTeX reads). An entry or a @string that a
    syntax error stopped is listed with what BibTeX read of it (``complete`` False); BibTeX then
    looks for the next ``@`` where it stopped, and so does this. PURE."""
    commands: list[BibCommand] = []
    pos = 0
    while (at := bib.find("@", pos)) >= 0:
        command, pos = _read_command(bib, at)
        if command is not None:
            commands.append(command)
    return commands


def string_macros_used_as_urls(bib: str, commands: list[BibCommand] | None = None) -> set[str]:
    """The lower-cased names of the ``@string`` macros a ``url`` or ``doi`` field of ``bib`` names
    (``url = myurl``): their text is printed as a URL. PURE."""
    commands = bib_commands(bib) if commands is None else commands
    return {
        bib[start:end].lower()
        for command in commands
        if command.command not in ("preamble", "string")
        for field in command.fields
        if field.name in VERBATIM_FIELDS
        for start, end, delimited in field.parts
        if not delimited
    }


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
    ``&lt;`` -> ``<`` and any other text form in an ``\\mbox``, ``&#92;`` ->
    ``\\mbox{\\textbackslash{}}``), ``<i>``/``<em>`` -> ``\\textit{}``, ``<b>``/``<strong>`` ->
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
    # A @string value is printed wherever a field names the macro, whatever the macro's name
    # (title = abstract prints @string{abstract = ...}); as a URL when a url or doi names it.
    commands = bib_commands(bib)
    macro_starts = {
        f.start for c in commands if c.command == "string" for f in c.fields if f.name
    }
    url_macros = string_macros_used_as_urls(bib, commands)
    for field in _fields(bib):
        name = field.name
        if field.start in macro_starts:
            name = "url" if name in url_macros else "string"
        for start, end, delimited in field.parts:
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


# -- the reference-list copy -------------------------------------------------------------------
#
# What plainnat prints from the LaTeX-safe copy, measured on the trial run's compiled list:
# titles lowercased at brace level 0 (change.case$ "t"), an ISSN and a dx.doi.org URL beside
# every DOI, a stray period after a given name ("Donald. Mackay."), and names with non-ASCII
# letters sorted after "z" (BibTeX compares raw bytes). paper_bib() writes these four things
# differently; nothing else changes.

# Fields whose case plainnat (and the other natbib styles) change: a title; booktitle is
# included for styles that treat it like one. journal is never case-changed.
_CASE_FIELDS = frozenset({"title", "booktitle"})
# Fields holding names, sorted and formatted by BibTeX's name functions.
_NAME_FIELDS = frozenset({"author", "editor"})
# Printed beside the DOI and of no use to a reader of the reference list.
_OMITTED_FIELDS = frozenset({"issn"})

# A doi.org / dx.doi.org link (the form Crossref puts in url), and a doi value's own prefix.
_DOI_HOST = r"(?:https?://)?(?:dx\.|www\.)?doi\.org/"
_DOI_LINK_RE = re.compile(r"\s*" + _DOI_HOST + r"(\S+?)\s*", re.IGNORECASE)
_DOI_PREFIX_RE = re.compile(r"\s*(?:doi:\s*|" + _DOI_HOST + ")", re.IGNORECASE)

# A control sequence: a control word, or a control symbol other than a brace (BibTeX counts
# every brace, escaped or not, so ``\{`` opens a group for it).
_CONTROL_SEQ_RE = re.compile(r"\\(?:[A-Za-z]+|[^{}A-Za-z])", re.DOTALL)
# The control symbols that take the next letter as their argument (accents).
_ACCENT_SYMBOLS = frozenset("'`^\"~=.")
# The accent commands that are control words (cedilla, caron, double acute, breve, ogonek,
# ring, dot below, bar below, tie).
_ACCENT_WORDS = frozenset("cvHukrdbt")
# What may follow an accent command as its unbraced argument: spaces, then one letter.
_ACCENT_LETTER_RE = re.compile(r"\s*[A-Za-z]")
_SPACE_RUN_RE = re.compile(r"\s*")
# A run of letters and digits: the unit the case protection braces.
_WORD_RUN_RE = re.compile(r"[^\W_]+")
_ASCII_UPPER_RE = re.compile(r"[A-Z]")

# Latin letters with no decomposition and a LaTeX command defined in OT1 and T1, which BibTeX's
# purify$ reduces to their letters (\o -> o, \ss -> ss): what a name letter becomes so that it
# sorts with its base letter. Ð Þ Đ Ŋ (T1-only commands) and Ħ Ŀ Ŧ (none) are kept as they are.
_NAME_LETTER_CMD = {
    "Æ": "AE", "æ": "ae", "Ø": "O", "ø": "o", "Œ": "OE", "œ": "oe", "ß": "ss",
    "Ł": "L", "ł": "l", "ı": "i",
}
# A depth-0 " and " between two names (BibTeX matches it without regard to case), and the
# comma and the spaces that divide one name into its parts.
_NAME_SEPARATOR_RE = re.compile(r"\s+and\s+", re.IGNORECASE)
_COMMA_RE = re.compile(",")
_SPACES_RE = re.compile(r"\s+")
# A given-name token: a capitalised word (or hyphenated words) and a period, standing alone.
_GIVEN_TOKEN_RE = re.compile(r"(?<!\S)([^\W\d_]+(?:-[^\W\d_]+)*)\.(?=\s|$)")
# Old given-name abbreviations that keep their period (two-letter ones, "Wm.", keep it anyway).
_GIVEN_NAME_ABBREVIATIONS = frozenset(
    {"Benj", "Chas", "Edw", "Geo", "Jas", "Jno", "Jos", "Jun", "Robt", "Saml", "Sen", "Thos"}
)
_VOWELS = frozenset("aeiouyAEIOUY")


def _group_close(value: str, start: int) -> int:
    """The index of the ``}`` closing the group that opens at ``value[start]`` (BibTeX counting:
    every brace counts), or the last index when it never closes."""
    depth = 0
    for i in range(start, len(value)):
        if value[i] == "{":
            depth += 1
        elif value[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(value) - 1


def _math_end(value: str, start: int) -> int:
    """The index just past the ``$`` or ``$$`` closing the math that opens at ``value[start]``,
    or the end of ``value`` when it never closes."""
    delimiter = "$$" if value.startswith("$$", start) else "$"
    i = start + len(delimiter)
    while i < len(value):
        if value[i] == "\\":
            i += 2
            continue
        if value.startswith(delimiter, i):
            return i + len(delimiter)
        i += 1
    return len(value)


def _case_unit_end(value: str, m: re.Match) -> int | None:
    """The end of the unit that starts with the control sequence ``m`` (read at brace level 0)
    and must be braced whole to keep its capitals, or None when ``m`` starts no such unit:

    - an accent command and its unbraced letter (``\\"O``, ``\\" O``, ``\\v S``);
    - a control word with an uppercase letter in its name (``\\LaTeX``, ``\\AE``, ``\\H``), with
      the spaces TeX swallows after it and the brace groups following it as its arguments
      (``\\LaTeX{}``, ``\\H{o}``), so bracing changes nothing TeX typesets.
    """
    name = m.group(0)[1:]
    if name in _ACCENT_SYMBOLS or name in _ACCENT_WORDS:
        letter = _ACCENT_LETTER_RE.match(value, m.end())
        if letter is not None:
            return letter.end()
    if not (name[:1].isalpha() and _ASCII_UPPER_RE.search(name)):
        return None
    end = _SPACE_RUN_RE.match(value, m.end()).end()
    while value.startswith("{", end):
        end = _group_close(value, end) + 1
        after = _SPACE_RUN_RE.match(value, end).end()
        if not value.startswith("{", after):
            break
        end = after
    return end


def _protect_case(value: str, field_start: bool = True) -> str:
    """``value`` (a title-like field value, or one ``#`` part of it) with the casing it gives
    protected from BibTeX's case change, by braces only. PURE.

    At brace level 0: a run of letters and digits holding an uppercase letter is braced, except
    that the field's first character (``field_start``) is printed as it is anyway; math holding
    an uppercase letter is braced; a group opening with a command (a BibTeX special character,
    whose letters BibTeX lowercases) and holding an uppercase letter is braced once more. An
    accent command with an unbraced capital letter, and a control word with a capital in its
    name (:func:`_case_unit_end`), are braced twice the same way: BibTeX lowercases them letter
    by letter (``\\latex`` is undefined), and once braced they would be a special character.
    Other groups are protected already and are left alone, and so are the other command names
    and the run such a command takes as its argument (bracing it would change the argument).
    """
    out: list[str] = []
    i, n = 0, len(value)
    after_command = False  # the next run may be the argument of the command just read
    while i < n:
        c = value[i]
        if c == "\\" and (m := _CONTROL_SEQ_RE.match(value, i)) is not None:
            end = _case_unit_end(value, m)
            if end is not None:
                unit = value[i:end]
                out.append("{{" + unit + "}}" if _ASCII_UPPER_RE.search(unit) else unit)
                after_command = False
                i = end
                continue
            out.append(m.group(0))
            symbol = m.group(0)[1:]
            after_command = symbol[:1].isalpha() or symbol in _ACCENT_SYMBOLS
            i = m.end()
            continue
        if c == "{":
            close = _group_close(value, i)
            group = value[i : close + 1]
            if group.startswith("{\\") and _ASCII_UPPER_RE.search(group):
                group = "{" + group + "}"
            out.append(group)
            after_command = False
            i = close + 1
            continue
        if c == "$":
            end = _math_end(value, i)
            math = value[i:end]
            out.append("{" + math + "}" if _ASCII_UPPER_RE.search(math) else math)
            after_command = False
            i = end
            continue
        m = _WORD_RUN_RE.match(value, i)
        if m is not None:
            run = m.group(0)
            upper = any(
                ch.isupper() for k, ch in enumerate(run) if not (field_start and i == 0 and k == 0)
            )
            out.append("{" + run + "}" if upper and not after_command else run)
            after_command = False
            i = m.end()
            continue
        out.append(c)
        if not c.isspace():
            after_command = False
        i += 1
    return "".join(out)


def _depth0_split(value: str, pattern: re.Pattern) -> list[str]:
    """``value`` split at the matches of ``pattern`` that lie at brace level 0, separators
    kept at the odd indices. PURE."""
    pieces: list[str] = []
    depth = 0
    last = 0
    i = 0
    while i < len(value):
        c = value[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 0 and (m := pattern.match(value, i)) is not None and m.end() > i:
            pieces += [value[last:i], m.group(0)]
            last = i = m.end()
            continue
        i += 1
    pieces.append(value[last:])
    return pieces


def _given_period(m: re.Match) -> str:
    """A given-name token without its stray period, or as it is (an initial, an abbreviation)."""
    words = m.group(1).split("-")
    last = words[-1]
    full_word = (
        all(w[0].isupper() and w[1:].islower() for w in words if w)
        and len(last) >= 3
        and last not in _GIVEN_NAME_ABBREVIATIONS
        and any(unicodedata.normalize("NFD", ch)[0] in _VOWELS for ch in last)
    )
    return m.group(1) if full_word else m.group(0)


def _tidy_given_names(name: str) -> str:
    """One name with the stray period after a full given name dropped (``Mackay, Donald.`` ->
    ``Mackay, Donald``; ``Donald. Mackay`` -> ``Donald Mackay``); initials keep theirs. The given
    part is what follows the last brace-level-0 comma, or every word but the last."""
    parts = _depth0_split(name, _COMMA_RE)
    if len(parts) > 1:
        return "".join(parts[:-1]) + _GIVEN_TOKEN_RE.sub(_given_period, parts[-1])
    words = _depth0_split(name, _SPACES_RE)
    if len(words) < 3:  # a single word is a family name
        return name
    given = "".join(words[:-2])
    return _GIVEN_TOKEN_RE.sub(_given_period, given) + "".join(words[-2:])


def _name_letter(cluster: str) -> str:
    """A non-ASCII letter of a name as the LaTeX BibTeX sorts by its base letter: accent
    commands for a letter with marks over an ASCII letter, a letter command for æ ø ł ß ...;
    anything else as it is."""
    if cluster.isascii():
        return cluster
    if cluster in _NAME_LETTER_CMD:
        return "{\\" + _NAME_LETTER_CMD[cluster] + "}"
    decomposed = unicodedata.normalize("NFD", cluster)
    if len(decomposed) > 1 and decomposed[0].isascii():
        latex = _accent_commands(decomposed[0], decomposed[1:])
        if latex is not None:
            return latex
    return cluster


def _tidy_names(value: str) -> str:
    """An author or editor value: each name's stray given-name period dropped, then its
    non-ASCII letters (outside math and verbatim arguments) written as LaTeX commands. PURE."""
    pieces = _depth0_split(value, _NAME_SEPARATOR_RE)
    value = "".join(p if k % 2 else _tidy_given_names(p) for k, p in enumerate(pieces))
    return "".join(
        "".join(_name_letter(c) for c in _clusters(text)) if kind == "text" else text
        for kind, text in _segments(value)
    )


def _starts_lowercase(word: str) -> bool:
    """True iff the first letter of ``word`` outside command names is a-z: BibTeX's test for a
    von word (it knows the case of ASCII letters only)."""
    m = _WORD_RUN_RE.search(_CONTROL_SEQ_RE.sub("", word))
    return m is not None and "a" <= m.group(0)[0] <= "z"


def raw_sort_letter(names: str) -> str | None:
    """The raw non-ASCII letter BibTeX sorts the first name of ``names`` (an author or editor
    value) by, or None. PURE.

    The natbib styles sort by the first name's von part, else its last name (``Last, First`` /
    ``von Last, First``: what precedes the first brace-level-0 comma; ``First von Last``: the
    first lowercase word but the last, else the last word), purified: braces dropped, a
    command reduced to ASCII letters or nothing. A raw non-ASCII letter there sorts after every
    ASCII letter, so the entry prints after the names that start with Z.
    """
    first = _depth0_split(names, _NAME_SEPARATOR_RE)[0].strip()
    parts = _depth0_split(first, _COMMA_RE)
    if len(parts) > 1:
        sort_part = parts[0]
    else:
        words = [w for w in _depth0_split(first, _SPACES_RE)[::2] if w]
        if not words:
            return None
        sort_part = next((w for w in words[:-1] if _starts_lowercase(w)), words[-1])
    for ch in sort_part:
        if ch == "\\":
            return None  # a command: purify$ leaves ASCII letters, or nothing
        if ch.isalnum():
            return None if ch.isascii() else ch
    return None


def sort_letter_command(letter: str) -> str | None:
    """The LaTeX for ``letter`` that BibTeX sorts by its base letter (what the reference-list
    copy writes in a name: ``Š`` -> ``{\\v{S}}``, ``Ø`` -> ``{\\O}``), or None when there is none
    (Ð Þ Đ Ŋ, whose T1 commands purify$ drops whole, and Ħ Ŧ Ŀ). PURE."""
    latex = _name_letter(letter)
    return None if latex == letter else latex


def _normalised_doi(doi: str) -> str:
    """A DOI without a leading ``doi:`` / doi.org prefix, percent-decoded, case-folded."""
    prefix = _DOI_PREFIX_RE.match(doi)
    return unquote(doi[prefix.end() :] if prefix else doi).strip().casefold()


def _repeats_doi(url: str, doi: str | None) -> bool:
    """True iff ``url`` is the doi.org / dx.doi.org link of ``doi`` (DOIs ignore case)."""
    m = _DOI_LINK_RE.fullmatch(url)
    return doi is not None and m is not None and _normalised_doi(m.group(1)) == _normalised_doi(doi)


def _present_entry(body: str) -> str:
    """One entry's fields (the text after ``@type{key,`` up to its closing brace) as the
    reference list should print them (see :func:`paper_bib`)."""
    fields = _fields(body)
    if not fields:
        return body
    doi = next(
        (body[f.parts[0][0] : f.parts[0][1]] for f in fields if f.name == "doi" and f.parts),
        None,
    )

    def omitted(field: _Field) -> bool:
        if field.name in _OMITTED_FIELDS:
            return True
        return (
            field.name == "url"
            and len(field.parts) == 1
            and _repeats_doi(body[field.parts[0][0] : field.parts[0][1]], doi)
        )

    def text(field: _Field) -> str:
        if field.name not in _CASE_FIELDS | _NAME_FIELDS:
            return body[field.start : field.end]
        out, pos = [], field.start
        for k, (start, end, delimited) in enumerate(field.parts):
            out.append(body[pos:start])
            value = body[start:end]
            if delimited:
                value = (
                    _protect_case(value, field_start=k == 0)
                    if field.name in _CASE_FIELDS
                    else _tidy_names(value)
                )
            out.append(value)
            pos = end
        out.append(body[pos : field.end])
        return "".join(out)

    # Each field keeps the separator written before it; the first field kept follows the
    # header's own spacing, and what follows the last field (the closing layout) is kept.
    out = [body[: fields[0].start]]
    first = True
    for k, field in enumerate(fields):
        if omitted(field):
            continue
        if not first:
            out.append(body[fields[k - 1].end : field.start])
        out.append(text(field))
        first = False
    out.append(body[fields[-1].end :])
    return "".join(out)


def _without_preambles(bib: str) -> str:
    """``bib`` without the ``@preamble`` commands BibTeX would act on (:func:`bib_commands`),
    from the ``@`` to where BibTeX stops reading each; repeated until none is left (taking one
    out could join text into another). PURE."""
    while preambles := [c for c in bib_commands(bib) if c.command == "preamble"]:
        out: list[str] = []
        pos = 0
        for command in preambles:
            out.append(bib[pos : command.start])
            pos = command.end
        out.append(bib[pos:])
        bib = "".join(out)
    return bib


# @MX:NOTE: [AUTO] What render writes into paper/ (references.bib and the SI subset); the store
# keeps the acquired bytes and its keys. Verify's bib check still passes on it.
def paper_bib(bib: str) -> str:
    """The bibliography a rendered paper loads: :func:`latex_safe_bib` of ``bib``, written for
    the reference list plainnat prints. PURE; keys never change; idempotent.

    Every ``@preamble`` is left out: BibTeX writes its text into the reference list as LaTeX
    (a reference needs none; one can define a macro or read a file).

    In every entry:

    - ``title`` and ``booktitle`` keep the casing the source gives (:func:`_protect_case`):
      "(BCF)", "OPERA models", "Connectivity III", "Matula numbers", "log Kow" print as
      acquired instead of lowercased, and so do an unbraced accented capital (``\\"Osterreich``)
      and a capitalised command (``\\LaTeX``, which lowercased is undefined);
    - ``issn`` is omitted, and so is a ``url`` that is the doi.org / dx.doi.org link of the
      entry's own ``doi`` (any other url stays; doi always stays);
    - in ``author`` and ``editor``, a full given name loses a stray period ("Mackay, Donald."
      -> "Mackay, Donald"; initials keep theirs), and a non-ASCII letter becomes LaTeX accent
      or letter commands, so BibTeX sorts it by its base letter (Šoškić with the S names).
      Ð Þ Đ Ŋ have no such command and stay raw (Ħ Ŧ fail verify's LaTeX-safety check; Ŀ is
      written L·); verify advises on a cited entry whose first author still sorts after Z
      (:func:`raw_sort_letter`).
    """
    safe = _without_preambles(latex_safe_bib(bib))
    out: list[str] = []
    pos = 0
    for m in _HEADER_RE.finditer(safe):
        if m.start() < pos:
            continue  # a header-shaped text inside an entry already read
        close = _value_end(safe, safe.index("{", m.start()))
        out.append(safe[pos : m.end()])
        out.append(_present_entry(safe[m.end() : close]))
        pos = close
    out.append(safe[pos:])
    return "".join(out)


__all__ = [
    "BibCommand",
    "MATH_ONLY_COMMANDS",
    "HTML_ENTITY_RE",
    "HTML_TAG_RE",
    "T1_ONLY_CHARS",
    "UNPRINTED_FIELDS",
    "VERBATIM_FIELDS",
    "accented_letters_in_math",
    "bare_specials",
    "bib_commands",
    "field_value_spans",
    "field_values",
    "html_tags",
    "latex_safe_bib",
    "math_commands_in_text",
    "paper_bib",
    "printed_field",
    "raw_sort_letter",
    "sort_letter_command",
    "stray_math_dollar",
    "string_macros_used_as_urls",
    "typesettable",
    "undefined_month_tokens",
    "untypesettable_chars",
    "url_arguments",
    "url_problems",
]
