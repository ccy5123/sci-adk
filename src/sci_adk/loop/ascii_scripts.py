"""
English-only (ASCII) scripts in a sci-adk research workspace (design/english-only-scripts.md).

The rule: a script a research workspace holds is ASCII-only -- its comments, docstrings,
messages and identifiers are English. A character the data needs (a column name, a unit
sign) is written as an escape, so the file stays ASCII and behaves the same. Why: the record
dump (``runs/<id>/record.tex``) typesets each recorded script with pdflatex, which cannot
typeset other characters, so the record can only NAME such a script instead of showing it
(:func:`sci_adk.render.reproduction.listing_obstacle`).

Which files (:func:`is_ascii_script`): the source files a ``code_ref`` ships
(:func:`sci_adk.loop.code_ref.is_source_path`, and an extensionless file that starts with
``#!``), less :data:`ASCII_EXEMPT_EXTENSIONS` -- Lean, whose standard notation is Unicode;
notebooks; literate documents. Everything else (Markdown, JSON, CSV, LaTeX, data) is free.

Two layers enforce the rule, both through this module:

  1. the workspace PreToolUse hook (``.claude/hooks/sci-adk/ascii-script-gate.sh``) feeds the
     hook input to ``sci-adk check-ascii`` (:func:`check_hook_input`), which refuses a Write,
     Edit or MultiEdit whose new text puts a non-ASCII character into a script, and a
     NotebookEdit that puts one into a code cell;
  2. ``sci-adk append-evidence`` refuses an Evidence item whose ``code_ref`` names such a
     script (:func:`code_ref_violations`); nothing is recorded.

``verify`` adds one advisory per recorded script that holds non-ASCII bytes (recorded before
the rule); never a FAIL. No LLM; the hook check reads only the file being edited (for line
numbers), the record check only the scripts a ``code_ref`` names.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from sci_adk.loop.code_ref import is_source_path, resolve_code_ref_scripts

# @MX:NOTE: [AUTO] The rule's file set is DERIVED from code_ref.SOURCE_EXTENSIONS (the files
#   the record ships and typesets), so a language added there is covered here too. Only a
#   format whose standard text is not ASCII is exempt.
ASCII_EXEMPT_EXTENSIONS = frozenset(
    {
        # Lean 4: Unicode is its standard notation (the formal-proof capability writes it)
        ".lean",
        # notebooks hold prose cells and outputs; the hook checks an .ipynb code cell as it
        # is edited (NotebookEdit)
        ".ipynb", ".nb",
        # literate documents: their prose is a document, not script text
        ".rmd", ".qmd",
    }
)

# The tool calls the hook judges; any other tool passes.
HOOK_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

# Bounds on one message: lines listed, characters listed per line.
_MAX_LINES = 10
_MAX_CHARS = 6

# Characters written as an escape of the same shape, by file extension.
_U_ESCAPE = frozenset(
    {".py", ".pyw", ".pyx", ".pxd", ".sage", ".r", ".jl",
     ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".cu", ".cuh", ".go", ".cs"}
)
_JS_ESCAPE = frozenset({".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx", ".rb"})
_SHELL = frozenset({".sh", ".bash", ".zsh"})

_GUIDANCE = (
    "Write comments, docstrings, messages and names in English. Write a character the data "
    "needs (a column name, a unit sign) as an escape, so the file stays ASCII and works the "
    "same: {example}. Why: the record (runs/<id>/record.tex) typesets each recorded script "
    "with pdflatex, which cannot typeset other characters, so it could only name this script, "
    "not show it."
)


@dataclass(frozen=True)
class NonAsciiLine:
    """One line of text that holds characters outside ASCII.

    Attributes:
        where: the line, as the message names it (``line 12``, ``line 2 of the new text``).
        chars: the distinct non-ASCII characters on it, in first-seen order. A byte that is
            not UTF-8 is its surrogate-escape character (U+DC80..U+DCFF).
    """

    where: str
    chars: Tuple[str, ...]


@dataclass(frozen=True)
class HookDecision:
    """What the PreToolUse hook does with one tool call.

    ``blocked`` -> the hook exits 2 and ``message`` (the reason) reaches the model. Not
    blocked with a ``message`` -> the call goes through UNCHECKED and ``message`` is the
    warning saying why.
    """

    blocked: bool
    message: str = ""


def _name(path: str) -> str:
    return re.split(r"[/\\]", path.strip())[-1]


def _suffix(path: str) -> str:
    stem, dot, suffix = _name(path).rpartition(".")
    return f".{suffix.lower()}" if stem and dot else ""


# @MX:ANCHOR: [AUTO] The one decision of WHICH files the rule covers.
# @MX:REASON: the hook check, the append-evidence refusal and the verify advisory all call
#   it; if they disagreed, a script the hook let through could be refused at record time.
def is_ascii_script(path: str, head: Optional[bytes] = None) -> bool:
    """Whether the ASCII rule covers ``path``. PURE.

    True for a source file a ``code_ref`` ships (by extension or name, see
    :func:`sci_adk.loop.code_ref.is_source_path`), and for an extensionless file when
    ``head`` -- its first bytes -- starts with ``#!``; never for an extension in
    :data:`ASCII_EXEMPT_EXTENSIONS`.
    """
    name = _name(path)
    if not name or _suffix(path) in ASCII_EXEMPT_EXTENSIONS:
        return False
    if is_source_path(path):
        return True
    return "." not in name and head is not None and head[:2] == b"#!"


def _without_cr(line: str) -> str:
    """``line`` without one trailing carriage return: a line of a CRLF file written back with
    LF (or the other way) is the same line."""
    return line[:-1] if line.endswith("\r") else line


def non_ascii_lines(
    text: str, *, first_line: int = 1, of: str = "", known: Sequence[str] = ()
) -> List[NonAsciiLine]:
    """Each line of ``text`` that holds a non-ASCII character, except a line whose text is in
    ``known`` (a line the file already holds, which the call writes back unchanged; one
    trailing carriage return is ignored on both sides, so CRLF and LF lines match). PURE.

    Lines are numbered from ``first_line``; ``of`` is appended to each line's name (e.g.
    ``" of the new text"`` when the text's place in the file is not known).
    """
    out: List[NonAsciiLine] = []
    unchanged = frozenset(_without_cr(line) for line in known)
    for offset, line in enumerate(text.split("\n")):
        if line.isascii() or _without_cr(line) in unchanged:
            continue
        seen: List[str] = []
        for ch in line:
            if ord(ch) > 0x7F and ch not in seen:
                seen.append(ch)
        out.append(NonAsciiLine(where=f"line {first_line + offset}{of}", chars=tuple(seen)))
    return out


def non_ascii_lines_in_bytes(data: bytes) -> List[NonAsciiLine]:
    """:func:`non_ascii_lines` of a file's bytes; a byte that is not UTF-8 is named as a
    byte. PURE."""
    return non_ascii_lines(data.decode("utf-8", "surrogateescape"))


def describe_char(ch: str) -> str:
    """``U+D55C HANGUL SYLLABLE HAN 'X'`` (the character shown when it is visible), or
    ``byte 0xE9 (not UTF-8)``. PURE."""
    cp = ord(ch)
    if 0xDC80 <= cp <= 0xDCFF:
        return f"byte 0x{cp - 0xDC00:02X} (not UTF-8)"
    name = unicodedata.name(ch, "")
    shown = f" '{ch}'" if ch.isprintable() and not ch.isspace() else ""
    return f"U+{cp:04X}" + (f" {name}" if name else "") + shown


def escape_example(path: str, ch: str) -> str:
    """How a script of ``path``'s kind writes ``ch`` as an escape. PURE."""
    cp = ord(ch)
    bs = chr(92)
    suffix = _suffix(path)
    if suffix in _U_ESCAPE:
        esc = f"{bs}u{cp:04x}" if cp <= 0xFFFF else f"{bs}U{cp:08x}"
        return f'"{esc}" for U+{cp:04X}'
    if suffix in _JS_ESCAPE:
        esc = f"{bs}u{cp:04x}" if cp <= 0xFFFF else f"{bs}u{{{cp:x}}}"
        return f'"{esc}" for U+{cp:04X}'
    if suffix in _SHELL:
        octal = "".join(f"{bs}{b:03o}" for b in ch.encode("utf-8"))
        return f"printf '{octal}' (its UTF-8 bytes) for U+{cp:04X}"
    if suffix in (".pl", ".pm"):
        return f'"{bs}x{{{cp:x}}}" for U+{cp:04X}'
    if suffix == ".m":
        return f"char({cp}) for U+{cp:04X}"
    if suffix in (".do", ".ado"):
        return f"uchar({cp}) for U+{cp:04X}"
    return f"the language's escape or character function for code point U+{cp:04X} ({cp})"


