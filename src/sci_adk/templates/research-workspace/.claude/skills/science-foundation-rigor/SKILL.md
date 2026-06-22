---
name: science-foundation-rigor
description: >
  sci-adk's foundational research discipline: record vs belief, the three core
  types (Spec / Evidence / Claim) with their invariants, the CLI verbs, the
  deterministic halts, the verify gate, and the runtime tool policy. Reference
  knowledge loaded by the sci hub and the science-workflow skills. Not a workflow.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob
user-invocable: false
metadata:
  version: "1.0.0"
  category: "foundation"
  status: "active"
  updated: "2026-06-22"
  modularized: "false"
  tags: "sci-adk, rigor, record-vs-belief, spec, evidence, claim, verify, decision-rule"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["record vs belief", "spec", "evidence", "claim", "decision rule", "verify", "novelty", "halt", "pre-registration", "anti-harking"]
  agents: ["manager-prereg", "expert-experimentalist", "expert-statistician", "expert-writer", "expert-literature"]
  phases: ["plan", "experiment", "publish", "verify"]
---

# science-foundation-rigor — The Research Discipline

The always-relevant rigor library. Everything the sci hub and the workflow skills
build on. This is reference knowledge, not a procedure — the workflows describe the
HOW; this describes the WHAT and the WHY.

## Quick Reference (30 seconds)

**The deepest principle: separate the record from belief.**

- **Evidence is a RECORD** — a monotone, append-only log of *what happened*. Null
  and negative results are part of the record. A null is a result.
- **A Claim is a BELIEF** — a non-monotone, revisable confidence *derived from*
  Evidence. A SUPPORTED claim can be demoted to CONTESTED or REFUTED as new
  Evidence arrives.
- **Build-state is not truth.** "It ran" / "the agent concluded" is not a verdict.
  The verdict is what the engine derives from the record.

**Referee, not player.** Agents *propose*; the engine *judges*, by the frozen Spec's
per-hypothesis `DecisionRule` and its halts. No self-certification.

**The hard rule.** No conclusion reaches the report without passing `sci-adk verify`
— a headless, read-only audit that exits 0 iff every recorded claim reproduces from
the record.

## Implementation Guide (5 minutes)

### The three core types

**1. Spec — the compiler input (a frozen contract).**

A pre-registration contract: the four panes (RawProposal, Hypotheses[], MethodPlan,
TargetClaims[]) plus a per-hypothesis `DecisionRule`. Frozen once accepted; the only
legitimate change is an amendment that creates a new version. The Spec is the
anti-HARKing anchor — it fixes WHAT will be tested and HOW support will be decided
BEFORE the data is seen.

Invariants S1–S5 (at a usable altitude):
- The Spec is immutable once frozen; amendments produce a new version, never an edit.
- An amendment requires a human checkpoint even in autonomous mode (S5).
- Every hypothesis carries its own DecisionRule (no global metric is assumed).

**2. Evidence — the accumulated record (append-only).**

A typed, immutable, provenance-stamped entry: `evidence_id`, `spec_id`, `result`,
`provenance`, and `bears_on[]` (which hypotheses it speaks to, and the direction:
supports / contradicts / inconclusive).

Invariants E1–E4:
- Evidence is append-only and immutable; a prior entry is never mutated (E1).
- Every entry carries provenance (it is reproducible).
- Null and negative results are first-class — they are recorded, not suppressed.
- `bears_on[]` is fixed at pre-registration time, transcribed at append time — never
  invented post-hoc (anti-HARKing).

**3. Claim — the compiler output (revisable belief).**

A belief derived from Evidence via the DecisionRule: `ClaimStatus`
(SUPPORTED / CONTESTED / REFUTED / pending), `Confidence`, `EvidenceLink[]`,
`StatusChange[]`.

Invariants C1–C6:
- A Claim derives ONLY from Evidence via the DecisionRule (no self-certification).
- Status movement is non-monotone — SUPPORTED can become CONTESTED / REFUTED.
- "CONTESTED" is explicit when Evidence conflicts (it is a result, not a failure).
- Confidence is judged against the Spec's own DecisionRule, not a global constant
  (there are NO hardcoded metrics like "85% coverage").

### The CLI verbs (the only way to write the record)

A worker NEVER writes the record directly. Every append goes through a `sci-adk`
verb, which enforces typing, provenance, and append-only-ness.

