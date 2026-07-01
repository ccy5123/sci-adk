# Implementation Plan — SPEC-SI-AUTHORING-001

> Decomposition of `design/si-belief-record-split.md` (v0.4). No time estimates; milestones are
> priority-ordered. The design is FROZEN — this plan realizes it, it does not re-decide it.

## Guiding principle

The work is asymmetric by design: the BELIEF-SIDE is mostly CHARACTERIZATION (the existing gate
already audits `si.tex`), and the genuinely NEW work is small and RECORD-SIDE (relocate + rename
the dump, add a presence-only deposit-completeness check). The plan front-loads the relocation
(which frees the `si.tex` slot) and the deposit gate (the only new gate), then builds the
authored path on the freed slot, and closes with characterization tests proving the belief-side
gate is unchanged.

M1–M4 cover the PER-RUN compile path and are implemented and tested (suite 1422 green). M5 (added
in v0.2.0) applies the SAME asymmetric model to the WORKSPACE-PACKAGE submission path by SYMMETRY:
relocate the package dump, author the package `si.tex`, exempt the relocated record by
construction, and REUSE the M2 deposit-completeness checker. M5 reinforces the asymmetry — its new
work is record-side relocation + a checker REUSE (no new checker); the package gate already audits
`si.tex`, so the belief side stays characterization.

## Technical approach

### Authored `si.tex` path (Pillar A) — reuse, do not re-implement

- The authored SI is the overflow of `main.tex`, so it reuses the SAME prose pipeline
  `render_paper_latex` uses: `substitute_factrefs` (fidelity) → `_novelty_prose` (which calls
  `_latex_sanitize_prose`, preserving `\ref`/`\cite`). The render entry point for the authored
  SI assembles free-structured agent sections through this pipeline, NOT through
  `render_si_latex`.
- S-numbering convention (`\thefigure`/`\thetable` = `S\arabic{...}`) and the per-kind figure
  package guarding already exist in `si.py`'s preamble logic; the authored path keeps the
  S-numbering and the figure-package guards but drops the type-sorted record sections.
- A prose model for the free-structured SI sections lives alongside `PaperProse`/`SIProse` in
  `render/prose.py`. Default skeleton sections (Supplementary Methods / Notes / Figures /
  Tables) are OPTIONAL defaults the agent can reorganize (REQ-SA-102).
- Tables are hand-authored: a table cell that cites a recorded value is written with `\evval`
  and passes the fidelity gate cell-by-cell (REQ-SA-104). No reuse of the dump's `tabular`
  builder.
- Figure ownership is XOR across `main.tex`/`si.tex` from one shared `figures/` file set
  (REQ-SA-105); the compiler already co-locates `fig<N>` files for both documents.

### Record artifact relocation + rename (Pillar B)

- `render_si_latex` is reused VERBATIM (REQ-SA-201). The change is at the CALL SITE
  (`compiler.py:587-593`): write its output to the deposit as `record.tex`, not `paper/si.tex`.
- Rename the renderer's identity wording from "Supporting Information" to "record" (the title
  line `si.py:327`, the `\author{sci-adk (deterministic record dump)}` at `si.py:329`, the
  italic record-note `si.py:336-340`). This is presentation wording, not logic — determinism is
  preserved (REQ-SA-203). Golden-test fixtures for `si.py` update accordingly.
- Per-run tool-vocab gate EXTENSION (REQ-SA-204, the one NEW belief-side change): the per-run
  gate `_check_paper_tool_vocab` (`verify.py:826-837`) currently scans `draft.tex` ONLY and
  EXEMPTS `si.tex`. It is EXTENDED to ALSO pass the authored `si.tex` through
  `check_paper_tool_vocabulary` (it is now a submission document). The record artifact
  `record.tex` stays EXEMPT (REQ-SA-206): it is NOT passed to `check_paper_tool_vocabulary`.
  This is the RED→GREEN change (per-run `si.tex` leak currently passes → flags). Stale comments
  asserting "si.tex = record dump (EXEMPT)" (`verify.py:117-118, 826-832, 163-188`) are corrected
  here.

