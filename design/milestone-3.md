# sci-adk Milestone-3 — From "pipeline works (toy)" to "actually usable"

> Status: PLANNED (2026-06-16). Roadmap for the next session(s). Milestone-2
> (DecisionEngine D0-D5) + the usable CLI compiler core are done and on `master`
> (commits c691732..f5dda82, pushed). This document is the next-session entry
> point: read it, then start at §4.

---

## 0. One-line framing

The **plumbing is real and correct** (proposal → parse → experiment → Evidence →
record/belief → Claim → paper draft, via `sci-adk run`), but the **intelligence
and finishing layers are still missing**. "Actually usable" means a researcher
gives a genuine four-pane proposal and gets a genuinely useful draft + *real*
experiments + honest, *judged* claims. Three things gate that: real experiments,
real judgment, and a real paper.

---

## 1. Where we are (measured 2026-06-16)

### Built and working (on master)
- `core/` types (Spec/Evidence/Claim) + invariants; `core/parser.py` (4-pane → Spec).
- `loop/decision_engine.py` — DecisionEngine D0-D5, all 5 rule kinds (see `design/decision-engine.md`).
- `loop/claim_updater.py` — non-monotone Claim updates; accepts an injectable `judge`.
- `loop/experiment_runner.py` + `runner/docker_executor.py` — Docker execution (T-1).
- `search/paperforge_adapter.py` + `loop/literature_acquirer.py` — OA-PDF acquisition + halt gates (see `design/literature-acquisition.md`).
- `loop/compiler.py` (`ResearchCompiler`) + `render/paper.py` + `cli.py` — the `sci-adk run` CLI.
- Full suite 333 tests green; Docker working; single `master` branch.

### Toy / stub / missing (the reason the output looks basic)
- **Experiment is a milestone-1 toy.** `execute_t1_molecule_encoding` (`runner/docker_executor.py`) multiplies a prime per recognized atom letter (`H2O→2×5=10`) and **ignores atom counts, bonds, and graph structure** — it does NOT implement the proposal's actual method. It demonstrates the pipeline, not science.
- **Claims are unjudged.** proof/qualitative rules route to a judge; with no judge they return `inconclusive` → `proposed`. The judgment (the intelligence) has not been applied.
- **render is a deterministic template** — structural Markdown skeleton, no LLM prose, no citations, no LaTeX.
- **`provenance/` is empty** (0 lines); only inline provenance (docker image, git commit) is captured.
- **Parser is crude** — assigns qualitative+exploratory by default; duplicates method text into "approaches"; `experiment_runner` bears only on `hypotheses[0]` (others get "no claim").
- **Rule ↔ statistic mismatch** — the canonical interval rule needs `Result.ci`, but the T-1 experiment emits `point`. Real runs need rules whose statistics the experiment actually produces.

---

## 2. Remaining work (tiered)

### Tier 1 — without these it is not "real" (the science loop)
1. **Real experiment execution / code generation.** From the proposal's MethodPlan,
   the agent writes a *real* experiment (e.g. the actual graph Gödel encoding with
   bonds/structure), runs it in Docker (`runner/` is general enough), and captures
   *real* statistics (`point`/`ci`/`posterior`). Replaces the T-1 toy. This is the
   "working code" pillar and the single biggest gap.
2. **Real judgment loop (turnkey).** The agent reads each proof/qualitative
   checkpoint (and, where needed, the acquired literature), judges it, injects the
   verdict via `ResearchCompiler(judge=...)`/`ClaimUpdater(judge=...)`, and
   recompiles so the Claim moves to `supported`/`refuted` with a real basis. The
   mechanism exists; the **checkpoint → judge → recompile loop is not yet a
   turnkey helper**.
3. **Meaningful DecisionRule ↔ statistic alignment.** Specs declare verifiable
   rules (threshold/interval/bayesian) whose statistics the experiment actually
   emits. Either improve the parser's rule inference or let the human/agent author
   rules; ensure the experiment produces the matching `Result` fields.

