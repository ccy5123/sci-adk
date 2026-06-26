#!/bin/bash
# sci-adk research-session enforcement: the HARD gate (Stop hook).
#
# Contract (design/research-session-enforcement.md, Layer 1 + D2 + D4):
#   On Stop, audit every run that has recorded belief. A run that has >=1
#   recorded Claim must reproduce from its record (`sci-adk verify` exits 0).
#   If any such run does NOT reproduce -> exit 2 (Claude Code blocks the Stop
#   and shows our stderr to the model). Otherwise -> exit 0.
#
# Properties:
#   - reads NO stdin; run discovery uses $CLAUDE_PROJECT_DIR (the documented
#     project-root env var Claude Code sets for hooks), falling back to $PWD.
#     A hook's CWD is NOT guaranteed to be the project root, so do not rely on it.
#   - graceful: a missing sci-adk or a missing runs/ never bricks a session.
#   - D2 strictness: only a run WITH a recorded claim is verified; exploratory
#     turns with no run / no claim pass silently (low noise -> gate stays on).
#   - pure bash, no jq.

SCIADK="${SCI_ADK_CMD:-sci-adk}"

# Resolve the first token of the command; if it is not runnable, degrade to 0.
# (Same contract as the MoAI wrappers: a missing tool never blocks a session.)
sciadk_cmd="${SCIADK%% *}"
if ! command -v "$sciadk_cmd" >/dev/null 2>&1; then
	exit 0
fi

runs_dir="${CLAUDE_PROJECT_DIR:-$PWD}/runs"
[ -d "$runs_dir" ] || exit 0

failed=""
for run in "$runs_dir"/*/; do
	# the glob is literal if runs/ is empty
	[ -d "$run" ] || continue

	# D2 gate: only consider a run that HAS >=1 recorded claim
	# (a claims/ dir containing at least one *.json). No claim -> nothing to
	# protect -> do NOT run verify on it.
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

# @MX:TODO: [AUTO] SPEC-PAPER-GATE-001 MP-5 (REQ-PG-104, deferred to the next increment): ALSO
#   run the workspace PACKAGE gate at session close -- `$SCIADK verify "${CLAUDE_PROJECT_DIR:-$PWD}"`
#   (which `verify_package` backs) -- and add its failure to $failed so a conclusion-bearing
#   package/ that fails the gate (unbacked number, missing frozen pkgreqs.json, unresolved cite)
#   BLOCKS Stop too. The per-run loop above (the claim-reproduction audit) stays unchanged; the
#   package gate is ADDITIVE alongside it.

if [ -n "$failed" ]; then
	{
		echo "[sci-adk] Stop blocked: recorded belief is not reproducible from the record."
		echo "[sci-adk] Run(s) failed 'sci-adk verify' (DIVERGED/UNRESOLVED):${failed}"
		echo "[sci-adk] Resolve DIVERGED/UNRESOLVED claims via 'sci-adk resolve' before ending the session."
	} >&2
	exit 2
fi

exit 0
