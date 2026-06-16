# sci-adk — Rigor ADK Plan (Step 3 of 3 → 2 → 1)

> Status: PLANNED (2026-06-16).
> Identity: **sci-adk** = a **domain-general rigor/verification ADK** — a
> *referee/scorekeeper, not a player* — for the user's **own broad research** (not an
> external shipping product). It *builds* the rigor kernel (record≠belief, frozen
> criteria, verification, provenance, replay) and *borrows* capabilities (experiment
> authoring, hypothesis, literature, prose) via the in-session Claude agent + subagents
> + external open tools. This document is **Step 3** of the user-confirmed sequence
> **Step 3 → Step 2 → Step 1**: it fixes that identity, maps the milestone-3 §4 work
> into the structure, and hands Step 2 the open questions. It is a PLAN, not the
> architecture (Step 2) and not code (Step 1).

---

## 1. Framing

sci-adk today is a working research compiler core: a proposal goes in, a paper draft
+ code + an append-only evidence trail comes out, driven by `sci-adk run`
(`src/sci_adk/cli.py:4-9`). The **engine is real**; what is missing is the **rigor
shell** around it — the kernel + protocol that turns the engine into a domain-general
**referee/scorekeeper** for the user's own research, not a library improvised on top of
the MoAI-ADK build harness.

The north star is not "copy moai-adk," and not "ship a product." It is to **borrow
moai-adk's orchestration shape and invert its truth model** — replacing "build state =
truth" with sci-adk's record-vs-belief model (`design/abstractions.md:15-48`) — and to
build only the *rigor kernel*, borrowing research *capabilities* rather than competing
with them (§2). This document makes that inversion the spine, does an honest gap
analysis, maps each milestone-3 §4 item to a sci-adk component, and hands Step 2 a
precise list of open architecture questions.

Confidence in the framing: **strong** — grounded in the type spec
(`design/abstractions.md`), the tool policy (`design/tool-policy.md`), the
milestone-3 roadmap (`design/milestone-3.md`), and direct reads of the code
(citations throughout).

---

## 2. Identity: sci-adk as a domain-general rigor ADK

### 2.1 Referee/scorekeeper, not a player

sci-adk borrows moai-adk's *shape* (an ADK: orchestration directives + a checkpoint
protocol + a command surface, propose/experiment/compile) but it is **not** a product
shipped to external researchers and **not** a capability competitor. It is a
**referee/scorekeeper** for the user's *own* broad research:

- It **builds** the *rigor kernel* — the part that must be trustworthy: record≠belief
  (Spec/Evidence/Claim), frozen criteria, verification, provenance, and replay.
- It **borrows and wraps** *capabilities* — experiment authoring, hypothesis generation,
  literature, prose — from the in-session Claude agent + subagents and external open
  tools. These are wrapped behind an adapter (§6, OQ-7), not reimplemented.

Two axes are deliberately separated: the system **generalizes over domains** (a general
kernel + per-domain capability plugins), while the **user axis stays self/lab** — a
personal/lab rigor harness, not a productization effort.

The difference from moai-adk is the quality gate. moai-adk's gate is software-engineering
truth (TRUST 5, LSP, coverage — monotone, binary, terminal). sci-adk's gate is the
Spec/Evidence/Claim contract: a per-Spec `DecisionRule` judged against accumulated
Evidence, where belief is non-monotone and a null result is a result
(`design/abstractions.md:116-128, 178-186, 238-257`).

### 2.1a External release — deferred, not foreclosed

External release is a **future option after stabilization**, not a current goal. The
system is used now as the user's own/lab rigor harness; external release is considered
only once the plug-seam and kernel are sufficiently fixed. Crucially, every architecture
decision here (general kernel, capability-adapter isolation, clean plug-seams) is made to
**preserve** that option — externalization is *deferred, not foreclosed*. The most
natural future external form is an **open-source reference implementation + a methodology
paper**, not a turnkey product.

### 2.2 Engine vs shell (the load-bearing distinction)

- **Engine — already self-standing.** `pyproject.toml` defines a package named
  `sci-adk` v0.1.0 (single runtime dep `pydantic>=2`), a `src/` layout, a console
  script `sci-adk = sci_adk.cli:main`, and an optional `[tools]` extra pinning
  paperforge to a git SHA (`pyproject.toml:5-26`). The core types, parser, decision
  engine, claim updater, experiment runner, literature acquirer, compiler, renderer,
  and CLI all exist under `src/sci_adk/` (21 modules; see `Glob src/sci_adk/**/*.py`).
  The engine does **not** import anything from `.claude/` or `.moai/`.