def _listing(lines: Sequence[NonAsciiLine]) -> List[str]:
    out = []
    for item in lines[:_MAX_LINES]:
        chars = ", ".join(describe_char(c) for c in item.chars[:_MAX_CHARS])
        more = len(item.chars) - _MAX_CHARS
        out.append(f"  {item.where}: {chars}" + (f" (and {more} more)" if more > 0 else ""))
    if len(lines) > _MAX_LINES:
        out.append(f"  ... and {len(lines) - _MAX_LINES} more lines")
    return out


def _guidance(path: str, lines: Sequence[NonAsciiLine]) -> str:
    first = next(
        (c for item in lines for c in item.chars if not 0xDC80 <= ord(c) <= 0xDCFF), None
    )
    if first is None:
        example = "save the file as UTF-8 first, then write each such character as an escape"
    else:
        example = "e.g. " + escape_example(path, first)
    return _GUIDANCE.format(example=example)


def describe_violation(head: str, path: str, lines: Sequence[NonAsciiLine]) -> str:
    """The multi-line message both layers print: ``head``, the lines with their
    characters, then the escape guidance. PURE."""
    return "\n".join([head, *_listing(lines), _guidance(path, lines)])


# -- layer 1: the PreToolUse hook ---------------------------------------------------------

_UNCHECKED = (
    "the call goes through unchecked; 'sci-adk append-evidence' still refuses to record a "
    "script that holds non-ASCII characters."
)


