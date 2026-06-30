# Acceptance Criteria — SPEC-SI-AUTHORING-001

> Given-When-Then scenarios mapped to `REQ-SA-NNN`. Each scenario is observable and testable.
> [RECORD-SIDE] scenarios are the genuinely new work; [CHARACTERIZATION] scenarios prove the
> belief-side gate is unchanged. Tests are PURE/deterministic unless marked `integration`
> (Docker / real compile).

## Pillar A — Authored `si.tex` path

### AC-A1 — Authored SI reuses the prose machinery, not the dump (REQ-SA-101)
- **Given** a run with a Spec, Claims, Evidence, and agent-authored SI prose sections,
- **When** the authored-`si.tex` render path runs,
- **Then** the emitted `si.tex` is produced by the `paper.py` prose pipeline (sanitizer +
  `\evval`/`\status` substitution + `\ref`/`\cite`/`\novelty` passthrough) and is NOT the output
  of `render_si_latex` (no type-sorted "Evidence record / Quantitative data / Claims and
  verdicts" dump sections).

### AC-A2 — Free authored structure (REQ-SA-102)
- **Given** agent SI prose with sections in a NON-default order (e.g. an extended-discussion
  section before a supplementary-methods section),
- **When** the authored `si.tex` renders,
- **Then** the sections appear in the agent's authored order (no forced record-type axis); the
  optional default skeleton is used only when the agent supplies no structure.

### AC-A3 — Every measured value is fidelity-gated (REQ-SA-103)
- **Given** authored SI prose containing `\evval{<id>}{<field>}` and `\status{<hyp>}` macros,
- **When** the authored `si.tex` renders,
- **Then** each macro is substituted with its recorded value, AND
- **Given** a macro citing an UNKNOWN evidence id / field / hypothesis,
- **When** the authored `si.tex` renders,
- **Then** the render FAILS LOUD (`ValueError`) — the SI cannot state a number the record does
  not hold.

### AC-A4 — Hand-authored tables, fidelity-gated per cell; dump table logic NOT reused (REQ-SA-104)
- **Given** an authored SI table whose cells cite recorded values via `\evval`,
- **When** the authored `si.tex` renders,
- **Then** each cited cell is the recorded value (gated cell-by-cell), AND the deterministic
  dump's `tabular`/`\label{tab:s1}` builder is NOT invoked for `si.tex` (that logic appears only
  in the record artifact `record.tex`).

### AC-A5 — Figure ownership is XOR across main/SI from one shared file set (REQ-SA-105)
- **Given** a run with N main figures and M supplementary figures over one `figures/` set,
- **When** `main.tex` and the authored `si.tex` render,
- **Then** the XOR holds as a concrete binary check: let `main_labels` = the set of figure
  `\label{fig:<id>}` ids in `main.tex` and `si_labels` = the set in `si.tex`; the test asserts
  `main_labels ∩ si_labels == ∅` (no figure label appears in both documents), AND the set of
  `fig<N>` file paths each document `\includegraphics`/references is drawn from ONE shared
  `figures/` directory (the union of referenced files ⊆ the single co-located `figures/` set; no
  second file set). Both assertions are explicit set operations, not a prose judgment.

### AC-A6 — Inline plain-text S-refs + S-numbering preserved (REQ-SA-106)
- **Given** body-overflow detail pushed from `main.tex` into `si.tex` with an inline
  `(Figure S3)` written by the author,
- **When** both documents render,
- **Then** `si.tex` carries `\thefigure`/`\thetable` = `S\arabic{...}` so its 3rd captioned
  figure prints as "Figure S3", matching the main-paper plain-text citation.

### AC-A7 — Thin/absent SI permitted (REQ-SA-107)
- **Given** a run with a single hypothesis and no overflow,
- **When** the authoring flow runs,
- **Then** a short authored `si.tex` (or no `si.tex` at all) is a valid outcome — no degenerate-
  case machinery fires and the run still verifies.

## Pillar B — Record artifact relocation + rename + exemption

### AC-B1 [RECORD-SIDE] — `render_si_latex` reused verbatim, determinism preserved (REQ-SA-201)
- **Given** the same Spec/Claims/Evidence inputs,
- **When** `render_si_latex` produces the record artifact twice,
- **Then** the output is byte-identical (determinism unchanged); the renderer's record-dump
  logic is unmodified except for the identity wording (B3).