### Deposit-completeness gate (Pillar C) — the only new RECORD-side gate

- A PURE checker modeled on `readme_submission_readiness_problems` (`pkgreqs_checks.py:448`):
  returns `[]` when the deposit carries (a) the record artifact and (b) a "Data & code
  availability" statement, else a problem line per missing element (REQ-SA-301/302/303).
- Wired into `sci-adk verify` ADDITIVELY (REQ-SA-305): it extends the existing problem list,
  never replaces or gates the record-green / claim-reproduction audit.
- Presence-only, deterministic, no LLM (REQ-SA-304).

### Belief-side characterization (Pillar D)

- No production change for the FOUR characterization checkers. Characterization tests assert that
  the existing checkers (`_PAPER_DOCS`, P2 number-audit, value-fidelity, novelty, cross-doc S-ref;
  tool-vocab is the NEW exception handled above) still cover `si.tex` after it
  becomes authored, and that an authored `si.tex` with an unbacked number FAILS the existing P2
  (REQ-SA-401/402), and that the cross-doc S-ref gate still guards linkage (REQ-SA-403).

### Package-path authoring flow (Pillar E, M5) — apply A/B/C/D by symmetry, reuse don't reinvent

M1–M4 are implemented (per-run path, suite green at 1422). M5 mirrors them on the PACKAGE path:

- **Authored package `si.tex` (mirrors A/M3).** `package.py:_ensure_manuscript` already preserves
  an author-supplied `main.tex` from `<ws>/package_src/`; extend the SAME mechanism to preserve a
  `package_src/si.tex` (REQ-SA-501). The dump is NO LONGER the no-author fallback for the `si.tex`
  slot (REQ-SA-502) — a thin/absent package SI is valid (REQ-SA-107 applies one layer up).
- **Relocate the package dump (mirrors B/M1).** `make_si.py`'s dump logic is the package's
  `render_si_latex` and is reused verbatim (REQ-SA-504); the change is its output PATH — re-target
  `make_si.py`'s `OUT` from `01_manuscript/si.tex` to `06_provenance/record.tex` (REQ-SA-505, the
  M5 layout decision) and rename its "Supporting Information" identity wording to read as the
  record (REQ-SA-506). `package.py:_run_builders` updates the builder output label + the
  `_write_readme`/`_write_manifest` layout strings accordingly. **F2: `make_si.py` ALSO emits a
  "Data & code availability" statement into the `06_provenance/record.tex` body (REQ-SA-506a)** —
  the authoritative source the M2 checker reads (`pkgreqs_checks.py:499`); without it the relocated
  record would fail the (now-HARD) package deposit gate. Record prose (no `\evval`), so it stays
  number-audit-clean and inside the exempt artifact.
- **Tool-vocab boundary by relocation, NOT by extension (mirrors B but DIFFERENT mechanism).** The
  per-run M1 was a RED→GREEN scan EXTENSION (`si.tex` was exempt, now scanned). The package gate
  ALREADY scans `si.tex` (`verify.py:1250-1256`); M5 instead RELOCATES the record OUT of the
  scanned `01_manuscript/` dir, so the now-authored `si.tex` stays scanned and the record artifact
  at `06_provenance/record.tex` is exempt BY CONSTRUCTION (REQ-SA-507) — no exempt-list, no
  scan-list change. The `make_si.py` hand-avoidance of tool nouns stops being load-bearing.
- **Package deposit-completeness (mirrors C/M2) — pure reuse.** Reuse the existing
  `deposit_completeness_problems` (M2, `pkgreqs_checks.py:474`) at a package call site in
  `_check_package_requirements`, pointed at the package record path via a package record-path
  source symmetric to `compiler.deposit_record_path` (REQ-SA-508). Additive to
  `package_requirements_clean` (REQ-SA-510), presence-only, no LLM (REQ-SA-511). **F3 asymmetry
  (intended):** the package path computes `clean = not problems` / `passed = clean`
  (`verify.py:550,558`), so appending the deposit check to `problems` makes it a HARD gate —
  UNLIKE per-run M2, where `deposit_complete` is a separate non-gating channel
  (`verify.py:465-466`). A package is the final submission unit, so a missing record /
  availability statement is a true defect. **Fixture migration:** existing seeded-green package
  fixtures (old model: dump in `si.tex`, no `record.tex`) are migrated mechanically — re-assemble
  so the dump lands at `06_provenance/record.tex` with the availability statement in its body — to
  stay green under the now-HARD package deposit gate; no seeded run's record/verdict changes.