def _unchecked(why: str) -> HookDecision:
    return HookDecision(blocked=False, message=f"[sci-adk] WARNING: {why}; {_UNCHECKED}")


def _parts(path: str) -> List[str]:
    """``path``'s components, ``.`` dropped and ``..`` applied."""
    out: List[str] = []
    for part in re.split(r"[/\\]", path):
        if part in ("", "."):
            continue
        if part == "..":
            if out:
                out.pop()
            continue
        out.append(part)
    return out


def _is_absolute(path: str) -> bool:
    return path.startswith(("/", "\\")) or re.match(r"[A-Za-z]:[/\\]", path) is not None


def _claude_config_file(path: str, project_dir: Optional[str], cwd: Optional[str]) -> bool:
    """True for a file of the project's own ``.claude/`` directory (Claude Code's hooks,
    agents, skills, settings), which the rule does not cover -- never one under
    ``.claude/worktrees/``: a Claude Code isolation worktree holds a copy of the project's
    scripts. Outside the project (or with no project directory known) a file under a
    ``.claude/`` directory that is not a worktree is one too (the user's ``~/.claude``)."""
    absolute = _is_absolute(path)
    if not absolute and cwd and _is_absolute(cwd):
        path, absolute = cwd + "/" + path, True
    parts = _parts(path)
    if project_dir and absolute:
        project = _parts(project_dir)
        if parts[: len(project)] == project:
            inside = parts[len(project):]
            return inside[:1] == [".claude"] and inside[1:2] != ["worktrees"]
    for k, part in enumerate(parts):
        if part == ".claude":
            return parts[k + 1 : k + 2] != ["worktrees"]
    return False


