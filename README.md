# sci-adk: Agentic Discovery Kit (ADK)

> Version: 0.2.0
> Status: working rigor/verification ADK — compiler + DecisionEngine + science guards (G1–G5) + deterministic record-fidelity render spine + publishing requirements (F1/F2/F3) + near-submission package layer + 1369 tests passing
> Last Updated: 2026-06-30

## What is sci-adk?

**sci-adk** is an **Agentic Discovery Kit (ADK)** — a rigor / verification system built on a **domain-general kernel** (zero domain code) and a capability-adapter seam; a *referee/scorekeeper, not a player* — for rigorous, reproducible agent-assisted research.

It **builds** the rigor kernel (record vs belief, frozen criteria, verification, provenance, deterministic replay) and **borrows** capabilities (experiment authoring, literature, prose) via the in-session Claude agent and subagents. It is openly developed and free to install, use, and extend. The operating rule is: **agents propose; the engine judges by frozen criteria. No self-certification. The verdict path is deterministic and rule-based.**

See `design/sci-adk-productization-plan.md` §2 / §2.1a for the full identity statement.

### Core Philosophy

The deepest design principle is the separation of **record** from **belief**:

- **Record (Evidence)**: Monotone, append-only log of what happened. Null and negative results are part of the record.
- **Belief (Claim)**: Non-monotone, revisable confidence derived from evidence. A supported claim can be demoted or retracted as new evidence arrives.

This rejects the software engineering assumption that "build state equals truth" — a single monotone, binary, terminal signal.

### Key Design Decisions

**No Hardcoded Metrics**: Each Spec declares its own `DecisionRule` per hypothesis. Claim confidence is judged against *that rule*, not global constants like "85% coverage."

**Null Results Are Valid**: Inconclusive or negative results are first-class outcomes. `EvidenceItem` explicitly supports `direction = refutes | inconclusive | neutral` as valid, complete outcomes.

**Record vs Belief Separation**: Evidence is monotone and append-only (never mutated). Claims are non-monotone and revisable (status can move in any direction). This enables honest scientific reporting.

---

## Install

```bash
pip install -e .
# for paperforge PDF acquisition (optional, private repo):
# pip install -e ".[tools]"
```

The console script `sci-adk` becomes available. The package is importable as `sci_adk`; `PYTHONPATH=src` also works without installing.

---

## Usage / CLI

```
sci-adk run <proposal.md> [-o OUTPUT] [--spec-id ID]
```
Compile a four-pane proposal (Background / Goal / Method / Expected Output) into `runs/<spec.id>/` — produces `spec.json`, `evidence/`, `claims/`, `paper/draft.tex`. The numeric path runs autonomously at zero LLM cost. Proof and qualitative hypotheses are surfaced as agent checkpoints (resolved in-session by the Claude agent; never via an autonomous API call).

```
sci-adk run --capability <id> [-o OUTPUT] [--spec-id ID]
```
Run a capability's built-in demo. The capability adapter resolves an `ExperimentFn` provider from the registry at runtime. Capability is HOW (runtime), not WHAT (frozen in the Spec) — it travels only in Evidence provenance.

```
sci-adk run --t1-demo [-o OUTPUT] [--spec-id ID]
```
Alias for `--capability t1-molecular-godel`. Runs the T-1 molecular Godel-encoding capability over its designed molecule test set. Yields an autonomous injectivity verdict via the DecisionEngine (numeric threshold rule — no judge needed). Under the default strict science guards the bare demo surfaces rigor findings (it carries no negative control by design, G3); pass `--no-strict-science` for a quick smoke run.

```
sci-adk resolve <run-dir>
```
Drive the checkpoint loop over an existing run dir. Re-enters with any `verdicts/<hyp-id>.json` the in-session agent has authored, then reports which checkpoints are still unresolved and which Claims the recorded verdicts resolved. No LLM is invoked.

