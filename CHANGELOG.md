# Changelog

All notable changes to sci-adk are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

sci-adk is pre-1.0; no version has been tagged yet. Everything built so far is
listed under **Unreleased** and will be moved under a version heading at the
first tagged release.

## [Unreleased]

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

[Unreleased]: https://github.com/ccy5123/sci-adk/commits/master
