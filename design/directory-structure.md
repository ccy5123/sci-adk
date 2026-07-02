# sci-adk Directory Structure

> Status: v0.1 CONFIRMED (2026-05-26). Language: Python (compiler implementation).
> Approved in session 1.

## The key separation: build harness vs sci-adk artifact

The repo contains **two coexisting things**, and confusing them is the trap
(a fresh session already fell into it once):

1. **MoAI-ADK build harness** — the tool used to *construct* sci-adk. Not part
   of sci-adk's design or output. Governed by the root MoAI `CLAUDE.md`.
   - `CLAUDE.md` (root) — MoAI Execution Directive (the build directive)
   - `.moai/` — MoAI state/config/manifest
   - `.claude/` — MoAI agents/skills/rules/hooks/commands/settings
   - `.mcp.json` — MoAI MCP servers incl. `moai-lsp` (build-time coding aid)
   - `.gitignore` — MoAI's
   - **Leave these in place. They are the workshop, not the product.**

2. **sci-adk itself** — the research compiler being built. This is our design
   and output. Governed by `design/` decisions + the tool policy + the
   Spec/Evidence/Claim abstractions.

Engineering layer (writing sci-adk's Python) legitimately uses MoAI/LSP/TDD/
coverage. Science layer (sci-adk's runtime research verification) rejects those
SW assumptions — see design/abstractions.md and design/tool-policy.md.

---

## sci-adk's own layout

```
sci-adk/
├── recon/                        # [READ-ONLY] prior session reconnaissance (sources)
├── design/                       # [DESIGN] sci-adk's own specs/decisions
│   ├── abstractions.md           #   Spec / Evidence / Claim (v0.1 confirmed)
│   ├── tool-policy.md            #   sci-adk runtime tool policy (authoritative)
│   ├── directory-structure.md    #   this file
│   └── handoffs/                 #   per-session handoff prompts (session-1..10, ...)
│
├── src/sci_adk/                  # [COMPILER SOURCE] the compiler itself (Python)
│   ├── core/                     #   spec.py / evidence.py / claim.py (+ invariants)
│   ├── loop/                     #   controller + decision_engine + feedback_generator (recon RC1)
│   ├── runner/                   #   generalized tool-runner over docker (recon N5)
│   ├── provenance/               #   git + dvc + seed/env capture (recon N7)
│   ├── search/                   #   academic MCP client glue (arXiv, S2)
│   └── render/                   #   Claims + Evidence -> LaTeX paper
│
├── environments/                 # [COMPILER SOURCE] docker domain images
│   └── python-base/              #   milestone image (NumPy/SciPy/SymPy/NetworkX/RDKit)
│
├── tests/                        # [COMPILER SOURCE] tests for the compiler (engineering layer)
│
└── runs/                         # [SYSTEM OUTPUT] per-research artifacts (sci-adk produces)
    └── <proposal>/               #   one research proposal = one "compilation" (e.g. T-1/)
        ├── spec.json             #     compiled Spec instance (frozen, versioned)
        ├── evidence/             #     append-only Evidence log
        ├── claims/               #     Claims (revisable belief state)
        ├── code/                 #     working code sci-adk wrote
        ├── data/                 #     DVC-tracked (.dvc pointers in git)
        └── paper/                #     LaTeX draft + .bib
```

## Three-level type discipline

- **Type specification** = `design/abstractions.md` (the schema)
- **Type implementation** = `src/sci_adk/core/` (Python: spec.py/evidence.py/claim.py)
- **Type instances** = `runs/<proposal>/` (a concrete Spec, its Evidence log, its Claims)

## Two verification layers (do not conflate)

- **Engineering layer**: does the compiler code work? → `tests/`. Normal
  software tests. MoAI/LSP/coverage apply here. This is fine.
- **Science layer**: is a research *finding* valid? → Evidence/Claim +
  per-Spec DecisionRule. NOT tests. The rejected SW assumption is conflating
  these two.

## Status: created vs planned

Created in session 1 (empty skeleton): `src/sci_adk/{core,loop,runner,provenance,
search,render}/`, `environments/python-base/`, `tests/`, `runs/`. All empty
package markers; zero logic surface.

Deferred to milestone (per tool-policy "add when needed"): `pyproject.toml`,
domain `Dockerfile`, sci-adk's own MCP wiring, DVC init, actual module code.

## Open question carried to next session

Deliverable #1 ("sci-adk CLAUDE.md / constitution") needs a home that is NOT
the root `CLAUDE.md` (which is MoAI's build directive). Where do sci-adk's
identity + the 7 CC meta-rules + tool-policy pointer live so they are active for
sessions working on sci-adk? Options to decide with the user:
(a) a `.claude/rules/` entry under the build harness that points to design/,
(b) a sci-adk constitution doc in `design/` that each session is told to read,
(c) defer until sci-adk is a standalone runnable system with its own CLAUDE.md.