```
sci-adk verify <run-dir>
```
Headless, read-only belief audit. Re-applies the frozen `DecisionRule` to the recorded Evidence (numeric: autonomously; non-numeric: via a `RecordedJudge` re-reading recorded trails — no LLM). Reports per recorded Claim: `REPRODUCED / DIVERGED / UNRESOLVED`, plus the record digest (tamper-evidence). Overwrites nothing. Exit 0 iff every recorded claim reproduces — CI-style re-verification a third party can run without Claude Code.

```
sci-adk prior-work <run-dir> --searched <DOI...>
sci-adk prior-work <run-dir> --skip --reason "..."
```
Record the Spec-time prior-work decision into the Evidence log. `--searched` acquires the given DOIs and records a `LITERATURE` EvidenceItem. `--skip` records a `PRIOR_WORK_DECISION` null with a required reason. Either closes the prior-work checkpoint.

```
sci-adk status <run-dir>
```
Terse, read-only session-state snapshot: recorded Claim statuses + open decisions. No LLM, no recompile. Cheap enough to call every turn. Exit 0 always (missing run dir → "nothing recorded" report).

```
sci-adk novelty <run-dir> --hyp <id> --kind result|method --found-nothing | --found <DOI...>
sci-adk contested <run-dir> --hyp <id>
```
Record novelty decisions (`novelty_result` / `novelty_method`, independent per hypothesis) and contested status into the Evidence log. `sci-adk verify` re-derives both novelty Claims.

```
sci-adk pubreqs freeze <run-dir>
```
Elicit and freeze a `pubreqs.json` publishing contract (venue, required sections, figure font/DPI policy, reproduction bundle). Gated deterministically by `sci-adk verify`.

```
sci-adk pkgreqs freeze <workspace>
sci-adk package <workspace>
```
Freeze the workspace-level package contract (`pkgreqs.json`) and assemble a near-submission package — one merged `main.tex` + `si.tex` + figures from all runs, plus a 6-folder reproduction bundle. Gated by the `package_requirements_clean` HARD gate inside `sci-adk verify`.

### Decomposed CLI verbs (operational layer)

The decomposed verbs (`init-spec` / `amend-spec` / `execute` / `append-evidence` / `derive-claim` / `render`) expose individual compiler stages for the operational-layer workers to call independently. `sci-adk run` remains the monolithic wrapper.

### Writing a proposal (4-pane format)

`sci-adk run <proposal.md>` parses a Markdown proposal with four `#` headings into a frozen Spec. Accepted headings (English or Korean): `# Background` / `# Goal` / `# Method` / `# Expected Output` (also `# 연구 배경` / `# 연구 목표` / `# 연구 방법` / `# 기대 산출물`).

```markdown
# Background
Molecular graphs have no canonical integer key, so structurally distinct
molecules can collide under naive encodings.

# Goal
Define an injective Gödel-style numbering for small molecular graphs.

# Method
Encode atoms and bonds by prime factorization + Cantor pairing; test
injectivity (zero collisions) over a fixed molecule set.

# Expected Output
A collision-free encoding over the tested set, reported as an injectivity verdict.
```

```bash
sci-adk run proposal.md
```

A bare `run` compiles the Spec + a proposal draft and surfaces any proof/qualitative **checkpoints** — it does *not* invent an experiment. Supply one with `--capability <id>` (adapter-served), or have the in-session agent author it; numeric rules then verify autonomously, and `sci-adk resolve` re-enters once verdicts are recorded.

### Quick Start

> **New here?** The [**15-minute tutorial**](docs/tutorial.md) walks through re-verifying the bundled run, reading record vs belief in a real run directory, compiling your own proposal, and what `verify` does and does not guarantee.

```bash
# 1. Install
pip install -e .

# 2. Re-verify the bundled T-1 run -- deterministic, offline, no LLM.
#    This is sci-adk's core property: a third party reproduces the verdict from
#    the record alone. Exit 0 iff every recorded claim reproduces.
sci-adk verify runs/t1-godel
sci-adk status runs/t1-godel

# 3. (optional) Generate a fresh demo run. Under the default science guards the
#    bare demo SURFACES rigor findings (G1-G4) -- the engine refusing to bless an
#    under-justified toy claim is the point, not a failure. Add --no-strict-science
#    for a quick smoke run that completes with an autonomous injectivity verdict.
sci-adk run --t1-demo --no-strict-science
```

