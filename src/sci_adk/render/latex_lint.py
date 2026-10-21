"""
A lint for author-written LaTeX: the commands in it that read or write files or run code.

sci-adk writes the LaTeX of the paper, the record and the bibliography it ships from the record
and from external metadata, and only that text is under its execution and compile guarantee: a
prose slot is sanitized, the bibliography is a canonical copy holding allow-listed commands only
(``bib_latex.paper_bib``). Author-written LaTeX is outside that guarantee -- the body of an
authored SI section (written into ``si.tex`` as is) and a package ``main.tex`` / ``si.tex`` the
author supplies. sci-adk does not judge what such LaTeX does; this lint names the primitives a
reviewer would want to see before compiling it, in a render warning and a verify advisory, and
never fails anything.

What it names (:func:`lint_commands`): reading a file (``\\input``, ``\\include``,
``\\InputIfFileExists``, ``\\expandableinput``, ``\\openin``, ``\\read``, ``\\readline``),
writing one or running a program (``\\write``, ``\\immediate``, ``\\openout``, ``\\ShellEscape``),
re-reading text as code (``\\scantokens``), expl3 (``\\ExplSyntaxOn`` and an expl3-shaped name:
a function ``\\module_name:args`` or ``\\name:args``, a variable ``\\l_...``, ``\\g_...``,
``\\c_...``, ``\\q_...``), Lua (``\\directlua``, ``\\latelua``), the pdfTeX primitives (any
control word starting with ``pdf``: links, actions, objects, file reads), hyperref's form and
action commands (``\\PushButton``, ``\\TextField``, ``\\CheckBox``, ``\\ChoiceMenu``, ``\\Submit``,
``\\Reset``, ``\\Acrobatmenu``, the ``Form`` environment), ``\\typein``, ``\\special``, the
listing readers ``\\verbatiminput``, ``\\VerbatimInput`` and ``\\lstinputlisting``, ``\\csname``
(which builds a command name, ``\\@@input`` too), ``\\makeatletter`` (after which ``\\@input`` and
``\\@@input`` are commands), and ``\\newread`` / ``\\newwrite`` (a stream for a file read or
write under another name). The list is not exhaustive. A comment is not read, nor is a
``verbatim`` or ``lstlisting`` body.

PURE (string in, string out): stdlib only.
"""

from __future__ import annotations

import re

# The control words named by name.
# Not exhaustive: TeX can reach a file or a program in more ways than a list names (a name built
# with \csname, a package's own reader); the lint names the common ones for a human to read.
_LINTED_WORDS = frozenset(
    "input include InputIfFileExists expandableinput openin read readline write immediate "
    "openout ShellEscape scantokens ExplSyntaxOn directlua latelua PushButton TextField "
    "CheckBox ChoiceMenu Submit Reset Acrobatmenu typein special verbatiminput lstinputlisting "
    "csname VerbatimInput makeatletter newread newwrite".split()
)
# expl3-shaped names under ordinary catcodes: \module_name:args, \name:args (a signature of
# argument specifiers), and the variables \l_ \g_ \c_ \q_.
_EXPL3_RE = re.compile(
    r"\\[A-Za-z]+(?:_[A-Za-z@]+)+:[A-Za-z]*"
    r"|\\[A-Za-z]+:[nNpTFwcVvoxefD]+(?![A-Za-z:])"
    r"|\\[lgcq]_[A-Za-z][A-Za-z_@]*"
)
_CONTROL_WORD_RE = re.compile(r"\\([A-Za-z]+)")
_FORM_ENV_RE = re.compile(r"\\begin\s*\{Form\}")
# A comment: a % that is not escaped (an even number of backslashes before it), to line end.
_COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*")
_VERBATIM_RE = re.compile(
    r"\\begin\s*\{(verbatim\*?|lstlisting|Verbatim)\}.*?\\end\s*\{\1\}", re.DOTALL
)


def _readable(tex: str) -> str:
    """``tex`` without its comments and verbatim bodies."""
    return _VERBATIM_RE.sub(" ", _COMMENT_RE.sub(r"\1", tex))


def lint_commands(tex: str) -> list[str]:
    """The file-reading, file-writing and execution commands ``tex`` uses (see the module
    docstring), each once, in order of first use, as written (``\\input``, ``\\file_input:n``,
    ``\\pdfstartlink``, ``\\begin{Form}``). PURE."""
    text = _readable(tex)
    found: list[tuple[int, str]] = []
    expl3_spans = []
    for m in _EXPL3_RE.finditer(text):
        found.append((m.start(), m.group(0)))
        expl3_spans.append((m.start(), m.end()))
    for m in _CONTROL_WORD_RE.finditer(text):
        if any(start <= m.start() < end for start, end in expl3_spans):
            continue
        name = m.group(1)
        if name in _LINTED_WORDS or name.startswith("pdf"):
            found.append((m.start(), "\\" + name))
    for m in _FORM_ENV_RE.finditer(text):
        found.append((m.start(), "\\begin{Form}"))
    return list(dict.fromkeys(name for _pos, name in sorted(found)))


def lint_advisories(tex: str, name: str) -> list[str]:
    """One advisory line naming what :func:`lint_commands` finds in ``tex`` (the document
    ``name``), or none. PURE."""
    commands = lint_commands(tex)
    if not commands:
        return []
    return [
        f"LaTeX lint: {name} uses {', '.join(commands)} -- commands that read or write files or "
        "run code; author-written LaTeX is outside sci-adk's checks (it does not judge what the "
        "LaTeX does), so read these lines before compiling (advisory, not gated)"
    ]


__all__ = ["lint_advisories", "lint_commands"]