### Tier 2 — needed for a usable PAPER output
4. **LLM-assisted paper prose.** The agent writes abstract/intro/method/results/
   discussion from Claims + Evidence (over the deterministic skeleton from
   `render/paper.py`). In-session agent work, not autonomous LLM.
5. **Citations / bibliography.** Connect paperforge-acquired papers to the draft:
   a references section + BibTeX; cite acquired DOIs in the relevant sections.
6. **LaTeX / pandoc output + figures/tables.** Use the allowed LaTeX/BibTeX/pandoc
   toolchain; render Evidence into tables/figures.

### Tier 3 — reproducibility, robustness, ops
7. **`provenance/`** — Git/DVC integration, seed/env capture → reproducible runs.
8. **Parser robustness** — better hypothesis/rule extraction; multi-hypothesis
   bearings in `experiment_runner`; fix the "approaches" duplication.
9. **Ops** — error handling, partial-run resume, config, real logging (not prints),
   compiler tests over realistic scenarios.
10. **(Optional) iteration loop** — run → critique → refine for quality lift.

---

## 3. The agent-driven model (HARD constraint — do not violate)

sci-adk's LLM is **Claude Code, and only the already-running in-session agent** —
**not the Anthropic API, and not a `claude -p` subprocess** (every `claude -p` is
a new billed invocation). See `design/tool-policy.md` + the user's 2026-06-16
constraint.

Consequence for Milestone-3: the "intelligence" steps (writing experiment code,
judging proof/qualitative, writing paper prose) are performed by the **in-session
agent at checkpoints**, with results recorded into `runs/<id>/` — never by
autonomous Python calling an LLM. So much of the remaining work is **building the
rails/protocol for the agent to drive each phase cleanly** + deterministic
infrastructure (provenance, citations, LaTeX). Numeric DecisionRules stay fully
autonomous and free.

---

## 4. Recommended next-session sequence

Prove "actually usable" with **one full real cycle on T-1** before generalizing:

1. **Real T-1 experiment.** Agent writes the genuine prime/Gödel graph-encoding
   (atoms + bonds + structure, injectivity test) as experiment code; run it in
   Docker; capture real statistics into Evidence. (Tier 1.1)
2. **Spec with a verifiable rule.** Give the T-1 hypothesis a rule whose statistic
   the experiment emits (e.g. a threshold/interval on the injectivity result), so
   the engine drives a real verdict (not a vote, not inconclusive). (Tier 1.3)
3. **Judge + recompile.** Resolve any remaining qualitative checkpoint in-session;
   recompile so the Claim reaches `supported`/`refuted` with a real basis. Wire a
   minimal turnkey checkpoint→recompile helper while doing it. (Tier 1.2)
4. **Paper prose + citations.** Agent writes real sections; acquire 2-3 relevant
   papers via paperforge and cite them + emit BibTeX. (Tier 2.4-2.5)

Completing 1-4 yields the first run where the paper draft, the working code, and
the judged evidence trail are all *real* — the first concrete evidence that
sci-adk is usable. Then generalize beyond T-1 (Tier 1 for arbitrary proposals)
and add Tier 3.

---

## 5. References

- Current usable state + run instructions + LLM constraint: auto-memory `sci-adk-usable`.
- DecisionEngine (D0-D5, judge/checkpoint model): `design/decision-engine.md`.
- Literature acquisition (paperforge): `design/literature-acquisition.md`.
- Tool policy (allowed/excluded; LLM = Claude Code): `design/tool-policy.md`.
- Abstractions (Spec/Evidence/Claim, record vs belief): `design/abstractions.md`.
- Code: `src/sci_adk/loop/compiler.py`, `render/paper.py`, `cli.py`,
  `loop/decision_engine.py`, `loop/judge.py`, `runner/docker_executor.py`.
- This session's commits on `master`: c691732 (paperforge), 1b39496 (halt),
  89a099b (D3), 38227ec (D5), 0376c4e (evidence-id fix), 3b80a4b (compiler
  bundle), f5dda82 (parser cleanup).

---

Version: 1.0 (PLANNED)
Source: gap analysis after the usable-compiler bundle (2026-06-16)
Last Updated: 2026-06-16
