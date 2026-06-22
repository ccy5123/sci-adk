# sci-adk — Rigor Shell Architecture (Step 2 of 3 → 2 → 1)

> Status: AGREED (2026-06-16) — all 7 decision-forks (F1–F7) decided in §8; Step 2 closed. This is **Step 2** of the
> user-confirmed sequence Step 3 → Step 2 → Step 1. Step 3
> (`design/sci-adk-productization-plan.md`) fixed the identity and handed over the
> open questions; this document DESIGNS the rigor shell architecture in concrete
> detail (interfaces, on-disk shapes, loop shape) but stops at architecture — no
> code (that is Step 1).
>
> Scope: resolves the **High** open questions OQ-1 (checkpoint representation),
> OQ-3 (turnkey loop), OQ-7 (domain-general kernel + capability adapter — central),
> plus OQ-2 (artifact locations). Lighter treatment of OQ-6 (command surface) and
> OQ-8 (S5 surfacing). Respects all decisions locked in Step 3 §3/§7 and the
> abstractions invariants (record≠belief; S1/S3/S5; E1/E3; C1/C5).
>
> This is a proposal: §2–§7 make concrete recommendations; §8 lists the genuine
> decision-forks where the user's input is needed before Step 1.

Confidence in the grounding: **strong** — every interface below is traced to a
current signature read directly from source (citations throughout). Confidence in
the recommendations: **moderate-to-strong**, flagged per fork in §8.

---

## 1. The seam in one picture

The Step-3 inversion ("borrow the shell, replace the truth model") becomes a single
structural seam: a **rigor kernel** that knows three small interfaces, and **one
capability adapter** behind which all Claude-Code-ness lives.

```
                       ┌─────────────────────────────────────────────┐
   in-session Claude   │            RIGOR KERNEL (sci-adk)             │
   agent (+ subagents) │   knows only 3 interfaces, never domain       │
        │              │   content, never that the capability is CC    │
        │              │                                               │
        │ proposes     │   Verifier   ← DecisionEngine + DecisionRule  │
        ▼              │   Experiment ← experiment=fn hook             │
  ┌───────────────┐    │   Judge      ← injectable judge / Checkpoint  │
  │  CAPABILITY   │───►│                                               │
  │   ADAPTER     │    │   + ResearchCompiler (orchestrates)           │
  │ (all CC-ness) │    │   + record (Spec/Evidence/Claim, append-only) │
  └───────────────┘    │   + provenance / replay (deterministic spine) │
        │              └─────────────────────────────────────────────┘
        │                              │ judges (engine = source of truth)
  generate/propose:                    ▼
   experiment code,            runs/<id>/  (the on-disk record)
   verdicts+basis, prose       spec.json · evidence/ · claims/ · paper/
                               + checkpoints/ · verdicts/ · artifacts/  (NEW, §4)
```

The one-line invariant that makes this safe: **agents propose; the engine judges**
(Step-3 §7). The kernel never asks the adapter for a verdict it then trusts blindly
— it asks the adapter for *findings/verdicts-as-input* and renders the binding
verdict itself by applying the frozen `DecisionRule` (`decision_engine.py:191-219`).

---

## 2. The rigor kernel — three interfaces

The kernel is the trustworthy part. Its job is to turn a *record* into a *belief*
under *frozen criteria*, and to do so reproducibly. The design principle here is
**minimality** (Step-3 §7, "as small as possible; resist speculative abstraction"):
the kernel already embodies these three interfaces in working code; this section
*names* them and pins what is IN vs OUT — it does not invent new abstractions.

### 2.1 Interface A — Verifier (the kernel's heart)

The verifier is what checks Evidence against frozen criteria. It already exists,
fully, as the `DecisionEngine.evaluate` path.

- **Current signature (ground truth):**
  `DecisionEngine.evaluate(rule: DecisionRule, results: EvidenceForHypothesis) -> Verdict`
  (`decision_engine.py:191`). `Verdict = direction + Confidence(basis required)`
  (`decision_engine.py:67-87`).
- **What it knows:** only `rule` (the frozen `DecisionRule`, `spec.py:94-133`) and
  the pre-filtered `(EvidenceItem, Bearing)` pairs bearing on one hypothesis
  (`decision_engine.py:90-109`). It holds **no state and no numeric constant** —
  every number comes from `rule.params` (invariant D1, `decision_engine.py:144-149`).
- **What it does NOT know:** the domain (molecules, theorems, anything), where the
  Evidence came from, whether an LLM was involved, or that the capability is Claude
  Code. It reads a frozen rule and typed Evidence; nothing else.
- **Recommendation:** treat `DecisionEngine` as the **canonical Verifier interface
  as-is**. Do not wrap it in a new abstract base class — that would be speculative.
  The verifier *interface* the kernel exposes is literally `evaluate(rule, results)
  -> Verdict`. This is the source-of-truth boundary for "the engine judges."

This is the only path by which belief is produced. Numeric kinds
(`threshold`/`bayesian`/`interval`) are evaluated autonomously and free
(`decision_engine.py:256-445`); non-numeric kinds (`proof`/`qualitative`) **route
to Interface C** rather than being computed (`decision_engine.py:453-533`).

### 2.2 Interface B — Experiment (record producer)

The experiment interface turns a Spec into Evidence. It already exists as the
pluggable hook.

- **Current signature (ground truth):**
  `ExperimentFn = Callable[[Spec, Path], Sequence[EvidenceItem]]`
  (`compiler.py:44`), invoked at `compiler.py:121-123` as
  `experiment(spec, self.workspace_dir)`.
