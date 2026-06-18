---
description: Drive a sci-adk research session for a proposal or goal — freeze the Spec, run experiments, author verdicts, and gate every conclusion through 'sci-adk verify'.
argument-hint: "<proposal.md | research goal>"
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# /research — drive a sci-adk session

Run a disciplined sci-adk research session for: **$ARGUMENTS**

This is a self-contained research-workspace command. It does NOT route to any
external skill — the only authority is the `sci-adk` CLI on PATH.

You are under the `researcher` persona contract: agents propose, the engine
judges; **no conclusion reaches the report without passing `sci-adk verify`**.

## Procedure

1. **Confirm the four-pane proposal.** If `$ARGUMENTS` is a path to a proposal
   file, Read it. If it is a free-text goal, draft the four panes (goal,
   hypotheses, method plan, target claims) and confirm them with the user via
   AskUserQuestion before freezing anything. Do not invent hypotheses the user
   did not agree to.

2. **Freeze the Spec.** Run `sci-adk run <proposal>` to compile the proposal
   into `runs/<spec.id>/`. This freezes the Spec (the pre-registration
   contract); from here, the Spec is immutable except by explicit amendment.

3. **Surface checkpoints and halts.** Run `sci-adk status <run>` to see open
   decision points, unresolved/contested claims, and pending halts. Work
   through them; record Evidence (append-only — null and negative results
   included). Record prior-work / novelty / contested decisions at their
   trigger moments via the matching verbs (`sci-adk prior-work`,
   `sci-adk novelty`, `sci-adk contested`).

4. **Author verdicts in-session, then resolve.** Write your verdicts for the
   open checkpoints, then run `sci-adk resolve <run>` to drive the checkpoint
   loop with the recorded verdicts. Re-run `sci-adk status <run>` to confirm
   what is now resolved and what remains.

5. **Gate before reporting.** Run `sci-adk verify <run>`. It exits 0 iff every
   recorded claim reproduces from the record. **Do not state any conclusion
   until `verify` passes.** If it reports DIVERGED/UNRESOLVED, return to
   step 3/4 and resolve before concluding.

6. **Report.** Only after `verify` passes, summarize the verified claims and
   point to the run dir's paper/evidence artifacts.

## Rules

- Show `sci-adk status <run>` between steps so state stays visible.
- Never conclude outside `verify`. Build-state is not truth.
- Never silently amend the frozen Spec — amendment is an explicit, recorded act.
- Never use the Anthropic API or `claude -p`; the LLM is the in-session agent only.
