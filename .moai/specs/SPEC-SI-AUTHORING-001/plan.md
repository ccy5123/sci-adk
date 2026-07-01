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

M6 (added in v0.3.0) is a small, BELIEF-SIDE apparatus change: the authored `si.tex` gets its own
`references_SI.bib`, symmetric to `main.tex`/`references.bib`, so a `\citep` in the SI resolves
instead of `[?]`. It reuses existing pure helpers end to end — bib wiring mirrors `paper.py`, the
cited-only subset is a set operation over `cited_keys`/`bib_keys`, and the SI cite gate REUSES
`cite_resolution_problems` (no new checker, no LLM at bib selection). The four decisions are frozen
in `design/si-bibliography.md`; M6 does not re-decide the FROZEN SI split.

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

### SI bibliography (Pillar F, M6) — the authored `si.tex` gets its own `references_SI.bib`

M1–M5 made `si.tex` authored belief; M6 closes the citation apparatus gap. The measured gap:
the authored-SI renderer (`authored_si.py:113`) loads `natbib` (`authored_si.py:192`) but takes
no `bib_path` and emits no `\bibliography` (`authored_si.py:244`), and the compiler calls it with
no bib (`compiler.py:625`) — so a `\citep` in `si.tex` renders `[?]`. The fix is symmetric to
`main.tex`/`references.bib` and reuses existing pure helpers throughout:

- **Renderer bib wiring (mirrors `paper.py`).** Add an optional `bib_path` to
  `render_authored_si_latex`; **Where** supplied, emit `\bibliographystyle{plainnat}` +
  `\bibliography{<stem>}` before `\end{document}` (the exact pattern at `paper.py:831-834` and
  `si.py:540-543`); **When** absent, emit nothing (the `paper.py:835` no-bib branch). The renderer
  stays PURE (caller supplies the path) and FAIL-LOUD, unchanged, and determinism is preserved
  (REQ-SA-601 optional-Where + REQ-SA-601a PURE/FAIL-LOUD + REQ-SA-602/603).
- **Cited-only subset build (reuse `cited_keys`/`bib_keys`; pinned ordering, D2).** At the
  compiler's authored-SI render (`compiler.py:625`), extract the cited-key set from the
  `AuthoredSI` SOURCE bodies (`prose.py:187,219`) via `cited_keys` (`pkgreqs_checks.py:113`)
  BEFORE the final render — valid because `\cite` survives the `_slot` pipeline verbatim
  (`authored_si.py:157-177`), so the source cited keys equal the rendered cited keys (no
  `bib_path`↔`cited_keys` circularity). Filter the ONE literature pool (`_locate_bib_path`,
  `compiler.py:814`) to those keys, write the subset to `paper/references_SI.bib` via a
  co-location helper symmetric to `_colocate_bib` (`compiler.py:818`), then pass its path to the
  SINGLE final render. Pure set operation — NO LLM, no new acquisition (REQ-SA-604/605). No pool /
  no SI citations → write NO `references_SI.bib` file (D6 ABSENCE) and pass no `bib_path`
  (REQ-SA-606, mirrors `compiler.py:830-831`). Correct the stale `compiler.py:544` comment so the
  false phrase "wired into BOTH documents" is gone (REQ-SA-607, grep-asserted). The main paper's
  `references.bib` co-location is untouched (independent bibs).
- **Package symmetry (two authoring cases, D1).** In `_ensure_manuscript` (`package.py:400-456`)
  add `01_manuscript/references_SI.bib`: preserve `package_src/references_SI.bib` verbatim if
  present (symmetric to `references.bib`, `package.py:431-432`), else the cited-only subset of the
  package bib by the package SI's cited-key set. Add `_REFERENCES_SI_BIB = "references_SI.bib"`
  beside `_REFERENCES_BIB` (`package.py:72`). The `\bibliography{references_SI}` line has TWO
  distinct owners: (a) an author-supplied `package_src/si.tex` is copied VERBATIM
  (`package.py:449-451`), so the AUTHOR owns the line and the assembler ONLY lands the bib beside
  it — it MUST NOT inject wiring into the copied file (REQ-SA-608a); (b) the assembler-authored
  skeleton (`_skeleton_si_tex`, `package.py:459-482`) is wired by the assembler IFF it cites
  anything, else it omits the line and writes no `references_SI.bib` (REQ-SA-608b/610). A
  missing/wrong author bibliography is surfaced by the SI cite gate (REQ-SA-613), not repaired.
