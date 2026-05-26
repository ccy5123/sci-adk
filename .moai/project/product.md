# sci-adk Product Overview

> Last Updated: 2026-05-26
> Status: Session 1 Design Complete

## Product Identity

**sci-adk** is a **research compiler**: a system that consumes a four-pane research proposal and emits a paper draft + working code + an evidence trail.

### Input

Four-pane research proposal format:
- **Research Background**: Context and motivation
- **Research Goal**: Hypotheses and objectives
- **Research Method**: Proposed approach and tools
- **Expected Output**: Target claims and contributions

Reference workflow: **T-1 (Molecular Numbering System)** - a Gödel-style encoding scheme for molecular graphs using number theory (see `recon/REPORT.md` §1.1).

### Output

End-to-end research artifacts:
1. **Paper Draft**: LaTeX or markdown manuscript
2. **Working Code**: Executable prototype in domain-appropriate language
3. **Evidence Trail**: Complete audit trail from hypothesis → experiments → results → claims

### Core Philosophy

The deepest design principle is the separation of **record** from **belief**:

- **Record (Evidence)**: Monotone, append-only log of what happened. Null and negative results are part of the record.
- **Belief (Claim)**: Non-monotone, revisable confidence derived from evidence. A supported claim can be demoted or retracted as new evidence arrives.

This rejects the software engineering assumption that "build state equals truth" — a single monotone, binary, terminal signal. Science requires that what we currently believe can move as the record grows.

## Target Users

- **Domain Researchers**: Need to formalize and verify research hypotheses with computational support
- **Computational Scientists**: Require end-to-end workflow from hypothesis to paper with provenance tracking
- **Research Groups**: Want reproducible, auditable research processes with explicit evidence trails

## Use Cases

### Primary Use Case: Dry-Lab Research

Full computational research workflow:
1. User provides four-pane proposal (e.g., T-1 molecular numbering system)
2. sci-adk compiles proposal into frozen **Spec** (pre-registered hypotheses + decision rules)
3. **Loop** executes experiments (hypothesis → experiment → evaluation cycles)
4. **Evidence** log accumulates results (supports/refutes/inconclusive/null)
5. **Claims** update based on evidence (non-monotone belief revision)
6. **Renderer** produces paper draft + code + evidence trail

### Secondary Use Cases

- **Hypothesis Pre-registration**: Formalize hypotheses and decision rules before seeing results
- **Evidence Auditing**: Complete provenance tracking for reproducibility
- **Null Result Publishing**: Explicit support for negative/inconclusive findings as valid outcomes

## Autonomy Modes

Two operational modes:

### Default: Full Autonomy
- User provides research proposal
- sci-adk operates independently (hypothesis selection, proof strategy, code direction, claim strength)
- User receives final paper + code + evidence trail

### Optional: Checkpoint Mode
- User approval at key decision points
- Checkpoints: hypothesis selection / proof strategy / code direction / claim strength
- Recommended for first milestone and exploratory research

## Scope and Boundaries

### In Scope

- **Dry-lab research**: Computational research with reproducible experiments
- **Domain plugins**: Extensible to specific domains (math, chemistry, ML, etc.)
- **Academic search integration**: arXiv, Semantic Scholar, PubMed, OpenReview, CrossRef
- **Isolated execution**: Docker-based environment per domain

### Out of Scope

- **Wet-lab research**: Physical experiments (future extension)
- **Human subject research**: IRB/Ethics board requirements out of scope
- **Build harness engineering**: MoAI-ADK is the tool used to construct sci-adk, not part of sci-adk's design

## Success Criteria

### First Milestone (MVP)

Minimal viable T-1 with 4 toolsets:
1. **Input Parsing**: Four-pane proposal → Spec compilation
2. **First Spec Instance**: Hypotheses + DecisionRules for T-1
3. **First Evidence**: At least one experiment run with provenance
4. **First Claim**: At least one claim with confidence score

### Technical Success Metrics

Per-spec decision rules (no hardcoded thresholds):
- Each Spec declares its own DecisionRule per hypothesis
- Claim confidence judged against that rule (not global constants)
- Null results expressible as valid claims (e.g., "no evidence for effect X")

## Relation to MoAI-ADK

### Critical Separation

This repo contains **two coexisting systems** — confusing them breaks everything:

1. **MoAI-ADK** = Build harness (tool used to *construct* sci-adk)
   - Root `CLAUDE.md`, `.moai/`, `.claude/`, `.mcp.json`
   - **Leave untouched** — this is the workshop, not the product
   - Software-engineering tools (LSP, TDD, coverage) legitimate here

2. **sci-adk** = The product being built (research compiler)
   - `src/`, `design/`, `runs/`
   - Governed by Spec/Evidence/Claim abstractions + tool policy
   - **Runtime research workflow rejects SW assumptions** (see `design/abstractions.md`)

### Policy Compliance

sci-adk's **research runtime** is governed by `design/tool-policy.md`:
- **Allowed**: Claude Code + Git + MCP, arXiv/S2, docker Python, LaTeX
- **Excluded**: LSP servers, ast-grep, Conventional Commits, Coverage thresholds
- These are excluded from *sci-adk's research workflow*, not from the build harness

## Reference

- Core Abstractions: `design/abstractions.md` (Spec/Evidence/Claim types)
- Directory Structure: `design/directory-structure.md` (layout)
- Tool Policy: `design/tool-policy.md` (runtime tool governance)
- Session 1 Handoff: `design/session-1-handoff.md` (current status + next steps)
- Recon Report: `recon/REPORT.md` (fork vs scratch decision, T-1 example)
