"""
Render a paper draft (Markdown) from a Spec + its Claims + Evidence.

This is the *deterministic* renderer: it lays out the proposal, the per-hypothesis
findings (the Claims the DecisionEngine produced), the evidence trail, and any
pending agent judgments -- as a structured draft, with NO LLM prose (so it runs
at zero cost, design/tool-policy.md). Prose polishing, when wanted, is a separate
in-session agent step over this draft (never an autonomous claude -p call).

Authoring convention: the Spec proposal panes, the hypothesis statements and the
``PaperProse`` slots are TEXT, escaped into the ``.tex`` the author uploads to Overleaf
(default pdflatex) -- a LaTeX command written there prints as literal text (a prose slot
passes only the ``\\ref``/``\\cite`` family and ``\\paragraph``; render warns about any other).
Write a symbol as its Unicode character (``≥``, ``H₂O``, ``30 °C``) or in plain ASCII: the
sanitizer (:func:`_latex_sanitize`) maps the common scientific symbols to pdflatex-safe LaTeX
(``≥`` -> ``$\\geq$``, ``α`` -> ``$\\alpha$``), passes common European accents (Gödel, Erdős)
under ``utf8`` inputenc, and folds or placeholds any other non-ASCII codepoint (CJK, emoji:
``?``, named in a render warning) so it cannot break compilation.

Reference: design/directory-structure.md (render/), design/abstractions.md.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional, Sequence

from sci_adk.core.claim import RULE_CONFIDENCE_KINDS, Claim, ClaimStatus, ConfidenceType
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import DecisionRule, Hypothesis, Spec
from sci_adk.render.factref import _EVVAL_RE, _STATUS_RE, substitute_factrefs
from sci_adk.render.figures import (
    AnyFigure,
    order_figures_by_reference,
    render_figure,
)
from sci_adk.render.novelty import (
    NOVELTY_RENDER_RE,
    NoveltySentence,
    novelty_scope_suffix,
    require_novelty_text,
)
from sci_adk.render.prose import PaperProse, SIProse

# LaTeX special characters and their escaped forms. Several replacements (the
# backslash and the tilde/caret commands) themselves contain ``{}`` -- so a naive
# left-to-right ``str.replace`` per char corrupts them (escaping ``\`` first injects
# ``{}`` that the later ``{``/``}`` passes then re-escape). ``_latex_escape`` avoids
# this with a placeholder phase: each special maps to a brace-free sentinel first,
# then every sentinel is expanded to its final form in one last pass.
_LATEX_SPECIALS: list[tuple[str, str]] = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]

# A sentinel per special whose characters are NONE of the LaTeX specials, so it
# survives every replacement pass untouched. The sentinels use NUL-range bytes
# (\x00..\x01); ``_latex_escape`` STRIPS those bytes from its input before the
# sentinel phase (see below), making their absence a hard invariant rather than an
# assumption -- a corrupted NUL-bearing string can never collide with a sentinel and
# inject a spurious ``\textbackslash``.
_LATEX_SENTINELS: list[tuple[str, str, str]] = [
    (char, f"\x00{i}\x01", replacement)
    for i, (char, replacement) in enumerate(_LATEX_SPECIALS)
]


def _latex_escape(s: str) -> str:
    """Escape LaTeX special characters in ``s`` so interpolated content is faithful.

    Routes ``& % $ # _ { } ~ ^ \\`` to their LaTeX-safe forms via a two-phase
    placeholder substitution: each special is first mapped to a brace-free sentinel
    (so the braces inside ``\\textbackslash{}`` / ``\\textasciitilde{}`` etc. are not
    themselves re-escaped), then every sentinel is expanded to its final command in
    one pass. Plain text with no specials is returned unchanged, and a literal
    backslash followed by another special escapes faithfully
    (``\\&`` -> ``\\textbackslash{}\\&``, never a corrupted ``\\textbackslash\\{\\}``).

    Call exactly once per string at interpolation time; NOT idempotent -- never
    pre-escape (a second pass would turn ``\\&`` into ``\\textbackslash{}\\&``).

    This is load-bearing: EVERY interpolated string in the LaTeX output (titles,
    statements, rule expressions, findings, basis text, ids) MUST pass through here
    or the emitted .tex will not compile (or will silently corrupt content).
    """
    # Strip the sentinel bytes from the input first, so a (corrupted) NUL-bearing
    # string cannot collide with a sentinel and inject a spurious command. This turns
    # the sentinels' "absent from content" assumption into a hard invariant.
    s = s.replace("\x00", "").replace("\x01", "")
    for char, sentinel, _final in _LATEX_SENTINELS:
        s = s.replace(char, sentinel)
    for _char, sentinel, final in _LATEX_SENTINELS:
        s = s.replace(sentinel, final)
    return s


# Curated unicode -> pdflatex-safe LaTeX: how a scientific symbol written as its Unicode
# character (the authoring convention, module docstring) reaches Overleaf's default pdflatex
# as LaTeX. Math symbols use
# ``$...$`` (base LaTeX -- no amssymb needed for any entry here). Applied AFTER
# :func:`_latex_escape`, so the values here are final LaTeX and the ASCII keys are
# disjoint from the LaTeX specials the escaper handles.
_UNICODE_MAP: dict[str, str] = {
    # Subscripts 0-9 -> $_n$.
    "₀": "$_0$", "₁": "$_1$", "₂": "$_2$", "₃": "$_3$",
    "₄": "$_4$", "₅": "$_5$", "₆": "$_6$", "₇": "$_7$",
    "₈": "$_8$", "₉": "$_9$",
    # Superscripts -> $^n$ (the common digits/sign; 1/2/3 have legacy codepoints).
    "⁰": "$^0$", "¹": "$^1$", "²": "$^2$", "³": "$^3$",
    "⁴": "$^4$", "⁵": "$^5$", "⁶": "$^6$", "⁷": "$^7$",
    "⁸": "$^8$", "⁹": "$^9$", "⁺": "$^+$", "⁻": "$^-$",
    "ⁿ": "$^n$",
    # Relations / operators.
    "≥": r"$\geq$", "≤": r"$\leq$", "≠": r"$\neq$",
    "±": r"$\pm$", "×": r"$\times$", "÷": r"$\div$",
    "−": "$-$",  # U+2212 minus sign (was rendered as "?")
    "≈": r"$\approx$", "≡": r"$\equiv$", "∝": r"$\propto$",
    "·": r"$\cdot$", "∙": r"$\cdot$",
    # Big operators / analysis.
    "∞": r"$\infty$", "∑": r"$\sum$", "∏": r"$\prod$",
    "∫": r"$\int$", "√": r"$\surd$", "∂": r"$\partial$",
    "∇": r"$\nabla$",
    # Set relations.
    "∈": r"$\in$", "∉": r"$\notin$", "⊂": r"$\subset$",
    "⊆": r"$\subseteq$", "∪": r"$\cup$", "∩": r"$\cap$",
    # Arrows.
    "→": r"$\rightarrow$", "←": r"$\leftarrow$",
    "↔": r"$\leftrightarrow$", "⇒": r"$\Rightarrow$",
    "⇐": r"$\Leftarrow$",
    # Greek lowercase alpha..omega.
    "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$",
    "δ": r"$\delta$", "ε": r"$\epsilon$", "ζ": r"$\zeta$",
    "η": r"$\eta$", "θ": r"$\theta$", "ι": r"$\iota$",
    "κ": r"$\kappa$", "λ": r"$\lambda$", "μ": r"$\mu$",
    "ν": r"$\nu$", "ξ": r"$\xi$", "ο": "o",
    "π": r"$\pi$", "ρ": r"$\rho$", "σ": r"$\sigma$",
    "ς": r"$\varsigma$", "τ": r"$\tau$", "υ": r"$\upsilon$",
    "φ": r"$\phi$", "χ": r"$\chi$", "ψ": r"$\psi$",
    "ω": r"$\omega$",
    # Greek uppercase Alpha..Omega (the ones with distinct LaTeX commands; the rest
    # look like Latin capitals and fold cleanly via NFKD if they ever appear).
    "Γ": r"$\Gamma$", "Δ": r"$\Delta$", "Θ": r"$\Theta$",
    "Λ": r"$\Lambda$", "Ξ": r"$\Xi$", "Π": r"$\Pi$",
    "Σ": r"$\Sigma$", "Φ": r"$\Phi$", "Ψ": r"$\Psi$",
    "Ω": r"$\Omega$",
    # Micro sign + degree.
    "µ": r"$\mu$", "°": r"\textdegree{}",
    # Dashes, quotes, ellipsis.
    "–": "--", "—": "---",
    "‘": "`", "’": "'", "“": "``", "”": "''",
    "…": r"\ldots{}",
}

# The inputenc-safe accent window. ``\usepackage[utf8]{inputenc}`` (TeX Live /
# Overleaf) only defines codepoints up to ~U+017E -- the end of Latin Extended-A --
# so this window covers Latin-1 Supplement (U+00C0..U+00FF) + Latin Extended-A
# (U+0100..U+017E). These pass through unchanged under pdflatex, so common European
# accents stay correct (Gödel, Erdős, ł U+0142, ø) -- all but the eight letters of
# :data:`_UNDEFINED_LATIN_A`. Latin Extended-B and above
# (U+0180..U+024F: Romanian Ș U+0218 / Ț U+021A, ƒ U+0192, etc.) are NOT defined by
# inputenc and would abort pdflatex if passed raw, so they fall through to the
# NFKD-fold/placeholder path instead (Ș->S, Ț->T; ƒ and Ʒ have no ASCII fold -> ?).
_ACCENT_LO = 0x00C0
_ACCENT_HI = 0x017E
# The letters of that window LaTeX defines no glyph for (H and T with stroke, kra, L with
# middle dot, n preceded by apostrophe): pdflatex stops on each with "Unicode character ...
# not set up for use with LaTeX" under both render preambles (T1 with Latin Modern or Times;
# measured by compiling the whole window, TeX Live 2026). Maltese, Sami, Catalan and
# Afrikaans text holds them. They take the fold/placeholder path (Ħ -> ?, Ŀ -> L?,
# ŉ -> ?n). The bib copy's character policy (``bib_latex.typesettable``) uses this set.
_UNDEFINED_LATIN_A = frozenset("ĦħĸĿŀŉŦŧ")

# The font encoding every preamble sci-adk emits loads, right after inputenc (right after
# \documentclass where there is no inputenc line), followed by the text typeface. With
# inputenc alone pdflatex runs in OT1, where 22 letters and quotes of this window and of the
# bibliography's punctuation stop the compile (Ð þ Ą ę Ŋ Ų « » ‚ „ ...; measured, TeX Live
# 2026). T1 typesets them.
#
# The text typeface follows the figure font policy (design/paper-publishing-requirements.md
# F2). Where it applies, math is set in Times (newtxmath, emitted later with amsmath and the
# Arial-compatible sans), so the text is Times too (newtxtext, TeX Gyre Termes X): one
# typeface for body and equations. Elsewhere Latin Modern: T1 vector fonts without cm-super,
# the Computer Modern design.
T1_FONT_LINES: tuple[str, str] = (r"\usepackage[T1]{fontenc}", r"\usepackage{lmodern}")
TIMES_FONT_LINES: tuple[str, str] = (r"\usepackage[T1]{fontenc}", r"\usepackage{newtxtext}")

# hyperref without coloured boxes around every citation, reference and URL.
HYPERREF_LINE = r"\usepackage[hidelinks]{hyperref}"


# @MX:ANCHOR: [AUTO] The one choice of text typeface every per-run preamble makes.
# @MX:REASON: callers render_paper_latex, si.render_si_latex and
# authored_si.render_authored_si_latex; pubreqs_checks.figure_font_policy_problems requires
# newtxtext where the policy applies, and the compile tests check typesettable() against both
# faces -- change all of them together.
def text_font_lines(font_policy: bool) -> tuple[str, str]:
    """The T1 + text-typeface preamble lines: Times (:data:`TIMES_FONT_LINES`) for a document
    the figure font policy applies to, Latin Modern (:data:`T1_FONT_LINES`) otherwise. PURE."""
    return TIMES_FONT_LINES if font_policy else T1_FONT_LINES


def font_policy_applies(figures: Sequence[AnyFigure]) -> bool:
    """True iff the figure font policy applies to a document carrying ``figures``: it has a
    native or an image figure. PURE."""
    return any(f.kind in ("native", "image") for f in figures)


def run_font_policy(
    draft_figures: Sequence[AnyFigure], si_figures: Sequence[AnyFigure] = ()
) -> bool:
    """The figure font policy for a whole run: True iff the draft OR the authored SI
    carries a figure. Decided once, so ``draft.tex`` and ``si.tex`` -- submitted together --
    always share :func:`text_font_lines` (a run whose only figure is in the SI used to pair
    a Latin Modern draft with a Times SI). PURE."""
    return font_policy_applies(list(draft_figures) + list(si_figures))

# Replacement for a non-ASCII codepoint that is neither curated nor an inputenc-safe
# accent and does not NFKD-fold to ASCII (e.g. CJK, emoji): a safe placeholder so the
# document still compiles. ``?`` is ASCII and not a LaTeX special.
_UNICODE_PLACEHOLDER = "?"

# The C0 control characters other than tab and line feed, and DEL: pdflatex stops on each of
# them in any slot (an invalid character; a form feed is an \outer \par that ends the
# argument it sits in). A carriage return is a line end: :func:`_clean_text` turns it into a
# line feed before this set is removed.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean_text(s: str) -> str:
    """``s`` with its line ends normalized (CRLF and a lone CR -> LF) and every C0 control
    character other than tab and LF, and DEL, removed (:data:`_CONTROL_RE`).

    The first step of both sanitizers and of every decision taken on prose before it is
    sanitized (the heading refusal, the fact-macro and novelty matches, the literal-command
    warnings), so each decision sees the text the sanitizer sees: a control character can
    neither hide a command from a check nor end up in a key or a heading. C1 controls
    (U+0080..U+009F) are left to the unicode fold, which makes each the placeholder.
    Idempotent. PURE."""
    return _CONTROL_RE.sub("", s.replace("\r\n", "\n").replace("\r", "\n"))


def _one_line(s: str) -> str:
    """``s`` cleaned (:func:`_clean_text`) with every whitespace run -- line breaks and blank
    lines included -- collapsed to one space and none at either end: for a title, the author
    and a section title, each one macro argument to pdflatex (a blank line in ``\\author{}``
    stops it with "Paragraph ended before \\author was complete"). PURE."""
    return " ".join(_clean_text(s).split())


def _latex_sanitize(s: str) -> str:
    """Escape LaTeX specials AND fold unicode to pdflatex-safe LaTeX (the safety net).

    Order-critical:

    1. :func:`_clean_text` -- line ends normalized; C0 controls other than tab and LF, and
       DEL, removed (pdflatex stops on them).
    2. :func:`_latex_escape` -- neutralizes the ASCII specials ``& % $ # _ { } ~ ^ \\``
       while the text is still raw (no LaTeX commands of ours present yet, so nothing we
       emit later gets double-escaped).
    3. Then, per remaining non-ASCII character: a curated scientific symbol maps to its
       LaTeX form via :data:`_UNICODE_MAP` (e.g. ``≥`` -> ``$\\geq$``, ``₂`` -> ``$_2$``,
       ``α`` -> ``$\\alpha$``); an inputenc-safe accent (U+00C0..U+017E, e.g. ``ö``)
       passes through unchanged, except the eight letters LaTeX has no glyph for
       (:data:`_UNDEFINED_LATIN_A`, e.g. Maltese ``Ħ``); any other codepoint -- including Latin Extended-B (U+0180+,
       e.g. Romanian ``Ș``/``Ț``) which inputenc does NOT define -- is NFKD-normalized with
       combining marks stripped, and every ASCII character the fold yields is escaped like
       any other text (:func:`_latex_escape`). That matters: a fullwidth or small-form
       special (U+FF3C fullwidth backslash, U+FF06 ``&``, U+FE5F ``#``, ...) folds to its
       ASCII special, so the fullwidth backslash prints as ``\\textbackslash{}`` and never
       acts as one. A fold that is STILL non-ASCII (CJK, emoji, C1 controls) is replaced with
       :data:`_UNICODE_PLACEHOLDER`.

    The fold is per character and comes after the curated map: normalizing the whole input
    up front would turn ``₂`` into ``2`` and ``…`` into ``...`` before the map could give
    ``$_2$`` and ``\\ldots{}``.

    Result: every codepoint is printable ASCII, a tab, a line feed or an inputenc-safe
    accent, and every special is escaped, so the emitted .tex compiles under Overleaf's
    default pdflatex and prints the text as written (a character with no form prints as
    ``?``; :func:`placeholder_warnings` names it).

    Replaces :func:`_latex_escape` at EVERY interpolation point in the LaTeX renderer.
    Like ``_latex_escape`` it is NOT idempotent -- call exactly once per string.
    """
    escaped = _latex_escape(_clean_text(s))
    return "".join(ch if ord(ch) < 0x80 else _fold_non_ascii(ch)[0] for ch in escaped)


def _fold_non_ascii(ch: str) -> tuple[str, bool]:
    """What :func:`_latex_sanitize` writes for one non-ASCII character ``ch``, and whether any
    part of it is :data:`_UNICODE_PLACEHOLDER` (the character, or part of it, has no form
    pdflatex typesets -- what :func:`placeholder_warnings` names). PURE."""
    mapped = _UNICODE_MAP.get(ch)
    if mapped is not None:
        return mapped, False
    if _ACCENT_LO <= ord(ch) <= _ACCENT_HI and ch not in _UNDEFINED_LATIN_A:
        # Common European accent: inputenc renders it under pdflatex. Keep it.
        return ch, False
    # Fold via NFKD (drops combining marks); keep the ASCII fallout, escaped (an astral-plane
    # math letter folds to its base Latin letter, a fullwidth special to the special itself),
    # placehold the rest.
    out: list[str] = []
    placeheld = False
    for f in unicodedata.normalize("NFKD", ch):
        if ord(f) < 0x80:
            out.append(_latex_escape(f))
        elif unicodedata.combining(f):
            continue  # drop combining marks
        else:
            out.append(_UNICODE_PLACEHOLDER)
            placeheld = True
    return "".join(out), placeheld


# The EXACT allowlist of LaTeX cross-reference / citation commands that
# :func:`_latex_sanitize_prose` lets through verbatim. Each is of the form
# ``\cmd{<key>}`` with ONE key of label characters (:data:`_KEY`: ``fig:water``,
# ``Smith2020a``, ``a, b``) -- exactly what an author writes to reference a figure or cite a
# paper. With the ``\paragraph`` heading below, it is the ONLY LaTeX that survives a prose
# slot. A non-allowlisted command (``\textbf{...}``, ``\input{...}``), every stray special
# (``&`` ``%`` ``_`` ``$``) and an allowlisted command whose key holds anything else stay
# escaped, so nothing in a prose slot reaches TeX as a command, a special or a raw
# non-ASCII character except these spans. ``\eqref`` is not on the list: prose cannot carry
# an equation and a figure-less draft loads no amsmath, so an ``\eqref`` in prose could
# never resolve. (A key may still name a label or a bib entry that does not exist: pdflatex
# warns and prints ``??``.)
#
# The key is whitelisted, not merely brace-free: TeX reads it inside ``\csname``, so a
# backslash in it runs a command (the ``\input`` in ``\ref{\input <file> }`` was run),
# ``%`` ``#`` ``$`` ``&`` ``^`` ``~`` stop pdflatex, and so does a non-ASCII letter (inputenc
# makes it a command: Cyrillic, Greek, ``Ș``, a fullwidth form). The empty key ``\ref{}``
# is matched too, so it is preserved rather than half-escaped. A key may hold a single line
# break but not a blank line: ``\citep{a,<blank line>b}`` stops pdflatex with "Paragraph
# ended before \@citex was complete". A key outside the set does not match and stays
# literal text, which :func:`literal_command_warnings` names. ``\b``-free by
# construction: the command names are immediately followed by ``{`` so ``\reference{}`` is
# NOT matched (the name alternation requires the literal ``{`` next), nor is a cite with an
# optional argument (``\citep[e.g.][]{k}``).
#
# The second alternative is the one STRUCTURAL command prose may carry: a run-in paragraph
# heading ``\paragraph{<text>}`` (a Methods/Results lead-in label such as ``Data.`` or
# ``Slope.``). Unlike a reference key its argument is reader-facing TEXT, so it is captured
# (group 1) and sanitized like any other prose -- only the command and its braces pass
# verbatim. Brace-free text only: a heading carrying another command (``\textbf{...}``) does
# not match and stays literal text, so the heading cannot smuggle LaTeX past the allowlist.
# Not matched: ``\paragraph*``, ``\subparagraph`` (no backslash right before ``paragraph``),
# ``\paragraphs``. The authored SI body is verbatim LaTeX and carries ``\paragraph`` as is,
# so a lead-in renders the same in draft.tex and si.tex.
#
# The heading text, like a key, may hold single line breaks but never a paragraph break,
# so ``\paragraph{a<blank line>b}`` -- which stops pdflatex with "Paragraph ended before
# \@sect was complete" -- is not a heading and stays literal text. A heading that passes is
# written on one line (its whitespace runs collapsed), so a line holding only Unicode spaces
# or combining marks, which folds to a blank line, never reaches TeX inside the argument.
# A heading is valid only
# inside a section: :func:`render_paper_latex` refuses one in the abstract and in the title
# (:data:`_HEADINGLESS_SLOTS`). Whatever does not pass prints as literal text, and render
# names the command (:func:`literal_command_warnings`).
#
# Brace-free text on one paragraph: a newline passes only when the next line is not blank
# (TeX ends a paragraph at a line holding only spaces or tabs too).
_ONE_PARAGRAPH = r"(?:[^{}\n]|\n(?![ \t\r]*\n))*"
# A reference or citation key: ASCII letters, digits, ``: _ . , ; + / = @ -``, spaces and
# tabs, and single line breaks.
_KEY = r"(?:[A-Za-z0-9:_.,;+/=@ \t-]|\n(?![ \t\r]*\n))*"
_PARAGRAPH_HEADING_RE = re.compile(r"\\paragraph\{(" + _ONE_PARAGRAPH + r")\}")
_PROSE_PASSTHROUGH_RE = re.compile(
    r"\\(?:ref|autoref|cite|citep|citet)\{" + _KEY + r"\}"
    r"|" + _PARAGRAPH_HEADING_RE.pattern
)
# The slots a run-in heading cannot stand in: the abstract (a list environment in the article
# class -- ``\begin{abstract}\paragraph{..}`` stops pdflatex with "Something's wrong--perhaps
# a missing \item") and the title (not a prose slot: the command would print as literal text).
_HEADINGLESS_SLOTS = ("title", "abstract")


def _latex_sanitize_prose(s: str) -> str:
    """Sanitize an agent-authored PROSE slot, PRESERVING ref/cite commands verbatim.

    The prose-only variant of :func:`_latex_sanitize`. Every prose slot
    (``PaperProse`` abstract/introduction/discussion, ``SIProse`` overview/notes) is the
    one place an author legitimately writes real LaTeX: ``\\ref{fig:<id>}`` to point at a
    figure and ``\\cite{<key>}`` to cite literature. The plain ``_latex_sanitize`` would
    escape those to literal text (``\\ref{fig:x}`` -> ``\\textbackslash{}ref\\{fig:x\\}``),
    which is why the body-order figure numbering (:func:`figures.order_figures_by_reference`,
    which scans the body for ``\\ref{fig:<id>}``) silently fell back to supply order --
    it never saw a real ref. This function closes that gap by letting EXACTLY the five
    allowlisted commands (:data:`_PROSE_PASSTHROUGH_RE`: ``\\ref``, ``\\autoref``,
    ``\\cite``, ``\\citep``, ``\\citet``, each with one key of label characters,
    :data:`_KEY`) through unchanged while still fully sanitizing everything else. One
    structural command
    is allowed besides them: a run-in heading ``\\paragraph{<text>}`` (a Methods/Results
    lead-in label), whose command and braces pass while its brace-free ``<text>`` is
    sanitized like the rest of the prose.

    Implementation: a SPLIT-and-stitch (collision-proof BY CONSTRUCTION -- no placeholder
    that could collide with content, and nothing of ours is routed back through the
    escaper). :func:`re.Match`/:func:`re.split`-style alternation walks ``s`` and carves it
    into segments separated by the allowlisted spans; only the SEGMENTS between/around the
    spans pass through the EXISTING :func:`_latex_sanitize` (specials escaped + unicode
    folded exactly as the non-prose path), while each allowlisted span is concatenated back
    VERBATIM. The label/key INSIDE ``{...}`` is therefore never escaped: it is a reference
    key (``fig:a_b``, ``Smith2020``), so an underscore there survives as ``_`` for the
    ``\\ref`` to resolve, not become ``\\_``.

    Why split rather than the sentinel trick :func:`_latex_escape` uses: ``_latex_escape``
    (called inside ``_latex_sanitize``) STRIPS the ``\\x00``/``\\x01`` sentinel bytes from
    its input as a hard collision-proofing invariant, so a placeholder routed THROUGH it
    would be destroyed. Splitting keeps the preserved spans entirely OUT of the escaper's
    path -- the same collision-proofing goal, reached without fighting that invariant.

    Safety boundary: ONLY the allowlist passes. A non-allowlisted command stays escaped
    (``\\textbf{x}`` -> literal ``\\textbackslash{}textbf\\{x\\}``) and a stray ``&`` / ``%``
    outside a preserved span is still escaped -- so prose cannot smuggle arbitrary LaTeX
    or unbalanced specials past the renderer. The ``\\paragraph`` heading text is escaped
    too (``\\paragraph{95% kept.}`` -> ``\\paragraph{95\\% kept.}``), and a heading holding
    braces (another command) or a blank line is not a heading at all, and neither is a key
    spanning a blank line or holding anything but label characters (``\\cite{a#b}``,
    ``\\ref{\\input x }``, ``\\cite{Ж}``): the whole construct stays literal (render
    names the command,
    :func:`literal_command_warnings`). This function does not know its slot: the abstract and
    the title, which take no heading, are refused by :func:`render_paper_latex` before they
    get here. The text is cleaned first (:func:`_clean_text`), before the allowlist is
    matched, so no key and no heading text carries a control character.

    PURE + deterministic. Like ``_latex_sanitize`` it is NOT idempotent -- a second pass
    would re-escape the (now bare) preserved commands. Call exactly once, on prose only.
    """
    s = _clean_text(s)
    out: list[str] = []
    pos = 0
    # Walk every allowlisted span in order; sanitize the gap BEFORE it, then append the
    # span itself verbatim. The trailing gap (after the last span) is handled below. A
    # string with no allowlisted span never enters the loop -> falls straight to the final
    # _latex_sanitize, i.e. identical to the non-prose path.
    for match in _PROSE_PASSTHROUGH_RE.finditer(s):
        out.append(_latex_sanitize(s[pos : match.start()]))  # gap -> fully sanitized
        heading = match.group(1)
        if heading is None:
            out.append(match.group(0))                        # \cmd{key} -> verbatim
        else:                                                 # \paragraph{text}: text is prose
            # On one line (_one_line): a line that holds only Unicode spaces or combining
            # marks passes the blank-line rule as written but folds to a blank line, which
            # stops pdflatex inside the macro argument.
            out.append(r"\paragraph{" + _latex_sanitize(_one_line(heading)) + "}")
        pos = match.end()
    out.append(_latex_sanitize(s[pos:]))  # trailing gap (or the whole string if no spans)
    return "".join(out)


def _shown(text: str, limit: int = 40) -> str:
    """``text`` cut to ``limit`` characters, whitespace runs collapsed: a span quoted in a
    message on one line."""
    cut = text[:limit]
    return " ".join(cut.split()) + ("..." if len(text) > limit else "")


def _refuse_heading(text: str, slot: str) -> None:
    """Raise ``ValueError`` when ``text`` holds a run-in heading and ``slot`` takes none.

    ``slot`` is one of :data:`_HEADINGLESS_SLOTS`. ``text`` is what the sanitizer would see
    (for the abstract, after ``\\evval``/``\\status`` substitution, so a heading whose text
    becomes brace-free only then is caught too), cleaned as the sanitizer cleans it
    (:func:`_clean_text`). A ``\\paragraph`` in another form is not a heading -- it prints as
    literal text and :func:`literal_command_warnings` names it.
    """
    match = _PARAGRAPH_HEADING_RE.search(_clean_text(text))
    if match is None:
        return
    why = (
        "the abstract is a list environment, so pdflatex stops on a heading there"
        if slot == "abstract"
        else "the title is not prose, so the command would print as literal text"
    )
    raise ValueError(
        f"prose slot '{slot}' holds the run-in heading {_shown(match.group(0))}: a heading "
        f"cannot stand in the {slot} ({why}). Write the label as plain text, or move the "
        "lead-in to Methods or Results."
    )


# What a prose slot passes (:data:`_PROSE_PASSTHROUGH_RE`), as the warnings state it once per
# render (:func:`prose_warnings`), after the short per-command lines.
_PASSING_COMMANDS = (
    "a prose slot passes only \\ref, \\autoref, \\cite, \\citep and \\citet with one "
    "key of ASCII letters, digits, spaces and : _ . , ; + / = @ - (no optional argument, no "
    "blank line), and \\paragraph{<brace-free text>} in a section slot; any other command "
    "prints as literal text -- write a symbol as its Unicode character or in plain ASCII"
)
# The same for the two plain-text slots.
_PLAIN_RULE = "the title and the author are plain text: no command passes there"
_PLAIN_SLOTS = ("title", "author")
# And for a character replaced by the placeholder (:func:`placeholder_warnings`).
_PLACEHOLDER_RULE = (
    "a character pdflatex cannot typeset with the preamble render emits prints as "
    f"'{_UNICODE_PLACEHOLDER}' (CJK, emoji, a few Latin letters such as the H and T with "
    "stroke): write it in plain ASCII or leave it out"
)
# A backslash the sanitizer printed as literal text (``\textbackslash{}``), then the rest of
# the command as it printed it: a name of letters (a control word), an escaped special
# (``\%`` ... ``\textbackslash{}``) or a punctuation mark (``\,`` ``\(`` ``\"``). A
# backslash before a space, a digit or the end of the text is not a command.
_LITERAL_COMMAND_RE = re.compile(
    r"\\textbackslash\{\}(?:"
    r"(?P<word>[A-Za-z]+)"
    r"|\\(?P<special>[&%$#_{}])"
    r"|\\text(?P<named>backslash|asciitilde|asciicircum)\{\}"
    r"|(?P<symbol>[!\"'()*+,\-./:;<=>?@\[\]`|])"
    r")"
)
_NAMED_SPECIALS = {"backslash": "\\", "asciitilde": "~", "asciicircum": "^"}


def _literal_commands(tex: str) -> list[str]:
    """The commands sanitized ``tex`` prints as literal text (:data:`_LITERAL_COMMAND_RE`),
    each once, in order of first appearance, spelled as written (``\\textbf``, ``\\%``).
    PURE."""
    found: list[str] = []
    for match in _LITERAL_COMMAND_RE.finditer(tex):
        if match.group("named"):
            name = _NAMED_SPECIALS[match.group("named")]
        else:
            name = match.group("word") or match.group("special") or match.group("symbol")
        command = "\\" + name
        if command not in found:
            found.append(command)
    return found


def _prose_as_sanitized(text: str) -> str:
    """What a prose slot's ``text`` sanitizes to, as render sanitizes it but without the
    record: each ``\\evval``/``\\status`` macro stands for a brace-free value (as substitution
    leaves one) and each ``\\novelty`` span for its sentence text (the scope added after it is
    record-derived plain text). The same steps, in the same order, as
    :func:`render_paper_latex` and ``si.render_si_latex``. PURE."""
    return "".join(_latex_sanitize_prose(piece) for piece in _prose_pieces(text))


def _prose_pieces(text: str) -> list[str]:
    """A prose slot's ``text`` as render hands it to the prose sanitizer, without the record:
    cleaned (:func:`_clean_text`), each ``\\evval``/``\\status`` macro replaced by a brace-free
    value (``0``, as substitution leaves one), each ``\\novelty`` span by its sentence text.
    The pieces the prose sanitizer sees, in order. PURE."""
    body = _STATUS_RE.sub("0", _EVVAL_RE.sub("0", _clean_text(text).strip()))
    pieces: list[str] = []
    pos = 0
    for match in NOVELTY_RENDER_RE.finditer(body):
        pieces.append(body[pos : match.start()])
        pieces.append(match.group(3))
        pos = match.end()
    pieces.append(body[pos:])
    return pieces


def _warning_slots(
    prose: Optional[PaperProse], si_prose: Optional[SIProse]
) -> list[tuple[str, str, str, bool]]:
    """``(label, slot, text, plain)`` for each written slot the warnings read, in order: the
    paper's title, author (plain text), abstract, introduction, methods, results, discussion,
    conclusion, then the record's overview and notes."""
    slots: list[tuple[str, str, Optional[str], bool]] = []
    if prose is not None:
        slots += [("prose slot", name, getattr(prose, name), True) for name in _PLAIN_SLOTS]
        slots += [
            ("prose slot", name, getattr(prose, name), False)
            for name in (
                "abstract", "introduction", "methods", "results", "discussion", "conclusion",
            )
        ]
    if si_prose is not None:
        slots += [
            ("SI prose slot", name, getattr(si_prose, name), False)
            for name in ("overview", "notes")
        ]
    return [(label, name, text, plain) for label, name, text, plain in slots if text]


def literal_command_warnings(
    prose: Optional[PaperProse], si_prose: Optional[SIProse] = None
) -> list[str]:
    """One short line per prose slot and command the sanitizer prints as literal text
    (``prose slot 'methods': \\textbf prints as literal text``); what passes is stated once
    per render by :func:`prose_warnings`.

    Derived from the sanitizer itself, not from a list of known mistakes: each slot is
    sanitized as render sanitizes it -- the title and the author whole, as one line
    (:func:`_one_line`, :func:`_latex_sanitize`), every other slot through the prose pipeline
    (:func:`_prose_as_sanitized`) -- and every backslash that came out as
    ``\\textbackslash{}`` before a command names that command (:func:`_literal_commands`).
    That covers a command off the list (``\\textbf``, ``\\subparagraph``, ``\\eqref``), a
    listed one in a form that does not pass (``\\citep[e.g.][]{k}``, a key or a heading text
    spanning a blank line, ``\\paragraph*``), a control symbol (``\\%``) and a fullwidth
    backslash, which prints as a backslash. Fact macros and novelty markup are substituted
    before sanitizing and never warn. Slots in the order of :func:`_warning_slots`. PURE.
    """
    lines: list[str] = []
    for label, name, text, plain in _warning_slots(prose, si_prose):
        tex = _latex_sanitize(_one_line(text)) if plain else _prose_as_sanitized(text)
        lines.extend(
            f"{label} '{name}': {command} prints as literal text"
            for command in _literal_commands(tex)
        )
    return lines


def _codepoint_name(ch: str) -> str:
    return "U+%04X (%s)" % (ord(ch), unicodedata.name(ch, "unnamed"))


# The replaced characters a placeholder warning names before it counts the rest.
_PLACEHOLDER_SHOWN = 8


def placeholder_warnings(
    prose: Optional[PaperProse], si_prose: Optional[SIProse] = None
) -> list[str]:
    """One line per prose slot (the title and the author included) naming, by codepoint, each
    character the sanitizer replaces -- wholly or in part -- with the placeholder ``?``
    (:func:`_fold_non_ascii`): CJK, emoji, the Latin-A letters without a glyph
    (:data:`_UNDEFINED_LATIN_A`). The text read is the text the sanitizer reads (the title and
    the author on one line, each other slot as :func:`_prose_pieces` gives it). The first
    :data:`_PLACEHOLDER_SHOWN` distinct characters are named, the rest counted. PURE."""
    lines: list[str] = []
    for label, name, text, plain in _warning_slots(prose, si_prose):
        read = _one_line(text) if plain else "".join(_prose_pieces(text))
        chars = list(dict.fromkeys(
            ch for ch in read if ord(ch) >= 0x80 and _fold_non_ascii(ch)[1]
        ))
        if not chars:
            continue
        shown = ", ".join(_codepoint_name(c) for c in chars[:_PLACEHOLDER_SHOWN])
        more = len(chars) - _PLACEHOLDER_SHOWN
        rest = f", and {more} more" if more > 0 else ""
        lines.append(f"{label} '{name}': {shown}{rest} print(s) as '{_UNICODE_PLACEHOLDER}'")
    return lines


# @MX:NOTE: [AUTO] The writer's only signal that a command printed as literal text or a character
#   was replaced: render and run print each line as a warning (compiler.prose_warnings) and
#   still exit 0.
def prose_warnings(
    prose: Optional[PaperProse], si_prose: Optional[SIProse] = None
) -> list[str]:
    """Every warning about what the sanitizer did to the written prose, ready to print: the
    short per-slot command lines (:func:`literal_command_warnings`), then each rule they need
    once (what a prose slot passes, :data:`_PASSING_COMMANDS`; that the title and the author
    pass nothing, :data:`_PLAIN_RULE`), then the per-slot placeholder lines
    (:func:`placeholder_warnings`) and their rule once (:data:`_PLACEHOLDER_RULE`). PURE."""
    commands = literal_command_warnings(prose, si_prose)
    named = {line.split("'")[1] for line in commands}
    rules: list[str] = []
    if named - set(_PLAIN_SLOTS):
        rules.append(_PASSING_COMMANDS)
    if named & set(_PLAIN_SLOTS):
        rules.append(_PLAIN_RULE)
    replaced = placeholder_warnings(prose, si_prose)
    return commands + rules + replaced + ([_PLACEHOLDER_RULE] if replaced else [])


def _novelty_prose(
    text: str,
    spec: Spec,
    novelty_decisions: Sequence[EvidenceItem],
    found: Optional[list[NoveltySentence]] = None,
    document: str = "draft.tex",
) -> str:
    """Sanitize a prose slot AND render its ``\\novelty{kind}{hyp}{text}`` markup (N2 gate).

    The novelty member of the prose pipeline (alongside :func:`_latex_sanitize_prose` and
    :func:`factref.substitute_factrefs`). It SPLIT-and-stitches on
    :data:`novelty.NOVELTY_RENDER_RE` exactly as ``_latex_sanitize_prose`` walks the ref/cite
    allowlist: each GAP between/around the ``\\novelty`` spans is fully prose-sanitized, and
    each SPAN ``\\novelty{kind}{hyp}{inner}`` is replaced by the PLAIN sentence -- no macro,
    no ``kind`` / ``hyp`` in the source (the submitted ``.tex`` carries no markup a reviewer
    would not recognize):

      - the inner text, prose-sanitized (FLAT: specials escaped, no nested ref/cite -- the
        documented honest limit), immediately followed by
      - the record-derived scope from :func:`novelty.novelty_scope_suffix` (the indexes that
        answered and the search date, or ``(as of <date>)``), sanitized like any other text
        -- a recorded index name may carry a LaTeX special.

    When ``found`` is given, each rendered sentence is appended to it as a
    :class:`novelty.NoveltySentence` for ``document`` -- the binding the compiler writes
    beside the paper so ``verify`` can re-derive it.

    A string with NO ``\\novelty`` markup never enters the loop -> falls straight to
    ``_latex_sanitize_prose(text)`` (BYTE-IDENTICAL to the pre-N2 path). PURE + FAIL-LOUD:
    an unsupported / unknown / bad-kind assertion raises ``ValueError`` via
    ``novelty_scope_suffix`` (the HARD gate at render time), and so does an empty text
    (``novelty.require_novelty_text``).
    """
    out: list[str] = []
    pos = 0
    for match in NOVELTY_RENDER_RE.finditer(text):
        out.append(_latex_sanitize_prose(text[pos : match.start()]))  # gap -> sanitized
        kind, hyp, inner = match.group(1), match.group(2), match.group(3)
        suffix = novelty_scope_suffix(kind, hyp, spec, novelty_decisions)  # fail-loud
        require_novelty_text(kind, hyp, inner)  # fail-loud: the claim is inside the span
        sentence = _latex_sanitize_prose(inner) + _latex_sanitize(suffix)
        out.append(sentence)
        if found is not None:
            found.append(NoveltySentence(document, kind, hyp, sentence))
        pos = match.end()
    out.append(_latex_sanitize_prose(text[pos:]))  # trailing gap / whole string if no spans
    return "".join(out)


def _confidence_str(claim: Claim) -> str:
    """Human-readable confidence: numeric value or graded level, + type."""
    c = claim.confidence
    type_name = c.type.value if hasattr(c.type, "value") else str(c.type)
    if c.value is not None:
        return f"{c.value:.3g} ({type_name})"
    if c.level is not None:
        level = c.level.value if hasattr(c.level, "value") else str(c.level)
        return f"{level} ({type_name})"
    return type_name


def _confidence_display(
    claim: Claim, rule: Optional[DecisionRule] = None
) -> Optional[str]:
    """The confidence string to SHOW, or ``None`` to suppress it (render decision).

    A verdict decided by a fixed pre-registered rule (threshold / interval) carries no
    degree of belief: its confidence is ``rule``, with no value, and the basis line
    (printed separately, C3) states the rule and the margin or interval. Nothing is shown.

    A claim recorded BEFORE the engine emitted ``rule`` carries a ``credence`` whose value
    is ``1 - exp(-|margin|)`` -- a margin transform, not a probability. When ``rule`` (the
    hypothesis's frozen decision rule) is one of those kinds, that credence is suppressed
    too, so an existing run renders cleanly without re-deriving.

    A genuine probability (a bayesian ``posterior``) or a graded level is shown via
    :func:`_confidence_str`. Render-only -- it never changes belief, only what is printed.
    """
    c = claim.confidence
    if c.type == ConfidenceType.RULE:
        return None
    if (
        c.type == ConfidenceType.CREDENCE
        and rule is not None
        and rule.kind in RULE_CONFIDENCE_KINDS
    ):
        return None
    return _confidence_str(claim)


def _status_str(claim: Claim) -> str:
    return claim.status.value if hasattr(claim.status, "value") else str(claim.status)


def _bearing_data_sources(
    hyp_id: str, evidence: Sequence[EvidenceItem]
) -> list[str]:
    """The distinct ``data_source`` values of the Evidence bearing on ``hyp_id``.

    ``None`` (unstated) is surfaced as the literal ``"none"`` so the label is honest
    about unmarked provenance. Order is first-seen for a stable, readable line.
    """
    seen: list[str] = []
    for ev in evidence:
        if not any(b.target_id == hyp_id for b in ev.bears_on):
            continue
        src = ev.provenance.data_source or "none"
        if src not in seen:
            seen.append(src)
    return seen


def _evidence_validity_fields(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> tuple[str, str, str]:
    """The honest evidence-validity facts for one hypothesis as ``(referent,
    data_sources, qualifier)`` (design/evidence-validity.md §4).

    Single source of truth for the honesty labeling shared by the Markdown and LaTeX
    renderers: referent (a frozen Spec field), the bearing data_source(s), and a short
    qualifier (in-silico/computational, or awaiting measured data) when warranted.
    Reporting only -- it never changes belief; it labels what the gate already let
    through, and never overclaims.
    """
    referent = hyp.referent  # "formal" | "empirical" (a frozen Spec field)
    sources = _bearing_data_sources(hyp.id, evidence)
    sources_str = ", ".join(sources) if sources else "none"

    qualifier = ""
    is_supported = claim is not None and claim.status == ClaimStatus.SUPPORTED
    has_measured = "measured" in sources
    if referent == "formal" and is_supported and "generated" in sources:
        # A formal claim supported on generated instances: a real computational
        # result, not a bare empirical "supported".
        qualifier = "in-silico/computational result"
    elif referent == "empirical" and not has_measured:
        # An empirical claim with no measured Evidence yet: belief is not grounded in
        # real data, so say so plainly (the gate already blocks a binding empirical
        # verdict here; a proposed/awaiting claim is the legitimate state).
        qualifier = "awaiting measured data"

    return referent, sources_str, qualifier


def _evidence_validity_label(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> str:
    """The Markdown evidence-validity label line for one hypothesis (§4).

    A concise, factual single line built from :func:`_evidence_validity_fields`:
    referent + bearing data_source(s) + an honest qualifier when warranted, so a
    reader can tell apart an in-silico/computational result, a real measured result,
    and an empirical claim still awaiting measured data.
    """
    referent, sources_str, qualifier = _evidence_validity_fields(hyp, claim, evidence)
    suffix = f" — {qualifier}" if qualifier else ""
    return (
        f"- Evidence validity: referent={referent}; "
        f"data_source(s)={sources_str}{suffix}"
    )


def render_paper(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    pending: Optional[Sequence[dict[str, Any]]] = None,
    prose: Optional[PaperProse] = None,
    cited_dois: Optional[Sequence[str]] = None,
) -> str:
    """
    Render a Markdown paper draft.

    Args:
        spec: the compiled Spec (provenance of the proposal + hypotheses).
        claims: the Claims produced for the hypotheses (belief state).
        evidence: the Evidence log (the record); optional.
        pending: agent-judgment checkpoints (proof/qualitative awaiting an
            in-session verdict); optional. Each item: {hypothesis_id, kind,
            expression, finding}.
        prose: optional agent-authored narrative (abstract/introduction/discussion).
            A present slot is injected as its section; ``None`` (or a ``None`` slot)
            falls back to the structural skeleton -- with ``prose=None`` the output is
            byte-identical to the pre-prose skeleton (a regression invariant).
        cited_dois: optional DOIs to list in a References section. ``None``/empty
            renders a "No literature cited." line. DOI list only -- no BibTeX is
            generated (design decision).

    Returns:
        A Markdown document string.
    """
    evidence = list(evidence or [])
    pending = list(pending or [])
    rp = spec.raw_proposal
    claim_by_hyp = {c.answers: c for c in claims}

    lines: list[str] = []
    title = (rp.goal or "Untitled research").strip().splitlines()[0]
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> Draft compiled by sci-adk from Spec `{spec.id}` "
                 f"(v{spec.version}). Belief state is revisable as Evidence accrues.")
    lines.append("")

    # Agent-authored abstract (after the title), when supplied. Absent -> nothing,
    # preserving the byte-identical skeleton.
    if prose is not None and prose.abstract:
        lines.append("## Abstract")
        lines.append(prose.abstract.strip())
        lines.append("")

    # Agent-authored introduction, when supplied.
    if prose is not None and prose.introduction:
        lines.append("## Introduction")
        lines.append(prose.introduction.strip())
        lines.append("")

    lines.append("## Goal")
    lines.append(rp.goal.strip() or "_(none)_")
    lines.append("")
    lines.append("## Background")
    lines.append(rp.background.strip() or "_(none)_")
    lines.append("")
    lines.append("## Method")
    lines.append(rp.method.strip() or "_(none)_")
    if spec.method and spec.method.approaches:
        lines.append("")
        lines.append("Planned approaches:")
        for a in spec.method.approaches:
            lines.append(f"- {a}")
    lines.append("")

    # Hypotheses & findings: the heart of the draft -- each hypothesis with the
    # Claim the DecisionEngine produced from the per-Spec DecisionRule.
    lines.append("## Hypotheses and findings")
    lines.append("")
    for h in spec.hypotheses:
        claim = claim_by_hyp.get(h.id)
        rule = h.decision_rule
        rule_kind = rule.kind.value if hasattr(rule.kind, "value") else str(rule.kind)
        mode = h.mode.value if hasattr(h.mode, "value") else str(h.mode)
        lines.append(f"### {h.statement}")
        lines.append(f"- Hypothesis id: `{h.id}` ({mode})")
        lines.append(f"- Decision rule ({rule_kind}): {rule.expression}")
        if claim is not None:
            # Same display rule as the record dump: no number for a rule verdict (old
            # or new); the basis line below carries the rule and its margin.
            confidence = _confidence_display(claim, rule)
            status_line = f"- **Status: {_status_str(claim)}**"
            if confidence is not None:
                status_line += f" — confidence {confidence}"
            lines.append(status_line)
            lines.append(f"- Basis: {claim.confidence.basis}")
        else:
            lines.append("- **Status: no claim** (no evidence bore on this hypothesis)")
        # Honest self-description: referent + bearing data_source(s) (evidence-validity
        # §4), so the draft never reads as a bare "supported" for a formal/generated
        # result, nor hides that an empirical claim lacks measured data.
        lines.append(_evidence_validity_label(h, claim, evidence))
        lines.append("")

    # Evidence trail (the append-only record).
    lines.append("## Evidence")
    if not evidence:
        lines.append("_No evidence recorded._")
    else:
        for ev in evidence:
            kind = ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind)
            summary = _result_summary(ev)
            lines.append(f"- `{ev.id}` ({kind}): {summary}")
    lines.append("")

    # Pending agent judgments (proof/qualitative checkpoints -- filled in-session).
    if pending:
        lines.append("## Pending agent judgments")
        lines.append("")
        lines.append("These hypotheses use a non-numeric rule and await an "
                     "in-session agent verdict (no autonomous LLM call):")
        for p in pending:
            lines.append(f"- `{p.get('hypothesis_id')}` "
                         f"({p.get('kind')}): {p.get('expression')}")
            finding = (p.get("finding") or "").strip()
            if finding:
                lines.append(f"  - finding: {finding}")
        lines.append("")

    # Agent-authored discussion, when supplied (before References).
    if prose is not None and prose.discussion:
        lines.append("## Discussion")
        lines.append(prose.discussion.strip())
        lines.append("")

    # References: a DOI list only (no BibTeX generation). Emitted only when the
    # caller passes the kwarg -- when cited_dois is omitted entirely (the legacy
    # call), nothing is appended, keeping the prose=None output byte-identical.
    if cited_dois is not None:
        lines.append("## References")
        dois = [d for d in cited_dois if d and d.strip()]
        if not dois:
            lines.append("No literature cited.")
        else:
            for doi in dois:
                lines.append(f"- https://doi.org/{doi}")
        lines.append("")

    return "\n".join(lines)


# A DOI the no-bibliography References list cites as ``\url{https://doi.org/<doi>}``: the
# directory indicator ``10.``, a registrant code of 4 to 9 digits (with optional dotted
# subdivisions), ``/`` and a suffix of printable ASCII other than ``{ } \ % # ^``. The DOI goes
# into ``\url`` as written, so a brace closed it (``10.1/x}\input{<file>}%`` made pdflatex
# read the file), and ``%`` ``#`` ``^`` and a backslash are TeX's comment, parameter,
# character-code and escape characters; a space or non-ASCII character is not part of a DOI.
_DOI_RE = re.compile(r"10\.[0-9]{4,9}(?:\.[0-9]+)*/(?:(?![{}\\%#^])[!-~])+")


def is_doi(text: str) -> bool:
    """True iff ``text`` (stripped) has the DOI form the References list cites
    (:data:`_DOI_RE`). The compiler gathers the cited DOIs with it and names any other in a
    render warning; :func:`render_paper_latex` applies it again. PURE."""
    return _DOI_RE.fullmatch(text.strip()) is not None


def _latex_evidence_validity_label(
    hyp: Hypothesis,
    claim: Optional[Claim],
    evidence: Sequence[EvidenceItem],
) -> str:
    """The LaTeX evidence-validity label line for one hypothesis (§4).

    The LaTeX twin of :func:`_evidence_validity_label`: built from the same
    single-source :func:`_evidence_validity_fields`, so the honest in-silico /
    awaiting-measured-data qualifiers appear in the .tex exactly as in the .md. The
    referent and data_source(s) are escaped (they originate in the Spec/Evidence).
    """
    referent, sources_str, qualifier = _evidence_validity_fields(hyp, claim, evidence)
    suffix = f" --- {_latex_sanitize(qualifier)}" if qualifier else ""
    return (
        f"\\textit{{Evidence validity:}} referent={_latex_sanitize(referent)}; "
        f"data\\_source(s)={_latex_sanitize(sources_str)}{suffix}"
    )


def render_paper_latex(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Optional[Sequence[EvidenceItem]] = None,
    pending: Optional[Sequence[dict[str, Any]]] = None,
    prose: Optional[PaperProse] = None,
    cited_dois: Optional[Sequence[str]] = None,
    bib_path: Optional[str] = None,
    figures: Optional[Sequence[AnyFigure]] = None,
    novelty_sentences: Optional[list[NoveltySentence]] = None,
    font_policy: Optional[bool] = None,
) -> str:
    """
    Render the BELIEF-NARRATIVE paper (``draft.tex``) -- agent prose + a record-fidelity
    spine (the "moved line", design/render-architecture-reframe.md).

    The reframe shrinks this renderer to its record-fidelity job and hands the paper's
    narrative + structure to the in-session agent (rigor-shell-architecture.md §2.4:
    "Writing paper prose" is OUT of the kernel). So the engine emits NO stage-dump
    sections (no Goal/Background/Evidence/Figures heading, no per-hypothesis verdict
    bullets) -- those record facts live in the deterministic SI (``render_si_latex``).
    What it DOES emit deterministically: the IMRaD skeleton an agent fills (Abstract /
    Introduction / Methods / Results / Discussion), the figures (drawn FROM the record),
    the bibliography wiring, and -- the fidelity gate -- the substitution of every
    ``\\evval``/``\\status`` macro in the agent prose with its TRUE recorded value
    (:func:`sci_adk.render.factref.substitute_factrefs`, FAIL-LOUD). So the narrative is
    the agent's, but every measured number / verdict it states is the record's.

    PURE: no LLM, no network. The agent prose arrives as ``prose`` (input, never
    generated here). Deterministic: same inputs -> byte-identical output.

    Args:
        spec: the compiled Spec (id + version for the title fallback + the header note).
        claims: the Claims (their statuses back ``\\status{<hyp>}`` in the prose).
        evidence: the Evidence record (figure y-values + ``\\evval`` values come from
            here); optional.
        pending: agent-judgment checkpoints; a NON-empty list emits a working-draft
            "Pending agent judgments" section (a finished paper has none). Optional.
        prose: the agent-authored narrative (``title``/``abstract``/``introduction``/
            ``methods``/``results``/``discussion``). Each present slot is emitted as its
            IMRaD section, after ``\\evval``/``\\status`` substitution + the prose
            sanitizer (``\\ref``/``\\cite`` preserved). ``title`` is the paper title; absent
            -> ``spec.id`` (NEVER the goal/hypothesis wall). ``None`` -> a near-empty paper
            (an unwritten narrative -- the record still lives in the SI). A run-in heading
            ``\\paragraph{<text>}`` in the abstract or the title raises ``ValueError``
            naming the slot (a heading stands only inside a section).
        cited_dois: used ONLY as the no-bibtex fallback -- when ``bib_path`` is ``None`` and
            these are present, a ``\\url`` DOI list is emitted as the References: each entry
            of the DOI form (:func:`is_doi`); any other is left out. Ignored when
            ``bib_path`` is given (BibTeX is the single source then).
        bib_path: path to an EXISTING ``.bib`` (the compiler checks existence; the renderer
            does no fs access). Present -> ``\\usepackage{natbib}`` is wired with
            ``\\bibliographystyle{plainnat}`` + ``\\bibliography{<stem>}`` (author-year, so
            the prose's ``\\citep``/``\\citet`` resolve). NO ``\\nocite{*}`` and NO manual
            DOI list (one reference source, never both). ``None`` -> the DOI-list fallback
            (or nothing).
        figures: agent-authored MAIN figures (native pgfplots / image) -- the ONLY place
            main figures appear (the SI carries only supplementary figures). Placed as
            floats inside Results, numbered by body-reference order across the WHOLE
            narrative (a ``\\ref{fig:<id>}`` may be in Results or Discussion), so the order
            is computed against all prose then the floats are emitted; the compiler
            re-derives the SAME order from the rendered draft for co-located ``fig<N>``
            filenames. ``None``/empty -> no figures.
        novelty_sentences: when given, every ``\\novelty{kind}{hyp}{text}`` in the prose is
            appended to it as a :class:`~sci_adk.render.novelty.NoveltySentence`
            (document ``draft.tex``, the sentence exactly as rendered). The draft itself
            carries only the plain sentence; the compiler writes these bindings to the side
            file ``verify`` checks. ``None`` -> nothing is collected (same draft text).
        font_policy: the figure font policy decided for the whole run
            (:func:`run_font_policy` -- the draft's and the SI's figures), so the draft and
            the SI share one text face. ``None`` -> decided from ``figures`` alone.

    Returns:
        A LaTeX document string (``\\documentclass`` ... ``\\end{document}``).
    """
    evidence = list(evidence or [])
    pending = list(pending or [])
    figures = list(figures or [])
    claims = list(claims)
    # Novelty decisions (bears_on=[]) back the \novelty{} markup re-derivation (N2 gate).
    novelty_decisions = [
        ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
    ]

    def _slot(text: str, slot: str) -> str:
        # Agent prose -> substitute record-fidelity facts (\evval/\status, fail-loud), THEN
        # render \novelty{} markup (plain sentence + record scope / HARD fail) + the prose
        # sanitizer (specials escaped; \ref/\cite preserved). Substitute factrefs before, so
        # a substituted string value is escaped as ordinary text; _novelty_prose owns the
        # prose sanitize and collects the novelty bindings. A slot that takes no run-in
        # heading (the abstract) refuses one, checked on the substituted text the sanitizer
        # sees. The text is cleaned first (_clean_text: line ends, control characters), so the
        # fact-macro, novelty and heading matches all see what the sanitizer sees.
        body = substitute_factrefs(_clean_text(text).strip(), evidence, claims)
        if slot in _HEADINGLESS_SLOTS:
            _refuse_heading(body, slot)
        return _novelty_prose(
            body,
            spec,
            novelty_decisions,
            found=novelty_sentences,
            document="draft.tex",
        )

    # Title: the agent's short title, else spec.id -- NEVER the goal/hypothesis wall. It is
    # escaped whole (not prose), so a run-in heading there is refused rather than printed. One
    # line: a blank line inside \title{} stops pdflatex.
    title = _one_line(prose.title if prose is not None and prose.title else "") or spec.id
    _refuse_heading(title, "title")

    lines: list[str] = []
    # Preamble. natbib (author-year \citep/\citet); figure packages PER KIND.
    has_native = any(f.kind == "native" for f in figures)
    has_image = any(f.kind == "image" for f in figures)
    if font_policy is None:
        font_policy = font_policy_applies(figures)
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.extend(text_font_lines(font_policy))
    lines.append(HYPERREF_LINE)
    lines.append(r"\usepackage{url}")
    lines.append(r"\usepackage{natbib}")
    # Figure font policy (design/paper-publishing-requirements.md F2): text and equations in
    # a Times-compatible serif (newtxtext, in the font lines above, + newtxmath), other figure
    # text in an Arial-compatible sans (helvet, scaled). pdflatex metric-compatible -- no font
    # files, no engine change. Emitted ONLY when the run's draft or SI carries a figure
    # (font_policy); a figure-less run keeps Latin Modern. The per-figure sans scoping is
    # applied in figures.render_figure.
    if font_policy:
        lines.append(r"\usepackage{amsmath}")
        lines.append(r"\usepackage{newtxmath}")
        lines.append(r"\usepackage[scaled]{helvet}")
    if has_native:
        lines.append(r"\usepackage{pgfplots}")
        lines.append(r"\pgfplotsset{compat=1.18}")
    if has_image:
        lines.append(r"\usepackage{graphicx}")
    # No \novelty macro in the preamble: a novelty assertion renders as its plain sentence
    # (_novelty_prose), and its {kind, hyp} binding lives in a side file, not in the source.
    lines.append(f"\\title{{{_latex_sanitize(title)}}}")
    # Author is agent-supplied; absent -> empty \author{} (the paper is tool-agnostic and
    # never names the rendering toolchain -- design feedback §10, tool-vocabulary leakage).
    # One line: a blank line inside \author{} stops pdflatex ("Paragraph ended before \author
    # was complete").
    author = _one_line(prose.author) if prose is not None and prose.author else ""
    lines.append(f"\\author{{{_latex_sanitize(author)}}}")
    # No date: \today printed the day of each compile, so the same source gave a different
    # first page every day. The submission date is the venue's, not the render's.
    lines.append(r"\date{}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")
    # NO engine-emitted "compiled by sci-adk from Spec ... Belief state ... Evidence"
    # note here: that is tool self-reference, which the belief-narrative paper must not
    # carry (§10). The provenance note lives in the deposit's record.tex (the record dump,
    # exempt from the vocabulary check); a data/code-availability pointer, if wanted, is
    # agent prose.

    # Abstract.
    if prose is not None and prose.abstract:
        lines.append(r"\begin{abstract}")
        lines.append(_slot(prose.abstract, "abstract"))
        lines.append(r"\end{abstract}")
        lines.append("")

    # IMRaD body -- agent-authored narrative; a section is emitted ONLY when its prose
    # slot is present. The engine adds no stage-dump section of its own.
    if prose is not None and prose.introduction:
        lines.append(r"\section{Introduction}")
        lines.append(_slot(prose.introduction, "introduction"))
        lines.append("")
    if prose is not None and prose.methods:
        lines.append(r"\section{Methods}")
        lines.append(_slot(prose.methods, "methods"))
        lines.append("")

    # Results: the agent's findings prose + the MAIN figures as floats (the only place
    # they appear). Figures are numbered by body-reference order across the WHOLE
    # narrative (a \ref may be in Results or Discussion), so the order is computed against
    # ALL prose -- the canonical \ref text (figures add only \label, no \ref) -- then the
    # floats are emitted here. Emitted when there is results prose OR at least one figure.
    if (prose is not None and prose.results) or figures:
        lines.append(r"\section{Results}")
        if prose is not None and prose.results:
            lines.append(_slot(prose.results, "results"))
            lines.append("")
        if figures:
            # Cleaned as the slots are (_clean_text), so a key holding a control character
            # numbers the figures as the rendered draft does -- the compiler re-derives the
            # numbers from that draft to name the copied image files.
            ref_body = "\n".join(
                _clean_text(s).strip()
                for s in (
                    (prose.abstract if prose else None),
                    (prose.introduction if prose else None),
                    (prose.methods if prose else None),
                    (prose.results if prose else None),
                    (prose.discussion if prose else None),
                )
                if s
            )
            for number, fig in order_figures_by_reference(figures, ref_body):
                lines.append(render_figure(fig, evidence, number))
                lines.append("")

    if prose is not None and prose.discussion:
        lines.append(r"\section{Discussion}")
        lines.append(_slot(prose.discussion, "discussion"))
        lines.append("")

    # Conclusion. The DEFAULT publishing contract requires this section
    # (core/pubreqs.DEFAULT_REQUIRED_SECTIONS), so without a slot to author it the
    # documented `pubreqs freeze --defaults` fast-path could never be satisfied: verify
    # failed with "missing required section: Conclusion" and no authoring surface could
    # fix it. Emitted like the others -- only when its slot is present, so a paper that
    # does not declare Conclusion is byte-identical to before.
    if prose is not None and prose.conclusion:
        lines.append(r"\section{Conclusion}")
        lines.append(_slot(prose.conclusion, "conclusion"))
        lines.append("")

    # Pending agent judgments -- only when present (an unresolved proof/qualitative
    # hypothesis). A finished paper has none; this is the working-draft signal.
    if pending:
        lines.append(r"\section{Pending agent judgments}")
        lines.append(
            "These hypotheses use a non-numeric rule and await an in-session agent "
            "verdict (no autonomous LLM call):"
        )
        lines.append(r"\begin{itemize}")
        for p in pending:
            hyp_id = _latex_sanitize(_one_line(str(p.get("hypothesis_id"))))  # in \texttt{}
            kind = _latex_sanitize(str(p.get("kind")))
            expr = _latex_sanitize(str(p.get("expression")))
            lines.append(f"  \\item \\texttt{{{hyp_id}}} ({kind}): {expr}")
            finding = (p.get("finding") or "").strip()
            if finding:
                lines.append(f"  \\item finding: {_latex_sanitize(finding)}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # References: ONE source, never both. An existing .bib -> natbib + plainnat +
    # \bibliography (citations come from the prose's \citep/\citet; NO \nocite{*}, NO
    # manual list). No .bib but cited DOIs -> a \url DOI list (the no-bibtex fallback).
    if bib_path is not None:
        stem = Path(bib_path).stem
        lines.append(r"\bibliographystyle{plainnat}")
        lines.append(f"\\bibliography{{{stem}}}")
    else:
        # Only a DOI of the DOI form (is_doi): it goes into \url{} as written, so anything
        # else could close the \url and run what follows. The compiler names each one left out.
        dois = [d.strip() for d in (cited_dois or []) if d and is_doi(d)]
        if dois:
            lines.append(r"\section{References}")
            lines.append(r"\begin{itemize}")
            for doi in dois:
                # DOIs go verbatim inside \url{} (NOT escaped -- \url handles specials).
                lines.append(f"  \\item \\url{{https://doi.org/{doi}}}")
            lines.append(r"\end{itemize}")
    lines.append("")
    lines.append(r"\end{document}")
    return "\n".join(lines)


def _truncate_words(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars at a WORD boundary, ellipsis OUTSIDE.

    Never cuts mid-token (the bug behind the malformed JSON dumps was a fixed char cap
    slicing through a value). The ellipsis is appended after the boundary, so it is never
    inside a quoted string / number.
    """
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0]
    return (head or text[:limit]) + " ..."


def _summarize_value(value: object) -> str:
    """A short, STRUCTURED rendering of one finding value (never a raw mid-token cut).

    A scalar -> its text (capped at a word boundary). A list of dicts -> the salient
    fields (``doi``/``source``/``license``/``filename``) of the first entry + a ``(+N
    more)`` count -- so a literature finding renders as a structured citation summary, not
    a truncated JSON blob. A list of scalars -> a count. A nested dict -> ``{...}`` (the
    SI's per-item record carries the full structure; this is the one-line summary).
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return _truncate_words(str(value), 80)
    if isinstance(value, list):
        if not value:
            return "[]"
        head = value[0]
        if isinstance(head, dict):
            keys = [k for k in ("doi", "source", "license", "filename") if k in head]
            shown = ", ".join(f"{k}={_truncate_words(str(head[k]), 60)}" for k in keys)
            more = f" (+{len(value) - 1} more)" if len(value) > 1 else ""
            return f"[{{{shown or '...'}}}{more}]"
        return f"[{len(value)} item(s)]"
    if isinstance(value, dict):
        return "{...}"
    return _truncate_words(str(value), 80)


def _summarize_finding(finding: str) -> str:
    """Render a finding as a STRUCTURED, escaped-downstream summary -- never raw JSON.

    A JSON object -> ``key=value; ...`` of structured per-field summaries (so the DOI /
    source / license / filename of a literature finding read cleanly, design feedback
    3.1). A JSON object with a ``summary`` string -- the experiment stage's convention for
    a finding that carries the values a paper may state (design/declared-numbers.md
    §4.4) -- reads as that text, capped like prose, then ``key = value`` for each value.
    A JSON array -> a count. Non-JSON prose -> the text, truncated at a word boundary with
    the ellipsis OUTSIDE (never mid-token). The caller escapes the result.
    """
    text = finding.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return f"finding={_truncate_words(text, 200)}"
    if isinstance(data, dict) and isinstance(data.get("summary"), str):
        values = "; ".join(
            f"{k} = {_summarize_value(v)}" for k, v in data.items() if k != "summary"
        )
        head = f"finding={_truncate_words(data['summary'], 200)}"
        return f"{head}; {values}" if values else head
    if isinstance(data, dict):
        bits = "; ".join(f"{k}={_summarize_value(v)}" for k, v in data.items())
        return f"finding=({bits})" if bits else "finding=()"
    if isinstance(data, list):
        return f"finding=[{len(data)} item(s)]"
    return f"finding={_summarize_value(data)}"


# -- §10 tool-vocabulary leakage check (the submission documents) ---------------------
#
# A belief-narrative paper must read as legitimate science to a reader who does not know
# sci-adk (the "tool-agnostic reader test"): no sentence may require knowing a sci-adk
# internal object to make sense. These phrases/words name the MACHINERY, not the science,
# so they must not appear in the submission documents: draft.tex AND the authored si.tex
# (SPEC-SI-AUTHORING-001 REQ-SA-204). Only the deposit's record.tex, the deterministic
# record dump outside paper/, is exempt (REQ-SA-206). (design feedback §10.)
#
# The bare phrase "decision rule" is NOT here: it is standard statistics (Wald; Bayes
# decision rules). Only the compounds that name the frozen machinery are listed below.
_PAPER_TOOL_PHRASES: tuple[str, ...] = (
    "sci-adk",
    "frozen spec",
    "engine-derived",
    "the engine",
    "verify audit",
    "append-only",
    "evidence record",
    "belief state",
    "anti-harking",
    "result.point",
    "result.finding",
    # Machinery compounds (design/reader-facing-prose.md §12.5, classes A+B). Every entry
    # here is a COMPOUND whose referent is the authoring system in EVERY venue -- that is
    # the admission criterion. Bare ordinary words are never added, however often they
    # leak: whether "recorded" or "gate" or "pre-registered" is a leak depends on what it
    # refers to and on who is reading (§12.1, §12.2), and a list can see neither. Adding
    # them would fire on correct papers, which is how a gate stops being read.
    "claim status",
    "evidence item",
    "record digest",
    "spec digest",
    "record fidelity",
    "frozen contract",
    "frozen decision rule",
    "pre-registered decision rule",
    "research compiler",
    "verify gate",
)
# Bare jargon words (word-boundary, case-insensitive): a paper states a "result", not a
# "verdict".
_PAPER_TOOL_WORD_RE = re.compile(r"\b(?:verdict|verdicts)\b", re.IGNORECASE)
# "Spec" as a sci-adk proper noun (case-sensitive). The generic word -- "specification",
# "specifically", lowercase "spec" -- is fine; the capitalized object "Spec" is not.
_PAPER_TOOL_PROPER_RE = re.compile(r"\bSpec\b")

# Run-artifact IDENTIFIERS and internal artifact FILENAMES (design/reader-facing-prose.md
# §12.3 class B). This is the one class a list can carry with near-zero risk: the shapes
# below are ours, they are meaningless to a reader, and no venue wants them -- so unlike
# the ordinary words of class C they are venue-INDEPENDENT (§12.2a).
#
# Matched by SHAPE, not enumerated: ids are generated per run, so listing them is
# impossible. ``claim-`` is narrowed to the two real id shapes, because "claim-based" and
# "claim-level" are ordinary English.
#
# DEPOSITED artifacts are deliberately ABSENT -- ``reproduce.py``, ``record.tex``,
# ``si.tex``, ``claims_all.csv`` and the rest of the bundle. Naming the file that carries
# the deposited record or regenerates the results is exactly what a data-availability
# statement is for; the package's own si.tex does it correctly today, and an earlier draft
# of this list broke seven existing tests by forbidding it. Only files a reader can never
# have a reason to name -- the internal contracts and working notes -- belong here.
#
# ``hyp-<id>`` is also ABSENT, for a different reason: the ENGINE emits hypothesis ids into
# the generated package SI, so adding the shape here would fail runs over text the engine
# itself wrote. Whether that emission is itself a leak is a separate decision in
# SPEC-SI-AUTHORING-001 territory (the SI is authored belief and sits next to the record),
# and it is left open rather than settled by a list entry.
#
# An id ends on a letter or digit: a "." or "-" after it is the sentence's punctuation,
# not part of the id ("... as recorded in evi-obs-1." reports "evi-obs-1").
#
# File and directory NAMES match in any case: "Checkpoints.md" opening a sentence is the
# same internal file. The id shapes stay case-sensitive -- they are generated lowercase.
_PAPER_ARTIFACT_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bevi-[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"),   # Evidence ids
    re.compile(r"\bclaim-(?:hyp|novelty)-[A-Za-z0-9._-]*[A-Za-z0-9]"),  # Claim ids
    re.compile(
        r"\b(?:spec|pubreqs|pkgreqs|declarations|review|deposit|numbers(?:\.draft)?)\.json\b",
        re.IGNORECASE,
    ),
    # The run's working checkpoint files (design/deposit-files.md D6). ``checkpoints/`` alone
    # is not banned -- a paper may deposit its own model checkpoints -- and the deposited
    # copy ``deposit/protocol/amendment-v2.json`` passes: the folder decides.
    re.compile(
        r"\bcheckpoints/(?:amendment-v\d+|prior(?:\\_|_)work|science)\.json\b",
        re.IGNORECASE,
    ),
    # the novelty bindings; a prose slot reaches the source with the underscore escaped
    re.compile(r"\bnovelty(?:\\_|_)sentences\.json\b", re.IGNORECASE),
    re.compile(r"\bspec\.v\d+\.json\b", re.IGNORECASE),   # an amended Spec's earlier versions
    re.compile(r"\bspec(?:\\_|_)history\b", re.IGNORECASE),   # ...and the directory of them
    re.compile(r"\b(?:checkpoints|science)\.md\b", re.IGNORECASE),
)


def check_paper_tool_vocabulary(paper_tex: str) -> list[str]:
    """Return the tool-vocabulary leaks found in one submission document.

    PURE. The §10 tool-agnostic check: returns the distinct forbidden phrases/words that
    name the sci-adk machinery (``sci-adk``, ``frozen Spec``, ``engine-derived``,
    ``verdict``, ``Evidence record``, ``result.point``, ...) found in ``paper_tex``. An
    EMPTY list means the document reads as tool-agnostic science. The verify gate passes
    each submission document separately -- ``draft.tex`` and the authored ``si.tex``
    (REQ-SA-204) -- and never the deposit's ``record.tex`` (the record dump, exempt by
    REQ-SA-206). De-duplicated, first-seen order; the verify gates and the render
    regression tests consume it.
    """
    low = paper_tex.lower()
    found: list[str] = []
    for phrase in _PAPER_TOOL_PHRASES:
        if phrase in low and phrase not in found:
            found.append(phrase)
    for match in _PAPER_TOOL_WORD_RE.finditer(paper_tex):
        word = match.group(0).lower()
        if word not in found:
            found.append(word)
    if _PAPER_TOOL_PROPER_RE.search(paper_tex) and "Spec" not in found:
        found.append("Spec")
    for pattern in _PAPER_ARTIFACT_RES:
        for match in pattern.finditer(paper_tex):
            token = match.group(0)
            if token not in found:
                found.append(token)
    return found


def _result_summary(ev: EvidenceItem) -> str:
    """One-line, STRUCTURED summary of an Evidence item's Result.

    The numeric scalars (point/ci/posterior) plus a structured rendering of the qualitative
    finding (:func:`_summarize_finding`) -- NO raw JSON dumped, NO mid-token truncation. The
    SI carries the full per-item record; this is the readable one-line summary.
    """
    r = ev.result
    parts: list[str] = []
    if r.point is not None:
        parts.append(f"point={r.point:.6g}")
    if r.ci is not None:
        parts.append(f"ci={list(r.ci)}")
    if r.posterior is not None:
        parts.append(f"posterior={r.posterior:.6g}")
    if r.finding:
        parts.append(_summarize_finding(r.finding))
    return ", ".join(parts) if parts else "(no result fields)"