### AC-B2 [RECORD-SIDE] — Dump relocated to the deposit as `record.tex` (REQ-SA-202)
- **Given** the compiler emitting the deterministic record dump,
- **When** a run compiles,
- **Then** the dump is written to the deposit as `record.tex`, AND the `paper/si.tex` path is
  NO LONGER occupied by the dump (it is free for the authored path, or carries the authored SI).

### AC-B3 [RECORD-SIDE] — Renamed from "Supporting Information" to "record" (REQ-SA-203)
- **Given** the relocated record artifact,
- **When** it renders,
- **Then** its title/author/identity wording reads as the RECORD/provenance (e.g. the title is
  not "Supporting Information: …" and the author line does not present it as an SI sibling of the
  paper).

### AC-B4 [RECORD-SIDE / NEW] — Per-run tool-vocab gate EXTENDED to `si.tex` (REQ-SA-204)
- **RED (current behavior, documents the gap):** **Given** an authored per-run `si.tex`
  containing a forbidden tool noun (e.g. "sci-adk"), **when** the CURRENT per-run tool-vocab gate
  runs (`_check_paper_tool_vocab` scans `draft.tex` only, `verify.py:826-837`), **then** the leak
  in `si.tex` is NOT flagged — the gate passes (the bug this requirement closes).
- **GREEN (after the change):** **Given** the same per-run `si.tex` with a forbidden tool noun,
  **when** the EXTENDED per-run tool-vocab gate runs, **then** it FLAGS `si.tex` and names the
  forbidden term(s) — `si.tex` is now scanned as a submission document.
- The test asserts the transition explicitly (pre-change: not flagged; post-change: flagged), so
  the new belief-side computation is observable, not assumed.

### AC-B6 [RECORD-SIDE] — `record.tex` stays EXEMPT after the extension (REQ-SA-206)
- **Given** a `record.tex` containing `capability:`/`docker:`/`environment:` provenance tokens
  (legitimate record vocabulary),
- **When** `sci-adk verify` runs with the extended per-run tool-vocab gate,
- **Then** `record.tex` is NOT flagged (it is exempt) — the gate applies to `main.tex` + `si.tex`
  (submission) and never scans `record.tex`. A test asserts the SAME `capability:`/`docker:`
  token FLAGS in `si.tex` but PASSES in `record.tex`, fixing the exemption boundary.

### AC-B5 — Relocation drops no audit from `si.tex` (REQ-SA-205)
- **Given** the dump relocated out of the `si.tex` slot,
- **When** `sci-adk verify` runs over an authored `si.tex`,
- **Then** the fidelity, number-audit, novelty, and cross-doc S-ref gates ALL still cover
  `si.tex` (verified by AC-D1..D3).

## Pillar C — Deposit-completeness gate

### AC-C1 [RECORD-SIDE] — Complete deposit passes (REQ-SA-301)
- **Given** a deposit containing the record artifact AND a "Data & code availability" statement,
- **When** the deposit-completeness check runs,
- **Then** it returns no problems (`[]`), modeled on `readme_submission_readiness_problems`.

### AC-C2 [RECORD-SIDE] — Missing record artifact fails loud (REQ-SA-302)
- **Given** a deposit with NO record artifact,
- **When** the deposit-completeness check runs,
- **Then** it FAILS with a problem line naming the missing record artifact.

### AC-C3 [RECORD-SIDE] — Missing availability statement fails loud (REQ-SA-303)
- **Given** a deposit with NO "Data & code availability" statement,
- **When** the deposit-completeness check runs,
- **Then** it FAILS with a problem line naming the missing statement.

### AC-C4 [RECORD-SIDE] — Presence-only, no LLM, no belief judgment (REQ-SA-304)
- **Given** a deposit whose `main.tex`/`si.tex` belief content is arbitrary,
- **When** the deposit-completeness check runs,
- **Then** it judges ONLY the presence of the two record-side elements; it invokes no LLM and
  makes no claim about belief content; same inputs → same result (deterministic).

### AC-C5 [RECORD-SIDE] — Additive to the existing record-green audit (REQ-SA-305)
- **Given** `sci-adk verify` over `runs/` already green for record reproduction,
- **When** the deposit-completeness check is added,
- **Then** the existing claim-reproduction / record-green audit is unchanged and still gates;
  the deposit check only EXTENDS the problem list.

## Pillar D — Belief-side gate unchanged (characterization)

