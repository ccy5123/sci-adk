# sci-adk — Operational Layer ("MoAI-ADK for Science")

> Status: **AGREED (2026-06-22)** — locked after section-by-section review with user.
> All 11 sections + Appendix A (5 decision-forks all CLOSED) + Appendix B reviewed.
> Step 2 (11-step build sequence in §10.5) may now begin.
>
> Original status line (pre-lock): PROPOSAL (2026-06-22) — first design pass after 3-round clarification with user.
> Defines an **operational layer** atop sci-adk's existing rigor layer, mirroring the
> MoAI-ADK orchestrator+specialist+evaluator+hook pattern. **Decision committed**:
> D-HYBRID (worker + guard) + MoAI pattern adopted verbatim + four sci-adk-specific
> constraints injected. This document does NOT yet implement any agents/skills/commands;
> it fixes the architecture for the build that follows.
>
> **Scope**: resolves the "Claude usage pattern" gap observed by the user — current
> sci-adk uses Claude as a sophisticated CLI user, whereas MoAI-ADK uses Claude as an
> orchestrator of a specialist team. This doc commits sci-adk to the latter, while
> preserving every existing rigor invariant.
>
> **Cross-references (checked against current files)**:
> - Rigor identity (record≠belief, frozen Spec, verify gate): `design/abstractions.md`,
>   `.claude/rules/sci-adk-constitution.md`.
> - Rigor kernel architecture (three interfaces, capability seam):
>   `design/rigor-shell-architecture.md` §2–§8.
> - External-system adoption policy (3-way split, verdict-path test):
>   `design/adoption-roadmap.md` §1–§2.
> - Existing hooks/output-style/init-session kit (research-session enforcement):
>   `design/research-session-enforcement.md` v0.2.
> - Per-domain skill template that this doc generalizes: `design/literature-acquisition.md`,
>   `design/figure-digitization.md`, `design/evidence-validity.md`, `design/paper-figures-and-si.md`.
> - MoAI Constitution this doc deliberately mirrors:
>   `.claude/rules/moai/core/moai-constitution.md`.
>
> **Conflict check (per the discipline "flag before starting")**: none found. Every
> mechanism below either (a) sits *above* the rigor kernel (operational layer) or
> (b) injects extra rigor (Spec-frozen reference, typed Evidence). Nothing weakens an
> existing invariant; `sci-adk verify` remains the sole verdict path.

---

## 1. Motivation

### 1.1 The observed gap

After three rounds of clarification, the user named the gap precisely: sci-adk
currently uses Claude as a *sophisticated tool user* (Claude calls `sci-adk` CLI
verbs in a single research session). MoAI-ADK uses Claude as an *orchestrator that
delegates to a specialist team*. The two operational shapes differ even though both
are "Claude Code projects":

| | MoAI-ADK | sci-adk (current) |
|---|---|---|
| Catalog | 32 specialist agents, 50+ Skills | none — single workspace `CLAUDE.md` + 2 hooks |
| Worker model | `Agent(subagent_type: ...)` delegation | direct in-session work |
| Command surface | `/moai plan\|run\|sync\|design\|...` | `/research` single entry |
| Output-style | orchestrator persona (delegates) | researcher persona (works) |
| Parallelism | single message with multiple `Agent()` calls | sequential by construction |
| Skills | progressive disclosure, on-demand | static |

> **Note (pattern vs volume)**: the comparison above is *pattern-level* (worker model,
> parallelism, etc.). sci-adk v1 adopts the MoAI *pattern* for all 6 axes but with a
> much smaller catalog — 5 workers + 3 guards + ~5 Skills + 6 commands (see §4, §5,
> §7). Catalog volume grows only when real bottlenecks demand it; the *shape* is
> fixed now.

The user's request: build the missing operational layer so sci-adk becomes "MoAI-ADK
for science," **without weakening the rigor layer**.

### 1.2 Two-layer orthogonality

The two layers are orthogonal:

```
[ Operational Layer (MoAI-ADK shape) ]
    orchestrator → workers (parallel) → guards → hard gate
    skills loaded on demand, commands as thin routers
              │
              │ writes to / reads from
              ▼
[ Rigor Layer (sci-adk constitution, already built) ]
    Spec (frozen) / Evidence (append-only) / Claim (revisable)
    DecisionEngine + DecisionRule + verify CLI + Stop hook
```

Adding the operational layer does not move the verdict path. The verdict path
remains `sci-adk verify`'s deterministic subroutine (`design/rigor-shell-architecture.md`
§6.2), invoked by the Stop hook (`design/research-session-enforcement.md` v0.2). The
operational layer only changes **who proposes and how work fans out**.

### 1.3 Why MoAI-ADK is the right shape

Two empirical reasons:

1. **Same problem already solved**. MoAI-ADK has converged on `expert-*` workers
   that reason via LLM and call CLI tools for deterministic execution, plus
   `evaluator-*` agents that cross-check with a Stop hook as the hard gate. This
   is structurally identical to what sci-adk needs: workers that reason about
   experiments and call `sci-adk` CLI for deterministic record-keeping, plus
   evaluators that cross-check with `sci-adk verify` as the hard gate.

2. **Same separation discipline**. MoAI's "agent = LLM, hook = deterministic"
   isomorphically matches sci-adk's "Claim = belief, Evidence = record". The
   shape is not a coincidence — both systems converged on the same principle
   from different domains.

The remaining work is *naming and wiring*, not invention.

---

## 2. Decision record (the three rounds)

### Round 1 — Starting axis: **strategic alignment first**

Chosen over (a) output-style swap, (b) agent catalog first, (c) skills first.
Rationale: this is a structural pivot; freezing the target architecture as a
design doc prevents downstream rework.

### Round 2 — Specialist concept: **D-HYBRID (worker + guard)**

Chosen over A (WORKER only — MoAI verbatim), B (STANCE — cognitive postures),
C (GUARD only — pure invariant enforcement). Rationale:

- MoAI's `expert-*` + `evaluator-active` pattern is itself already a worker+guard
  hybrid. Importing the shape directly minimizes invention.
- Pure WORKER misses sci-adk's existing gate discipline (verify boundary).
- Pure STANCE conflicts with "ADK" framing (cognitive-posture agents don't compose
  the way SW specialists do).
