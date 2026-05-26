# sci-adk Technical Stack

> Last Updated: 2026-05-26
> Status: v0.1 CONFIRMED - Python selected for compiler implementation
> Implementation Language: Python 3.11+

## Core Abstractions

The foundation of sci-adk is the separation of **record** from **belief**, implemented through three core types:

### Spec (Compiler Input)
- **Purpose**: Frozen pre-registration contract
- **Immutable**: Versioned with amendment audit trail
- **Components**:
  - RawProposal (4-pane input verbatim)
  - Hypotheses[] (derived from "goal" pane)
  - MethodPlan (derived from "method" pane)
  - TargetClaims[] (derived from "expected_output" pane)
- **Invariants**: S1-S5 (see `design/abstractions.md`)
- **Key Decision**: Amendment requires human checkpoint even in autonomous mode (S5)

### Evidence (Accumulated Record)
- **Purpose**: Immutable, append-only log of experiments
- **Properties**: Monotone growth only
- **Components**:
  - Provenance (code_ref, data_ref, seed, environment, cost)
  - Result (quantitative/qualitative)
  - Bearing[] (supports/refutes/neutral/inconclusive)
- **Invariants**: E1-E4 (see `design/abstractions.md`)
- **Key Property**: Null/negative results are valid outcomes

### Claim (Compiler Output)
- **Purpose**: Revisable belief state derived from Evidence
- **Properties**: Non-monotone status movement
- **Components**:
  - ClaimStatus (proposed/supported/contested/refuted/retracted)
  - Confidence (credence/posterior/graded with required basis text)
  - EvidenceLink[] (supporting AND refuting)
  - StatusChange[] (audit of belief movement)
- **Invariants**: C1-C6 (see `design/abstractions.md`)
- **Key Property**: "contested" is explicit when evidence conflicts

## Implementation Language

### Python 3.11+

**Rationale**:
- Scientific computing ecosystem (NumPy, SciPy, SymPy, NetworkX, RDKit)
- Academic search MCP client integration
- Docker containerization for isolated execution
- Clear syntax for dataclass/type representation of core abstractions

**Scope**:
- Compiler implementation (`src/sci_adk/`)
- NOT research runtime code (domain-specific, per-proposal)

## Research Loop Architecture

### Reusable Loop Skeleton

Phases relabeled from software development:
```
gather → model → evaluate → review
```

### Components

1. **Controller**: Main loop orchestration
   - Convergence detection (decision rules met OR evidence budget exhausted OR human checkpoint)
   - NOT "errors == 0" — null result is valid convergence

2. **FeedbackGenerator**: Produces EvidenceItems
   - Scientific metrics (effect sizes, posteriors, proof steps)
   - NOT go-test/lint counts

3. **DecisionEngine**: Evaluates Claim confidence
   - Against Spec DecisionRules (per-hypothesis, not global constants)
   - Supports threshold/bayesian/interval/proof/qualitative rules
   - NOT binary 0-conjunction quality gate

## Execution Environment

### Docker Isolation

**Base Image**: `environments/python-base/`
- Python 3.11+
- Scientific stack: NumPy, SciPy, SymPy, NetworkX, RDKit (chemistry)
- Future: SageMath (math), Lean 4 + Mathlib (formal proof), JAX (autodiff)

**Provenance Capture**:
- Container image IDs
- Toolchain versions (pip freeze)
- RNG seeds (stochastic reproducibility)
- Environment variables

### Parallel Execution

- **tmux**: Worktree isolation for parallel experiments
- **Claude subagent**: Task delegation for concurrent work

## Tool Policy

### Allowed Tools (sci-adk Runtime)

**LLM Backend**:
- Claude Code (primary)
- GLM via z.ai (fallback, rate limit)

**Integration Standard**:
- MCP (Model Context Protocol)

**Provenance**:
- Git (code/document versioning)
- DVC (Data Version Control)

**Academic Search** (MCP servers):
- arXiv MCP
- Semantic Scholar MCP
- PubMed MCP (biomedical)
- OpenReview MCP (ML/CS)
- CrossRef MCP (DOI resolution)

**External Information**:
- Claude native web_search, web_fetch
- Context7 (library documentation)

**Paper Writing**:
- LaTeX, BibTeX, pandoc

### Excluded Tools (sci-adk Runtime)

These are used by MoAI-ADK but **intentionally excluded** from sci-adk's research workflow because they embody software development assumptions:

- **LSP servers**: Assumes "syntax/type correctness = task complete"
  - sci-adk's completion criterion: paper draft + working code + consistent evidence trail