### AC-D1 [CHARACTERIZATION] — `si.tex` still audited by the FOUR unchanged checkers (REQ-SA-401)
- **Given** an authored `si.tex` on disk,
- **When** `sci-adk verify` runs,
- **Then** `si.tex` is included in `_PAPER_DOCS` and is scanned by the SAME FOUR checkers as
  `main.tex` with NO new computation: P2 number-audit, value-fidelity residual scan,
  ref-consistency, and novelty.
- **Note (not characterization):** the fifth submission-document checker, tool-vocabulary, is
  the one EXCEPTION — it is newly EXTENDED to `si.tex` per AC-B4 (the per-run gate previously
  EXEMPTED `si.tex`). It is deliberately NOT included in this "no new computation" list.

### AC-D2 [CHARACTERIZATION] — P2 now does real work on authored numbers (REQ-SA-402)
- **Given** an authored `si.tex` containing a quantitative token with NO backing in the
  recorded-value pool,
- **When** the existing P2 number-audit runs,
- **Then** P2 FAILS and names the unbacked token — the SAME checker that passed trivially over
  the old dump now does real work, with no change to what P2 computes.

### AC-D3 [CHARACTERIZATION] — Cross-doc S-ref gate still guards linkage; no compile coupling (REQ-SA-403)
- **Given** a `main.tex` citing "Figure S5" while the authored `si.tex` has only 3 SI figures,
- **When** `check_cross_doc_s_refs` runs,
- **Then** it reports the dangling "Figure S5", AND no `xr`/`zref-xr` package or cross-document
  compile dependency is introduced.

### AC-D4 [CHARACTERIZATION] — Verify computation over belief docs is unchanged except one authorized extension (REQ-SA-404)
- **Given** the full SPEC implementation,
- **When** the diff to `sci-adk verify` is reviewed,
- **Then** the only changes are (a) which artifact occupies the `si.tex` slot, (b) the ADDITIVE
  record-side deposit-completeness check, and (c) the SINGLE authorized belief-side extension of
  the per-run tool-vocabulary gate to `si.tex` (AC-B4 / REQ-SA-204, with `record.tex` exempt). NO
  OTHER checker's computation over the belief documents is altered — the four characterization
  checkers (P2, value-fidelity, ref-consistency, novelty) are byte-unchanged in what they
  compute.

## Pillar E — Package-path authoring flow (M5)

> M5 applies the A/B/C/D model to the package path by symmetry. [RECORD-SIDE] = new package work;
> [CHARACTERIZATION] = the package gate already audits `si.tex`, only its input changes. Tests are
> PURE/deterministic unless marked `integration`.

### AC-E1 [RECORD-SIDE] — Package `si.tex` is authored, not dump-generated (REQ-SA-501)
- **Given** a workspace with an author-supplied `<ws>/package_src/si.tex`,
- **When** `sci-adk package` assembles the package,
- **Then** `package/01_manuscript/si.tex` is the author file preserved verbatim (symmetric to how
  `package_src/main.tex` is preserved), AND it is NOT the output of the `make_si.py` dump (no
  type-sorted "Run index / Per-hypothesis recorded statistics" dump tables).

### AC-E2 [RECORD-SIDE] — Dump is no longer the `si.tex` fallback (REQ-SA-502)
- **Given** a workspace with NO `package_src/si.tex`,
- **When** `sci-adk package` assembles the package,
- **Then** the `make_si.py` dump is NOT written into `01_manuscript/si.tex` (a thin/absent
  authored package SI is valid, or a deterministic tool-agnostic authored-SI skeleton symmetric to
  the `main.tex` skeleton is emitted — never the record dump in the `si.tex` slot).

### AC-E3 [RECORD-SIDE] — `make_si.py` dump logic reused, determinism preserved (REQ-SA-504)
- **Given** the same workspace record,
- **When** the package record renderer (the reused `make_si.py` logic) produces the record artifact twice,
- **Then** the output is byte-identical (determinism unchanged); the dump's record-derived,
  field-agnostic construction is unmodified except for its output path + identity wording.

### AC-E4 [RECORD-SIDE / M5 DECISION] — Dump relocated to `06_provenance/record.tex` (REQ-SA-505)
- **Given** `sci-adk package` emitting the deterministic record dump,
- **When** a package assembles,
- **Then** the dump is written to `package/06_provenance/record.tex` (the M5-chosen location), AND
  `01_manuscript/si.tex` is NO LONGER occupied by the dump (it is free for the authored SI).

### AC-E5 [RECORD-SIDE] — Package record artifact renamed to read as the record (REQ-SA-506)
- **Given** the relocated package record artifact,
- **When** it renders,
- **Then** its title/identity wording reads as the RECORD/provenance (not "Supporting Information"),
  consistent with the per-run `record.tex` rename (AC-B3).