- Pure GUARD loses the "team that produces" feel sci-adk now lacks.

### Round 3 — Integration mode: **MoAI pattern verbatim + 4 sci-adk constraints**

Chosen over (a) skeleton-only with new naming, (b) philosophy only with hand-rolled
implementation, (c) deferred decision. Rationale:

- The user's `D-HYBRID` answer already implies high overlap with MoAI shape.
- Adopting MoAI's `.claude/agents/`, `.claude/skills/`, `.claude/commands/` layouts
  verbatim means future MoAI improvements (e.g., new evaluator tooling) flow into
  sci-adk for free.
- The four sci-adk-specific constraints (§6) are *additive*, not modifications to
  MoAI shape: they tighten worker behavior without changing the agent contract.

### Rejected alternatives (recorded for future readers)

| Rejected | Why |
|----------|-----|
| Build agents/commands first, design doc later | Round 1 rejected this; the pivot is structural |
| WORKER-only framing | Round 2: misses guard discipline |
| STANCE-only framing | Round 2: doesn't compose, breaks ADK metaphor |
| GUARD-only framing | Round 2: loses producer team feel |
| Hand-rolled new file layouts | Round 3: forks from MoAI improvements |
| LLM-as-verdict (chief-judge over N tournament) | `design/adoption-roadmap.md` §5/C CUT — would move verdict path |
| Putting evaluator agents in the verdict path | Conflicts with sci-adk constitution; evaluator agents are *advisory only* |

---

## 3. Core isomorphism (what maps to what)

This section is the load-bearing part of the doc: it pins exactly how MoAI elements
map to sci-adk elements. Everything that follows (§4–§8) is a consequence.

### 3.1 MoAI `expert-*` / `manager-*` ↔ sci-adk worker

| MoAI element | sci-adk counterpart | Note |
|---|---|---|
| `.claude/agents/expert-backend.md` | `.claude/agents/expert-experimentalist.md` | same file format, same frontmatter schema |
| Bash tool calls `go test ./...` | Bash tool calls `sci-adk run` / `sci-adk resolve` | CLI = deterministic execution layer |
| Skill loading `Skill("moai-domain-backend")` | Skill loading `Skill("science-workflow-experiment")` | progressive disclosure |
| Returns structured result to orchestrator | Returns structured result to orchestrator | identical contract |

**Critical invariant**: a worker NEVER writes directly to the record. All Evidence
append goes through `sci-adk` CLI subroutines, which enforce typing, provenance,
and append-only-ness. The agent is the *intent author*; the CLI is the *record
keeper*. This preserves `abstractions.md` E1–E4.

### 3.2 MoAI `evaluator-active` + Stop hook ↔ sci-adk evaluator + `sci-adk verify`

| MoAI element | sci-adk counterpart | Note |
|---|---|---|
| `evaluator-active` subagent (4-dim soft score) | `evaluator-rigor` subagent (rigor invariants pre-check) | both advisory; both produce structured feedback |
| `moai hook subagent-stop` (Bash hook, no LLM) | `sci-adk verify` invoked by Stop hook (existing) | both deterministic, both have final authority |
| Hook exit-2 → stderr re-fed to model | Hook exit-2 → stderr re-fed to model | identical mechanism (already implemented) |

**Critical invariant**: an evaluator agent's score does NOT decide pass/fail. The
hook-driven `sci-adk verify` is the sole verdict authority (`adoption-roadmap.md` §1,
"verdict path"). Evaluators are *information amplifiers* — they catch problems
earlier and explain them better, but they cannot grant a pass that the CLI gate
would refuse. This preserves the rigor layer's deterministic-only verdict path.

### 3.3 MoAI Skills ↔ sci-adk science Skills

| MoAI Skill family | sci-adk counterpart |
|---|---|
| `moai-foundation-*` (core principles) | `science-foundation-rigor` (record≠belief, frozen Spec, verify gate) |
| `moai-workflow-*` (TDD/DDD cycles) | `science-workflow-prereg`, `science-workflow-experiment`, `science-workflow-replicate`, `science-workflow-publish` |
| `moai-domain-*` (backend/frontend/...) | `science-domain-*` (chemistry/biology/physics/...) — loaded per project, sci-adk kernel stays domain-general |
| `moai-tool-*` (specific tools) | `science-tool-*` (docker images, BibTeX helpers, ...) |
| `moai-framework-*` (Electron, etc.) | `science-framework-*` (notebook conventions, lab-protocol templates) |
| `moai` (orchestration hub) | `sci` (orchestration hub — routes `/sci` subcommands to workers; see §7.4) |

**Critical invariant**: domain Skills (`science-domain-*`) are loaded per project and
never enter the kernel. The kernel knows three interfaces (`rigor-shell-architecture.md`
§2); Skills inform agents *about* the domain but never change kernel behavior. This
preserves `tool-policy.md` and `feedback_domain-generality` (the kernel carries zero
domain code).

### 3.4 MoAI `/moai` commands ↔ sci-adk `/sci` commands

| MoAI command | sci-adk counterpart | Routes to |
|---|---|---|
| `/moai plan` | `/sci plan` | `manager-prereg` |
| `/moai run` | `/sci experiment` | `expert-experimentalist` (and downstream) |
| `/moai sync` | `/sci publish` | `expert-writer` + `evaluator-rigor` |
| `/moai review` | `/sci verify` | `evaluator-*` agents + `sci-adk verify` |
| `/moai project` | `/sci status` | thin wrapper over `sci-adk status <run>` |
| (no equivalent) | `/sci replicate` | `expert-replicator` (sci-adk specific) |

All commands are thin routers per MoAI's [Thin Command Pattern]
(`.claude/rules/moai/development/coding-standards.md`): YAML frontmatter +
`Use Skill("sci")` body, no workflow logic in command files.

### 3.5 Principle — alignment, not lock-in

The mappings in §3.1–§3.4 align *existing* MoAI elements with *existing or planned*
sci-adk elements. They do NOT lock sci-adk to MoAI's catalog evolution:

- sci-adk MAY add families/agents/commands that have no MoAI counterpart (e.g., a
  future `science-protocol-*` Skill family for lab protocols, a sci-adk-only
  `manager-replication` worker, a `/sci experiment-rerun` command).
