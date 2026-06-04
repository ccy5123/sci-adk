# sci-adk Constitution

> Session: sci-adk development
> Purpose: Central identity and rules for sci-adk research compiler
> Status: Active for all sci-adk work sessions
> Version: 1.0.0 (Session 2 confirmed)
> Last Updated: 2026-06-04

---

## What is sci-adk?

**sci-adk** is a **research compiler**: a system that consumes a four-pane research proposal and emits a paper draft + working code + an evidence trail.

### Core Philosophy

The deepest design principle is the separation of **record** from **belief**:

- **Record (Evidence)**: Monotone, append-only log of what happened. Null and negative results are part of the record.
- **Belief (Claim)**: Non-monotone, revisable confidence derived from evidence. A supported claim can be demoted or retracted as new evidence arrives.

This rejects the software engineering assumption that "build state equals truth" — a single monotone, binary, terminal signal.

### Reference Workflow

**T-1 (Molecular Numbering System)**: Gödel-style encoding scheme for molecular graphs using number theory. See `recon/REPORT.md` §1.1.

---

## Critical Environment Separation

This repo contains **two coexisting systems** — confusing them breaks everything:

1. **MoAI-ADK** = Build harness (tool used to *construct* sci-adk)
   - Root `CLAUDE.md`, `.moai/`, `.claude/`, `.mcp.json`
   - **Leave untouched** — this is the workshop, not the product
   - Software-engineering tools (LSP, TDD, coverage) legitimate here

2. **sci-adk** = The product being built (research compiler)
   - `src/`, `design/`, `runs/`
   - Governed by Spec/Evidence/Claim abstractions + tool policy
   - **Runtime research workflow rejects SW assumptions**

### Policy Compliance

sci-adk's **research runtime** is governed by `design/tool-policy.md`:
- **Allowed**: Claude Code + Git + MCP, arXiv/S2, docker Python, LaTeX
- **Excluded**: LSP servers, ast-grep, Conventional Commits, Coverage thresholds
- These are excluded from *sci-adk's research workflow*, not from the build harness

---

## Claude Code Collaboration Meta-Rules (7 Rules)

Source: `recon/cc-meta-rules.md`

**1. No Guessing (추측금지)**
- Verify paths with bash before acting
- Session 1 demonstrated: CC discovered MoAI installation by measuring `.claude/` state, not guessing

**2. Measurement Over Estimation (추정<측정)**
- Run actual commands to verify state
- Don't assume from inference

**3. Self-Correction (자기결론 정기의심)**
- Play devil's advocate against your own conclusions
- Session 1: CC's "LSP policy violation" optimistic conclusion was corrected by user

**4. Confidence Labels (신뢰도라벨)**
- Always indicate confidence level in assessments
- Required: `basis` text for all confidence judgments

**5. User Verification Welcome (사용자검증환영)**
- Don't defend against correction
- Session 1: User corrected CC's LSP assumption; CC accepted and updated

**6. path:line Citations (path:line인용)**
- Reference sources with file paths and line numbers
- Enables reproducible verification

**7. Null Results Are Results (null result도결과)**
- Negative/inconclusive findings are valid outcomes
- Record them in Evidence log, don't treat as "stuck"

---

## Core Abstractions

Source: `design/abstractions.md` (v0.1 CONFIRMED)

### Three Core Types

**1. Spec (Compiler Input)**
- Frozen pre-registration contract
- Immutable once accepted (amendments create new versions)
- Components: RawProposal, Hypotheses[], MethodPlan, TargetClaims[]
- Invariants: S1-S5 (amendment requires human checkpoint even in autonomous mode)

**2. Evidence (Accumulated Record)**
- Immutable, append-only log
- Components: Provenance, Result, Bearing[]
- Invariants: E1-E4 (null/negative results are valid outcomes)

**3. Claim (Compiler Output)**
- Revisable belief state derived from Evidence
- Components: ClaimStatus, Confidence, EvidenceLink[], StatusChange[]
- Invariants: C1-C6 (non-monotone status movement, explicit "contested" when evidence conflicts)

### Key Design Decision

**No Hardcoded Metrics**: Each Spec declares its own DecisionRule per hypothesis. Claim.confidence is judged against *that rule* (not global constants like "85% coverage").

---

## Tool Policy