- **Shell — currently borrowed.** There is no sci-adk rigor shell yet.
  The orchestration the project uses *right now* is MoAI-ADK's: root `CLAUDE.md`, the
  agents in `.claude/agents/moai/`, the MoAI skills, and the plan/run/sync commands.
  That shell is the *build harness* that constructs sci-adk; it is legitimate for
  building, but it is **not** sci-adk's own rigor shell. The work =
  giving sci-adk its own kernel + checkpoint protocol, built on Spec/Evidence/Claim, so
  it can referee the user's research without inheriting the SW-engineering truth model.

Confidence: **strong** for "engine self-standing" (measured in `pyproject.toml` and
the module list); the shell gap is by inspection — no `src/sci_adk/`-native
orchestration/agent layer exists in the package.

---

## 3. The inversion (the spine of this plan)

Making **sci-adk** "a moai-adk for science" is an **inversion at the truth-model layer**.
The orchestration *shell* is analogous; the *quality gate / truth model* is inverted.

| moai-adk (SW engineering) | sci-adk (science) |
|---|---|
| MoAI orchestrator (autonomous, spawns subagents) | the **in-session Claude Code agent** as research orchestrator — may itself fan out to in-session Claude subagents, but never via `claude -p`/API (§3.1) |
| SPEC (EARS, frozen) | Spec (pre-registration, frozen; S1/S5) |
| plan → run → sync | propose → experiment → compile(paper) |
| specialist agents (expert-backend, …) | research specialists (experiment-author, judge, paper-writer, literature-acquirer) |
| TRUST 5 quality gates: **build = truth (monotone, binary, terminal)** | **Evidence/Claim + per-Spec DecisionRule: record ≠ belief (non-monotone, revisable, null is a result)** |
| skills (progressive disclosure) | research skills |
| LSP / coverage / conventional-commits gates | EXCLUDED by tool-policy; replaced by DecisionRule-per-Spec |

**Row-by-row:**

- **Orchestrator.** moai-adk's MoAI is an autonomous orchestrator that spawns
  subagents at will. sci-adk's orchestrator is the *already-running in-session
  agent*, which **may likewise fan out to Claude subagents** (parallel experiments,
  independent judges; `design/tool-policy.md:42-44` lists "Claude subagent" as
  allowed). The single inverted assumption is the *mechanism*, not the fan-out: the
  spawner must be the in-session agent, never sci-adk's Python via the Anthropic API
  or `claude -p` (see §3.1).
- **Frozen contract.** moai-adk's SPEC freezes requirements in EARS. sci-adk's
  Spec freezes the *question and the DecisionRule* before results are seen
  (anti-HARKing), and amending it requires a human checkpoint even in autonomous mode
  (`design/abstractions.md:62-67, 118-128`, invariants S1 and S5). **(B) The freeze must
  reach the qualitative path: a `qualitative` DecisionRule must freeze a *substantive
  rubric R* (concrete criteria in `DecisionRule.expression`, `abstractions.md:93-102`),
  not a vague placeholder like the current "Expert judgment based on evidence"
  (`runs/t1-demo/paper/draft.md:29`). A frozen-but-vague rule freezes the question but
  defers the real criteria to eval time (post-hoc = HARKing); N independent judges then
  only reduce variance, not the post-hoc-ness. This operationalizes S3
  (`abstractions.md:122-124`) and extends anti-HARKing to qualitative verdicts; R itself
  changes only via S5 versioning.**
- **Phase verbs.** plan→run→sync becomes propose→experiment→compile. "compile" here
  means: parse → run experiment → accumulate Evidence → derive Claims → render paper,
  which is exactly what `ResearchCompiler` already orchestrates
  (`src/sci_adk/loop/compiler.py:4-25`).
- **Specialists.** The SW experts map to research roles whose products are typed
  artifacts (experiment code → Evidence; a verdict → Claim movement; prose → paper).
  Whether these roles are agent files or prompt-protocols is a Step-2 question (§6).