- MoAI MAY add families that have no sci-adk import (e.g., `moai-domain-frontend`,
  `moai-platform-chrome-extension`) — these stay outside sci-adk's purview.
- When MoAI revises an element that sci-adk has imported (e.g., `evaluator-active`'s
  scoring schema), sci-adk re-evaluates whether to track the change or fork — the
  default is track, deviation requires explicit `design/*.md` justification.

The mapping table is a contract for *imported* shapes, not a constraint on *new*
shapes. This lets sci-adk grow domain-specific operational assets without
re-litigating MoAI parity for each addition.

---

## 4. Worker catalog (v1 minimal set)

Five workers cover the four-pane research proposal lifecycle. Each definition is
the *contract*, not the implementation; implementation belongs to Step 2.

### 4.1 `manager-prereg` — Spec freezer

| Field | Value |
|---|---|
| Responsibility | Author and freeze `Spec` from user input (4-pane proposal); handle amendments |
| Tools | Read, Write, Edit, Grep, Glob, Bash, TodoWrite, Skill |
| Skills loaded | `science-workflow-prereg`, `science-foundation-rigor` |
| Calls sci-adk verbs | `sci-adk run --init-spec`, `sci-adk amend-spec` |
| Input | User intent (natural language) + brand/domain context |
| Output | Frozen Spec (`runs/<id>/spec.json`) + checkpoint receipt |
| Invariant enforced | S1–S5 (`abstractions.md` §Spec) — amendments require checkpoint |
| When invoked | `/sci plan`, or orchestrator at cycle start |
| Note | At `/sci plan` time, runs in 2 passes: (1) draft Spec → dispatch `expert-literature` for novelty search → (2) finalize Spec with literature evidence → freeze via `sci-adk init-spec`. Sequential, not parallel — literature search requires exact hypothesis text |

### 4.2 `expert-experimentalist` — Evidence collector

| Field | Value |
|---|---|
| Responsibility | Execute experiments per Spec MethodPlan, append Evidence faithfully (null/negative included) |
| Tools | Read, Write, Edit, Grep, Glob, Bash, TodoWrite, Skill |
| Skills loaded | `science-workflow-experiment`, `science-domain-*` (per project) |
| Calls sci-adk verbs | `sci-adk run --execute`, `sci-adk evidence-append` |
| Input | Frozen Spec + execution context |
| Output | Evidence entries (append-only, typed, provenance-stamped); `bearing[]` filled at append time per Spec.MethodPlan's pre-registered mapping (no post-hoc interpretation — anti-HARKing) |
| Invariant enforced | E1–E4 — null results are first-class, no mutation |
| When invoked | `/sci experiment` |
| Note | Domain-general: actual experiment code/tools come from `science-domain-*` Skills or user-supplied artifacts, never hardcoded in the agent |

### 4.3 `expert-statistician` — Claim deriver

| Field | Value |
|---|---|
| Responsibility | Apply Spec's DecisionRule to accumulated Evidence; derive Claim status + confidence |
| Tools | Read, Grep, Glob, Bash, Skill |
| Skills loaded | `science-workflow-experiment`, `science-foundation-rigor` |
| Calls sci-adk verbs | `sci-adk run --derive-claim`, `sci-adk verify` (read-only check) |
| Input | Spec + Evidence record (reads existing `bearing[]`; does NOT modify Evidence, preserves E1 immutability) |
| Output | Claim entries (SUPPORTED / CONTESTED / REFUTED / pending) with derivation basis |
| Invariant enforced | C1–C6 — Claim derives only from Evidence via DecisionRule; non-monotone |
| When invoked | `/sci experiment` (after experimentalist) |

### 4.4 `expert-writer` — Paper renderer

| Field | Value |
|---|---|
| Responsibility | Author `PaperProse` / `SIProse` hooks; emit figure specs; orchestrate paper compilation |
| Tools | Read, Write, Edit, Grep, Glob, Bash, Skill |
| Skills loaded | `science-workflow-publish`, `paper-figures-and-si` |
| Calls sci-adk verbs | `sci-adk run --render`, `sci-adk verify` (consistency gate) |
| Input | Spec + Evidence + Claim |
| Output | `paper/draft.tex` + `paper/si.tex` + `paper/figures/` + `paper/references.bib` |
| Invariant enforced | Paper-consistency gate (`\ref`↔`\label`), record fidelity (figures pull `y` from Evidence by `evidence_id`) |
| When invoked | `/sci publish` |

### 4.5 `expert-literature` — Prior-work and novelty searcher

| Field | Value |
|---|---|
| Responsibility | Conduct prior-work search; record `found_nothing` or relevant prior art per hypothesis × kind |
| Tools | Read, Write, Grep, Glob, Bash, WebFetch, WebSearch, Skill |
| Skills loaded | `science-workflow-prereg`, `science-tool-academic-search` |
| Calls sci-adk verbs | `sci-adk prior-work`, `sci-adk novelty --kind {result\|method}` |
| Input | Hypothesis text + kind (result/method) + search date |
| Output | Literature record + novelty decision (`found_nothing` or prior-art evidence) |
| Invariant enforced | Anti-HARKing — search recorded at pre-reg time, not retrofitted |
| When invoked | `/sci plan` (initial), `/sci experiment` (re-check if Spec amended) |
| Note | At `/sci plan` searches against *draft* Spec (so literature can inform freeze decision). After freeze, search results are immutable record. Re-search only on Spec amendment |

### 4.6 sci-adk CLI verb decomposition

To support fan-out across workers, the existing monolithic `sci-adk run` is decomposed
into 6 stage verbs while preserving `sci-adk run` as a backward-compatible wrapper.

| Verb | Purpose | Caller (typical) |
|---|---|---|
| `sci-adk init-spec` | Author + freeze Spec from draft | `manager-prereg` |
| `sci-adk amend-spec` | Spec amendment with checkpoint receipt | `manager-prereg` |
| `sci-adk execute` | Execute Spec.MethodPlan (run experiments) | `expert-experimentalist` |
| `sci-adk append-evidence` | Append typed Evidence (with `bearing[]`) | `expert-experimentalist` |
| `sci-adk derive-claim` | Apply DecisionRule, derive Claim | `expert-statistician` |
| `sci-adk render` | Compile paper/ artifacts | `expert-writer` |

