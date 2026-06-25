# sci-adk Quick Start

> sci-adk v0.1.0 — Agentic Discovery Kit (ADK)

## 1. Install

```bash
# From the sci-adk repo root:
pip install -e .

# Confirm the console script is available:
sci-adk --help
```

Optional: paperforge PDF acquisition (private repo, requires access):
```bash
pip install -e ".[tools]"
```

## 2. Run the T-1 demo (no proposal file needed)

```bash
sci-adk run --t1-demo
```

This runs the built-in T-1 molecular Godel-encoding capability over its designed
molecule set and yields an autonomous injectivity verdict via the DecisionEngine
(numeric threshold rule — no LLM invoked).

## 3. Inspect the run directory

```bash
ls runs/t1-godel/
# spec.json        — frozen Spec
# evidence/        — append-only Evidence log
# claims/          — Claim state
# checkpoints.md   — open agent checkpoints
# science.md       — science-guard findings (G1–G5)
# paper/           — LaTeX paper draft (draft.tex, references.bib)
```

## 4. Headless re-verification (no LLM required)

```bash
sci-adk verify runs/t1-godel
# Exit 0 iff every recorded Claim reproduces from the record.
# A third party can run this without Claude Code.
```

## 5. Compile your own proposal

Write a four-pane Markdown proposal and run:

```bash
sci-adk run proposal.md
```

Accepted section headings (English or Korean):
`# Background` / `# Goal` / `# Method` / `# Expected Output`

## 6. Operational layer — research workspace

Turn any directory into a disciplined sci-adk research workspace:

```bash
sci-adk init-session <dir>
```

This installs the Stop/UserPromptSubmit enforcement hooks, the `science-orchestrator`
persona, and the `/sci` command entry point. Available `/sci` commands once installed:
`plan`, `experiment`, `publish`, `verify`, `status`, `replicate`, `package`.

## 7. All tests

```bash
python3 -m pytest -q          # 1281 tests passing
python3 -m pytest -m integration -q  # integration tests (require Docker)
```

---

Full documentation: `README.md`
Design documents: `design/`
