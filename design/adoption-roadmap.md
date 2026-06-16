# sci-adk — External-System Adoption Roadmap

> Status: PLANNED (2026-06-17). A **staged** plan for which external research systems
> sci-adk adopts, when, and where — aligned to the rigor-ADK identity (*build the rigor
> kernel, borrow capabilities; referee, not player*). This is a **plan**, not execution:
> it fixes adoption *decisions, stages, and triggers* at the pattern/architecture level.
> Implementation detail is out of scope (that is Step 2 per item, when an item is triggered).
>
> **Authority:** this document is the **authoritative** source on *which specific external
> systems* sci-adk adopts and how. The Step-3 plan (`design/sci-adk-productization-plan.md`
> §2) speaks only generically of "borrowing external open tools"; where any plan text
> mentions specific adoption, this document governs.
>
> **Cross-references (grounding, checked against the files):**
> - Identity (referee≠player, build kernel / borrow capability, self/lab, external deferred):
>   `design/sci-adk-productization-plan.md` §2, §2.1a.
> - Chief-judge over N, frozen rubric R, "no k-of-n voting": plan §3.1 (C).
> - Constraints & non-goals — **agents propose, engine judges, no self-certification,
>   source of truth = engine**; one capability-adapter seam; in-session only; no hardcoded
>   metrics; S5 human checkpoint: plan §7.
> - record ≠ belief (append-only Evidence, non-monotone Claim, null is a result):
>   `design/abstractions.md:15-48, 132-186, 190-257`.
> - The built seam + the three kernel interfaces + headless verify (F3/F4/F6):
>   `design/rigor-shell-architecture.md` §2, §3, §6.2, §8.
>
> **Conflict check (per the discipline "flag before starting"):** none found. Every
> adoption below respects plan §7 — capabilities only *propose*; the engine renders the
> verdict by frozen criteria; anything that would put an LLM in the *verdict* path is
> cut (§5/C). Borrowed systems are *wrapped*, never reimplemented in the kernel.

---

## 1. The one litmus test that drives the 3-way split

Every external system is sorted by a single question, which is just plan §7 made operational:

> **Does it touch the verdict path** — the rendering of a Claim's belief from Evidence
> under the frozen `DecisionRule`?

- **Touches the verdict path → it cannot enter as-is.** The verdict path is the rigor
  kernel's heart and must stay deterministic / rule-based, with the engine as the sole
  source of truth (plan §7; `abstractions.md:280-292`). An external "LLM judges/ranks/scores"
  component is therefore **cut** from the verdict and may survive only as a *proposal* or
  *priority heuristic* on the capability side (§5/C).
- **Produces a proposal/artifact the engine then judges → borrow it** as a capability
  plugin behind the one adapter seam (§4/B): experiment code, candidate verdicts,
  literature, prose, figure critique. These never self-certify; they feed the engine.
- **Is part of the trustworthy spine itself → build it** in the kernel (§3/A): the
  verifier, the append-only record + exact replay, the plug-seam, the typed store, and the
  single substrate adapter that isolates all Claude-Code-ness.

This is why the same word ("tournament") can be both cut (as a verdict) and allowed (as a
capability-side ordering heuristic): the test is *where it sits relative to the verdict*,
not what it is.

A second, standing rule from plan §7: **borrowed ≠ reimplemented.** Every B/A-borrowed
system is wrapped as an adapter/plugin or adopted as a *pattern only* (LangGraph). The
kernel never grows a dependency on a borrowed system's internals.

---

## 2. The stage model

Stages are gated by *triggers*, not dates. Each stage names **what enters**, the **start
trigger**, and the **closed-when** criterion.