### AC-E5a [RECORD-SIDE / F2] — `make_si.py` emits the availability statement into the record body (REQ-SA-506a)
- **Given** a workspace record,
- **When** the package record renderer (`make_si.py`) writes `06_provenance/record.tex`,
- **Then** the record artifact's BODY contains a "Data & code availability" statement (matched by the
  M2 checker's `_DATA_AVAILABILITY_RE`), so the record artifact alone satisfies the
  deposit-completeness check WITHOUT relying on the package README. The test asserts the phrase is
  present in the `06_provenance/record.tex` text (the authoritative source), and that it carries no
  `\evval` macro (record prose, number-audit-clean, inside the exempt artifact).

### AC-E6 [RECORD-SIDE] — Package tool-vocab gate: authored `si.tex` scanned, record exempt by construction (REQ-SA-507)
- **Given** a package whose `06_provenance/record.tex` contains `capability:`/`docker:`/
  `environment:` provenance tokens AND whose `01_manuscript/si.tex` contains the SAME forbidden
  tool noun,
- **When** the package tool-vocabulary gate runs,
- **Then** it FLAGS the authored `01_manuscript/si.tex` and names the forbidden term(s), AND it does
  NOT flag `06_provenance/record.tex` (the record lives outside the scanned `01_manuscript/` dir, so
  it is exempt BY CONSTRUCTION — no exempt-list). The test asserts the SAME token flags in `si.tex`
  but passes in `record.tex`, fixing the package boundary (symmetric to AC-B4 + AC-B6, achieved by
  relocation, not by a scan extension).

### AC-E7 [CHARACTERIZATION] — Package per-document checks unchanged after `si.tex` becomes authored (REQ-SA-503/513)
- **Given** an authored `package/01_manuscript/si.tex` containing a quantitative token with NO
  backing in the package recorded-value pool (`RecordedValuePool.from_package`),
- **When** the existing package number-audit runs,
- **Then** it FAILS and names the unbacked token — the SAME package checker that passed over the old
  dump now does real work, with no change to what it computes; AND the package value-fidelity,
  compile/ref-consistency, and cite-resolution checks are byte-unchanged in computation (they
  already scanned `si.tex`).

### AC-E8 [RECORD-SIDE] — Package deposit-completeness reuses the M2 checker, reads the record body (REQ-SA-508)
- **Given** a package containing `06_provenance/record.tex` whose BODY carries a "Data & code
  availability" statement (the authoritative source, AC-E5a),
- **When** the package deposit-completeness check runs (the REUSED `deposit_completeness_problems`
  pointed at the package record path),
- **Then** it returns no problems (`[]`); the availability statement is detected from the RECORD
  ARTIFACT BODY (not the README); no new checker logic is introduced (the same M2 checker).

### AC-E9 [RECORD-SIDE / F4] — Package deposit-completeness fails loud, ONE element at a time (REQ-SA-509)
- **Given** a package missing `06_provenance/record.tex`,
- **When** the package deposit-completeness check runs,
- **Then** it FAILS with a single problem line naming the missing record artifact and reports NO
  availability line (the availability statement lives in the record body, so with no record there is
  nothing to carry it), AND
- **Given** a package whose `06_provenance/record.tex` IS present but its body has NO availability
  statement,
- **When** the check runs,
- **Then** it FAILS with a single problem line naming the missing availability statement. The checker
  reports ONE problem at a time in this precedence (record-missing first); it never emits both lines
  at once, and "availability without record" cannot arise — matching `pkgreqs_checks.py:491-503`
  (F4). (NOT "both named separately"; the previous wording overstated the checker.)

### AC-E10 [RECORD-SIDE / F3] — Package deposit check additive, HARD-gating in the package path, presence-only, no LLM (REQ-SA-510/511)
- **Given** a package whose other `package_requirements_clean` checks are green and whose
  `main.tex`/`si.tex` belief content is arbitrary,
- **When** the package deposit-completeness check is added,
- **Then** the existing `package_requirements_clean` checks (layout, traceability, record-green,
  per-document) are unchanged and still gate; the deposit check only EXTENDS the package problem
  list; it judges ONLY the presence of the two record-side elements; it invokes no LLM; same inputs
  → same result.
