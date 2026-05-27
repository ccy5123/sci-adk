# sci-adk: Research Compiler

> Version: 0.1 (Milestone 1 Complete)
> Status: End-to-end pipeline working
> Last Updated: 2026-05-27

## What is sci-adk?

**sci-adk** is a **research compiler**: a system that consumes a four-pane research proposal and emits a paper draft + working code + an evidence trail.

### Core Philosophy

The deepest design principle is the separation of **record** from **belief**:

- **Record (Evidence)**: Monotone, append-only log of what happened
- **Belief (Claim)**: Non-monotone, revisable confidence derived from evidence

This rejects the software engineering assumption that "build state equals truth."

## Milestone 1: Complete ✅

### What Works

1. **Input Parsing** (Phase 2)
   - Parse 4-pane proposals (Background/Goal/Method/Expected Output)
   - Compile into frozen Spec instances
   - Korean + English section headers supported
   - Auto-generate Spec IDs

2. **Core Types** (Phase 1)
   - Spec: Frozen pre-registration contract
   - Evidence: Append-only log with provenance
   - Claim: Revisable belief state
   - Full invariant enforcement (S1-S5, E1-E4, C1-C6)
   - 1,360 lines of Python code

3. **Docker Execution** (Phase 3)
   - Isolated Python 3.11 environment
   - Scientific stack (numpy, scipy, networkx)
   - Provenance capture (image ID, git commit, timestamp)
   - T-1 molecular encoding executor

4. **Evidence Generation** (Phase 4)
   - Run experiments in Docker containers
   - Generate EvidenceItems with Bearings
   - Support for null/negative results
   - Auto-save to `runs/<spec_id>/evidence/`

5. **Claim Update** (Phase 5)
   - Evaluate Evidence against Spec DecisionRules
   - Update Claim confidence with required basis text
   - Support for contested status (mixed evidence)
   - Auto-save to `runs/<spec_id>/claims/`

### Quick Start

```bash
# Run end-to-end demo
python3 demo_e2e.py

# Expected output:
#   Step 1: Parsing T-1 proposal...
#   ✅ Spec created: spec-t1-demo
#   Step 2: Running T-1 experiment...
#   ✅ Evidence generated: 1 items
#   Step 3: Updating claims...
#   ✅ Claims updated: 1 claims
#   Output: runs/spec-t1-demo/
```

## Project Structure

```
sci-adk/
├── design/                  # Design documents
│   ├── abstractions.md      # Core type specifications (v0.1)
│   ├── tool-policy.md       # Runtime tool governance
│   ├── directory-structure.md
│   ├── milestone-1.md       # Milestone 1 definition
│   └── session-1-handoff.md
├── src/sci_adk/            # Compiler implementation
│   ├── core/               # Core types (Phase 1)
│   │   ├── spec.py         # Spec + invariants S1-S5
│   │   ├── evidence.py     # Evidence + invariants E1-E4
│   │   ├── claim.py        # Claim + invariants C1-C6
│   │   └── parser.py       # 4-pane parser (Phase 2)
│   ├── loop/               # Research loop (Phase 4-5)
│   │   ├── experiment_runner.py  # Evidence generation
│   │   └── claim_updater.py      # Claim updates
│   └── runner/             # Docker execution (Phase 3)
│       └── docker_executor.py
├── environments/           # Docker images
│   └── python-base/        # Python 3.11 scientific stack
├── tests/                  # Unit tests
│   ├── test_spec.py        # Spec invariants (602 lines)
│   ├── test_evidence.py    # Evidence invariants (648 lines)
│   └── test_claim.py       # Claim invariants (814 lines)
├── runs/                   # Research output
│   └── <spec_id>/          # Per-research artifacts
│       ├── spec.json       # Compiled Spec
│       ├── evidence/        # Evidence log
│       └── claims/          # Claim state
├── demo_e2e.py             # End-to-end demo
├── CLAUDE.md               # MoAI-ADK build directive
└── README.md               # This file
```

## Usage Examples

### Parse a Proposal

```python
from src.sci_adk.core.parser import parse_proposal

proposal = """
연구 배경: 연구 배경 텍스트...
연구 목표: 가설 정의...
연구 방법: 방법론 설명...
기대 산출물: 산출물 기대...
"""

spec = parse_proposal(proposal)
print(f"Spec: {spec.id}")
print(f"Hypotheses: {len(spec.hypotheses)}")
```