- **What it knows:** the frozen `Spec` and a workspace `Path`. It returns
  append-only `EvidenceItem`s (`evidence.py:221-261`), each carrying `Provenance`
  (E3, `evidence.py:93-117`) and `bears_on` bearings (E4).
- **What it does NOT know:** how the Evidence will be judged, what the
  `DecisionRule` is, or anything about belief. It is a pure record producer: Spec
  in, Evidence out.
- **Recommendation:** keep `ExperimentFn` exactly as the Experiment interface. The
  only change is **who supplies it** — today `cli.py:18,52` hard-codes
  `t1_molecular_experiment`; under the adapter seam (§3) the adapter *serves* the
  `ExperimentFn`. The signature is unchanged.

Note an important property: an `ExperimentFn` is the seam where both kinds of work
meet. The *authoring* of the function body is agent-driven (in-session, a
checkpoint); the *execution* (Docker run, capturing `Result` fields) is the
deterministic spine (`docker_executor.py`, `experiment_runner.py:51-88`). The
interface does not distinguish them — it only sees Spec → Evidence — which is
exactly why it generalizes.

### 2.3 Interface C — Judge (proposes a verdict; never the source of truth)

The judge supplies a *candidate* verdict for the non-numeric kinds the verifier
cannot reduce to a formula. It already exists as a Protocol + an injection point.

- **Current signature (ground truth):** the `Judge` Protocol (`judge.py:52-76`):
  - `judge_qualitative(criterion, finding, params) -> JudgeVerdict`
  - `judge_proof(criterion, finding, artifact_ref, evidence_kinds, params) -> JudgeVerdict`
  - `JudgeVerdict = direction + level + basis + counterexample` (`judge.py:32-49`).
- **Injection points (ground truth):** `ResearchCompiler(judge=…)`
  (`compiler.py:86-92`) → `ClaimUpdater(spec, …, judge=…)` (`claim_updater.py:62-84`)
  → `DecisionEngine(judge=…)` (`decision_engine.py:179-189`). When `judge is None`,
  proof/qualitative return `inconclusive` and are surfaced as `Checkpoint`s instead
  (`compiler.py:131,141-142`; `claim_updater.py:73-77`).
- **What the judge knows:** only the rule's **own prose criterion**
  (`rule.expression`) — never a global rubric (D1, `judge.py:62-63`). It reports
  what it found.
