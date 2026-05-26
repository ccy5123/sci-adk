# sci-adk Project Structure

> Last Updated: 2026-05-26
> Status: v0.1 CONFIRMED - Skeleton created
> Implementation Language: Python

## Directory Layout

```
sci-adk/
├── recon/                        # [READ-ONLY] Reconnaissance from prior session
│   ├── REPORT.md                 #   Fork vs scratch decision, T-1 reference
│   ├── cc-meta-rules.md          #   Claude Code collaboration rules (7 meta-rules)
│   ├── sw-assumptions.md         #   Software assumptions that break for science
│   ├── tdd-mismatch.md           #   TDD vs research workflow analysis
│   └── domain-research.md        #   Academic tool landscape
│
├── design/                       # [DESIGN] sci-adk specifications and decisions
│   ├── abstractions.md           #   Core types: Spec / Evidence / Claim (v0.1)
│   ├── tool-policy.md            #   Runtime tool policy (authoritative)
│   ├── directory-structure.md    #   This file
│   └── session-1-handoff.md      #   Inter-session handoff prompt
│
├── src/sci_adk/                  # [COMPILER SOURCE] Python implementation
│   ├── __init__.py
│   ├── core/                     #   Core type implementations
│   │   ├── __init__.py
│   │   ├── spec.py               #     Spec type + invariants (S1-S5)
│   │   ├── evidence.py           #     Evidence type + invariants (E1-E4)
│   │   └── claim.py              #     Claim type + invariants (C1-C6)
│   │
│   ├── loop/                     #   Research execution loop
│   │   ├── __init__.py
│   │   ├── controller.py         #     Main loop controller (gather → model → evaluate → review)
│   │   ├── feedback_generator.py #     Produces EvidenceItems from experiments
│   │   └── decision_engine.py    #     Evaluates Claim confidence against Spec DecisionRules
│   │
│   ├── runner/                   #   Generalized tool runner over docker
│   │   ├── __init__.py
│   │   └── docker_executor.py    #     Isolated execution environments
│   │
│   ├── provenance/               #   Reproducibility tracking
│   │   ├── __init__.py
│   │   ├── git_tracker.py        #     Code provenance (commits, worktrees)
│   │   └── env_capture.py        #     Environment capture (seeds, toolchain versions)
│   │
│   ├── search/                   #   Academic search integration
│   │   ├── __init__.py
│   │   └── mcp_client.py         #     arXiv, S2, PubMed, OpenReview, CrossRef
│   │
│   └── render/                   #   Paper generation
│       ├── __init__.py
│       ├── latex_renderer.py     #     Claims + Evidence → LaTeX draft
│       └── bibliography.py       #     BibTeX management
│
├── environments/                 # [COMPILER SOURCE] Docker domain images
│   └── python-base/              #   Milestone image (NumPy/SciPy/SymPy/NetworkX/RDKit)
│       ├── Dockerfile
│       └── requirements.txt
│
├── tests/                        # [COMPILER SOURCE] Engineering layer tests
│   ├── __init__.py
│   ├── test_spec.py              #   Spec type tests
│   ├── test_evidence.py          #   Evidence type tests
│   ├── test_claim.py             #   Claim type tests
│   └── test_loop.py              #   Loop integration tests
│
├── runs/                         # [SYSTEM OUTPUT] Per-research artifacts
│   └── <proposal>/               #   One research proposal = one "compilation"
│       ├── spec.json             #     Compiled Spec instance (frozen, versioned)
│       ├── evidence/             #     Append-only Evidence log
│       │   ├── evidence-001.json
│       │   ├── evidence-002.json
│       │   └── ...
│       ├── claims/               #     Claims (revisable belief state)
│       │   ├── claim-001.json
│       │   └── ...
│       ├── code/                 #     Working code sci-adk wrote
│       │   └── src/
│       ├── data/                 #     DVC-tracked (data/ has .dvc pointers in git)
│       │   └── .dvc
│       └── paper/                #     LaTeX draft + .bib
│           ├── main.tex
│           ├── sections/
│           └── references.bib
│
├── .moai/                        # [MoAI-ADK] Build harness state (do not modify)
│   ├── config/
│   │   └── config.yaml
│   ├── specs/
│   └── project/
│       ├── product.md            #     This document (product overview)
│       ├── structure.md          #     This file (project structure)
│       └── tech.md               #     Technical stack
│
├── .claude/                      # [MoAI-ADK] Build harness agents/skills (do not modify)
├── .mcp.json                     # [MoAI-ADK] MCP servers for build harness
├── CLAUDE.md                     # [MoAI-ADK] MoAI Execution Directive (build directive)
├── .gitignore                    # [MoAI-ADK] Build harness gitignore
└── pyproject.toml                # [Deferred to milestone] Python project config
```

## Three-Level Type Discipline