- **The gate (the actual inversion).** moai-adk treats a green build as truth: one
  signal, monotone, terminal. sci-adk rejects that
  (`design/abstractions.md:15-29`): the *record* (Evidence) is append-only and
  monotone, but *belief* (Claim status/confidence) is non-monotone — a supported
  claim can be demoted or refuted by later Evidence (`design/abstractions.md:238-257`,
  invariants C1/C5). "Done" is "DecisionRule met OR evidence budget exhausted OR human
  checkpoint," and a null result is a valid convergence, not a stuck state
  (`design/abstractions.md:280-292`).
- **Skills.** Borrowable structure (progressive disclosure), retargeted to research
  knowledge.
- **The excluded gates.** LSP/coverage/conventional-commits are excluded from the
  research runtime *because each imports a SW-workflow truth assumption*
  (`design/tool-policy.md:60-74`). Their replacement is not a new constant; it is the
  structural DecisionRule-per-Spec mechanism (`design/abstractions.md:310-317`).

The inversion is the whole point: borrow the shell, replace the truth model.

### 3.1 The HARD constraint that shapes the shell

sci-adk's LLM intelligence is supplied by **Claude Code's already-running in-session
agent — and any Claude subagents it delegates to** (`design/tool-policy.md:42-44`) —
not the Anthropic API, and not a `claude -p` subprocess (every `claude -p` is a new
billed invocation) (`design/tool-policy.md:24-29`, `design/milestone-3.md:80-93`, and
the user's 2026-06-16 constraint).

Consequence: the "intelligence" steps — writing experiment code, judging
proof/qualitative checkpoints, writing paper prose — are performed by the in-session
agent **at checkpoints**, with results recorded into `runs/<id>/`. Numeric
DecisionRules stay fully autonomous and free (`design/milestone-3.md:90-93`). The
compiler already encodes this: it never spawns `claude -p` and never calls an API;
non-numeric rules are surfaced as a `Checkpoint` for an injected `judge`
(`src/sci_adk/loop/compiler.py:11-17, 46-57`).

**Therefore the sci-adk orchestration layer is a *checkpoint protocol* driven by the
in-session agent — which MAY fan out to Claude subagents at a checkpoint** (e.g.
parallel experiment authors, or several *independent* judges whose verdicts are then
aggregated — see (C) below; `design/tool-policy.md:42-44` allows "Claude subagent").
What is excluded is not subagents but the *mechanism*: sci-adk's Python must never
autonomously call an LLM ("never by autonomous Python calling an LLM",
`design/milestone-3.md:84-90`) — no Anthropic API, no `claude -p`. The rigor shell builds
clean *rails* for the in-session agent (and any subagents it spawns) to drive each
phase, plus deterministic infrastructure (provenance, citations, LaTeX) that needs no
LLM at all. Two lines stay fixed: the S5 Spec-amendment human checkpoint cannot be
delegated to a subagent (`design/abstractions.md:118-128`), and every subagent's output
must carry provenance (E3, `design/abstractions.md:178-186`).

**(C) Aggregating N judges — chief-judge, not a vote.** Independent judges cut
single-judge *leniency/variance* (problem A) but do not by themselves close two gaps:
they do not aggregate to one Claim movement, and N opinions are still post-hoc unless a
rubric is frozen (B). So the pattern is **not k-of-n voting**. N independent judge
subagents each emit a verdict + reasoning (context isolation makes them genuinely
independent); one **chief judge** then applies the *frozen rubric R* (B), states which
reasoning is decisive **under R**, and renders the single verdict that moves the Claim.
The chief's role is bounded to *"adjudicate the disagreement by R"* — **no free
discretion**: a free-discretion chief would re-concentrate the very bias A was meant to
remove and open a fresh HARKing vector at the top. **C is therefore safe only with B**
(the frozen R is what bounds the chief); the two are a pair, not independent options.
The N verdicts plus the chief's R-grounded reasoning are recorded as provenance
(E3, `design/abstractions.md:178-186`). At the compiler interface this is still a single
injected `judge` (`src/sci_adk/loop/compiler.py:46-57`) whose *internal* shape is
chief-over-N — so it composes with the existing mechanism; the exact chief role-spec and
the on-disk form of the N verdicts are Step-2 implementation (§6, OQ-1/OQ-3).

---

## 4. Gap analysis: kernel vs borrowed shell

### 4.1 What sci-adk already has (measured)

- A self-standing package: name/version/console-script/deps in
  `pyproject.toml:5-26`; no dependency on `.claude/`/`.moai/`.
- A working compile path: `sci-adk run <proposal>` →
  `runs/<spec.id>/{spec.json, evidence/, claims/, paper/draft.md}`
  (`src/sci_adk/cli.py:4-9`; observed artifacts in `runs/t1-demo/` via
  `Glob runs/t1-demo/**/*`: `spec.json`, `evidence/…json`, `claims/claim-hyp-001.json`,
  `paper/draft.md`, `checkpoints.md`).
- The record-vs-belief core: `core/spec.py`, `core/evidence.py`, `core/claim.py`,
  `core/parser.py`; the decision engine (`loop/decision_engine.py`), non-monotone
  claim updater with injectable judge (`loop/claim_updater.py`), and the checkpoint
  surface in `loop/compiler.py:50-57`.
- A pluggable experiment hook: `compile(experiment=fn)` where
  `fn(spec, workspace_dir) -> [EvidenceItem]` (`src/sci_adk/loop/compiler.py:19-22,
  43-44`) — the swap point for a real experiment.
- Literature acquisition wired (paperforge), policy-recorded
  (`design/tool-policy.md:106-144`).
- 333 tests green (per `design/milestone-3.md:30`); not re-run here.

### 4.2 What the rigor shell still needs

- **Its own orchestration shell.** A research-native equivalent of moai-adk's
  `CLAUDE.md` + agent/skill catalog + command surface, expressed in terms of
  Spec/Evidence/Claim and the checkpoint protocol — NOT inherited from the build
  harness. Today this does not exist as a `src/sci_adk/`-native layer (by inspection).
- **A turnkey checkpoint loop.** The mechanism exists (injectable `judge`,
  `Checkpoint`), but the **checkpoint → judge → recompile** path is not yet a single
  turnkey helper (`design/milestone-3.md:52-55`). This is the heart of the shell.
- **A clean kernel/capability seam (not a product boundary).** Separate the *rigor
  kernel* from *borrowed capabilities* behind one adapter (§6, OQ-7), and keep the
  two-environment separation already documented
  (`.claude/rules/sci-adk-constitution.md`, "Critical Environment Separation"). The
  external *product boundary* is **not a current decision** — this is a self/lab harness
  (OQ-5 moot); the seam is built to *preserve* a future external option (§2.1a), not to
  ship today.
- **The finishing infrastructure** that the engine deliberately left open
  (`design/abstractions.md:296-308`): a real renderer (prose + citations + LaTeX) and
  real provenance.

### 4.3 Honest "not yet decided"

- The **on-disk representation** of a checkpoint and its resolved verdict in
  `runs/<id>/` (a `checkpoints.md` exists today via `Glob runs/t1-demo/**/*`; whether
  that is the contract is open — OQ-1).
- How an **arbitrary-domain** proposal selects/authors its experiment and which
  capability adapter serves it — the central generalization question, promoted to OQ-7.

(Resolved since the last revision, no longer open: specialist *form* = prompt-protocol +
subagent fan-out, no external agent catalog (OQ-4); execution = in-session agent, with a
deterministic-only headless mode (OQ-9); and there is no external product boundary to
decide — self/lab harness (OQ-5 moot). See §6.)

---

## 5. How milestone-3 §4 maps into sci-adk

milestone-3 §4 (`design/milestone-3.md:97-116`) is "one full real cycle on T-1." Each
of its four items builds a specific sci-adk component. Driven vs deterministic is
called out per the HARD constraint (§3.1).

| §4 item | sci-adk component it builds | Agent-driven or deterministic infra |
|---|---|---|
| **§4.1 Real T-1 experiment** (`milestone-3.md:101-104`; Tier 1.1) | The **experiment-author rail** + a real experiment runner. The in-session agent writes the genuine prime/Gödel graph encoding (atoms + bonds + structure, injectivity test); it runs via the existing Docker runner and produces real statistics into Evidence, replacing the toy at `src/sci_adk/runner/docker_executor.py:203` (the `H2O→2×5=10`, count-ignoring encoding at `docker_executor.py:208-234`). Swap point: the `experiment=fn` hook (`compiler.py:19-22, 43-44`). | **Both.** Writing the experiment code = agent-driven (in-session checkpoint). Running it in Docker + capturing `Result` fields = deterministic infra. |
| **§4.2 Spec with a verifiable rule** (`milestone-3.md:105-106`; Tier 1.3) | A **DecisionRule↔statistic alignment** for the experiment-author rail: the T-1 hypothesis gets a rule (threshold/interval) whose statistic the experiment actually emits, so the engine drives a real verdict. Fixes the measured mismatch — the canonical interval rule needs `Result.ci` but T-1 emits `point` (`milestone-3.md:38`; `draft.md:39` shows `point=3`). | **Deterministic** (engine evaluates a numeric rule autonomously), with rule authoring done by human/agent up front. |
| **§4.3 Judge + recompile** (`milestone-3.md:107-109`; Tier 1.2) | The **judge rail** + a turnkey **checkpoint → judge → recompile** helper. The agent resolves the qualitative checkpoint in-session — optionally as a **chief judge over N independent judge subagents** (§3.1 (C)) — and injects the verdict via `ResearchCompiler(judge=…)` / `ClaimUpdater(judge=…)` so the Claim reaches `supported`/`refuted` with a real basis — replacing the current unjudged state (`draft.md:30` `Status: proposed`, `draft.md:41-46` "Pending agent judgments"). The injection points exist (`compiler.py:46-57`); the turnkey loop does not. | **Agent-driven** (the verdict is intelligence), wrapped by a **deterministic** recompile helper. |
| **§4.4 Paper prose + citations** (`milestone-3.md:110-111`; Tier 2.4-2.5) | The **paper-writer rail** + citation/render infra. The agent writes real abstract/intro/method/results/discussion from Claims+Evidence over the deterministic skeleton (`src/sci_adk/render/paper.py`), fixing the duplicated "approaches" block (`draft.md:19-23` repeats `draft.md:14-17`); paperforge acquires 2-3 papers, cited as DOIs + BibTeX. | **Both.** Prose = agent-driven. References section, BibTeX emission, DOI acquisition = deterministic infra. |

Completing §4.1-§4.4 yields the first run where paper draft, working code, and judged
evidence trail are all *real* (`design/milestone-3.md:113-116`) — and, in
sci-adk terms, the first instantiation of all four specialist rails on a real
problem.

**Verifier = the kernel's heart; verification strategy.** The *verifier* interface — the
thing that checks Evidence against frozen criteria — is the core of the rigor kernel; it
is what the autonomous `DecisionEngine`/numeric-rule path already embodies
(`design/abstractions.md:280-292`). Two strategy decisions follow:

- **First real cycle = a real small problem with a cheap, *exact* verifier**, not the
  toy. With an exact verifier the autonomous numeric path drives the loop and rigor is
  automatic; qualitative-judgment problems come *after*. T-1 qualifies *if* driven by its
  exact injectivity check (the §4.2 numeric path) rather than routed to a qualitative
  judge — so for the first demonstration §4.2 leads and §4.3 is the follow-on.
- **Generalization is verified on ≥2 *different* problems**, so the kernel's abstraction
  is not accidentally specialized to one case.

---

## 6. The 3 → 2 → 1 sequence

### Step 3 (this document) — delivers

- The sci-adk identity (engine-vs-shell, §2) and the truth-model inversion as the
  organizing principle (§3).
- The gap analysis (kernel vs borrowed shell) grounded in measured facts (§4), honest
  about what is undecided.
- The mapping of every milestone-3 §4 item to a sci-adk component (§5).
- The open-question set handed to Step 2 (below) — the foundation for Steps 2 and 1.

### Step 2 (next) — must DESIGN and AGREE the sci-adk orchestration architecture

Step 2 designs the research-specialist layer + checkpoint protocol. Several questions are
**resolved below** by the identity decisions; the rest remain genuinely open:

- **OQ-1 — Checkpoint representation.** How is a checkpoint (and its resolved verdict)
  represented on disk and in the protocol? Is the existing `runs/<id>/checkpoints.md`
  (`Glob runs/t1-demo/**/*`) the contract, or is a typed artifact needed? *Includes the
  multi-judge case:* the on-disk form of N independent verdicts + the chief's R-grounded
  adjudication (the chief-judge *pattern* is decided in §3.1 (C); only its representation
  is open here).
- **OQ-2 — Artifact locations.** Where do agent-driven artifacts (experiment code,
  the judge's verdict + basis, paper prose) live under `runs/<id>/`, alongside the
  existing `spec.json` / `evidence/` / `claims/` / `paper/`?
- **OQ-3 — Turnkey loop shape.** What is the exact shape of the turnkey
  checkpoint → judge → recompile loop (entry point, idempotent re-runs, how a verdict
  re-enters via `ResearchCompiler(judge=…)`)? (Mechanism: `compiler.py:46-57`.) *The
  injected `judge` may internally be chief-over-N independent judges (§3.1 (C));* the
  loop must thread the frozen rubric R to the chief and persist all N verdicts — the
  role-spec and wiring are the open part.
- **OQ-4 — Specialist form. RESOLVED.** Research specialists (experiment-author, judge,
  paper-writer, literature-acquirer) are **prompt-protocols** the in-session agent
  follows, with subagent fan-out — **not** agent-definition files and **no** external
  agent catalog (HARD constraint §3.1 + the self/lab identity §2 settle this). Step 2
  designs the protocols, not a catalog.
- **OQ-5 — Product boundary / decoupling. MOOT (for now).** sci-adk is a self/lab rigor
  harness, not an external shipping product (§2), so there is no product boundary to
  decide now. What remains is the *kernel/capability seam* (folded into OQ-7), kept clean
  to preserve a future external option (§2.1a) — a design concern, not a shipping
  decision.
- **OQ-6 — Research command surface.** What is the propose/experiment/compile command
  surface, and how does it relate to the existing `sci-adk run`
  (`src/sci_adk/cli.py:21-38`) — extend it, or wrap it in a shell?
- **OQ-7 — Domain-general kernel + capability adapters (CENTRAL).** The core design
  question. The system = a **general rigor kernel** + **per-domain capability plugins** +
  a **capability adapter**. The kernel knows only the verifier/experiment/judge
  *interfaces* — never domain content, never the capability's identity. **All
  Claude-Code-ness lives in one capability adapter**, so the capability can later be
  swapped without touching the kernel. Concretely this replaces the single hard-coded
  `t1_molecular_experiment` (`compiler.py:18` import in `cli.py`) with adapter-served
  experiment selection.
- **OQ-8 — Spec-amendment checkpoint surfacing.** How does the shell surface the S5
  human checkpoint for Spec amendment (`design/abstractions.md:118-128`) within the
  in-session model?
- **OQ-9 — Execution model & subagent fan-out. RESOLVED.** Execution runs **with an
  in-session Claude agent** (mode a): the orchestrator may fan out to Claude subagents
  (parallel experiments, independent judges; `design/tool-policy.md:42-44`). A
  **headless/standalone** mode is the **deterministic spine only** — record replay and
  re-verification of frozen numeric rules, with *no* autonomous capability (no LLM). Both
  modes are first-class; subagent fan-out is a core capability of the in-session mode.

Priorities for Step 2: **High** — OQ-1 (checkpoint representation), OQ-3 (turnkey loop),
OQ-7 (general kernel + capability adapter — now central). **Medium** — OQ-2, OQ-6.
**Resolved** — OQ-4, OQ-9 (decided above). **Moot** — OQ-5. **Low** — OQ-8. Phase
ordering: settle the High set first; the kernel/adapter seam (OQ-7) constrains the rest.

### Step 1 (last) — EXECUTE milestone-3 §4 on the agreed architecture

With the Step-2 architecture agreed, Step 1 runs the §4 sequence
(`design/milestone-3.md:97-116`) — §4.1 real experiment → §4.2 verifiable rule →
§4.3 judge+recompile → §4.4 prose+citations — instantiating the four specialist rails
on T-1. Within §4, ordering is fixed (each step depends on the prior); priority is
**High** for §4.1-§4.3 (the science loop, without which the output is not real) and
**Medium** for §4.4 (the usable paper). Generalization across domains (OQ-7) — verified
on ≥2 different problems (§5) — and Tier 3 (provenance, robustness, ops;
`design/milestone-3.md:70-76`) follow as a later phase.

---

## 7. Constraints & non-goals

- **Tool-policy exclusions stay excluded** from the research runtime: LSP servers,
  ast-grep, Conventional Commits, Coverage thresholds — each because it imports a
  SW-workflow truth assumption (`design/tool-policy.md:60-74`). They remain legitimate
  in the *build harness* (`design/tool-policy.md:6-20`); the exclusion is about
  sci-adk's rigor gate, not how it is built.
- **No hardcoded success metrics** anywhere — not in this plan, not in the shell. The
  replacement is structural: each Spec declares its own `DecisionRule` per hypothesis,
  judged against Evidence (`design/abstractions.md:310-317`). This plan uses
  priority labels (High/Medium/Low) and phase ordering, never thresholds or durations.
- **Qualitative judgment is pre-registered, not post-hoc.** A `qualitative` DecisionRule
  freezes a substantive rubric R at Spec-freeze (B, §3); when N independent judges are
  used, a chief judge aggregates them by applying that Spec-declared R — not k-of-n
  voting (C, §3.1). R and the chief's adjudication are Spec-declared, never hardcoded;
  chief-judge has no `n` to hardcode, so the aggregation stays §7-clean.
- **In-session agent only — a chosen identity, not just a constraint.** sci-adk's Python
  never calls an LLM on its own (no Anthropic API, no `claude -p`); intelligence comes
  from the in-session agent, which *may* fan out to Claude subagents
  (`design/tool-policy.md:42-44`). This is the referee/scorekeeper stance (§2): the
  kernel borrows capabilities, it does not autonomously *be* one
  (`design/tool-policy.md:24-29`, §3.1).
- **Agents propose; the engine judges. No self-certification.** Capabilities (the
  in-session agent + subagents) only *generate/propose* — experiment code, candidate
  verdicts, prose. The **engine** renders the verdict by applying the frozen criteria; an
  agent may never self-certify its own output as the result. The **source of truth for a
  verdict is the engine**, not the capability that produced the artifact (the chief-judge
  bound in §3.1 (C) enforces this at the judgment step).
- **One capability-adapter seam.** All Claude-Code-specific behavior is isolated behind a
  single capability adapter (§6, OQ-7); the rigor kernel depends only on
  verifier/experiment/judge interfaces, so the capability can be swapped without touching
  the kernel.
- **Spec-amendment human checkpoint (S5).** Even in autonomous mode, amending a frozen
  Spec requires a human checkpoint — the single carve-out from autonomy that preserves
  the anti-HARKing guarantee (`design/abstractions.md:118-128`).
- **Scope discipline — do not rebuild the engine.** The core types, parser, decision
  engine, claim updater, runner, literature acquirer, compiler, renderer, and CLI
  exist and pass tests. The work adds the *rigor shell* and the *finishing
  infrastructure*; it must not re-implement what already works
  (`design/milestone-3.md:23-30`).
- **Non-goals for this document.** This is a plan, not the architecture (Step 2) and
  not code (Step 1). It fixes the *identity* and the *patterns* (referee/scorekeeper,
  kernel/adapter split, chief-judge) but does not design the checkpoint protocol or the
  capability adapter in detail — those are the Step-2 open questions (§6).

---

## 8. References

Design docs:
- Record-vs-belief organizing principle: `design/abstractions.md:15-48`.
- Spec / Invariants S1, S5: `design/abstractions.md:62-67, 118-128`.
- Evidence / Invariants E1-E4 (null is a result): `design/abstractions.md:132-186`.
- Claim / Invariants C1, C5 (non-monotone belief): `design/abstractions.md:190-257`.
- Loop mapping (convergence ≠ errors==0): `design/abstractions.md:280-292`.
- Deliberately-open items (renderer, provenance, persistence): `design/abstractions.md:296-308`.
- No hardcoded metrics: `design/abstractions.md:310-317`.
- milestone-3 measured state + tiers + §4 sequence: `design/milestone-3.md:21-38, 42-76, 97-116`.
- Agent-driven HARD constraint: `design/milestone-3.md:80-93`.
- Tool policy build-vs-runtime scope + exclusions + paperforge: `design/tool-policy.md:6-20, 24-74, 106-144`.
- Two-environment separation: `.claude/rules/sci-adk-constitution.md` (Critical Environment Separation).

Code (measured):
- Self-standing package: `pyproject.toml:5-26`.
- CLI entry + compile target: `src/sci_adk/cli.py:4-9, 21-38`.
- Compiler checkpoint/judge model + experiment hook: `src/sci_adk/loop/compiler.py:4-25, 19-22, 43-57`.
- T-1 toy experiment: `src/sci_adk/runner/docker_executor.py:203, 208-234`.
- Empty provenance: `src/sci_adk/provenance/__init__.py` (1 line).
- Run output (toy encoding, "approaches" duplication, unjudged status):
  `runs/t1-demo/paper/draft.md:14-23, 30, 39, 41-46`.
- Module inventory: `Glob src/sci_adk/**/*.py` (21 modules); run artifacts: `Glob runs/t1-demo/**/*`.

---

Version: 1.0 (PLANNED)
Source: Step 3 of the 3 → 2 → 1 rigor-ADK plan sequence (2026-06-16)
Last Updated: 2026-06-16
