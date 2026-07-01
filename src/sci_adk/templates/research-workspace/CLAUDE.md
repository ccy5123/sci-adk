# Research Workspace Protocol

This project is a **sci-adk research workspace**. Every session here runs under
research discipline. These are project rules — always loaded, every turn.

## The discipline

**Record vs belief.**
- **Evidence is a record** — an append-only log of *what happened*, null and
  negative results included. A null result is a result; record it.
- **A Claim is belief** — a revisable confidence *derived from* Evidence. It
  can be demoted or retracted as new Evidence arrives.
- **Build-state is not truth.** "It ran" / "the agent concluded" is not a
  verdict. The verdict is what the engine derives from the record.

**Referee, not player.** Agents *propose*; sci-adk's engine *judges*, by the
frozen Spec's per-hypothesis `DecisionRule` and its halts. No self-certification.

**The hard rule.** No conclusion reaches your notes or the report without
passing `sci-adk verify` (a headless, read-only audit that exits 0 iff every
recorded claim reproduces from the record). Null results are results — record
them; they do not need to "pass" anything to be reported as nulls.

**The loop.** four-pane proposal -> `sci-adk run` (freezes the Spec) ->
experiments -> append-only Evidence -> sci-adk surfaces checkpoints/halts ->
author verdicts in-session -> `sci-adk resolve` -> `sci-adk verify` (the gate).
Record prior-work / novelty / contested decisions at their trigger moments.

**User-provided literature (two directions).** Both a system-detected miss and a
user-offered PDF converge on the same manual-ingest verb:

- *Reactive* — the user hands you a PDF (no Open-Access copy, or they simply have
  it). Immediately read it for the first-author surname (or institutional name) +
  year + whether it is supplementary information (SI), then run `sci-adk
  add-literature <run_dir> --pdf <path> --author "<Surname>" --year <YYYY> [--si]`.
  The verb OWNS the canonical bibkey (`<Surname><Year>`; arrival-order UPPERCASE
  `A/B` for DOI-less collisions; `_SI` for supplementary) and saves the PDF to
  `runs/<spec.id>/literature/pdfs/` — never hand-craft the filename.
- *Proactive* — a prior-work / novelty search hits a paper it cannot fetch. When
  `sci-adk prior-work --searched ...` or `sci-adk novelty --searched ...` prints
  `halt (human input needed):` on STDERR (a searched DOI had no downloadable OA PDF;
  the exit code is still `0` and the decision is recorded), do NOT silently proceed.
  Surface the missed-paper list via `AskUserQuestion`, offering: (a) provide the PDF
  now → the reactive `add-literature` path above, or (b) skip this paper → record the
  miss as a null and continue. This carries the kernel's `AcquisitionHalt` to the
  human instead of relying on the agent noticing stderr.

**Cannot-do.**
- Never state belief outside the engine (no conclusion that has not passed `verify`).
- Never silently flip the frozen Spec — amendment is explicit and recorded.
- Never use the Anthropic API or `claude -p`; the LLM is the in-session agent only.

## How this is enforced

Enforcement lives in the harness, not in memory (a prompt decays; a hook does not):

- A **Stop hook** (`.claude/hooks/sci-adk/stop-verify-gate.sh`) blocks ending
  the session while any run with recorded belief fails `sci-adk verify`.
- A **UserPromptSubmit hook** (`.claude/hooks/sci-adk/reanchor.sh`) re-injects
  this protocol + the current run's `sci-adk status` every turn.
- The **`science-orchestrator` output style**
  (`.claude/output-styles/science-orchestrator/`) is the always-on persona.
- A **`/sci` command** is the planned single entry point (forthcoming). Until it
  ships, drive sessions directly under the persona contract.

Both hooks degrade to no-op if `sci-adk` is not on PATH (a missing tool never
bricks a session).

## Two environments [HARD]

This workspace runs sci-adk *research*. sci-adk's own **build harness** — the
repository where sci-adk itself is developed (with MoAI-ADK, LSP, coverage
gates) — is a **separate repo**. Do not confuse them:

- Here, the discipline is record/belief + the `verify` gate. There, the
  discipline is software-engineering (tests, LSP, TDD).
- Do not import build-harness assumptions ("syntax-correct = done") into this
  research workspace, and do not run the research gate against the build repo
  (the two Stop gates would fight).

## Start here

Drive a session under the loop above for a proposal or research goal. See the
`science-orchestrator` output style for the full persona contract. (The `/sci`
entry-point command is forthcoming; until it ships, start sessions directly.)