- **F3 asymmetry (intended, asserted):** because the package path sets `package_requirements_clean =
  (not problems)` and `passed = clean` (`verify.py:550,558`), a package MISSING the record artifact
  or availability statement makes `package_requirements_clean` FALSE — i.e. the deposit check is a
  HARD gate in the package path, UNLIKE per-run M2 where `deposit_complete` is a separate NON-gating
  channel (`verify.py:465-466`, not part of `passed`). The test asserts: a complete package passes
  the gate; a package missing either element FAILS the gate (`package_requirements_clean == False`).
- **F3 fixture migration (asserted):** a pre-M5 seeded-green package (dump in `01_manuscript/si.tex`,
  no `06_provenance/record.tex`) is migrated by re-assembly (dump → `06_provenance/record.tex` with
  the availability statement in its body); the test asserts the migrated package is green again under
  the now-HARD deposit gate, and no seeded run's record digest / verdict changed.

### AC-E11 [RECORD-SIDE — workflow] — Package writer authors `package_src/si.tex` (REQ-SA-512)
- **Given** the updated `science-workflow-package` skill,
- **When** its step-3 authoring guidance is read,
- **Then** it directs `Agent(expert-writer)` to author `package_src/si.tex` (symmetric to
  `package_src/main.tex`), and no longer describes `si.tex` as "a `si.tex` where the record dump is
  augmented"; the deterministic record is presented as living at `06_provenance/record.tex`.

### AC-E12 [RECORD-SIDE] — Package path is domain-neutral (REQ-SA-514)
- **Given** the M5 package implementation,
- **When** the relocation, authored-SI, and package deposit-completeness code/strings are reviewed,
- **Then** none names or assumes a domain, venue, or study (the IEAM-P8 package is an example of the
  package PATH, not a hardcoded target).

## Edge cases

- **EC-1 — No SI authored (thin record).** A run with no overflow produces no `si.tex`; the
  deposit still carries the record artifact + availability statement; verify passes (AC-A7, AC-C1).
- **EC-2 — Authored SI with zero figures/tables.** The S-numbering renames and figure-package
  guards are no-ops; cross-doc S-ref gate sees zero SI floats and flags any "Figure S<n>"
  citation in `main.tex` (AC-D3 boundary).
- **EC-3 — `record.tex` legitimately names provenance.** A record artifact full of
  `capability:`/`docker:` tokens passes verify (exempt, AC-B6); the same tokens in an authored
  per-run `si.tex` now FAIL the extended per-run tool-vocab gate (AC-B4).
- **EC-4 — Bare numeric literal in authored SI prose (honest limit).** A number typed as a bare
  literal (not via `\evval`) is outside the fidelity gate, BUT is still subject to the existing
  P2 number-audit (AC-D2) — the documented honest limit is unchanged from `main.tex`.
- **EC-5 — One missing deposit element at a time (F4).** The deposit-completeness check reports ONE
  problem in precedence order: record-missing → name the record artifact and RETURN (no availability
  line, since the statement lives in the record body); record-present-but-availability-missing →
  name the availability statement. It never emits both lines at once, and "availability without
  record" cannot arise (`pkgreqs_checks.py:491-503`). (AC-C2 then AC-C3; per-run and package share
  this one-at-a-time behavior — the earlier "vice versa / each named separately" wording overstated
  the checker.)
- **EC-6 (M5) — Package with no authored SI (thin package).** A package whose workspace has no
  `package_src/si.tex` produces no `01_manuscript/si.tex` (or a tool-agnostic skeleton); the
  package still carries `06_provenance/record.tex` + an availability statement; the package gate
  passes (AC-E2, AC-E8). The dump never lands in the `si.tex` slot.
- **EC-7 (M5) — Package record artifact legitimately names provenance.** A
  `06_provenance/record.tex` full of `capability:`/`docker:` tokens passes the package gate
  (exempt by construction, AC-E6); the SAME tokens in the authored `01_manuscript/si.tex` FAIL the
  package tool-vocab gate (AC-E6).
- **EC-8 (M5) — Existing green package upgraded.** A package that was green under the OLD model
  (dump in `si.tex`) stays green under M5 once it carries the relocated `06_provenance/record.tex`
  + an availability statement; the relocation alone does not silently fail an otherwise-complete
  package beyond the additive deposit check (AC-E10, R6 mitigation).

## Quality gate criteria

- All `REQ-SA-NNN` requirements have at least one passing acceptance test.
- New code follows sci-adk's existing render-layer purity (PURE: data in, string/report out; no
  LLM, no network; deterministic) and the F4 kernel seam (render/ imports `sci_adk.core` +
  sibling render helpers only).
