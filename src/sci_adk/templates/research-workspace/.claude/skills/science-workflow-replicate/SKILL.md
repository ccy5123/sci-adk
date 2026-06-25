---
name: science-workflow-replicate
description: >
  sci-adk replication workflow knowledge: re-run a FROZEN Spec's MethodPlan on an
  INDEPENDENT data set or system and append concordant or discordant replication
  Evidence (independence recorded in provenance, bears_on[] per the pre-registered
  mapping), then let the engine re-derive — a concordant replication strengthens the
  Claim, a discordant one moves it to CONTESTED. Loaded by the sci hub for /sci replicate
  and by expert-replicator. Builds on science-foundation-rigor and science-workflow-experiment.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob
user-invocable: false
metadata:
  version: "1.0.0"
  category: "workflow"
  status: "active"
  updated: "2026-06-25"
  modularized: "false"
  tags: "sci-adk, replicate, replication, reproducibility, independent-data, independent-system, provenance, bears-on, non-monotone, contested, concordant, discordant, recomputation"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["replicate", "replication", "reproduce", "reproducibility", "independent data", "independent system", "rerun on new data", "concordant", "discordant", "contested replication"]
  agents: ["expert-replicator"]
  phases: ["replicate"]
---

# science-workflow-replicate — Independent Replication

The replication procedure: re-run an ALREADY-FROZEN Spec's MethodPlan against an
INDEPENDENT context and append honest replication Evidence, then let the engine revise
the Claim. For the discipline (record vs belief, invariants, verbs, halts) load
`Skill("science-foundation-rigor")`; for the run/derive mechanics this reuses, load
`Skill("science-workflow-experiment")`. This skill is the HOW of replication specifically.

## Quick Reference (30 seconds)

- **Same frozen Spec, independent context.** Replication re-runs the SAME MethodPlan;
  what changes is the data/system, never the method. The method stays frozen — changing
  it is a `manager-prereg` amendment, not a replication.
- **One worker.** `expert-replicator` runs the frozen MethodPlan against the independent
  context and appends replication Evidence; `expert-statistician` (or `sci-adk
  derive-claim`) then re-derives the Claim over the combined record.
- **Independence is a provenance fact.** A replication Evidence entry is ordinary
  `experiment_run` Evidence whose INDEPENDENCE is recorded in `provenance` (a different
  data sample, implementation, operator/machine, or seed). No dedicated replication kind.
- **Discordance is a result.** A replication that disagrees moves the Claim toward
  CONTESTED / REFUTED — record it exactly; the engine revises belief (Claims are
  non-monotone). Suppressing a discordant replication is how a record lies.

## Implementation Guide (5 minutes)

### When to replicate

Replicate when you want to test the REPRODUCIBILITY of a recorded Claim under genuine
independence — not to "confirm" it. The result is informative either way: concordance
strengthens the supporting record; discordance contests it. Replication is a strong test
precisely because it can fail.

### What counts as independent

The independence must be REAL and recorded. At least one axis must genuinely differ from
the original run:
- a different data sample / dataset (independent data),
- a different implementation of the method (independent code),
- a different operator / machine / environment, or
- a different random seed (for a stochastic method).

[HARD] Re-running identical deterministic code on the identical input is a
RECOMPUTATION, not a replication — it restates the same fact and adds NO independent
Evidence. For a `formal` + deterministic `threshold` hypothesis, a meaningful replication
MUST vary the implementation or the input set. If nothing genuinely independent varies,
there is no replication to record.

### Run it and record it (expert-replicator)

Re-run the FROZEN MethodPlan against the independent context:

- `sci-adk execute` — runs the frozen experiment (docker / python etc.) against the new
  data/system, capturing provenance.
- `sci-adk append-evidence` — appends ONE typed, immutable Evidence entry per replication
  result (concordant AND discordant), with:
  - `bears_on[]` per the Spec's pre-registered mapping — the SAME mapping the original run
    used; never re-mapped post-hoc to protect the original Claim (anti-HARKing);
  - `provenance` that NAMES the axis of independence (the distinct `data_source`,
    `environment`, `code_ref`, or seed that differs from the original run).

The verb is append-only: replication Evidence NEVER overwrites the original Evidence — it
ADDS to the same run's record. Never hand-edit `runs/<id>/` Evidence files.

### Let the engine revise the belief (expert-statistician / derive-claim)

The verdict is the engine's, not yours. After the replication Evidence is on record,
`sci-adk derive-claim` re-applies the frozen DecisionRule over the COMBINED Evidence:
- concordant replication → more supporting Evidence → the Claim's support is strengthened;
- discordant replication → the Claim moves to CONTESTED (evidence conflicts) or REFUTED.
You do not announce "it replicated" by judgment; `derive-claim` / `sci-adk verify` decide.
Make a CONTESTED outcome explicit — it is a result, the record working as intended.

### Frozen-Spec boundary

`expert-replicator` receives a `[FROZEN SPEC REFERENCE]` block (spec_id, spec_digest); the
verbs check the digest against the on-disk Spec and a mismatch raises `SpecDigestMismatch`.
Apply the MethodPlan EXACTLY as frozen against the independent context — if the method
itself must change to fit the new data/system, that is a `manager-prereg` amendment (a new
frozen Spec version), not a replication.

## Advanced (10+ minutes)

A replication does not get its own Evidence kind or its own DecisionRule — that is
deliberate. Replication is just INDEPENDENT Evidence bearing on the SAME frozen
hypotheses, and the non-monotone Claim machinery (`design/abstractions.md` invariants
C1–C6) is exactly what turns a discordant replication into a CONTESTED status without any
special case. This is the record/belief separation doing its job: the record grows
monotonically (the original run + the replication both stand), while the belief revises.
`sci-adk verify` re-derives the combined record read-only, so a recorded replication is
tamper-evident like any other Evidence.

## Works Well With

- `science-foundation-rigor` — the Evidence/Claim discipline (non-monotone Claims) this
  builds on.
- `science-workflow-experiment` — the run/append/derive mechanics replication reuses.
- `science-workflow-prereg` — produced the frozen Spec + DecisionRule + `bears_on[]` map
  the replication re-runs against.
- `expert-replicator` — the worker that runs the frozen MethodPlan on the independent
  context and appends replication Evidence.
- `expert-statistician` — re-derives the Claim over the combined original + replication record.
