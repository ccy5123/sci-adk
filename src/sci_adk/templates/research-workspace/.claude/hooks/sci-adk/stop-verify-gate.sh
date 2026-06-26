#!/bin/bash
# sci-adk research-session enforcement: the HARD gate (Stop hook).
#
# Contract (design/research-session-enforcement.md, Layer 1 + D2 + D4;
#           SPEC-PAPER-GATE-001 P1, REQ-PG-104):
#   On Stop, audit every recorded conclusion against the record:
#     1. Per-run claim reproduction (D2): a run that has >=1 recorded Claim
#        must reproduce from its record (`sci-adk verify <run>` exits 0).
#     2. Package gate (MP-5): when a conclusion-bearing `package/` exists, the
#        workspace package gate (`sci-adk verify <workspace>`) must pass too.
#   If any audited conclusion fails -> exit 2 (Claude Code blocks the Stop and
#   shows our stderr to the model). Otherwise -> exit 0.
#
# Properties:
#   - reads NO stdin; run discovery uses $CLAUDE_PROJECT_DIR (the documented
#     project-root env var Claude Code sets for hooks), falling back to $PWD.
#     A hook's CWD is NOT guaranteed to be the project root, so do not rely on it.
#   - graceful: a missing sci-adk or a missing runs/ never bricks a session.
#   - D2 strictness: only a run WITH a recorded claim is verified, and the
#     package gate runs only when a package/ exists -- exploratory turns with no
#     run / no claim / no package pass silently (low noise -> gate stays on).
#   - pure bash, no jq.

SCIADK="${SCI_ADK_CMD:-sci-adk}"

# Resolve the first token of the command; if it is not runnable, degrade to 0.
# (Same contract as the MoAI wrappers: a missing tool never blocks a session.)
sciadk_cmd="${SCIADK%% *}"
if ! command -v "$sciadk_cmd" >/dev/null 2>&1; then
	exit 0
fi

ws_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
runs_dir="$ws_dir/runs"

failed=""

# 1. Per-run claim-reproduction audit (D2): only consider a run that HAS >=1
#    recorded claim (a claims/ dir containing at least one *.json). No claim ->
#    nothing to protect -> do NOT run verify on it. (Unchanged by SPEC-PAPER-GATE-001;
#    the package gate below is ADDITIVE alongside it.)
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
		if ! $SCIADK verify "$run_path" >/dev/null 2>&1; then
			failed="${failed} ${run_path}"
		fi
	done
fi

# 2. SPEC-PAPER-GATE-001 MP-5 (REQ-PG-104): ALSO run the workspace PACKAGE gate at
#    session close when a conclusion-bearing package/ exists. `sci-adk verify <ws>`
#    (which verify_package backs) blocks Stop too if the package gate fails (an
#    unbacked number, a missing frozen pkgreqs.json, an unresolved cite, ...).
#    D2-style strictness: no package/ -> nothing to gate (low noise).
if [ -d "${ws_dir}/package" ]; then
	if ! $SCIADK verify "$ws_dir" >/dev/null 2>&1; then
		failed="${failed} ${ws_dir}/package"
	fi
fi

if [ -n "$failed" ]; then
	{
		echo "[sci-adk] Stop blocked: a recorded conclusion does not pass 'sci-adk verify'."
		echo "[sci-adk] Failed (DIVERGED/UNRESOLVED run or package gate):${failed}"
		echo "[sci-adk] Resolve DIVERGED/UNRESOLVED claims via 'sci-adk resolve', or fix the package gate's reported reasons, before ending the session."
	} >&2
	exit 2
fi

exit 0