- The existing test suite stays green; new behaviors are tested; Docker/compile-dependent tests
  marked `integration`.
- `sci-adk verify` exits 0 on a real run exercising ① authored, ② authored, ③ record deposit.
- Exactly ONE belief-side gate computation change is added — the per-run tool-vocab extension to
  `si.tex` (`record.tex` exempt, AC-B4/AC-B6); the four characterization checkers are unchanged
  (AC-D4 verified by diff review).
- Coverage on new modules/functions meets the project bar.
- **(M5)** `package_requirements_clean` stays green on a real package exercising authored
  `main.tex` + authored `01_manuscript/si.tex` + `06_provenance/record.tex` (whose body carries the
  "Data & code availability" statement, F2/AC-E5a); the package deposit-completeness check is
  additive AND is a HARD gate in the package path (F3 intended asymmetry, AC-E10) and reuses the M2
  checker reading the record body (AC-E8, no new checker), failing ONE element at a time (F4/AC-E9);
  pre-M5 seeded packages are migrated to the new layout (F3 fixture migration, AC-E10) with no
  record/verdict change; the package tool-vocab boundary is correct (authored `si.tex` scanned,
  record exempt by construction — AC-E6); the four package per-document checks are unchanged in
  computation (AC-E7).

## Definition of Done

- [ ] M1: deterministic dump relocated to the deposit as `record.tex` (deposit path fixed as the
      single source the C-gate references), renamed to read as the record, tool-vocab exempt;
      per-run tool-vocab gate EXTENDED to scan `si.tex` (`record.tex` exempt, AC-B4/AC-B6);
      `si.tex` slot freed; `si.py` golden fixtures updated; stale "si.tex = record dump (EXEMPT)"
      comments corrected (`verify.py:117-118, 826-832, 163-188`); suite green.
- [ ] M2: PURE deposit-completeness check (record artifact + availability statement) wired
      additively into `sci-adk verify`; fails loud on each missing element; references the M1
      deposit path as single source (no hard-coded path); tested.
- [ ] M3: authored, free-structured `si.tex` path reusing `paper.py` machinery; every value
      `\evval`-gated; hand-authored tables; figure XOR ownership (set-intersection assertion);
      S-numbering + inline S-refs; thin/absent SI permitted; tested.
- [ ] M4: characterization tests prove the FOUR belief-side checkers are unchanged (P2 does
      real work, value-fidelity / ref-consistency / novelty unchanged, cross-doc gate guards
      linkage, no `xr`/`zref-xr`); end-to-end compile + verify exits 0; AC-D4 diff review confirms
      ONLY the authorized tool-vocab extension was added on the belief side.
- [ ] M5: the `make_si.py` dump is relocated to `package/06_provenance/record.tex` (renamed to read
      as the record, determinism preserved) AND its body carries a "Data & code availability"
      statement (F2/AC-E5a — the authoritative source the M2 checker reads); `package/01_manuscript/
      si.tex` is no longer dump-generated and an author `package_src/si.tex` is preserved verbatim;
      the package tool-vocab gate scans the authored `si.tex` but not `06_provenance/record.tex` (by
      construction); the M2 `deposit_completeness_problems` checker is wired ADDITIVELY into the
      package scan (single package record-path source, reused — no new checker) as a HARD gate (F3
      intended asymmetry: package `passed = clean`, per `verify.py:550,558`), failing ONE element at
      a time (F4); pre-M5 seeded packages migrated to the new layout with no record/verdict change
      (F3); package characterization tests prove the four package per-document checks are unchanged;
      the `science-workflow-package` skill + writer author `package_src/si.tex`;
      `package_requirements_clean` stays green; suite green.
- [ ] All acceptance scenarios (AC-A1..A7, AC-B1..B6, AC-C1..C5, AC-D1..D4, AC-E1..E5, AC-E5a,
      AC-E6..E12) pass.
- [ ] All edge cases (EC-1..EC-8) covered.
- [ ] Exclusions honored: no new belief-side gate BEYOND the authorized per-run tool-vocab
      extension, no new package gate logic beyond the additive package deposit check (M2 reuse), no
      `zref-xr`, no change to what verify computes over `runs/` or per-document in the package, no
      LLM in verdict/record path, no `main.tex`/JOSS-paper change, no package exempt-list, M1–M4
      per-run path intact, domain-neutral.
- [ ] Design source `design/si-belief-record-split.md` v0.4 unmodified (this SPEC decomposes it;
      M5 applies §5/§9 to the package path without re-deciding it).