def _read_text(path: str, cwd: Optional[str]) -> Optional[str]:
    target = Path(path)
    if not target.is_absolute() and cwd:
        target = Path(cwd) / target
    try:
        return target.read_bytes().decode("utf-8", "surrogateescape")
    except (OSError, ValueError):
        return None


def _edit_pieces(
    current: Optional[str], edits: Sequence[Tuple[str, str, bool]]
) -> Tuple[List[Tuple[str, Optional[int]]], Optional[str]]:
    """Apply ``edits`` (old, new, replace_all) to ``current`` in memory, in order.

    Returns each edit's new text with the file line it starts on (``None`` once an old text
    is not found -- the tool will fail on it, so later places are unknown), and the text
    the edits produce (``None`` when unknown). A file that does not exist is empty.
    """
    text = "" if current is None else current
    pieces: List[Tuple[str, Optional[int]]] = []
    for old, new, replace_all in edits:
        index = text.find(old) if text is not None else -1
        if text is None or index < 0:
            pieces.append((new, None))
            text = None
            continue
        pieces.append((new, text.count("\n", 0, index) + 1))
        text = (text.replace(old, new) if replace_all
                else text[:index] + new + text[index + len(old):])
    return pieces, text


def _edits_of(tool: str, tool_input: dict) -> Optional[List[Tuple[str, str, bool]]]:
    raw = [tool_input] if tool == "Edit" else tool_input.get("edits")
    if not isinstance(raw, list):
        return None
    edits = []
    for edit in raw:
        if not isinstance(edit, dict):
            return None
        old, new = edit.get("old_string", ""), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        edits.append((old, new, bool(edit.get("replace_all", False))))
    return edits


def check_hook_input(raw: str, project_dir: Optional[str] = None) -> HookDecision:
    """Judge one PreToolUse hook input (the JSON Claude Code writes to the hook's stdin).

    Blocks a Write (``content``), Edit (``new_string``) or MultiEdit (every
    ``new_string``) that would put a non-ASCII character into a file :func:`is_ascii_script`
    covers, and a NotebookEdit whose new source for a code cell holds one (a markdown cell,
    or a deletion, passes). A line the call writes back unchanged is not judged: for an Edit
    or MultiEdit a line of its old text, for a Write a line the file already holds (a script
    written before the rule stays editable). A file of the project's own ``.claude/``
    directory (``project_dir``, else the input's ``cwd``; not ``.claude/worktrees/``) and any
    other tool pass. An input that cannot be read passes with a warning: the record-time
    check still applies. Reads the file being edited, only for its line numbers and lines.
    """
    try:
        payload = json.loads(raw)
    except ValueError as e:
        return _unchecked(f"could not read the hook input as JSON ({e})")
    if not isinstance(payload, dict):
        return _unchecked("the hook input is not a JSON object")
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return _unchecked("the hook input names no tool_name")
    if tool not in HOOK_TOOLS:
        return HookDecision(blocked=False)
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return _unchecked(f"the {tool} hook input has no tool_input object")
    path = tool_input.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    if not isinstance(path, str) or not path:
        return _unchecked(f"the {tool} hook input names no file")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    if _claude_config_file(path, project_dir or cwd, cwd):
        return HookDecision(blocked=False)

    if tool == "NotebookEdit":
        if tool_input.get("edit_mode") == "delete" or tool_input.get("cell_type") == "markdown":
            return HookDecision(blocked=False)
        source = tool_input.get("new_source")
        if not isinstance(source, str):
            return _unchecked("the NotebookEdit hook input has no new_source text")
        lines = non_ascii_lines(source, of=" of the cell")
        what = f"a code cell of the notebook {path}"
    elif tool == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str):
            return _unchecked("the Write hook input has no content text")
        if not is_ascii_script(path, content[:2].encode("utf-8", "surrogateescape")):
            return HookDecision(blocked=False)
        current = _read_text(path, cwd) if not content.isascii() else None
        lines = non_ascii_lines(content, known=current.split("\n") if current else ())
        what = f"the script {path}"
    else:
        edits = _edits_of(tool, tool_input)
        if edits is None:
            return _unchecked(f"the {tool} hook input has no old_string/new_string text")
        current = _read_text(path, cwd)
        pieces, result = _edit_pieces(current, edits)
        head_text = result if result is not None else (current or "")
        if not is_ascii_script(path, head_text[:2].encode("utf-8", "surrogateescape")):
            return HookDecision(blocked=False)
        lines = []
        for number, ((new, start), (old, _new, _all)) in enumerate(zip(pieces, edits), start=1):
            known = old.split("\n")
            if start is not None:
                lines += non_ascii_lines(new, first_line=start, known=known)
            else:
                label = " of the new text" if tool == "Edit" else f" of edit {number}'s new text"
                lines += non_ascii_lines(new, of=label, known=known)
        what = f"the script {path}"

    if not lines:
        return HookDecision(blocked=False)
    head = (f"[sci-adk] Blocked: this {tool} puts non-ASCII characters into {what}; "
            "a script in a research workspace is ASCII-only:")
    return HookDecision(blocked=True, message=describe_violation(head, path, lines))