| Stage | Name | What enters | Start trigger | Closed-when |
|-------|------|-------------|---------------|-------------|
| **0** | First-cycle MVP (rigor spine) | A1–A5 (kernel: verifier, record+replay, plug-seam, typed store, substrate adapter) | none — this is the foundation | one real cycle runs end-to-end on a problem with a cheap *exact* verifier, and the seam is enforced | 
| **1** | Experiment-authoring scale | B1 (Sakana tree-search/experiment-manager → experiment-author plugin) | the experiment *search space* becomes the bottleneck (a single hand/agent-authored experiment is no longer enough) | the experiment-author plugin proposes/iterates experiments through the seam, recorded as Evidence, with no kernel change |
| **2** | Domain capability | B2 (PaperQA2 → literature), B3 (ether0 → chemistry), other FutureHouse domain tools | the **chosen first problem's domain** demands it (literature-heavy → PaperQA2; chemistry → ether0). *Depends on first-problem selection (out of scope, §6).* Usually **0 items** for an exact-verifier MVP | the domain plugin serves its capability behind the adapter; the kernel still sees only the three interfaces |
| **3** | Multi-cycle continuity | B4 (Kosmos-style structured world-model → cross-cycle consistency memory) | the system runs **multiple cycles** and needs consistency/memory *between* them | cross-cycle memory informs proposals without ever entering the verdict path |
| **4** | Paper-output assist | B5 (VLM figure-feedback → paper-writer aux) | the loop reaches the **result → paper** output stage | figure critique improves the rendered paper; deterministic render + citations remain the record |