- **SI cite-resolution gate (reuse `cite_resolution_problems`).** Add, additively, a cite gate for
  `si.tex` vs `references_SI.bib`, parallel to the existing `main.tex` gate — per-run at the
  `verify.py:1012-1018` site (load `paper/references_SI.bib`, run
  `cite_resolution_problems(si_tex, si_bib)` alongside the `draft.tex` gate) and package at the
  `verify.py:1242` site (load `01_manuscript/references_SI.bib`, run the same over the package
  `si.tex`). No new checker (REQ-SA-611/612/613/614); vacuously clean for a citation-free SI
  (REQ-SA-615). This is the ONLY missing per-document check — `si.tex` is already number-audited /
  compile-checked / tool-vocab-scanned / value-fidelity-scanned.

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

### Milestone M6 (Priority Medium) — SI bibliography (`references_SI.bib`) for the authored `si.tex`

Realizes Pillar F. M1–M5 are implemented (per-run + package authored-SI, suite green). M6 gives
the authored `si.tex` its OWN bibliography, symmetric to `main.tex`/`references.bib`, so a `\citep`
in the SI resolves instead of `[?]`. All new code reuses existing pure helpers (bib wiring mirrors
`paper.py`; subset = `cited_keys`/`bib_keys`; SI gate = `cite_resolution_problems`). No re-decision
of the FROZEN SI split — the four decisions are frozen in `design/si-bibliography.md`. Sub-steps
are priority-ordered within M6 (renderer wiring first, then the per-run subset build + gate, then
the package symmetry).

- REQ-SA-601, REQ-SA-601a, REQ-SA-602, REQ-SA-603, REQ-SA-604, REQ-SA-605, REQ-SA-606,
  REQ-SA-607, REQ-SA-608, REQ-SA-608a, REQ-SA-608b, REQ-SA-609, REQ-SA-610, REQ-SA-611,
  REQ-SA-612, REQ-SA-613, REQ-SA-614, REQ-SA-615, REQ-SA-616, REQ-SA-617
- Exit: `render_authored_si_latex` (`authored_si.py:113`) accepts `bib_path`, emits
  `\bibliography{references_SI}` when supplied / nothing when absent, and stays PURE/FAIL-LOUD
  (byte-determinism preserved, other slots unchanged); the compiler (`compiler.py:625`) extracts
  cited keys from the `AuthoredSI` SOURCE bodies BEFORE the final render (D2 ordering, no
  circularity), builds + co-locates the cited-only `paper/references_SI.bib` from the ONE pool
  (`compiler.py:814`) via `cited_keys`/`bib_keys` (deterministic, no LLM), writes NO file when
  there are no citations / no pool (D6), passes the bib path to the SINGLE final render, and the
  stale `compiler.py:544` "wired into BOTH documents" phrase is grep-asserted gone (D3); the package
  path adds `01_manuscript/references_SI.bib` (`_REFERENCES_SI_BIB` constant added) and handles BOTH
  the author-supplied-verbatim case (bib landed beside the copied file, NO wiring injection —
  REQ-SA-608a) and the generated-skeleton case (assembler wires `\bibliography` iff the skeleton
  cites — REQ-SA-608b); the SI cite-resolution gate is wired additively at the `verify.py:1012-1018`
  (per-run) and `verify.py:1242` (package) sites, reusing `cite_resolution_problems` — a dangling
  `si.tex` cite FAILS (RED→GREEN) and a citation-free SI is vacuously clean; the two documents' bibs
  are independent and the main paper bib is unchanged; M6 is domain-neutral; the AC-F10
  scope-discipline "no OTHER computation changed" clause is confirmed by human diff-review
  (REVIEW-GATED); `sci-adk verify` exits 0 on a real run whose authored `si.tex` cites resolved
  keys; suite green.

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