- **What the judge does NOT decide:** the binding verdict. The engine bounds the
  judge: a confident `proof` "verified" does NOT become `supports` — the engine
  forces a human spot-check first (`decision_engine.py:493-506`); a counterexample
  refutes decisively regardless of the judge's direction (`decision_engine.py:466-472,
  487-492`); a low-confidence qualitative judgment escalates to a human
  (`decision_engine.py:526-530`). **This is the "no self-certification" guarantee
  encoded in the kernel.**
- **Recommendation:** keep the `Judge` Protocol as Interface C. The chief-over-N
  pattern (Step-3 §3.1 (C)) is realized **inside** a concrete `Judge`
  implementation — the engine still sees one injected `Judge` (§5.3). The frozen
  rubric R lives in `rule.expression`/`rule.params` and reaches the judge unchanged
  through `criterion`/`params` — **no kernel change is needed to thread R** (this is
  a genuinely clean fit; see §5.3).
- **Engine gate (F2 decision):** a non-numeric verdict is accepted only if it arrives
  with a well-formed provenance trail (`verdicts/<hyp-id>.json`: N raw judge outputs +
  the applied R + the chief's reasoning, §4.4). The engine refuses a verdict lacking
  the trail — an extension of the existing self-certification block
  (`decision_engine.py:493-530`). The check is *structural* (presence + required
  fields), never the combination policy, so the kernel still does not know `N` or how
  the chief aggregates — the seam holds.

### 2.4 What is IN the kernel vs OUT

| In the kernel (trustworthy, deterministic where possible) | Out of the kernel (borrowed via the adapter) |
|---|---|
| `core/` types: Spec / Evidence / Claim + invariants (`spec.py`, `evidence.py`, `claim.py`) | Writing experiment code (the body of an `ExperimentFn`) |
| `ProposalParser` (text → Spec) | Generating candidate verdicts (`JudgeVerdict` content) |
| `DecisionEngine` (Interface A — the verifier) | Writing paper prose |
| `ClaimUpdater` (record-keeping + non-monotone updates) | Literature retrieval (which papers, what they say) |
| `ResearchCompiler` (orchestration of the above) | Any decision that requires intelligence |
| `Checkpoint` + the injection points (the rails) | — |
| Provenance, replay, LaTeX/citation emission (deterministic spine) | — |
| The frozen `DecisionRule` and its application (the verdict) | — |

**Render-spine scope (the "moved line", 2026-06-22, design/render-architecture-reframe.md):**
the "LaTeX/citation emission (deterministic spine)" row above is scoped to the
RECORD-FIDELITY essentials — the SI record dump, figures drawn from the record, the
bibliography wiring, and the `\evval`/`\status` fact substitution + a fidelity gate. The
main paper's NARRATIVE, title, and section structure are the agent's ("Writing paper prose"
is OUT, above); the spine no longer assembles them. A paper's measured numbers and verdicts
stay record-faithful by construction because they are written as `\evval`/`\status` markup
that the engine substitutes from the record at render time (FAIL-LOUD), so "no LLM in the
verdict path" holds while the narrative moves to the agent.

**The kernel must never:** import from the adapter; embed domain content; know that
the capability is Claude Code; or autonomously call an LLM (Step-3 §7). It depends
only on Interfaces A/B/C. This one-way dependency (`adapter → kernel` only, never the
reverse) is enforced by an actual lint/CI check, not just convention (F4, §8). Today
the *only* violations of this are (i) `cli.py:18`
hard-importing `t1_molecular_experiment`, and (ii) the lazy import of the T-1 Docker
runner inside `compiler.py:213` (`t1_molecular_experiment._run`). §3 removes both.

**Conflict noted honestly:** `t1_molecular_experiment` currently *lives in*
`compiler.py:204-218` — kernel code. That is a kernel/adapter leak: a T-1-specific
(domain) helper sitting in the orchestrator module. The clean design moves all such
built-in experiment factories *out* of `compiler.py` into the adapter layer (§3.3).
The `ExperimentFn` *type* stays in the kernel; the *T-1 instance* does not.

---

## 3. The capability-adapter seam (OQ-7, CENTRAL)

### 3.1 Where Claude-Code-ness lives

All Claude-Code-specific behavior is isolated behind **one capability adapter**.
The kernel depends on Interfaces A/B/C; the adapter *provides* B and C (and the raw
material for prose/literature). The adapter is the single place that knows "the
capability is the in-session Claude agent (+ subagents)."

The adapter is **not** a Python class that calls an LLM — that would violate the
in-session-only rule (Step-3 §7: sci-adk's Python never calls an LLM). It is a
**registry + protocol boundary**:

- For **Interface B (Experiment):** the adapter is a *registry of `ExperimentFn`
  providers*, keyed by a selector the Spec carries (§3.2). The in-session agent
  authors an experiment (at a checkpoint), the adapter records/serves it as an
  `ExperimentFn`, and the kernel runs it. The Docker execution inside is
  deterministic spine.
- For **Interface C (Judge):** the adapter supplies the concrete `Judge`
  implementation. Because sci-adk's Python may not call an LLM, the "live" judge is
  not an API client — it is a **boundary the in-session agent fills**: the agent
  produces `JudgeVerdict` content in-session and it is injected via the existing
  `judge=` path (§5). The adapter's job is to define *how* the in-session verdict
  becomes a `Judge` object the engine can call (the recommended shape: a
  `RecordedJudge` that reads agent-written verdict files — §5.2). `ClaudeJudge`
  today is a deliberate placeholder that raises (`judge.py:79-107`) precisely
  because the live invocation mechanism was left to this step.

### 3.2 How a per-domain capability plugin registers an experiment

The central generalization question: an *arbitrary-domain* proposal must select and
author its experiment without the kernel knowing the domain.

**Decided mechanism (F3) — a runtime selector + an adapter registry:**

1. A **runtime selector** (a `--capability` flag, or an adapter default) names a
   **capability id** (e.g. `"python-docker"`, `"lean4"`, `"agent-authored"`). It is
   resolved *outside* the frozen Spec — capability is HOW, not WHAT (F3). `MethodPlan.tools`
   (`spec.py:229-251`) may echo it only as an optional, non-binding *intent* marker.
2. A **capability registry** (in the adapter layer, e.g. `sci_adk/adapter/`, fork F4)
   maps a capability id → an `ExperimentFn` provider. A per-domain plugin registers
   itself under its id.
3. The compiler asks the adapter for the `ExperimentFn` for the selected capability,
   then runs it through the unchanged Interface B. If the selector is
   "agent-authored," the provider wraps an agent checkpoint that writes an experiment
   script + returns its Evidence (deterministic execution of agent-authored code).
4. **Every attempt is recorded (F3 strengthening, anti method-shopping).** The
   capability actually used is written to `EvidenceItem.provenance` (E3), and *each*
   attempt — every capability tried, including ones whose results were unwanted — is
   its own append-only `EvidenceItem`. Because the Evidence log is append-only (E1) and
   null/negative results are first-class (E2), the full set of attempts stays visible:
   "method shopping" (cherry-picking the capability that gave the desired answer) is
   structurally prevented, not merely discouraged.

The kernel sees only `experiment: ExperimentFn` (`compiler.py:99`). It never sees the
registry, the selector resolution, the domain, or how many capabilities were tried.
The registry lives entirely in the adapter.

### 3.3 Replacing the hard-coded T-1 import

Concretely, the two leaks identified in §2.4 are removed like this:

- **Move** `t1_molecular_experiment` (`compiler.py:204-218`) out of `compiler.py`
  into the adapter layer as the **first registered capability plugin** (the
  `"python-docker"` / T-1 provider). The kernel `compiler.py` stops importing any
  domain experiment.
- **Change** `cli.py:18` from `from sci_adk.loop.compiler import …,
  t1_molecular_experiment` to resolving the experiment through the adapter registry
  given the Spec's selector (or an explicit `--capability` flag, §7). The
  `--t1-molecules` flag (`cli.py:33-37,49-52`) becomes one capability's options,
  not a hard-wired compiler concept.

**Swappability test (the design goal):** swapping the capability — e.g. from
Claude-authored Python experiments to a future different authoring backend — touches
*only* the adapter registry and the concrete `Judge`. The kernel
(`core/`, `decision_engine.py`, `claim_updater.py`, `compiler.py` orchestration,
`render/`) is untouched. If a proposed change to support a new domain forces a
kernel edit, the seam has been violated — that is the review tripwire for Step 1.

### 3.4 Honest limit of the seam

The seam isolates Claude-Code-ness *at the boundary*, but it does **not** make the
verdicts domain-free: the *content* of an agent-authored `ExperimentFn` and of a
`JudgeVerdict` is inescapably domain- and capability-specific. The claim is narrower
and true: the **kernel's code** never depends on the domain or the capability; all
that dependence is pushed into adapter-served data/functions. This is the most the
seam can deliver, and it is enough to preserve the future-external option
(Step-3 §2.1a) — a different capability can be plugged in without rewriting the
rigor kernel.

---

## 4. Checkpoint & verdict representation (OQ-1 / OQ-2)

### 4.1 The current on-disk reality (ground truth)

`Glob runs/t1-demo/**/*` returns exactly:

```
runs/t1-demo/spec.json                       # Spec, JSON (compiler.py:183-187)
runs/t1-demo/evidence/<evi-id>.json          # EvidenceItem, JSON (experiment_runner.py:159-165)
runs/t1-demo/claims/claim-<hyp-id>.json      # Claim, JSON (claim_updater.py:338-344)
runs/t1-demo/paper/draft.md                  # rendered draft (compiler.py:137-139)
runs/t1-demo/checkpoints.md                  # checkpoints, MARKDOWN (compiler.py:190-201)
```

So today: the three core types are **typed JSON** (round-trippable via
`model_validate` / `model_dump(mode="json")`), but the checkpoint is **human-prose
Markdown** (`checkpoints.md`, read at `runs/t1-demo/checkpoints.md:1-12`) with no
machine-readable verdict slot at all. The verdict, once an agent resolves a
checkpoint, has **nowhere typed to live** — it is implicit in the recompiled Claim's
`confidence.basis`.

### 4.2 The problem with the status quo for OQ-1

`checkpoints.md` is fine as a *human-facing prompt* but cannot serve as the
**contract** for replay/provenance (E3) or for the multi-judge case, because:

- It is not parseable back into a structured input — a replay (OQ-9 headless) cannot
  re-derive the verdict from it deterministically.
- It has no place for **N independent verdicts + the chief's R-grounded
  adjudication** (Step-3 §3.1 (C)). N judge subagents each emit a verdict + reasoning;
  the chief applies frozen R and names the decisive reasoning. None of that survives
  in a prose bullet list.
- A verdict that moves a Claim is *Evidence-grade provenance* (E3 demands enough to
  reproduce); a prose note does not meet that bar.

### 4.3 Recommended on-disk form — typed JSON checkpoints + verdicts, Markdown as a *view*

**Recommendation:** introduce typed JSON for both the checkpoint and its resolved
verdict, and keep the Markdown as a generated human-facing *view* (not the contract).

Proposed `runs/<id>/` layout (additions in **bold**; existing unchanged):

```
runs/<id>/
  spec.json                         # unchanged (kernel record)
  evidence/<evi-id>.json            # unchanged (append-only record)
  claims/claim-<hyp-id>.json        # unchanged (revisable belief)
  paper/draft.md                    # unchanged (deterministic render)
  checkpoints.md                    # KEEP as a generated human view (prompt)
  checkpoints/<hyp-id>.json         # NEW: typed Checkpoint (the contract)
  verdicts/<hyp-id>.json            # NEW: typed resolved verdict (+ N + chief)
  artifacts/                        # NEW: agent-authored artifacts (§4.5)
    experiments/<hyp-id>.py         #   experiment code the agent authored
    prose/<section>.md              #   agent-written prose over the skeleton
    literature/<ref-id>.json        #   acquired references (DOI + BibTeX)