| Verb | Stage | What it does |
|---|---|---|
| `sci-adk init-spec` | plan | Freezes the Spec (S1–S5); emits spec_id + spec_digest + receipt |
| `sci-adk amend-spec` | plan | New Spec version with a human-checkpointed amendment receipt (S5) |
| `sci-adk execute` | experiment | Runs the frozen MethodPlan, capturing provenance |
| `sci-adk append-evidence` | experiment | Appends ONE typed, immutable Evidence entry with `bears_on[]` |
| `sci-adk derive-claim` | experiment | Applies the DecisionRule; records Claim status + confidence + basis |
| `sci-adk render` | publish | Renders `paper/{draft.tex, si.tex, figures/, references.bib}` from the record |
| `sci-adk verify` | verify | Read-only audit; exits 0 iff every recorded claim reproduces (the verdict) |
| `sci-adk resolve` | experiment | Resolves the checkpoints the engine surfaced (verdict loop) |
| `sci-adk status` | any | Read-only snapshot: open checkpoints, unresolved/contested claims (no LLM) |
| `sci-adk prior-work` | plan | Records the prior-art search + what was found (or none) |
| `sci-adk novelty --kind {result\|method}` | plan | Records the per-kind novelty decision (`found_nothing` or prior-art) |
| `sci-adk contested` | plan | Records a contested-literature finding |

`sci-adk run [SPEC-id]` remains a monolithic wrapper chaining the stage verbs
(`init-spec → execute → append-evidence → derive-claim → render`). Workers MAY call
individual verbs for fan-out, OR `sci-adk run` for the whole cycle.

### The deterministic halts

The engine surfaces decision points and HALTS — resolve them, never route around them:

- **config halt** — a malformed or under-specified Spec / configuration.
- **validity halt** — an empirical Claim would reach SUPPORTED on synthetic /
  generated Evidence alone (referent-typing; see `science-foundation-rigor` validity).
- **novelty halt** — a `\novelty{kind}{hyp}` is asserted without a matching
  `found_nothing` search on record.
- **evidence-validity halt** — a digitized Evidence entry tries to auto-promote to
  measured without an extractor (and extractor ≠ verifier).
- **prior-work halt** — a freeze proceeds without the required prior-art search.

A halt is the engine doing its referee job. It is resolved by recording the missing
thing (a search, an empirical Evidence entry, an amendment) — never by bypassing it.

### Two-kind novelty

Novelty is a revisable LITERATURE-referent Claim — "no prior published work
establishes a specified aspect of a hypothesis, as of a search date" — in TWO
ORTHOGONAL kinds:

- **result-novelty** — novelty of the hypothesis's statement / conclusion.
- **method-novelty** — novelty of the hypothesis's approach.

A kind is novel ONLY if its OWN `found_nothing` search is on record. A `found_nothing`
search for one kind NEVER satisfies the other. The decision is recorded at the
trigger moment (pre-registration / amendment), never retrofitted (anti-HARKing).

### The verify gate

`sci-adk verify` is the sole verdict authority. It re-applies the frozen rules to
the recorded Evidence + verdict trails and exits 0 iff every recorded claim
reproduces from the record. It also runs the paper-consistency gate (`\ref`↔`\label`,
figure sources, novelty markup) over the rendered `.tex`. The Stop hook fires it at
session end; its exit code closes the session or sends it back to resolve.

Guard agents (`evaluator-*`) are advisory information amplifiers — they catch
problems earlier and explain them better, but they are NEVER the verdict authority.

### Tool policy (runtime)

These exclusions apply to sci-adk's RESEARCH runtime, not to any software project a
user happens to also work on:

- **Allowed**: Claude Code (in-session agent) + Git + MCP; arXiv / Semantic Scholar
  (academic search); docker (Python and per-domain images); LaTeX / BibTeX.
- **Excluded**: LSP servers, coverage thresholds, Conventional Commits / PR-merge
  gates. Rationale: "syntax-correct = done" and "code-coverage = verified" are
  software-engineering assumptions that the record/belief discipline rejects —
  scientific "done" is `sci-adk verify`-pass, not a green build or a merged PR.

The kernel carries ZERO domain code. Domain knowledge enters via the Spec's
MethodPlan and future `science-domain-*` skills, never via the kernel.

## Advanced (10+ minutes)

The full type specification lives in `design/abstractions.md` (schema + invariants
S1–S5 / E1–E4 / C1–C6). The verify subroutines live in `src/sci_adk/loop/verify.py`
(the `_audit_*` functions are the canonical source the guard agents reference). The
constitution (`.claude/rules/sci-adk-constitution.md` in the dev repo; the workspace
`CLAUDE.md` here) records the discipline's origin and the two-environment scoping.

## Works Well With

- `science-workflow-prereg` — Stage 2 (freeze) procedure built on these types.
- `science-workflow-experiment` — Stage 3 (record + derive) procedure.
- `science-workflow-publish` — Stage 4 (render) procedure.
- The `sci` orchestration hub — routes /sci subcommands to the workers.
- The `science-orchestrator` output style — the always-on persona.
