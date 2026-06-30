---
name: science-workflow-package
description: >
  sci-adk Stage 4 (package) workflow knowledge: drive the [0]-[5] near-submission
  contract to produce a workspace SUBMISSION — ONE merged main.tex + si.tex + figures
  plus the standard 6-folder reproduction package built from ALL runs. Verify every run
  green, elicit + freeze pkgreqs.json (venue + format), Agent(expert-writer) authors the
  merged manuscript FROM the record TO the contract, sci-adk package assembles the folders,
  Agent(evaluator-rigor) runs an advisory pass, sci-adk verify runs the
  package_requirements_clean HARD gate. Loaded by the sci hub for /sci package and by
  expert-writer. Builds on science-foundation-rigor.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob
user-invocable: false
metadata:
  version: "1.0.0"
  category: "workflow"
  status: "active"
  updated: "2026-06-25"
  modularized: "false"
  tags: "sci-adk, package, submission, near-submission, merged-manuscript, pkgreqs, six-folder, reproduction, value-fidelity, advisory"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["package", "submission", "near-submission", "merged manuscript", "pkgreqs", "six folder", "reproduction package", "submit", "venue submission", "package requirements"]
  agents: ["expert-writer"]
  phases: ["package"]
---

# science-workflow-package — Assemble the Submission (Stage 4)

The package-stage procedure: turn a verify-green workspace into the SUBMISSION a venue
receives — ONE merged `main.tex` + `si.tex` + figures, plus the standard 6-folder
reproduction package built from ALL runs. For the discipline (record vs belief, verbs, the
verify gate) load `Skill("science-foundation-rigor")`; this skill is the HOW.

## Quick Reference (30 seconds)

- **Package = the submission; per-run `paper/` = the record.** A package is a
  WORKSPACE-level unit that synthesizes EVERY run into one manuscript plus its full
  evidence trail. It sits ABOVE the per-run `/sci publish` render — it composes with it,
  it does not replace it. Each `runs/<id>/paper/` stays the detailed internal per-run
  record.
- **Author WHAT, assemble the spine.** `Agent(expert-writer)` authors the merged
  `main.tex` FROM the record TO the [0]-[5] contract; `sci-adk package` is the
  deterministic assembler that lays down the 6 folders from the record. The authorial
  qualities (narrative, contribution framing, honest-negative discussion) are SURFACED via
  the writer contract + an evaluator advisory pass — never a gate the engine fakes.
- **No new belief.** Every number in the package is a recorded Claim that reproduces under
  `sci-adk verify`. The package INTERPRETS / FRAMES / DISCUSSES those results; it asserts
  no un-reproduced value. The merged manuscript NAMES THE SCIENCE, not the toolchain.

## Implementation Guide (5 minutes)

### The procedure (six steps)

1. **Verify every run green ([0] gate).** Before anything else, confirm every run under
   `runs/` reproduces (`sci-adk verify <run>` per run). If any run is not green, STOP and
   report which run / which Claim failed — a package is built only on a verify-green
   record.
2. **Elicit + freeze `pkgreqs.json`.** The orchestrator (only it can prompt) asks the user
   via `AskUserQuestion` for the venue and the format fields — required sections, reference
   style, abstract max-words, body word range, free-form advisory — offering a "use the
   proposed defaults" fast-path (IMRaD sections, `runs == "all"`). Then freeze:
   `sci-adk pkgreqs freeze <ws> [--defaults | --venue … --required-section … …]` writes the
   FROZEN `<ws>/pkgreqs.json` (+ digest) at the workspace root, BESIDE `runs/` (NOT inside
   the regenerated `package/`, so re-running `package` never clobbers it). A worker never
   freezes or relaxes it. ABSENT contract → the gate runs layout/traceability but the
   venue-format checks are vacuously clean (backward compatible).
3. **Author the merged manuscript and SI.** `Agent(expert-writer)` authors ONE `main.tex` AND
   an AUTHORED `si.tex` (its body-overflow Supplementary Information, SYMMETRIC to `main.tex` —
   authored belief, NOT a record dump) synthesizing ALL runs to the [1] contract — deriving
   narrative / contribution / discussion FROM the record, authoring TO the `pkgreqs.json`
   contract: naming the science (no toolchain nouns), separating confirmatory from exploratory,
   foregrounding null / negative / refuted. The writer drops the authored documents at
   `<ws>/package_src/main.tex` and `<ws>/package_src/si.tex` (+ `package_src/references.bib`) —
   OUTSIDE `package/` so the assembler preserves them across a rebuild. The deterministic record
   is NOT authored: it is the package's record artifact at `06_provenance/record.tex` (the
   `make_si.py` dump), a sibling of the per-run `runs/<id>/record.tex`. Authorial =
   contract-driven, not gated; every number in the authored `si.tex` is still record-gated.
4. **Assemble the 6 folders.** `sci-adk package <ws>` runs the record-driven builders
   (shipped in `04_scripts/`: `build_record_index.py`, `make_si.py`, `check_package.py`)
   and lays down `01_manuscript … 06_provenance` + `MANIFEST.md` + `README.md`. It
   PRESERVES the author `main.tex`/`si.tex`/`references.bib` from `<ws>/package_src/` verbatim
   (and flips `main_tex_authored`/`si_tex_authored`); if no author manuscript/SI is present it
   emits a deterministic, tool-agnostic skeleton. `make_si.py` writes the deterministic record
   to `06_provenance/record.tex` (NOT the manuscript SI slot), with a "Data & code availability"
   statement in its body. Deterministic + idempotent: it asserts no value and never touches
   `pkgreqs.json`.
