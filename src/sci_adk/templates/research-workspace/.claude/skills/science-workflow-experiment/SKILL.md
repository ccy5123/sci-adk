---
name: science-workflow-experiment
description: >
  sci-adk Stage 3 (experiment) workflow knowledge: run the frozen MethodPlan and
  append faithful Evidence (null/negative included, bears_on[] pre-registered), then
  apply the frozen DecisionRule to derive Claims — author verdicts for non-numeric
  checkpoints and loop sci-adk resolve. Loaded by the sci hub for /sci experiment and
  by expert-experimentalist and expert-statistician. Builds on science-foundation-rigor.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob
user-invocable: false
metadata:
  version: "1.0.0"
  category: "workflow"
  status: "active"
  updated: "2026-06-22"
  modularized: "false"
  tags: "sci-adk, experiment, evidence, claim, decision-rule, bears-on, anti-harking, resolve, verdict"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["execute", "append evidence", "derive claim", "decision rule", "bears on", "null result", "checkpoint", "resolve", "verdict"]
  agents: ["expert-experimentalist", "expert-statistician"]
  phases: ["experiment"]
---

# science-workflow-experiment — Record + Derive (Stage 3)

The experiment-stage procedure: execute the frozen MethodPlan, append an honest
append-only Evidence record, then derive revisable Claims from that record via the
frozen DecisionRule. For the discipline (record vs belief, invariants, verbs, halts)
load `Skill("science-foundation-rigor")`; this skill is the HOW.

## Quick Reference (30 seconds)

- **Two sub-stages, sequential** (3b reads 3a's record):
  1. `expert-experimentalist` runs the MethodPlan → appends Evidence (null/negative
     included), filling `bears_on[]` per the Spec's pre-registered mapping.
  2. `expert-statistician` reads the Evidence → applies the frozen DecisionRule →
     derives Claims; authors verdicts for non-numeric checkpoints; loops `sci-adk resolve`.
- **The record is honest or it is worthless**: append nulls and negatives exactly;
  suppressing a null is the most common way a research record lies.
- **No post-hoc bearing**: `bears_on[]` was fixed at pre-registration; transcribe it,
  never invent it (anti-HARKing).

## Implementation Guide (5 minutes)

### Sub-stage 3a — Collect Evidence (expert-experimentalist)

Run the FROZEN MethodPlan — do not redesign the method to chase a result (that would
be HARKing and breaks the pre-registration anchor). The experiment tools and code
arrive via the Spec's MethodPlan, `science-domain-*` skills, or user-supplied
artifacts; the kernel carries no domain code.

- `sci-adk execute` — runs the frozen experiment (docker / python etc.), capturing
  provenance.
- `sci-adk append-evidence` — appends ONE typed, immutable Evidence entry per result,
  including null and negative results. Each entry carries `bears_on[]` (which
  hypotheses it speaks to, and the direction: supports / contradicts / inconclusive)
  STRICTLY per the Spec MethodPlan's pre-registered mapping.

Anti-HARKing rule: a result that bears on a hypothesis the Spec did NOT pre-map for
it is a finding to report to the orchestrator (possibly an amendment), not a bearing
you add yourself. "The script ran without error" is not Evidence of a hypothesis —
the typed entry (result + provenance + bearing) is. Never hand-edit `runs/<id>/`
Evidence files; the verb is the only way to write the record.

### Sub-stage 3b — Derive Claims (expert-statistician)

Read the Evidence record (including the recorded `bears_on[]`) — Evidence is
immutable (E1); never modify it. If it looks wrong or incomplete, that is a finding
to report, not an edit, and not a reason to estimate.

- `sci-adk derive-claim` — applies the per-hypothesis frozen DecisionRule to the
  Evidence and records the Claim status (SUPPORTED / CONTESTED / REFUTED / pending) +
  confidence + derivation basis. The ENGINE renders the status; you do not decide by
  judgment that a hypothesis is supported. "The result looks convincing" is not a
  verdict.
- Make CONTESTED / REFUTED outcomes explicit — they are results, not failures. Claims
  are non-monotone: a status can move as new Evidence arrives.

### Proof / qualitative checkpoints

When the engine raises a checkpoint the DecisionRule cannot resolve numerically (a
proof obligation, a qualitative judgment the Spec delegates to a human-authored
verdict), author the verdict as `verdicts/<hyp>.json`: a verdict tied to the recorded
Evidence and the frozen rule, with an explicit basis. The verdict then flows back
through `derive-claim` / `verify` like any other recorded belief.

### The resolve loop

The engine surfaces checkpoints and halts. Run `sci-adk resolve` to clear them, then
re-derive / re-check. Loop until no open checkpoints remain. As a self-check before
returning, run `sci-adk verify` (read-only) and confirm every Claim reproduces from
the record. `sci-adk status <run>` is a cheap snapshot of what is still open.

### Frozen-Spec boundary

Both workers receive a `[FROZEN SPEC REFERENCE]` block (spec_id, spec_digest). The
verbs check the digest against the on-disk Spec; a mismatch raises
`SpecDigestMismatch` and the call fails. Apply the MethodPlan and DecisionRule
EXACTLY as frozen — if the rule or method itself must change, that is a
manager-prereg amendment, not a worker's call.

## Advanced (10+ minutes)

Evidence schema + invariants E1–E4 and Claim schema + invariants C1–C6:
`design/abstractions.md`. The validity halt (an empirical Claim cannot reach
SUPPORTED on synthetic / digitized Evidence alone — referent typing) is enforced by
`sci-adk verify` and pre-checked by the `evaluator-validity` guard. The digitized
Evidence kind (proposed → verified gate, extractor ≠ verifier, never auto-promote to
measured) is part of the same record-fidelity family.

## Works Well With

- `science-foundation-rigor` — the Evidence/Claim discipline this builds on.
- `science-workflow-prereg` — produced the frozen Spec + DecisionRule + `bears_on[]` map.
- `science-workflow-publish` — narrates the derived Claims (nothing over-stated).
- `expert-experimentalist` — the worker that runs the MethodPlan and appends Evidence.
- `expert-statistician` — the worker that derives Claims and authors verdicts.
