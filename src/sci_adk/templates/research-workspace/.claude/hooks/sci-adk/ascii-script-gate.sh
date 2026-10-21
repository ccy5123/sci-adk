#!/bin/bash
# sci-adk research-session enforcement: English-only (ASCII) scripts (PreToolUse hook on
# Write, Edit, MultiEdit and NotebookEdit).
#
# Contract (design/english-only-scripts.md):
#   A script in a research workspace is ASCII-only: comments, docstrings, messages and names
#   in English; a character the data needs is written as an escape. Before a Write, Edit,
#   MultiEdit or NotebookEdit runs, this hook refuses it when the text it would write puts a
#   character outside ASCII into a script -- a source file such as .py .R .jl .m .sh .do
#   .sql, an extensionless file that starts with #!, or a notebook code cell. Lean (.lean) is
#   exempt: its standard notation is Unicode. Other files (.md .json .csv .tex, data) and
#   files under .claude/ are not checked.
#   A refusal is exit 2: Claude Code cancels the call and shows our stderr -- the file, the
#   lines, the characters with their code points, and how to write them as escapes -- to
#   the model.
#   Why: the record (runs/<id>/record.tex) typesets each recorded script with pdflatex,
#   which cannot typeset other characters, so the record could only name such a script.
#   The decision is sci-adk's ('sci-adk check-ascii', the same file set the record-time
#   refusal in 'sci-adk append-evidence' uses); this script only hands it the hook input.
#
# Properties:
#   - fast paths, without starting sci-adk: a Write/Edit/MultiEdit of one file whose
#     extension is a document's (doc_exts below: never a script) passes at once; so does an
#     input with no byte above 0x7F and no JSON escape of such a character (it cannot put one
#     into a file). An input shaped like a JSON object but not valid JSON passes that second
#     test silently when it holds no such byte: no character outside ASCII can reach a script
#     that way.
#   - an input that is not a JSON object ({...}) at all is one the hook cannot read: the call
#     goes through with a warning.
#   - graceful: no input, a missing sci-adk, one older than this hook, or one that fails
#     (any exit but 0 and 3: a crash is Python's 1) lets the call through with a warning
#     (stderr, plus a JSON systemMessage on stdout so the user sees it); 'sci-adk
#     append-evidence' still refuses to record such a script. Only exit 3, which 'sci-adk
#     check-ascii' gives for a refusal and nothing else gives, blocks.
#   - pure bash, no jq.

SCIADK="${SCI_ADK_CMD:-sci-adk}"

# A one-line string as JSON string content (control characters dropped).
json_escape() {
	printf '%s' "$1" | tr -d '\000-\037' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

# Let the call through, with a warning the user sees.
allow_with_warning() {
	printf '%s\n' "$1" >&2
	printf '{"systemMessage": "%s"}\n' "$(json_escape "$1")"
	exit 0
}

unchecked="the call goes through unchecked; 'sci-adk append-evidence' still refuses to record a script that holds non-ASCII characters."

payload=""
if [ ! -t 0 ]; then
	IFS= read -r -d '' -t 10 payload || true
fi
if [ -z "$payload" ]; then
	allow_with_warning "[sci-adk] WARNING: the English-only scripts hook got no hook input on stdin; ${unchecked}"
fi

# Claude Code's hook input is one JSON object: anything else is input this hook cannot read.
trimmed="${payload#"${payload%%[![:space:]]*}"}"
trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
case "$trimmed" in
	"{"*"}") ;;
	*) allow_with_warning "[sci-adk] WARNING: the English-only scripts hook could not read its hook input (not a JSON object); ${unchecked}" ;;
esac

# A document target passes at once. The one "file_path" of a Write, Edit or MultiEdit (a
# NotebookEdit names notebook_path, a notebook, which is checked) is read when it holds no
# quote or backslash; its extension, lower case, against doc_exts (none is a script; a test
# holds the list against the rule's own file set).
doc_exts="md markdown txt rst csv tsv json jsonl yaml yml toml tex bib bst cls sty html htm xml svg log lean"
if [ "$(printf '%s' "$payload" | grep -o '"file_path"[[:space:]]*:' | wc -l)" -eq 1 ]; then
	target=$(printf '%s' "$payload" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"\\]*\)".*/\1/p' | head -n 1)
	name="${target##*/}"
	case "$name" in
		?*.*)
			ext=$(printf '%s' "${name##*.}" | tr 'A-Z' 'a-z')
			for doc in $doc_exts; do
				[ "$ext" = "$doc" ] && exit 0
			done
			;;
	esac
fi

# Fast path: no byte above 0x7F, and no JSON escape (backslash, u, 4 hex digits) of a code
# point above 0x7F. A literal escape in source text (an escaped backslash in JSON) also
# matches the pattern; sci-adk then decodes the input and allows it.
non_ascii_byte=$(printf '%s' "$payload" | LC_ALL=C tr -d '\000-\177' | head -c 1)
if [ -z "$non_ascii_byte" ] \
	&& ! printf '%s' "$payload" | grep -Eq '\\u(00[89a-fA-F]|0[1-9a-fA-F]|[1-9a-fA-F])'; then
	exit 0
fi

sciadk_cmd="${SCIADK%% *}"
if ! command -v "$sciadk_cmd" >/dev/null 2>&1; then
	allow_with_warning "[sci-adk] WARNING: cannot check this call for non-ASCII script text: '${sciadk_cmd}' is not on PATH; ${unchecked}"
fi

out=$(printf '%s' "$payload" | $SCIADK check-ascii 2>&1)
rc=$?
case "$rc" in
	0)
		# allowed; any output is the warning that it went through unchecked
		[ -z "$out" ] || allow_with_warning "$out"
		exit 0
		;;
	3)
		printf '%s\n' "$out" >&2
		exit 2
		;;
	*)
		case "$out" in
			*"invalid choice: 'check-ascii'"*)
				why="the installed sci-adk is older than this hook (it has no 'check-ascii'): upgrade sci-adk" ;;
			*)
				# the last line: a crash's exception, argparse's error
				why="'sci-adk check-ascii' exited ${rc}: $(printf '%s' "$out" | tail -n 1)" ;;
		esac
		allow_with_warning "[sci-adk] WARNING: could not check this call for non-ASCII script text (${why}); ${unchecked}"
		;;
esac
