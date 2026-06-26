# Implementation Plan — SPEC-PAPER-GATE-001

## Goal

Close the three structural leaks (L1 vacuous gate, L2 opt-in number fidelity, L3 author-owned
merged prose) so the paper-writing/packaging stage carries the same hard-gate discipline as
the rest of the engine: agents propose, the engine judges deterministically against the
record, no self-certification.

## Technical Approach

Five pillars implemented as the smallest deterministic checkers that close the holes, reusing
the existing gate language (markup/token checkers, frozen-contract discipline, fail-loud
substitution). All checkers are PURE + deterministic + third-party-re-runnable. No NLP, no LLM
in the verdict path. New checks are additive to `verify_run`/`verify_package`; the existing
record-green / claim-reproduction gate is untouched.

The keystone is M1: a paper/package that ASSERTS conclusions must not pass while its
requirements gate is silently vacuous (P1), and every reported number must trace to the record
by a reproducible audit (P2). M2 hardens citations and section order. M3 removes the
hand-typing surface structurally via a cross-run merge render.

## Milestones (priority-ordered, no time estimates)

### Milestone M1 — KEYSTONE (Priority: High) — P1 + P2

The non-negotiable core: make the gate non-vacuous and make "every number traces to the
record" a gate rather than a README claim.

- **M1.1 (P1) — Non-vacuous posture.** Resolve OD-1 (trigger predicate) and OD-8 (migration
  loudness). Make `sci-adk verify` emit a loud refusal/warning for a conclusion-bearing
  artifact with no frozen contract (REQ-PG-101). Require a frozen contract as a completion
  step in `/sci publish` and `/sci package` (REQ-PG-102/103).
- **M1.2 (P1) — Stop-hook wiring.** Add `sci-adk verify <workspace>` to the Stop hook so the
  package gate runs at session close (REQ-PG-104), preserving the per-run claim-reproduction
  audit alongside it (REQ-PG-107).
- **M1.3 (P1) — Defaults + F2 wiring.** Add Conclusion to `DEFAULT_REQUIRED_SECTIONS`
  (REQ-PG-105); add `figure_font_policy` + `image_min_dpi` to `PackageReqs` and apply the
  font/DPI checks in the package gate (REQ-PG-106).
- **M1.4 (P2) — Number-audit.** Resolve OD-2 (record-backing strategy — the keystone
  decision) and OD-3 (tokenizer scope). Implement the deterministic quantitative-token audit
  over `main.tex` + `si.tex` that FAILS on any token absent from the recorded-value pool
  (REQ-PG-201..204), comparing only against RECORDED values (REQ-PG-203). Implement the
  chosen record-backing mechanism (REQ-PG-205/206) per OD-2.

Rationale for ordering M1 first: P1 + P2 are the two leaks that let a fully hand-built
manuscript pass. Without them, M2/M3 polish gates that a hand-build still bypasses.

### Milestone M2 (Priority: Medium) — P3 + P4

- **M2.1 (P3) — Citation-key shape gate.** Resolve OD-4 (fail vs re-key) and OD-5 (WARN vs
  FAIL for unpublished). Validate every `\cite` and `.bib` key against `<Surname><Year>(+a/b)`
  for both per-run and package (REQ-PG-301/302); detect mis-disambiguated duplicate groups
  (REQ-PG-303); WARN on unpublished/DOI-less load-bearing citations (REQ-PG-304); add the
  missing per-run cite-resolution check (REQ-PG-305).
- **M2.2 (P4) — Section order + word limits.** Resolve OD-6 (FAIL vs WARN for declared
  non-IMRaD venues). Enforce section ORDER against declared/default IMRaD incl. Conclusion
  (REQ-PG-401/402/403); make abstract/body word-limit checks actually gate via P1's
  non-vacuous posture (REQ-PG-404).

### Milestone M3 (Priority: Medium-Low, architectural) — P5

- **M3.1 (P5) — Cross-run merge render.** Resolve OD-7 (record/prose boundary). Add a
  programmatic cross-run merge-render extracting numbers/tables/figures from all listed runs'
  records, leaving only prose for the agent (REQ-PG-501/502); make hand-typed record-typed
  quantities structurally impossible or P2-caught (REQ-PG-503); subsume P2 for the merged case
  while P2 remains the gate for author-supplied slots (REQ-PG-504).

M3 may land after M1/M2 because the per-slot gates (P2) already protect author-supplied
manuscripts; P5 is the structural elimination of the hand-typing surface for the merged case.

## Dependencies and Sequencing

- M1.4 (P2) depends on OD-2 and OD-3 resolution before implementation begins.
- M2.2 (P4 word limits) depends on M1.1 (non-vacuous posture) — the limits only gate once the
  contract is required.
- M3 (P5) depends on M1.4 (P2) for the author-slot fallback gate and OD-7 for the boundary.
- All milestones depend on the design rationale record `design/paper-writing-enforcement.md`
  capturing the resolved ODs.

## Risks

- **R1 — Number-audit false positives/negatives (P2).** A reported number that is a transform
  of recorded values (e.g. a ratio of two recorded means) may have no single record row.
  Mitigation: OD-2 must explicitly decide the derived-number policy; default to flagging
  (FAIL) and let the chosen strategy provide a recorded home or a macro for derived quantities.
- **R2 — Migration surprise (P1).** Flipping the vacuous-clean posture could fail existing
  runs that predate the SPEC. Mitigation: OD-8 — WARNING for pre-existing runs, REFUSAL for
  new artifacts; loud, actionable messages; documented in the design record.
- **R3 — Author ergonomics (P2 strategy ii).** Requiring `\evval`-style macros for every
  number is the strongest guarantee but heaviest author cost. Mitigation: stage strategy
  (iii) first per OD-2 recommendation.
- **R4 — Tokenizer over-reach (P2/OD-3).** Auditing section/figure/equation numbers would
  produce noise. Mitigation: explicit ignore-list in OD-3; table cells optionally deferred.
- **R5 — Venue order rigidity (P4/OD-6).** Hard-failing order breaks legitimate non-IMRaD
  venues. Mitigation: FAIL against declared order, default IMRaD, WARN when no order declared.

## Verification Strategy

- Each new gate ships with deterministic unit tests (pure checkers, no Docker).
- Docker-dependent end-to-end tests (full `verify <workspace>` over a built package) marked
  `integration`.
- The existing ~1281-test suite must stay green; characterization tests added where a check
  modifies an existing gate's output.
- The five must-pass scenarios in `acceptance.md` are encoded as tests.

## Out of Scope for This Plan

- Any NLP/semantic prose analysis, LLM-in-verdict, page-count gating, or domain/venue
  specialization (see spec.md Exclusions).
- Changes to acquisition-time citation keying (`search/citation_keys.py` ownership unchanged).
