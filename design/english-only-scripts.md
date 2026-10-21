# English-only (ASCII) scripts in a research workspace

> Status: BUILT (user decision 2026-10-20). Code: `src/sci_adk/loop/ascii_scripts.py`;
> tests: `tests/test_english_only_scripts.py`, `tests/test_english_only_round2.py`,
> `tests/test_english_only_round3.py`, `tests/test_english_only_round4.py`.

## Rule

A script in a sci-adk research workspace is ASCII-only: its comments, docstrings, messages and
identifiers are in English. A character the data needs (a Korean column name, a micro sign, a
degree sign) is written as an escape, so the file stays ASCII and behaves the same:

| Language | U+00B5 written as |
|---|---|
| Python, R, Julia, C, C++, CUDA, Go, C# | `"\u00b5"` (`\U0001f600` above U+FFFF) |
| JavaScript, TypeScript, Ruby | `"\u00b5"` (`\u{1f600}` above U+FFFF) |
| shell | `printf '\302\265'` (the UTF-8 bytes in octal) |
| Perl | `"\x{b5}"` |
| MATLAB | `char(181)` |
| Stata | `uchar(181)` |

Why: the record dump `runs/<id>/record.tex` typesets each recorded script in an `lstlisting`
with pdflatex, which cannot typeset characters outside ASCII. The record therefore names such a
script, with the reason, instead of showing it (`listing_obstacle` in
`src/sci_adk/render/reproduction.py`); the script still ships byte for byte under `paper/code/`.

Scope: the research-workspace kit that `sci-adk init-session` installs. The sci-adk development
repository is not covered. Existing scripts are not rewritten.

## Which files

The rule covers the source files a `code_ref` ships: `SOURCE_EXTENSIONS` and
`SOURCE_FILE_NAMES` in `src/sci_adk/loop/code_ref.py`, and an extensionless file that starts
with `#!`. Deriving the set from the shipping rule means a file the record would typeset is
always a file the rule covers. `.pyw` was added to `SOURCE_EXTENSIONS` (Python source).

Exempt (`ASCII_EXEMPT_EXTENSIONS`):

- `.lean`: Lean 4's standard notation is Unicode (U+2200 FOR ALL, U+2192 RIGHTWARDS ARROW,
  U+2115 for the natural numbers); the formal-proof capability writes it.
- `.ipynb`, `.nb`: notebooks hold prose cells and outputs. The hook checks an `.ipynb` code
  cell when NotebookEdit writes it.
- `.rmd`, `.qmd`: literate documents, whose prose is a document.

Every other file (Markdown, JSON, CSV, LaTeX, data) is not checked, nor is a file of the
project's own `.claude/` directory (Claude Code's hooks, agents, skills; the project is
`CLAUDE_PROJECT_DIR`, else the hook input's `cwd`). A file under `.claude/worktrees/` is checked:
a Claude Code isolation worktree holds a copy of the project's scripts.

## Two layers

1. **Write time.** The PreToolUse hook `.claude/hooks/sci-adk/ascii-script-gate.sh`, on Write,
   Edit, MultiEdit and NotebookEdit. An input that is not a JSON object (`{...}`) is one the hook
   cannot read (below). Two inputs pass at once, without starting sci-adk: a Write, Edit or
   MultiEdit of one file whose extension is a document's (the hook's `doc_exts`: `.md`, `.csv`,
   `.json`, `.tex`, `.lean` ...; a test holds the list against the rule's file set, so none is a
   script), and an input with no byte above 0x7F and no JSON escape of one. An input shaped
   like a JSON object but not valid JSON passes the second test without a warning when it holds
   no such byte: no character outside ASCII can reach a script that way. Otherwise the hook
   hands the input to `sci-adk check-ascii` (an internal verb, outside the public CLI: `sci-adk
   --help` and the verb list leave it out, user decision 2026-10-21;
   `design/surface-freeze-analysis.md`), which judges the text the call would write: the Write `content`, the
   Edit `new_string`, every MultiEdit `new_string`, a NotebookEdit code cell's `new_source`. A
   line written back unchanged is not judged (a line of the edit's old text; for a Write, a
   line the file already holds; one trailing carriage return is ignored, so an LF Write over a
   CRLF script keeps its lines), so a script written before the rule stays editable. A
   violation is exit 3 from `check-ascii`, which only a refusal gives, and the hook then exits 2;
   the message names the file, each line (the file's own line number when the edit's old text
   is found in the file), each character with its code point and Unicode name, and the escape
   for that file's language. An input the hook cannot read, a missing sci-adk, one older than
   the hook, or a `check-ascii` that fails in any other way (Python exits 1 on a crash) lets the
   call through with a warning on stderr and in a JSON `systemMessage`.
2. **Record time.** `sci-adk append-evidence` reads the item's `code_ref` as the reproduction
   bundle does (`resolve_code_ref_scripts`) and refuses the item, exit 2 with `error: ...` and
   nothing recorded, when a named script the rule covers holds a byte outside ASCII. A byte
   that is not UTF-8 is named as a byte. It is the only verb that records a `code_ref` a user
   writes: `execute` and `run` record what the capability writes (a Lean file or a commit
   hash), and the decision verbs record fixed pointers.

## Scripts recorded before the rule

`verify` prints one advisory per recorded script that holds non-ASCII bytes, naming the first
Evidence item whose `code_ref` names it, as `advisory:` whether or not a publishing contract is
frozen. It never fails a run for this.

## Limits

- The hook judges new text only. A non-ASCII character already in a file stays until a call
  rewrites that text.
- The hook sees only the Write, Edit, MultiEdit and NotebookEdit tools. A script written through
  the Bash tool (a heredoc, `python -c`, `sed -i`) is not checked when it is written; the
  record-time refusal in `append-evidence` is then the check.
- A notebook written whole by Write, or named in a `code_ref`, is not checked. A NotebookEdit
  that replaces a cell without naming its `cell_type` is judged as a code cell.
- A workspace installed before this change keeps its `CLAUDE.md`. Re-running `init-session`
  installs the hook file (absent before) and merges the PreToolUse entry into
  `.claude/settings.json`; it does not rewrite an existing `CLAUDE.md` or skill file.