### Run Experiments

```python
from src.sci_adk.loop.experiment_runner import run_t1_experiments

spec = ...  # from parse_proposal()
molecules = ["H2O", "CO2", "CH4"]
evidence_items = run_t1_experiments(spec, molecules)
```

### Update Claims

```python
from src.sci_adk.loop.claim_updater import update_claims

spec = ...  # from parse_proposal()
evidence_items = ...  # from run_t1_experiments()
claims = update_claims(spec, evidence_items)

for claim in claims:
    print(f"{claim.id}: {claim.status} (confidence: {claim.confidence.value:.2f})")
```

## Development Status

### ✅ Complete (Milestone 1)

- [x] Core type implementation (Spec, Evidence, Claim)
- [x] Input parsing (4-pane → Spec)
- [x] Docker execution environment
- [x] Evidence generation (T-1 experiments)
- [x] Claim updates (Evidence → Claim)
- [x] Unit tests (2,634 lines)
- [x] End-to-end demo

### ⏸️ Deferred (Milestone 2+)

- [ ] Full DecisionRule engine (interval, bayesian, proof)
- [ ] Paper rendering (Claims + Evidence → LaTeX)
- [ ] DVC integration (data versioning)
- [ ] Academic MCP (arXiv, S2, PubMed)
- [ ] Loop convergence detection
- [ ] Multi-hypothesis evaluation

## Key Design Decisions

### No Hardcoded Metrics

Each Spec declares its own DecisionRule per hypothesis. Claim confidence is judged against *that rule*, not global constants like "85% coverage."

### Record vs Belief Separation

- **Evidence** is monotone and append-only (never mutated)
- **Claims** are non-monotone and revisable (status can move in any direction)
- This separation enables honest scientific reporting

### Null Results Are Valid

Inconclusive or negative results are first-class outcomes. EvidenceItem explicitly supports `direction = refutes | inconclusive | neutral` as valid complete outcomes.

## Two-Environment Separation

This repo contains **two coexisting systems**:

1. **MoAI-ADK** = Build harness (tool to *construct* sci-adk)
   - Root `CLAUDE.md`, `.moai/`, `.claude/`, `.mcp.json`
   - Leave untouched — this is the workshop, not the product

2. **sci-adk** = The product (research compiler)
   - `src/`, `design/`, `runs/`
   - Governed by Spec/Evidence/Claim abstractions + tool policy

## Tool Policy

### Allowed (sci-adk Runtime)

- Claude Code + Git + MCP
- arXiv, Semantic Scholar (MCP)
- docker Python, LaTeX

### Excluded (sci-adk Runtime)

- LSP servers (syntax correctness ≠ task complete)
- ast-grep (software refactoring, not scientific)
- Conventional Commits (PR automation, sci-adk's "done" ≠ PR merge)
- Coverage thresholds (code testing ≠ scientific verification)

**Note**: These exclusions apply to *sci-adk's research runtime*, NOT the build harness.

## Testing

```bash
# Unit tests (pytest required - not installed yet)
pytest tests/test_spec.py
pytest tests/test_evidence.py
pytest tests/test_claim.py

# End-to-end demo
python3 demo_e2e.py
```

## Session History

### Session 1 (2026-05-26)
- Reconnaissance and fork vs scratch decision
- Core abstractions design (Spec/Evidence/Claim)
- Directory structure definition
- Tool policy establishment

### Session 2 (2026-05-27)
- Core type implementation (1,360 lines)
- Unit tests (2,634 lines)
- Input parser (Phase 2)
- Docker execution (Phase 3)
- Evidence generation (Phase 4)
- Claim updates (Phase 5)
- **Milestone 1 complete** ✅

## References

- **Core Abstractions**: `design/abstractions.md`
- **Directory Structure**: `design/directory-structure.md`
- **Tool Policy**: `design/tool-policy.md`
- **Milestone 1**: `design/milestone-1.md`
- **Session 1 Handoff**: `design/session-1-handoff.md`
- **Recon Report**: `recon/REPORT.md`

## License

TBD

## Authors

cyjoe (sci-adk project lead)

---

**Milestone 1 Status**: ✅ Complete  
**Next Milestone**: Loop convergence + Paper rendering  
**Last Updated**: 2026-05-27
