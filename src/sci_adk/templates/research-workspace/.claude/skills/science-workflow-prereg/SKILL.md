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

- **Search → freeze → record**: manager-prereg DRAFTS the Spec as JSON at
  `drafts/<spec-id>/spec.json` → expert-literature searches prior art per
  (hypothesis × kind) and writes search logs → manager-prereg sets the novelty flags
  from the logs and FREEZES via `sci-adk init-spec --spec-json
  drafts/<spec-id>/spec.json` → the orchestrator RECORDS the decisions, before any
  experiment.
- **Why this order**: the novelty search needs the exact, final hypothesis text, so it
  follows the draft; it must precede the freeze so it cannot be fitted to the plan;
  and the recording verbs need the run directory the freeze creates. The log's
  `searched_at` is what shows the search came first.
- **The freeze is the anti-HARKing anchor**: once frozen, the Spec does not change to
  fit the data. A design change after the freeze is an AMENDMENT (a recorded,
  human-checkpointed act), never an in-passing edit.

## Implementation Guide (5 minutes)

### The four panes

A Spec is authored as four panes plus a per-hypothesis DecisionRule:

1. **RawProposal** — the research goal in the user's own framing.
2. **Hypotheses[]** — each hypothesis stated precisely, with its `novelty_result` /
   `novelty_method` flags (both default False; a kind is novel only if its own
   pre-freeze search found nothing, recorded as `found_nothing` right after the
   freeze).
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
DecisionRule as a JSON document in the `Spec` schema, written to
`drafts/<spec-id>/spec.json` (`id`, `raw_proposal`, `hypotheses[]` each with its
`decision_rule`, `method`, `target_claims[]`). JSON is the freeze format because it
carries any DecisionRule kind with its `params` exactly — a numeric `threshold` or
`interval` rule included. Do NOT author `created_at` (the freeze sets it), and leave
`version` at 1 with no `prior_version_id` / `amendment_rationale` (those belong to
amendments). Unknown fields are rejected at freeze, not dropped — at any depth, named
by their JSON path (e.g. `hypotheses[1].decision_rule.parms`); only the free-form
`decision_rule.params` mapping takes any key. Do NOT
freeze. Return the draft (exact hypothesis text per kind) so the orchestrator can
dispatch the literature search against it.

**Literature pass (expert-literature).** Search prior art per (hypothesis × kind)
against the draft hypothesis text, BEFORE the freeze, and write a search log per unit
(`drafts/<spec-id>/search-notes/`, with its `searched_at`). Nothing is recorded yet:
the recording verbs need `runs/<id>/spec.json`, which only the freeze creates. Return
a `Sources:` list of surfaced URLs.

**Record (right after the freeze, before any experiment).** From the logs, one at a
time:
- `sci-adk novelty --kind result` and `sci-adk novelty --kind method` — the per-kind
  decision (`found_nothing` or prior-art), each with `--search-log`. The `--kind` flag
  is REQUIRED; there is no kind-agnostic novelty decision.
- `sci-adk prior-work` — the Spec-level search + what was found.
- `sci-adk contested` — if the literature conflicts on the point.
The search is never retrofitted: `verify` fails a `found_nothing` whose log was
searched after the freeze.

**Acquisition halt (some DOI had no OA PDF).** When `prior-work --searched` or
`novelty --searched` prints `halt (human input needed):` on stderr (a searched DOI
had no downloadable Open-Access PDF), the exit code is still `0` and the decision is
already recorded — but do NOT silently proceed. The orchestrator surfaces the missed
paper list to the user via `AskUserQuestion`, offering: (a) provide the PDF now → the
manual-ingest path (`sci-adk add-literature <run_dir> --pdf <path> --doi <missed
DOI>`, which keeps the key that DOI already has in `references.bib`; see the
workspace CLAUDE.md "User-provided literature" rule for the verb + bibkey
ownership), or (b) skip this
paper → record the miss as a null and continue. This is how the kernel's
`AcquisitionHalt` reliably reaches the human instead of depending on the agent
noticing stderr.

**Pass 2 — freeze (manager-prereg, 2nd call).** Review the search logs. Set
`novelty_result` / `novelty_method` ONLY where that unit's logs carry a found-nothing
outcome — no candidate marked `same`, and at least two distinct indexes answered
(never auto-carry one kind's result to the other). The matching `found_nothing` is
recorded right after the freeze; `verify` flags any set flag still without one. Each flag gets a
one-line recorded basis. Then freeze with `sci-adk init-spec --spec-json
drafts/<spec-id>/spec.json`, which validates the draft, stamps `created_at` with the
freeze time (a value in the file is ignored, so the freeze cannot be backdated), and
emits `spec_id` + `spec_digest` + a checkpoint receipt (S1–S5 enforced). From here the
Spec is immutable except by explicit amendment: `init-spec` refuses an id that is
already frozen (`runs/<id>/spec.json` exists) and writes nothing — change a frozen
Spec with `sci-adk amend-spec`, never by re-freezing.

**Quick-start route (not `/sci plan`).** A four-pane Markdown proposal can be frozen
and run in one step with `sci-adk run proposal.md`. Its parser authors qualitative
DecisionRules only; a pre-registration with numeric rules goes through the JSON
freeze above.

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
- The flag is anti-HARKing: it is set at pre-registration, from a search run before
  the freeze, not after seeing whether the experiment "worked".
- `sci-adk verify` re-derives the novelty status from the recorded decisions. It
  FAILS a `found_nothing` whose log shows fewer than two answering indexes or a search
  after the freeze, and it reports (never fails) a set flag with no matching
  `found_nothing` recorded — the novelty claim then stays PROPOSED.

### Amendment (S5)

A frozen Spec changes ONLY via `sci-adk amend-spec`, triggered by an explicit
decision (a checkpoint the engine surfaced, or a recorded user instruction) — never
by convenience. State precisely WHAT changes and WHY, grounded in the recorded reason.

1. **Draft** the new version as a full Spec JSON: a copy of the frozen
   `runs/<spec-id>/spec.json` with the changes made, written to
   `drafts/<spec-id>/amend-v<N>/spec.json`. Set `version` to the next version (or
   remove it) and remove `amendment_rationale` (or set it to the exact rationale
   text). `created_at` and `prior_version_id` are set by the amendment; values in the
   draft are ignored. Write the rationale beside the draft.
2. **Approve.** Show the human the change and the rationale; nothing is recorded until
   they approve (S5).
3. **Record** with `sci-adk amend-spec runs/<spec-id> --rationale "<rationale>"
   --spec-json drafts/<spec-id>/amend-v<N>/spec.json`. The verb prints which fields
   changed. It refuses a draft whose `id`, `version` or `amendment_rationale` does not
   match, an unknown field, or content identical to the frozen version. Without
   `--spec-json` only the version and rationale change.

Every prior frozen version is kept byte-for-byte in `runs/<spec-id>/spec_history/`
(`spec.v<N>.json`; its sha256 is in the receipt `checkpoints/amendment-v<N+1>.json`),
so what was originally pre-registered stays on record. Evidence already recorded stays
in the record; new Evidence/Claims bind to the new digest the verb prints, and
expert-literature re-searches only the hypotheses that changed.

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