**Standing dependency (outside this roadmap):** *choosing the first problem* is a
preceding step. It is **not** chosen here. It is the premise behind Stage 0 ("a cheap,
exact verifier" — plan §5) and the trigger source for Stage 2 (the domain). Treat it as a
placeholder dependency wherever a B item says "depends on first-problem selection."

---

## 3. A — Build now (rigor kernel / Stage 0 spine)

These are the trustworthy spine. They are **built in the kernel** (or, for the substrate,
isolated to one adapter), deterministically where possible (no LLM in the verdict path).

> **Status note:** Stage 0 is **substantially COMPLETE on `origin/master`** as of this
> session (commits cited per item). What remains in "A" is finishing infrastructure
> (render/citations — see §4/B5 boundary) and *validating* the general seam on a 2nd domain.

### A1 — Verifier interface + reproducible verification *(the kernel's heart)*
- **(a) Bring:** a deterministic verifier that checks Evidence against a frozen
  `DecisionRule` and renders the binding `Verdict`. Numeric kinds evaluate autonomously and
  free; non-numeric (proof/qualitative) route to an injected judge and are bound by the
  engine (no self-certify). First problem must have a **cheap, exact** verifier so the
  autonomous numeric path drives the loop (plan §5).
- **(b) NOT bring:** any LLM-as-verdict; any global success constant (no hardcoded metrics,
  plan §7 — the rule is per-Spec).
- **(c) Lives:** kernel — `loop/decision_engine.py` (`DecisionEngine.evaluate`), the judge
  rail (`loop/judge.py`, `loop/recorded_judge.py`), `loop/verify.py`.
- **(d) Stage/status:** Stage 0 — **DONE.** Numeric engine pre-existing; proof/qualitative
  judge rail + F2 trail gate (`dd333dc`); headless `sci-adk verify` re-derivation (`ab3a3bb`).

### A2 — Record + replay pattern *(LangGraph pattern only — no dependency)*
- **(a) Bring:** the *pattern* of typed state + checkpoints + time-travel/replay, realized
  as an **append-only Evidence record** (E1, monotone) + **exact deterministic replay**
  (`sci-adk verify` re-derives belief from the record with no LLM) + a **record digest**
  for tamper-evidence. Belief (Claim) is non-monotone and revisable over the record.
- **(b) NOT bring:** the LangGraph library/dependency, its persistence backend, or its
  graph-execution runtime. Pattern only (plan §7 "borrowed ≠ reimplemented").
- **(c) Lives:** kernel — `core/evidence.py` (append-only), `core/claim.py` (non-monotone),
  `loop/verify.py` + `provenance/record_digest` (replay + tamper-evidence),
  `loop/checkpoint_loop.py` (re-enter/recompile).
- **(d) Stage/status:** Stage 0 — **DONE.** Append-only Evidence pre-existing; replay audit
  + digest (`ab3a3bb`); turnkey checkpoint→judge→recompile loop (`dd333dc`).
- *Sources:* LangGraph persistence + checkpoints (pattern reference) — see §8.

### A3 — Plug-seam *(the standard socket — the central design body)*
- **(a) Bring:** the interface by which a domain experiment/verifier plugs into the kernel
  invariantly. The kernel knows only **three interfaces** — Verifier (`DecisionEngine`),
  Experiment (`ExperimentFn` hook), Judge (injected) — never domain content, never that the
  capability is Claude Code. A **capability registry + `--capability` selector** resolves the
  experiment at runtime; an **F4 lint** makes `kernel → adapter` imports a *build-failing*
  invariant (catches absolute *and* relative imports). The MVP socket is minimal (1 verifier
  + 1 experiment), but the **general contract** is the design body and the load-bearing
  enabler for all of §4/B.
- **(b) NOT bring:** multi-capability auto-attempt *orchestration* (no consumer yet — the
  append-only record + capability-in-provenance already block method-shopping structurally);
  a frozen `capability` field in the Spec (capability is HOW/runtime, not WHAT/frozen — F3).
- **(c) Lives:** the contract is kernel-side (the three interfaces); the registry + the T-1
  provider live in the adapter (`adapter/registry.py`, `adapter/t1_capability.py`); the F4
  lint is a test (`tests/test_kernel_adapter_seam.py`).
- **(d) Stage/status:** Stage 0 — **DONE** for the minimal seam + enforced invariant
  (`59578d8`). The **general** contract is *validated* only once a 2nd domain plugs in
  without a kernel edit (§6 — the generalization gate).

### A4 — Persistent typed store
- **(a) Bring:** typed Spec / Evidence / Claim persisted as JSON under `runs/<id>/`
  (round-trippable, replayable). Part of the A2 record pattern.
- **(b) NOT bring:** an external DB/state service; DVC-style heavyweight provenance beyond
  what replay needs.
- **(c) Lives:** kernel — `core/spec.py`, `core/evidence.py`, `core/claim.py`,
  `loop/verdict.py` (typed checkpoints/verdicts).
- **(d) Stage/status:** Stage 0 — **DONE** (pre-existing core types + typed checkpoint/verdict
  contract added with the judge rail `dd333dc`).

### A5 — Substrate: Claude Code in-session agent + subagents *(isolated to one adapter)*
- **(a) Bring:** the chosen intelligence substrate — the **in-session** Claude Code agent,
  which MAY fan out to Claude **subagents** (parallel experiments, independent judges). All
  Claude-Code-ness is isolated behind **one capability adapter**; the kernel never imports
  the adapter (F4-enforced).
- **(b) NOT bring:** autonomous Python LLM calls — **no Anthropic API, no `claude -p`** (plan
  §3.1, §7). The kernel must not *be* a capability; it borrows one.
- **(c) Lives:** `sci_adk/adapter/` (the one seam); the in-session-only rule is an identity
  invariant enforced socially + by the absence of any API/subprocess LLM call in kernel code.
- **(d) Stage/status:** Stage 0 — **DONE** (adapter package + F4 enforcement `59578d8`;
  in-session-only is a standing identity constraint).
- *Sources:* Claude Code / Agent SDK (subagents) — see §8.

---

## 4. B — Borrow later (capability plugins — staged + triggered)

Each is a **capability plugin behind the one adapter seam (A3)** — it *proposes/produces*;
the engine judges. None enters the verdict path. Each carries **what to borrow / which
stage / the trigger that starts it**.

### B1 — Sakana *AI-Scientist-v2* tree-search / experiment-manager → **experiment-author plugin**
- **(a) Borrow:** the agentic tree-search over experiment ideas + experiment-management loop,
  wrapped as an experiment-author capability that *proposes* and iterates `ExperimentFn`s.
- **(b) NOT borrow:** its LLM-reviewer-as-acceptance signal (that is a verdict-path component
  → governed by §5/C, replaced by the engine + chief-judge); its end-to-end "autonomy as
  truth" framing.
- **(c) Lives:** adapter plugin, served through the A3 seam as an `ExperimentFn` provider.
- **(d) Stage 1 / trigger:** the **experiment search space is the bottleneck** — a single
  hand- or agent-authored experiment no longer suffices. **Not needed for the first
  (simple-experiment) problem.**
- *Sources:* §8.

### B2 — FutureHouse *PaperQA2* → **literature domain plugin**
- **(a) Borrow:** high-recall literature QA/retrieval over a corpus, as a literature
  capability feeding Evidence (LITERATURE) + the prior-work decision record.
- **(b) NOT borrow:** any "PaperQA scores/ranks the claim" use — literature informs, it does
  not judge (verdict-path → §5/C).
- **(c) Lives:** adapter plugin; complements the existing paperforge acquisition + the
  Spec-time prior-work trigger.
- **(d) Stage 2 / trigger:** the **chosen first-problem domain is literature-heavy** and the
  current paperforge acquisition is insufficient. *Depends on first-problem selection (§6).*
  **Usually 0 for an exact-verifier MVP.**
- *Sources:* §8.

### B3 — FutureHouse *ether0* (chemistry 24B) → **chemistry domain plugin**
- **(a) Borrow:** the chemistry reasoning model as a domain capability proposing
  chemistry experiments/analyses.
- **(b) NOT borrow:** ether0 as an arbiter of correctness — the engine + the domain's exact
  verifier judge (verdict-path → §5/C).
- **(c) Lives:** adapter plugin behind the seam.
- **(d) Stage 2 / trigger:** **first problem's domain = chemistry.** Hard dependency on
  first-problem selection (§6); a non-chemistry first problem ⇒ this is never triggered.
- *Sources:* §8.

> *FutureHouse Phoenix and other FutureHouse tools fall in the same Stage-2 domain-plugin
> category and the same trigger (the chosen domain demands them); adopt per-domain on the
> same "propose, never judge" terms.*

### B4 — Kosmos-style structured **world-model** → **cross-cycle consistency memory**
- **(a) Borrow:** the *pattern* of a structured world-model that carries findings/consistency
  **across** research cycles, as a cross-cycle memory informing proposals.
- **(b) NOT borrow:** any role where the world-model *decides* a Claim; cross-cycle memory is
  context for proposing, never a verdict (verdict-path → §5/C). Reference for the *pattern*,
  not a dependency.
- **(c) Lives:** adapter/capability layer; reads the append-only record, never mutates a
  frozen Spec (S5) or a verdict.
- **(d) Stage 3 / trigger:** the system runs **multiple cycles** and needs continuity between
  them.
- *Sources:* §8.

### B5 — VLM **figure-feedback** → **paper-writer aux**
- **(a) Borrow:** a vision-language critique of generated figures, as an aid to the
  paper-writer rail.
- **(b) NOT borrow:** any use where figure critique alters Claims/Evidence — it polishes
  *output*, not belief.
- **(c) Lives:** adapter plugin at the render/paper stage; the deterministic renderer +
  citations remain the record.
- **(d) Stage 4 / trigger:** the loop reaches **result → paper output**. **Last** in the
  sequence.

---

## 5. C — Cut / absorb

### C1 — LLM **tournament / Elo as verdict** (Google Co-Scientist) → **CUT**
- **Why cut:** a tournament/Elo *ranking by an LLM* is an LLM sitting in the **verdict path**
  — the capability self-certifying its own output as the result. That violates plan §7
  ("agents propose, the engine judges; no self-certification; source of truth = the engine").
- **Replaced by:** the **chief-judge over N independent judges applying a frozen rubric R**
  (plan §3.1 (C)) — *not* k-of-n voting. N independent judge subagents propose; one chief
  applies the Spec-frozen R, names the decisive reasoning under R, and renders the single
  verdict the engine binds. The frozen R is what removes the post-hoc/HARKing vector a free
  tournament would reintroduce.
- **Allowed remnant (capability side only):** a tournament/ranking may survive as a
  **priority heuristic** — ordering *which hypotheses to verify first* — as an **optional,
  later** plugin (Stage 1+). It MUST NEVER touch a verdict; it only schedules work the engine
  will still judge by frozen criteria.
- **Absorb:** Co-Scientist's **reflection / meta-review** role is **absorbed into the
  chief-judge structure** — the chief's R-grounded adjudication *is* the meta-review,
  bounded by R (no free discretion).
- *Sources:* §8.

### General cut rule
Any external "LLM judges / ranks / scores the result" component is **cut from the verdict
path** by the §1 litmus test. It may be re-admitted **only** as a capability-side *proposal*
or *ordering heuristic*, never as the verdict. This is the standing filter for future
external systems not yet listed here.

---

## 6. Dependencies & sequencing

- **First-problem selection** (preceding, *out of scope* here) sets: the Stage-0 premise
  (a cheap exact verifier) and the Stage-2 domain triggers (B2/B3). Until it is chosen,
  Stage-2 items stay placeholders.
- **Stage 0 (A1–A5)** is the foundation and is **substantially done**; **A3 (the general
  plug-seam)** is the load-bearing enabler for every B plugin.
- **Generalization gate:** the general seam (A3) is only *proven* when a **2nd, different
  domain** plugs in with **no kernel edit** (plan §5 "≥2 different problems"). This gate
  precedes any claim of domain-generality and is the natural next milestone after Stage 0.
- **B ordering** follows the stages: B1 (experiment scale) → B2/B3 (domain, if triggered) →
  B4 (multi-cycle) → B5 (paper assist, last).

---

## 7. Identity-consistency summary (no conflict with the Step-3 plan)

| Adoption | Plan anchor it respects |
|----------|-------------------------|
| A (build kernel spine) | §2 (build the rigor kernel), §3 (inversion), §7 (one seam, no hardcoded metrics) |
| A5 substrate isolated to one adapter | §3.1, §7 (one capability-adapter seam; in-session only) |
| B (borrow as plugins, triggered) | §2.1 (borrow + wrap capabilities), §7 (borrowed ≠ reimplemented) |
| LangGraph pattern-only, Kosmos reference-only | §7 (no reimplementation; pattern/reference) |
| C cut tournament-as-verdict; chief-judge instead | §3.1 (C), §7 (engine judges; no self-certification) |
| tournament allowed only as priority heuristic | §7 (capabilities propose; never the verdict) |
| first-problem out of scope | plan §5 (premise), this roadmap §6 (dependency) |

---

## 8. References (external sources — user-provided, verified 2026-06)

**A — build now (pattern/substrate references):**
- LangGraph persistence (record+replay *pattern*):
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph checkpoints reference (snapshot/time-travel pattern):
  https://reference.langchain.com/python/langgraph/checkpoints
- Claude Code subagents (substrate):
  https://docs.claude.com/en/docs/agent-sdk/subagents
- Claude Code overview: https://docs.claude.com/en/docs/claude-code/overview
- Claude Agent SDK (Python): https://github.com/anthropics/claude-agent-sdk-python

**B — borrow later (capability plugins):**
- Sakana *AI-Scientist-v2* (tree-search / experiment-manager → experiment-author plugin):
  paper https://arxiv.org/abs/2504.08066 (v1 https://arxiv.org/abs/2408.06292);
  code https://github.com/SakanaAI/AI-Scientist-v2
- FutureHouse *PaperQA2* (literature plugin):
  code https://github.com/Future-House/paper-qa; paper https://arxiv.org/abs/2409.13740
- FutureHouse *ether0* (chemistry 24B plugin):
  code https://github.com/Future-House/ether0;
  weights https://huggingface.co/futurehouse/ether0; paper https://arxiv.org/abs/2506.17238
- *Kosmos* (structured world-model reference; FutureHouse/Edison):
  paper https://arxiv.org/abs/2511.02824

**C — cut / absorb:**
- Google *Co-Scientist* (tournament/Elo — verdict cut, reflection/meta-review absorbed):
  paper https://arxiv.org/abs/2502.18864;
  blog https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/

> External URLs are user-provided and marked verified (2026-06); they are cited as given,
> not independently re-fetched here. Internal `design/`-file cross-references were checked
> against the actual files (see the header grounding list).

---

Version: 1.0 (PLANNED)
Source: External-system adoption roadmap, aligned to the Step-3 rigor-ADK plan (2026-06-17)
Last Updated: 2026-06-17