### Library Usage (secondary interface)

The Python API remains available for programmatic use:

```python
from sci_adk.core.parser import parse_proposal
from sci_adk.adapter.t1_capability import build_t1_spec, build_t1_demo_molecules, t1_experiment
from sci_adk.loop.claim_updater import update_claims
from pathlib import Path

# Parse a four-pane proposal
spec = parse_proposal(proposal_text)

# Run a capability experiment
molecules = build_t1_demo_molecules()
evidence_items = t1_experiment(molecules)(spec, Path("runs"))

# Update claims from evidence
claims = update_claims(spec, evidence_items)
for claim in claims:
    print(f"{claim.id}: {claim.status} (confidence: {claim.confidence.value:.2f})")
```

---

## Operational Layer (research workspace)

Beyond the CLI, sci-adk ships an **operational layer** that turns any directory into a
disciplined research workspace. Install it with:

```bash
sci-adk init-session <dir>
```

This lays down (non-clobbering, idempotent):

- **`science-orchestrator`** — the always-on persona: clarifies intent, delegates to
  research workers, and gates every conclusion through `sci-adk verify`.
- **Worker agents** — `manager-prereg` (author + freeze the Spec), `expert-experimentalist`
  (run experiments → Evidence), `expert-statistician` (apply the `DecisionRule` → Claims),
  `expert-writer` (render the paper), `expert-literature` (prior-art / novelty search).
- **Guard agents** (advisory) — `evaluator-rigor` / `evaluator-novelty` /
  `evaluator-validity`: soft pre-checks that catch problems early. They never grant a
  pass — `sci-adk verify` (run by the Stop hook) is the sole verdict.
- **`/sci` commands** — `plan` / `experiment` / `publish` / `verify` / `status` / `replicate` / `package` routing through the `sci` orchestration Skill.
- **Enforcement hooks** — a Stop gate (`sci-adk verify`) and a per-turn re-anchor.

Workers fan out across the decomposed CLI verbs (`init-spec` / `amend-spec` / `execute` /
`append-evidence` / `derive-claim` / `render`); `sci-adk run` remains the monolithic
wrapper. The operational layer is **opt-in scaffolding over the same deterministic
kernel** — it adds delegation and early checks, never a new verdict path. See
`design/sci-adk-as-moai.md` for the full design.

---

## Development Status

### Done (kernel spine)

