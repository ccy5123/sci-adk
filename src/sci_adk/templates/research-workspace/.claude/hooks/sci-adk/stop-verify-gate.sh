#!/bin/bash
# sci-adk research-session enforcement: the HARD gate (Stop hook).
#
# Contract (design/research-session-enforcement.md, Layer 1 + D2 + D4;
#           SPEC-PAPER-GATE-001 P1, REQ-PG-104):
#   On Stop, audit every recorded conclusion against the record, in two classes.
#     1. Claim reproduction -- blocks EVERY Stop. Each run with >=1 recorded Claim must
#        pass `sci-adk verify --claims-only <run>`: every recorded claim re-derives from
#        the record (no DIVERGED / UNRESOLVED) and every novelty found-nothing rests on a
#        sound search log.
#     2. Paper side -- blocks the FIRST Stop only. For a run whose claims reproduce, the
#        full `sci-adk verify <run>` (manuscript consistency, numbers, publishing
#        requirements, deposit files, ...); and, when a package/ exists, the workspace
#        package gate `sci-adk verify <workspace>`. Claude Code retries a Stop that a hook
#        blocked with "stop_hook_active": true in the hook-input JSON on stdin; on that
#        retry a paper-side failure no longer blocks -- the hook exits 0 and warns (stderr,
#        plus a JSON systemMessage on stdout so the user sees it). The session that hits a
#        paper-side failure may not own the paper (an experiment session told not to touch
#        it); blocking it again only loops until Claude Code force-ends the turn.
#   A block is exit 2: Claude Code keeps the session going and shows our stderr -- each
#   failing run and the lines verify printed for it -- to the model.
#   verify's exit code is unchanged and stays the verdict; this hook only decides how often
#   a failure may hold the session open.
#
# Properties:
#   - runs are discovered from $CLAUDE_PROJECT_DIR (the documented project-root env var
#     Claude Code sets for hooks), falling back to $PWD -- never from the stdin payload.
#     A hook's CWD is NOT guaranteed to be the project root, so do not rely on it.
#   - stdin is read once and never waited on from a terminal; an empty or unreadable
#     payload counts as a first Stop.
#   - graceful: a missing sci-adk or a missing runs/ never bricks a session.
#   - D2 strictness: only a run WITH a recorded claim is verified, and the package gate
#     runs only when a package/ exists -- exploratory turns with no run / no claim / no
#     package pass silently (low noise -> gate stays on).
#   - pure bash, no jq.

SCIADK="${SCI_ADK_CMD:-sci-adk}"

# Resolve the first token of the command; if it is not runnable, degrade to 0.
# (Same contract as the MoAI wrappers: a missing tool never blocks a session.)
sciadk_cmd="${SCIADK%% *}"
if ! command -v "$sciadk_cmd" >/dev/null 2>&1; then
	exit 0
fi

# Hook input: Claude Code writes one JSON object to stdin. Only stop_hook_active is read,
# by pattern (no jq). True means this Stop retries one that a Stop hook already blocked.
stop_hook_active=0
if [ ! -t 0 ]; then
	payload=""
	IFS= read -r -d '' -t 5 payload || true
	if printf '%s' "$payload" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
		stop_hook_active=1
	fi
fi

# The lines of a verify report that say what failed: claim lines that did not reproduce,
# error lines, and each "... FAILED" header with its first three bullets (the rest
# counted). At most 20 lines.
failure_lines() {
	awk '
		function flush_more() {
			if (more > 0) print "      ... (" more " more)"
			more = 0
		}
		/ FAILED/ { flush_more(); print; inblock = 1; shown = 0; next }
		inblock && /^    - / {
			if (shown < 3) { print; shown++ } else { more++ }
			next
		}
		{ flush_more(); inblock = 0 }
		/DIVERGED|UNRESOLVED|NOT reproduced|(^|: )error: / { print }
		END { flush_more() }
	' | head -n 20
}

# One target's part of a message: its label, then its failure lines -- or, when verify
# printed none, the command that shows the full report.
#   $1 = label, $2 = what to pass to `sci-adk verify`, $3 = verify's merged output
section() {
	local lines
	lines=$(printf '%s\n' "$3" | failure_lines)
	printf '[sci-adk]   %s\n' "$1"
	if [ -n "$lines" ]; then
		printf '%s\n' "$lines"
	else
		printf '      (no FAILED line in the output; run: sci-adk verify %s)\n' "$2"
	fi
}

