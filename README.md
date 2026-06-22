# sci-adk: Rigor / Verification ADK

> Version: 0.1.0
> Status: working rigor-ADK CLI — compiler + DecisionEngine + judge rail + headless `verify` + literature triggers (novelty + contested) + tex-only paper render
> Last Updated: 2026-06-18

## What is sci-adk?

**sci-adk** is a **domain-general rigor / verification ADK** — a *referee/scorekeeper, not a player* — for the user's own research.

It **builds** the rigor kernel (record vs belief, frozen criteria, verification, provenance, deterministic replay) and **borrows** capabilities (experiment authoring, literature, prose) via the in-session Claude agent and subagents. External release is a deferred, not foreclosed, future option. The operating rule is: **agents propose; the engine judges by frozen criteria. No self-certification. The verdict path is deterministic and rule-based.**

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
Alias for `--capability t1-molecular-godel`. Runs the T-1 molecular Godel-encoding capability over its designed molecule test set. Yields an autonomous injectivity verdict via the DecisionEngine (numeric threshold rule — no judge needed).

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

```bash
# 1. Install
pip install -e .

# 2. Run the built-in T-1 demo (autonomous numeric verdict, no proposal file needed)
sci-adk run --t1-demo

# 3. Inspect the run directory
ls runs/t1-godel/

# 4. Headless re-verification (no LLM required)
sci-adk verify runs/t1-godel
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
- **`/sci` commands** — `plan` / `experiment` / `publish` / `verify` / `status`
  (+ `replicate`, a v2 stub) routing through the `sci` orchestration Skill.
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
- **LaTeX paper output**: `render_paper_latex` emits a tex-only, Overleaf-compilable `draft.tex` (no-dep pdflatex-safe unicode net, `references.bib` co-located into `paper/`), an agent-authored prose-input hook, and a References section wiring cited DOIs — `render/paper.py`
- **paperforge re-pin → DOI→BibTeX**: pin `2cec69b` ships `paperforge.bibtex`
- 1025 unit tests passing (`python3 -m pytest -q`)

### Remaining

- Paper render: tex-only `draft.tex` exists (Overleaf-compilable); **PDF compilation (LaTeX docker)** and the **render-time novelty 'first' output gate** remain deferred
- 2nd-domain generalization: the plug-seam is built and enforced; validated only once a second domain plugs in without a kernel edit (adoption-roadmap Stage 0 generalization gate)
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
│   ├── rigor-shell-architecture.md     # Kernel + seam architecture, Step 2
│   ├── adoption-roadmap.md   # Staged external-system adoption (A done / B staged / C cut)
│   ├── decision-engine.md    # DecisionEngine design
│   ├── literature-acquisition.md       # Literature acquisition design
│   ├── milestone-3.md        # Milestone 3 roadmap
│   ├── tool-policy.md        # Runtime tool governance (allowed / excluded)
│   ├── directory-structure.md
│   ├── constitution.md       # sci-adk identity and rules
│   └── session-4-handoff.md  # Latest session handoff
├── environments/             # Docker images
│   └── python-base/          # Python 3.11 + scientific stack
├── tests/                    # Engineering-layer tests (1025 passing)
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
├── pyproject.toml            # sci-adk v0.1.0; console script sci-adk = sci_adk.cli:main
└── README.md                 # This file
```

---

## Testing

```bash
# All tests (1025 passing)
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
| `design/sci-adk-productization-plan.md` | Identity: referee/scorekeeper, rigor ADK; Step 3 |
| `design/rigor-shell-architecture.md` | Kernel + seam architecture (F1–F7 decided); Step 2 |
| `design/adoption-roadmap.md` | Staged adoption: A (done) / B (staged) / C (cut) |
| `design/decision-engine.md` | DecisionEngine design and invariants |
| `design/literature-acquisition.md` | Literature acquisition and prior-work trigger |
| `design/tool-policy.md` | Runtime tool governance |
| `design/milestone-3.md` | Milestone 3 roadmap |
| `design/constitution.md` | sci-adk identity and session rules |

---

## License

TBD

## Authors

cyjoe (sci-adk project lead)
