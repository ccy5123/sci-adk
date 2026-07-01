---
id: SI-AUTHORING-001
version: 0.3.1
status: draft
created: 2026-07-01
updated: 2026-07-01
author: cyjoe
priority: high
issue_number: null
---

# SPEC-SI-AUTHORING-001 — Authoring-Flow SI: belief is authored, the record is the deposit

## HISTORY

- 2026-07-01 (v0.1.0): Initial draft. Decomposes the FROZEN, SPEC-ready design
  `design/si-belief-record-split.md` (v0.4) into testable requirements. The design relocates
  the record/belief boundary by ARTIFACT TYPE: `main.tex` and `si.tex` are both AUTHORED
  belief (gated by the existing fidelity + cross-doc gates), and the auditable RECORD is the
  data/code deposit (`runs/` + `sci-adk verify`) which already exists. Today's
  `render_si_latex` deterministic dump is RELOCATED into the deposit as the retained `record`
  artifact (code reused verbatim). The measured key fact (design §8.4): `verify.py` already
  audits `si.tex` as a manuscript, so the belief-side gate is UNCHANGED — the only new gate
  work is a small RECORD-SIDE deposit-completeness check. This SPEC supersedes the render
  layout described in `design/render-architecture-reframe.md` for the SI artifact only (the
  paper `draft.tex`/`main.tex` path is unchanged).
- 2026-07-01 (v0.2.0): M5 added — applies the SAME authoring-flow model to the PACKAGE
  submission path (design §9: the `package` path is explicitly IN SCOPE). M1–M4 covered the
  PER-RUN compile path (`runs/<id>/paper/` + the per-run deposit `runs/<id>/record.tex`); they
  are implemented and tested (suite green, 1422 passing). M5 closes the symmetric gap on the
  WORKSPACE-PACKAGE path: the package builder (`render/package.py` via the shipped
  `04_scripts/make_si.py`) still emits `package/01_manuscript/si.tex` as a deterministic
  record DUMP. By SYMMETRY with M1 (relocation) + M3 (authoring) + the M1 tool-vocab boundary,
  M5 makes the package `01_manuscript/si.tex` AUTHORED belief (authored by the package writer,
  symmetric to how `main.tex` is already authored), RELOCATES the deterministic dump to the
  package's provenance area as a record artifact, EXEMPTS that record artifact from the
  package tool-vocab gate while keeping the now-authored `si.tex` scanned, and extends the
  M2 deposit-completeness precedent to the package layout. M5 does NOT re-decide the FROZEN
  design — it applies the model the design already set (`design/si-belief-record-split.md`
  v0.4 §5: `si.tex` = authored belief, the deterministic dump = a relocated record artifact)
  to the package layer. The package-INTERNAL layout choices the design did not fix (which
  folder holds the relocated record artifact, its exact filename) are decided here and marked
  as M5 decisions.
- 2026-07-01 (v0.3.0): M6 added — the authored `si.tex` (②) gets its OWN bibliography file
  `references_SI.bib`, symmetric to how `main.tex`/`draft.tex` uses `references.bib`. Measured
  gap: the authored-SI renderer `render_authored_si_latex` (`authored_si.py:113`) adds
  `\usepackage{natbib}` (`authored_si.py:192`) but takes NO `bib_path` and emits NO
  `\bibliography{}` (ends at `\end{document}`, `authored_si.py:244`), and the compiler calls it
  with no bib (`compiler.py:625`) — so any `\citep`/`\cite` in `si.tex` renders `[?]`. M6 wires
  the authored-SI renderer for a bib, builds + co-locates a CITED-ONLY `references_SI.bib`
  (subset of the ONE per-run literature pool `runs/<id>/artifacts/literature/references.bib`,
  `compiler.py:814`), applies the same treatment to the package path
  (`01_manuscript/references_SI.bib`), and ADDS a cite-resolution gate for `si.tex` vs
  `references_SI.bib` (per-run `verify.py:1012-1018`, package `verify.py:1242`) parallel to the
  existing `main.tex`-vs-`references.bib` gate. The four decisions are FROZEN in the decision
  record `design/si-bibliography.md` (v1.0); M6 does NOT re-decide the FROZEN SI split
  (`design/si-belief-record-split.md` v0.4 remains the single source for that). Requirement id
  prefix `REQ-SA-6xx`. Pillar F (below). This is a belief-side apparatus change:
  `references_SI.bib` is co-located with the authored belief document ②, is NOT a new record
  artifact, and its subset selection is DETERMINISTIC (scan `\cite*` keys, filter the pool — no
  LLM).
- 2026-07-01 (v0.3.1): M6 / Pillar F revised per an independent plan-auditor pass (3 Major +
  5 Minor defects; the four confirmed decisions + REQ-SA numbering are unchanged). Fixes:
  (D1) REQ-SA-608 split by case — an author-supplied `package_src/si.tex` is copied VERBATIM
  (`package.py:449-451`), so the AUTHOR owns its `\bibliography{references_SI}` line and the
  assembler ONLY lands `references_SI.bib` beside it (no wiring injection); ONLY the generated
  skeleton (`package.py:459-482`) is wired by the assembler. The SI cite gate (REQ-SA-613)
  surfaces a missing/wrong author bibliography. (D2) REQ-SA-604 pins the subset-build ordering:
  cited keys are extracted from the authored SI SOURCE (`AuthoredSI` section bodies,
  `prose.py:187,219`) BEFORE the final render (enabled by `\cite` surviving the `_slot` pipeline
  verbatim, `authored_si.py:157-177`), then the cited-only subset is built and passed as
  `bib_path` to the single final render — no circularity. (D3) REQ-SA-607/AC-F6 make the stale
  `compiler.py:544` comment correction a grep-testable exit criterion (assert the false phrase
  "wired into BOTH documents" no longer appears at that site). (D6) REQ-SA-606/AC-F5 choose
  ABSENCE: no citations / no pool → the compiler SHALL NOT write `references_SI.bib`. (D7)
  REQ-SA-610 gets a direct package-skeleton acceptance assertion (AC-F7d). (D8) plan.md R14
  mitigation rewritten. (D4) Pillar B ids reordered 204→205→206. (D5) REQ-SA-601 re-tagged
  Optional (Where) with the PURE/FAIL-LOUD invariant split into REQ-SA-601a (Ubiquitous). No
  `src/` change; design decisions in `design/si-bibliography.md` (bumped to v1.1) unchanged in
  substance.

---

## Context and Motivation

sci-adk's deepest split is RECORD (append-only evidence) vs BELIEF (revisable claims). The
render layer turns Claims + Evidence into a LaTeX paper. After `render-architecture-reframe.md`,
`main.tex` became an agent-authored belief narrative, but `si.tex` was left as a deterministic
record DUMP (`render/si.py:render_si_latex`) organized by record TYPE. The design
`si-belief-record-split.md` diagnoses this as a MISLOCATED record/belief boundary:

- A type-sorted dump (all Evidence → table → all Claims → all Figures) is machine-natural but
  reader-hostile, and it has no authorial through-line connecting the `\evval` numbers in the
  main paper to their backing.
- Real scientific authoring is three layers distinguished BY ARTIFACT TYPE, not prose density:
  main paper (authored belief) · SI PDF (authored belief, overflow of main) · data deposit
  (the record). The auditable record was never the SI; in sci-adk it is the deposit
  (`runs/` + `sci-adk verify`).

The correction (design §5): the three correctly-typed artifacts are

1. **main.tex** — headline belief narrative (`render_paper_latex`, UNCHANGED).
2. **si.tex** — extended belief: an AUTHORED overflow of main, FREE structure, captioned
   figures + hand-authored tables + extended discussion, every measured value `\evval`-gated,
   plain-text "Figure S<n>" refs to/from main. A NEW authoring path that REUSES the `paper.py`
   machinery, NOT the `si.py` dump.
3. **deposit** — `runs/` + `sci-adk verify` + a "Data & code availability" statement + ONE
   retained deterministic record artifact (`record.tex`/`.pdf` = today's `render_si_latex`
   output, RELOCATED into the deposit and re-named from "SI" to "record", code reused
   verbatim).

This SPEC is a **render-layer + deposit change to sci-adk (the product)**, built via the MoAI
build harness. It is scoped to the domain-journal / `package` submission path.

## Key measured facts (the SPEC must encode, not re-decide)

Measured from the current source during the Plan phase (file:line evidence below). These bound
what is NEW work (record-side) vs what is CHARACTERIZATION of existing behavior (belief-side).

- **Most of the belief-side gate over `si.tex` already exists (FOUR gates, characterization).**
  `verify.py:114` — `_PAPER_DOCS = ("draft.tex", "si.tex")`; the P2 number-audit runs over both
  (`verify.py:908,1145`), as do value-fidelity (the factref residual scan), ref-consistency,
  novelty, and cross-doc S-ref. When `si.tex` was a dump, P2 passed trivially (dump = record);
  now that `si.tex` is AUTHORED, the SAME wiring does REAL work auditing the authored numbers
  against the record pool. **These four gates open NO new verification hole; their computation
  is unchanged (only the input — now authored — differs). This is CHARACTERIZATION.**
