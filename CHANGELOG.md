# Changelog

All notable changes to sci-adk are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The public surface (CLI + curated Python API) is frozen as the 1.0 contract
(`design/surface-freeze-analysis.md`); `1.0.0` will be tagged near the methods-paper
(JOSS) submission. `0.2.0` is the first tagged release.

## [Unreleased]

## [0.3.0] - 2026-06-30

### Added

- bib LaTeX-safety gate in `sci-adk verify`: a blocking check
  (`bib_latex_safety_problems`) that fails on a `references.bib` containing HTML
  entities (`&amp;`), HTML tags (`<i>`), a bare `&`, or non-standard Unicode
  spaces — the failure modes that break `bibtex`/`pdflatex`. Runs per-run and at
  the package level; names the offending entry, never rewrites it.
- `--version` flag (reads the installed package metadata).
- 15-minute try-it tutorial for external users (`docs/tutorial.md`), the landing
  page for a clean-clone first run (`git clone` -> `pip install -e .` ->
  `sci-adk verify runs/t1-godel`, verified reproducible offline).
- pyOpenSci / JOSS readiness: coverage report in CI and GitHub issue templates
  (bug report / feature request).

## [0.2.0] - 2026-06-30

### Added — public API

- Curated public Python API: `sci_adk` re-exports the 29-symbol record/belief
  surface (Spec / Evidence / Claim + `DecisionEngine` + `verify_run` /
  `verify_package`), guarded by a contract test; everything else is
  internal/unstable.

### Added — kernel spine

- Core types with invariant enforcement: Spec (S1–S5), Evidence (E1–E4),
  Claim (C1–C6) — record (append-only) vs belief (revisable) separation.
- Four-pane proposal parser (Background / Goal / Method / Expected Output;
  English and Korean section headers).
- `DecisionEngine`: threshold + Bayesian + interval numeric rules, plus a
  proof/qualitative judge rail with a mandatory verdict-trail gate.
- `sci-adk verify`: headless re-derivation of every recorded Claim plus a record
  digest (tamper-evidence); exit 0 iff all claims reproduce — no LLM required.
- Checkpoint loop (`sci-adk resolve`) re-entering a run with recorded verdicts.
- Capability-adapter seam with an enforced "kernel must not import adapter"
  invariant (F4 lint).
- T-1 capability: an injective Gödel-style molecular-graph encoding with an
  autonomous numeric injectivity verdict.
- Docker-isolated Python execution with provenance capture.

### Added — rigor and publishing layers

- Referent-typed evidence-validity enforcement (synthetic data cannot make a
  SUPPORTED *empirical* claim).
- Figure-digitization as a gated `digitized` Evidence kind (extractor ≠
  verifier).
- Science guards G1–G5 (analyticity / test-power / falsifiability / mode /
  cost) — pure, no-LLM spec-layer rigor gates surfacing findings in
  `runs/<id>/science.md`.
- Literature triggers: prior-work recording, contested status, and novelty as a
  first-class revisable Claim (2-kind: result vs method).
- Render record-fidelity spine: a deterministic spine + agent-authored belief
  narrative + a markup fidelity gate, producing a tool-agnostic paper; native
  figures and an SI record dump.
- Publishing requirements F1/F2/F3 (`pubreqs` contract + figure font/DPI policy
  + reproduction bundle), gated inside `sci-adk verify`.
- Workspace-level near-submission package (`sci-adk package`, `pkgreqs`, and a
  `package_requirements_clean` gate).
- Operational layer (`sci-adk init-session`): the `science-orchestrator`
  persona, worker and guard agents, `/sci` commands, and enforcement hooks.

### Project / release hygiene

- MIT license; `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `CITATION.cff`; CI running the unit suite on Python 3.11 and 3.12.
- CLI/API surface-freeze analysis fixing the 1.0 contract
  (`design/surface-freeze-analysis.md`); methods-paper (JOSS) draft under `paper/`.

[Unreleased]: https://github.com/ccy5123/sci-adk/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ccy5123/sci-adk/releases/tag/v0.2.0