1. **Type Specification**: `design/abstractions.md` (schema definitions)
2. **Type Implementation**: `src/sci_adk/core/` (Python: spec.py/evidence.py/claim.py)
3. **Type Instances**: `runs/<proposal>/` (concrete Spec, Evidence log, Claims)

## Two Verification Layers

Do not conflate these two distinct verification concerns:

### Engineering Layer (Build Harness)
- **Question**: Does the compiler code work?
- **Location**: `tests/`
- **Tools**: Normal software tests, MoAI/LSP/coverage
- **Scope**: Verifying Python implementation correctness
- **Status**: Legitimate software engineering — this is fine

### Science Layer (sci-adk Runtime)
- **Question**: Is a research *finding* valid?
- **Location**: Evidence/Claim + per-Spec DecisionRule
- **Tools**: NOT tests — these are rejected SW assumptions
- **Scope**: Verifying scientific claims against evidence
- **Status**: Core innovation — record vs belief separation

## File Responsibilities

### Core Types (`src/sci_adk/core/`)

- **spec.py**: Spec compilation from 4-pane proposal
  - Enforce invariants S1-S5 (frozen versions, amendment requires human checkpoint)
  - Derive Hypotheses from "goal" pane
  - Derive MethodPlan from "method" pane
  - Derive TargetClaims from "expected_output" pane

- **evidence.py**: Evidence log management
  - Enforce invariants E1-E4 (append-only, null results are valid)
  - Capture Provenance (code_ref, data_ref, seed, environment, cost)
  - Type-safe Result representation (quantitative/qualitative)

- **claim.py**: Claim belief state management
  - Enforce invariants C1-C6 (non-monotone status, history append-only)
  - Confidence computation against Spec DecisionRules
  - Evidence linking (supporting AND refuting)

### Research Loop (`src/sci_adk/loop/`)

- **controller.py**: Main loop orchestration
  - Phase management: gather → model → evaluate → review
  - Convergence detection: decision rules met OR evidence budget exhausted OR human checkpoint
  - NOT "errors == 0" convergence — null result is valid

- **feedback_generator.py**: Evidence production
  - Executes experiments (via runner/)
  - Produces EvidenceItems (not go-test/lint counts)
  - Scientific metrics (effect sizes, posteriors, proof steps)

- **decision_engine.py**: Claim evaluation
  - Evaluates Claim confidence against Spec DecisionRules
  - NOT binary 0-conjunction quality gate
  - Supports threshold/bayesian/interval/proof/qualitative rules

### Execution (`src/sci_adk/runner/`)

- **docker_executor.py**: Isolated execution
  - Domain-specific Docker images
  - Environment capture (toolchain versions)
  - Seed management for stochastic reproducibility

### Provenance (`src/sci_adk/provenance/`)

- **git_tracker.py**: Code version tracking
  - Commit references for each experiment
  - Worktree isolation for parallel experiments

- **env_capture.py**: Environment fingerprinting
  - Toolchain versions (Python, libraries)
  - Container image IDs
  - RNG seeds

### Search (`src/sci_adk/search/`)

- **mcp_client.py**: Academic database integration
  - arXiv, Semantic Scholar, PubMed, OpenReview, CrossRef
  - Literature EvidenceItem production
  - Citation management

### Rendering (`src/sci_adk/render/`)

- **latex_renderer.py**: Paper generation
  - Claims + Evidence → LaTeX sections
  - Automatic figure/table inclusion
  - Acknowledgments (data/code provenance)

- **bibliography.py**: Reference management
  - BibTeX generation from EvidenceItems
  - DOI resolution via CrossRef

## Status: Created vs Planned

### Created (Session 1 - Empty Skeleton)

- Directory structure: `src/sci_adk/{core,loop,runner,provenance,search,render}/`
- Docker base: `environments/python-base/`
- Test skeleton: `tests/`
- Output root: `runs/`

All are empty package markers (`__init__.py` only) — zero logic surface.

### Deferred to Milestone

Per tool-policy "add when needed":
- `pyproject.toml` (Python project configuration)
- Domain `Dockerfile` (beyond python-base)
- sci-adk's own MCP wiring (search/ implementation)
- DVC init (data/ tracking)
- Actual module code (core types, loop, runner, etc.)

## Open Question: sci-adk Constitution Location

**Deliverable #1** ("sci-adk CLAUDE.md / constitution") needs a home that is NOT the root `CLAUDE.md` (which is MoAI's build directive).

Where do sci-adk's identity + the 7 CC meta-rules + tool-policy pointer live so they are active for sessions working on sci-adk?

**Options to decide with user**:
- (a) `.claude/rules/` entry under build harness pointing to `design/`
- (b) Constitution doc in `design/` that each session reads
- (c) Defer until sci-adk is standalone runnable system with its own CLAUDE.md

See `design/session-1-handoff.md` 남은 작업 #1 for context.