- **Package characterization (mirrors D).** The package number-audit / value-fidelity /
  ref-consistency / cite-resolution already scan `si.tex`; characterization tests assert they are
  unchanged in computation after `si.tex` becomes authored, and that an authored package `si.tex`
  with an unbacked number FAILS the existing package number-audit (REQ-SA-503/513).
- **Package writer (workflow).** Update `science-workflow-package` step 3 so the writer authors
  `package_src/si.tex` (REQ-SA-512); drop the "si.tex where the record dump is augmented" framing.

## Milestones (priority-ordered)

### Milestone M1 (Priority High) — Record artifact relocation + rename + tool-vocab extension

Realizes Pillar B. Re-targets the deterministic dump to the deposit's `record.tex`, renames its
identity wording to "record", EXTENDS the per-run tool-vocab gate to scan `si.tex` (keeping
`record.tex` exempt), and corrects the stale "si.tex = record dump" comments. Frees the `si.tex`
slot for M3.

- REQ-SA-201, REQ-SA-202, REQ-SA-203, REQ-SA-204, REQ-SA-206
- Exit: the deterministic dump lands as the deposit's `record.tex` (byte-identical content
  modulo the renamed identity wording); the deposit path is fixed as the single source the C-gate
  references; `si.tex` slot is free; the per-run tool-vocab gate now scans `si.tex` (RED→GREEN,
  AC-B4) while `record.tex` is NOT scanned (AC-B6); stale comments at `verify.py:117-118,
  826-832, 163-188` corrected; suite green with updated `si.py` golden fixtures.

### Milestone M2 (Priority High) — Deposit-completeness gate

Realizes Pillar C. The single new gate. Independent of M3 (it checks record-side artifacts), so
it can land right after M1 frees the relocation.

- REQ-SA-301, REQ-SA-302, REQ-SA-303, REQ-SA-304, REQ-SA-305
- Exit: a PURE deposit-completeness checker (precedent: `readme_submission_readiness_problems`)
  fails loud on a missing record artifact or missing availability statement, is additive to the
  existing record-green audit, and is covered by tests.

### Milestone M3 (Priority High) — Authored `si.tex` path

Realizes Pillar A. Builds on the M1-freed `si.tex` slot. The new belief artifact path reusing
`paper.py` machinery.

- REQ-SA-101, REQ-SA-102, REQ-SA-103, REQ-SA-104, REQ-SA-105, REQ-SA-106, REQ-SA-107
- Exit: an authored, free-structured `si.tex` renders through the reused prose pipeline; every
  measured value is `\evval`-gated; tables are hand-authored cell-by-cell; figure ownership is
  XOR with `main.tex`; S-numbering + inline plain-text S-refs preserved; thin/absent SI permitted.

### Milestone M4 (Priority Medium) — Belief-side characterization + integration

Realizes Pillar D, plus the end-to-end wiring (the authoring flow in `/sci publish` emits ① and
the authored ②, the compiler emits ③).

- REQ-SA-205, REQ-SA-401, REQ-SA-402, REQ-SA-403, REQ-SA-404
- Exit: characterization tests prove the FOUR characterization checkers (P2, value-fidelity,
  ref-consistency, novelty) are unchanged in computation, and the diff confirms the ONLY
  belief-side change is the authorized per-run tool-vocab extension (M1); an authored `si.tex`
  with an unbacked number fails the EXISTING P2; the cross-doc S-ref gate still guards linkage;
  the full compile path (① authored, ② authored, ③ record deposit) is exercised on a real run and
  `sci-adk verify` exits 0.

### Milestone M5 (Priority Medium) — Package-path authoring flow (applies M1+M3+M2 by symmetry)

