---
name: science-workflow-publish
description: >
  sci-adk Stage 4 (publish) workflow knowledge: author the PaperProse / SIProse /
  FigureSpec hooks and render the self-contained paper/ folder via sci-adk render,
  with figures pulling y FROM Evidence by evidence_id (record fidelity), the
  within-doc paper-consistency gate, plain-text cross-doc SI references, body-order
  figure numbering, and Overleaf folder upload. Loaded by the sci hub for /sci publish
  and by expert-writer. Builds on science-foundation-rigor.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob
user-invocable: false
metadata:
  version: "1.0.0"
  category: "workflow"
  status: "active"
  updated: "2026-06-22"
  modularized: "false"
  tags: "sci-adk, publish, render, paper, figures, evidence-id, paper-consistency, si, overleaf"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["render", "paper", "figure", "evidence_id", "paper consistency", "ref label", "supporting information", "overleaf", "record fidelity"]
  agents: ["expert-writer"]
  phases: ["publish"]
---

# science-workflow-publish — Render the Paper (Stage 4)

The publish-stage procedure: render a self-contained `paper/` folder by authoring the
prose/figure hooks and letting the engine render deterministically from the recorded
Spec, Evidence, and Claims. For the discipline (record vs belief, verbs, the verify
gate) load `Skill("science-foundation-rigor")`; this skill is the HOW.

## Quick Reference (30 seconds)

- **Author WHAT, not the bytes.** Author the `PaperProse` / `SIProse` / `FigureSpec`
  hooks; the ENGINE renders the LaTeX deterministically FROM the record. This mirrors
  how the prose hook works — content + intent from the agent, faithful rendering from
  the engine.
- **Figures pull `y` FROM Evidence by `evidence_id`** — you reference the Evidence,
  you do NOT retype numbers into the figure. An unknown `evidence_id` or a
  `None`/`NaN`/`inf` value is a HARD error — that is the record-fidelity guarantee.
- **Main paper = belief narrative; SI = the full record auto-dumped.** Record/belief
  maps onto SI/paper: the SI is the deterministic dump of the record; the main paper
  is the narrative, and every quantitative statement must trace to the record.

## Implementation Guide (5 minutes)

### Author the hooks

- **`PaperProse`** — the main-paper narrative (what the paper claims and why). It must
  match the DERIVED Claim statuses: never restate a Claim more strongly than its
  status, never introduce a finding the record does not contain.
- **`SIProse`** — optional prose around the auto-dumped Supporting Information record.
- **`FigureSpec`** — figure specifications. For a data plot, the `y` values are pulled
  FROM Evidence by `evidence_id` (record fidelity). For a diagram (not a data plot),
  an image figure is supplied externally via the general figure mechanism — the
  kernel carries no domain plotting code, so any domain-specific figure tool produces
  the image file outside the kernel and you reference it.

### Render

`sci-adk render` is the ONLY way to produce the paper artifacts — do not hand-write
the final `.tex`. It emits a self-contained folder:

```
paper/
├── draft.tex        # the main paper (belief narrative)
├── si.tex           # Supporting Information (the full record, auto-dumped)
├── figures/         # body-order numbered figure files
└── references.bib   # bibliography
```

The SI is the deterministic record dump (Evidence record + quantitative table +
Claims with their C3 bases + decision rules + figures + record-integrity). The whole
`paper/` folder is self-contained for a single Overleaf folder upload.

### The paper-consistency gate

`sci-adk verify` runs a within-document consistency gate over the rendered `.tex` as a
HARD gate — a dangling `\ref`, an orphan figure, or an unsupported `\novelty` marker
makes verify exit non-zero EVEN IF the Claims reproduce. Run `sci-adk verify` as a
read-only self-check before returning.

### Publishing requirements (the frozen contract)

`/sci publish` may FREEZE a publishing contract at `runs/<id>/pubreqs.json` (via
`sci-adk pubreqs freeze`, beside `spec.json` so `render` never clobbers it) — venue,
required sections, figure font policy, raster `image_min_dpi`, reference style, length
limits, and free-form advisory conditions. It is a RECORD (frozen + digest, like the
Spec): authored TO, then checked AGAINST. The orchestrator elicits it (`AskUserQuestion`);
a worker authors to it but never freezes or relaxes it.

`sci-adk verify` enforces it as the `paper_requirements_clean` HARD gate: each declared,
deterministically-checkable requirement — sections present (`\section{...}` in
`draft.tex`), the F2 figure font policy + raster DPI, the reference style wired, word
count ≤ limit, the F3 reproduction bundle present (`paper/reproduce.py` referencing the
recorded `code_ref`s) — must pass; `advisory` items and `max_pages` (no page count
without a compile) are surfaced but NEVER gate. ABSENT `pubreqs.json` → the gate is
vacuously clean (backward compatible). A gate-bearing field cannot be relaxed after a
failure except by an explicit re-freeze (anti-moving-the-goalposts).

### Authoring constraints

- **Body-order figure numbering.** A prose `\ref{fig:<id>}` drives the numbering —
  referenced figures are numbered in the order they are first referenced in the body.
  Use a stable `\label{fig:<id>}` and reference by it; never hardcode a figure number.
- **Cross-doc SI references are PLAIN TEXT.** A main-paper → SI-figure reference must
  be plain text (e.g. "Figure S1"), NOT `\ref{fig:SI-...}` — the within-document gate
  flags a cross-doc `\ref` as dangling (cross-doc `\ref` resolution is deferred).
- **Novelty markup is HARD-gated.** A `\novelty{result|method}{hyp}{text}` marker may
  only be emitted for a kind whose novelty flag is supported on the record (a
  `found_nothing` search exists). Do not assert novelty the record does not back.

### Frozen-Spec boundary

The artifacts bind to the frozen `spec_id` + `spec_digest`; the verbs check the digest
against the on-disk Spec. Render against the Spec, Evidence, and Claims AS RECORDED.
`paper/` is ready for Overleaf folder upload only once the consistency gate passes.

## Advanced (10+ minutes)

The figure/SI design (hybrid LaTeX-native pgfplots data plots + image fallback for
diagrams; SI = auto record-dump; the verify consistency gate) is detailed in the
paper-figures-and-si design. The novelty render-time `\novelty{}` markup gate
(detection via explicit markup, HARD-fail on unsupported, scoped "to our knowledge,
as of <search date>" auto-attach on supported) is a separate track in the literature
acquisition design — render-time emission of `\novelty` should survive into the
`.tex` so verify can re-scan it.

## Works Well With

- `science-foundation-rigor` — the record-fidelity discipline this builds on.
- `science-workflow-experiment` — produced the Evidence + derived Claims being narrated.
- `expert-writer` — the worker that authors the hooks and renders the paper.
- The `evaluator-rigor` guard — advisory paper-consistency pre-check before close.