- Core types: Spec / Evidence / Claim with full invariant enforcement (S1–S5, E1–E4, C1–C6)
- Input parsing: four-pane proposal (Background / Goal / Method / Expected Output) to frozen Spec; Korean and English section headers supported
- Docker execution: isolated Python 3.11 scientific environment with provenance capture (image ID, git commit, timestamp)
- Evidence generation: append-only Evidence log with Bearings, null/negative results, auto-save
- DecisionEngine: threshold + Bayesian + interval numeric rules + proof/qualitative judge rail (F2 trail gate)
- Claim updates: Evidence to Claim with required basis text; contested status for mixed evidence
- `sci-adk verify`: headless re-derivation + record digest (tamper-evidence); exit 0 iff all claims reproduce
- Checkpoint loop: `sci-adk resolve` re-enters a run with recorded agent verdicts
- Prior-work trigger: `sci-adk prior-work` records the Spec-time prior-work decision (searched or skipped)
- Capability adapter seam: `adapter/registry.py` + F4 lint (`tests/test_kernel_adapter_seam.py`) enforces the kernel-cannot-import-adapter invariant
- T-1 capability: Godel-style molecular-graph encoding over number theory; real injective encoding with autonomous injectivity verdict
- `provenance/` package: record digest for append-only tamper-evidence
- `search/paperforge_adapter.py`: DOI-to-OA-PDF acquisition with halt gates wired into the prior-work path
- `.gitattributes`: LF enforcement on add
- Referent-typed **evidence-validity** enforcement: synthetic/generated data cannot make a SUPPORTED *empirical* claim (formal vs empirical referent typing; hard halts) — `core/validity.py`
- **Figure-digitization**: a `digitized` Evidence kind with proposed→verified gate (extractor required, extractor ≠ verifier, never auto-promoted to measured) + deterministic digitizer
- **PDF normalization**: owner/permission-restricted acquired PDFs auto-normalized (pypdf); user-password-locked PDFs surfaced as `locked`, never cracked — `search/pdf_normalize.py`
- **Citation-key naming** for acquired PDFs: `<Surname><Year>` with DOI-sorted a/b on collision; rename is swap/cycle-safe (two-stage batch) — `search/citation_keys.py`
- **Literature triggers — novelty + contested**: contested = recording-only; **novelty is a 1st-class revisable Claim `claim-novelty-<hyp>` derived by rule (B-replace)** — SUPPORTED iff a recorded `found_nothing` prior-art search; NON-HALT compile-time checkpoint; `sci-adk novelty`/`sci-adk contested` CLI verbs; `verify` re-derives the novelty claim
- **Science guards (G1–G5)**: spec-layer rigor gates enforced at compile time and verdict time — G1 analyticity (no known-theorem dressed as discovery), G2 test-power (discriminating-case declaration), G3 falsifiability (mutation test: apparatus must be able to report FAIL), G4 mode-coherence (threshold + exploratory = structural conflict), G5 claim-cost (practical-property claim with no declared cost metric). `strict_science` is on by default for `run` / `derive-claim`; guards surface findings in `runs/<id>/science.md`. Pure, no-LLM. See `design/science-guards.md`.
- **Render reframe** — paper render is now a **deterministic record-fidelity SPINE + an agent-authored belief NARRATIVE + a markup fidelity gate**: the agent authors title/IMRaD/discussion; the engine substitutes measured values and verdicts via `\evval{<id>}{<field>}` / `\status{<hyp>}` macros at render time (FAIL-LOUD if the record does not hold the value); `sci-adk verify` flags any unresolved macro residuals. Produces a tool-agnostic paper (no sci-adk internal nouns in `draft.tex`). See `design/render-architecture-reframe.md`.
- **Publishing requirements (F1/F2/F3)**: F1 — elicit + freeze a `pubreqs.json` contract (venue, required sections, length limits) at `/sci publish` time and gate the rendered paper deterministically; F2 — figure font/DPI policy (serif equations, sans figure text, minimum DPI for raster figures) enforced at render + re-checked by `verify`; F3 — reproduction bundle (generating code retained as SI code listing + `paper/reproduce.py` re-runner). CLI: `sci-adk pubreqs freeze`. See `design/paper-publishing-requirements.md`.
- **Workspace near-submission package**: `sci-adk package` assembles a workspace-level submission — one merged `main.tex` + `si.tex` + figures from ALL runs, plus a standard 6-folder reproduction package. A `pkgreqs.json` frozen contract (venue + format) gates the package via the `package_requirements_clean` HARD gate inside `sci-adk verify`. CLI: `sci-adk package`, `sci-adk pkgreqs freeze`. `/sci package` drives the full [0]–[5] contract. See `design/near-submission-package.md`.
- **Novelty 2-kind (result vs method)** — `novelty_result` / `novelty_method` are independent flags per hypothesis (N1); each produces a separate `claim-novelty-<hyp>-result` / `-method` Claim derived by the B-replace rule; `sci-adk novelty` + `sci-adk contested` CLI verbs; `verify` re-derives both. `\novelty{}` render markup (N2) and render/verify novelty gate (N3) track the 2-kind split into the rendered paper. See `design/literature-acquisition.md`.
- **Paper figures + SI**: native pgfplots data-plot renderer with stable labels + Overleaf folder co-location; SI auto-record-dump (`si.tex`); a `\ref`↔`\label` within-document consistency gate as a `sci-adk verify` HARD gate; image-path figures (`ImageFigureSpec`, domain-general — the kernel carries zero domain code); optional `SIProse` hook around the SI record dump; body-order figure numbering. See `design/paper-figures-and-si.md`.
- **LaTeX paper output**: `render_paper_latex` emits a tex-only, Overleaf-compilable `draft.tex` (IMRaD structure, no-dep pdflatex-safe unicode net, `references.bib` co-located into `paper/`), an agent-authored prose-input hook, and a References section wiring cited DOIs — `render/paper.py`
- **paperforge re-pin → DOI→BibTeX**: pin `2cec69b` ships `paperforge.bibtex`
- 1369 unit tests passing (`python3 -m pytest -q`)