### M6 risks

- **R12 — Wiring the SI bib to the FULL pool instead of the cited-only subset.** The easy path is
  to point `si.tex` at the same `references.bib` the main paper uses; that violates self-containment
  (the SI's printed reference list would carry the main paper's uncited-in-SI entries) and the
  cited-only decision. Mitigation: REQ-SA-604/609 mandate the cited-only subset via
  `cited_keys(si_tex)`; AC-F4/F7 assert `bib_keys(references_SI.bib) == cited_keys(si_tex) ∩ pool`
  (uncited entry absent).
- **R13 — Fabricating a bib when the pool or citations are absent.** A naive build could write an
  empty-but-present `references_SI.bib` and still emit `\bibliography`, or (worse) attempt to
  acquire a missing citation. Mitigation: REQ-SA-605/606 forbid acquisition and (D6) require the
  no-pool/no-cite path to write NO `references_SI.bib` file at all and pass no `bib_path` (no
  `\bibliography`), mirroring the main paper's missing-pool handling (`compiler.py:830-831`); AC-F5
  asserts `not (paper/references_SI.bib).exists()`.
- **R14 — SI cite gate accidentally checking `si.tex` against the wrong bib.** The gate must read
  the SI bib (`paper/references_SI.bib` per-run, `01_manuscript/references_SI.bib` package), never
  the main `references.bib`. Mitigation (D8): the SI cite gate reads `references_SI.bib` (the
  cited-only subset), never `references.bib`; because a key cited in `si.tex` but absent from the
  pool is therefore absent from `references_SI.bib`, the gate FAILS on it — a main-bib-only key
  cannot mask a dangling SI cite (the SI bib does not contain main-only keys). REQ-SA-612/613 name
  the exact SI bib path per path; AC-F8 asserts a `si.tex` cite absent from `references_SI.bib`
  FAILS per-run and package.
- **R15 — Introducing a new checker or an LLM at bib-selection.** The temptation is a bespoke SI
  bib builder or an LLM to pick "relevant" references. Mitigation: REQ-SA-605 (deterministic set
  op, no LLM) + REQ-SA-611/616 (REUSE `cite_resolution_problems`, no new checker); AC-F10 asserts
  the gate is the existing checker and no new SI acquisition/pool is added.
- **R16 — Regressing the existing `main.tex` bib or the deposit `record.tex` bib.** The SI bib must
  be strictly additive. Mitigation: REQ-SA-607/616 forbid touching `_colocate_bib` /
  `paper.py` bib emission / `si.py:540-543`; AC-F6 asserts the main paper bib is byte-unchanged and
  the two bibs are independent.

## Out of scope (this plan)

- `main.tex` / `render_paper_latex` (unchanged); the package `main.tex` authoring + skeleton logic
  (M5 touches the package `si.tex` slot, the dump destination, and the additive deposit check only).
  M6 leaves the main paper's `references.bib` wiring and `_colocate_bib` untouched.
- The JOSS tool paper `paper/paper.md` (untouched).
- Any change to what `sci-adk verify` computes over `runs/` + the record artifact, or what the
  package gate computes per-document (M5 only changes that the package `si.tex` is now authored; M6
  only ADDS a cite-resolution check for `si.tex`, parallel to the existing `main.tex` one).
- `zref-xr` / `xr` cross-document compile coupling (dropped in design §6).
- A separate SI literature-acquisition pool (M6's `references_SI.bib` is a cited-only subset of the
  ONE per-run pool), and the deposit `record.tex`'s own bib wiring (`si.py:540-543`, unchanged).
- The per-run path (M1–M4), which is already implemented and stays intact.