`sci-adk run [SPEC-ID]` remains as a 5-stage chained wrapper:
`init-spec → execute → append-evidence → derive-claim → render`. External users who call
`sci-adk run` directly experience zero change. Workers MAY call individual verbs (for
fan-out) OR `sci-adk run` (for monolithic execution). Verb addition cost is included in
§10.5 build sequence (~2 build steps: verb scaffolding + tests).

### Deferred workers (v2+)

These were considered but excluded from v1 to keep the catalog tight:

- `expert-theorist` — Spec ↔ Claim semantic bridge. Currently handled by user input
  + `manager-prereg`. Promote when "derive testable hypothesis from informal theory"
  becomes a bottleneck.
- `expert-replicator` — runs Spec on independent data/system. Currently handled by
  re-running `expert-experimentalist` with new context. Promote when replication
  semantics need their own checkpoint discipline.

---

## 5. Guard catalog (v1 minimal set)

Three guards cover the boundaries the user named in Round 1's "control location"
discussion. Each guard exists in two forms:

- **agent form** (`evaluator-*` subagent) — soft pre-check, advisory, called by orchestrator
- **CLI form** (subroutine inside `sci-adk verify`) — hard verdict, deterministic, called by Stop hook

The agent form catches problems early with rich explanations; the CLI form is the
sole verdict authority. This mirrors MoAI's `evaluator-active` (agent) + `moai hook
subagent-stop` (CLI) duality.

**Invocation discipline**: the CLI form is **mandatory** (Stop hook always fires
`sci-adk verify`). The agent form is **orchestrator discretion** per §6.4 — skipping
it is legitimate; the only consequence is later/coarser error reporting. The agent
form's check list is *generated from the CLI form's source code* (each guard agent's
prompt references the canonical `_audit_*` functions in `src/sci_adk/loop/verify.py`)
to preserve DRY — invariant changes update CLI once, agent prompt picks up
automatically.

### 5.1 `evaluator-rigor` — Combined S/E/C invariants

| Field | Value |
|---|---|
| Checks | S1–S5 (Spec freezing/amendment), E1–E4 (Evidence append-only/provenance/digest), C1–C6 (Claim derivation, non-monotone movement), record-integrity (digest match), paper-consistency (`\ref`↔`\label`) |
| When invoked (agent) | After every worker completes; before orchestrator declares cycle done |
| When invoked (CLI) | Stop hook, every session end |
| Pass criterion | All listed invariants hold; CLI exit 0 |
| On failure | agent: structured feedback to orchestrator; CLI: exit 2, stderr re-fed to model, session blocked from closing |
| Tools | Read, Grep, Glob, Bash (read-only), mcp__sequential-thinking__sequentialthinking |

### 5.2 `evaluator-novelty` — 2-kind novelty audit

| Field | Value |
|---|---|
| Checks | For each hypothesis × kind (result/method) with `novelty_{kind}=True`, verify a `found_nothing` `LiteratureDecision` exists; verify decision matches the right `{hyp, kind}` |
| When invoked (agent) | After `expert-literature` completes; before `expert-writer` renders |
| When invoked (CLI) | Stop hook (inside `sci-adk verify`'s `_audit_novelty_claim`) |
| Pass criterion | All novelty-claimed hypothesis×kind pairs have matching `found_nothing` record |
| On failure | agent: instructs orchestrator to invoke `expert-literature` for missing kind; CLI: DIVERGED, exit 2 |
| Tools | Read, Grep, Glob, Bash (read-only) |

### 5.3 `evaluator-validity` — Referent-typed evidence-to-claim audit

| Field | Value |
|---|---|
| Checks | No empirical Claim achieves SUPPORTED status when only synthetic/digitized Evidence backs it; referent typing enforced (`evidence-validity.md`) |
| When invoked (agent) | After `expert-statistician` derives Claim; before orchestrator declares cycle done |
| When invoked (CLI) | Stop hook (inside `sci-adk verify`'s validity check) |
| Pass criterion | All SUPPORTED empirical Claims have at least one empirical Evidence entry as basis |
| On failure | agent: instructs orchestrator to either add empirical Evidence or downgrade Claim referent type; CLI: exit 2 |
| Tools | Read, Grep, Glob, Bash (read-only) |

### Deferred guards (v2+)

- `evaluator-replication` — would require multiple independent Spec runs; defer with
  `expert-replicator`.
- `evaluator-figure-source` — would extend `evaluator-validity` to figure data
  (digitized vs measured promotion path). Currently covered by `figure-digitization.md`
  rules inside `sci-adk verify`; promote only if violations recur.
- `plan-auditor` analog — would audit Spec doc quality (EARS-like clarity). Currently
  `manager-prereg` self-checks; promote if Spec quality issues surface.

---

## 6. Sci-adk-specific constraints injected into MoAI shape

The four constraints that distinguish "science MoAI-ADK" from a literal copy of MoAI.
These are *additive* — they tighten worker behavior; nothing in MoAI's agent contract
forbids them.

### 6.1 Constraint #1 — Auto-inject frozen Spec reference into worker prompts

**Mechanism**: orchestrator's spawn-prompt template for every worker call appends:

```
[FROZEN SPEC REFERENCE]
spec_id: <id>
spec_digest: <sha256>
frozen_at: <ISO-8601>
amendment_policy: amendments require checkpoint receipt (S5)
```

Workers see the frozen Spec hash on every invocation; any attempt to "implicitly
revise" the Spec inside an agent prompt fails the spec-digest check at the next
boundary. This converts MoAI's "context is loaded once at start" into sci-adk's
"context is re-stamped every turn" pattern, lifted from
`research-session-enforcement.md`'s UserPromptSubmit hook to the agent layer.

**Boundary check mechanism**: a worker invokes a `sci-adk` CLI verb (e.g.,
`sci-adk append-evidence`) → CLI extracts `spec_id` + `spec_digest` from the input
payload → compares against `runs/<id>/spec.json` digest on disk → mismatch raises
`SpecDigestMismatch` → CLI exits non-zero, the worker call fails, the orchestrator
sees the failure and must either re-fetch the frozen Spec or invoke
`manager-prereg` to amend (which itself produces a checkpoint, S5). Workers cannot
silently advance past the boundary.

### 6.2 Constraint #2 — Typed Evidence output schema, free-form return forbidden

**Mechanism**: worker prompts include a structured-output schema for any Evidence
they emit. Free-form prose return is disallowed for Evidence-bearing workers
(`expert-experimentalist`, `expert-literature`). The schema mirrors `abstractions.md`
§Evidence:

```json
{
  "evidence_id": "string",
  "spec_id": "string",
  "result": { ... domain-specific ... },
  "provenance": { ... },
  "bearing": [ { "hypothesis_id": "string", "direction": "supports|contradicts|inconclusive" } ]
}
```

This is enforced by the `sci-adk` CLI verb the worker calls (`sci-adk append-evidence`
rejects malformed input), so the agent's selfwise discipline is not the only safety
net — the CLI is.

**Same mechanism for Claim output**: `expert-statistician`'s output schema mirrors
`abstractions.md` §Claim; CLI verb `sci-adk derive-claim` rejects malformed Claim
input (missing `evidence_link[]`, missing `decision_rule_ref`, illegal status
transition, etc.). `expert-writer`'s output is paper artifacts (not Spec/Evidence/
Claim) — instead of typed schema, it goes through the consistency-gate inside
`sci-adk verify` (paper-consistency check: `\ref`↔`\label`, figure source pulled
from Evidence by `evidence_id`, etc., per `paper-figures-and-si.md`).

### 6.3 Constraint #3 — Novelty + validity guards added to evaluator catalog

Done in §5.2 and §5.3 above. These are SW-absent rigor invariants specific to
science. Adding them is a *catalog extension*, not a structural change.

### 6.4 Constraint #4 — Stop hook trusts `sci-adk verify` only; ignores evaluator agent scores

**Mechanism**: the existing Stop hook (`research-session-enforcement.md` v0.2 D2)
runs `sci-adk verify` and exits per CLI exit code. Evaluator agent results are
*not consulted* by the Stop hook. This preserves `adoption-roadmap.md` §1's
verdict-path rule: an LLM (even an evaluator subagent) cannot be the verdict
authority. Evaluator agents are *advisory* throughout the cycle; the boundary
gate is CLI-only.

**Implication**: an orchestrator that bypasses evaluator agents and goes straight
to `sci-adk verify` is fully legitimate. Evaluator agents are an *optimization*
(catch problems earlier, explain them better), not a *requirement*.

**Audit trail**: when an orchestrator skips an evaluator agent, a single log line
is appended to `runs/<id>/orchestrator.log` recording the skip (ISO-8601 timestamp +
skipped-evaluator-name + worker that preceded the skip). The skip itself is not a
violation, but a pattern of skips can be detected by `sci-adk status <run>` and
inform v2 policy (e.g., whether to make a specific evaluator mandatory).

---

## 7. `/sci` command surface

Following MoAI's [Thin Command Pattern]
(`.claude/rules/moai/development/coding-standards.md`), every command file is a
thin router (under 20 LOC body), all workflow logic lives in skill bodies.

### 7.1 Command catalog (v1)

| Command | Argument hint | Routes to | Purpose |
|---|---|---|---|
| `/sci plan` | `"<intent>"` | `manager-prereg` (+ `expert-literature` for novelty search) | Author and freeze Spec |
| `/sci experiment` | `[SPEC-id]` | `expert-experimentalist` → `expert-statistician` → `evaluator-rigor` (agent form) | Run one experimental cycle |
| `/sci publish` | `[SPEC-id]` | `expert-writer` + `evaluator-rigor` (agent form) | Render `paper/` |
| `/sci verify` | `[SPEC-id]` | `evaluator-*` agents + `sci-adk verify` CLI | Cross-check before close |
| `/sci replicate` | `[SPEC-id] <new-context>` | `expert-experimentalist` with replication framing | Run Spec on independent data/system (v2 work, scaffold present) |
| `/sci status` | `[SPEC-id]` | `sci-adk status <run>` (no LLM) | Read open checkpoints / unresolved / contested Claims |

### 7.2 Default routing (no subcommand)

`/sci` with no subcommand routes to the autonomous workflow: `plan → experiment →
publish` pipeline, with user confirmation at each stage transition via
`AskUserQuestion`. Mirrors MoAI's `/moai` default behavior.

### 7.3 Relation to existing `/research` — removed, no alias

The existing `/research` entry point (`research-session-enforcement.md` v0.2 D2)
is **removed** in favor of `/sci`. Rationale: sci-adk has no external users yet
(the rigor kernel was built but the kit was never adopted outside the dev repo),
so back-compat for `/research` would be dead weight. The
`templates/research-workspace/` kit is updated to ship `/sci` instead of
`/research`.

This is the only backward-incompatible change in this design; all other migrations
(§10) are additive. See §10.4 for the explicit footnote.

### 7.4 The orchestration Skill

Per MoAI's pattern (`Use Skill("moai") with arguments: ...`), `/sci` commands
route through a single **orchestration Skill** named `sci`. This Skill lives at
`.claude/skills/sci/SKILL.md` and is responsible for:

- Parsing the subcommand argument (`plan` | `experiment` | `publish` | ...)
- Loading the appropriate `science-workflow-*` Skill for domain knowledge
- Spawning the relevant worker agents via `Agent(subagent_type: ...)`
- Returning structured results to the orchestrator

The `sci` Skill is the *operational hub*; `science-foundation-rigor` and
`science-workflow-*` Skills are *knowledge libraries* it loads on demand. This
mirrors MoAI's `moai` Skill ↔ `moai-foundation-*` / `moai-workflow-*` relationship.

The `sci` Skill is added to §3.3 mapping (as the operational hub, alongside the
5 knowledge-library families) and to §10.2 file structure
(`.claude/skills/sci/SKILL.md`).

### 7.5 Not in v1 (command surface)

Explicitly excluded from `/sci` v1:

- `/sci amend` — Spec amendment is via re-invoking `/sci plan` with an existing
  SPEC-id; `manager-prereg` handles amendment vs init decision.
- `/sci replay` — deterministic replay is already covered by `sci-adk run SPEC-id`
  (the wrapper); no command needed.
- `/sci export` — paper artifacts are at `runs/<id>/paper/`, direct filesystem
  access; no orchestration value in a command.

---

## 8. End-to-end scenario (one research cycle)

This walks through what changes between current sci-adk and the proposed
operational layer. The example is the IEAM-P8 BAF prediction work
(`ieam-p8-baf-prediction` memory).

### 8.1 User input

```
User: "RDKit Abraham descriptors는 BCF에서 LOCO-CV 검정에서
       in-sample은 잘 맞지만 out-of-sample은 무너진다는 가설을 검증해줘"