- **ast-grep**: Structural code pattern search for refactoring
  - sci-adk's workflow: scientific experiments, not code refactoring
- **Conventional Commits**: PR automation convention
  - sci-adk's "done" ≠ PR merge (paper draft + evidence)
- **Coverage thresholds** (e.g., 85%): Code test coverage
  - sci-adk's verification metric: proof consistency, reproducibility, statistical testing

**Critical**: These exclusions apply to *sci-adk's research runtime*, NOT the build harness (MoAI-ADK).

## No Hardcoded Metrics

Per tool policy: **no success metric is hardcoded anywhere**.

**Replacement** (structural, not a new constant):
- Each Spec declares its own DecisionRule per hypothesis
- Claim.confidence judged against *that rule* (not global thresholds)

This is the mechanism that lets metrics be per-research rather than global.

## Data Flow

```
Four-Pane Proposal
         ↓
    [Spec Compilation]
         ↓
  Spec (frozen, versioned)
         ↓
    [Research Loop]
         ↓
  ┌─→ gather → model → evaluate → review ─┐
  │                                      │
  └──────────────── NO convergence ───────┘
         │ (convergence = rules met OR budget exhausted OR checkpoint)
         ↓
    Evidence (append-only log)
         ↓
    [Claim Update]
         ↓
  Claims (revisable belief)
         ↓
    [Renderer]
         ↓
  Paper Draft + Code + Evidence Trail
```

## Confidence Computation

### Supported Types

1. **Credence**: Subjective probability [0, 1]
2. **Posterior**: Bayesian posterior probability
3. **Graded**: strong/moderate/weak/none

### Required Field

- **basis** (natural-language justification) is the load-bearing field
- `value`/`level` is whichever indicator is representative for the field
- The `basis` text carries the actual judgment (recon meta-rule #4)

### Decision Rule Types

- **threshold**: "posterior odds > 10 => support"
- **bayesian**: "posterior distribution exceeds threshold"
- **interval**: "effect-size 95% CI excludes 0 => support; includes 0 => null"
- **proof**: "verified derivation exists => support; counterexample => refute"
- **qualitative**: "expert/structured criterion stated in prose"

## Verification Layers

### Engineering Layer (Build Harness)
- **Question**: Does the compiler code work?
- **Tools**: `tests/`, MoAI, LSP, coverage
- **Status**: Legitimate software engineering

### Science Layer (sci-adk Runtime)
- **Question**: Is a research finding valid?
- **Tools**: Evidence/Claim + per-Spec DecisionRule
- **Status**: Core innovation — rejects SW assumptions

## Integration Points

### Input
- Four-pane proposal (text/markdown)
- User provides via CLI or API

### Output
- `runs/<proposal>/spec.json`: Compiled Spec instance
- `runs/<proposal>/evidence/`: Evidence log (JSONL append-only)
- `runs/<proposal>/claims/`: Claim state (JSON)
- `runs/<proposal>/code/`: Working code
- `runs/<proposal>/paper/main.tex`: LaTeX draft

### Academic Search
- MCP client integration for literature EvidenceItems
- Automatic citation management (BibTeX)

### Provenance
- Git integration for code versioning
- DVC integration for data versioning (deferred to milestone)

## Future Extensions

### Domain Plugins (Deferred)
- Formal proof: Lean 4 + Mathlib
- Symbolic math: SageMath
- Autodiff: JAX
- Biomedical: BioPython, OpenMM

### Advanced Features (Deferred)
- Collaborative research: Multi-user Claim negotiation
- Reproducibility scoring: Automated provenance completeness checks
- Result prediction: ML-based hypothesis prior estimation

## Dependencies

### Runtime (Python)
- `pydantic`: Data validation for core types
- `docker`: Docker Python SDK for container execution
- `gitpython`: Git operations
- `httpx`: HTTP client for MCP servers
- `numpy`, `scipy`: Scientific computing (base image)

### Development (Engineering Layer)
- `pytest`: Test framework
- `pytest-cov`: Coverage reporting
- `black`: Code formatting
- `ruff`: Linting

### Deferred to Milestone
- `dvc`: Data version control
- `bibtexparser`: Bibliography management
- `jupyter`: Notebook execution (if needed)

## References

- Core Abstractions: `design/abstractions.md`
- Directory Structure: `design/directory-structure.md`
- Tool Policy: `design/tool-policy.md`
- Session 1 Status: `design/session-1-handoff.md`
- Recon Decision: `recon/REPORT.md`
