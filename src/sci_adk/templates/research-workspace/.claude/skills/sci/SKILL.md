---
name: sci
description: >
  sci-adk research orchestration hub. Routes /sci subcommands (plan, experiment,
  publish, verify, status, replicate) or a natural-language intent to research
  workers, loads the matching science-workflow knowledge library, and gates every
  conclusion through `sci-adk verify`. Agents propose; the engine judges.
allowed-tools: Agent, AskUserQuestion, Skill, Bash, Read, Write, Edit, Glob, Grep, TaskCreate, TaskUpdate, TaskList, TaskGet
argument-hint: "[plan|experiment|publish|verify|status|replicate] [SPEC-id] | \"intent\""
---

## Pre-execution Context

!`sci-adk status 2>/dev/null || echo "(no run selected — sci-adk status reports per-run; pass a run id to a subcommand)"`
!`git -C "${CLAUDE_PROJECT_DIR:-.}" status --porcelain 2>/dev/null | head -20 || true`

## Authority References

These govern every research cycle; do NOT duplicate their content here. Load on demand:

- Record vs belief, Spec/Evidence/Claim invariants, CLI verbs, halts, verify gate, tool policy: `Skill("science-foundation-rigor")`
- The always-on persona (six-stage cycle, worker/guard catalog, verdict rule): the `science-orchestrator` output style
- Workspace discipline (record/belief, two-env scoping, enforcement hooks): the workspace `CLAUDE.md`
- The single hard verdict: `sci-adk verify` (run by the Stop hook). Guards are advisory.

---

## Intent Router

### Raw User Input

$ARGUMENTS

### Routing Instructions

[HARD] Extract the FIRST WORD of the Raw User Input. If it matches a subcommand
below (or its alias), route to that workflow immediately. All text after the
subcommand is CONTEXT for the matched workflow — it is NOT a routing signal.

### Priority 1 — Explicit Subcommand

- **plan** (alias: prereg, spec): Author and freeze a Spec.
- **experiment** (alias: run, execute): Run one experimental cycle (record + derive).
- **publish** (alias: render, paper): Render the `paper/` folder.
- **verify** (alias: check, gate): Cross-check before close.
- **status** (alias: state): Read open checkpoints / unresolved / contested claims.
- **replicate** (alias: rerun): Re-run a frozen Spec on an INDEPENDENT data set / system.

### Priority 2 — SPEC-ID Detection

If Priority 1 did not match and the input contains a `SPEC-XXX` pattern, route to
**experiment** with that SPEC-id as the target.

### Priority 3 — Natural-language Classification

If neither matched, classify the whole input:

- Hypothesis / proposal / pre-registration language → **plan**
- Run / execute / measure / collect-evidence language → **experiment**
- Write-up / figure / render / paper language → **publish**
- Audit / cross-check / before-close language → **verify**
- "What is open / current state" language → **status**

### Priority 4 — Default (no subcommand)

Bare `/sci` (or ambiguous intent) routes to the **autonomous pipeline**:
`plan → experiment → publish`, with an `AskUserQuestion` confirmation at EACH
stage transition (the user must approve before the next stage runs). If the
intent is genuinely unclear, use `AskUserQuestion` to present the top 2-3
matching subcommands and let the user choose.

---

## The Verdict Rule [HARD]

- The Stop hook runs `sci-adk verify` and **that CLI exit code is the sole verdict.**
- Guard agents (`evaluator-rigor` / `evaluator-novelty` / `evaluator-validity`) are
  ADVISORY soft pre-checks. A guard score never decides pass/fail.
- Going straight to `sci-adk verify` (skipping guards) is fully legitimate; the
  skip appends one audit line to `runs/<id>/orchestrator.log`.
- No conclusion reaches the report without passing `sci-adk verify`. A null result
  is a result — record it; it does not need to "pass" anything.

---

## Subcommand Routing

Each subcommand: parse the argument, load the matching `science-workflow-*` Skill
for domain knowledge, then spawn the worker(s) via `Agent(subagent_type: ...)`.
Spawn implementation workers with `isolation: "worktree"` (the 5 v1 workers + the
`expert-replicator` writing worker, per the design). Run independent agents in
PARALLEL — a single message with multiple
`Agent()` calls. Pass each worker a `[FROZEN SPEC REFERENCE]` block (spec_id,
spec_digest, frozen_at, amendment_policy) once the Spec is frozen.

### plan — Author and freeze a Spec

Load `Skill("science-workflow-prereg")`. Two-pass, SEQUENTIAL (the novelty search
needs the exact draft hypothesis text):

1. `Agent(subagent_type: "manager-prereg")` → draft the Spec (goal + hypotheses +
   MethodPlan + per-hypothesis DecisionRule), NOT yet frozen.
2. `Agent(subagent_type: "expert-literature")` → prior-art / novelty search per
   (hypothesis × kind) against the draft, per the search conduct in
   `Skill("science-tool-academic-search")` (arXiv / Semantic Scholar / web, recorded
   search date, WebFetch fallback); records `sci-adk prior-work` +
   `sci-adk novelty --kind {result|method}` at this trigger moment.
3. `Agent(subagent_type: "manager-prereg")` (2nd call) → review the literature
   evidence, set `novelty_result` / `novelty_method`, freeze via `sci-adk init-spec`.

Return the frozen `spec_id` + `spec_digest` + the novelty flags with their bases.

