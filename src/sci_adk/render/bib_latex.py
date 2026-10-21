"""
The bibliography a rendered paper loads, and which characters pdflatex can typeset.

Render copies the run's literature pool (``literature/references.bib``, as paperforge or a manual
ingest wrote it) into ``paper/references.bib`` and the cited-only ``paper/references_SI.bib``.
Registrar BibTeX (Crossref's metadata is XML-rooted) can carry HTML entities (``&amp;``), HTML
markup (``<i>K</i>``) and characters pdflatex cannot typeset (U+2212 MINUS SIGN), and a
hand-written or publisher bibliography any LaTeX at all. What render writes is
:func:`paper_bib`, the canonical copy (:func:`canonical_bib`): every entry BibTeX reads, as
``@type{key, field = {value}, ...}``, each value LaTeX-safe and holding only the commands on an
allow-list (:data:`TEXT_COMMANDS`, :data:`MATH_COMMANDS`), anything else printed as text; plus
the reference-list changes (title case kept as acquired, no ISSN or URL repeating the DOI, no
stray period after a given name, name letters BibTeX sorts by their base letter). Verify accepts
a shipped bibliography only when it is that copy (``pkgreqs_checks.bib_form_problems``), so the
copy and the check judge the same text. The pool itself is never rewritten here: its keys never
change and the merge keeps old entries verbatim (``search/literature_merge.py``).

:func:`latex_safe_bib` is the character and markup layer on its own, over a file as written
(layout, keys, field names and the text between entries copied as they are, a bare month name
BibTeX does not define written as its macro); the canonical copy applies the same conversion
to each value (:func:`_latex_safe_text`). In that layer:

- ``url`` and ``doi`` values are never escaped: plainnat prints them through ``\\url`` /
  ``\\Url``, which print a special character as itself, so an escape there prints its backslash
  (measured: ``AID\\_JBM1`` for ``\\_`` in a doi). XML's own escapes in them are decoded. They
  are NOT inert: hyperref reads a URL as TeX to make the link, so the canonical copy keeps a url
  only when it is plain (:func:`plain_url`) and a doi only in the DOI form, and verify fails a
  backslash, ``^^``, a brace or a ``run:`` / ``file:`` link in an author's url or doi value and in
  the URL argument of ``\\url`` / ``\\href`` (:func:`url_problems`).
- fields no BibTeX style prints (:data:`UNPRINTED_FIELDS`: ``abstract``, ``keywords``, ``file``,
  ``annote``, ``timestamp`` ... -- what Zotero, JabRef, Mendeley and BibDesk write) are left as
  acquired; the canonical copy leaves them out.

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

Commands (:func:`_allowed_value`): a value is read as TeX tokens; an allow-listed command is
kept with its arguments inside one brace group (BibTeX's case change cannot alter it), any
other control word or symbol is printed as text (``{\\textbackslash}name``), ``\\(...\\)`` and
``\\[...\\]`` become ``$...$``, and TeX's ``^^`` character-code notation never survives (math
``^^`` is written as two printed carets, in text a ``^`` is escaped anyway). Verify names what
the copy would print as text (:func:`command_issues`).

natbib's citation label (:func:`label_source`): ``[`` ``]`` at brace level 0 of every value, and
``(`` ``)`` at brace level 0 of an author, editor or key field, are braced; an entry plainnat
would label by three characters natbib cannot read gets a key field (:func:`unsafe_label`); a
year is plain text. An author's bibliography, not rewritten, is checked for the same shapes
(:func:`label_issues`) and for what BibTeX's case change would alter (:func:`case_change_issues`).

What BibTeX prints is read as BibTeX reads the file (:func:`bib_commands`): every ``@string``
value (printed wherever a field names the macro) and every ``@preamble`` (written into the
reference list as it is) as well as the entries, a parenthesised entry or ``@ article`` too. The
canonical copy expands every macro and leaves every ``@preamble`` out; verify fails one.

PURE (string in, string out): stdlib plus sibling render helpers, no I/O.
"""

from __future__ import annotations

import bisect
import functools
import html
import re
import unicodedata
from typing import Iterator, NamedTuple
from urllib.parse import unquote

from sci_adk.render.paper import (
    _ACCENT_HI,
    _UNDEFINED_LATIN_A,
    _UNICODE_MAP,
    _latex_escape,
    is_doi,
)

# An entry header ``@type{KEY,``. A value never runs past one unless its braces say so.
_HEADER_RE = re.compile(r"@\w+\s*\{\s*[^,\s}]+\s*,")

