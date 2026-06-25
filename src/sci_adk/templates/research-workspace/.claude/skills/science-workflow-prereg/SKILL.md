---
name: science-workflow-prereg
description: >
  sci-adk Stage 2 (plan / freeze) workflow knowledge: the two-pass Spec freeze
  (draft → prior-art and per-kind novelty search → confirm flags and freeze), the
  four panes, per-hypothesis DecisionRule authoring (no global metric), 2-kind
  novelty, and amendment. Loaded by the sci hub for /sci plan and by manager-prereg
  and expert-literature. Builds on science-foundation-rigor.
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
  tags: "sci-adk, prereg, spec, freeze, novelty, decision-rule, anti-harking, amendment, science-guards, falsifiability"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["pre-registration", "spec freeze", "novelty search", "prior art", "decision rule", "four panes", "amendment", "init-spec", "science guards", "negative control", "discriminating cases", "epistemic kind", "falsifiability"]
  agents: ["manager-prereg", "expert-literature"]
  phases: ["plan"]
---

# science-workflow-prereg — Freeze the Spec (Stage 2)

The plan-stage procedure: turn a confirmed research intent into a FROZEN Spec — the
immutable pre-registration contract the rest of the cycle is judged against. For the
underlying discipline (record vs belief, the Spec/Evidence/Claim invariants, the
verbs and halts) load `Skill("science-foundation-rigor")`; this skill is the HOW.

## Quick Reference (30 seconds)

- **Two passes, sequential**: manager-prereg DRAFTS the Spec → expert-literature
  searches prior art per (hypothesis × kind) → manager-prereg CONFIRMS the novelty
  flags and FREEZES via `sci-adk init-spec`.
- **Why sequential**: the novelty search needs the exact, final hypothesis text. You
  cannot search before the draft exists, and you cannot freeze before the search
  records its decision.
- **The freeze is the anti-HARKing anchor**: once frozen, the Spec does not change to
  fit the data. A design change after the freeze is an AMENDMENT (a recorded,
  human-checkpointed act), never an in-passing edit.

## Implementation Guide (5 minutes)

### The four panes

A Spec is authored as four panes plus a per-hypothesis DecisionRule:

1. **RawProposal** — the research goal in the user's own framing.
2. **Hypotheses[]** — each hypothesis stated precisely, with its `novelty_result` /
   `novelty_method` flags (both default False; a kind is novel only if its own
   `found_nothing` search lands on record).
3. **MethodPlan** — how each hypothesis will be tested, INCLUDING the pre-registered
   `bears_on[]` mapping (which result will speak to which hypothesis, and the
   direction). This mapping is fixed now so the experimentalist transcribes it later
   rather than inventing a post-hoc bearing.
4. **TargetClaims[]** — the claims the cycle aims to derive.

### Per-hypothesis DecisionRule (no global metric)

Every hypothesis carries its OWN DecisionRule — the threshold that decides
SUPPORTED vs not for that hypothesis (e.g. an out-of-sample slope bound, a proof
obligation, a qualitative checkpoint). There is NO global constant like "85%
coverage"; the engine later judges the Claim against *this rule*. A hypothesis
without a DecisionRule is a blocker at draft time — do not freeze a Spec that leaves
support undecidable.

### The two-pass freeze

**Pass 1 — draft (manager-prereg).** Author the four panes + per-hypothesis
DecisionRule. Do NOT freeze. Return the draft (exact hypothesis text per kind) so the
orchestrator can dispatch the literature search against it.

**Literature pass (expert-literature).** Search prior art per (hypothesis × kind)
against the draft hypothesis text, as of a recorded search date:
- `sci-adk prior-work` — records the search + what was found (or none).
- `sci-adk novelty --kind result` and `sci-adk novelty --kind method` — records the
  per-kind decision (`found_nothing` or prior-art). The `--kind` flag is REQUIRED;
  there is no kind-agnostic novelty decision.
- `sci-adk contested` — if the literature conflicts on the point.
Record at this trigger moment (pre-registration), never retrofitted. Return a
`Sources:` list of surfaced URLs.