### experiment — Record evidence and derive claims

Load `Skill("science-workflow-experiment")`. SEQUENTIAL (3b reads 3a's Evidence):

1. `Agent(subagent_type: "expert-experimentalist")` → run the frozen MethodPlan via
   `sci-adk execute` + `sci-adk append-evidence` (null/negative included; `bears_on[]`
   per the pre-registered mapping — anti-HARKing).
2. `Agent(subagent_type: "expert-statistician")` → apply the frozen DecisionRule;
   derive Claims via `sci-adk derive-claim`; author `verdicts/<hyp>.json` for any
   non-numeric checkpoint; loop `sci-adk resolve` until checkpoints clear.
3. Optionally `Agent(subagent_type: "evaluator-rigor")` (agent form, advisory).

### publish — Render the paper

Load `Skill("science-workflow-publish")`.

1. **Elicit + freeze the publishing requirements** (orchestrator-only — a worker
   cannot prompt). BEFORE spawning the writer, ask the user (via `AskUserQuestion`)
   for the venue, the required sections, figure font policy on/off, raster
   `image_min_dpi`, reference style, length limits, and any free-form advisory
   conditions — offering a "use the proposed defaults" fast-path (IMRaD sections,
   font policy on, `image_min_dpi` 300, reproduction bundle on). Freeze the answers:
   `sci-adk pubreqs freeze <run> [--defaults | --venue … --required-section … …]`
   writes the FROZEN `runs/<id>/pubreqs.json` (+ its digest) beside `spec.json`. Skip
   ONLY if the user declines declared requirements (the gate is then vacuously clean —
   backward compatible). A frozen requirement's gate-bearing fields are immutable;
   relaxing one after a figure fails needs an explicit re-freeze (anti-moving-the-goalposts).
2. `Agent(subagent_type: "expert-writer")` → author `PaperProse` / `SIProse` /
   `FigureSpec` hooks (figures pull `y` FROM Evidence by `evidence_id`) authoring TO
   the frozen `pubreqs.json` contract (declared sections present, font policy, length
   limits) → `sci-adk render` → `paper/{draft.tex, si.tex, figures/, references.bib}`
   + the F3 reproduction bundle (`paper/reproduce.py`, `paper/code/`). Pass the frozen
   `pubreqs.json` path in the spawn prompt. Optionally
   `Agent(subagent_type: "evaluator-rigor")` for the paper-consistency pre-check.
3. `sci-adk verify` now ALSO runs the `paper_requirements_clean` umbrella gate (the
   declared sections, F2 font/DPI policy, reference style, max-words, F3 reproduction
   bundle) as a HARD gate; `advisory` items + `max_pages` are surfaced, never gated.

### verify — Cross-check before close

Optionally run the guard agents in PARALLEL (single message, multiple `Agent()`):
`evaluator-rigor`, `evaluator-novelty`, `evaluator-validity` — advisory soft
pre-checks. Then run the hard verdict: `sci-adk verify`. Its exit code is the
sole verdict; exit 0 → `paper/` ready for Overleaf folder upload, non-zero
(DIVERGED / UNRESOLVED) → resolve and loop back to experiment / publish.

### status — Read run state (no LLM)

Run `sci-adk status <run>` directly — a cheap, read-only snapshot of recorded
claim statuses, open checkpoints, unresolved and contested claims, and skipped-guard
audit lines. No agent spawn.

### replicate — Re-run a frozen Spec on an independent context

Load `Skill("science-workflow-replicate")`.

`Agent(subagent_type: "expert-replicator")` → re-run the FROZEN MethodPlan against the
INDEPENDENT data set / system the user supplied (a different sample, implementation,
operator, or seed); `sci-adk execute` + `sci-adk append-evidence` append replication
Evidence whose `provenance` NAMES the axis of independence and whose `bears_on[]` follows
the Spec's pre-registered mapping (concordant AND discordant results recorded). Then
re-derive over the combined record (`Agent(subagent_type: "expert-statistician")` or
`sci-adk derive-claim`): a concordant replication strengthens the Claim, a discordant one
moves it to CONTESTED. The replication NEVER overwrites the original Evidence — it ADDS to
the record; the engine revises the belief.

[HARD] An identical deterministic re-run on the identical input is a RECOMPUTATION, not a
replication — it adds no independent Evidence. If the requested replication has no genuine
axis of independence, surface that to the user (via `AskUserQuestion`) before spawning the
worker. Replication does NOT change the method — a method change is a `/sci plan`
amendment, not a replication.

---

## Execution Directive

1. Parse the subcommand + flags from the Raw User Input.
2. Route via the Intent Router (Priority 1 → 4). If ambiguous, `AskUserQuestion`.
3. Load the matching `science-workflow-*` Skill for domain knowledge.
4. Register work items with `TaskCreate` (pending).
5. Spawn the worker(s) via `Agent()` — parallel when independent, sequential when a
   stage depends on a prior stage's record. Stamp every worker with the
   `[FROZEN SPEC REFERENCE]` block once the Spec is frozen.
6. Track progress with `TaskUpdate`.
7. At every autonomous stage transition, confirm with `AskUserQuestion` before
   proceeding.
8. Synthesize worker results; present in the user's `conversation_language`, Markdown only.
9. Never state belief outside the engine — no conclusion reaches the report without
   passing `sci-adk verify`.

---

Version: 1.0.0