# A one-line string as JSON string content (control characters dropped).
json_escape() {
	printf '%s' "$1" | tr -d '\000-\037' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

ws_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
runs_dir="$ws_dir/runs"

claim_failed=""
claim_report=""
paper_failed=""
paper_report=""

# Per-run audit (D2): only a run that HAS >=1 recorded claim (a claims/ dir containing at
# least one *.json). No claim -> nothing to protect -> verify is not run on it.
if [ -d "$runs_dir" ]; then
	for run in "$runs_dir"/*/; do
		# the glob is literal if runs/ is empty
		[ -d "$run" ] || continue

		claims_dir="${run}claims"
		[ -d "$claims_dir" ] || continue
		has_claim=0
		for cj in "$claims_dir"/*.json; do
			[ -f "$cj" ] || continue
			has_claim=1
			break
		done
		[ "$has_claim" -eq 1 ] || continue

		# strip the trailing slash for a clean run-dir argument / report label
		run_path="${run%/}"

		# 1. claim reproduction: blocks every Stop
		if ! out=$($SCIADK verify --claims-only "$run_path" 2>&1); then
			case "$out" in
				*"unrecognized arguments: --claims-only"*) sciadk_too_old=1 ;;
			esac
			claim_failed="${claim_failed} ${run_path}"
			claim_report="${claim_report}$(section "$run_path" "$run_path" "$out")
"
			continue
		fi

		# 2. the full gate: the claims reproduce, so what fails here is paper-side
		if ! out=$($SCIADK verify "$run_path" 2>&1); then
			paper_failed="${paper_failed} ${run_path}"
			paper_report="${paper_report}$(section "$run_path" "$run_path" "$out")
"
		fi
	done
fi

# SPEC-PAPER-GATE-001 MP-5 (REQ-PG-104): the workspace PACKAGE gate, when a
# conclusion-bearing package/ exists (an unbacked number, a missing frozen pkgreqs.json,
# an unresolved cite, ...). Paper-side: it blocks once. No package/ -> nothing to gate.
if [ -d "${ws_dir}/package" ]; then
	if ! out=$($SCIADK verify "$ws_dir" 2>&1); then
		paper_failed="${paper_failed} ${ws_dir}/package"
		paper_report="${paper_report}$(section "${ws_dir}/package" "$ws_dir" "$out")
"
	fi
fi

if [ -n "$claim_failed" ]; then
	{
		echo "[sci-adk] Stop blocked: a recorded claim does not re-derive from its record ('sci-adk verify --claims-only' fails) for:${claim_failed}"
		printf '%s' "$claim_report"
		if [ "${sciadk_too_old:-0}" -eq 1 ]; then
			echo "[sci-adk] The installed sci-adk is older than this hook (it has no 'verify --claims-only'): upgrade sci-adk. Until then this hook cannot tell a claim failure from a paper-side one, so every verify failure blocks every Stop."
		elif printf '%s' "$claim_report" | grep -qE 'DIVERGED|UNRESOLVED|NOT reproduced'; then
			echo "[sci-adk] Re-derive the claims with 'sci-adk resolve <run>' (author any missing verdict first) or correct the record, then check with 'sci-adk verify --claims-only <run>'. This blocks every Stop until the recorded claims reproduce."
		else
			echo "[sci-adk] 'sci-adk verify --claims-only' could not check the record (see the error above): fix the record files it names, then check with 'sci-adk verify --claims-only <run>'. This blocks every Stop until it passes."
		fi
		if [ -n "$paper_failed" ]; then
			echo "[sci-adk] Also failing on the paper side (that part blocks only once):${paper_failed}"
			printf '%s' "$paper_report"
		fi
	} >&2
	exit 2
fi

if [ -n "$paper_failed" ]; then
	if [ "$stop_hook_active" -eq 0 ]; then
		{
			echo "[sci-adk] Stop blocked once: the recorded claims reproduce, but 'sci-adk verify' fails on the paper side for:${paper_failed}"
			printf '%s' "$paper_report"
			echo "[sci-adk] These are paper-side checks (the manuscript, its numbers, publishing requirements, deposit files, the package). Fix them if this session owns the paper; if it does not, say so and stop again -- a paper-side failure blocks only once, and the next Stop ends the session with a warning."
		} >&2
		exit 2
	fi
	warning="[sci-adk] WARNING: the session ends while 'sci-adk verify' still fails on the paper side for:${paper_failed} -- the session that owns the paper must fix it ('sci-adk verify <run>' lists the reasons)."
	{
		echo "$warning"
		printf '%s' "$paper_report"
	} >&2
	printf '{"systemMessage": "%s"}\n' "$(json_escape "$warning")"
	exit 0
fi

exit 0