# A well-formed HTML entity (named, decimal or hex, ending in ';') not preceded by a backslash:
# ``\&amp;`` is LaTeX already -- an escaped ampersand followed by the letters "amp;".
# A numeric reference has at most 8 digits (the largest code point has 7): a longer one is text,
# never decoded (Python refuses to convert an integer of more than 4300 digits).
HTML_ENTITY_RE = re.compile(
    r"(?<!\\)&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]{1,8}|#[xX][0-9A-Fa-f]{1,8});"
)
# XML's predefined entities and numeric references: the only escapes XML-rooted metadata puts
# into a URL. Other entity-shaped text in a url or doi value is part of the URL.
_XML_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|#[0-9]{1,8}|#[xX][0-9A-Fa-f]{1,8});")

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
# An opening or closing tag of that markup; :func:`_convert_markup` pairs them in one pass.
_MARKUP_TAG_RE = re.compile(
    r"<(?P<close>/)?(?P<tag>" + "|".join(sorted(_MARKUP_CMD, key=len, reverse=True))
    + r")(?![\w:.-])(?(close)\s*|" + _TAG_ATTRS + r"\s*)>",
    re.IGNORECASE,
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
# ``\(`` opens math up to the next ``\)`` (found by :func:`_segments`, once, so a run of ``\(``
# with no partner is read in linear time).
_VALUE_SEGMENT_RE = re.compile(
    r"(?P<verbatim>" + _VERBATIM_ARG + r")"
    r"|(?P<math>\$\$.*?\$\$|(?<!\\)\$(?:[^$\\]|\\.)*\$)"
    r"|(?P<paren>\\\()",
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
_NOT_ENTITY = r"(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]{1,8}|#[xX][0-9A-Fa-f]{1,8});)"
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

# @MX:NOTE: [AUTO] An allow-list on purpose: a deny-list over the copy could not be closed (a
#   command split across '#' parts or @string macros, BibTeX's case change turning \INPUT into
#   \input, expl3, PDF actions ...). Each name here is compiled by a test with the preambles
#   render emits (Latin Modern without figures, Times with them; paper and record).
# The commands a value of the paper's bibliography may hold, by what they take in text mode
# (TEXT_COMMANDS) and in math (MATH_COMMANDS). Every other control word or symbol is printed as
# text by the copy (:func:`paper_bib`), and verify fails a bibliography that holds one.
# Accents written with a letter name (an accent written with a symbol, the acute or the umlaut,
# is handled as a control symbol); the cedilla, ogonek and comma below need T1, which every
# preamble loads.
_TEXT_ACCENT_WORDS = frozenset("c v H u k r d b t textcommabelow".split())
_TEXT_ACCENT_SYMBOLS = frozenset("'`^\"~=.")
# Letters with no accent (the dotless i and j, the Scandinavian, Polish and Icelandic letters).
_TEXT_LETTERS = frozenset(
    "i j o O l L ss SS ae AE oe OE aa AA dh DH th TH ng NG dj DJ".split()
)
# Text symbols publisher metadata carries and the copy itself writes; the TS1 ones are in the
# LaTeX kernel (the old textcomp package).
_TEXT_SYMBOLS = frozenset(
    "textbackslash textasciitilde textasciicircum textless textgreater textbraceleft "
    "textbraceright textbar textunderscore textdollar textendash textemdash textquoteleft "
    "textquoteright textquotedblleft textquotedblright textquotesingle textregistered "
    "texttrademark textcopyright copyright textdegree textperiodcentered textbullet "
    "textellipsis ldots dots dag ddag S P pounds textsection textparagraph textdagger "
    "textdaggerdbl guillemotleft guillemotright guilsinglleft guilsinglright quotedblbase "
    "quotesinglbase textexclamdown textquestiondown textmu textperthousand texttimes textpm "
    "textminus textdiv textcelsius textohm textonehalf textonequarter textthreequarters "
    "textnumero textcent textyen texteuro textflorin textordfeminine textordmasculine "
    "textonesuperior texttwosuperior textthreesuperior textsterling textleftarrow "
    "textrightarrow textuparrow textdownarrow LaTeX LaTeXe TeX space nobreakspace thinspace "
    "enspace quad qquad allowbreak slash".split()
)
# Markup that takes one text argument.
_TEXT_MARKUP = frozenset(
    "textit textbf textsc textrm textsf texttt textup textsl textmd textnormal emph "
    "textsuperscript textsubscript mbox underline".split()
)
# Font declarations (article.cls): each acts to the end of its group, so the copy writes one
# with the rest of its group inside one brace group.
_TEXT_DECLARATIONS = frozenset("em it bf sc rm sf tt sl normalfont".split())
# Math defined without amsmath (the figure-less preamble loads none): Greek, relations,
# operators, arrows, the named functions, styles and the font commands of the kernel.
_MATH_SYMBOLS = frozenset(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu "
    "xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta "
    "Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega "
    "pm mp times div cdot cdots vdots ddots ldots dots leq geq le ge neq ne approx sim simeq "
    "cong equiv propto ll gg infty partial nabla sum prod int oint surd prime circ to "
    "rightarrow leftarrow Rightarrow Leftarrow leftrightarrow Leftrightarrow longrightarrow "
    "longleftarrow uparrow downarrow mapsto rightleftharpoons in notin ni subset supset "
    "subseteq supseteq cup cap setminus emptyset forall exists neg lnot land lor wedge vee "
    "oplus otimes ominus odot langle rangle lfloor rfloor lceil rceil lbrace rbrace hbar ell "
    "Re Im aleph star ast dagger ddagger bullet perp parallel mid vert Vert backslash colon "
    "angle triangle diamond log ln lg exp sin cos tan cot sinh cosh tanh arcsin arccos "
    "arctan min max lim sup inf det dim ker deg arg gcd Pr quad qquad S P pounds dag ddag "
    "wp imath jmath top bot vdash dashv models smile frown asymp bowtie prec succ preceq "
    "succeq sqsubseteq sqsupseteq doteq leftharpoonup rightharpoonup hookrightarrow "
    "hookleftarrow nearrow searrow swarrow nwarrow Uparrow Downarrow updownarrow Updownarrow "
    "longmapsto Longrightarrow Longleftarrow Longleftrightarrow longleftrightarrow flat "
    "natural sharp clubsuit diamondsuit heartsuit spadesuit amalg uplus sqcap sqcup "
    "triangleleft triangleright bigtriangleup bigtriangledown oslash bigcirc wr coprod bigcap "
    "bigcup bigvee bigwedge bigoplus bigotimes bigodot biguplus bigsqcup".split()
)
_MATH_DECLARATIONS = frozenset(
    "rm it bf sf tt displaystyle textstyle scriptstyle scriptscriptstyle".split()
)
# \not is a symbol in the kernel but takes an argument in newtxmath (the figure preamble), and
# there it reads only one plain symbol: anything else stopped pdflatex (nothing after it, an
# empty group, a box, a command with arguments: "TeX capacity exceeded"). The copy keeps \not
# only before one character of _NOT_CHARS or one "zero" math command (each compiled after \not
# by a test under both typefaces), written \not{X}; any other \not is printed as text.
_MATH_ONE_ARG = frozenset(
    "sqrt mathrm mathit mathbf mathsf mathtt mathcal hat bar tilde vec dot ddot check breve "
    "acute grave mathring widehat widetilde overline underline overrightarrow "
    "overleftarrow not".split()
)
_MATH_TWO_ARGS = frozenset({"frac"})
_NOT_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789=<>|+-:/()[]!"
)
# The math font declarations that are assignments (\fam), not items of the math list: a script
# after one still belongs to the atom before it (x^2\rm^3 is a double superscript).
_FONT_ASSIGNMENTS = frozenset("rm it bf sf tt".split())

# @MX:ANCHOR: [AUTO] The allow-list: what the copy keeps, what verify accepts, and what the
#   compile test proves defined -- one set for all three.
# @MX:REASON: callers: _Writer here (the copy and the verify-side judge), pkgreqs_checks
#   (bib_command_problems through command_issues), tests/test_bib_allowlist.py (compiles each
#   name under four preambles); a name added without the test may be undefined in one of them.
#: Control words a text-mode bib value may hold, by kind: ``zero`` (no argument), ``accent``
#: and ``one`` (one text argument), ``declaration`` (acts to the end of its group), ``url``,
#: ``href`` (a plain URL argument, see :func:`plain_url`) and ``math`` (``\\ensuremath``).
TEXT_COMMANDS: dict[str, str] = {
    **{name: "accent" for name in _TEXT_ACCENT_WORDS},
    **{name: "zero" for name in _TEXT_LETTERS | _TEXT_SYMBOLS},
    **{name: "one" for name in _TEXT_MARKUP},
    **{name: "declaration" for name in _TEXT_DECLARATIONS},
    "url": "url",
    "href": "href",
    "ensuremath": "math",
}
#: Control words a math-mode value may hold: ``zero``, ``one`` and ``two`` (math arguments;
#: ``\\sqrt`` also takes ``[n]``), ``declaration``, ``text`` (``\\mbox``: a text argument) and
#: ``math`` (``\\ensuremath``). A text command in math is written inside an ``\\mbox``.
MATH_COMMANDS: dict[str, str] = {
    **{name: "zero" for name in _MATH_SYMBOLS},
    **{name: "declaration" for name in _MATH_DECLARATIONS},
    **{name: "one" for name in _MATH_ONE_ARG},
    **{name: "two" for name in _MATH_TWO_ARGS},
    "mbox": "text",
    "ensuremath": "math",
}
# The math commands pdflatex does not take as a superscript or subscript argument without
# braces ("Missing { inserted": x^\hat{y}, x^\cdots, x_\log, x^\rm 2), measured as $x^\name$ and
# $x_\name$ (with {a} or {a}{b} after a command that takes arguments) under both preambles
# render emits; \cong \doteq \notin \rightleftharpoons stop only under Latin Modern, the big
# operators \colon \not only under Times. Every other MATH_COMMANDS name compiled unbraced (\alpha,
# \prime, \mathrm{T}, \frac{1}{2}); a test pins both sides. The copy braces every script argument
# anyway; an author's bibliography fails on these (script_issues).
_SCRIPT_UNSAFE = frozenset(
    "Longrightarrow Pr acute arccos arcsin arctan arg bar bf bowtie breve cdots check cong cos "
    "cosh cot ddot ddots deg det dim displaystyle dot doteq dots exp gcd grave hat inf int it "
    "ker ldots lg lim ln log longrightarrow mathring max mbox min models notin oint "
    "overleftarrow overline overrightarrow qquad quad rightleftharpoons rm scriptscriptstyle "
    "scriptstyle sf sin sinh sqrt sup tan tanh textstyle tilde tt underline vdots vec widehat "
    "widetilde bigcap bigcup bigodot bigoplus bigotimes bigsqcup biguplus bigvee bigwedge colon "
    "coprod not prod sum".split()
)
# The control symbols and characters pdflatex takes as a script argument without braces
# (measured: x^\{ x^\| x^\& x^\_ x^\$ x^- x^( compile; x^\, x^\; x^~ x^' and a letter outside
# ASCII, which inputenc makes a command, stop).
_UNBRACED_SCRIPT_SYMBOLS = frozenset("{}|&%#_$")
_UNBRACED_SCRIPT_BAD_CHARS = frozenset("~'$&#%^_")
# The control symbols kept as they are: the escaped specials in text and math, and the math
# spaces and the double bar in math.
_TEXT_ESCAPED_SYMBOLS = frozenset("&%$#_")
_MATH_KEPT_SYMBOLS = frozenset("&%$#_,;:!|")
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
    if category in ("Zs", "Zl", "Zp"):  # a space, a line or a paragraph separator
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
    """``text`` with each pair of markup tags (:data:`_MARKUP_CMD`) as its command: a closing
    tag closes the innermost open tag of its name (``<i>a<i>b</i>c</i>`` ->
    ``\\textit{a\\textit{b}c}``); a tag with no partner is left (and stripped later). One pass
    over the tags, so a run of unclosed tags is read in linear time."""
    tags = list(_MARKUP_TAG_RE.finditer(text))
    if not tags:
        return text
    open_tags: dict[str, list[int]] = {}
    partner: dict[int, int] = {}
    for k, m in enumerate(tags):
        name = m.group("tag").lower()
        if m.group("close") is None:
            open_tags.setdefault(name, []).append(k)
        elif open_tags.get(name):
            opened = open_tags[name].pop()
            partner[opened] = k
            partner[k] = opened
    out: list[str] = []
    pos = 0
    for k, m in enumerate(tags):
        if k not in partner:
            continue
        out.append(text[pos : m.start()])
        if m.group("close") is None:
            out.append("\\" + _MARKUP_CMD[m.group("tag").lower()] + "{")
        else:
            out.append("}")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _segments(value: str) -> Iterator[tuple[str, str]]:
    """``(kind, text)`` pieces of one field value, in order; ``kind`` is ``"text"``,
    ``"math"`` or ``"verbatim"`` (an argument typeset verbatim, ``\\url{...}``)."""
    pos = search = 0
    closer = -2  # the next "\)" at or after the last search (-1: there is none)
    while (m := _VALUE_SEGMENT_RE.search(value, search)) is not None:
        start, end = m.span()
        if m.group("paren"):
            if closer != -1 and closer < end:
                closer = value.find("\\)", end)
            if closer == -1:  # no partner, nor for any later "\(": text
                search = end
                continue
            end = closer + 2
        if start > pos:
            yield "text", value[pos:start]
        yield ("verbatim" if m.group("verbatim") else "math"), value[start:end]
        pos = search = end
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


def caret_notation(value: str) -> bool:
    """True iff the text or math of ``value`` holds ``^^``: TeX reads ``^^`` and what follows as
    another character (``^^5c`` is a backslash, ``^^e`` a ``%``) wherever ``^`` is a
    superscript character, so it can spell a command no scan of backslashes sees. A verbatim
    argument (``\\url{...}``) is not read. PURE."""
    return any(kind != "verbatim" and "^^" in text for kind, text in _segments(value))


# -- a value as TeX reads it, and the allow-list ----------------------------------------------------
#
# A value is read into TeX tokens (_tex_tokens): control words (``\\name``, the spaces after it
# skipped as TeX skips them), control symbols (``\\'``, ``\\&``, ``\\\\``), brace groups (TeX's
# braces: ``\\{`` is a symbol, not a brace), white space runs and characters. _Writer writes
# them back: a command on the allow-list with its arguments, anything else as text. The same
# walk is the copy (paper_bib) and the verify-side judge (command_issues): what the copy would
# print as text is what verify names.

_TEX_SPACE = frozenset(" \t\n\r")
# The control symbols in text that are spacing hints and are left out (an italic correction or
# a space factor setting at the start of a paragraph stops pdflatex).
_DROPPED_SYMBOLS = frozenset("/@")
# A plain URL: a scheme the reference list may link to, then printable ASCII without white
# space, a backslash, a brace, % (TeX's comment), # (its parameter character) or ^ (its
# character-code notation) -- hyperref reads a URL as TeX to make the link.
_PLAIN_URL_RE = re.compile(r"(?:https?|ftp)://(?:(?![\\{}%#^])[!-~])+", re.IGNORECASE)
_BACKSLASH_TEXT = "{\\textbackslash}"

# @MX:WARN: [AUTO] Limits measured with TeX Live 2026; lowering one is safe, raising one is not.
# @MX:REASON: TeX has 255 grouping levels (braces 254 deep stopped pdflatex); each nested text
#   accent doubles pdflatex's time (22 deep took 17 s, a 100-byte title stopped a render);
#   TeX's input buffer holds 200000 characters and BibTeX breaks a .bbl line only at a space
#   (a 240000-character word stopped pdflatex); BibTeX's string pool holds 200000 characters
#   per value. The writer recurses once per brace level, so the depth also bounds the stack.
#   hyperref keeps at most 10 links open ("pdf link stack size=10"); a \sqrt with an index and
#   the arrow accents typeset their argument four times (\mathpalette): \sqrt[3] 12 deep took
#   over 120 s a pass, \overrightarrow 10 deep 39 s, 49 deep ran out of grouping levels;
#   \textsuperscript about 37 deep shrank the type to "Improper `at' size"; 4700 arrow accents
#   in one reference took 24 s a pass (1000: 0.6 s; the time grows faster than their number).
_MAX_DEPTH = 50
_MAX_ACCENTS = 3
_MAX_WORD = 10000
_MAX_FIELD = 100000
# Math commands with arguments open around one another, text markup open around one another,
# and math commands with arguments in one value; links open around one another is at most one.
_MAX_MATH_NESTING = 4
_MAX_TEXT_NESTING = 8
_MAX_MATH_WRAPPERS = 32
#: The math commands that take arguments (\\not, which takes one symbol, aside): what they take
#: is typeset one level deeper.
_MATH_WRAPPERS = frozenset(n for n, k in MATH_COMMANDS.items() if k in ("one", "two")) - {"not"}
_ARROW_ACCENTS = frozenset({"overrightarrow", "overleftarrow"})
_LINK_KINDS = frozenset({"url", "href"})
_LINK_IN_LINK = (
    "a link command (\\href, \\url) inside another link (hyperref keeps at most 10 open; the "
    "inner one is printed as text)"
)
_MATH_DEEP = (
    f"math commands with arguments nested more than {_MAX_MATH_NESTING} deep (an arrow accent or "
    "a root with an index typesets its argument four times, so pdflatex's time grows fourfold "
    "with each level; the deeper ones are printed as text)"
)
_ROOT_IN_ROOT = (
    "a \\sqrt with an index inside another \\sqrt (each typesets its argument four times; the "
    "inner one is printed as text)"
)
_ARROW_IN_ARROW = (
    "an arrow accent (\\overrightarrow, \\overleftarrow) inside another arrow accent (each "
    "typesets its argument four times; the inner one is printed as text)"
)
_TEXT_DEEP = (
    f"text markup nested more than {_MAX_TEXT_NESTING} deep (\\textsuperscript and "
    "\\textsubscript make the type smaller at each level until pdflatex stops; the deeper ones "
    "are printed as text)"
)
_MATH_MANY = (
    f"more than {_MAX_MATH_WRAPPERS} math commands with arguments in one value (pdflatex's time "
    "grows faster than their number; the rest are printed as text)"
)
# What the caps above print as text: noted, and never a reason to keep a math command in running
# text out of math (the cap applies there just the same).
_CAP_NOTES = frozenset(
    {_LINK_IN_LINK, _MATH_DEEP, _ROOT_IN_ROOT, _ARROW_IN_ARROW, _TEXT_DEEP, _MATH_MANY}
)
# What the copy rewrites in a script so that it compiles (script_issues): an author's
# bibliography fails on each.
_DOUBLE_SCRIPT = (
    "a second superscript or subscript on one base ('Double superscript'; the copy gives it an "
    "empty base, {})"
)
_EMPTY_SCRIPT = "a superscript or subscript with nothing after it (the copy writes ^{} or _{})"
_UNBRACED_SCRIPT = (
    "a superscript or subscript argument pdflatex takes only in braces ('Missing { inserted': "
    "x^\\hat{y}, x^\\rm 2, a letter outside ASCII; the copy braces it)"
)
#: The longest value the copy and verify read as BibTeX joins it (BibTeX's string pool holds
#: 200000 characters; a chain of @string macros each doubling the last reached 2**27 * 4).
MAX_EXPANDED = 2 * _MAX_FIELD
_MAX_URL = 4000
_TOO_DEEP = f"braces nested more than {_MAX_DEPTH} deep (the copy writes the value empty)"
_ACCENTS_DEEP = (
    f"accents nested more than {_MAX_ACCENTS} deep (pdflatex's time doubles with each; the "
    "deeper ones are printed as text)"
)


def plain_url(url: str) -> bool:
    """True iff ``url`` is a URL the copy keeps (:data:`_PLAIN_URL_RE`, at most
    :data:`_MAX_URL` characters). PURE."""
    return len(url) <= _MAX_URL and _PLAIN_URL_RE.fullmatch(url) is not None


def _tex_tokens(text: str) -> tuple[list, bool, int]:
    """``text`` as TeX tokens, whether its braces were unbalanced in TeX's reading (a ``}``
    with no group open is dropped, a group left open is closed at the end), and how deep its
    groups nest. A token is ``("w", name)``, ``("s", character)`` (``""``: a backslash ending
    the text), ``("g", tokens)``, ``(" ",)`` or ``("c", character)``."""
    root: list = []
    stack = [root]
    unbalanced = False
    deepest = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            if i + 1 >= n:
                stack[-1].append(("s", ""))
                i += 1
                continue
            d = text[i + 1]
            if d.isascii() and d.isalpha():
                j = i + 1
                while j < n and text[j].isascii() and text[j].isalpha():
                    j += 1
                stack[-1].append(("w", text[i + 1 : j]))
                while j < n and text[j] in _TEX_SPACE:
                    j += 1  # TeX skips the spaces after a control word
                i = j
            else:
                stack[-1].append(("s", d))
                i += 2
        elif c == "{":
            child: list = []
            stack[-1].append(("g", child))
            stack.append(child)
            deepest = max(deepest, len(stack) - 1)
            i += 1
        elif c == "}":
            if len(stack) > 1:
                stack.pop()
            else:
                unbalanced = True
            i += 1
        elif c in _TEX_SPACE:
            while i < n and text[i] in _TEX_SPACE:
                i += 1
            if not stack[-1] or stack[-1][-1][0] != " ":
                stack[-1].append((" ",))
        else:
            stack[-1].append(("c", c))
            i += 1
    return root, unbalanced or len(stack) > 1, deepest


def _plain_text(latex: str, keep) -> str:
    """The characters of ``latex`` that ``keep`` accepts, read as TeX reads them (inside groups
    and command arguments too; command names left out), white space runs as one space and the
    ends trimmed. PURE."""
    out: list[str] = []
    stack = [iter(_tex_tokens(latex)[0])]
    while stack:
        tok = next(stack[-1], None)
        if tok is None:
            stack.pop()
        elif tok[0] == "g":
            stack.append(iter(tok[1]))
        elif tok[0] == " ":
            out.append(" ")
        elif tok[0] == "c" and keep(tok[1]):
            out.append(tok[1])
    return " ".join("".join(out).split())


def _join(out: list[str], piece: str) -> None:
    """Append ``piece``, with a space when it starts with a letter or digit right after a
    control word (``\\alpha x``, never the undefined ``\\alphax``; ``\\geq 3`` as written --
    TeX skips the space after a control word, so it changes nothing)."""
    if not piece:
        return
    if out and piece[0].isascii() and piece[0].isalnum() and _CONTROL_WORD_END_RE.search(out[-1]):
        out.append(" ")
    out.append(piece)


def _next_arg(toks: list, j: int) -> tuple[list, int] | None:
    """The argument TeX reads at ``toks[j]`` (spaces skipped): a group's tokens or one token,
    and the index after it; None when nothing follows."""
    while j < len(toks) and toks[j][0] == " ":
        j += 1
    if j >= len(toks):
        return None
    tok = toks[j]
    return (tok[1] if tok[0] == "g" else [tok]), j + 1


def _plain_chars(toks: list) -> str | None:
    """The text of ``toks`` when it is characters only (a URL argument), else None."""
    if all(tok[0] == "c" for tok in toks):
        return "".join(tok[1] for tok in toks)
    return None


def _wrap(text: str, wrap: bool) -> str:
    return "{" + text + "}" if wrap else text


def _printed_name(name: str, text_char) -> str:
    """The name of a control word or symbol as text (``~`` as a tilde, not a tie)."""
    if name == "~":
        return "{\\textasciitilde}"
    return "".join(text_char(c, True) for c in name)


def _unwrapped(toks: list) -> list:
    """``toks`` without the brace pairs around all of it (white space beside a group ignored):
    ``{{}}`` -> nothing, ``{{x}}`` -> ``x``; ``toks`` itself when there are none."""
    out = toks
    while True:
        solid = [tok for tok in out if tok[0] != " "]
        if len(solid) != 1 or solid[0][0] != "g":
            return out
        out = solid[0][1]


def _not_operand(toks: list, j: int) -> tuple[str, int] | None:
    """What ``\\not`` at ``toks[j - 1]`` may be kept with: one character of :data:`_NOT_CHARS`
    or one ``zero`` math command, alone or alone in a group, as ``(LaTeX, index after it)``;
    None for anything else (see :data:`_MATH_ONE_ARG`)."""
    arg = _next_arg(toks, j)
    if arg is None:
        return None
    solid = [tok for tok in arg[0] if tok[0] != " "]
    if len(solid) != 1:
        return None
    tok = solid[0]
    if tok[0] == "c" and tok[1] in _NOT_CHARS:
        return tok[1], arg[1]
    if tok[0] == "w" and MATH_COMMANDS.get(tok[1]) == "zero":
        return "\\" + tok[1], arg[1]
    return None


def _unbraced_script_ok(tok: tuple) -> bool:
    """True iff pdflatex takes ``tok`` as a superscript or subscript argument without braces
    (see :data:`_SCRIPT_UNSAFE`)."""
    if tok[0] == "c":
        return (tok[1].isascii() and tok[1] not in _UNBRACED_SCRIPT_BAD_CHARS
                and typesettable(tok[1]))
    if tok[0] == "s":
        return tok[1] in _UNBRACED_SCRIPT_SYMBOLS
    if tok[0] == "w":
        return tok[1] in MATH_COMMANDS and tok[1] not in _SCRIPT_UNSAFE
    return False


def _excess_wrappers(tokens: list) -> frozenset[int]:
    """The ids of the math commands with arguments (:data:`_MATH_WRAPPERS`) after the first
    :data:`_MAX_MATH_WRAPPERS` of a value, in reading order: the writer prints each as text.
    Marked on the tokens before the walk, so what the writer remembers stays valid."""
    count = 0
    excess: set[int] = set()
    stack = [iter(tokens)]
    while stack:
        tok = next(stack[-1], None)
        if tok is None:
            stack.pop()
        elif tok[0] == "g":
            stack.append(iter(tok[1]))
        elif tok[0] == "w" and tok[1] in _MATH_WRAPPERS:
            count += 1
            if count > _MAX_MATH_WRAPPERS:
                excess.add(id(tok))
    return frozenset(excess)


def _holds_command(toks: list) -> bool:
    return any(tok[0] in ("w", "s") or (tok[0] == "g" and _holds_command(tok[1]))
               for tok in toks)


def _composite_safe(body: str) -> bool:
    """True iff an accent with the argument ``body`` (as written) compiles: LaTeX's T1 accents
    look its first item up as ``\\csname\\string<first token of the item>...\\endcsname``
    (``ltoutenc``), so an item that is an empty group stops pdflatex (``\\string`` takes
    ``\\endcsname``: "Missing \\endcsname inserted"), and so does a group holding a command
    after its first token (the command is expanded inside the ``\\csname``). Measured for
    every accent under both typefaces: ``{}``, ``e``, ``{e}``, ``{e}f``, ``{\\'{e}}``, ``\\i``
    compile; ``{{}}``, `` {}``, ``{}{}``, ``{{\\textbackslash}foo}`` stop."""
    toks = [tok for tok in _tex_tokens(body)[0] if tok[0] != " "]
    if not toks or toks[0][0] != "g":
        return True
    item = toks[0][1]
    if not item:
        return False
    rest = item if item[0][0] == "g" else item[1:]
    return not _holds_command(rest)


class _Writer:
    """Writes TeX tokens back keeping only allow-listed commands; collects what it printed as
    text (:attr:`issues`, each named once by :func:`command_issues`), what it moved into the
    mode its command needs (:attr:`fixes`) and the characters pdflatex has no form of
    (:attr:`unset`: kept as they are, so a reference never silently loses a letter; render
    warns and verify fails each).

    The walk stays linear: a group's or an argument's tokens are written once and remembered
    (the copy tries a group as one unit before it writes it as a sequence, which would
    otherwise redo every level below it), and where math closes is found once per token list.
    """

    def __init__(self, label: bool = False) -> None:
        # A field natbib reads into a citation label (author, editor, key): its '(' and ')'
        # at brace level 0 are braced, as '[' and ']' are in every field.
        self.label = label
        self.issues: list[str] = []
        # What the copy changed so a value compiles (a math command in running text put in
        # math, a text command in math boxed): fine in the copy, a stop in an author's file.
        self.fixes: list[str] = []
        self.unset: list[str] = []
        # What it rewrote in a script so that it compiles (a second script on one base, a script
        # with nothing to take, an argument TeX takes only braced): see script_issues.
        self.scripts: list[str] = []
        self.accents = 0  # text accents open around the item being written
        self.links = 0  # links open around it (at most one: a link inside is printed as text)
        self.math_depth = 0  # math commands with arguments open around it
        self.text_depth = 0  # text markup open around it
        self.in_arrow = False  # inside an arrow accent
        self.in_root = False  # inside a \sqrt
        # The math commands past the per-value cap (_excess_wrappers), by id.
        self.excess: frozenset[int] = frozenset()
        self._memo: dict = {}
        self._positions: dict = {}

    def _mark(self) -> tuple[int, int, int, int]:
        return len(self.issues), len(self.fixes), len(self.unset), len(self.scripts)

    def _rollback(self, mark: tuple[int, int, int, int]) -> None:
        del self.issues[mark[0] :]
        del self.fixes[mark[1] :]
        del self.unset[mark[2] :]
        del self.scripts[mark[3] :]

    def _state(self) -> tuple:
        """What a group or an argument is written under, besides its tokens and mode."""
        return (self.accents, self.links, self.math_depth, self.text_depth, self.in_arrow,
                self.in_root)

    def _remember(self, kind: str, toks: list, mode: str, write) -> str:
        """``write()``'s result for ``toks``, computed once (what it noted is noted again on
        every reuse). The token list is kept with the result, so its id cannot be reused."""
        key = (kind, id(toks), mode, self._state())
        hit = self._memo.get(key)
        if hit is not None and hit[0] is toks:
            self.issues += hit[2]
            self.fixes += hit[3]
            self.unset += hit[4]
            self.scripts += hit[5]
            return hit[1]
        mark = self._mark()
        out = write()
        self._memo[key] = (toks, out, self.issues[mark[0] :], self.fixes[mark[1] :],
                           self.unset[mark[2] :], self.scripts[mark[3] :])
        return out

    def _as_text(self, name: str, note: str, mode: str) -> str:
        """The command ``name`` printed as text (boxed in math) because a cap stopped it,
        noted once with ``note``; what follows it is written next, as it stands."""
        self.issues.append(note)
        text = _BACKSLASH_TEXT + _printed_name(name, self.text_char)
        return _box(text) if mode == "math" else text

    def _capped_text(self, name: str) -> str | None:
        """The cap note when the text command ``name`` may not be kept here: a link inside a
        link, text markup past :data:`_MAX_TEXT_NESTING`; else None."""
        kind = TEXT_COMMANDS.get(name)
        if kind in _LINK_KINDS and self.links:
            return _LINK_IN_LINK
        if kind == "one" and self.text_depth >= _MAX_TEXT_NESTING:
            return _TEXT_DEEP
        return None

    def _root_index(self, toks: list, i: int) -> tuple[int, int] | None:
        """``(start, end)`` of the index of the ``\\sqrt`` at ``toks[i]`` (``[n]``), or None."""
        k = i + 1
        while k < len(toks) and toks[k][0] == " ":
            k += 1
        if k < len(toks) and toks[k] == ("c", "["):
            end = self._next_at(toks, k + 1, ("c", "]"))
            if end is not None:
                return k + 1, end
        return None

    def _capped_math(self, toks: list, i: int) -> str | None:
        """The cap note when the math command with arguments at ``toks[i]`` may not be kept
        here: past the per-value count, past :data:`_MAX_MATH_NESTING`, an arrow accent inside
        an arrow accent, a root with an index inside a root; else None."""
        tok = toks[i]
        if id(tok) in self.excess:
            return _MATH_MANY
        if self.math_depth >= _MAX_MATH_NESTING:
            return _MATH_DEEP
        if tok[1] in _ARROW_ACCENTS and self.in_arrow:
            return _ARROW_IN_ARROW
        if tok[1] == "sqrt" and self.in_root and self._root_index(toks, i) is not None:
            return _ROOT_IN_ROOT
        return None

    def _enter(self, name: str) -> tuple:
        """Open the math command ``name`` around what is written next; returns what
        :meth:`_leave` restores."""
        saved = (self.math_depth, self.in_arrow, self.in_root)
        self.math_depth += 1
        self.in_arrow = self.in_arrow or name in _ARROW_ACCENTS
        self.in_root = self.in_root or name == "sqrt"
        return saved

    def _leave(self, saved: tuple) -> None:
        self.math_depth, self.in_arrow, self.in_root = saved

    def _next_at(self, toks: list, start: int, close: tuple, width: int = 1) -> int | None:
        """The first index ``j >= start`` where ``width`` tokens equal to ``close`` begin, or
        None; the places are found once per token list."""
        key = (id(toks), close, width)
        entry = self._positions.get(key)
        if entry is None or entry[0] is not toks:
            found = [j for j in range(len(toks) - width + 1)
                     if all(toks[j + k] == close for k in range(width))]
            entry = (toks, found)
            self._positions[key] = entry
        found = entry[1]
        k = bisect.bisect_left(found, start)
        return found[k] if k < len(found) else None

    def _printed(self, name: str, mode: str) -> str:
        """The control word or symbol ``name`` printed as text (boxed in math), noted."""
        self.issues.append("\\" + name)
        text = _BACKSLASH_TEXT + _printed_name(name, self.text_char)
        return _box(text) if mode == "math" else text

    # -- sequences and groups

    def seq(self, toks: list, mode: str, top: bool, field: bool = False) -> str:
        out: list[str] = []
        scripts = ""  # in math: the scripts the current base carries ("^", "_")
        after_prime = False
        i, n = 0, len(toks)
        while i < n:
            tok = toks[i]
            kind = tok[0]
            if kind == " ":
                out.append(" ")
                after_prime = False  # TeX joins a prime and what follows only when adjacent
                i += 1
                continue
            if mode == "math" and kind == "c" and tok[1] in "^_'":
                piece, i, scripts = self._script(toks, i, scripts, after_prime)
                after_prime = tok[1] == "'"
                _join(out, piece)
                continue
            if kind == "g":
                piece = self.group(tok[1], mode)
                i += 1
            elif mode == "math":
                piece, i = self.math_item(toks, i)
            else:
                piece, i = self.text_item(toks, i, top, field)
            if mode == "math" and kind == "w" and tok[1] in _FONT_ASSIGNMENTS:
                after_prime = False  # no atom: a script after it is on the same base
            elif mode != "math" or piece.strip():
                scripts, after_prime = "", False  # an atom (a dropped token is none)
            _join(out, piece)
        return "".join(out)

    def _single_unit(self, toks: list, mode: str) -> str | None:
        """``toks`` written as the one unit they are (a kept command and its arguments, or
        math), without the braces the copy puts around a unit, or None when they are not one:
        the braces around them already make it one special character for BibTeX."""
        if mode == "text" and toks:
            mark = self._mark()
            piece, j = self.text_item(toks, 0, top=False, field=False, unit=True)
            if piece is not None and j == len(toks):
                return piece
            self._rollback(mark)
        return None

    def group(self, toks: list, mode: str) -> str:
        return self._remember("group", toks, mode, lambda: self._group(toks, mode))

    def _group(self, toks: list, mode: str) -> str:
        piece = self._single_unit(toks, mode)
        return "{" + (piece if piece is not None else self.seq(toks, mode, top=True)) + "}"

    def arg(self, toks: list, mode: str) -> str:
        """A command's argument (the braces are the caller's)."""
        return self._remember("arg", toks, mode, lambda: self._arg(toks, mode))

    def _arg(self, toks: list, mode: str) -> str:
        piece = self._single_unit(toks, mode)
        return piece if piece is not None else self.seq(toks, mode, top=False)

    def math_arg(self, toks: list) -> str:
        """Math tokens (an argument, a script's group, the body of math)."""
        return self._remember("math", toks, "math", lambda: self.seq(toks, "math", top=False))

    def _math(self, toks: list, wrap: bool) -> str:
        """Math written as ``$...$`` (braced when ``wrap``), or nothing when it is empty: an
        empty ``$$`` opens display math."""
        body = self.math_arg(toks)
        return _wrap("$" + body + "$", wrap) if body.strip() else ""

    # -- text mode

    def text_char(self, ch: str, field: bool) -> str:
        if ch in "&%#_":
            return "\\" + ch
        if ch == "^":
            return "{\\textasciicircum}"
        if ch == "<":
            return "{\\textless}"
        if ch == ">":
            return "{\\textgreater}"
        if ch in "[]" and field:
            return "{" + ch + "}"  # natbib reads a label up to the first ] at brace level 0
        if ch in "()" and field and self.label:
            return "{" + ch + "}"  # ... and its names up to the first ( at brace level 0
        if ch.isascii():
            return ch if typesettable(ch) else ""
        if typesettable(ch):
            return ch
        return self._converted(ch, False)

    def _converted(self, ch: str, math: bool) -> str:
        """A character pdflatex has no glyph for as it stands: its LaTeX form, or the
        character itself (noted in :attr:`unset`)."""
        form = _char_to_latex(ch, math)
        if form != ch and all(typesettable(c) for c in form):
            return form
        self.unset.append(ch)
        return ch

    def _math_span(self, toks: list, i: int, close: tuple, width: int) -> tuple[int, int] | None:
        """(end of the math tokens, index after the closing delimiter) for math opening at
        ``toks[i]`` and closed by ``width`` tokens equal to ``close`` at the same level."""
        j = self._next_at(toks, i + width, close, width)
        return None if j is None else (j, j + width)

    def text_item(self, toks: list, i: int, top: bool, field: bool, unit: bool = False):
        """One item of a text sequence: ``(LaTeX, index after it)``. With ``unit`` the item
        must be one the copy braces (a kept command and its arguments, or math), written
        without those braces; ``(None, i)`` when it is not."""
        tok = toks[i]
        wrap = top and not unit
        kind = tok[0]
        if kind in ("g", " "):
            return None, i  # a group or a space is no unit (seq writes them itself)
        if kind == "c":
            ch = tok[1]
            if ch == "$":
                display = i + 1 < len(toks) and toks[i + 1] == ("c", "$")
                span = self._math_span(toks, i, ("c", "$"), 2 if display else 1)
                if span is not None:
                    start = i + (2 if display else 1)
                    return self._math(toks[start : span[0]], wrap), span[1]
                if unit:
                    return None, i
                return "\\$", i + 1
            if unit:
                return None, i
            return self.text_char(ch, field), i + 1
        if kind == "s":
            return self._text_symbol(toks, i, wrap, unit)
        return self._text_word(toks, i, wrap, unit)

    def _text_symbol(self, toks: list, i: int, wrap: bool, unit: bool):
        ch = toks[i][1]
        if ch in _TEXT_ACCENT_SYMBOLS:
            return self._accent(toks, i, ch, wrap, unit)
        if ch in "([":
            span = self._math_span(toks, i, ("s", ")" if ch == "(" else "]"), 1)
            if span is not None:
                return self._math(toks[i + 1 : span[0]], wrap), span[1]
        if ch == "|":
            self.fixes.append("\\| in running text")
            return _wrap("$\\|$", wrap), i + 1
        if unit:
            if ch in "{}":
                return "\\textbrace" + ("left" if ch == "{" else "right"), i + 1
            if ch in ",-":
                return "\\" + ch, i + 1
            return None, i
        if ch in _TEXT_ESCAPED_SYMBOLS:
            return "\\" + ch, i + 1
        if ch in "{}":
            return "{\\textbrace" + ("left" if ch == "{" else "right") + "}", i + 1
        if ch in ",-":
            return "{\\" + ch + "}", i + 1
        if ch in _TEX_SPACE or ch == "\\":
            return " ", i + 1  # a control space or a line break: a space
        if ch in _DROPPED_SYMBOLS:
            return "", i + 1
        return self._printed(ch, "text"), i + 1

    def _accent(self, toks: list, i: int, name: str, wrap: bool, unit: bool):
        arg = _next_arg(toks, i + 1)
        if arg is None:
            return (None, i) if unit else (self._printed(name, "text"), i + 1)
        if self.accents >= _MAX_ACCENTS:
            if unit:
                return None, i
            # Printed as text; its argument is written next, at this depth, so any accent in
            # it is printed as text too.
            self.issues.append(_ACCENTS_DEEP)
            return _BACKSLASH_TEXT + _printed_name(name, self.text_char), i + 1
        mark = self._mark()
        self.accents += 1
        try:
            body = self._accent_body(arg[0], name)
        finally:
            self.accents -= 1
        if body is None:
            # An argument the accent cannot read: the accent is printed as text and its
            # argument written next, as text.
            self._rollback(mark)
            return (None, i) if unit else (self._printed(name, "text"), i + 1)
        return _wrap("\\" + name + "{" + body + "}", wrap), arg[1]

    def _accent_body(self, toks: list, name: str) -> str | None:
        """An accent's argument as written, or None when no form of it compiles
        (:func:`_composite_safe`): braces around all of it are dropped when that makes it one
        that compiles (``\\~{{}}`` -> ``\\~{}``; noted, an author's file stops there)."""
        body = self.arg(toks, "text")
        if _composite_safe(body):
            return body
        inner = _unwrapped(toks)
        if inner is not toks:
            body = self.arg(inner, "text")
            if _composite_safe(body):
                self.fixes.append(f"\\{name} over an empty or doubly braced group")
                return body
        return None

    def _text_word(self, toks: list, i: int, wrap: bool, unit: bool):
        name = toks[i][1]
        kind = TEXT_COMMANDS.get(name)
        if kind == "zero":
            j = i + 1
            if j < len(toks) and toks[j] == ("g", []):
                j += 1  # \ss{} -> {\ss}
            return ("\\" + name if unit else "{\\" + name + "}"), j
        if kind == "accent":
            return self._accent(toks, i, name, wrap, unit)
        if kind in ("one", "url", "href") and (note := self._capped_text(name)) is not None:
            return (None, i) if unit else (self._as_text(name, note, "text"), i + 1)
        if kind == "one":
            arg = _next_arg(toks, i + 1)
            if arg is not None:
                self.text_depth += 1
                try:
                    body = self.arg(arg[0], "text")
                finally:
                    self.text_depth -= 1
                return _wrap("\\" + name + "{" + body + "}", wrap), arg[1]
        elif kind == "declaration":
            rest = toks[i + 1 :]
            while rest and rest[0][0] == " ":
                rest = rest[1:]
            body = self.seq(rest, "text", top=False)
            return _wrap("\\" + name + (" " + body if body else ""), wrap), len(toks)
        elif kind == "url":
            arg = _next_arg(toks, i + 1)
            url = _plain_chars(arg[0]) if arg is not None else None
            if url is not None and plain_url(url):
                return _wrap("\\url{" + url + "}", wrap), arg[1]
        elif kind == "href":
            first = _next_arg(toks, i + 1)
            url = _plain_chars(first[0]) if first is not None else None
            second = _next_arg(toks, first[1]) if first is not None else None
            if url is not None and plain_url(url) and second is not None:
                self.links += 1
                try:
                    body = self.arg(second[0], "text")
                finally:
                    self.links -= 1
                return _wrap("\\href{" + url + "}{" + body + "}", wrap), second[1]
        elif kind == "math":
            arg = _next_arg(toks, i + 1)
            if arg is not None:
                return self._math(arg[0], wrap), arg[1]
        elif name in MATH_COMMANDS and MATH_COMMANDS[name] != "declaration":
            if name in _MATH_WRAPPERS and (note := self._capped_math(toks, i)) is not None:
                return (None, i) if unit else (self._as_text(name, note, "text"), i + 1)
            mark = self._mark()
            piece, j = self.math_item(toks, i)
            # A math command in running text: put it in math (what a cap printed as text in it
            # stays printed there).
            if all(issue in _CAP_NOTES for issue in self.issues[mark[0] :]):
                self.fixes.append("\\" + name + " in running text")
                return _wrap("$" + piece + "$", wrap), j
            self._rollback(mark)
        if unit:
            return None, i
        return self._printed(name, "text"), i + 1

    # -- math mode

    def _script(self, toks: list, i: int, scripts: str, after_prime: bool):
        """A superscript, a subscript or a prime at ``toks[i]`` in math: ``(LaTeX, index after
        it, the scripts its base now carries)``. The argument is always braced (a command right
        after ^ or _ stops pdflatex: ``x^\\hat{y}``, ``x^\\int``), and a second script of one
        kind on a base gets an empty base first (``x^2^3`` is a double superscript; primes in
        a row are one)."""
        ch = toks[i][1]
        if ch == "^" and i + 1 < len(toks) and toks[i + 1] == ("c", "^"):
            # Two carets: printed, never TeX's character-code notation (^^5c is a backslash).
            return "\\mbox{{\\textasciicircum}{\\textasciicircum}}", i + 2, ""
        kind = "_" if ch == "_" else "^"
        lead = ""
        # Primes in a row, and a superscript right after them, are one superscript to TeX
        # (x'' and x'^2 compile; x' ' and x^2' are a double superscript).
        joined = after_prime and ch in "'^"
        if kind in scripts and not joined:
            lead, scripts = "{}", ""
            self.scripts.append(_DOUBLE_SCRIPT)
        if kind not in scripts:
            scripts += kind
        if ch == "'":
            return lead + "'", i + 1, scripts
        j = i + 1
        while j < len(toks) and toks[j][0] == " ":
            j += 1
        if j >= len(toks) or (toks[j][0] == "c" and toks[j][1] in "^_"):
            self.scripts.append(_EMPTY_SCRIPT)
            return lead + ch + "{}", j, scripts  # a script with nothing to take
        tok = toks[j]
        if tok[0] == "g":
            return lead + ch + "{" + self.math_arg(tok[1]) + "}", j + 1, scripts
        if not _unbraced_script_ok(tok):
            self.scripts.append(_UNBRACED_SCRIPT)
        piece, k = self.math_item(toks, j)
        return lead + ch + "{" + piece + "}", k, scripts

    def _math_char(self, ch: str) -> str:
        """A character outside ASCII in math: its math form (the plus-minus sign as ``\\pm``), a
        letter with accents as accent commands in a box, any other character pdflatex typesets
        in a box (inputenc writes it as a text command, which math does not take), else the
        character itself (noted in :attr:`unset`)."""
        form = _char_to_latex(ch, True)
        if form != ch:
            if all(typesettable(c) for c in form):
                return form
        elif typesettable(ch):
            return _box(ch)
        self.unset.append(ch)
        return ch

    def math_item(self, toks: list, i: int):
        tok = toks[i]
        if tok[0] == "c":
            ch = tok[1]
            if ch == "$":
                return "\\mbox{\\$}", i + 1  # inside a group in math: never a delimiter
            if ch in "&%#":
                return "\\" + ch, i + 1
            if ch.isascii():
                return (ch if typesettable(ch) else ""), i + 1
            return self._math_char(ch), i + 1
        if tok[0] == "s":
            ch = tok[1]
            if ch in _MATH_KEPT_SYMBOLS:
                return "\\" + ch, i + 1
            if ch in "{}":
                return "\\lbrace" if ch == "{" else "\\rbrace", i + 1
            if ch in _TEX_SPACE:
                return "\\ ", i + 1
            if ch == "\\":
                return " ", i + 1
            if ch in _TEXT_ACCENT_SYMBOLS:
                piece, j = self._accent(toks, i, ch, False, True)
                if piece is not None:
                    self.fixes.append("\\" + ch + " in math")
                    return _box(piece), j
            if ch in "-":
                return "", i + 1
            return self._printed(ch, "math"), i + 1
        name = tok[1]
        kind = MATH_COMMANDS.get(name)
        if kind in ("zero", "declaration"):
            return "\\" + name, i + 1
        if name in _MATH_WRAPPERS and (note := self._capped_math(toks, i)) is not None:
            return self._as_text(name, note, "math"), i + 1
        if name == "not":
            operand = _not_operand(toks, i + 1)
            if operand is not None:
                return "\\not{" + operand[0] + "}", operand[1]
        elif kind == "one":
            index = self._root_index(toks, i) if name == "sqrt" else None
            arg = _next_arg(toks, index[1] + 1 if index is not None else i + 1)
            if arg is not None:
                saved = self._enter(name)
                try:
                    optional = ("[" + self.seq(toks[index[0] : index[1]], "math", top=False) + "]"
                                if index is not None else "")
                    body = self.math_arg(arg[0])
                finally:
                    self._leave(saved)
                return "\\" + name + optional + "{" + body + "}", arg[1]
        elif kind == "two":
            first = _next_arg(toks, i + 1)
            second = _next_arg(toks, first[1]) if first is not None else None
            if second is not None:
                saved = self._enter(name)
                try:
                    pieces = (self.math_arg(first[0]), self.math_arg(second[0]))
                finally:
                    self._leave(saved)
                return "\\" + name + "{" + pieces[0] + "}{" + pieces[1] + "}", second[1]
        elif kind == "text":
            arg = _next_arg(toks, i + 1)
            if arg is not None:
                return "\\mbox{" + self.arg(arg[0], "text") + "}", arg[1]
        elif kind == "math":
            arg = _next_arg(toks, i + 1)
            if arg is not None:
                return self.math_arg(arg[0]), arg[1]
        elif TEXT_COMMANDS.get(name) not in (None, "declaration"):
            if (note := self._capped_text(name)) is not None:
                return self._as_text(name, note, "math"), i + 1
            piece, j = self.text_item(toks, i, top=False, field=False, unit=True)
            if piece is not None:
                self.fixes.append("\\" + name + " in math")
                return _box(piece), j
        return self._printed(name, "math"), i + 1


_SPACE_RUNS_RE = re.compile(r" {2,}")


def _allowed_value(
    value: str, label: bool = False
) -> tuple[str, list[str], list[str], list[str], list[str]]:
    """``value`` (one printed field value, LaTeX-safe) written with allow-listed commands only:
    ``(LaTeX, issues, fixes, unset, scripts)`` -- what was printed as text or was unbalanced,
    what was moved into the mode its command needs (a math command in running text, a text
    command in math) or rewritten so it compiles (an accent over an empty group), the
    characters pdflatex has no form of (kept as they are), and what was rewritten in a script
    so it compiles (a second script on one base, a script with nothing to take, an argument
    TeX takes only in braces). White space runs become one space and the ends are trimmed, as
    BibTeX compresses them. Braces nested more than :data:`_MAX_DEPTH` deep give an empty
    value. ``label``: a field natbib reads into a citation label (its ``(`` and ``)`` at brace
    level 0 are braced too). PURE."""
    tokens, unbalanced, deepest = _tex_tokens(value)
    if deepest > _MAX_DEPTH:
        return "", [_TOO_DEEP], [], [], []
    writer = _Writer(label)
    writer.excess = _excess_wrappers(tokens)
    try:
        written = writer.seq(tokens, "text", top=True, field=True)
    except RecursionError:  # a stack the depth limit should never let happen
        return "", [_TOO_DEEP], [], [], []
    out = _SPACE_RUNS_RE.sub(" ", written).strip(" ")
    issues = list(dict.fromkeys(writer.issues))
    if unbalanced:
        issues.append("a brace TeX reads as unbalanced (an escaped \\{ or \\})")
    while "^^" in out:  # never TeX's character-code notation, however the pieces met
        out = out.replace("^^", "^{}\\mbox{{\\textasciicircum}}", 1)
    return (out, issues, list(dict.fromkeys(writer.fixes)), list(dict.fromkeys(writer.unset)),
            list(dict.fromkeys(writer.scripts)))


def value_issues(value: str) -> tuple[list[str], list[str]]:
    """``(command_issues(value), script_issues(value))`` from one walk of ``value``. PURE."""
    _out, issues, fixes, _unset, scripts = _allowed_value(value)
    return issues + fixes, scripts


def command_issues(value: str) -> list[str]:
    """What ``value`` (one printed field value as written) holds outside the allow-list, each
    once, in order: a command off :data:`TEXT_COMMANDS` / :data:`MATH_COMMANDS` for its mode
    (``\\input``, ``\\hspace``, ``\\mathbb`` ...), a math delimiter ``\\(`` / ``\\[`` with no
    partner, a brace TeX reads as unbalanced, braces nested past :data:`_MAX_DEPTH`, accents
    nested past :data:`_MAX_ACCENTS`, a link inside a link, math commands with arguments nested
    past :data:`_MAX_MATH_NESTING` (an arrow accent in an arrow accent, a root with an index in a
    root) or more than :data:`_MAX_MATH_WRAPPERS` of them, text markup nested past
    :data:`_MAX_TEXT_NESTING` (the copy prints each as text or writes the value empty), then a
    command in the wrong mode (``\\alpha in running text``, ``\\textit in math``: the copy moves
    it, an author's file stops pdflatex there). PURE; the same walk as the copy. TeX's ``^^``
    notation is named by :func:`caret_notation`."""
    return value_issues(value)[0]


def script_issues(value: str) -> list[str]:
    """What the copy rewrites in a superscript or subscript of ``value`` (one printed field
    value as written) so that it compiles, each once: a second script of one kind on one base
    (``x^2^3``, ``x_1_2``, ``x^2'``, ``x' '``), a script with nothing to take (``x^$``), an
    argument pdflatex takes only in braces (``x^\\hat{y}``, ``x^\\rm 2``, ``x^\\cdots``, a letter
    outside ASCII; see :data:`_SCRIPT_UNSAFE`). The canonical copy never has one; an author's
    bibliography fails on each. PURE; the same walk as the copy."""
    return value_issues(value)[1]


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
# 0.99e (TeX Live 2026) with \nocite{*}: the same entries and @preamble text, except on the
# file's last line, where BibTeX reads only the first command (a @string, a @comment or an
# entry followed there by another entry gives no second entry; the same text followed by any
# other line gives both) and drops what follows a syntax error: this reads all of it, so it
# reads MORE than BibTeX there, never less, and a check of it sees more. A test diffs the two
# both ways for files with no syntax error and a last line without a command
# (tests/test_bib_round7.py) and one way for mutated files (tests/test_bib_round6.py); the
# canonical copy ends every entry with a line of its own. Two readings after an error follow
# BibTeX's code: a
# @string whose name it read defines the macro as that name (lower case) before the value is
# read, so a definition that fails leaves the macro defined as its own name; and an entry whose
# key repeats one read before (ASCII case ignored) is "Repeated entry": BibTeX reads none of
# its fields and looks for the next '@' right after the key (as it does for every entry when
# \nocite{*} is used, and for a cited key otherwise; an uncited repeat's fields are read but
# not printed, so stopping after the key reads more, never less). Both are errors, and an
# author's bibliography that holds one fails verify (bib_syntax_issues).

_BIB_WHITE = frozenset(" \t\n\r")
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
# The characters an identifier (an entry type, a field or macro name) cannot hold.
_ID_ILLEGAL = frozenset('"#%\'(),={}')


class BibCommand(NamedTuple):
    """One ``@`` command BibTeX acts on: its name in lower case (``preamble``, ``string`` or an
    entry type), where the ``@`` is, where BibTeX stopped reading it (just past the closing
    delimiter, or where a syntax error stopped it), an entry's key, its fields (a @preamble's
    value is one field named ``""``, a @string's one field named after the macro), whether
    BibTeX read it to its closing delimiter, whether the value of its last field stopped on a
    syntax error (``bad_last``: BibTeX stores no such field; a @string's macro is then defined
    as its own name), and whether an entry's key repeats an earlier one (``repeated``: BibTeX
    read nothing after the key)."""

    command: str
    start: int
    end: int
    key: str | None
    fields: tuple[_Field, ...]
    complete: bool
    bad_last: bool = False
    repeated: bool = False


def _ascii_lower(text: str) -> str:
    """``text`` with A-Z lowered and nothing else, as BibTeX lowers an entry type, a field or
    macro name and a key (the case of other letters is not ignored). PURE."""
    return text.translate(_ASCII_LOWER)


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


def _read_command(bib: str, at: int, seen: set[str]) -> tuple[BibCommand | None, int]:
    """The command BibTeX reads at the ``@`` ``bib[at]`` (None when it reads none), and where it
    goes on looking for the next ``@``. ``seen`` holds the keys read so far (ASCII lower case);
    an entry's key is added to it."""
    n = len(bib)
    i = _skip_bib_white(bib, at + 1)
    j = _identifier_end(bib, i)
    if j == i or not _adjacent(bib, j, "{("):
        return None, max(j, at + 1)
    name = _ascii_lower(bib[i:j])
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
            # BibTeX defines the macro as its own name here, before it reads the value.
            macro = _ascii_lower(bib[k:m])
            k = _skip_bib_white(bib, m)
            if k >= n or bib[k] != "=":
                field = _Field(macro, field_start, field_start, ())
                return BibCommand(name, at, k, None, (field,), False, True), k
            k = _skip_bib_white(bib, k + 1)
        parts, k, ok = _read_value(bib, k, close)
        complete = ok and k < n and bib[k] == close
        end = k + 1 if complete else k
        field = _field(macro, field_start, parts, n)
        return BibCommand(name, at, end, None, (field,), complete, not ok), end
    # An entry: the key runs to a comma or white space (or, in braces, a closing brace).
    stops = _BIB_WHITE | ({",", "}"} if close == "}" else {","})
    m = k
    while m < n and bib[m] not in stops:
        m += 1
    key = bib[k:m]
    if _ascii_lower(key) in seen:  # "Repeated entry": nothing after the key is read
        return BibCommand(name, at, m, key, (), False, False, True), m
    seen.add(_ascii_lower(key))
    fields: list[_Field] = []

    def stopped(position: int, bad_last: bool = False) -> tuple[BibCommand, int]:
        return BibCommand(name, at, position, key, tuple(fields), False, bad_last), position

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
        field_name = _ascii_lower(bib[k:m])
        k = _skip_bib_white(bib, m)
        if k >= n or bib[k] != "=":
            return stopped(min(k, n))
        k = _skip_bib_white(bib, k + 1)
        parts, k, ok = _read_value(bib, k, close)
        fields.append(_field(field_name, field_start, parts, n))
        if not ok or k >= n:
            return stopped(min(k, n), not ok)
    return BibCommand(name, at, k + 1, key, tuple(fields), True), k + 1


# @MX:ANCHOR: [AUTO] The one reading of a .bib as BibTeX reads it: the verify bib checks scan
#   what it returns, and the paper copy drops each @preamble it finds.
# @MX:REASON: callers: canonical_bib and entry_values here (the copy render ships), pkgreqs_checks
#   (bib_keys, bib_subset, bib_form_problems, the _bib_units every bib check scans); a reading
#   that differs from BibTeX's lets text BibTeX prints go unchecked or out of the copy.
def bib_commands(bib: str) -> list[BibCommand]:
    """Every ``@`` command BibTeX acts on in ``bib``, in order, read as BibTeX reads it (see the
    note above :data:`_BIB_WHITE`): ``@preamble``, ``@string`` and entries (``@comment`` is not
    a command, and neither is an ``@`` inside a value BibTeX reads). An entry or a @string that a
    syntax error stopped is listed with what BibTeX read of it (``complete`` False); BibTeX then
    looks for the next ``@`` where it stopped, and so does this. An entry repeating an earlier
    key is listed with no field (``repeated``). PURE (the reading of the last few files is
    remembered: verify reads one file with several checks)."""
    return list(_read_commands(bib))


@functools.lru_cache(maxsize=8)
def _read_commands(bib: str) -> tuple[BibCommand, ...]:
    commands: list[BibCommand] = []
    seen: set[str] = set()
    pos = 0
    while (at := bib.find("@", pos)) >= 0:
        command, pos = _read_command(bib, at, seen)
        if command is not None:
            commands.append(command)
    return tuple(commands)


def string_macros_used_as_urls(bib: str, commands: list[BibCommand] | None = None) -> set[str]:
    """The lower-cased names of the ``@string`` macros a ``url`` or ``doi`` field of ``bib`` names
    (``url = myurl``): their text is printed as a URL. PURE."""
    commands = bib_commands(bib) if commands is None else commands
    return {
        _ascii_lower(bib[start:end])
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


# @MX:NOTE: [AUTO] The character and markup layer on its own (the canonical copy, paper_bib,
#   applies it per value); characters with no LaTeX form are kept so verify can name them.
def latex_safe_bib(bib: str) -> str:
    """``bib`` with every printed field value made LaTeX-safe; everything else untouched except
    a bare month name BibTeX does not define, which becomes its macro. PURE.

    A test-only layer (not in ``__all__``): nothing sci-adk ships is written by it -- render
    writes :func:`paper_bib`, which applies the same per-value conversion
    (:func:`_latex_safe_text`) inside the canonical copy. The tests use it to pin the
    character and markup policy on its own.

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
# The fields natbib can read into a citation label (plainnat's calc.label).
_LABEL_FIELDS = _NAME_FIELDS | {"key"}
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


# -- the canonical copy ------------------------------------------------------------------------
#
# What render writes into paper/: every entry BibTeX reads (bib_commands), as
# ``@type{key, field = {value}, ...}`` -- one braced value per field, @string macros expanded
# (the predefined month macros jan..dec as plainnat defines them), '#' parts joined, no
# @string, @preamble or @comment and no text between entries. A value holds only what the
# allow-list keeps (_allowed_value); verify passes a shipped bibliography only when
# paper_bib(text) == text, so the copy and the check judge the same text. Each value is written
# again until that changes nothing (_settled), so the copy is its own fixed point by
# construction, whatever its pieces do to one another.

# The month text plainnat's MACRO commands give jan..dec (what a concatenation such as
# ``jan # "~5"`` prints); a bare month macro is written as the macro, so the style decides.
_MONTH_TEXT = dict(zip(_MONTH_ABBR, (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)))
# The journal macros plain.bst and every natbib style define (MACRO commands, the same text in
# plainnat, abbrvnat, unsrtnat and apalike; TeX Live 2026): a field naming one prints its text.
_STYLE_MACRO_TEXT = {
    **_MONTH_TEXT,
    "acmcs": "ACM Computing Surveys", "acta": "Acta Informatica",
    "cacm": "Communications of the ACM", "ibmjrd": "IBM Journal of Research and Development",
    "ibmsj": "IBM Systems Journal", "ieeese": "IEEE Transactions on Software Engineering",
    "ieeetc": "IEEE Transactions on Computers",
    "ieeetcad": "IEEE Transactions on Computer-Aided Design of Integrated Circuits",
    "ipl": "Information Processing Letters", "jacm": "Journal of the ACM",
    "jcss": "Journal of Computer and System Sciences", "scp": "Science of Computer Programming",
    "sicomp": "SIAM Journal on Computing", "tocs": "ACM Transactions on Computer Systems",
    "tods": "ACM Transactions on Database Systems", "tog": "ACM Transactions on Graphics",
    "toms": "ACM Transactions on Mathematical Software",
    "toois": "ACM Transactions on Office Information Systems",
    "toplas": "ACM Transactions on Programming Languages and Systems",
    "tcs": "Theoretical Computer Science",
}
# A key the copy keeps: what a \cite in the paper may name -- ASCII letters, digits and
# : _ . ; + / = @ - (paper._KEY, without the comma and white space that separate keys there) --
# and the letters outside ASCII that pdflatex typesets (inputenc reads them in the .aux too:
# a \citep of Mueller2019 spelled with u-umlaut compiles under both render preambles; a test
# pins it).
_KEY_ASCII = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:_.;+/=@-"
)
# The entry types a BibTeX style defines (plainnat: one function each that prints a reference);
# another type is written misc, which is how a style prints it -- one named like a function of
# the style (@output, @and, @emphasize) stopped BibTeX.
_STANDARD_TYPES = frozenset(
    "article book booklet conference inbook incollection inproceedings manual mastersthesis "
    "misc phdthesis proceedings techreport unpublished".split()
)
_FIELD_NAME_RE_OK = re.compile(r"[a-z][a-z0-9_:.+-]*")
_STORE = "correct it in the run's literature store (literature/references.bib)"
# natbib's label is the first two authors' last names and the year in one BibTeX entry string,
# at most 250 characters by BibTeX's default (500 in TeX Live 2026; a 1000-character name made
# the label lose its year, and natbib stopped): a last name of at most 100 characters and a year
# of at most 40 keep it under 250.
_MAX_NAME = 100
_MAX_YEAR = 40
# How many times a value is written again before it is given up as having no stable form.
_FIXPOINT_ROUNDS = 6
_TEX_PIECE_RE = re.compile(r"\\(?:[A-Za-z]+|.)|.", re.DOTALL)


# The longest key the copy keeps (a key of 100000 characters overflowed TeX's buffer in the
# .aux; one of 1000 was cited by \citep, \citet, \cite and \citeauthor under both preambles).
_MAX_KEY = 200


def _key_ok(key: str) -> bool:
    """True iff the copy keeps an entry with ``key`` (see :data:`_KEY_ASCII`): at most
    :data:`_MAX_KEY` characters, the first one ASCII (a \\cite of a key starting with a letter
    outside ASCII stopped pdflatex under both preambles: natbib makes a command name of the
    key, "Missing \\endcsname inserted"; the same letter later in a key compiles). PURE."""
    return bool(key) and len(key) <= _MAX_KEY and key[0] in _KEY_ASCII and all(
        c in _KEY_ASCII or (not c.isascii() and c.isalpha() and typesettable(c)) for c in key
    )


def _ascii_spelling(ch: str) -> str:
    """An ASCII spelling of the letter ``ch``: its base letters (O with diaeresis -> ``O``, the
    feminine ordinal -> ``a``), the letters BibTeX reduces its command to (AE ligature ->
    ``AE``), or ``""``."""
    folded = "".join(c for c in unicodedata.normalize("NFKD", ch) if c.isascii() and c.isalnum())
    return folded or _NAME_LETTER_CMD.get(ch, "")


def _key_problem(key: str) -> str:
    """Why a citation cannot name ``key`` (one :func:`_key_ok` refuses), as a phrase."""
    if len(key) > _MAX_KEY:
        return (f"its key is {len(key)} characters long, more than the {_MAX_KEY} characters a "
                "key may hold (a key of 100000 characters overflowed TeX's buffer): give it a "
                "shorter key")
    if key and not key[0].isascii():
        spelled = _ascii_spelling(key[0]) + key[1:]
        example = f", e.g. {spelled!r}" if _key_ok(spelled) else ""
        return (f"its key starts with {_codepoints(key[0])}, a character outside ASCII, and a "
                "\\cite of such a key stops pdflatex (natbib makes a command name of the key: "
                "'Missing \\endcsname inserted'): give it a key that starts with an ASCII "
                f"letter{example}")
    return ("a key holds only letters, digits and : _ . ; + / = @ - (what a citation can name; "
            "LaTeX reads a backslash in one as a command; a letter outside ASCII only after the "
            "first character, and only when pdflatex typesets it)")


def _codepoints(chars) -> str:
    return ", ".join("U+%04X (%s)" % (ord(c), unicodedata.name(c, "unnamed")) for c in chars)


class CanonicalBib(NamedTuple):
    """The canonical copy of a bibliography (:func:`canonical_bib`): its text, and one line per
    entry, field or macro it left out or changed in a way a reader would notice (render prints
    them as warnings)."""

    text: str
    notes: tuple[str, ...]


def _expanded(bib: str, field: _Field, macros: dict[str, str], notes: list[str], where: str) -> str:
    """A field's value as BibTeX stores it: its parts joined, each macro replaced by its text
    (a month or journal macro the styles define by its text there); an undefined macro is
    nothing, and noted. Joined to at most :data:`MAX_EXPANDED` characters (a chain of macros
    each doubling the last is never expanded in full); an entry field cut there is noted."""
    out: list[str] = []
    size = 0
    for start, end, delimited in field.parts:
        raw = bib[start:end]
        if delimited or raw[:1].isdigit():
            piece = raw
        else:
            name = _ascii_lower(raw)
            if name in macros:
                piece = macros[name]
            elif name in _STYLE_MACRO_TEXT:
                piece = _STYLE_MACRO_TEXT[name]
            else:
                notes.append(f"{where} names the macro '{raw}', which the bibliography does not "
                             f"define, so BibTeX prints nothing for it; {_STORE}")
                continue
        if size + len(piece) > MAX_EXPANDED:
            out.append(piece[: MAX_EXPANDED - size])
            if where.startswith("entry"):
                notes.append(f"{where} is longer than {MAX_EXPANDED} characters as BibTeX joins "
                             f"its parts and macros (more than BibTeX holds); the rest is left "
                             f"out; {_STORE}")
            break
        out.append(piece)
        size += len(piece)
    return "".join(out)


def _define(bib: str, command: BibCommand, macros: dict[str, str], notes: list[str]) -> None:
    """Define the macro of the @string ``command`` as BibTeX does: its value, or its own name when
    the definition has a syntax error."""
    field = command.fields[0] if command.fields else None
    if field is None or not field.name:
        return
    if command.bad_last:
        macros[field.name] = field.name
    else:
        macros[field.name] = _expanded(bib, field, macros, notes, f"@string '{field.name}'")


def entry_values(bib: str) -> list[tuple[BibCommand, list[tuple[str, str]]]]:
    """Each entry BibTeX reads in ``bib`` with its fields' values as BibTeX prints them:
    ``(command, [(field name, value), ...])``, ``#`` parts joined and ``@string`` macros
    expanded in file order (a month macro as plainnat's month name, an undefined macro as
    nothing, a macro whose definition has a syntax error as its own name). Every field read is
    listed, also one whose value a syntax error stopped (what was read of it), so a check over
    these values sees at least what BibTeX prints. PURE (remembered as :func:`bib_commands`)."""
    return [(command, list(values)) for command, values in _read_entry_values(bib)]


@functools.lru_cache(maxsize=8)
def _read_entry_values(bib: str) -> tuple[tuple[BibCommand, tuple[tuple[str, str], ...]], ...]:
    macros: dict[str, str] = {}
    out: list[tuple[BibCommand, tuple[tuple[str, str], ...]]] = []
    for command in _read_commands(bib):
        if command.command == "preamble":
            continue
        if command.command == "string":
            _define(bib, command, macros, [])
            continue
        out.append(
            (command, tuple((f.name, _expanded(bib, f, macros, [], "")) for f in command.fields))
        )
    return tuple(out)


def _undefined_macros(bib: str, field: _Field, defined: set[str], where: str) -> list[str]:
    if field.name == "month":
        return []  # a month name BibTeX does not define has its own advisory
    return [
        f"{where} names the macro '{bib[start:end]}', which the bibliography does not define "
        "before it (BibTeX prints nothing for it)"
        for start, end, delimited in field.parts
        if not delimited
        and not bib[start:end][:1].isdigit()
        and _ascii_lower(bib[start:end]) not in defined
    ]


# @MX:NOTE: [AUTO] The places where BibTeX's reading depends on how it recovers from an error:
#   an author's bibliography holding one fails verify, so every check of it reads what BibTeX does.
def bib_syntax_issues(bib: str) -> list[str]:
    """One phrase per place in ``bib`` where what BibTeX reads depends on how it recovers from an
    error, in file order: a @string or @preamble with a syntax error (BibTeX defines the macro as
    its own name), an entry with a syntax error (BibTeX stops reading it and looks for the next
    ``@`` from there), an entry repeating the key of an earlier one (BibTeX reads nothing after
    the key), and a macro a field names that no @string defines before it (BibTeX prints nothing;
    the month and journal macros the styles define are defined). Empty for a bibliography BibTeX
    reads without an error. PURE."""
    issues: list[str] = []
    defined: set[str] = set(_STYLE_MACRO_TEXT)
    line, counted = 1, 0
    for command in bib_commands(bib):
        line += bib.count("\n", counted, command.start)  # the commands are in file order
        counted = command.start
        if command.command == "preamble":
            if not command.complete:
                issues.append(f"@preamble on line {line} has a syntax error")
            continue
        if command.command == "string":
            field = command.fields[0] if command.fields else None
            name = field.name if field is not None else ""
            if field is not None:
                issues += _undefined_macros(bib, field, defined, f"@string '{name}'")
            if command.bad_last:
                issues.append(f"@string '{name}' on line {line} has a syntax error, so BibTeX "
                              f"defines the macro as its own name ('{name}')")
            elif not command.complete:
                issues.append(f"@string '{name}' on line {line} has a syntax error after its "
                              "value")
            if name:
                defined.add(name)
            continue
        where = f"entry '{command.key}'"
        if command.repeated:
            issues.append(f"{where} on line {line} repeats the key of an earlier entry: BibTeX "
                          "reads nothing after its key and looks for the next @ from there")
            continue
        if not command.complete:
            issues.append(f"{where} on line {line} has a syntax error: BibTeX stops reading it "
                          "there and looks for the next @ from that point")
        for field in command.fields:
            issues += _undefined_macros(bib, field, defined, f"{where} field '{field.name}'")
    return issues


def _bare_month(bib: str, field: _Field, macros: dict[str, str]) -> str | None:
    """The month macro a ``month`` field is (``month = jan``, or an undefined month name such as
    ``June`` or ``sept``, which BibTeX would print as nothing), or None."""
    if len(field.parts) != 1 or field.parts[0][2]:
        return None
    token = _ascii_lower(bib[field.parts[0][0] : field.parts[0][1]])
    if token in macros:
        return None
    return token if token in _MONTH_TEXT else _MONTH_MACRO.get(token)


def _canonical_doi(value: str) -> str | None:
    """A doi value without a ``doi:`` or doi.org prefix when it has the DOI form
    (``paper.is_doi``), else None."""
    doi = " ".join(value.split())
    prefix = _DOI_PREFIX_RE.match(doi)
    doi = doi[prefix.end() :] if prefix else doi
    return doi if is_doi(doi) else None


def _year_char(ch: str) -> bool:
    """A character a year keeps: a letter or digit (a Latin letter pdflatex typesets outside
    ASCII), a space, ``~`` and ``( ) . , / ? : ; ' -`` (each compiled in a natbib label)."""
    if ch.isascii():
        return ch.isalnum() or ch in " ~().,/?:;'-"
    return ch.isalpha() and typesettable(ch)


def _name_char(ch: str) -> bool:
    if ch.isascii():
        return ch.isalnum() or ch in " .,-'"
    return ch.isalpha() and typesettable(ch)


def _plain_year(text: str, where: str) -> tuple[str, list[str]]:
    """A year as natbib can read it in its label: plain text only (a command, math or a group
    there stopped natbib with "Improper alphabetic constant"), at most :data:`_MAX_YEAR`
    characters; a note when anything but braces was left out."""
    plain = _plain_text(text, _year_char)
    notes: list[str] = []
    if plain != " ".join(text.replace("{", "").replace("}", "").split()):
        notes.append(f"{where} holds LaTeX natbib cannot read in a citation label ({text!r}); "
                     f"written as the plain text {plain!r}; {_STORE}")
    if len(plain) > _MAX_YEAR:
        plain = plain[:_MAX_YEAR].rstrip()
        notes.append(f"{where} is longer than {_MAX_YEAR} characters (natbib's label holds it); "
                     f"cut to {plain!r}; {_STORE}")
    return plain, notes


def _last_name(name: str) -> str:
    """The part of one name BibTeX's label takes: before the first brace-level-0 comma, else
    the last word (a name in one pair of braces: what the braces hold)."""
    parts = _depth0_split(name, _COMMA_RE)
    if len(parts) > 1:
        last = parts[0].strip()
    else:
        words = [w for w in _depth0_split(name, _SPACES_RE)[::2] if w]
        last = words[-1] if words else ""
    if last.startswith("{") and _group_close(last, 0) == len(last) - 1:
        last = last[1:-1]
    return last


# A name's last comma followed by nothing BibTeX reads as a name part: white space, '-' and '~'
# separate the tokens of a name, so "Doe, -", "Doe,--" and "Doe, J, ~" end in an empty part
# (BibTeX: "has a comma at the end", exit 2).
_EMPTY_NAME_TAIL_RE = re.compile(r",[\s~-]*\Z")


def _without_empty_tail(name: str) -> str:
    """``name`` without each last comma that only white space, '-' or '~' follows."""
    while (m := _EMPTY_NAME_TAIL_RE.search(name)) is not None:
        name = name[: m.start()].rstrip()
    return name


def _safe_names(value: str, where: str) -> tuple[str, list[str]]:
    """An author or editor value with each name BibTeX or natbib would stop on made safe ("Too
    many commas in name", "has a comma at the end", BibTeX errors): a name ending in a comma,
    or in a comma followed only by '-', '--' or '~' (BibTeX reads no name part there), is
    written without it (a store measured under ~/research ends every name so: ``Sterling G.
    Baird,``), and a name with more than two brace-level-0 commas, or only commas, as one name
    in braces; a name whose last name is longer than :data:`_MAX_NAME` characters as its first
    characters, braced. Notes say so."""
    pieces = _depth0_split(value, _NAME_SEPARATOR_RE)
    notes: list[str] = []
    for k in range(0, len(pieces), 2):
        name = pieces[k].strip()
        if not name:
            continue
        original = name
        kept = _without_empty_tail(name)
        if kept != name and kept.strip(" ,~-"):
            name = kept
            notes.append(f"{where}: the name {original!r} ends with a comma followed by no name "
                         "part (BibTeX stops on it: 'has a comma at the end'); written without "
                         f"it; {_STORE}")
        if (len(_depth0_split(name, _COMMA_RE)) // 2 > 2
                or _EMPTY_NAME_TAIL_RE.search(name) is not None):
            notes.append(f"{where}: the name {name!r} has more commas than a name takes (BibTeX "
                         f"stops on it); written as one name in braces; {_STORE}")
            name = "{" + name + "}"
        if len(_last_name(name)) > _MAX_NAME:
            short = _plain_text(name, _name_char)[:_MAX_NAME].strip()
            notes.append(f"{where}: a name whose last name is longer than {_MAX_NAME} characters "
                         f"(natbib's label holds it) is written as {short!r}; {_STORE}")
            name = "{" + short + "}"
        if name != original:
            pieces[k] = name
    return "".join(pieces), notes


def _break_long_words(text: str) -> tuple[str, bool]:
    """``text`` with a space put into each run longer than :data:`_MAX_WORD` characters without
    one (never right after a command, whose following space TeX drops), and whether one was."""
    if all(len(word) <= _MAX_WORD for word in text.split(" ")):
        return text, False
    out: list[str] = []
    run = 0
    for m in _TEX_PIECE_RE.finditer(text):
        piece = m.group(0)
        if piece == " ":
            run = 0
        elif run >= _MAX_WORD and not out[-1].startswith("\\"):
            out.append(" ")
            run = 0
        out.append(piece)
        run += len(piece)
    return "".join(out), True


def _written_once(name: str, value: str, where: str) -> tuple[str, list[str], list[str]]:
    """``value`` as the copy writes field ``name`` once: ``(LaTeX, issues, notes)`` -- the
    issues of :func:`_allowed_value` (what was printed as text), and the notes for what else
    changed."""
    text, issues, _fixes, unset, _scripts = _allowed_value(
        _latex_safe_text(value), label=name in _LABEL_FIELDS
    )
    notes: list[str] = []
    if unset:
        notes.append(f"{where} holds {_codepoints(unset)}, which pdflatex cannot typeset with "
                     "the preamble sci-adk emits and which has no LaTeX form: the copy keeps it "
                     f"(a reference does not silently lose a letter), and verify fails it; {_STORE}")
    if name in _NAME_FIELDS:
        text, more = _safe_names(_tidy_names(text), where)
        notes += more
    elif name in _CASE_FIELDS:
        text = _protect_case(text)
    elif name == "year":
        text, more = _plain_year(text, where)
        notes += more
    elif name == "key" and len(text) > _MAX_NAME:
        short = _plain_text(text, _name_char)[:_MAX_NAME].strip()
        notes.append(f"{where} is longer than {_MAX_NAME} characters (natbib's label holds it; "
                     f"BibTeX cuts a longer one, braces and all); written as {short!r}; {_STORE}")
        text = short
    text, broke = _break_long_words(text)
    if broke:
        notes.append(f"{where} has a word longer than {_MAX_WORD} characters, broken with a "
                     "space (TeX reads a line of at most 200000 characters, and BibTeX breaks "
                     "a line only at a space)")
    return text, issues, notes


def _written(name: str, value: str, where: str) -> tuple[str, list[str], list[str]]:
    """:func:`_written_once`, with a value written longer than :data:`_MAX_FIELD` characters cut
    (BibTeX's string pool holds 200000) and noted."""
    text, issues, notes = _written_once(name, value, where)
    if len(text) <= _MAX_FIELD:
        return text, issues, notes
    cut = len(value)
    while len(text) > _MAX_FIELD and cut > 1:
        cut = max(1, cut * _MAX_FIELD // len(text) * 9 // 10)
        text, issues, notes = _written_once(name, value[:cut], where)
    notes.append(f"{where} is too long for BibTeX (over {_MAX_FIELD} characters as written); "
                 f"cut to its first {cut} characters; {_STORE}")
    return text, issues, notes


def _settled(name: str, value: str, where: str) -> tuple[str, list[str], list[str]]:
    """:func:`_written`, written again until that changes nothing: verify accepts a shipped
    bibliography only as its own copy, so each value must be a fixed point. The issues and notes
    are those of the first writing (what the source held)."""
    text, issues, notes = _written(name, value, where)
    for _round in range(_FIXPOINT_ROUNDS):
        again = _written(name, text, where)[0]
        if again == text:
            return text, issues, notes
        text = again
    return "", issues, notes + [f"{where} is left empty: the copy found no form of it that it "
                                f"writes the same way twice; {_STORE}"]


# -- natbib's citation label ----------------------------------------------------------------------
#
# plainnat's calc.label makes an entry's label from the last names of its first author (two
# authors: both), else (book, inbook, proceedings) of its editor, else from its key field, else
# (manual, proceedings) from the first three characters of its organization ("The " dropped:
# "The " #4 organization chop.word #3 text.prefix$), else from the first three bytes of its
# citation key (cite$ #1 #3 substring$), and writes \bibitem[<label>(<year>)]. natbib reads that
# back up to the first '(' at brace level 0 as the names and from there to ')' as the year. A
# field is "empty" for BibTeX when it is missing or white space. Measured (TeX Live 2026, both
# preambles): a three-character prefix that cuts \& \% \_ \$ or $\alpha$, or a letter outside
# ASCII in two (BibTeX counts bytes), stopped pdflatex; so did a '_' in a key's first three
# characters (it reaches \citep as text); so did a '(' in the names followed by a command, a
# group or a letter outside ASCII ("Improper alphabetic constant").
_LABEL_ORDER = {
    "book": ("author", "editor", "key"),
    "inbook": ("author", "editor", "key"),
    "proceedings": ("editor", "key", "organization"),
    "manual": ("author", "key", "organization"),
}
_DEFAULT_LABEL_ORDER = ("author", "key")
# What a three-character label may hold at brace level 0 besides whole special characters
# ({\...}) and whole letters outside ASCII pdflatex typesets.
_PREFIX_SAFE = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,-'"
)


def label_source(kind: str, values: dict[str, str]) -> tuple[str, str]:
    """``(field, value)`` plainnat makes the citation label of an entry of type ``kind`` (lower
    case) with the field ``values`` from: its first label field that is not empty, or
    ``("cite", "")`` when it is labelled by its citation key. PURE."""
    for name in _LABEL_ORDER.get(kind, _DEFAULT_LABEL_ORDER):
        value = values.get(name, "")
        if value.strip():
            return name, value
    return "cite", ""


def _chop_the(text: str) -> str:
    return text[4:] if text.startswith("The ") else text


def _text_prefix(text: str, count: int = 3) -> tuple[str, bool]:
    """BibTeX's ``text.prefix$`` of ``text`` -- its first ``count`` text characters, a brace
    group at brace level 0 that starts with a backslash counted as one and any other character
    as its UTF-8 bytes, as BibTeX counts them -- and whether natbib reads it in a label: ASCII
    letters, digits, spaces and . , - ' at brace level 0, whole special characters and whole
    letters outside ASCII pdflatex typesets. PURE."""
    out: list[str] = []
    i = n = depth = 0
    safe = True
    while i < len(text) and n < count:
        c = text[i]
        if c == "{":
            if depth == 0 and text.startswith("{\\", i):
                end = _group_close(text, i)
                out.append(text[i : end + 1])
                i, n = end + 1, n + 1
                continue
            depth += 1
            safe = False  # BibTeX counts into the group and closes it after the cut
        elif c == "}":
            depth = max(0, depth - 1)
        else:
            size = len(c.encode("utf-8"))
            if n + size > count:
                return "".join(out), False  # a letter cut in two
            n += size
            if depth or not (c in _PREFIX_SAFE or (c.isalpha() and typesettable(c))):
                safe = False
        out.append(c)
        i += 1
    return "".join(out), safe


def _key_prefix(key: str) -> tuple[str, bool]:
    """The first three bytes of a citation key as plainnat writes them into a label, and
    whether natbib reads them: no letter cut in two and no ``_`` (text mode stops on it). PURE."""
    raw = key.encode("utf-8")[:3]
    try:
        prefix = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace"), False
    return prefix, "_" not in prefix


def _plain_label(text: str) -> str:
    """The letters, digits and spaces of ``text`` read as TeX, as a key field holds them."""
    return _plain_text(
        text, lambda c: c == " " or (c.isalnum() and (c.isascii() or typesettable(c)))
    )


def unsafe_label(kind: str, cite_key: str, values: dict[str, str]) -> tuple[str, str] | None:
    """``(what, prefix)`` when plainnat labels the entry by the first three characters of its
    organization or citation key and those are ones natbib cannot read, else None. PURE."""
    source, value = label_source(kind, values)
    if source == "organization":
        prefix, safe = _text_prefix(_chop_the(value))
        return None if safe else ("organization", prefix)
    if source == "cite":
        prefix, safe = _key_prefix(cite_key)
        return None if safe else ("citation key", prefix)
    return None


def _label_key(kind: str, cite_key: str, values: dict[str, str]) -> tuple[str, str, str] | None:
    """``(key text, what, prefix)``: the key field the copy writes so the label never comes
    from an unsafe three-character prefix (:func:`unsafe_label`) -- the first three letters,
    digits and spaces of the organization (``AT\\&T`` -> ``ATT``), or the first three
    characters of the citation key as text (``a_b2020`` -> ``a\\_b``) -- or None."""
    unsafe = unsafe_label(kind, cite_key, values)
    if unsafe is None:
        return None
    what, prefix = unsafe
    text = ""
    if what == "organization":
        text = _plain_label(_chop_the(values.get("organization", "")))[:3].strip()
    if not text:
        text = _written_once("key", cite_key[:3], "")[0]
    return text, what, prefix


# The function names of the standard and natbib styles (plain, abbrv, unsrt, alpha, apalike,
# plainnat, abbrvnat, unsrtnat; TeX Live 2026) that are no entry type: BibTeX runs the function
# an entry's type names, so @output, @and, @emphasize and @format.names stopped it ("You can't
# pop an empty literal stack"). The canonical copy writes such a type misc.
STYLE_FUNCTION_NAMES = frozenset(
    "and author.editor.full author.editor.key.label author.editor.sort author.full "
    "author.key.label author.key.organization.label author.organization.sort author.sort "
    "begin.bib bib.sort.order calc.label calc.short.authors chop.word editor.full "
    "editor.key.label editor.key.organization.label editor.organization.sort editor.sort "
    "either.or.check emphasize empty.misc.check end.bib field.or.null fin.entry "
    "format.article.crossref format.authors format.book.crossref format.btitle format.bvolume "
    "format.chapter.pages format.crossref.editor format.date format.doi format.edition "
    "format.editors format.eid format.full.names format.in.ed.booktitle "
    "format.incoll.inproc.crossref format.isbn format.issn format.key format.lab.names "
    "format.names format.number.series format.pages format.thesis.type format.title "
    "format.tr.number format.url format.vol.num.eid format.vol.num.pages forward.pass "
    "init.seq init.state.consts initialize.et.al.char.used initialize.extra.label.stuff "
    "initialize.longest.label int.to.fix longest.label.pass make.full.names multi.page.check "
    "n.dashify new.block new.block.checka new.block.checkb new.sentence new.sentence.checka "
    "new.sentence.checkb not or output output.bibitem output.check output.nonnull "
    "output.year.check presort reverse.pass sort.format.names sort.format.title sortify "
    "tie.or.space.connect".split()
)
# The fields a style changes the case of (change.case$ in the TeX Live styles: title, edition,
# type), and the letter commands whose lower case is their own lower-case letter (\AE -> \ae).
_CASE_CHANGED_FIELDS = frozenset({"title", "edition", "type"})
_LETTER_PAIRS = frozenset("AE OE AA O L SS DH TH NG DJ".split())


#: How many entries with one citation label plainnat tells apart: a letter after the year, a to
#: z; the 27th gets '{' and natbib stops ("Paragraph ended before \@lbibitem was complete").
_MAX_LABEL_LETTERS = 26


def _label_name(name: str) -> str:
    """The von and last names of one name as plainnat's label holds them ("{vv~}{ll}"): before
    the first brace-level-0 comma, else from the first word after the first that starts with a
    lower-case letter, else the last word. PURE."""
    parts = _depth0_split(name, _COMMA_RE)
    if len(parts) > 1:
        return " ".join(parts[0].split())
    words = [w for w in _depth0_split(name, _SPACES_RE)[::2] if w]
    for k in range(1, len(words) - 1):
        if _starts_lowercase(words[k]):
            return " ".join(words[k:])
    return words[-1] if words else ""


def natbib_label(kind: str, cite_key: str, values: dict[str, str]) -> tuple[str, str]:
    """``(names, year)`` of the citation label plainnat's calc.label makes for an entry of type
    ``kind`` with key ``cite_key`` (``values``: its fields as BibTeX prints them): the first
    author's last name, "A and B" for two, "A et~al." for more (or a second name "others"),
    else the label field :func:`label_source` names; the year is ``""`` when the entry has none
    or is labelled by its key field. Entries with an equal label are told apart by a letter.
    An approximation for counting labels (white space between words is normalised). PURE."""
    source, value = label_source(kind, values)
    if source in _NAME_FIELDS:
        names = [n for n in (p.strip() for p in _depth0_split(value, _NAME_SEPARATOR_RE)[::2]) if n]
        short = _label_name(names[0]) if names else ""
        if len(names) > 2:
            short += " et~al."
        elif len(names) == 2:
            short += " et~al." if names[1] == "others" else " and " + _label_name(names[1])
    elif source == "key":
        short = value.strip()
    elif source == "organization":
        short = _text_prefix(_chop_the(value))[0]
    else:
        short = _key_prefix(cite_key)[0]
    year = values.get("year", "").strip()
    if not year or short == values.get("key", "").strip():
        year = ""
    return short, year


def crowded_labels(entries) -> dict[str, list[str]]:
    """The citation labels more than :data:`_MAX_LABEL_LETTERS` of ``entries`` (``(kind, cite
    key, values)`` each, as :func:`natbib_label` takes them) share, as ``"Names (year)"`` with
    the keys that have it, in order. PURE."""
    groups: dict[tuple[str, str], list[str]] = {}
    for kind, key, values in entries:
        groups.setdefault(natbib_label(kind, key, values), []).append(key)
    return {
        (short + (f" ({year})" if year else "")): keys
        for (short, year), keys in groups.items()
        if len(keys) > _MAX_LABEL_LETTERS
    }


def _label_part(name: str) -> str:
    """What of one name natbib's label can hold: before its first brace-level-0 comma (the
    von and last names), else all of it. PURE."""
    parts = _depth0_split(name, _COMMA_RE)
    return parts[0].strip() if len(parts) > 1 else name.strip()


def _label_text_issues(field: str, text: str, length: int) -> list[str]:
    """What natbib cannot read in ``text``, a part of a citation label from field ``field``
    (``length``: the characters it puts there, measured as the copy measures them)."""
    issues: list[str] = []
    depth = 0
    seen: set[str] = set()
    for i, c in enumerate(text):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 0 and c in "[]" and c not in seen:
            seen.add(c)
            issues.append(f"field '{field}' has '{c}' at brace level 0, which ends natbib's "
                          f"citation label: put it in braces ({{{c}}})")
        elif depth == 0 and c == "(" and "(" not in seen:
            j = i + 1
            while j < len(text) and text[j] in _TEX_SPACE:
                j += 1
            after = text[j] if j < len(text) else ""
            if not (after.isascii() and (after.isalnum() or after == ")")):
                seen.add("(")
                what = repr(after) if after else "nothing"
                issues.append(
                    f"field '{field}' has a '(' at brace level 0 followed by {what}: natbib "
                    "reads the citation label up to the first '(' as the names and the rest as "
                    "the year, and stops ('Improper alphabetic constant'): put the parenthesis "
                    "in braces ({(})"
                )
    if length > _MAX_NAME:
        issues.append(f"field '{field}' puts {length} characters into natbib's citation label "
                      "(BibTeX cuts a label at 250, braces and all, and natbib stopped on the "
                      f"cut): at most {_MAX_NAME}")
    return issues


def label_issues(kind: str, cite_key: str, values: dict[str, str]) -> list[str]:
    """What natbib cannot read in the citation label plainnat makes of an entry of type
    ``kind`` with key ``cite_key`` (``values``: its fields as BibTeX prints them, with those it
    inherits through a crossref), one phrase each: a '(' or a bracket at brace level 0 of the
    names or key the label holds, a label part longer than :data:`_MAX_NAME` characters, an
    unsafe three-character prefix (:func:`unsafe_label`), a year that is not plain text. The
    canonical copy never has one (it braces, shortens, writes a key field and a plain year).
    PURE."""
    issues: list[str] = []
    source, value = label_source(kind, values)
    if source in _NAME_FIELDS:
        names = [n for n in (p.strip() for p in _depth0_split(value, _NAME_SEPARATOR_RE)[::2]) if n]
        for name in names[: 2 if len(names) == 2 else 1]:
            issues += _label_text_issues(source, _label_part(name), len(_last_name(name)))
    elif source == "key":
        issues += _label_text_issues("key", value.strip(), len(value.strip()))
    label = _label_key(kind, cite_key, values)
    if label is not None:
        text, what, prefix = label
        lacking = " or ".join(_LABEL_ORDER.get(kind, _DEFAULT_LABEL_ORDER))
        issues.append(
            f"has no {lacking}, so plainnat labels it by the first three characters of its {what} "
            f"({prefix!r}), which natbib cannot read in a citation label (they cut an escape, "
            f"math or a letter in two, or hold '_'): add a key field of plain letters (key = "
            f"{{{text}}})"
        )
    year = values.get("year")
    if year is not None:
        plain = _plain_text(year, _year_char)
        if plain != " ".join(year.replace("{", "").replace("}", "").split()) or len(plain) > _MAX_YEAR:
            issues.append(
                f"has the year {year!r}: natbib reads the year into its citation label, as plain "
                f"text of at most {_MAX_YEAR} characters (a command, math or a group there stopped "
                "natbib with 'Improper alphabetic constant'): write it as plain text"
            )
    return issues


def entry_issues(kind: str, key: str) -> list[str]:
    """What BibTeX or a citation cannot take in an entry's type ``kind`` (lower case) or key, one
    phrase each: a key a citation cannot name (see :data:`_KEY_ASCII`; a backslash in one is
    read as TeX in the ``.aux``), a type named like a function of the styles
    (:data:`STYLE_FUNCTION_NAMES`). PURE."""
    issues: list[str] = []
    if not _key_ok(key):
        issues.append(f"has the key {key[:80]!r}, which a citation cannot name: "
                      f"{_key_problem(key)}")
    if kind in STYLE_FUNCTION_NAMES:
        issues.append(f"has the type @{kind}, the name of a function of the standard BibTeX styles "
                      "(BibTeX runs that function instead of printing the entry, and stopped): "
                      "write it @misc")
    return issues


def case_change_issues(name: str, value: str) -> list[str]:
    """What BibTeX's ``change.case$`` would alter in field ``name`` (one a style changes the case
    of: title, edition, type) as BibTeX prints it, each once: at brace level 0, a control word
    holding a capital letter (``\\LaTeX`` -> ``\\latex``, undefined; ``\\S`` -> ``\\s``; the
    letters ``\\AE`` ``\\O`` ... only lower their own case) and a capital letter in math
    (``$\\Delta$`` -> ``$\\delta$``, ``$T$`` -> ``$t$``). A brace group is left alone, so the
    copy, which braces every kept command and its math, never has one. PURE."""
    if name not in _CASE_CHANGED_FIELDS:
        return []
    found: list[str] = []
    math = False
    for tok in _tex_tokens(value)[0]:
        if tok[0] == "c" and tok[1] == "$":
            math = not math
        elif tok[0] == "s" and tok[1] in "()[]":
            math = tok[1] in "(["
        elif tok[0] == "w" and any(c.isupper() for c in tok[1]):
            if math or tok[1] not in _LETTER_PAIRS:
                found.append("\\" + tok[1])
        elif math and tok[0] == "c" and tok[1].isascii() and tok[1].isupper():
            found.append(f"the capital {tok[1]!r} in math")
    return list(dict.fromkeys(found))


class _Entry(NamedTuple):
    """One entry of the canonical copy before it is written out."""

    kind: str
    key: str
    lines: list[str]
    written: dict[str, str]


def _entry_text(entry: _Entry) -> str:
    body = ",\n".join(entry.lines)
    return f"@{entry.kind}{{{entry.key},\n" + (body + "\n" if body else "") + "}\n"


def _with_label_key(entry: _Entry, values: dict[str, str], notes: list[str]) -> _Entry:
    """``entry`` with a key field when its label would be an unsafe prefix (:func:`_label_key`;
    ``values``: its fields with those it inherits through a crossref)."""
    label = _label_key(entry.kind, entry.key, values)
    if label is None:
        return entry
    text, what, prefix = label
    notes.append(
        f"entry '{entry.key}': plainnat labels it by the first three characters of its {what} "
        f"({prefix!r}), which natbib cannot read in a citation label; written with key = "
        f"{{{text}}}, so the paper cites it as '{text}' (plainnat cites an entry labelled by its "
        f"key without a year); {_STORE}"
    )
    lines = [line for line in entry.lines if not line.startswith("  key = ")]
    return _Entry(entry.kind, entry.key, lines + [f"  key = {{{text}}}"],
                  {**entry.written, "key": text})


def _canonical_entry(
    bib: str, command: BibCommand, key: str, macros: dict[str, str], notes: list[str],
    keys: set[str],
) -> _Entry:
    """One entry in canonical form (see :func:`canonical_bib`); ``keys`` are the keys of the
    entries the copy holds (ASCII lower case), which a crossref must name."""
    where = f"entry '{key}'"
    written: dict[str, str] = {}
    kept: dict[str, _Field] = {}
    for field in command.fields[:-1] if command.bad_last else command.fields:
        if field.name and field.name not in kept:
            kept[field.name] = field  # BibTeX keeps the first of a repeated field
    doi_field = kept.get("doi")
    doi_value = (
        _expanded(bib, doi_field, macros, [], where) if doi_field is not None else None
    )
    lines: list[str] = []
    printed: list[str] = []
    for name, field in kept.items():
        if not _FIELD_NAME_RE_OK.fullmatch(name) or not printed_field(name):
            continue
        if name in _OMITTED_FIELDS:
            continue
        if name == "month" and (macro := _bare_month(bib, field, macros)) is not None:
            lines.append(f"  month = {macro}")
            continue
        value = _expanded(bib, field, macros, notes, f"{where} field '{name}'")
        if name == "crossref":
            target = value.strip()
            if _key_ok(target) and _ascii_lower(target) in keys:
                lines.append(f"  crossref = {{{target}}}")
                written[name] = target
            else:
                notes.append(f"{where}: its crossref {target!r} is left out -- no entry of the "
                             "bibliography has that key, and BibTeX stops on a cross reference "
                             f"to none; {_STORE}")
            continue
        if name == "doi":
            doi = _canonical_doi(value)
            if doi is not None:
                lines.append(f"  doi = {{{doi}}}")
            else:
                notes.append(
                    f"{where}: its doi {' '.join(value.split())!r} is left out of the paper's "
                    "bibliography -- a doi there is 10.<registrant>/<suffix of printable ASCII "
                    f"without white space, braces, backslash, % # or ^>; {_STORE}"
                )
            continue
        if name == "url":
            url = " ".join(value.split())
            if _repeats_doi(url, doi_value):
                continue  # the entry's own doi.org link: the doi is printed already
            if plain_url(url):
                lines.append(f"  url = {{{url}}}")
            else:
                notes.append(
                    f"{where}: its url {url[:200]!r} is left out of the paper's bibliography -- a "
                    f"url there is http, https or ftp, at most {_MAX_URL} characters, with no white "
                    f"space, backslash, brace, % # or ^ (hyperref reads a URL as TeX); {_STORE}"
                )
            continue
        text, issues, field_notes = _settled(name, value, f"{where} field '{name}'")
        printed.extend(issue for issue in issues if issue.startswith("\\"))
        notes.extend(f"{where} field '{name}': {issue}; {_STORE}"
                     for issue in issues if not issue.startswith("\\"))
        notes.extend(field_notes)
        lines.append(f"  {name} = {{{text}}}")
        written[name] = text
    if printed:
        notes.append(
            f"{where}: {', '.join(dict.fromkeys(printed))} printed as text in the paper's "
            "bibliography -- outside the commands a reference list may hold (accents, letters, "
            f"text symbols, simple markup, math without amsmath); {_STORE}"
        )
    kind = command.command if command.command in _STANDARD_TYPES else "misc"
    return _Entry(kind, key, lines, written)


# @MX:ANCHOR: [AUTO] The one writer of a bibliography sci-adk ships, and the form verify demands.
# @MX:REASON: callers: paper_bib (render's paper/references.bib, the SI subset, the deposit and
#   the package SI copies), pkgreqs_checks.bib_form_problems (verify: text == paper_bib(text)),
#   compiler (its notes become render warnings); a change re-forms every shipped bibliography
#   and fails verify on each one rendered before it, until re-rendered.
def canonical_bib(bib: str) -> CanonicalBib:
    """``bib`` as the paper's bibliography: every entry BibTeX reads, in order, as
    ``@type{key,\\n  field = {value},\\n  ...\\n}``, entries one blank line apart. PURE;
    idempotent (``canonical_bib(text).text == text`` for its own output; each value is written
    again until it is, :func:`_settled`).

    Read as BibTeX reads it (:func:`bib_commands`): a parenthesised entry, ``@ article``, a
    syntax error (what BibTeX read before it is kept, and noted; a field whose value failed is
    not), a @string whose definition failed (the macro is its own name), a repeated field (the
    first is kept) or key (the first entry is kept, ASCII case ignored). ``@string`` macros are
    expanded, ``#`` parts joined, ``@preamble``, ``@comment`` and the text between entries left
    out; the entry type is lower case (``misc`` when it is not one of :data:`_STANDARD_TYPES`),
    field names too.

    Fields: no style prints the :data:`UNPRINTED_FIELDS` and the ISSN beside the DOI, so they
    are left out, and so is a url that is the doi.org link of the entry's doi. A bare month
    macro stays a macro (``month = jan``; an undefined month name becomes one). ``url`` and
    ``doi`` are kept only when plain (:func:`plain_url`, ``paper.is_doi``; a doi.org prefix is
    dropped from a doi), ``crossref`` only when it names an entry of the copy. Every other value
    is made LaTeX-safe (:func:`latex_safe_bib`'s character and markup policy), then written with
    the allow-listed commands only (:data:`TEXT_COMMANDS`, :data:`MATH_COMMANDS`): each kept
    command and its arguments in a brace group BibTeX treats as one special character, so its
    case change cannot alter it; math as ``{$...$}`` (``\\(...\\)`` and ``\\[...\\]`` too; empty
    math is left out), every script argument braced and a second script on one base given an
    empty base; a math command in running text in math; a text command in math in an
    ``\\mbox``; ``[`` and ``]`` at brace level 0 in braces (natbib reads a label up to the first
    ``]``); any other command printed as text (``{\\textbackslash}name``, boxed in math). Titles
    keep the case the source gives (:func:`_protect_case`); names are tidied, sort by their base
    letters (:func:`_tidy_names`) and are kept to what BibTeX and natbib read
    (:func:`_safe_names`); a year is plain text (:func:`_plain_year`). Limits keep a value within
    TeX and BibTeX (braces 50 deep, 3 nested accents, a word of 10000 and a value of 100000
    characters) and pdflatex's time bounded: no link inside a link, math commands with
    arguments at most 4 deep (no arrow accent inside one, no root with an index inside a root)
    and at most 32 in a value, text markup at most 8 deep; past a limit a command is printed as
    text.

    An entry whose key is not one a ``\\cite`` can name (one starting with a character outside
    ASCII or longer than 200 characters too) is left out. Each entry, field or macro left out
    or changed, each command printed as text, and each citation label more than 26 entries
    share (natbib stops on the 27th cited; not rewritten) is named in
    :attr:`CanonicalBib.notes`.
    """
    commands = bib_commands(bib)
    keys = {
        _ascii_lower(c.key) for c in commands
        if c.command not in ("string", "preamble") and not c.repeated and _key_ok(c.key or "")
    }
    macros: dict[str, str] = {}
    notes: list[str] = []
    entries: list[str] = []
    line, counted = 1, 0  # the line a command ends on, counted on as the commands come
    for command in commands:
        if command.command == "preamble":
            continue
        if command.command == "string":
            _define(bib, command, macros, notes)
            if command.bad_last and command.fields and command.fields[0].name:
                name = command.fields[0].name
                notes.append(f"@string '{name}' has a syntax error, so BibTeX defines the macro "
                             f"as its own name: a field naming it prints '{name}'; {_STORE}")
            continue
        key = command.key or ""
        if command.repeated:
            notes.append(
                f"entry '{key}' is left out of the paper's bibliography: it repeats the key of an "
                f"earlier entry, and BibTeX keeps the first (it reads nothing after this one's "
                f"key); {_STORE}"
            )
            continue
        if not _key_ok(key):
            notes.append(
                f"entry {key!r} is left out of the paper's bibliography: {_key_problem(key)}; "
                f"{_STORE}"
            )
            continue
        if not command.complete:
            fields = command.fields[:-1] if command.bad_last else command.fields
            read = len([f for f in fields if f.name])
            line += bib.count("\n", counted, command.end)
            counted = command.end
            notes.append(
                f"entry '{key}' has a BibTeX syntax error near line {line}: BibTeX stops reading "
                "it there, so the copy keeps "
                + (f"the {read} field(s) read before it" if read else "none of its fields")
                + f"; {_STORE}"
            )
        entries.append(_canonical_entry(bib, command, key, macros, notes, keys))
    entries = _labelled(entries, notes)
    notes.extend(_crowded_label_notes(entries))
    return CanonicalBib("\n".join(_entry_text(e) for e in entries), tuple(dict.fromkeys(notes)))


def _crowded_label_notes(entries: list[_Entry]) -> list[str]:
    """One note per citation label more than :data:`_MAX_LABEL_LETTERS` entries share
    (:func:`crowded_labels`; a crossref child judged with what it inherits)."""
    by_key = {_ascii_lower(e.key): e.written for e in entries}
    rows = []
    for e in entries:
        values = e.written
        if "crossref" in values:
            values = {**by_key.get(_ascii_lower(values["crossref"]), {}), **values}
        rows.append((e.kind, e.key, values))
    notes = []
    for label, keys in crowded_labels(rows).items():
        shown = ", ".join(keys[:5]) + (", ..." if len(keys) > 5 else "")
        notes.append(
            f"{len(keys)} entries share the citation label {label!r} ({shown}): plainnat tells "
            "entries with one label apart by a letter after the year, a to z, and natbib stops "
            f"when more than {_MAX_LABEL_LETTERS} of them are cited ('Paragraph ended before "
            "\\@lbibitem was complete'); the copy leaves them as they are -- cite at most "
            f"{_MAX_LABEL_LETTERS} of them, or tell them apart by author or year; {_STORE}"
        )
    return notes


def _labelled(entries: list[_Entry], notes: list[str]) -> list[_Entry]:
    """``entries`` with a key field where plainnat's label would be an unsafe prefix. An entry
    with a crossref is judged with the fields it inherits (BibTeX copies each field the entry
    lacks from the entry it names), after that entry got its own key."""
    out = [e if "crossref" in e.written else _with_label_key(e, e.written, notes)
           for e in entries]
    by_key = {_ascii_lower(e.key): e.written for e in out}
    for k, e in enumerate(out):
        if "crossref" in e.written:
            parent = by_key.get(_ascii_lower(e.written["crossref"]), {})
            out[k] = _with_label_key(e, {**parent, **e.written}, notes)
    return out


# @MX:NOTE: [AUTO] What render writes into paper/ (references.bib, the SI subset, the deposit copy)
# and the package's SI cut; the store keeps the acquired bytes and its keys.
def paper_bib(bib: str) -> str:
    """The bibliography a rendered paper loads: :func:`canonical_bib` of ``bib``, its text.
    PURE; keys never change (an entry is kept with its key, or left out); idempotent."""
    return canonical_bib(bib).text


__all__ = [
    "BibCommand",
    "CanonicalBib",
    "HTML_ENTITY_RE",
    "HTML_TAG_RE",
    "MATH_COMMANDS",
    "MAX_EXPANDED",
    "STYLE_FUNCTION_NAMES",
    "T1_ONLY_CHARS",
    "TEXT_COMMANDS",
    "UNPRINTED_FIELDS",
    "VERBATIM_FIELDS",
    "accented_letters_in_math",
    "bare_specials",
    "bib_commands",
    "bib_syntax_issues",
    "canonical_bib",
    "caret_notation",
    "case_change_issues",
    "command_issues",
    "crowded_labels",
    "entry_issues",
    "field_value_spans",
    "field_values",
    "html_tags",
    "label_issues",
    "label_source",
    "natbib_label",
    "paper_bib",
    "plain_url",
    "printed_field",
    "raw_sort_letter",
    "script_issues",
    "sort_letter_command",
    "stray_math_dollar",
    "string_macros_used_as_urls",
    "typesettable",
    "undefined_month_tokens",
    "unsafe_label",
    "untypesettable_chars",
    "url_arguments",
    "url_problems",
    "value_issues",
]