5. **Advisory review.** `Agent(evaluator-rigor)` runs an ADVISORY pass over the assembled
   package — is the contribution stated? are negatives first-class? are confirmatory and
   exploratory clearly separated? This is SURFACED to the user; it NEVER gates (no LLM in
   the verdict path).
6. **Gate + self-assessment.** `sci-adk verify <ws>` auto-detects the workspace `package/`
   and runs the `package_requirements_clean` HARD gate; the CLI prints failures like the
   other paper gates. The `README.md` carries the submission-readiness self-assessment
   naming the record-external gaps.

### The 6-folder layout ([2])

```
package/
├── 01_manuscript/   main.tex + si.tex (BOTH authored belief) + references.bib (+ figures/)
├── 02_data/         claims_all.csv (master traceability) + per-run claim CSVs
├── 03_figures/      per-run communication figures + their generators
├── 04_scripts/      the field-agnostic builders + each run's official scripts
├── 05_inputs/       inputs or copyright-respecting pointers
├── 06_provenance/   run_index.csv (spec-id · digest · verdict) + per-run verify logs
│                    + record.tex (the deterministic record dump + availability statement)
├── MANIFEST.md      the file inventory
└── README.md        overview + reproduction + submission-readiness self-assessment
```

### The gate — `package_requirements_clean` (HARD, deterministic)

`sci-adk verify` (workspace scope) enforces the package as a HARD gate — read-only, no
recompile, no LLM. It checks: the 6-folder layout + `MANIFEST.md` + `README.md` present;
`main.tex`/`si.tex` compile integrity (`\ref`↔`\label`, figure files present, braces
balanced); every `\cite*` key resolves in `references.bib`; the manuscript is tool-agnostic
(reuses `paper_tool_clean`); each declared `required_sections` is a real `\section{...}`;
the abstract word count ≤ `abstract_max_words`; the declared `reference_style` is wired
(`\bibliographystyle`); `02_data/claims_all.csv` is present with every run's claims
represented (traceability); `06_provenance/run_index.csv` is present and every listed run
reproduces (the record audit); `\evval`/`\status`-marked numbers re-derive from the record
(reuse the reframe value-fidelity gate); the `README.md` carries a submission-readiness
section; and the deposit is complete — `06_provenance/record.tex` is present and its body
carries a "Data & code availability" statement (reuses the per-run deposit-completeness
checker; in the package path this is a HARD gate). The deterministic record at
`06_provenance/record.tex` is EXEMPT from the tool-vocab gate by construction (the gate reads
only `01_manuscript/`), so it may legitimately name provenance. SURFACED as ADVISORY (never
gated): `body_word_range`, free-prose numbers not
behind `\evval`, and the §4 evaluator qualities. A gate-bearing field cannot be relaxed
after a failure except by an explicit re-freeze (anti-moving-the-goalposts).

### The HARD constraints (the discipline this obeys)

- **No LLM in the verdict path.** Every requirement that GATES the package is a
  deterministic checker folded into `sci-adk verify`. Authorial qualities that cannot be
  checked deterministically are SURFACED as advisory, never a pass/fail the engine fakes.
- **Tool-agnostic merged paper.** `main.tex` + `si.tex` name the science, not the
  toolchain (the `paper_tool_clean` rule extends to the merged manuscript).
- **Record / belief separation.** No new empirical belief: every number is a recorded
  Claim that reproduces. The package frames and discusses those results; it asserts no
  un-reproduced value.
- **Frozen contract.** `pkgreqs.json` is a frozen contract (digest, like the Spec and
  `pubreqs.json`); relaxing a gate-bearing field needs an explicit amendment re-freeze.

## Advanced (10+ minutes)

The [0]-[5] canonical contract and the resolved decision-forks (PF-1..7) are detailed in
the near-submission-package design. Two relationships matter at the boundary:

- **Package vs per-run publish.** `/sci publish` (per-run) renders `runs/<id>/paper/` — the
  internal record for one run, with `runs/<id>/pubreqs.json` as its per-run format gate.
  `/sci package` (this workflow) produces the workspace submission across ALL runs. When a
  workspace has MORE THAN ONE run, "render the paper / write up / submit" is the package;
  per-run `publish`/`render` still works for a single run or a mid-work record, but the hub
  WARNS when it is used as a stand-in for a multi-run submission ("this produces the
  internal per-run record, not the submission — use `/sci package`"). Route-to-package +
  warn, never a hard refuse.
- **If stuck ([5]).** Do not fabricate; report which Claim is missing. If the result is
  thin, down-scope the venue honestly (brief report / negative-result note) — never inflate
  to fill a section.

## Works Well With

- `science-foundation-rigor` — the record / belief discipline this builds on.
- `science-workflow-publish` — the per-run render that produced each `runs/<id>/paper/` the
  package co-locates as the internal record.
- `science-workflow-experiment` — produced the Evidence + derived Claims being synthesized.
- `expert-writer` — the worker that authors the merged manuscript to the contract.
- The `evaluator-rigor` guard — advisory contribution/negatives pass before the gate.
