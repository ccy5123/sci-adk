#!/bin/bash
# sci-adk research-session enforcement: re-anchor (UserPromptSubmit hook).
#
# Contract (design/research-session-enforcement.md, Layer 2 + D1):
#   On every user turn, this hook's STDOUT is injected into the model's
#   context. Re-deliver the discipline (a one-line protocol reminder) PLUS the
#   current run's session-state (via the read-only `sci-adk status <run>`
#   verb). This is the direct antidote to compaction drift: the rule is
#   re-applied each turn instead of relying on the model to remember it.
#
# Properties:
#   - reads NO stdin; run discovery uses $CLAUDE_PROJECT_DIR (the documented
#     project-root env var Claude Code sets for hooks), falling back to $PWD.
#   - graceful: missing sci-adk or missing runs/ -> exit 0, print nothing
#     load-bearing (never brick a session).
#   - picks the MOST-RECENTLY-MODIFIED run dir as "the current run".
#   - pure bash, no jq. exit 0 ALWAYS (a re-anchor never blocks a turn).

SCIADK="${SCI_ADK_CMD:-sci-adk}"

sciadk_cmd="${SCIADK%% *}"
if ! command -v "$sciadk_cmd" >/dev/null 2>&1; then
	exit 0
fi

runs_dir="${CLAUDE_PROJECT_DIR:-$PWD}/runs"
[ -d "$runs_dir" ] || exit 0

# Find the most-recently-modified run dir and count how many run dirs exist.
latest=""
latest_mtime=-1
count=0
for run in "$runs_dir"/*/; do
	[ -d "$run" ] || continue
	count=$((count + 1))
	# %Y = seconds since epoch; portable on GNU/Linux (WSL ubuntu, per D4)
	mtime=$(stat -c %Y "$run" 2>/dev/null || echo 0)
	if [ "$mtime" -gt "$latest_mtime" ]; then
		latest_mtime="$mtime"
		latest="${run%/}"
	fi
done

# No run dirs yet -> nothing to anchor to (the /research entry point + persona
# handle the "you never started a run" nudge). Exit quietly.
[ -n "$latest" ] || exit 0

echo "[sci-adk] You are under research discipline: agents propose, the engine judges. No conclusion bypasses 'sci-adk verify'."
$SCIADK status "$latest" 2>/dev/null

if [ "$count" -gt 1 ]; then
	others=$((count - 1))
	echo "[sci-adk] (${others} other run dir(s) present; showing the most recent — pass a run dir to 'sci-adk status' for the others.)"
fi

exit 0