# -- layer 2: the record-time refusal -----------------------------------------------------


@dataclass(frozen=True)
class ScriptViolation:
    """A script a ``code_ref`` names that holds non-ASCII bytes."""

    path: str  # as the code_ref names it
    file: Path  # the file it resolved to
    lines: Tuple[NonAsciiLine, ...]


def code_ref_violations(
    code_ref: str, run_dir: Path, workspace_dir: Path
) -> List[ScriptViolation]:
    """Each script ``code_ref`` names -- read the way the reproduction bundle reads it
    (:func:`sci_adk.loop.code_ref.resolve_code_ref_scripts`) -- that the rule covers and
    that holds a byte outside ASCII. Reads only those files; a file that cannot be read is
    skipped (the bundle reports it)."""
    out: List[ScriptViolation] = []
    for named in resolve_code_ref_scripts(code_ref, run_dir, workspace_dir):
        script = named.resolution.script
        if script is None:
            continue
        try:
            data = Path(script).read_bytes()
        except OSError:
            continue
        if data.isascii() or not is_ascii_script(named.path, data[:2]):
            continue
        out.append(ScriptViolation(named.path, Path(script),
                                   tuple(non_ascii_lines_in_bytes(data))))
    return out


def refusal_message(evidence_id: str, violations: Sequence[ScriptViolation]) -> str:
    """The ``error: ...`` append-evidence prints when it refuses an item. PURE."""
    parts = []
    for index, v in enumerate(violations):
        head = (f"error: Evidence '{evidence_id}' was not appended (nothing was recorded): its "
                f"code_ref names {v.path}, a script that holds non-ASCII characters; a script "
                "in a research workspace is ASCII-only:") if index == 0 else (
                f"also {v.path}:")
        parts.append(describe_violation(head, v.path, v.lines))
    return "\n".join(parts)


def recorded_advisory(evidence_id: str, violation: ScriptViolation) -> str:
    """The one-line ``verify`` advisory for a recorded script holding non-ASCII bytes.
    PURE."""
    first = violation.lines[0] if violation.lines else NonAsciiLine("line ?", ())
    chars = ", ".join(describe_char(c) for c in first.chars[:3])
    count = len(violation.lines)
    return (
        f"{evidence_id}'s code_ref names {violation.path}, a script that holds non-ASCII "
        f"characters ({first.where}: {chars}"
        + (f"; {count} lines in all" if count > 1 else "")
        + "), so the record names it without showing it; it was recorded before scripts had "
        "to be ASCII-only, and append-evidence now refuses such a script (write each such "
        "character as an escape)"
    )


__all__ = [
    "ASCII_EXEMPT_EXTENSIONS",
    "HOOK_TOOLS",
    "HookDecision",
    "NonAsciiLine",
    "ScriptViolation",
    "check_hook_input",
    "code_ref_violations",
    "describe_char",
    "describe_violation",
    "escape_example",
    "is_ascii_script",
    "non_ascii_lines",
    "non_ascii_lines_in_bytes",
    "recorded_advisory",
    "refusal_message",
]