Source: `design/tool-policy.md` (AUTHORITATIVE)

### Allowed Tools (sci-adk Runtime)

**LLM Backend**: Claude Code, GLM (fallback)
**Integration**: MCP (Model Context Protocol)
**Provenance**: Git, DVC
**Academic Search**: arXiv, Semantic Scholar, PubMed, OpenReview, CrossRef (all MCP)
**Execution**: docker (Python, SageMath, Lean 4, LaTeX per domain)
**Paper Writing**: LaTeX, BibTeX, pandoc

### Excluded Tools (sci-adk Runtime)

These are used by MoAI-ADK but **intentionally excluded** from sci-adk's research workflow:
- **LSP servers**: "syntax/type correctness = task complete" assumption rejected
- **ast-grep**: Software refactoring tool, not scientific
- **Conventional Commits**: PR automation, sci-adk's "done" ≠ PR merge
- **Coverage thresholds**: Code testing ≠ scientific verification

**Critical**: These exclusions apply to *sci-adk's research runtime*, NOT the build harness.

### Tool Addition Protocol

When adding new tools:
1. Specific use case (one line)
2. Review against excluded tools (can excluded tool replace it?)
3. Review against allowed tools (can existing tool replace it?)
4. If both no → request user approval

**Principle**: Tool addition = system surface increase = debugging/reproducibility burden. Be conservative.

---

## Directory Structure

Source: `design/directory-structure.md` (v0.1 CONFIRMED)

### Layout

```
sci-adk/
├── recon/              # READ-ONLY: Prior session reconnaissance
├── design/             # DESIGN: sci-adk specifications and decisions
│   ├── constitution.md #   This file (identity + rules)
│   ├── abstractions.md #   Core types (Spec/Evidence/Claim)
│   ├── tool-policy.md  #   Runtime tool policy
│   └── ...
├── src/sci_adk/        # COMPILER SOURCE: Python implementation
│   ├── core/          #   Spec/Evidence/Claim types
│   ├── loop/          #   Research execution loop
│   ├── runner/        #   Docker tool execution
│   ├── provenance/    #   Git + reproducibility tracking
│   ├── search/        #   Academic MCP client integration
│   └── render/        #   Claims + Evidence → LaTeX paper
├── environments/      # Docker domain images
├── tests/             # Engineering layer tests
└── runs/              # SYSTEM OUTPUT: Per-research artifacts
```

### Three-Level Type Discipline

1. **Type Specification**: `design/abstractions.md` (schema)
2. **Type Implementation**: `src/sci_adk/core/` (Python)
3. **Type Instances**: `runs/<proposal>/` (concrete data)

### Two Verification Layers

- **Engineering Layer**: `tests/` (MoAI/LSP/coverage apply here — this is fine)
- **Science Layer**: Evidence/Claim + DecisionRules (NOT tests — this is the innovation)

---

## Known Issues

- **Git ownership**: Session 1 reported "dubious ownership" (WSL-over-Windows). User must approve `git config --global --add safe.directory ...` to resolve.
- **.gitignore**: MoAI's .gitignore + sci-adk additions (runs/*/data/, LaTeX temp files)

---

## Project Documentation

Source: `.moai/project/` (generated 2026-05-26)

- **product.md**: Product overview (identity, use cases, success criteria)
- **structure.md**: Directory structure (file responsibilities)
- **tech.md**: Technical stack (Python, abstractions, tool policy)

---

## How This File Works

This file is the central entry point for sci-adk's identity and rules. All sessions working on sci-adk should read this file first to understand:

- Core philosophy (record vs belief separation)
- Two-environment separation (MoAI-ADK vs sci-adk)
- 7 CC meta-rules (collaboration protocol)
- Core abstractions (Spec/Evidence/Claim)
- Tool policy (allowed/excluded tools)
- Directory structure

### Future Migration

When sci-adk becomes a fully standalone system with its own CLAUDE.md, this file can be migrated to become the root CLAUDE.md and the MoAI-ADK build harness dependency can be removed.

Until then, this is the practical solution for ensuring sci-adk's identity is always active during development sessions.

---

**Session 2 Handoff Completed**: 2026-06-04
**Confirmed**: sci-adk constitution location = design/constitution.md
**Next**: Deliverable #4 (First milestone scope) → Implementation