### Remaining

- Paper render: IMRaD `draft.tex` exists (Overleaf-compilable); **PDF compilation (LaTeX docker)** remains deferred; cross-document main↔SI `\ref` via `xr` (4c) deferred (Overleaf compile-order wrinkle outweighs value — authoring convention: refer to SI figures as plain text "Figure S1")
- 2nd-domain generalization (RESOLVED 2026-06-26, `design/g-a-a3-decision.md`): the **verification** kernel is validated on a second domain (ecotoxicology), run unmodified with zero kernel edits — the domain-general *verification* claim is evidence-backed (the cross-domain record lives in separate research, paper in preparation); the **autonomous experiment** adapter-seam remains validated on T-1 only (scoped out of the 1.0 claim)
- Multi-capability auto-attempt orchestration: deferred (no consumer yet; append-only record + capability-in-provenance block method-shopping structurally)
- Literature scale: `loop/literature_acquirer.py` exists; PaperQA2 and similar heavy literature plugins are Stage 2 (triggered by first-problem domain selection)

See `design/adoption-roadmap.md` for the full staged adoption plan (Stage 0 spine complete; Stage 1–4 are future, trigger-gated).

---

## Project Structure

```
sci-adk/
├── src/sci_adk/              # Compiler implementation
│   ├── __init__.py
│   ├── cli.py                # CLI entry point (sci-adk command)
│   ├── core/                 # Core types + invariants
│   │   ├── spec.py           # Spec + invariants S1-S5
│   │   ├── evidence.py       # Evidence + invariants E1-E4
│   │   ├── claim.py          # Claim + invariants C1-C6
│   │   ├── parser.py         # Four-pane proposal parser
│   │   └── validity.py       # Referent-typed evidence-validity enforcement
│   ├── loop/                 # Research execution loop
│   │   ├── compiler.py       # ResearchCompiler (orchestrates run)
│   │   ├── decision_engine.py # Verifier: frozen DecisionRule -> Verdict
│   │   ├── judge.py          # Injectable judge interface
│   │   ├── recorded_judge.py # RecordedJudge: reads verdicts/<hyp>.json
│   │   ├── claim_updater.py  # Evidence -> Claim updates
│   │   ├── experiment_runner.py  # ExperimentFn execution
│   │   ├── checkpoint_loop.py    # sci-adk resolve (re-entry loop)
│   │   ├── verdict.py        # Typed checkpoint/verdict schema
│   │   ├── verify.py         # sci-adk verify (headless re-derivation)
│   │   ├── prior_work.py     # sci-adk prior-work (prior-work trigger)
│   │   ├── literature_acquirer.py  # LITERATURE Evidence acquisition
│   │   └── literature_triggers.py  # Novelty (B-replace) + contested triggers
│   ├── runner/               # Docker execution
│   │   └── docker_executor.py
│   ├── render/               # Paper rendering
│   │   └── paper.py          # render_paper_latex: tex-only Overleaf-compilable draft.tex
│   ├── search/               # Literature / PDF acquisition
│   │   ├── paperforge_adapter.py  # DOI -> OA PDF via paperforge subprocess
│   │   ├── citation_keys.py  # <Surname><Year> citation-key naming (swap/cycle-safe)
│   │   └── pdf_normalize.py  # Permission-restricted PDF normalization (pypdf)
│   ├── provenance/           # Record integrity
│   │   └── __init__.py       # Record digest (tamper-evidence)
│   └── adapter/              # Capability seam (kernel must not import this)
│       ├── registry.py       # Capability registry + resolver
│       ├── t1_capability.py  # T-1 Godel-encoding capability provider
│       └── t1_encoding.py    # Injective molecular-graph Godel encoding
├── design/                   # Design documents
│   ├── abstractions.md       # Core type spec: record vs belief invariants
│   ├── sci-adk-productization-plan.md  # Identity (referee/scorekeeper), Step 3
│   ├── sci-adk-as-moai.md    # Operational layer design (workers, guards, /sci commands)
│   ├── rigor-shell-architecture.md     # Kernel + seam architecture (F1–F7)
│   ├── adoption-roadmap.md   # Staged external-system adoption (A done / B staged / C cut)
│   ├── decision-engine.md    # DecisionEngine design and invariants
│   ├── literature-acquisition.md       # Literature acquisition, novelty 2-kind (v0.6)
│   ├── evidence-validity.md  # Referent-typed evidence-validity gate
│   ├── figure-digitization.md          # Digitized Evidence kind + proposed/verified gate
│   ├── science-guards.md     # Science guards G1–G5 (spec-layer rigor enforcement)
│   ├── render-architecture-reframe.md  # Render = record-fidelity spine + agent narrative
│   ├── paper-publishing-requirements.md # F1/F2/F3 publishing requirements + pubreqs
│   ├── near-submission-package.md      # Workspace package layer + pkgreqs
│   ├── paper-figures-and-si.md         # Native figures + SI record-dump + ref-consistency gate
│   ├── research-session-enforcement.md # Stop/UserPromptSubmit hook architecture
│   ├── tool-policy.md        # Runtime tool governance (allowed / excluded)
│   ├── milestone-3.md        # Milestone 3 roadmap
│   ├── directory-structure.md
│   ├── constitution.md       # sci-adk identity and session rules
│   └── session-6-handoff.md  # Latest session handoff
├── environments/             # Docker images
│   └── python-base/          # Python 3.11 + scientific stack
├── tests/                    # Engineering-layer tests (1369 passing)
│   ├── test_spec.py          # Spec invariants
│   ├── test_evidence.py      # Evidence invariants
│   ├── test_claim.py         # Claim invariants
│   ├── test_decision_engine.py
│   ├── test_decision_engine_numeric.py
│   ├── test_decision_engine_proof_qualitative.py
│   ├── test_decision_engine_trail_gate.py
│   ├── test_checkpoint_loop.py
│   ├── test_verify.py
│   ├── test_compiler.py
│   ├── test_kernel_adapter_seam.py  # F4 lint: kernel must not import adapter
│   ├── test_t1_end_to_end.py
│   └── ...                   # 68 test files total
├── runs/                     # Research output (per-run artifacts)
│   └── <spec_id>/
│       ├── spec.json         # Compiled Spec (frozen)
│       ├── evidence/         # Append-only Evidence log
│       ├── claims/           # Claim state
│       ├── checkpoints.md    # Agent checkpoints (unresolved)
│       ├── verdicts/         # Agent-authored verdict files
│       └── paper/draft.tex   # Paper draft (Overleaf-compilable LaTeX)
├── pyproject.toml            # sci-adk v0.2.0; console script sci-adk = sci_adk.cli:main
└── README.md                 # This file
```