**Pass 2 — freeze (manager-prereg, 2nd call).** Review the literature evidence. Set
`novelty_result` / `novelty_method` ONLY where a matching `found_nothing` search is
on record (never auto-carry one kind's result to the other). Each flag gets a
one-line recorded basis. Then freeze via `sci-adk init-spec`, which emits
`spec_id` + `spec_digest` + a checkpoint receipt (S1–S5 enforced). From here the Spec
is immutable except by explicit amendment.

### Science guards at freeze (G1–G5)

At draft/freeze, declare the claim-strength guard fields per hypothesis so the Spec is
not silently weak. (For what each guard MEANS and WHY, load
`Skill("science-foundation-rigor")` §"The science guards" — here is only WHEN, which
field, via which verb.) Set these in the draft (Pass 1), or add later by amendment:

- **G1 analyticity** — declare `epistemic_kind` (`finding` / `capability_check` /
  `unit_test`). A known result framed as `finding` is refused later under
  `strict_science`: reclassify it, or assert novelty (`novelty_result` /
  `novelty_method` with a `found_nothing` search) — verifying an OPEN conjecture by
  examples is legitimate, and the novelty assertion is the open-question signal.
- **G2 test-power** — declare `discriminating_cases[]`: hard cases that SEPARATE a
  correct method from a plausibly-broken one (each with its reason).
- **G4 mode-coherence** — a frozen pass/fail `threshold` rule belongs to a
  `confirmatory` hypothesis; set `mode = confirmatory` (an exploratory hypothesis's
  rule should be a guide, not a binding gate).
- **G5 claim-cost** — if the hypothesis or its target claims use a practical-property
  term (index / efficient / scalable / fast / compact / succinct / lightweight /
  practical / optimal), declare `cost_metrics` (the size/time measurement that makes
  the cost claim checkable).
- **G3 falsifiability target** — in the MethodPlan, pre-register that the experiment
  stage MUST produce a `NEGATIVE_CONTROL` Evidence item: a deliberately broken variant
  whose `outcome == not_supported`, covering the declared `discriminating_cases`.
  prereg SETS the target; the experiment stage PRODUCES the Evidence (it never enters
  the DecisionEngine).

These triggering fields are frozen with the Spec (anti-HARKing). The **spec gate**
(`audit_spec_science`, run by `init-spec`) is ALWAYS-on and NEVER halts — it surfaces
G1/G2/G4/G5 as recording-type checkpoints (like prior-work / novelty), resolved by an
amendment, so a weak Spec is never silently accepted. The HARD verdict-gate halts
(G1/G2/G3 under `strict_science`) fire LATER, in the experiment stage — see
`science-workflow-experiment`.

### 2-kind novelty (the rule)

- `result` and `method` are ORTHOGONAL — search and record each on its own.
- A `found_nothing` search for one kind NEVER satisfies the other.
- The flag is anti-HARKing: it is set at pre-registration, from a recorded search,
  not after seeing whether the experiment "worked".
- `sci-adk verify` later re-derives the novelty status from the recorded decisions;
  a flag without a matching `found_nothing` record is a novelty halt.

### Amendment (S5)

A frozen Spec changes ONLY via `sci-adk amend-spec`, triggered by an explicit
decision (a checkpoint the engine surfaced, or a recorded user instruction) — never
by convenience. An amendment produces a new Spec version + checkpoint receipt; state
precisely WHAT changes and WHY, grounded in the recorded reason. Downstream
Evidence/Claims then bind to the new digest, and expert-literature re-searches only
the hypotheses that changed.

## Advanced (10+ minutes)

Spec schema + invariants S1–S5: `design/abstractions.md` §Spec. Novelty 2-kind
definition + the gate boundary (sci-adk records that a `found_nothing` search of the
right {hyp, kind} exists; it does NOT adjudicate same-ness or significance — that is
the searcher's recorded judgment): `science-foundation-rigor` + the literature
acquisition design. The `[FROZEN SPEC REFERENCE]` block the orchestrator stamps onto
every subsequent worker is what makes a silent post-freeze edit fail the next
verb's digest check.

## Works Well With

- `science-foundation-rigor` — the Spec/Evidence/Claim discipline this builds on.
- `science-workflow-experiment` — consumes the frozen Spec + DecisionRule + `bears_on[]` map.
- `manager-prereg` — the worker that drafts, confirms, and freezes.
- `expert-literature` — the worker that searches and records the novelty decision.