Realizes Pillar E. M1–M4 (per-run) are implemented and tested (suite 1422 green). M5 closes the
symmetric gap on the WORKSPACE-PACKAGE path: relocate the package dump out of the `si.tex` slot,
make the package `si.tex` authored, exempt the relocated record by construction, and reuse the M2
deposit-completeness checker for the package. No re-decision of the FROZEN design — same model,
package layer. Sub-steps are priority-ordered within M5 (relocation first frees the slot, then the
additive package deposit check, then the authored-SI preservation + writer/skill update, closing
with package characterization).

- REQ-SA-501, REQ-SA-502, REQ-SA-503, REQ-SA-504, REQ-SA-505, REQ-SA-506, REQ-SA-506a,
  REQ-SA-507, REQ-SA-508, REQ-SA-509, REQ-SA-510, REQ-SA-511, REQ-SA-512, REQ-SA-513, REQ-SA-514
- Exit: `make_si.py`'s dump lands at `package/06_provenance/record.tex` (renamed to read as the
  record, determinism preserved) AND its body carries a "Data & code availability" statement (F2,
  REQ-SA-506a — the authoritative source the M2 checker reads); `package/01_manuscript/si.tex` is
  no longer dump-generated and an author-supplied `package_src/si.tex` is preserved verbatim
  (symmetric to `main.tex`); the package tool-vocab gate scans the authored `si.tex` but NOT
  `06_provenance/record.tex` (by construction — test asserts the same `capability:`/`docker:` token
  flags in `si.tex` but passes in `record.tex`); the M2 `deposit_completeness_problems` checker is
  wired additively into the package scan (single package record-path source, no hard-coded path) as
  a HARD gate (F3 intended asymmetry: package `passed = clean`, unlike per-run's non-gating channel)
  and fails loud naming ONE missing element at a time (record-missing first, F4); existing
  seeded-green package fixtures migrated mechanically to carry `06_provenance/record.tex` + the
  availability statement (F3, no record/verdict change); package characterization tests prove the
  four package per-document checks are unchanged in computation (an authored package `si.tex` with
  an unbacked number fails the existing
  package number-audit); `science-workflow-package` + the writer author `package_src/si.tex`;
  `package_requirements_clean` stays green on a real package exercising authored `main.tex` +
  authored `si.tex` + `06_provenance/record.tex`; suite green.

## Risks

- **R1 — Adding belief-side gate logic beyond the one authorized extension.** Most of the gate
  already exists (§8.4); the SOLE authorized belief-side change is extending the per-run
  tool-vocab gate to `si.tex` (REQ-SA-204). Mitigation: Pillar D is CHARACTERIZATION for the four
  unchanged checkers; REQ-SA-404 forbids altering what verify computes on the belief side EXCEPT
  that one extension. Any OTHER new belief-side computation is a red flag for re-reading the
  design.
- **R2 — Relocation silently dropping an audit from `si.tex`.** Moving the dump out of the
  `si.tex` slot must not remove fidelity/number-audit/novelty/cross-doc coverage from the now-
  authored `si.tex`. Mitigation: REQ-SA-205 + the M4 characterization tests assert all four
  gates still cover `si.tex`.
- **R3 — Golden-fixture churn from the rename.** Renaming "Supporting Information" → "record" in
  `si.py` changes `si.py` golden test output. Mitigation: the rename is presentation-only and
  deterministic; update fixtures in M1; assert byte-identity of the rest of the dump to confirm
  no logic drift.
- **R4 — Reusing `render_paper_latex` too literally for the SI.** The authored SI needs FREE
  structure, not the IMRaD skeleton. Mitigation: reuse the prose PIPELINE
  (sanitize/factref/novelty), not the IMRaD section ordering; the SI prose model carries
  free-structured sections.
- **R5 — Tool-vocab boundary error (the inversion risk).** The per-run gate must be extended to
  `si.tex` (REQ-SA-204) WITHOUT also scanning `record.tex` (REQ-SA-206); if `record.tex` is
  accidentally scanned, or `si.tex` is left exempt, the boundary inverts. Mitigation: REQ-SA-204
  (extend to ① + ②) and REQ-SA-206 (exempt ③) fix the boundary explicitly; the AC-B4/AC-B6 tests
  assert the SAME `capability:`/`docker:` token FLAGS in `si.tex` but PASSES in `record.tex`.

### M5 risks

- **R6 — Package record relocation regressing `package_requirements_clean` or seeded green
  packages.** Moving `make_si.py`'s output out of `01_manuscript/si.tex` changes the package
  layout that existing tests/fixtures assert; a green package must stay green modulo carrying the
  relocated record + an availability statement. Mitigation: REQ-SA-504 keeps the dump logic
  byte-identical (only the path/identity changes); REQ-SA-510 makes the deposit check additive;
  update package fixtures for the new `06_provenance/record.tex` location; assert
  `package_requirements_clean` stays green on a real package.
- **R7 — Package tool-vocab boundary (the package inversion risk).** If the relocated record were
  left in (or symlinked into) `01_manuscript/`, the package tool-vocab gate would police a record
  artifact (the exact wrong-direction failure today's `make_si.py` hand-avoidance papers over).
  Mitigation: REQ-SA-505 puts the record in `06_provenance/` (outside the scanned dir) so the
  exemption is BY CONSTRUCTION; the package test asserts the same `capability:`/`docker:` token
  flags in the authored `si.tex` but passes in `06_provenance/record.tex`. Do NOT add an
  exempt-list branch (that would be the over-engineered path).
- **R8 — Reinventing the deposit checker for the package.** The temptation is to write a second
  package-specific completeness checker. Mitigation: REQ-SA-508 mandates REUSE of the M2
  `deposit_completeness_problems`; the only new code is a package call site + a single package
  record-path source (symmetric to `compiler.deposit_record_path`). Any new checker logic is a red
  flag.
- **R9 — Drifting the package `si.tex` slot semantics from the per-run model.** The package
  `si.tex` must end up exactly as authored belief as per-run `si.tex` (REQ-SA-501/503), not a
  half-measure "augmented dump". Mitigation: REQ-SA-512 updates the writer/skill to author
  `package_src/si.tex` symmetric to `main.tex`; REQ-SA-502 forbids the dump as the `si.tex`
  fallback.
- **R10 — Availability-statement source mismatch (F2).** The M2 checker reads the availability
  statement from the RECORD ARTIFACT BODY (`pkgreqs_checks.py:499`), but `make_si.py` currently
  emits no such phrase and REQ-SA-506/512 also mention the README's availability line — so a naive
  implementation could put the statement only in the README and the (now-HARD) package deposit gate
  would still FAIL. Mitigation: REQ-SA-506a pins the authoritative source to the
  `06_provenance/record.tex` body and requires `make_si.py` to emit it there; the package C-gate
  test asserts the statement is detected from the record body, not the README.
- **R11 — The now-HARD package deposit gate silently reddening seeded packages (F3).** Because the
  package path's `package_requirements_clean = passed` (`verify.py:550,558`), adding the deposit
  check to `problems` makes it gate — so every pre-M5 seeded package (no `record.tex`, no
  availability statement) drops to RED on the first M5 run. Mitigation: REQ-SA-510 records the
  intended asymmetry AND the mechanical fixture-migration path (re-assemble so the dump lands at
  `06_provenance/record.tex` with the availability statement in its body); Run migrates the
  fixtures as part of M5 rather than treating the RED as a regression.

## Out of scope (this plan)

- `main.tex` / `render_paper_latex` (unchanged); the package `main.tex` authoring + skeleton logic
  (M5 touches the package `si.tex` slot, the dump destination, and the additive deposit check only).
- The JOSS tool paper `paper/paper.md` (untouched).
- Any change to what `sci-adk verify` computes over `runs/` + the record artifact, or what the
  package gate computes per-document (M5 only changes that the package `si.tex` is now authored).
- `zref-xr` / `xr` cross-document compile coupling (dropped in design §6).
- The per-run path (M1–M4), which is already implemented and stays intact.