---

## Testing

```bash
# All tests (1369 passing)
python3 -m pytest -q

# Integration tests (require Docker)
python3 -m pytest -m integration -q
```

---

## Two-Environment Separation

This repo contains **two coexisting systems** — confusing them breaks everything:

1. **MoAI-ADK** = Build harness (tool used to *construct* sci-adk)
   - Root `CLAUDE.md`, `.moai/`, `.claude/`, `.mcp.json`
   - Leave untouched — this is the workshop, not the product
   - Software-engineering tools (LSP, TDD, coverage) are legitimate here

2. **sci-adk** = The product being built (rigor ADK)
   - `src/`, `design/`, `runs/`
   - Governed by Spec/Evidence/Claim abstractions and tool policy
   - The runtime research workflow rejects software-engineering truth assumptions

This separation applies **only to this dev repository** (where sci-adk source
coexists with a MoAI build harness). An external research workspace created by
`sci-adk init-session <dir>` contains only sci-adk artifacts — there is no second
environment to confuse. (design/sci-adk-as-moai.md §9.2)

---

## Tool Policy

### Allowed (sci-adk Runtime)

- Claude Code + Git + MCP
- arXiv, Semantic Scholar, PubMed, OpenReview, CrossRef (via MCP)
- docker Python, SageMath, Lean 4, LaTeX (per domain)
- paperforge (DOI-to-OA-PDF acquisition, subprocess)