```

### 8.2 Orchestrator response (new behavior)

```
[science-orchestrator output-style activates]

Stage 1: Clarify (orchestrator)
  AskUserQuestion: hypothesis kind (result / method / both)?
  AskUserQuestion: DecisionRule for "무너진다" (out-of-sample slope threshold)?
  AskUserQuestion: data source frozen at Spec time or per-run pinned?

Stage 2: /sci plan — Spec authoring + novelty (2-pass per §4.1)
  2a. Agent(subagent_type: "manager-prereg")
      → drafts Spec v1 (hypothesis + MethodPlan + DecisionRule, NOT yet frozen)
      → returns: spec_id=SPEC-IEAM-P8-BAF in draft state
  
  2b. Agent(subagent_type: "expert-literature")
      → reads draft Spec → searches arXiv/S2 per (hyp × kind)
      → sci-adk prior-work + sci-adk novelty --kind result + --kind method
      → returns: found_nothing for both kinds
  
  2c. Agent(subagent_type: "manager-prereg") [2nd call]
      → reviews literature evidence → confirms novelty_result/method flags
      → sci-adk init-spec → Spec FROZEN, checkpoint accepted

Stage 3: /sci experiment — Evidence collection + Claim derivation
  3a. Agent(subagent_type: "expert-experimentalist", isolation: "worktree")
      → runs docker python LOCO-CV per Spec MethodPlan
      → sci-adk execute + sci-adk append-evidence
        (bearing[] populated per Spec MethodPlan's pre-registered mapping)
      → returns: 4 cycles of Evidence appended
  
  3b. Agent(subagent_type: "expert-statistician")
      → reads Evidence (incl. bearing[]) → applies DecisionRule
      → sci-adk derive-claim
      → returns: hyp-001 SUPPORTED (slope +0.97 ≤ 1.02), hyp-002/003 contested

Stage 4: /sci publish — Paper render
  Agent(subagent_type: "expert-writer", isolation: "worktree")
    → authors PaperProse + SIProse hooks + FigureSpec list
        (figures pull `y` from Evidence by evidence_id — record fidelity)
    → sci-adk render
    → returns: paper/{draft.tex, si.tex, figures/, references.bib}

Stage 5: Pre-close guard check (orchestrator discretion per §6.4)
  parallel (single message, multiple Agent() calls):
    Agent(subagent_type: "evaluator-rigor")    → S/E/C + integrity + paper-consistency → pass
    Agent(subagent_type: "evaluator-novelty")  → 2-kind × found_nothing matching → pass
    Agent(subagent_type: "evaluator-validity") → empirical Claim has empirical Evidence → pass
  (orchestrator MAY skip — see §6.4; Stage 6 CLI is the hard verdict regardless)

Stage 6: Session close
  Stop hook fires → sci-adk verify (CLI — hard verdict, deterministic)
    → all invariants pass → exit 0 → session closes
    → paper/ ready for Overleaf folder upload
```

### 8.3 What changed vs current sci-adk

| Stage | Current | New |
|---|---|---|
| Stage 1 Clarify | Single-track clarification | Same, with "science-orchestrator" framing |
| Stage 2 Plan | Claude directly runs `sci-adk run` | manager-prereg + expert-literature 2-pass (draft → search → freeze) |
| Stage 3 Experiment | Sequential, monolithic | expert-experimentalist → expert-statistician (3b depends on Evidence from 3a) |
| Stage 4 Render | Single Claude calls render | expert-writer in isolated worktree |
| Stage 5 Pre-close | None (only CLI verify at end) | **Agent-form guards as soft pre-checks (parallel)** |
| Stage 6 Close | Stop hook + `sci-adk verify` | Same (preserved, byte-identical) |

The verdict path (Stop hook → `sci-adk verify` → exit code) is **byte-identical**
to current behavior. The new layers are pure value-add: parallel execution,
specialized prompts/skills per agent, early problem detection. Falling back to
"orchestrator does everything itself" remains legitimate; the operational layer
is opt-in scaffolding, not a rigor lock-in.

---

## 9. Two-environment scoping correction

The user observed in Round 3 that `[HARD]` two-environment separation rule applies
only to the dev repo (where sci-adk source coexists with MoAI build harness). This
section formalizes the correction.

### 9.1 The current rule (CLAUDE.md, sci-adk-constitution.md)

> [HARD] same machine — MoAI-ADK build harness directory (`src/sci_adk/`,
> `.claude/output-styles/moai/`) and sci-adk workspace must not be conflated.
> `init-session` blocks self-install via marker guard.

### 9.2 Corrected scoping

The rule applies **only to the sci-adk *dev* repository** — i.e., the workspace
where sci-adk source code lives next to a MoAI build harness for productizing
sci-adk itself. External users running `sci-adk init-session ~/my-research-project`
have a workspace that contains only sci-adk artifacts (or, optionally, an unrelated
MoAI-ADK project of their own — no co-location with sci-adk *source*).

For external users, the relevant guard is "this workspace runs sci-adk discipline";
two-environment separation is moot because there is no second environment.

### 9.3 Documentation patch (APPLIED in build step 10)

Applied:

- `.claude/rules/sci-adk-constitution.md`: added a "Scope of this rule (dev repo
  only)" `[HARD]` note scoping the two-environment separation to this dev repo (§9.2).
- `README.md`: added the same scoping note to its "Two-Environment Separation"
  section, plus an "Operational Layer (research workspace)" section documenting the
  `init-session` kit.
- `init-session` guard message: unchanged (still blocks self-install in the dev repo;
  external workspaces never trigger it), as planned.

Cross-reference correction (per Appendix B): §9.1 listed the root `CLAUDE.md` as a
carrier of the two-environment rule, but on inspection the dev-repo `CLAUDE.md` (the
generic MoAI directive) contains no such rule — it lives only in
`sci-adk-constitution.md` (and the README). So the patch landed there; no root
`CLAUDE.md` edit was needed.

---

## 10. Migration path

### 10.1 Phase A — Preserve current assets (no change)

The following remain exactly as they are:

- `src/sci_adk/core/` (Spec/Evidence/Claim types)
- `src/sci_adk/loop/` (DecisionEngine, verify subroutines, novelty/validity audits)
- `src/sci_adk/cli.py` — **existing verbs preserved** (run/resolve/prior-work/verify/status/init-session); 6 new standalone verbs (`init-spec`/`amend-spec`/`execute`/`append-evidence`/`derive-claim`/`render`) **added in Phase B per §4.6**
- `src/sci_adk/templates/research-workspace/` (hooks/output-style/CLAUDE.md kit)
- `.claude/rules/sci-adk-constitution.md` (modulo §9.3 scoping correction)
- `design/*` (existing design docs)

No code in the rigor layer is touched.

### 10.2 Phase B — Add operational layer assets

New files under `src/sci_adk/templates/research-workspace/`:

```
.claude/
├── agents/
│   ├── manager-prereg.md
│   ├── expert-experimentalist.md
│   ├── expert-statistician.md
│   ├── expert-writer.md
│   ├── expert-literature.md
│   ├── evaluator-rigor.md
│   ├── evaluator-novelty.md
│   └── evaluator-validity.md
├── skills/
│   ├── sci/SKILL.md            # ← orchestration hub (§7.4)
│   └── science/
│       ├── foundation/rigor/SKILL.md
│       ├── workflow/prereg/SKILL.md
│       ├── workflow/experiment/SKILL.md
│       ├── workflow/replicate/SKILL.md
│       ├── workflow/publish/SKILL.md
│       └── tool/academic-search/SKILL.md
├── commands/
│   ├── sci.md
│   ├── sci-plan.md
│   ├── sci-experiment.md
│   ├── sci-publish.md
│   ├── sci-verify.md
│   ├── sci-replicate.md
│   └── sci-status.md
└── output-styles/
    └── science-orchestrator.md
```

All assets are *added*, not replacing existing ones.

### 10.3 Phase C — `init-session` upgrade

`sci-adk init-session <dir>` learns to install the Phase B asset tree alongside
the existing kit. Behavior:

- Existing workspaces (pre-upgrade): unchanged unless user re-runs `init-session`
- New workspaces: get full kit including agents/skills/commands/output-styles
- Re-running `init-session` on an existing workspace: idempotent merge (existing
  behavior), now extends to the new asset directories

Marker guard (`src/sci_adk/` + `.claude/output-styles/moai/` presence detection)
remains unchanged.

### 10.4 Backward compatibility

| Existing | After upgrade | Compatibility |
|---|---|---|
| `/research` slash command | **Removed** — no existing users to migrate; new workspaces install `/sci` directly | n/a (no users) |
| `researcher` output-style | **Removed** — consistent with `/research` removal (§7.3); `science-orchestrator` becomes the sole installed output-style. No existing users to migrate | n/a (no users) |
| `UserPromptSubmit` re-anchor hook | Unchanged | ✅ |
| `Stop` hook → `sci-adk verify` | Unchanged | ✅ |
| `sci-adk` CLI verbs | Existing verbs unchanged; 6 new standalone verbs added per §4.6 (`init-spec`, `amend-spec`, `execute`, `append-evidence`, `derive-claim`, `render`); `sci-adk run` preserved as 5-stage wrapper | additive |
| `runs/<id>/` layout | Unchanged | ✅ |

External users on the existing kit experience zero forced changes. Upgrading is
opt-in via `sci-adk init-session --upgrade <dir>` (flag to be added in Step 2).

### 10.5 Build sequence (Step 2 plan, not yet executed)

In execution order:

1. design doc reviewed & locked (this document → AGREED)
2. **sci-adk CLI verb decomposition** (per §4.6): add 6 standalone verbs (`init-spec`, `amend-spec`, `execute`, `append-evidence`, `derive-claim`, `render`) + preserve `sci-adk run` as 5-stage wrapper. Tests: per-verb CLI tests + wrapper integration test + verb_decomposition regression test.
3. `science-orchestrator` output-style authored (only persona; `researcher` removed per §10.4)
4. v1 worker agent definitions (5 files: manager-prereg + expert-{experimentalist,statistician,writer,literature})
5. v1 guard agent definitions (3 files: evaluator-{rigor,novelty,validity})
6. v1 Skills: `sci/SKILL.md` orchestration hub (§7.4) + `science-foundation-rigor` + `science-workflow-{prereg,experiment,publish}` (≥5 files; `replicate` and `tool/academic-search` may slip to step 11 if scope tight)
7. `/sci` thin command files (6 files: sci.md + 5 subcommand routers; `sci-replicate.md` scaffolded as v2 stub)
8. `init-session` upgrade (Phase C: install agents/skills/commands/output-style into research workspace; idempotent merge; marker guard unchanged)
9. End-to-end test on a real cycle: re-run IEAM-P8 BAF (or pick new domain) through `/sci plan → experiment → publish → Stop verify` and verify paper/ artifacts byte-identical to pre-pivot baseline modulo orchestration metadata
10. Documentation updates (`CLAUDE.md` two-env scoping per §9, README operational-layer mention, design doc status → AGREED)
11. Commit + report (+ optional scope items: science-tool-academic-search Skill, science-workflow-replicate Skill, sci-replicate.md activation if v2 promoted)

Each step uses `Agent(subagent_type: "builder-agent" | "builder-skill")` per
MoAI's authoring patterns (`.claude/rules/moai/development/agent-authoring.md`).

---

## 11. Non-goals

The following are *explicitly out of scope* for this design and the build that
follows. Recording them here prevents future drift.

- **LLM-as-verdict (chief-judge over N tournament)** — `adoption-roadmap.md` §5/C
  permanent CUT. Evaluator agents remain advisory; only `sci-adk verify` decides
  pass/fail.
- **External-system integration** (Sakana, PaperQA2, ether0, Kosmos, FutureHouse
  domain tools) — deferred per `adoption-roadmap.md` stage model; gated by
  per-problem triggers.
- **Novelty N2/N3 render-time gate** (`\novelty{}` markup + scoped-render + verify
  re-scan) — separate track per `literature-acquisition.md` v0.6.
- **Cross-doc main↔SI `\ref` verify gate** — deferred per `paper-figures-and-si.md`
  Phase 4c (Overleaf compile-order wrinkle); plain-text "Figure S1" authoring
  convention remains.
- **Replicator worker + replication evaluator** — scaffolded in §4 (deferred) and §5
  (deferred); promote when replication semantics surface as a real bottleneck.
- **Theorist worker** — deferred to v2; current pre-reg flow uses user-driven
  hypothesis authoring.
- **Domain-specific kernels** — `feedback_domain-generality` holds; sci-adk kernel
  remains domain-general. Domain knowledge enters via `science-domain-*` Skills only.
- **Auto-commit/auto-PR pipeline** — sci-adk's "done" is verify-pass, not git push;
  no Conventional Commits gate added.

---

## Appendix A — Open decision-forks for Step 2

These are *implementation* questions the user should answer before Step 2 begins.
None block this design doc from being locked; they shape the build.

### F-A.1 — `science-orchestrator` vs `researcher` output-style — **CLOSED**

Decided during design review: `researcher` output-style is removed alongside the
`/research` command (§7.3, §10.4) since sci-adk has no existing users. The single
installed persona is `science-orchestrator`. Status: closed, no Step-2 input needed.

### F-A.2 — Domain Skill loading mechanism — **CLOSED**

Decided: option **(iii) — both**. `init-session --domain <name>` provides explicit
user choice (loaded at session start); `manager-prereg` auto-detects domain from
Spec text as a fallback when `--domain` is not supplied. Explicit user choice
always wins on conflict. Status: closed.

### F-A.3 — Worker isolation mode — **CLOSED**

Decided: **yes for all workers including `expert-statistician`**. All 5 v1 workers
(manager-prereg, expert-{experimentalist, statistician, writer, literature}) spawn
with `Agent(isolation: "worktree")` per
`.claude/rules/moai/workflow/worktree-integration.md`. Rationale: consistency
across catalog; isolation overhead is minor relative to LLM cost; statistician
writes Claim records via `sci-adk derive-claim`, which benefits from isolated CWD.
Status: closed.

### F-A.4 — Evaluator agent invocation discipline — **CLOSED**

Decided: option **(ii) — orchestrator discretion**. Evaluator agents are an
optimization (catch problems earlier with better explanations), not a requirement.
The CLI gate (`sci-adk verify` via Stop hook) is the hard verdict regardless.
Skipping evaluator agents emits a single log line to `runs/<id>/orchestrator.log`
per §6.4 audit trail, detectable by `sci-adk status <run>`. Status: closed.

### F-A.5 — `/sci` default behavior with no subcommand — **CLOSED**

Decided: option **(i) — autonomous pipeline**. Bare `/sci` routes to the
autonomous `plan → experiment → publish` pipeline with `AskUserQuestion`
confirmation at each stage transition, matching `/moai`'s default behavior.
Status: closed.

---

## Appendix B — Cross-reference checklist (verified 2026-06-22)

Every cross-reference in this document was checked against the actual file:

- `design/abstractions.md` — Spec/Evidence/Claim definitions, invariants S/E/C numbering
- `design/rigor-shell-architecture.md` §2, §6.2, §8 — three interfaces, verify gate, decision-forks
- `design/adoption-roadmap.md` §1, §5/C — verdict-path test, LLM-as-verdict CUT
- `design/research-session-enforcement.md` v0.2 D1–D4 — hooks/kit/init-session
- `design/literature-acquisition.md` v0.6 — N1 novelty 2-kind state
- `design/figure-digitization.md` — digitized Evidence kind
- `design/evidence-validity.md` — synthetic→empirical block
- `design/paper-figures-and-si.md` Phase 4c — cross-doc ref deferral
- `design/tool-policy.md` — allowed/excluded tool list
- `.claude/rules/sci-adk-constitution.md` — current dev-repo rules
- `.claude/rules/moai/core/moai-constitution.md` — MoAI principles being mirrored
- `.claude/rules/moai/development/coding-standards.md` — Thin Command Pattern
- `.claude/rules/moai/workflow/worktree-integration.md` — agent isolation rules

If any cross-reference is found stale during Step 2, this document is updated
*before* the implementation step that depends on it.

---

Version: 1.0 (AGREED — locked after section-by-section review, 2026-06-22)
Status: AGREED → BUILT (2026-06-22). Steps 1-10 of the §10.5 sequence complete:
CLI verb decomposition (6 verbs + run wrapper), science-orchestrator output-style
(researcher + /research removed), 5 worker + 3 guard agent defs, 5 Skills (sci hub +
foundation-rigor + 3 workflows), 7 /sci thin commands, init-session full-kit install
(_PLAIN_ASSETS 3→23), e2e live cycle PASSED on t1-demo (verify exit 0; exposed+fixed a
pre-existing t1-Docker bug), and the §9.3 docs patch. Optional deferred to a later pass:
science-workflow-replicate + science-tool-academic-search Skills, sci-replicate.md
activation. 1024 engineering tests green.
Review summary:
  §1 motivation: approved (+ pattern-vs-volume Note)
  §2 decision record: approved (3 rounds + 7 rejected alternatives)
  §3 isomorphism: approved (+ alignment-not-lock-in §3.5)
  §4 worker catalog: approved (5 workers + §4.6 CLI verb decomposition)
  §5 guard catalog: approved (3 guards + invocation discipline note)
  §6 sci-adk constraints: approved (+ 3 mechanism clarifications)
  §7 /sci surface: approved (/research removed + §7.4 sci Skill + §7.5 v1 non-goals)
  §8 end-to-end: approved (6-stage rewrite aligned with §4/5/6)
  §9 two-env scoping: approved
  §10 migration: approved (4 fixes incl. researcher output-style removed)
  §11 non-goals: approved
  App A: F-A.1~F-A.5 all CLOSED
  App B: 13 cross-references verified
Authority: governs the operational layer; rigor layer authority remains with
  `design/abstractions.md` + `design/rigor-shell-architecture.md`