- **EXCEPTION (the one belief-side change): per-run tool-vocabulary currently EXEMPTS `si.tex`,
  and extending it is NEW work.** Measured: the PER-RUN tool-vocab gate scans ONLY `draft.tex`
  (`verify.py:826-837`, `_check_paper_tool_vocab` docstring: "the SI is openly the record dump
  ... it is never scanned"). The gate scans `si.tex` ONLY in the PACKAGE path
  (`verify.py:1250-1256`, the package tool-vocab scan; the package number-audit is at
  `verify.py:1210-1215`). Because authoring ② makes `si.tex` a SUBMISSION belief document, the
  per-run tool-vocab gate MUST be EXTENDED to scan `si.tex` (with `record.tex` staying EXEMPT).
  This is NEW record/belief-boundary work, NOT characterization — it is the single place
  authoring ② changes what the per-run gate computes. (Design §8.4: the tool-agnostic gate
  applies to ① AND ②.)
- **Linkage already gated without compile coupling.** `consistency.py:22-31,198`
  (`check_cross_doc_s_refs`) already prevents a dangling plain-text "Figure S<n>" by counting
  the SI's float environments. `zref-xr` is DROPPED (design §6) — do NOT spec it.
- **The retained record artifact stays tool-vocabulary EXEMPT.** As the record / provenance,
  the relocated `record.tex` legitimately names `capability:…`, `docker:…`, `environment:…`.
  AFTER the per-run extension above, the tool-agnostic gate applies to ① (`main.tex`) AND ②
  (`si.tex`) — the submission documents — while ③ (`record.tex`) is EXEMPT. `record.tex` is
  by-construction clean on number-audit (it IS the record).
- **NEW work is small: one belief-side extension + one record-side gate.** (1) extend the
  per-run tool-vocab gate to scan `si.tex`, `record.tex` exempt (belief-side, above); (2) a
  record-side deposit-completeness check: the retained record
  artifact present + a "Data & code availability" statement present. Precedent:
  `pkgreqs_checks.py:448 readme_submission_readiness_problems` (a PURE, deterministic check
  returning a single problem line when an expected section is absent).
- **Relocation target.** `compiler.py:587-593` writes `render_si_latex(...)` output to
  `paper_dir / "si.tex"`. The relocation re-targets the deterministic dump to the deposit's
  `record.tex` and frees the `si.tex` slot for the authored overflow path.

---

## Key measured facts — the PACKAGE path (M5; symmetric to the per-run facts above)

Measured from the current source during the M5 Plan phase. M1–M4 fixed the PER-RUN compile
path; the WORKSPACE-PACKAGE path still carries the OLD model and is the M5 gap. These facts
bound what is NEW (record-side) vs CHARACTERIZATION on the package path.

- **The package `si.tex` is STILL the record dump (the gap).** `render/package.py:298-304`
  runs the shipped `04_scripts/make_si.py` builder in-process and labels its output
  `outputs["01_manuscript/si.tex"] = "Supporting Information record dump (record-derived)"`.
  `make_si.py` writes `package/01_manuscript/si.tex` as a type-sorted dump (index table +
  per-hypothesis claims table) — the package analogue of the per-run `render_si_latex` dump
  M1 relocated. So on the package path `si.tex` is NOT yet authored belief; this is exactly
  the pre-M1/M3 per-run state, one layer up.
- **`main.tex` is ALREADY authored on the package path (the symmetry anchor).**
  `package.py:385-425` (`_ensure_manuscript`) PRESERVES an author-supplied
  `<ws>/package_src/main.tex` verbatim (`main_tex_authored = True`) and only emits a
  deterministic skeleton when none is supplied. The `science-workflow-package` skill step 3
  has `Agent(expert-writer)` author `main.tex` (and currently "a `si.tex` where the record
  dump is augmented") into `package_src/`. M5 makes `si.tex` follow `main.tex`: authored from
  `package_src/`, not generated.
- **The package tool-vocab gate ALREADY scans `si.tex` (and the dump dodges it by hand).**
  `verify.py:1250-1256` scans BOTH `01_manuscript/main.tex` AND `01_manuscript/si.tex` for
  tool-vocab leaks. Because today's `si.tex` is the record dump, `make_si.py:165-166` HAND-
  AVOIDS toolchain nouns in its prose ("the package gate checks si.tex tool-agnostic too":
  "outcome" not "verdict", "deterministic archive" not "append-only") so the record dump can
  pass a gate meant for belief. This is the inverted boundary M5 corrects: the tool-agnostic
  gate should apply to AUTHORED belief, and the record artifact should be EXEMPT (it
  legitimately names provenance) — exactly the per-run REQ-SA-204/206 boundary, applied to
  the package. **Unlike the per-run path (where M1 was a RED→GREEN extension that added a new
  scan), the package gate ALREADY scans `si.tex`; M5's change is to make the SCANNED `si.tex`
  genuinely authored and to relocate the record OUT of the scanned slot so the gate stops
  policing a record artifact.**
- **The M2 deposit-completeness checker already exists and is package-shaped-ready.**
  `pkgreqs_checks.py:474 deposit_completeness_problems(record_path)` is PURE, presence-only,
  takes an already-resolved `record_path`, and detects a "Data & code availability" statement
  (`_DATA_AVAILABILITY_RE`). M2 wired it for the per-run deposit via `deposit_record_path`
  (`compiler.py:97`). M5 REUSES this exact checker for the package, pointing it at the package
  record artifact — no new checker logic, only a new call site + a package record-path source.
- **The package record-artifact LOCATION is unspecified by the design (an M5 decision).** The
  design fixed the MODEL (a relocated record artifact in the provenance/record area) but not
  the package-internal folder. By symmetry with per-run `runs/<id>/record.tex` (the run dir IS
  the deposit) and the existing 6-folder layout, the natural home is `06_provenance/`
  (`render/package.py:23-30`: "`06_provenance/  run_index.csv + per-run verify logs`" — the
  provenance/record floor). **M5 DECISION: the relocated package record artifact is
  `package/06_provenance/record.tex`.** It is OUTSIDE `01_manuscript/`, so it is EXEMPT from
  the package number-audit / tool-vocab / value-fidelity scans (which read only
  `01_manuscript/main.tex` + `01_manuscript/si.tex`, `verify.py:1130-1132,1181-1182`) BY
  CONSTRUCTION — the same "outside the scanned dir" exemption that makes per-run `record.tex`
  exempt. This path is the SINGLE SOURCE the package deposit-completeness check references.

---

## Key measured facts — the SI bibliography (M6)

Measured from the current source during the M6 Plan phase. These bound the NEW work (wire a
bib into the authored SI + build the cited-only subset + extend the cite gate) and confirm
the symmetry anchors (main paper + record dump already wire a bib). The four decisions are
FROZEN in `design/si-bibliography.md`; this SPEC encodes them, it does not re-decide them.

- **The authored-SI renderer has NO bib wiring (the gap M6 closes).**
  `authored_si.py:113` — `render_authored_si_latex(si, spec, claims, evidence)` has NO
  `bib_path` parameter. The preamble adds `\usepackage{natbib}` at `authored_si.py:192`, but
  the render ends at `\end{document}` (`authored_si.py:244`) with NO `\bibliography{}` line.
  A `\citep`/`\cite` the author writes therefore prints `[?]` — the `natbib` package is loaded
  but no bibliography is attached. This is the single renderer gap.
- **The compiler calls the authored-SI renderer with no bib passed.**
  `compiler.py:625` — `render_authored_si_latex(si, spec, claims_list, evidence_list)`; no SI
  bib is co-located and none is passed. The compiler co-locates the MAIN paper's bib
  (`_colocate_bib`, `compiler.py:582,832`) but nothing for the SI.
- **Stale comment (must be corrected, F6).** `compiler.py:544` ("The co-located
  `references.bib` is wired into BOTH documents (the SI's `\citep` resolved too).") describes
  the OLD record-dump path (`render_si_latex` DID take `bib_path`, `si.py:540-543`), not the
  new authored `si.tex`. It is FALSE for the authored ② and MUST be updated when M6 lands.
- **Both siblings already wire a bib (the symmetry anchors, characterization).**
  main paper `paper.py:831-834` (`\bibliographystyle{plainnat}` + `\bibliography{<stem>}` when
  a `bib_path` is supplied); the deposit record dump `si.py:540-543` (same wiring; takes
  `bib_path`). M6 makes the authored `si.tex` structurally identical to `main.tex`: one
  authored `.tex` + one co-located `.bib`.
- **The per-run literature pool is ONE file (the subset source).**
  `compiler.py:814` (`_locate_bib_path`) — `runs/<id>/artifacts/literature/references.bib` is
  the run's ONE literature pool, co-located to `paper/references.bib` (`compiler.py:582,832`).
  `references_SI.bib` is a SUBSET of this pool (cited-only), NOT a separate acquisition.
- **The subset selection is a pure, deterministic pair of existing helpers (no LLM).**
  `pkgreqs_checks.py:113` `cited_keys(tex)` (every distinct `\cite*` key in a `.tex`, sorted,
  PURE) + `pkgreqs_checks.py:124` `bib_keys(bib)` (every entry key in a `.bib`, PURE). The SI
  subset = pool entries whose key is in `cited_keys(si_tex)`. No model, no network.
- **The cite-resolution gate today checks the MAIN manuscript only (the gate gap M6 closes).**
  Per-run: `verify.py:1012-1018` reads `paper/references.bib` and runs
  `cite_resolution_problems(draft_tex, bib)` over `draft.tex` only — `si.tex` is NOT
  cite-checked. Package: `verify.py:1242` runs `cite_resolution_problems(main_tex, bib)` over
  `main.tex` only; `si_tex` is number-audited / compile-checked / tool-vocab-scanned /
  value-fidelity-scanned (`verify.py:1212,1222,1254,1264`) but is NOT passed to
  `cite_resolution_problems`. M6 adds the parallel `si.tex`-vs-`references_SI.bib` gate on both
  paths, reusing the SAME pure `cite_resolution_problems` checker (`pkgreqs_checks.py:129`).
- **The package ships ONE shared bib today (the package gap).**
  `package.py:431-437` (`_ensure_manuscript`) copies `package_src/references.bib` to
  `01_manuscript/references.bib`; the merged `main.tex` wires `\bibliography{references}`
  (`package.py:543-544`). The authored `package_src/si.tex` is preserved verbatim
  (`package.py:449-451`) but shares that ONE `references.bib` and wires no SI bib. M6 adds a
  cited-only `01_manuscript/references_SI.bib` and wires the package `si.tex` to it.

---

## Terminology

- **① / main.tex**: the headline belief narrative, rendered by `render_paper_latex`. Unchanged
  by this SPEC.
- **② / si.tex**: the authored Supporting Information — a belief artifact, the overflow of ①.
  Produced by the NEW authoring path (this SPEC), reusing the `paper.py` prose machinery.
- **③ / the deposit**: `runs/` + `sci-adk verify` + the "Data & code availability" statement +
  the ONE retained deterministic record artifact (`record.tex`/`.pdf`).
- **record artifact (`record.tex`)**: the relocated, renamed output of today's
  `render_si_latex` — the deterministic record dump, demoted from "SI sibling" to the deposit's
  retained record. Tool-vocabulary EXEMPT.
- **deposit-completeness**: the record-side gate that the deposit carries (a) the retained
  record artifact and (b) a "Data & code availability" statement.
- **fidelity gate**: `\evval`/`\status` record-faithful substitution (`render/factref.py`),
  FAIL-LOUD, spanning ① and ②.
- **cross-doc S-ref gate**: `consistency.check_cross_doc_s_refs` — counts the cited document's
  S-numbered floats and reports a main→SI "Figure/Table S<n>" that points past that count.

### M5 (package-path) terms

- **the package**: the WORKSPACE-level SUBMISSION assembled by `render/package.py` — ONE merged
  `main.tex` + `si.tex` + figures in `package/01_manuscript/`, plus the standard 6-folder
  reproduction bundle, built from ALL runs. Distinct from the per-run `runs/<id>/paper/`.
- **package ② / `01_manuscript/si.tex`**: the package's authored Supporting Information — the
  package analogue of per-run ②. Authored by the package writer (symmetric to package
  `main.tex`), NOT generated by `make_si.py`.
- **package record artifact / `06_provenance/record.tex`** [M5 DECISION]: the relocated,
  renamed output of the `make_si.py` dump LOGIC — the package's deterministic record renderer,
  demoted from the `01_manuscript/si.tex` slot to the package provenance floor. Tool-vocabulary
  EXEMPT (outside `01_manuscript/`, by construction).
- **package deposit-completeness**: the record-side presence check that the package carries (a)
  the package record artifact (`06_provenance/record.tex`) and (b) a "Data & code availability"
  statement. Reuses `deposit_completeness_problems` (M2).
- **the package writer**: `Agent(expert-writer)` under `science-workflow-package`, which already
  authors `package_src/main.tex`; M5 extends it to author `package_src/si.tex`.

### M6 (SI-bibliography) terms

- **`references_SI.bib`**: the authored SI's OWN bibliography file — a co-located `.bib`
  sibling of `si.tex`, symmetric to how `references.bib` is the sibling of `main.tex`/
  `draft.tex`. Belief-side apparatus (part of the authored submission document ②), NOT a
  record artifact.
- **the literature pool**: the run's ONE acquired bibliography,
  `runs/<id>/artifacts/literature/references.bib` (`compiler.py:814`, co-located to
  `paper/references.bib`). `references_SI.bib` is a cited-only SUBSET of it.
- **cited-only subset**: the deterministic construction of `references_SI.bib` — the pool
  entries whose key is in the SI's cited-key set, and NO uncited entries. The cited-key set is
  extracted from the authored SI SOURCE (`AuthoredSI` section bodies, `prose.py:187,219`) via
  `cited_keys` (`pkgreqs_checks.py:113`) BEFORE the final render (D2 ordering), well-defined
  because `\cite` survives the `_slot` pipeline verbatim (`authored_si.py:157-177`). Pure set
  operation, no LLM.
- **SI cite-resolution gate**: the NEW belief-side gate — every `\cite*` key in `si.tex`
  resolves in `references_SI.bib`, per-run and package. Parallel to the existing
  `main.tex`-vs-`references.bib` gate; REUSES `cite_resolution_problems` (`pkgreqs_checks.py:129`).

---

## Requirements (EARS)

Requirement IDs use the `REQ-SA-NNN` prefix. Pillars: A (authored si.tex path), B (record
artifact relocation + rename + exemption), C (deposit-completeness gate), D (belief-side gate
characterization) — all PER-RUN (M1–M4). Pillar E (REQ-SA-5xx, M5) applies the SAME model to
the PACKAGE path. Pillar F (REQ-SA-6xx, M6) gives the authored `si.tex` its own
`references_SI.bib` (belief-side apparatus), symmetric to `main.tex`/`references.bib`. Each
requirement is tagged **[RECORD-SIDE]** (genuinely new work) or
**[BELIEF-SIDE / CHARACTERIZATION]** (confirms existing behavior is preserved; no new gate
logic). Keyword conventions: **shall** (ubiquitous), **When** (event-driven), **While**
(state-driven), **Where** (optional/feature), **If…then** (unwanted-behavior).

### A — Authored `si.tex` path (reuses `paper.py` machinery)

- **REQ-SA-101 (Ubiquitous) [RECORD-SIDE is NO; this is the new BELIEF artifact path].** sci-adk
  **shall** provide an authored-`si.tex` render path that emits the Supporting Information as an
  AUTHORED belief artifact — the overflow of `main.tex` — reusing the existing `paper.py` prose
  machinery (the prose sanitizer, the `\evval`/`\status` fidelity substitution, the
  `\ref`/`\cite`/`\novelty` passthrough), and NOT the `render_si_latex` deterministic dump.
- **REQ-SA-102 (Ubiquitous).** The authored `si.tex` **shall** support a FREE authored
  structure (no fixed record-type axis): the renderer **may** offer a conventional default
  skeleton (e.g. Supplementary Methods / Notes / Figures / Tables), and the agent **shall** be
  able to reorganize sections freely per the overflow.
- **REQ-SA-103 (Ubiquitous).** Every measured value stated in the authored `si.tex` **shall** be
  bound to the record via the existing `\evval`/`\status` fidelity gate (FAIL-LOUD on an
  unknown id / field / hypothesis), exactly as `main.tex` already is — so the SI's narrative is
  the agent's, but every number it states is the record's.
- **REQ-SA-104 (Ubiquitous).** Tables in the authored `si.tex` **shall** be hand-authored by the
  agent with each cited cell value written through the fidelity gate; the deterministic dump's
  table logic **shall not** be reused for `si.tex` (it lives only in the record artifact ③).
  Row completeness is the author's responsibility (the same honest limit the fidelity gate
  already carries).
- **REQ-SA-105 (Ubiquitous).** Each figure **shall** live in exactly one of `main.tex` or
  `si.tex` (Figure N XOR Figure S*), drawing on one shared `figures/` file set; the labels
  differ (main `Figure N`, SI `Figure S*`). (The record artifact ③ continues to carry all
  figures exhaustively.)
- **REQ-SA-106 (Event-driven).** **When** the authoring flow pushes body-overflow detail from
  `main.tex` into `si.tex`, the plain-text `(Figure S<n>)` / `(Table S<n>)` cross-references
  **shall** be authored inline (one voice, co-authored), and `si.tex` **shall** retain the
  S-numbering convention (`\thefigure`/`\thetable` = `S\arabic{...}`) so a main-paper "Figure
  S<n>" matches the printed SI number.
- **REQ-SA-107 (State-driven, thin records).** **While** a run has few hypotheses (a small
  study), the authored `si.tex` **shall** be permitted to be short or absent — a small real
  study has a short supplement or none; no special degenerate machinery is required.

### B — Record artifact: relocate, rename, exempt

- **REQ-SA-201 (Ubiquitous) [RECORD-SIDE].** The deterministic dump renderer (`render_si_latex`)
  **shall** be RETAINED and reused verbatim to produce the deposit's ONE retained record
  artifact; its determinism (same inputs → byte-identical output) and its `sci-adk verify`
  relationship **shall** be unchanged.
- **REQ-SA-202 (Event-driven) [RECORD-SIDE].** **When** the compiler emits the deterministic
  record dump, it **shall** write it to the deposit as `record.tex` (the relocation target),
  freeing the `si.tex` slot for the authored overflow path (A), instead of writing the dump to
  `paper/si.tex`.
- **REQ-SA-203 (Ubiquitous) [RECORD-SIDE].** The retained record artifact **shall** be named and
  presented as the RECORD (not "Supporting Information"): the artifact's title/identity wording
  produced by the renderer **shall** read as the record/provenance, not as an SI sibling of the
  paper.
- **REQ-SA-204 (Ubiquitous) [RECORD-SIDE / NEW — belief-boundary extension].** Because the
  authored `si.tex` is now a SUBMISSION belief document (no longer the record dump), the PER-RUN
  tool-vocabulary gate **shall** be EXTENDED to scan `si.tex` in addition to `main.tex`. (Today
  the per-run gate scans `draft.tex`/`main.tex` only and EXEMPTS `si.tex`, `verify.py:826-837`;
  this requirement is the RED→GREEN change: per-run, a forbidden tool noun in `si.tex` currently
  passes, and after this change it FLAGS.) This is the single belief-side computation change in
  this SPEC; it is the explicit exception to REQ-SA-401/REQ-SA-404.
- **REQ-SA-206 (Ubiquitous) [RECORD-SIDE].** The retained record artifact `record.tex` **shall**
  remain EXEMPT from the tool-vocabulary gate (it legitimately names
  `capability:`/`docker:`/`environment:` provenance); after REQ-SA-204 the tool-agnostic gate
  **shall** apply to `main.tex` and the authored `si.tex` (the submission documents) and **shall
  not** scan `record.tex`.
- **REQ-SA-205 (Unwanted-behavior).** **If** the relocation moves the dump out of the `si.tex`
  slot, **then** the resulting `si.tex` (now authored, B-freed) **shall not** silently lose
  any record-fidelity audit that previously applied to it — the existing fidelity, number-audit,
  novelty, and cross-doc gates **shall** continue to cover `si.tex` (see D).
  - **[D4 — id ordering note, intentional].** In Pillar B the ids appear 204→206→205 rather than
    strictly ascending. This grouping is deliberate: 204 (extend the tool-vocab gate to `si.tex`)
    pairs immediately with 206 (its exact boundary — `record.tex` stays exempt), and 205 (no
    record-fidelity audit dropped) reads as the closing invariant. The numbering was fixed when
    M1 landed (implemented + tested); it is left in place to avoid churning implemented ids.

- **REQ-SA-301 (Ubiquitous) [RECORD-SIDE].** `sci-adk verify` **shall** carry a
  deposit-completeness check that confirms the deposit contains (a) the retained record artifact
  and (b) a "Data & code availability" statement; the check **shall** be PURE and deterministic,
  modeled on the existing `readme_submission_readiness_problems` precedent (a single problem
  line per missing element).
- **REQ-SA-302 (Unwanted-behavior) [RECORD-SIDE].** **If** the deposit is missing the retained
  record artifact, **then** the deposit-completeness check **shall** FAIL and name the missing
  record artifact.
- **REQ-SA-303 (Unwanted-behavior) [RECORD-SIDE].** **If** the deposit is missing a "Data & code
  availability" statement, **then** the deposit-completeness check **shall** FAIL and name the
  missing statement.
- **REQ-SA-304 (Ubiquitous, record-vs-belief invariant) [RECORD-SIDE].** The deposit-completeness
  check **shall** be a PRESENCE check on record-side artifacts only; it **shall not** judge the
  belief content of `main.tex`/`si.tex`, and it **shall not** invoke any LLM (consistent with
  "no LLM in the record path").
- **REQ-SA-305 (State-driven) [RECORD-SIDE].** **While** `sci-adk verify` over `runs/` is already
  green for record reproduction, the deposit-completeness check **shall** be ADDITIVE — it
  **shall not** weaken or replace the existing record-green / claim-reproduction audit.

### D — Belief-side gate is UNCHANGED (characterization, not new logic)

- **REQ-SA-401 (Ubiquitous) [BELIEF-SIDE / CHARACTERIZATION].** The verify gate over `si.tex`
  **shall** be unchanged in its computation for the FOUR already-covering checkers: `si.tex`
  continues to be audited as a manuscript by the same checkers that audit `main.tex` — P2
  number-audit, value-fidelity residual scan, ref-consistency, and novelty — with NO new gate
  computation added for these. (The fifth submission-document checker, tool-vocabulary, is the
  one EXCEPTION: it is EXTENDED to `si.tex` by REQ-SA-204 because the per-run gate previously
  EXEMPTED `si.tex` — that is NEW work, not characterization.)
- **REQ-SA-402 (State-driven) [BELIEF-SIDE / CHARACTERIZATION].** **While** `si.tex` is authored
  (no longer a dump where P2 passed trivially), the SAME P2 number-audit **shall** do real work
  auditing the AUTHORED numbers against the recorded-value pool, with NO change to what P2
  computes — only its input (now authored) differs.
- **REQ-SA-403 (Ubiquitous) [BELIEF-SIDE / CHARACTERIZATION].** The cross-doc S-ref gate
  (`check_cross_doc_s_refs`) **shall** remain the linkage guard between `main.tex` and `si.tex`;
  no compile-coupling mechanism (`xr` / `zref-xr`) **shall** be introduced.
- **REQ-SA-404 (Unwanted-behavior) [BELIEF-SIDE / CHARACTERIZATION].** **If** a change in this
  SPEC would alter what `sci-adk verify` COMPUTES over the belief documents — EXCEPT the single
  authorized exception of extending the per-run tool-vocabulary gate to `si.tex` (REQ-SA-204) —
  **then** it is out of scope and **shall not** be made. (The authorized exception, the
  relocation of which artifact occupies the `si.tex` slot, and the additive record-side deposit
  check are the ONLY permitted changes.)

### E — Package-path authoring flow (M5; applies the A/B/C/D model to the package by symmetry)

M5 applies the design model (`design/si-belief-record-split.md` §5/§9, package path in scope)
to `render/package.py` + the shipped `04_scripts/make_si.py` + the package writer + the
package-path gate (`verify.py` package scan). The package-internal layout choices are M5
decisions (flagged below).

#### E.1 — Authored package `si.tex` (mirrors A: REQ-SA-101/103/104, applied to the package)

- **REQ-SA-501 (Ubiquitous) [RECORD-SIDE — this is the new BELIEF artifact path].** The package
  assembler **shall** treat `package/01_manuscript/si.tex` as an AUTHORED belief artifact —
  the package analogue of per-run ② and symmetric to package `main.tex` — and **shall** preserve
  an author-supplied `si.tex` (e.g. from `<ws>/package_src/si.tex`) verbatim, exactly as it
  already preserves an author-supplied `main.tex` (`package.py` `_ensure_manuscript`). The
  package `si.tex` **shall not** be generated by `make_si.py`.
- **REQ-SA-502 (Event-driven) [RECORD-SIDE].** **When** no author-supplied package `si.tex` is
  present, the assembler **shall** behave symmetrically to the `main.tex` no-author case (the
  authored SI is optional overflow — REQ-SA-107 thin/absent applies): it **shall not** fall back
  to writing the `make_si.py` dump into `01_manuscript/si.tex`. (A deterministic, tool-agnostic
  authored-SI skeleton MAY be emitted by symmetry with the `main.tex` skeleton, or no `si.tex`
  emitted at all; either is valid — the record dump is no longer the fallback.)
- **REQ-SA-503 (Ubiquitous) [BELIEF-SIDE / CHARACTERIZATION].** Every measured value in an
  authored package `si.tex` **shall** continue to be audited against the package recorded-value
  pool by the EXISTING package number-audit (`RecordedValuePool.from_package`, `verify.py`
  package scan over `main.tex` + `si.tex`) and the EXISTING package value-fidelity residual
  scan — with NO change to what those checks compute; only their input (now authored, not the
  dump) differs. (The package analogue of REQ-SA-402.)

#### E.2 — Relocate + rename the package dump (mirrors B: REQ-SA-201/202/203)

- **REQ-SA-504 (Ubiquitous) [RECORD-SIDE].** The `make_si.py` dump LOGIC **shall** be RETAINED
  and reused as the package's deterministic record renderer; its determinism (same record →
  same bytes) and its field-agnostic, record-derived construction **shall** be unchanged. (The
  package analogue of REQ-SA-201; `make_si.py` is the package's `render_si_latex`.)
- **REQ-SA-505 (Event-driven) [RECORD-SIDE — M5 DECISION on the package layout].** **When** the
  package assembler emits the deterministic record dump, it **shall** write it to the package
  PROVENANCE area as `package/06_provenance/record.tex` (the M5-chosen relocation target),
  instead of to `package/01_manuscript/si.tex`. The location `06_provenance/record.tex` is the
  M5 decision (the design fixed the model, not the package folder): it is symmetric to per-run
  `runs/<id>/record.tex` and sits on the existing 6-folder provenance/record floor. This path
  is the SINGLE SOURCE the package deposit-completeness check (REQ-SA-508) references.
- **REQ-SA-506 (Ubiquitous) [RECORD-SIDE].** The relocated package record artifact **shall** be
  named and presented as the RECORD (not "Supporting Information"): the renderer's title/identity
  wording (`make_si.py` "Supporting Information" / record-dump prose) **shall** read as the
  record/provenance, not as an SI sibling of the package manuscript. (The package analogue of
  REQ-SA-203.)
- **REQ-SA-506a (Ubiquitous) [RECORD-SIDE — F2 authoritative location decision].** The package
  record renderer (`make_si.py`) **shall** EMIT a "Data & code availability" statement into the
  body of the record artifact it writes (`06_provenance/record.tex`). This pins the AUTHORITATIVE
  source of the availability statement to the RECORD ARTIFACT BODY, consistent with the M2 checker
  `deposit_completeness_problems` which detects the statement by reading the record artifact's text
  (`pkgreqs_checks.py:499`, `_DATA_AVAILABILITY_RE`), NOT the package README. [Why this is needed:
  per-run M2's `render_si_latex` does NOT auto-emit the phrase (the per-run test appends it), and
  today's `make_si.py` has NO such phrase — so without this requirement the package record artifact
  would FAIL the deposit-completeness check (REQ-SA-508). The README's availability line
  (`package.py` `_write_readme`) is NOT the source the M2 checker reads.] The statement is record
  prose naming where the data/code are deposited; it asserts no measured value (no `\evval`), so it
  is by-construction clean on number-audit and is part of the EXEMPT record artifact (REQ-SA-507).

#### E.3 — Tool-vocab boundary on the package (mirrors B: REQ-SA-204/206, package shape)

- **REQ-SA-507 (Ubiquitous) [RECORD-SIDE / boundary correction].** After the relocation, the
  package tool-vocabulary gate (`verify.py` package scan) **shall** apply to the AUTHORED
  package `main.tex` and the AUTHORED package `si.tex` (the submission documents) and **shall
  not** scan `package/06_provenance/record.tex` (the record artifact, which legitimately names
  `capability:`/`docker:`/`environment:` provenance). Because the package gate reads only
  `01_manuscript/main.tex` + `01_manuscript/si.tex` and the record artifact lives in
  `06_provenance/`, this exemption holds BY CONSTRUCTION (no new exempt-list needed). **Unlike
  per-run M1 (a RED→GREEN scan EXTENSION), the package gate ALREADY scans `si.tex`; this
  requirement makes the scanned `si.tex` genuinely authored and moves the record OUT of the
  scanned dir, so the gate stops policing a record artifact** — the package analogue of the
  REQ-SA-204 + REQ-SA-206 boundary, achieved by relocation rather than by adding a scan. The
  hand-avoidance of toolchain nouns in `make_si.py` prose (today's workaround) **shall** no
  longer be the mechanism by which the record passes a belief gate (the record is now exempt).

#### E.4 — Package deposit-completeness (mirrors C: REQ-SA-301/302/303/304/305, reusing M2)

- **REQ-SA-508 (Ubiquitous) [RECORD-SIDE].** `sci-adk verify` (workspace/package scope) **shall**
  carry a package deposit-completeness check that confirms the package contains (a) the relocated
  record artifact (`06_provenance/record.tex`) and (b) a "Data & code availability" statement IN
  THAT RECORD ARTIFACT'S BODY (the authoritative source fixed by REQ-SA-506a); the check **shall**
  REUSE the existing `deposit_completeness_problems` checker (M2) — PURE, deterministic,
  presence-only — pointed at the package record path (REQ-SA-505), with NO new checker logic.
- **REQ-SA-509 (Unwanted-behavior) [RECORD-SIDE].** **If** the package is missing the relocated
  record artifact `06_provenance/record.tex`, **then** the check **shall** FAIL naming the missing
  record artifact and report NO further line (the availability statement lives IN the record body,
  so with no record there is nothing to carry it). **If** the record artifact is present but its
  body has NO "Data & code availability" statement, **then** the check **shall** FAIL naming the
  missing statement. The checker reports ONE problem at a time in this precedence (record-missing
  first), matching the M2 checker's behavior (`pkgreqs_checks.py:491-503`) — it never emits both
  lines at once, and "availability without record" cannot arise (per the M2 checker comment).
- **REQ-SA-510 (State-driven) [RECORD-SIDE].** **While** the package `package_requirements_clean`
  HARD gate is already green (layout + traceability + record-green + the existing per-document
  checks), the package deposit-completeness check **shall** be ADDITIVE — it **shall** extend the
  package problem list and **shall not** weaken or replace the existing `package_requirements_clean`
  gate or any other gated conjunct. (The package analogue of REQ-SA-305.)
  - **[F3 — explicit per-run vs package gating asymmetry, intended].** UNLIKE per-run M2, where
    `deposit_complete` is a SEPARATE NON-GATING channel that does NOT join the `passed` exit gate
    (`verify.py:465-466`; `passed` reads `all_reproduced`, not `deposit_complete`), the PACKAGE
    path computes `clean = not problems` and `passed = clean` (`verify.py:550,558`). Because the
    package deposit-completeness check appends to `_check_package_requirements`'s `problems`
    (REQ-SA-508), a missing record artifact or availability statement makes
    `package_requirements_clean` FALSE — i.e. in the package path the deposit-completeness check
    IS a HARD gate. This asymmetry (per-run advisory vs package HARD-gating) is INTENDED: a package
    is the final submission unit, so a missing record artifact / availability statement is a true
    submission defect; a per-run deposit is an intermediate record where the same gap is advisory.
  - **[F3 — fixture migration, so Run does not regress seeded packages].** Existing seeded-green
    package fixtures (which under the OLD model carried the dump in `01_manuscript/si.tex` and NO
    `06_provenance/record.tex` / availability statement) **shall** be MIGRATED as part of M5 by
    (i) relocating the dump to `06_provenance/record.tex` (REQ-SA-505) and (ii) ensuring that
    record artifact body carries the availability statement (REQ-SA-506a) — keeping them green
    under the now-HARD package deposit gate. The migration is mechanical (re-assemble the package),
    not a content change; no seeded run's record/verdict is altered.
- **REQ-SA-511 (Ubiquitous, record-vs-belief invariant) [RECORD-SIDE].** The package
  deposit-completeness check **shall** be a PRESENCE check on package record-side artifacts only;
  it **shall not** judge the belief content of the package `main.tex`/`si.tex`, and it **shall
  not** invoke any LLM (consistent with "no LLM in the record path"). (The package analogue of
  REQ-SA-304.)

#### E.5 — Package writer + scope discipline

- **REQ-SA-512 (Ubiquitous) [RECORD-SIDE — workflow].** The `science-workflow-package` skill and
  the package writer (`Agent(expert-writer)`) **shall** be updated so the package `si.tex` is
  AUTHORED (from `package_src/si.tex`, symmetric to `package_src/main.tex`), and **shall** no
  longer describe `si.tex` as "a `si.tex` where the record dump is augmented"; the deterministic
  record now lives at `06_provenance/record.tex` and is presented as the package's record, not as
  an authored SI.
- **REQ-SA-513 (Unwanted-behavior) [BELIEF-SIDE / CHARACTERIZATION].** **If** an M5 change would
  alter what the package gate COMPUTES over the package belief documents BEYOND (a) which artifact
  occupies the `01_manuscript/si.tex` slot (now authored, not the dump), (b) the relocation of the
  deterministic dump out of that slot, and (c) the ADDITIVE package deposit-completeness check —
  **then** it is out of scope and **shall not** be made. The four package per-document checks
  (number-audit, value-fidelity, compile/ref-consistency, cite resolution) **shall** be unchanged
  in what they compute (they already scan `si.tex`; M5 only changes that `si.tex` is now authored).
- **REQ-SA-514 (Ubiquitous) [RECORD-SIDE].** M5 **shall** be domain-neutral and **shall not** name
  or assume any domain, venue, or study; the relocation, the authored package SI, and the package
  deposit-completeness check apply to ANY workspace package (the IEAM-P8 package is an example of
  the package PATH, not a hardcoded target).

### F — SI bibliography: `references_SI.bib` for the authored `si.tex` (M6)

M6 gives the authored `si.tex` (②) its OWN bibliography, symmetric to how `main.tex`/
`draft.tex` uses `references.bib`. Tag `[BELIEF-SIDE]` = the SI bib is the authored
document's citation apparatus (co-located with ②, not a record artifact). The four decisions
are FROZEN in `design/si-bibliography.md`; these requirements encode them. Keyword conventions
as above.

#### F.1 — Authored-SI renderer gains bib wiring (mirrors `paper.py:831-834`)

- **REQ-SA-601 (Optional / Where) [BELIEF-SIDE].** The authored-SI renderer
  (`render_authored_si_latex`, `authored_si.py:113`) **shall** accept a new optional `bib_path`
  parameter (symmetric to `render_paper_latex`'s `bib_path`); **Where** a `bib_path` is supplied,
  the renderer **shall** emit `\bibliographystyle{plainnat}` + `\bibliography{<stem>}` in the
  rendered `si.tex` (exactly as `paper.py:831-834` and `si.py:540-543` do), so the author's
  `\citep`/`\cite` resolve instead of rendering `[?]`. (D5: this is the OPTIONAL bib-wiring
  clause; the PURE/FAIL-LOUD invariant is split into REQ-SA-601a.)
- **REQ-SA-601a (Ubiquitous) [BELIEF-SIDE].** The authored-SI renderer **shall** stay PURE (no
  filesystem access; the caller supplies the `bib_path`) and **shall** remain FAIL-LOUD on the
  existing fidelity macros — the bib wiring adds NO new gate to the render and does not change the
  renderer's purity/fail-loud contract.
- **REQ-SA-602 (Event-driven) [BELIEF-SIDE].** **When** no `bib_path` is supplied to the
  authored-SI renderer (a thin/absent-bibliography SI, e.g. an SI that cites nothing),
  **then** the renderer **shall** emit NO `\bibliography{}` line (symmetric to
  `paper.py:835`'s no-bib branch) — a citation-free authored SI stays minimal and valid, and
  the `\usepackage{natbib}` preamble line (`authored_si.py:192`) is harmless without a
  `\bibliography`.
- **REQ-SA-603 (Ubiquitous) [BELIEF-SIDE].** The bib-wiring change **shall** preserve the
  authored-SI renderer's determinism (same authored input + same `bib_path` → byte-identical
  `si.tex`) and its existing behavior for every other slot (fidelity substitution, `\novelty`
  gate, S-numbering, figure XOR) — M6 **shall not** alter what the renderer computes beyond
  appending the bibliography lines.

#### F.2 — Compiler builds + co-locates the cited-only per-run `references_SI.bib`

- **REQ-SA-604 (Event-driven) [BELIEF-SIDE].** **When** the compiler renders an authored
  `paper/si.tex` (`compiler.py:625`), it **shall** build a `references_SI.bib` as the
  CITED-ONLY subset of the run's ONE literature pool
  (`runs/<id>/artifacts/literature/references.bib`, `compiler.py:814`) — the pool entries whose
  key is in the SI's cited-key set and NO uncited entries — and **shall** co-locate it next to
  `si.tex` as `paper/references_SI.bib`, then pass its path to the renderer (REQ-SA-601). This
  reuses the existing co-location pattern (`_colocate_bib`, `compiler.py:818`); the difference is
  the SUBSET filter and the `references_SI` stem.
  - **[D2 — ordering, pinned, no circularity].** The cited-key set **shall** be extracted from
    the authored SI SOURCE — the `AuthoredSI` section bodies (`prose.py:187,219`,
    `SISection.body`) — BEFORE the final render, so the subset is known WITHOUT needing the
    rendered `.tex`. (Equivalently, a first render pass with no `bib_path` MAY be used to obtain
    the `.tex`, then `cited_keys` scanned, then a single final render WITH the built `bib_path`;
    the source-scan avoids even that pass.) This is well-defined because `\cite`/`\citep` keys
    survive the fidelity pipeline VERBATIM (`_slot` runs `substitute_factrefs` + the sanitizer,
    both of which preserve `\cite`/`\ref`, `authored_si.py:157-177`), so the cited keys in the
    SOURCE bodies are exactly the cited keys in the rendered `.tex`. Order of operations:
    (1) scan cited keys from the `AuthoredSI` bodies → (2) filter the pool to those keys →
    (3) write `references_SI.bib` → (4) ONE final `render_authored_si_latex(..., bib_path=...)`.
    No `bib_path`-before-`cited_keys` circularity.
- **REQ-SA-605 (Ubiquitous, no-LLM invariant) [BELIEF-SIDE].** The subset selection **shall**
  be DETERMINISTIC — a pure set operation over `cited_keys(si_tex)` and the literature pool
  entries — and **shall not** invoke any LLM, network, or literature-acquisition path. There is
  NO separate SI literature pool; `references_SI.bib` is derived solely from the already-acquired
  per-run pool.
- **REQ-SA-606 (Unwanted-behavior) [BELIEF-SIDE].** **If** the run has NO literature pool
  (`_locate_bib_path` returns `None`) OR the authored `si.tex` cites nothing, **then** the
  compiler **shall not** fabricate a bib and **shall not** write a `references_SI.bib` file at
  all (D6: ABSENCE, not an empty file) — it passes NO `bib_path` to the renderer, so `si.tex`
  emits no `\bibliography` (REQ-SA-602), consistent with how the main paper handles a missing
  pool (`compiler.py:830-831` → no `\bibliography`). A cited key with no matching pool entry is
  NOT silently dropped: `references_SI.bib` cannot contain a key absent from the pool, so the
  dangling `si.tex` cite is surfaced by the SI cite-resolution gate (F.4).
- **REQ-SA-607 (Ubiquitous) [BELIEF-SIDE].** The compiler's per-run co-location of
  `references_SI.bib` **shall** be additive and **shall not** alter the main paper's
  `references.bib` co-location (`_colocate_bib`, `compiler.py:582,832`) or wiring — the two
  documents' bibliographies are independent (each cites-and-resolves its own). The stale
  comment at `compiler.py:544` **shall** be corrected to describe the authored-SI bib model;
  concretely (D3, grep-testable exit criterion) the false phrase "wired into BOTH documents"
  **shall not** appear at that site after M6 (AC-F6 asserts its absence).

#### F.3 — Package path symmetry (`01_manuscript/references_SI.bib`)

- **REQ-SA-608 (Ubiquitous) [BELIEF-SIDE].** The package assembler (`package.py`
  `_ensure_manuscript`, `package.py:449-456`) **shall** provide a `01_manuscript/references_SI.bib`
  for the package `si.tex`, symmetric to how the package `main.tex` uses
  `01_manuscript/references.bib` (`package.py:431-437`). **Where** an author supplies
  `package_src/references_SI.bib`, it **shall** be preserved verbatim (symmetric to
  `package_src/references.bib`, `package.py:431-432`); otherwise `references_SI.bib` **shall** be
  the cited-only subset of the package bibliography (the pool entries whose key is in the package
  SI's cited-key set, the package analogue of REQ-SA-604). The two package documents' bibs are
  independent (REQ-SA-609).
- **REQ-SA-608a (State-driven — AUTHOR-SUPPLIED si.tex) [BELIEF-SIDE] (D1, case a).** **While** the
  package `si.tex` is an author-supplied `package_src/si.tex` (copied VERBATIM,
  `package.py:449-451`), the AUTHOR **shall** own the `\bibliography{references_SI}` line inside
  that file, and the assembler **shall** ONLY land `01_manuscript/references_SI.bib` next to it —
  the assembler **shall not** inject or rewrite any `\bibliography` wiring into the copied author
  file (it cannot, without violating the verbatim copy). **If** an author-supplied `si.tex` cites
  keys but carries a missing or wrong `\bibliography` line, **then** the SI cite-resolution gate
  (REQ-SA-613) is what surfaces the unresolved cites — the assembler does not silently repair the
  author's file.
- **REQ-SA-608b (Event-driven — GENERATED skeleton si.tex) [BELIEF-SIDE] (D1, case b).** **When**
  no author `package_src/si.tex` is supplied and the assembler emits the deterministic authored-SI
  SKELETON (`_skeleton_si_tex`, `package.py:459-482`), the assembler **shall** wire
  `\bibliography{references_SI}` in the emitted skeleton IF and ONLY IF that skeleton cites
  anything; a citation-free skeleton emits no `\bibliography` and no `references_SI.bib`
  (REQ-SA-610). Only in this generated-skeleton case does the assembler own the `\bibliography`
  line (it authored the file), distinct from the author-supplied case (REQ-SA-608a).
- **REQ-SA-609 (Ubiquitous) [BELIEF-SIDE].** The package `references_SI.bib` **shall** contain
  ONLY entries CITED in the package `01_manuscript/si.tex` (cited-only), **shall not** duplicate
  the package `main.tex`'s uncited-in-SI references, and **shall** keep the two package documents'
  bibliographies independent (`main.tex` → `references.bib`, `si.tex` → `references_SI.bib`).
- **REQ-SA-610 (State-driven, thin/absent SI) [BELIEF-SIDE].** **While** the package `si.tex` is
  the deterministic authored-SI SKELETON (no author `package_src/si.tex`, `package.py:452-453`)
  and cites nothing, the assembler **shall** be permitted to emit no `references_SI.bib` / no
  `\bibliography` for the package `si.tex` — a citation-free package SI stays valid (the package
  analogue of REQ-SA-602/REQ-SA-107).

#### F.4 — SI cite-resolution verify gate (per-run + package), reusing `cite_resolution_problems`

- **REQ-SA-611 (Ubiquitous) [BELIEF-SIDE — NEW gate].** `sci-adk verify` **shall** carry a
  cite-resolution gate for the authored `si.tex` against `references_SI.bib`, exactly parallel to
  the existing `main.tex`-vs-`references.bib` gate: every `\cite*` key in `si.tex` **shall**
  resolve in `references_SI.bib`. The gate **shall** REUSE the existing pure
  `cite_resolution_problems` checker (`pkgreqs_checks.py:129`) pointed at `(si_tex,
  references_SI.bib)` — NO new checker logic.
- **REQ-SA-612 (Event-driven) [BELIEF-SIDE].** **When** the per-run verify runs
  (`_check_paper_requirements`, the site of `verify.py:1012-1018`), it **shall** additionally load
  `paper/references_SI.bib` and run `cite_resolution_problems(si_tex, si_bib)` over the authored
  per-run `si.tex`, additive to the existing `cite_resolution_problems(draft_tex, bib)` over
  `draft.tex`. (Per-run cite-resolution today covers `draft.tex` only, `verify.py:1014`.)
- **REQ-SA-613 (Event-driven) [BELIEF-SIDE].** **When** the package verify runs
  (`_check_package_requirements`, the site of `verify.py:1242`), it **shall** additionally load
  `01_manuscript/references_SI.bib` and run `cite_resolution_problems(si_tex, si_bib)` over the
  authored package `si.tex`, additive to the existing `cite_resolution_problems(main_tex, bib)`
  over `main.tex`. (Package cite-resolution today covers `main.tex` only, `verify.py:1242`.)
- **REQ-SA-614 (Unwanted-behavior) [BELIEF-SIDE].** **If** a `\cite*` key in `si.tex` has no
  entry in `references_SI.bib`, **then** the SI cite-resolution gate **shall** FAIL and name the
  unresolved key(s) (the same problem shape as `cite_resolution_problems` for `main.tex`,
  `pkgreqs_checks.py:141-143`), on the per-run and the package path.
- **REQ-SA-615 (State-driven, thin/absent SI) [BELIEF-SIDE].** **While** a run/package has no
  authored `si.tex` (thin/absent SI, REQ-SA-107) or an `si.tex` that cites nothing, the SI
  cite-resolution gate **shall** be vacuously clean (no `\cite*` keys → no unresolved keys),
  consistent with `cite_resolution_problems` returning `[]` on empty input.

#### F.5 — Scope discipline

- **REQ-SA-616 (Unwanted-behavior) [BELIEF-SIDE].** **If** an M6 change would (a) add a separate
  SI literature-acquisition pool, (b) alter the main paper's `references.bib` wiring
  (`paper.py`, `_colocate_bib`), (c) change the deposit `record.tex`'s own bib wiring
  (`si.py:540-543`), (d) change what `sci-adk verify` computes over `runs/` or the record, or
  (e) introduce cross-document bibliography coupling — **then** it is out of scope and **shall
  not** be made. The ONLY permitted changes are: the authored-SI renderer's bib wiring (F.1), the
  cited-only `references_SI.bib` build + co-location per-run and package (F.2/F.3), and the
  additive SI cite-resolution gate (F.4).
- **REQ-SA-617 (Ubiquitous) [BELIEF-SIDE].** M6 **shall** be domain-neutral and **shall not**
  name or assume any domain, venue, or study; the `references_SI.bib` wiring, subset build, and
  SI cite gate apply to ANY run/package.

---

## Exclusions (What NOT to Build)

- **No new belief-side gate logic BEYOND the one authorized exception.** The existing fidelity /
  number-audit / novelty / cross-doc gates already cover `si.tex` as a manuscript (measured,
  design §8.4) — no new computation is added for those. The SOLE belief-side change is extending
  the per-run tool-vocabulary gate to `si.tex` (REQ-SA-204), which is NEW work because the
  per-run gate previously EXEMPTED `si.tex` (`verify.py:826-837`); `record.tex` stays exempt.
- **No `zref-xr` / `xr` cross-document compile coupling.** Linkage stays plain-text S-refs +
  the existing `check_cross_doc_s_refs` gate (design §6, decided and dropped). Clickable
  cross-document navigation is explicitly NOT built.
- **No change to what `sci-adk verify` computes** over `runs/` + the record artifact (the
  record path is untouched except for the additive deposit-completeness PRESENCE check).
- **No LLM in the verdict or record path.** The authored `si.tex` is written by the in-session
  agent (belief), but every number it states passes the deterministic fidelity gate; the
  deposit-completeness check is a deterministic presence check with no model.
- **No reuse of the dump's table logic in `si.tex`.** The deterministic table renderer lives
  ONLY in the record artifact ③; `si.tex` tables are hand-authored (REQ-SA-104).
- **No gate guaranteeing interpretation or completeness.** The fidelity gate guarantees the
  CITED NUMBERS only; an author can still omit a row or mis-frame (the same, unchanged exposure
  `main.tex` already carries).
- **No change to the JOSS tool paper.** `paper/paper.md` (the short tool paper) is OUT of scope
  and untouched (design §9).
- **No change to `main.tex` / `render_paper_latex`.** ① is unchanged; this SPEC touches the SI
  artifact and the deposit only.
- **No domain/study specialization.** No requirement, renderer, or default may name or assume a
  specific domain, venue, or study (the IEAM-P8 package is an example of the submission PATH, not
  a hardcoded target).

### M5 (package-path) exclusions

- **No new package gate logic.** The package number-audit, value-fidelity, compile/ref-consistency,
  and cite-resolution checks already scan `01_manuscript/si.tex` (`verify.py` package scan) — M5
  adds NO new per-document computation for them; it only makes the scanned `si.tex` authored. The
  only NEW gate work is REUSING the M2 `deposit_completeness_problems` checker at a package call
  site (REQ-SA-508) — no new checker is written.
- **No new record renderer.** The `make_si.py` dump LOGIC is reused as the package record renderer
  (REQ-SA-504); only its output identity/location changes. No parallel package record renderer.
- **No package tool-vocab exempt-list.** The record artifact is exempt BY CONSTRUCTION (it lives in
  `06_provenance/`, outside the `01_manuscript/` dir the gate reads). M5 **shall not** add an
  explicit exemption branch to the package tool-vocab scan (REQ-SA-507).
- **No regression of `package_requirements_clean` or seeded green packages.** The package
  deposit-completeness check is additive (REQ-SA-510); existing green packages **shall** stay green
  modulo carrying the now-relocated record artifact + an availability statement.
- **No change to `main.tex` / the merged-manuscript skeleton logic.** Package `main.tex` authoring
  and the deterministic skeleton are unchanged; M5 touches the `si.tex` slot, the record-dump
  destination, and the additive deposit check only.
- **No change to the per-run path (M1–M4).** The per-run `runs/<id>/paper/` + `runs/<id>/record.tex`
  + per-run deposit-completeness are already implemented and **shall** stay intact.

### M6 (SI-bibliography) exclusions

- **No separate SI literature acquisition.** `references_SI.bib` is a CITED-ONLY subset of the ONE
  per-run pool (`runs/<id>/artifacts/literature/references.bib`); M6 adds NO new acquisition path,
  no second pool. Uncited pool entries **shall not** appear in `references_SI.bib`.
- **No LLM at bib-selection time.** The subset is a pure set operation over `cited_keys(si_tex)` +
  the pool (`pkgreqs_checks.py:113/124`); no model, no network.
- **No new cite-resolution checker.** The SI cite gate REUSES the existing pure
  `cite_resolution_problems` (`pkgreqs_checks.py:129`) pointed at `(si_tex, references_SI.bib)`;
  no parallel checker is written.
- **No change to `main.tex`/`references.bib` wiring.** `paper.py` bib emission and `_colocate_bib`
  (`compiler.py:582,832`) are unchanged; the SI bib is independent and additive.
- **No change to the deposit `record.tex` bib.** The record dump keeps its own `references.bib`
  wiring (`si.py:540-543`); it is the record artifact and is untouched by ②'s bib.
- **No change to what `sci-adk verify` computes over `runs/` or the record.** M6 adds only a
  belief-side cite-resolution check for `si.tex`, parallel to the existing `main.tex` one.
- **No cross-document bibliography coupling.** The two documents' bibliographies stay independent;
  no `\bibliography` shared between `main.tex` and `si.tex`.
- **No domain/study specialization.** No requirement, renderer, or default may name or assume a
  domain, venue, or study.

---

## [HARD] Constraints

- **Record/belief boundary by artifact TYPE.** `main.tex` and `si.tex` are BELIEF (authored,
  fidelity-gated); the deposit (`runs/` + `verify` + record artifact + availability statement)
  is the RECORD. Do not blur them.
- **Reuse, do not re-implement.** The authored `si.tex` path REUSES `paper.py` machinery; the
  record artifact REUSES `render_si_latex` verbatim. No parallel renderer is written.
- **Belief-side gate is characterization only.** Requirements tagged
  [BELIEF-SIDE / CHARACTERIZATION] confirm existing behavior is preserved; if implementing one
  requires NEW gate computation, the implementation is wrong (re-read design §8.4).
- **Domain-neutral.** The SPEC, its requirements, and the resulting code MUST be domain-general;
  no general surface may name or assume a domain, venue, or study.
- **Honor FROZEN invariants.** Record vs belief; no self-certification (the gate is the verdict,
  not a manual check); the deposit-completeness check is additive and never weakens the existing
  record-green / claim-reproduction gate.
- **Minimal, no over-engineering.** The new gate work is small and record-side; the authored path
  reuses existing prose machinery. Smallest change that realizes the design.
- **Suite stays green.** The existing suite MUST stay green; each new behavior needs tests;
  Docker-dependent tests marked `integration`.

---

## Design Source

The authoritative design is `design/si-belief-record-split.md` (v0.4, FROZEN, SPEC-ready). This
SPEC decomposes that design without redesigning it. All design §8 open points are closed there.
Lineage: extends/revises `design/render-architecture-reframe.md` (for the SI artifact only).
Related: `design/paper-figures-and-si.md`, `design/paper-publishing-requirements.md`,
`design/paper-writing-enforcement.md` (SPEC-PAPER-GATE-001, the sibling gate SPEC whose P2
number-audit covers `si.tex`).

The M6 SI-bibliography decision is FROZEN in the decision record `design/si-bibliography.md`
(v1.0) — the single source for the four `references_SI.bib` decisions (cited-only subset, both
paths, SI cite gate, design-first process). That record EXTENDS `si-belief-record-split.md`
(which remains the single source for the record/belief SI split); M6 encodes it, it does not
re-decide the FROZEN split.

---

## Affected Surfaces (evidence map, for the Run phase — not implementation guidance)

- `src/sci_adk/render/si.py` — `render_si_latex` retained verbatim as the record-artifact
  renderer; its title/author identity wording ("Supporting Information" → "record",
  `si.py:280,327,329,336-340`) re-named to read as the record (REQ-SA-203).
- `src/sci_adk/render/paper.py` — the `paper.py` prose machinery
  (`_latex_sanitize_prose`, `_novelty_prose`, `substitute_factrefs` wiring,
  `render_paper_latex` IMRaD skeleton) reused for the authored `si.tex` path (REQ-SA-101).
- `src/sci_adk/render/prose.py` — the prose slot model for the authored SI (free-structured
  sections), distinct from the deterministic `SIProse` overview/notes wrapper.
- `src/sci_adk/loop/compiler.py` — `compiler.py:587-593` re-targets the deterministic dump to
  the deposit's `record.tex`; a NEW authored `si.tex` render call is added (REQ-SA-202). The
  exact deposit PATH for `record.tex` is fixed in M1 and is the SINGLE SOURCE the
  deposit-completeness checker (REQ-SA-301) references — the C-gate test MUST read that source,
  not hard-code a path assumption (F4: implementer discretion on the path, but one source of
  truth).
- `src/sci_adk/render/consistency.py` — `check_cross_doc_s_refs` reused unchanged as the linkage
  gate (REQ-SA-403).
- `src/sci_adk/render/factref.py` — the `\evval`/`\status` fidelity gate reused unchanged over
  the authored `si.tex` (REQ-SA-103).
- `src/sci_adk/render/pkgreqs_checks.py` — `readme_submission_readiness_problems` (L448) is the
  precedent for the NEW deposit-completeness check (REQ-SA-301).
- `src/sci_adk/loop/verify.py` — `_PAPER_DOCS` (L114), P2 number-audit (L908,1145):
  CHARACTERIZED as already covering `si.tex` (D, four checkers). The per-run tool-vocab gate
  `_check_paper_tool_vocab` (L826-837) currently scans `draft.tex` ONLY and EXEMPTS `si.tex`; it
  is EXTENDED to scan `si.tex` while keeping `record.tex` exempt (REQ-SA-204, the NEW belief-side
  work). The package-path tool-vocab scan (L1196) already covers `si.tex` and is unchanged. The
  deposit-completeness check is wired in additively (REQ-SA-301/305).
- **Stale comments to update (F5).** Comments/docstrings that describe `si.tex` as "the record
  dump (EXEMPT)" become false once `si.tex` is authored belief and MUST be corrected to the new
  model: `verify.py:117-118` (`_PACKAGE_SI` "si.tex is the record dump (EXEMPT ...)"),
  `verify.py:826-832` (`_check_paper_tool_vocab` docstring "the SI is openly the record dump ...
  never scanned"), and `verify.py:163-188` (the `paper_consistency`/`_PAPER_DOCS` doc block
  describing `si.tex` as the dump). Updating these is part of the M1 (relocation) / M4
  (characterization) exit criteria.

### M5 (package-path) affected surfaces (evidence map)

- `src/sci_adk/render/package.py` — `_run_builders` (L274-311) currently runs `make_si.py` to
  write `01_manuscript/si.tex` (L298-304, the dump label). M5 re-targets the `make_si.py` output
  to `06_provenance/record.tex` (REQ-SA-505) and makes `_ensure_manuscript` (L385-425) preserve
  an author-supplied `package_src/si.tex` symmetric to `main.tex` (REQ-SA-501/502). The
  `_write_readme` / `_write_manifest` layout strings (L717-779) referencing `01_manuscript/si.tex`
  as the SI and `make_si.py -> 01_manuscript/si.tex` are updated to the new model.
- `src/sci_adk/templates/research-workspace/package/04_scripts/make_si.py` — the dump LOGIC is
  reused as the package record renderer (REQ-SA-504); its output path `OUT` (L43) re-targets to
  `06_provenance/record.tex` and its title/identity wording ("Supporting Information", L153, L161,
  L167) re-named to read as the record (REQ-SA-506). The hand-avoidance of toolchain nouns
  (L165-166) is no longer the gate-passing mechanism (the record is now exempt, REQ-SA-507).
  **F2: `make_si.py` MUST also emit a "Data & code availability" statement into the
  `06_provenance/record.tex` body (REQ-SA-506a)** — this is the AUTHORITATIVE source the M2 checker
  reads (`pkgreqs_checks.py:499`); `make_si.py` currently has no such phrase (grep 0), so emitting
  it is part of the M5 record-renderer change (it is record prose, no `\evval`, so it stays
  number-audit-clean and inside the exempt artifact).
- `src/sci_adk/render/pkgreqs_checks.py` — `deposit_completeness_problems` (L474) is REUSED
  verbatim for the package; a package record-path helper (symmetric to
  `compiler.deposit_record_path`, the M1 single source) supplies the `06_provenance/record.tex`
  path. Whether that helper lives in `render/package.py` or beside `PACKAGE_FOLDERS` is implementer
  discretion, but it is ONE source the package C-gate reads (mirrors F4). **F4 reference:** the
  checker reports the record-missing line and RETURNS (L491-498), then the availability-missing line
  only if the record is present (L499-503) — ONE problem at a time, never both; "availability without
  record" cannot arise (L494-495). The package C-gate test asserts this one-at-a-time behavior, not
  "both named separately."
- `src/sci_adk/loop/verify.py` — the package scan (`_check_package_requirements`, L1156-1323):
  the package `si.tex` is now authored (number-audit L1210-1215, tool-vocab L1250-1256,
  value-fidelity L1258-1266 are UNCHANGED in computation, REQ-SA-503/513). The package
  deposit-completeness check (REQ-SA-508) is wired in ADDITIVELY here, reusing
  `deposit_completeness_problems` pointed at a package record-path source. **F3: because the package
  path computes `clean = not problems` / `passed = clean` (`verify.py:550,558`) — UNLIKE per-run
  where `deposit_complete` is a separate non-gating channel (`verify.py:465-466`) — appending the
  deposit check to `problems` makes it a HARD gate in the package path (intended asymmetry,
  REQ-SA-510).** Stale package comments ("`si.tex` is the record dump", L1248-1249, and the
  `_PACKAGE_SI` doc block L125-132) are corrected.
- `src/sci_adk/templates/research-workspace/.claude/skills/science-workflow-package/SKILL.md` —
  step 3 (author the merged manuscript) updated so `si.tex` is authored from `package_src/si.tex`
  (REQ-SA-512); the layout/gate descriptions (L104-129) updated to the new model (authored
  `01_manuscript/si.tex`, deterministic record at `06_provenance/record.tex`).
- **M5 measured-fact note:** unlike per-run M1 (which ADDED a `si.tex` scan), the package gate
  ALREADY scans `si.tex`; the M5 boundary correction is achieved by RELOCATION (moving the record
  out of the scanned slot) rather than by extending a scan. There is therefore NO package analogue
  of the per-run RED→GREEN tool-vocab AC — the package tool-vocab test instead asserts the record
  artifact at `06_provenance/record.tex` is NOT scanned while the authored `si.tex` still is.

### M6 (SI-bibliography) affected surfaces (evidence map)

- `src/sci_adk/render/authored_si.py` — `render_authored_si_latex` (L113) gains an optional
  `bib_path` parameter; **Where** supplied, emit `\bibliographystyle{plainnat}` +
  `\bibliography{<stem>}` after the last authored section / figures block, BEFORE
  `\end{document}` (L244), mirroring `paper.py:831-834` and `si.py:540-543`. The preamble
  `\usepackage{natbib}` (L192) already exists — the gap is only the missing `\bibliography` +
  the missing parameter (REQ-SA-601/602/603).
- `src/sci_adk/render/paper.py` — the bib-wiring pattern to mirror is `paper.py:831-834`
  (bib present) + `paper.py:835` (no-bib branch). Reference only; unchanged (REQ-SA-616).
- `src/sci_adk/render/si.py` — `render_si_latex` bib wiring `si.py:540-543` is the second
  symmetry anchor (the record dump). Reference only; unchanged (the deposit `record.tex` keeps
  its own `references.bib`, REQ-SA-616).
- `src/sci_adk/loop/compiler.py` — at the authored-SI render call (`compiler.py:625`): extract the
  cited-key set from the `AuthoredSI` section bodies (`prose.py:187,219`) via `cited_keys`
  (`pkgreqs_checks.py:113`) BEFORE the final render (D2 ordering — no `bib_path`↔`cited_keys`
  circularity; valid because `_slot` preserves `\cite` verbatim, `authored_si.py:157-177`), filter
  the pool located by `_locate_bib_path` (`compiler.py:814`,
  `runs/<id>/artifacts/literature/references.bib`) to those keys, co-locate the subset to
  `paper/references_SI.bib` (new helper symmetric to `_colocate_bib`, `compiler.py:818`), then pass
  its path to the SINGLE final render (REQ-SA-604/605). **D6:** when no citations / no pool, write
  NO `references_SI.bib` and pass no `bib_path` (REQ-SA-606). **D3:** correct the STALE comment at
  `compiler.py:544` so the false phrase "wired into BOTH documents" no longer appears at that site
  (REQ-SA-607, grep-testable — AC-F6).
- `src/sci_adk/render/pkgreqs_checks.py` — `cited_keys` (L113) + `bib_keys` (L124) are the pure
  helpers for the cited-only subset (REQ-SA-604/605); `cite_resolution_problems` (L129) is the
  REUSED SI cite-resolution checker (REQ-SA-611). No new checker (REQ-SA-616).
- `src/sci_adk/render/package.py` — `_ensure_manuscript` (L400-456): add
  `01_manuscript/references_SI.bib` alongside `references.bib` — preserve
  `package_src/references_SI.bib` verbatim if present (symmetric to L431-432), else the cited-only
  subset of the package bib filtered by the package SI's cited-key set (REQ-SA-608/609). Add
  `_REFERENCES_SI_BIB = "references_SI.bib"` beside `_REFERENCES_BIB` (L72). **D1 — two cases for
  the `\bibliography{references_SI}` line:** (a) an author-supplied `package_src/si.tex` is copied
  VERBATIM (`package.py:449-451`), so the AUTHOR owns the `\bibliography` line and the assembler
  ONLY lands `references_SI.bib` beside it — it MUST NOT inject wiring into the copied file
  (REQ-SA-608a); a missing/wrong author bibliography is surfaced by the SI cite gate (REQ-SA-613),
  not silently repaired. (b) the deterministic `_skeleton_si_tex` (L459-482) is authored BY the
  assembler, so the assembler wires `\bibliography{references_SI}` in the skeleton IFF it cites
  anything, else omits it and writes no `references_SI.bib` (REQ-SA-608b/610).
- `src/sci_adk/loop/verify.py` — per-run `_check_paper_requirements` (the site of L1012-1018):
  additionally load `paper/references_SI.bib` and run `cite_resolution_problems(si_tex, si_bib)`
  over the per-run `si.tex`, additive to the existing `draft.tex` gate (REQ-SA-612). Package
  `_check_package_requirements` (the site of L1242): additionally load
  `01_manuscript/references_SI.bib` and run `cite_resolution_problems(si_tex, si_bib)` over the
  package `si.tex`, additive to the existing `main.tex` gate (REQ-SA-613). Both REUSE the pure
  checker; the SI `si_tex` is already read in the package scan (L1183) and available per-run.
- **M6 measured-fact note:** the authored `si.tex` is ALREADY number-audited / compile-checked /
  tool-vocab-scanned / value-fidelity-scanned on both paths (M1–M5) — the ONLY missing per-document
  check is cite-resolution (`cite_resolution_problems` covers `draft.tex`/`main.tex` only today,
  `verify.py:1014,1242`). M6 closes exactly that gap; it adds no other per-document computation.