### Excluded (sci-adk Runtime)

- LSP servers: "syntax/type correctness = task complete" assumption rejected
- ast-grep: software refactoring tool, not scientific
- Conventional Commits: PR automation; sci-adk's "done" is not a PR merge
- Coverage thresholds: code testing is not scientific verification

These exclusions apply to *sci-adk's research runtime*, NOT the build harness. Full policy in `design/tool-policy.md`.

---

## Design Documents

| Document | Contents |
|----------|----------|
| `design/abstractions.md` | Core type spec: Spec / Evidence / Claim invariants (v0.1 CONFIRMED) |
| `design/sci-adk-productization-plan.md` | Identity: Agentic Discovery Kit, referee/scorekeeper; Step 3 |
| `design/sci-adk-as-moai.md` | Operational layer: workers, guards, /sci commands, 6 CLI verbs |
| `design/rigor-shell-architecture.md` | Kernel + seam architecture (F1–F7 decided); Step 2 |
| `design/adoption-roadmap.md` | Staged adoption: A (done) / B (staged) / C (cut) |
| `design/decision-engine.md` | DecisionEngine design and invariants |
| `design/science-guards.md` | Science guards G1–G5 (spec-layer rigor: analyticity / test-power / falsifiability / mode / cost) |
| `design/literature-acquisition.md` | Literature acquisition, novelty 2-kind result/method (v0.6) |
| `design/evidence-validity.md` | Referent-typed evidence-validity gate (synthetic data cannot ground empirical SUPPORTED) |
| `design/figure-digitization.md` | Digitized Evidence kind: proposed→verified gate, deterministic digitizer |
| `design/render-architecture-reframe.md` | Render = record-fidelity spine + agent belief narrative + `\evval`/`\status` fidelity gate |
| `design/paper-publishing-requirements.md` | F1 publishing requirements + F2 figure font/DPI + F3 reproduction bundle; `pubreqs` |
| `design/near-submission-package.md` | Workspace-level near-submission package; `pkgreqs` + `package_requirements_clean` gate |
| `design/paper-figures-and-si.md` | Native figures (pgfplots), SI auto-record-dump, `\ref`↔`\label` consistency gate |
| `design/research-session-enforcement.md` | Stop/UserPromptSubmit hook architecture |
| `design/tool-policy.md` | Runtime tool governance (allowed / excluded) |
| `design/milestone-3.md` | Milestone 3 roadmap |
| `design/constitution.md` | sci-adk identity and session rules |

---

## Support & Contributing

Contributions, bug reports, and questions are welcome.

- **Report a bug or request a feature**: open an issue at <https://github.com/ccy5123/sci-adk/issues>
- **Contributing guidelines**: see [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Questions / usage help**: open a GitHub issue describing what you ran and what you expected
- **Cite sci-adk**: see [`CITATION.cff`](CITATION.cff)

---

## License

MIT License — Copyright (c) 2026 Chan Young Joe. See `LICENSE`.

## Authors

Chan Young Joe (cyjoe) — sci-adk project lead