```

Why JSON, matching the existing convention: the core types already persist as JSON
via Pydantic (`compiler.py:185`, `experiment_runner.py:165`, `claim_updater.py:344`);
a typed `Checkpoint`/verdict JSON is *consistent with the kernel's own record format*
and is round-trippable for replay. `checkpoints.md` is then rendered *from*
`checkpoints/*.json` (the inverse of today, where the prose is primary).

### 4.4 The multi-judge verdict shape (the chief-over-N case)

A resolved `verdicts/<hyp-id>.json` **MUST** carry the following — this trail is
mandatory; the engine refuses a non-numeric verdict that lacks it (§2.3, F2):

- `hypothesis_id`, `rule_kind` (`proof`|`qualitative`), and the **frozen rubric R**
  reference (`rule.expression` + `rule.params`, copied for replay so the verdict is
  self-contained against the Spec version it judged).
- `panel`: a list of N independent `JudgeVerdict`-shaped entries (each: `direction`,
  `level`, `basis`, `counterexample`) — these are the genuinely independent subagent
  opinions (Step-3 §3.1 (C)).
- `chief`: the single adjudication — `direction`, `level`, `basis` — where `basis`
  **states which panel reasoning is decisive under R** (the chief has no free
  discretion; Step-3 §3.1 (C)). This is the `JudgeVerdict` actually returned to the
  engine.
- provenance: spec version, timestamp, and (if subagents fanned out) per-verdict
  cost/agent ids, satisfying E3.

This is recorded provenance, not belief — it is the audit of *how* the verdict was
reached, parallel to how `EvidenceItem.provenance` audits an experiment. The Claim
itself still carries only the chief's verdict in its `confidence` (the binding
belief), with the `verdicts/<hyp-id>.json` as the linked provenance.

### 4.5 Where agent-driven artifacts live (OQ-2)

**Recommendation:** a single `runs/<id>/artifacts/` tree, sub-divided by kind
(`experiments/`, `prose/`, `literature/`). Rationale:

- It keeps the **kernel record** (`spec.json`/`evidence/`/`claims/`/`paper/`) clean
  and unchanged — those are produced by the kernel and must stay the authoritative
  record.
- Agent-authored material is *input to* or *decoration of* the record, not the
  record itself, so it sits in a sibling tree. Experiment code that produced
  Evidence is referenced from `EvidenceItem.provenance.code_ref`
  (`evidence.py:113`) — so `artifacts/experiments/<hyp-id>.py` is pointed-to by the
  Evidence it generated, closing the E3 reproducibility loop.
- Prose lives in `artifacts/prose/` and is merged into `paper/draft.md` by a
  deterministic render step (the renderer already accepts the skeleton;
  `paper.py:38-56`), so the agent's prose never silently *becomes* the record
  without passing through the deterministic renderer.

---

## 5. The turnkey loop (OQ-3)

### 5.1 The mechanism that exists vs the gap

The injection points are real and complete (§2.3). What is missing is a **single
turnkey helper** that: (1) runs an initial compile, (2) surfaces checkpoints, (3)
accepts agent-resolved verdicts, (4) recompiles with the injected judge, (5) is
idempotent on re-run. Today a caller must wire `ResearchCompiler(judge=…)` by hand
and there is no persisted verdict to re-enter (§4.1).

### 5.2 Recommended loop shape

A thin orchestration helper (kernel-side, no LLM) — call it conceptually the
**checkpoint loop** — with this shape, all grounded in current signatures:

1. **Compile** `ResearchCompiler(workspace_dir).compile(proposal, experiment=fn)`
   (`compiler.py:94-151`). If `result.needs_agent` is False (numeric-only path), the
   loop is **done in one pass** — no judge needed (this is the §4.2-first / exact-
   verifier case from Step-3 §5).
2. **Surface** the typed `checkpoints/<hyp-id>.json` (§4.3) + the human view
   `checkpoints.md`. The in-session agent reads them.
3. **Resolve** (agent-driven, in-session): the agent (optionally fanning out to N
   judge subagents + a chief, §5.3) writes `verdicts/<hyp-id>.json` (§4.4). This is
   the only intelligence step; sci-adk's Python does not call an LLM here.
4. **Re-enter** (deterministic): the loop constructs a `RecordedJudge` — a concrete
   `Judge` (`judge.py:52-76`) whose `judge_qualitative`/`judge_proof` read the
   chief verdict from `verdicts/<hyp-id>.json` — and recompiles
   `ResearchCompiler(workspace_dir, judge=RecordedJudge(run_dir)).compile(proposal,
   experiment=fn)`. The engine applies the frozen rule to the recorded verdict
   (`decision_engine.py:508-533`), the `ClaimUpdater` moves the Claim non-monotonically
   (`claim_updater.py:245-280`), and the paper re-renders.
5. **Stop** when no checkpoint remains unresolved, or the human spot-check that the
   engine demands for `proof` (`decision_engine.py:496-502`) is itself surfaced as a
   checkpoint and resolved.

**Entry point recommendation:** a single function/class in `sci_adk/loop/` (e.g.
`run_checkpoint_loop(proposal, run_dir, experiment, capability)`), plus a matching
CLI verb (§7). It does not replace `ResearchCompiler` — it *drives* it across the
agent boundary.

### 5.3 Threading the frozen rubric R + persisting N verdicts (clean fit)

The chief-over-N pattern (Step-3 §3.1 (C)) composes with the existing mechanism with
**no kernel change**, which is a genuinely clean result worth stating:

- The frozen rubric R is already in `rule.expression` (+ `rule.params`) and is
  passed to the judge verbatim as `criterion`/`params` (`judge.py:62`,
  `decision_engine.py:524-525`). The chief applies R because R *is* the criterion the
  judge receives. No new threading is required at the engine interface.
- N independence comes from subagent context isolation (the in-session agent fans out
  to N judge subagents; `tool-policy.md:42-44` allows it). The N verdicts + chief are
  persisted in `verdicts/<hyp-id>.json` (§4.4).
- The engine still sees **one** injected `Judge` (`RecordedJudge`) whose *internal*
  shape is chief-over-N (Step-3 §3.1, last paragraph). So chief-over-N is an adapter-
  side concern; the kernel is unaware of `N`.

**One honest tension to flag (not a blocker):** the engine's `proof` override forces
a human spot-check even after a confident "verified" (`decision_engine.py:493-506`).
Under chief-over-N, the "confident verified" is the *chief's* verdict. So a `proof`
loop has *two* agent-resolved gates: the chief's verdict, then the human spot-check
checkpoint the engine raises. This is correct (it preserves anti-self-certification)
but means the turnkey loop must handle a checkpoint that the *engine* generates on
recompile, not only the ones from the initial compile. The loop in §5.2 step 5
accounts for this; Step 1 must implement it as a fixpoint (recompile until no new
checkpoint appears), not a single pass.

### 5.4 Idempotency

Re-running the loop on an already-resolved run must not duplicate or corrupt the
record:

- **Evidence** is append-only (E1) — a naive re-run that re-executes the experiment
  would append a *new* `EvidenceItem`. The loop must therefore **not** re-run the
  experiment if Evidence for this Spec version already exists (recommendation:
  experiment execution is keyed by Spec version + capability; re-running reuses
  existing Evidence unless `--force`). **Decided (F5):** `--force` does not overwrite —
  it *appends* a new `EvidenceItem` (E1 preserved). This reuse-default assumes
  *deterministic* experiments; a probabilistic capability would hide run-to-run variance
  and must later shift to "append every run" or carry a determinism marker (§8 F5).
- **Claims** are load-or-create (`claim_updater.py:179-182, 230-243`): re-evaluation
  over the same Evidence yields the same verdict (D5 determinism,
  `decision_engine.py:160-163`) and appends **no** spurious `StatusChange` when the
  status is stable (`claim_updater.py:267-272`). So Claim recompute is already
  idempotent — confirmed in code.
- **Verdicts** are read from `verdicts/<hyp-id>.json` by `RecordedJudge`, so a
  recompile with no new agent input reproduces the same Claim. Idempotent by
  construction.

---

## 6. Execution modes (OQ-9, restated against the interfaces)

OQ-9 is resolved in Step 3; here is how the two modes realize against §2's interfaces.

### 6.1 In-session mode (full capability, with fan-out)

- Driven by the in-session Claude agent, which MAY fan out to subagents
  (`tool-policy.md:42-44`).
- All three interfaces are live: **Experiment** authored by the agent + run on the
  deterministic spine; **Judge** filled by the agent (chief-over-N); **Verifier**
  applies frozen rules. This is the §5 turnkey loop in full.
- Numeric checkpoints still resolve autonomously and free (no agent needed for
  `threshold`/`bayesian`/`interval`).

### 6.2 Headless mode (deterministic spine only — replay + re-verify)

- **No LLM, no capability.** Headless mode runs *only* the kernel's deterministic
  parts: re-parse the Spec, replay recorded Evidence, re-apply the frozen numeric
  `DecisionRule`s, re-derive Claims, re-render the paper.
- Realized against the interfaces by **omitting B's authoring and C entirely**:
  - Experiment: not re-authored; existing `evidence/*.json` is replayed (read back
    via `EvidenceItem.model_validate`). No `ExperimentFn` is invoked unless re-running
    is explicitly requested (and even then only deterministic execution, never
    agent-authoring).
  - Judge: there are two headless sub-modes, both LLM-free, split by whether a
    recorded verdict trail exists:
    - **Fresh headless compile (no trails): `judge=None`.** With no
      `verdicts/*.json` yet, proof/qualitative return `inconclusive` and surface as
      checkpoints (`decision_engine.py:473-478, 517-522`) — headless **cannot
      author** a non-numeric verdict, only *report* the open checkpoint.
    - **Re-verification of a resolved run (`sci-adk verify`): inject
      `RecordedJudge(run_dir)`.** This was written before `RecordedJudge` existed.
      Once the in-session agent has authored `verdicts/<hyp-id>.json`, the headless
      audit injects a `RecordedJudge` (kernel-side, deterministic, pure JSON
      deserialization — **still no LLM, no capability**, `recorded_judge.py`). The
      engine re-reads the recorded chief-over-N trail and re-applies the frozen rule
      **plus the F2 trail gate**, so **non-numeric belief IS audited**, not merely
      reported as open. A non-numeric hypothesis whose trail is **absent** still
      yields `inconclusive` (F2) and is reported as unresolved / not reproducible
      from the record. The seam holds: the kernel re-reads the trail, it never
      re-judges.
  - Verifier: fully live (it never needed an LLM).
- **Use:** CI-style re-verification that a recorded run still holds under its frozen
  rules — **numeric** belief by autonomous re-evaluation, **non-numeric** belief by
  re-reading the recorded verdict trails via `RecordedJudge` (`sci-adk verify`,
  §7.1, F6) — plus provenance/reproducibility audits (a record digest over
  spec + evidence + verdict trails). It is the re-runnable proof that the *record*
  and the *belief derived from it* are reproducible without any intelligence in the
  loop — so a third party can audit the verdicts without Claude Code.

This makes the in-session vs headless split fall exactly on the A/B/C boundary: A is
always available; B-execution is available headless but B-authoring is not; C is
in-session only.

---

## 7. Command surface (OQ-6) + S5 surfacing (OQ-8) — brief

### 7.1 Command surface (OQ-6) — recommended position

Today the surface is one verb: `sci-adk run <proposal>` (`cli.py:21-38`). Step-3's
inversion names three phase-verbs: propose → experiment → compile.

**Recommendation (lean): extend `sci-adk run`, do not build three separate
commands yet.** Keep `run` as the end-to-end compile (it already does parse → optional
experiment → claims → render). Add:

- `--capability <id>` to select the adapter-served experiment (replacing the
  hard-wired `--t1-molecules`, which becomes that capability's option, §3.3).
- A new `sci-adk resolve <run-dir>` verb that runs the §5 turnkey checkpoint loop
  (surface checkpoints → accept verdicts → recompile). This is the one genuinely new
  command, because the checkpoint→judge→recompile loop is new behavior.
- A `sci-adk verify <run-dir>` verb for §6.2: it re-applies the frozen criteria to the
  *recorded* Evidence (NOT a re-run), with **no capability and no LLM** — so a third
  party can audit the verdicts without Claude Code (F6, §8).

Three full propose/experiment/compile commands are **deferred** — they would
formalize phase boundaries the single `run` already crosses internally, adding
surface without new capability (resist speculative abstraction, kernel §1). Revisit
only if multi-session use shows the phases need independent re-entry. This is fork
F6 (§8) — lean-extend vs three-verb — because it is a real ergonomics choice.

### 7.2 S5 human-checkpoint surfacing (OQ-8) — one paragraph

Spec amendment is the single carve-out from autonomy (S5, `spec.py:373-416`;
`abstractions.md:125-128`): even in autonomous mode, bumping a frozen Spec to
`version+1` requires a human checkpoint, never a subagent. In the in-session model,
the shell surfaces this exactly like a judgment checkpoint but with a **hard gate**:
when the agent (or the loop) determines the Spec must change (e.g. a `DecisionRule`
is unsatisfiable as written), it MUST NOT call `Spec.amend(...)` itself — it writes
an *amendment-request* checkpoint (a new `checkpoints/<spec>.amend.json` kind) and
stops. The human reviews and explicitly approves; only then is `Spec.amend(...,
rationale=…)` invoked (it already requires a non-empty rationale,
`spec.py:402-403`), producing `version+1` with the prior version retained (S1). The
distinction from a judge checkpoint: a judge checkpoint may be resolved by a subagent;
an S5 amendment checkpoint may **only** be resolved by a human (the orchestrator's
`AskUserQuestion`, never a subagent). Step 1 must enforce that asymmetry in the loop.
**Decided (F7):** the human amendment is itself transparent — it logs `version +
rationale` (`spec.py:402-403` already requires a non-empty rationale) and preserves the
prior Spec + its Evidence, so even a human criteria change stays in the record, never
silent (anti-HARKing extends to human amendments).

---

## 8. Decision-forks for the user (the AGREE step)

These are the genuine choices where your input changes the Step-1 build. Each gives
the fork, my recommendation, and the tradeoff. Forks F1–F3 are High (they shape the
kernel/seam); F4–F7 are Medium/Low.

**F1 — Checkpoint/verdict on-disk form. DECIDED (2026-06-16): typed JSON, Markdown as a
view.**
- Decision: **typed `checkpoints/*.json` + `verdicts/*.json`** are the contract;
  `checkpoints.md` is demoted to a generated human view (§4.3). Rationale: JSON is
  replayable (E3), holds the N-verdicts + chief shape (§4.4), and matches the existing
  core-type JSON convention.

**F2 — Where the chief-over-N lives. DECIDED (2026-06-16): adapter-side `RecordedJudge`,
NOT a kernel panel.**
- Decision: chief-over-N is adapter-side, inside a `RecordedJudge`; the kernel stays
  unaware of `N` and of the combination policy (§5.3). The engine keeps seeing one
  `Judge`.
- **Strengthening (decided):** the verdict provenance trail is *mandatory and
  schematized*. `verdicts/<hyp-id>.json` MUST carry [the N judges' raw outputs + the
  applied rubric R + the chief's N→verdict reasoning] (§4.4). The engine **refuses to
  accept** a non-numeric verdict that lacks a well-formed trail — layered on the
  existing self-certification block (§2.3). The engine's check is *structural* (trail
  present + required fields), never the combination policy — so the kernel still does
  not know `N` or how the chief aggregates; the seam holds.

**F3 — Experiment selection mechanism. DECIDED (2026-06-16): runtime selector +
provenance, NOT a frozen Spec field.**
- Decision: capability is a **runtime selector** (`--capability` flag / adapter
  default), resolved *outside* the frozen Spec. The frozen contract stays pure
  (question + DecisionRule); capability is HOW, not WHAT. `MethodPlan.tools`
  (`spec.py:229-251`) may echo it only as an optional, non-binding *intent* marker. A
  dedicated frozen `capability` field was rejected as a category error (freezing a
  runtime concern into the anti-HARKing contract).
- **Strengthening (decided):** the capability(ies) actually used are recorded in
  Evidence provenance (E3) — and not only the resolved one: **every attempt** is its
  own append-only `EvidenceItem`. Because the Evidence log is append-only (E1) and
  null/negative results are first-class (E2), recording all attempts **structurally
  blocks "method shopping"** (trying capabilities until one yields the wanted result,
  then reporting only that). The full set of attempts stays visible in the record.

**F4 — Adapter package location. DECIDED (2026-06-16): separate `sci_adk/adapter/`
package.**
- Decision: the adapter is its own package, NOT folded into `sci_adk/loop/`.
- **Strengthening (decided):** the seam is enforced by an *actual* lint/CI check — **a
  kernel module importing the adapter fails the build**. The dependency direction is
  one-way: `adapter → kernel` is allowed, `kernel → adapter` is forbidden. (The check
  itself is a Step-1 build item, §9.) This turns "the kernel must not import the adapter"
  from a convention into an enforced invariant.

**F5 — Re-run idempotency policy. DECIDED (2026-06-16): reuse Evidence, re-run only on
`--force`.**
- Decision: a re-run of the same `(Spec version + capability)` reuses existing
  `evidence/*.json`; re-execution happens only on explicit `--force` (§5.4). Keeps the
  loop idempotent and the append-only log honest. (Distinct from F3: a *different*
  capability is a new attempt recorded as new Evidence — F5 governs only identical
  re-runs.)
- **Strengthening (decided):** `--force` does **not overwrite** — it **appends** a new
  `EvidenceItem` (E1 append-only preserved; the dispersion across runs becomes part of
  the record).
- **Honest limit (flagged):** "reuse by default" assumes **deterministic** experiments.
  For a *probabilistic* capability, reuse would hide run-to-run variance. The MVP
  (deterministic, T-1-class) is fine; once a capability is probabilistic the policy must
  shift to "append every run" or carry a determinism marker (future, not MVP).

**F6 — Command surface. DECIDED (2026-06-16): extend `run` + add `resolve`/`verify`.**
- Decision: keep/extend `sci-adk run` (`--capability`); add `resolve` (the §5
  checkpoint → judge → recompile loop) and `verify` (headless re-verification). Three
  full propose/experiment/compile verbs are deferred (§7.1).
- **Strengthening (decided):** `verify` works **without any capability** — it re-applies
  the frozen criteria to the *recorded* Evidence (it does NOT re-run the experiment).
  Deterministic, headless, no LLM → **a third party can audit the verdicts without
  Claude Code** (independent reproducibility of the belief from the record).

**F7 — S5 amendment checkpoint kind. DECIDED (2026-06-16): distinct human-only
`*.amend.json`.**
- Decision: Spec amendment is its own checkpoint kind (`checkpoints/<spec>.amend.json`),
  resolvable **only by a human** — not a judge checkpoint with a flag (§7.2). Makes
  "a subagent may never resolve this" structurally enforceable (the S5 carve-out).
- **Strengthening (decided):** human amendments are themselves **transparent** — the
  amendment logs `version + rationale` (S1 already requires a non-empty rationale) and
  **preserves the prior Spec and its Evidence**. So even when a *human* changes the
  criteria, the change is in the record, never silent — anti-HARKing extends to human
  amendments, not only agent ones.

---

## 9. Deferred to Step 1 / out of scope

Step 2 is architecture; the following are deliberately left to Step 1 (implementation)
or out of scope:

- **Exact JSON schemas** for `checkpoints/*.json` and `verdicts/*.json` (field types,
  required vs optional). §4 fixes the *shape and contents*; the precise Pydantic model
  is Step 1.
- **The `RecordedJudge` implementation** and the `run_checkpoint_loop` body — §5 fixes
  the *loop shape and re-entry points*; the code is Step 1.
- **The adapter registry implementation** and the migration of `t1_molecular_experiment`
  out of `compiler.py` — §3 fixes the *seam and mechanism*; the move is Step 1.
- **The first real problem is chosen WITH the user at Step-1 kickoff — NOT pre-selected
  here.** T-1 (genuine prime/Gödel encoding replacing the toy at
  `docker_executor.py:203-276`, with its exact injectivity verifier per §5) is a
  *candidate*, not a decision; the §4.2 DecisionRule↔statistic alignment follows the
  chosen problem. This is milestone-3 §4 work, executed in Step 1 on this agreed
  architecture.
- **The F4 lint/CI check** (`kernel → adapter` import fails the build) — the enforced
  seam invariant is specified in §3/§8 F4; adding the actual check is a Step-1 item.
- **Real provenance** (`provenance/__init__.py` is currently a 1-line empty module —
  confirmed by Read) and the LaTeX/BibTeX/DOI citation emission — finishing
  infrastructure, Step 1.
- **The live `ClaudeJudge` API/`claude -p` path** — explicitly NOT built: it is
  excluded by the in-session-only decision (Step-3 §7). The placeholder
  (`judge.py:79-107`) stays a guard that raises.
- **Generalization across ≥2 domains** (Step-3 §5) — validated in a later phase, after
  the first real T-1 cycle.

Out of scope entirely: any external product boundary (OQ-5 moot — self/lab harness);
any change to the excluded-tools policy (LSP/coverage/ast-grep stay excluded from the
research runtime, `tool-policy.md:60-74`); any rebuild of the working engine
(scope discipline, Step-3 §7).

---

## 10. References (path:line)

Design docs:
- Step-3 plan (identity, inversion, OQ-1..OQ-9, locked decisions):
  `design/sci-adk-productization-plan.md` (esp. §3.1, §3.1(C), §6 OQ list, §7).
- Record vs belief; Spec/Evidence/Claim invariants: `design/abstractions.md:15-48`
  (organizing principle), `:62-128` (Spec, S1/S3/S5), `:132-186` (Evidence, E1-E4),
  `:190-257` (Claim, C1/C5), `:280-292` (loop mapping), `:310-317` (no hardcoded metrics).
- Tool policy (allowed/excluded; subagent fan-out allowed): `design/tool-policy.md:6-20,
  24-74` (esp. `:42-44` Claude subagent allowed, `:60-74` exclusions).
- Two-environment separation: `.claude/rules/sci-adk-constitution.md`.

Code (measured this session):
- Verifier interface: `src/sci_adk/loop/decision_engine.py:67-87` (Verdict),
  `:90-109` (EvidenceForHypothesis), `:179-189` (judge injection), `:191-219`
  (evaluate dispatch), `:256-445` (numeric handlers), `:453-533` (proof/qualitative
  routing + overrides), `:144-176` (invariants D1-D8).
- Experiment interface: `src/sci_adk/loop/compiler.py:44` (`ExperimentFn`), `:94-151`
  (compile), `:121-123` (invocation), `:204-218` (`t1_molecular_experiment` — the
  domain leak to relocate); execution spine `src/sci_adk/runner/docker_executor.py`,
  `src/sci_adk/loop/experiment_runner.py:51-88`.
- Judge interface: `src/sci_adk/loop/judge.py:32-49` (JudgeVerdict), `:52-76` (Judge
  Protocol), `:79-107` (ClaudeJudge placeholder that raises).
- Checkpoint surface + injection chain: `src/sci_adk/loop/compiler.py:50-74`
  (Checkpoint/CompileResult), `:131,141-142,190-201` (collect/save checkpoints),
  `src/sci_adk/loop/claim_updater.py:62-84` (judge forwarding), `:179-280`
  (non-monotone load-or-create + update).
- Core types: `src/sci_adk/core/spec.py:94-133` (DecisionRule), `:178-201`
  (Hypothesis), `:286-416` (Spec + amend/S5); `src/sci_adk/core/evidence.py:93-117`
  (Provenance/E3), `:221-261` (EvidenceItem/E1); `src/sci_adk/core/claim.py:111-169`
  (Confidence/C3), `:221-329` (Claim/C1-C5, update_status).
- CLI surface + hard-coded T-1 import: `src/sci_adk/cli.py:18` (import), `:21-38`
  (parser), `:49-56` (experiment wiring).
- Renderer (deterministic skeleton): `src/sci_adk/render/paper.py:38-56`.
- Empty provenance module: `src/sci_adk/provenance/__init__.py` (1 line, empty).
- On-disk run artifacts: `Glob runs/t1-demo/**/*` (5 files: spec.json,
  evidence/<id>.json, claims/claim-hyp-001.json, paper/draft.md, checkpoints.md);
  `runs/t1-demo/checkpoints.md:1-12` (Markdown checkpoint, no verdict slot);
  `runs/t1-demo/claims/claim-hyp-001.json:6-12` (unjudged inconclusive state);
  `runs/t1-demo/evidence/<id>.json:6-32` (Evidence JSON with provenance + bears_on).

---

Version: 1.1 (AGREED — F1–F7 decided)
Source: Step 2 of the 3 → 2 → 1 rigor-ADK sequence (2026-06-16)
Last Updated: 2026-06-16
