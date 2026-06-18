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
- The **`researcher` output style** (`.claude/output-styles/researcher/`) is the
  always-on persona.
- The **`/research` command** (`.claude/commands/research.md`) is the single
  entry point — start research sessions there.

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

Run `/research <proposal.md | research goal>` to drive a session under the loop
above. See the `researcher` output style for the full persona contract.
