---
id: PAPER-GATE-001
version: 0.1.0
status: draft
created: 2026-06-26
updated: 2026-06-26
author: cyjoe
priority: high
issue_number: null
---

# SPEC-PAPER-GATE-001 — Paper-Writing / Packaging Hard-Gate Discipline

## HISTORY

- 2026-06-26 (v0.1.0): Initial draft. Brings the paper-writing/packaging stage under the
  same hard-gate discipline as the rest of the sci-adk engine, after a code audit + a real
  failed manuscript exposed three structural leaks that let a hand-assembled,
  manually-verified manuscript bypass essentially every gate. Design rationale to live at
  `design/paper-writing-enforcement.md`.

---

## Context and Motivation

sci-adk's thesis: **agents propose; the engine judges by frozen criteria; no
self-certification; record (Evidence) vs belief (Claim).** Every stage honors this EXCEPT
paper writing/packaging, which is opt-in and markup-gated, so a hand-assembled,
manually-verified merged manuscript bypasses the engine's verdict.

This SPEC is a **verdict-path change to sci-adk (the product)**, built via the MoAI build
harness. It closes three structural leaks confirmed by code audit (file:line evidence
below) and corroborated by a real manuscript that exhibited all of them.

### Leak L1 — Vacuous-by-default publishing/package gate

- `loop/verify.py:831-833` — when `runs/<id>/pubreqs.json` is absent, the per-run
  publishing-requirements gate returns `[]` (vacuously clean, "backward compatible").
- `loop/verify.py:1082` — the workspace package venue-FORMAT checks run only
  `if pkgreqs is not None`.
- `loop/verify.py:443` — `verify_package` returns clean when there is NO `package/`, AND the
  format checks above are skipped without a frozen `pkgreqs.json`.
- Freezing the contract is OPTIONAL: publish `SKILL.md:95` says `/sci publish` *may FREEZE*
  a contract; NO hook requires it.
- The Stop hook
  (`templates/research-workspace/.claude/hooks/sci-adk/stop-verify-gate.sh:32,51`) only runs
  `sci-adk verify <run>` per-run for runs with a recorded Claim. It NEVER runs
  `sci-adk verify <workspace>`, so the package gate (`verify_package`, verify.py:431) is
  never enforced at session close.

### Leak L2 — Fidelity is opt-in per number

- Only values authored through `\evval`/`\status` macros (`render/factref.py`) or
  native-plot y-values pulled by `evidence_id` (`render/figures.py:392`) are record-bound.
- A number typed as a literal in prose, a hand-typed table cell, or a number inside an image
  figure is COMPLETELY outside the gate: `factref.py:29-34` documents this honest limit
  explicitly; `figures.py:408` states "no Evidence is consulted" for image figures.
- `find_unresolved_factrefs` (factref.py:204) only catches a *residual `\evval`/`\status`
  macro* left in the rendered `.tex` — it does NOT scan for bare numeric literals.
- There is NO check that every quantitative token in the manuscript maps to a verified
  Claim/Evidence value. The package README even ASSERTS "Every number in `main.tex` and
  `si.tex` maps to a row of `02_data/claims_all.csv`" (`render/package.py:631`) while
  NOTHING enforces it.

### Leak L3 — Merged manuscript prose is author-owned by construction

- `render/package.py:415-417` copies a hand-written `package_src/main.tex` VERBATIM ("author
  owns the prose", `package.py:393-394`); `references.bib` likewise (`package.py:407-408`).
- sci-adk has NO programmatic cross-run merge render — the narrative and all its numbers are
  hand-authored; only side tables (`claims_all.csv`, `run_index.csv`) and `si.tex` are
  record-derived.

### Secondary gaps

- **Citation-key shape never validated on the manuscript.** The `<Surname><Year>(+a/b)`
  convention is applied only at literature acquisition (`search/citation_keys.py`, via
  `loop/literature_acquirer.py:299`), ordered by DOI-ascending for a/b disambiguation. The
  only manuscript cite gate is *resolution* (`render/pkgreqs_checks.py:109`, package only),
  not key SHAPE. Per-run papers have no cite check at all (`verify.py` imports
  `cite_resolution_problems` only inside `_check_package_requirements`). Hand-inserted
  DOI-less `.bib` entries pass through untouched.
- **Section structure is presence-only, order-blind.** `required_sections_problems`
  (`render/pubreqs_checks.py:69`) tests presence via a set — ORDER is never checked.
  Conclusion is NOT in `DEFAULT_REQUIRED_SECTIONS` (`core/pubreqs.py:36`:
  Abstract/Introduction/Methods/Results/Discussion). `PackageReqs.required_sections` defaults
  to EMPTY (`core/pkgreqs.py:100`).
- **Venue word-limit checks are contract-gated** (vacuous without a frozen contract; same
  posture as L1).
- **Package-gate F2 wiring gap.** `PubReqs` carries `figure_font_policy` + `image_min_dpi`
  (`core/pubreqs.py`), but `PackageReqs` carries only `required_sections`, `reference_style`,
  `abstract_max_words` (`core/pkgreqs.py:100-107`). `_check_package_requirements`
  (verify.py:1082-1094) therefore omits the font/DPI checks the per-run gate has.

### Real-world evidence (the failure mode this SPEC must prevent)

A hand-built manuscript at a separate workspace exhibited ALL of these: IMRaD broken (Methods
last, after Discussion; no Conclusion; results sections never grouped); venue contract
violated and ungated (abstract over a declared limit; body over a declared range);
non-conforming cite keys + mis-disambiguated duplicates + an uncited defined entry + a
load-bearing unpublished placeholder citation; only the pre-registered point statistic per
hypothesis traceable to the record while every contrast/ratio/range/importance number in prose
was hand-typed with no record row and no checker; and a desynced manifest (figure/bib counts
wrong, a redundant duplicate zip shipped). This manuscript is **evidence of the failure mode
only** — see the domain-neutrality constraint below.

---

## Terminology

- **Conclusion-bearing artifact**: a per-run paper draft (`paper/draft.tex`) or an assembled
  workspace package (`package/`) whose manuscript asserts findings — operationally, a draft
  that contains at least one figure, at least one `\cite`, or at least one section beyond
  Abstract, OR a package directory that exists at all. (The exact trigger predicate is
  OD-1.)
- **Frozen contract**: a `pubreqs.json` (per-run) or `pkgreqs.json` (workspace) frozen via
  `sci-adk pubreqs freeze` / its package equivalent, carrying a tamper-evidence digest.
- **Recorded-value pool**: the set of quantitative values the engine can derive from the
  record (Claim point statistics, Evidence Result scalars, per-figure CSVs the figures were
  rendered from). Its exact scope is OD-2.
- **Quantitative token**: a numeric literal in rendered prose or a table cell (integer,
  decimal, scientific notation, percentage, ratio like `4.6x`), excluding tokens the audit
  is configured to ignore (section/figure/table/equation/reference numbers, dates, page
  numbers, math-mode structural literals). The exact tokenizer scope is OD-3.

---

## Requirements (EARS)

Requirement IDs use the `REQ-PG-NNN` prefix. Pillars: P1 (non-vacuous gate), P2
(number-audit), P3 (citation-key shape), P4 (section order + word limits), P5 (cross-run
merge render). Keyword conventions: **shall** (ubiquitous), **When** (event-driven),
**While** (state-driven), **Where** (optional/feature), **If…then** (unwanted-behavior).

### P1 — Mandatory, non-vacuous publishing/package gate

- **REQ-PG-101 (Unwanted-behavior).** **If** a conclusion-bearing artifact exists with NO
  frozen contract, **then** `sci-adk verify` **shall** emit a loud REFUSAL/WARNING naming the
  missing contract and **shall not** return a silent clean pass for that artifact.
- **REQ-PG-102 (Event-driven).** **When** `/sci publish` runs to produce a conclusion-bearing
  paper, the workflow **shall** require a frozen `pubreqs.json` as a completion step (freeze
  is no longer optional for a conclusion-bearing paper).
- **REQ-PG-103 (Event-driven).** **When** `/sci package` runs to assemble a `package/`, the
  workflow **shall** require a frozen `pkgreqs.json` as a completion step.
- **REQ-PG-104 (Event-driven).** **When** a session reaches the Stop hook, the gate **shall**
  run `sci-adk verify <workspace>` (the package gate) in addition to the existing per-run
  claim-reproduction audit, and **shall** block Stop if the package gate fails.
- **REQ-PG-105 (Ubiquitous).** The default `required_sections` for a conclusion-bearing
  artifact **shall** be the IMRaD set including Conclusion
  (Abstract/Introduction/Methods/Results/Discussion/Conclusion) when the author selects "use
  defaults".
- **REQ-PG-106 (Ubiquitous).** `PackageReqs` **shall** carry `figure_font_policy` and
  `image_min_dpi` fields, and the workspace package gate **shall** apply the font-policy and
  raster-DPI checks the per-run gate already applies (closing the F2 wiring gap).
- **REQ-PG-107 (Unwanted-behavior, FROZEN-preserving).** **If** any P1 change is applied,
  **then** it **shall not** weaken or bypass the existing record-green / claim-reproduction
  gate (`verify_run`) — the new gates are additive.
- **REQ-PG-108 (State-driven, migration).** **While** the posture change from
  "absent-contract = vacuously clean" to "loud refusal" is in effect, the system **shall**
  surface the refusal as an actionable message (what to freeze, how) rather than a silent
  behavior flip, and the migration note **shall** be recorded in
  `design/paper-writing-enforcement.md`.

### P2 — Reproducible number-audit (central fix)

- **REQ-PG-201 (Ubiquitous).** A `sci-adk verify` checker **shall** tokenize every
  quantitative token in `main.tex` and `si.tex` (prose and tables) of a conclusion-bearing
  artifact.
- **REQ-PG-202 (Unwanted-behavior).** **If** a tokenized quantitative token does NOT map to a
  verified value in the recorded-value pool, **then** the number-audit **shall** FAIL and
  name the unbacked token(s) and their location.
- **REQ-PG-203 (Ubiquitous, record-vs-belief invariant).** The number-audit **shall** compare
  tokens ONLY against RECORDED values; it **shall not** fabricate, infer, or accept a
  "seems-right" value, and a human/agent manual spot-check **shall not** substitute for the
  gate.
- **REQ-PG-204 (Event-driven).** **When** the number-audit runs, it **shall** be
  deterministic and re-runnable by a third party from the shipped record alone (replacing
  manual spot-checking with a reproducible audit).
- **REQ-PG-205 (Optional / configurable, depends on OD-2).** **Where** the chosen
  record-backing strategy requires reportable quantities beyond the pre-registered point
  statistic, the engine **shall** provide a recorded home for those quantities (e.g. recorded
  Evidence values and/or per-figure CSVs) so that contrast/ratio/range/importance numbers
  have a record row.
- **REQ-PG-206 (Optional, depends on OD-2).** **Where** the chosen strategy refuses bare
  literals, every prose number **shall** be a record-pulled macro (`\evval`-style), and a
  bare quantitative literal in a conclusion-bearing slot **shall** be refused.

### P3 — Citation-key format enforcement

- **REQ-PG-301 (Ubiquitous).** A non-vacuous `sci-adk verify` checker, applied to BOTH the
  per-run paper and the package, **shall** validate that every `\cite` key and every defined
  `.bib` entry key conforms to `<Surname><Year>(+a/b)`.
- **REQ-PG-302 (Unwanted-behavior).** **If** a `\cite` key or `.bib` key does not conform to
  `<Surname><Year>(+a/b)`, **then** the citation-key checker **shall** FAIL (or deterministically
  re-key per OD-4) and name the offending key(s).
- **REQ-PG-303 (Unwanted-behavior).** **If** two entries share a base `<Surname><Year>` and
  are mis-disambiguated (e.g. a bare key plus a `…b` with no `…a`), **then** the checker
  **shall** FAIL and name the mis-disambiguated group.
- **REQ-PG-304 (Optional / warning).** **Where** a load-bearing citation is
  unpublished / DOI-less / tentative, the checker **shall** surface a WARNING naming the entry
  (not necessarily a FAIL — see OD-5).
- **REQ-PG-305 (Ubiquitous).** The per-run paper **shall** also be subject to cite-resolution
  (every `\cite` key resolves to a defined `.bib` entry), closing the per-run cite-gate gap.

### P4 — Section structure and ORDER

- **REQ-PG-401 (Ubiquitous).** The section checker **shall** enforce section ORDER against the
  declared venue order (default IMRaD:
  Introduction→Methods→Results→Discussion→Conclusion), not presence alone.
- **REQ-PG-402 (Unwanted-behavior).** **If** the manuscript's section order deviates from the
  declared/default order, **then** the checker **shall** FAIL (or WARN per a declared venue
  override — see OD-6) and name the out-of-order sections.
- **REQ-PG-403 (Ubiquitous).** Conclusion **shall** be part of the default required-section
  set (consistent with REQ-PG-105).
- **REQ-PG-404 (State-driven).** **While** a frozen contract declares abstract and/or body
  word limits, the word-limit checks **shall** actually gate (FAIL on violation) via P1's
  non-vacuous posture.

### P5 — Cross-run merge render (architectural, M3)

- **REQ-PG-501 (Ubiquitous).** sci-adk **shall** provide a programmatic cross-run merge-render
  that extracts numbers, tables, and figures from ALL listed runs' records into the merged
  manuscript, leaving ONLY prose for the agent to author.
- **REQ-PG-502 (Ubiquitous).** Record-extracted content (numbers, tables, figures) in the
  merged manuscript **shall** be gated (record-faithful by construction); agent-authored prose
  **shall** be free, with the boundary between the two explicitly defined (OD-7).
- **REQ-PG-503 (Unwanted-behavior).** **If** the merged manuscript contains a record-typed
  quantity that was hand-typed rather than record-extracted, **then** the merge-render path
  **shall** make that structurally impossible or the number-audit (P2) **shall** FAIL on it.
- **REQ-PG-504 (Optional).** **Where** the merge-render is used, it **shall** subsume the P2
  number-audit for the merged case (numbers cannot be hand-typed), while P2 remains the gate
  for any author-supplied slot.

---

## Open Decisions (require orchestrator confirmation)

- **OD-1 — Conclusion-bearing trigger predicate (affects P1, P2, P3, P4).** What exactly
  triggers "must have a frozen contract / must be audited"? Proposed: a `paper/draft.tex`
  with ≥1 figure OR ≥1 `\cite` OR ≥1 non-Abstract section; AND any existing `package/`.
  Confirm the predicate and whether a pure-null-result note (no asserted finding) is exempt.
- **OD-2 — P2 record-backing strategy (the keystone decision).** Today the record stores only
  the one pre-registered `point_statistic` per hypothesis, so contrast/framing numbers have
  no record row. Choose one (or a staged combination):
  - **(i) Extend the record** so all reportable quantities are recorded Evidence values
    (most faithful; largest surface change; requires authors to record framing numbers).
  - **(ii) Require record-pulled macros** for every prose number (`\evval`-style); bare
    literals refused (smallest engine change; heaviest author-ergonomics cost; strongest
    guarantee).
  - **(iii) Audit against a broader recorded-value pool** (Claims + per-figure CSVs the
    figures were rendered from) (middle ground; risk of false-negatives if a reported number
    is a transform of recorded values, e.g. a ratio of two recorded means — confirm whether
    derived/transform numbers are in or out of scope).
  Recommendation to weigh: stage (iii) first (closes most of the hole with least friction),
  then (ii) for slots that must be exact. Confirm choice and the derived-number policy.
- **OD-3 — Tokenizer scope (affects P2).** Which numeric tokens are audited vs ignored?
  Proposed ignore-list: section/figure/table/equation/reference numbers, dates, page numbers,
  version strings, and math-mode structural literals; audited: prose decimals/percentages/
  ratios and table data cells. Confirm the ignore-list and whether table cells are in M1 or
  deferred.
- **OD-4 — P3 fail vs re-key.** On a non-conforming cite/.bib key, FAIL (author must fix) or
  deterministically re-key (engine rewrites, DOI-ascending a/b as at acquisition)? Re-key is
  more automatic but mutates author files; FAIL is more transparent. Recommendation: FAIL on
  the manuscript (author-owned), reserve re-keying for the acquisition path that already does
  it.
- **OD-5 — P3 unpublished/tentative citation: WARN vs FAIL.** A load-bearing
  unpublished/DOI-less placeholder is a real risk but legitimately occurs (preprints,
  in-prep). Recommendation: WARN (surfaced, not blocking). Confirm.
- **OD-6 — P4 order FAIL vs WARN for declared non-IMRaD venues.** Some venues legitimately
  reorder (e.g. Methods-last journals). Recommendation: FAIL against the *declared* order;
  default IMRaD when undeclared; WARN only when no order is declared at all. Confirm.
- **OD-7 — P5 record/prose boundary.** Exactly which manuscript regions are
  record-extracted (gated) vs agent-authored (free)? Proposed: numbers, data tables, and
  figures are record-extracted; section prose, framing, and interpretation are agent-authored.
  Confirm, and confirm M3 may land after M1/M2 ship the per-slot gates.
- **OD-8 — Migration loudness (affects REQ-PG-108).** The current "absent contract =
  vacuously clean" was a deliberate backward-compat rule. Confirm the migration posture:
  loud REFUSAL (verify exits non-zero) vs loud WARNING (verify warns but exits zero for a
  grace period) for *existing* runs that predate this SPEC. Recommendation: WARNING for
  pre-existing runs, REFUSAL for any artifact produced after this SPEC ships.

---

## Decisions Confirmed (M1 keystone — 2026-06-26, orchestrator + user)

The M1-blocking open decisions are resolved as follows. OD-4/5/6 were confirmed when M2
began and OD-7 when M3 began (see "Decisions Confirmed (M2 + M3)" below).

- **OD-2 → STAGED.** P2 record-backing = stage (iii) first (audit every quantitative
  token against a broad recorded-value pool: Claim point statistics + Evidence Result
  scalars + the per-figure CSVs figures were rendered from), THEN stage (ii) (require
  record-pulled macros; refuse bare literals). Include a derived-number policy for
  ratios/transforms of recorded values (a derived value matches if it is recomputable
  from recorded values within tolerance). Stage (iii) is the M1 deliverable; (ii) is a
  follow-on within P2.
- **OD-1 → STRICT.** The conclusion-bearing trigger is ANY `paper/draft.tex` OR ANY
  `package/` — no null-result exemption. Every such artifact must have a frozen contract
  and pass the number-audit.
- **OD-3 → prose numbers + table cells, in M1.** Tokenizer audits prose decimals /
  percentages / ratios AND table data cells; ignore-list = section / figure / table /
  equation / reference numbers, dates, page numbers, version strings, and math-mode
  structural literals.
- **OD-8 → IMMEDIATE REFUSAL for all.** No grace period: `sci-adk verify` exits non-zero
  for ANY conclusion-bearing artifact (existing or new) that lacks a frozen contract or
  fails the number-audit.

**OD-8 migration consequence (M1 scope):** with immediate refusal + the strict OD-1
trigger, the in-repo demo runs (`runs/t1-godel`, `runs/t1-demo`) and any test asserting
they verify-green will FAIL once the gate ships. M1 MUST therefore bring the in-repo
demo artifacts into compliance (freeze a compliant `pubreqs.json` and ensure their
numbers audit clean) and update the affected tests — the flagship demo must exemplify
the discipline, not be exempt from it.

---

## Decisions Confirmed (M2 + M3 — 2026-06-26, orchestrator + user)

- **OD-4 → FAIL (no re-key).** A non-conforming `\cite`/`.bib` key FAILS with the offending
  key named; the engine never rewrites author files (re-keying stays in the acquisition path,
  `search/citation_keys.py`).
- **OD-5 → WARN.** A load-bearing unpublished/DOI-less citation is a non-blocking advisory
  warning, not a gate failure.
- **OD-6 → declared-order FAIL / undeclared WARN.** Section order FAILS against a *declared*
  `required_sections` order; with no order declared, deviation from default IMRaD is a WARN.
- **OD-7 → record-extracted numbers/tables/figures, free prose; CLEAN LITERALS, no macro.**
  The merge render (P5) extracts each run's recorded point statistic + pre-registered
  threshold from the package record table (`02_data/claims_all.csv`) and writes them into the
  merged `main.tex` as PLAIN numeric literals — NOT `\evval`-style macros — so the
  reviewer-facing source carries no opaque shorthand (user constraint, 2026-06-26). Section
  prose, framing, and interpretation are the agent's free slots. The verdict stays the
  DETERMINISTIC package number-audit (no LLM judge): every emitted literal is a member of the
  audit pool built from that same CSV, so the manuscript passes P2 by construction (REQ-PG-504)
  and any later hand-edit to a non-record value FAILS P2 (REQ-PG-503). Figures are extracted by
  co-location into `03_figures/` and referenced from the record dump (`si.tex`); inline figure
  includes in `main.tex` are a follow-on.

---

## Exclusions (What NOT to Build)

- **No NLP / semantic understanding of prose.** The number-audit and section/cite checks are
  deterministic markup/token checkers, consistent with sci-adk's existing gate language
  (ref/label, `\novelty`, factref). No language model judges the manuscript.
- **No LLM in the verdict path.** Gates are deterministic and re-runnable; an agent's or a
  human's manual review is never the verdict (record-vs-belief invariant).
- **No weakening of the existing record-green / claim-reproduction gate.** All new checks are
  additive; `verify_run`'s claim reproduction is untouched.
- **No domain/venue/study specialization.** No requirement, checker, or default may name or
  assume a specific domain, venue, or study. (See Domain-Neutrality constraint.)
- **No automatic prose rewriting or content generation by the gate.** The gate refuses or
  warns; it does not author or "fix" prose (re-keying of author .bib is explicitly out of
  scope unless OD-4 selects it).
- **No page-count gating** (no deterministic page count without a compile; remains advisory,
  consistent with `core/pubreqs.py` `max_pages`).
- **No change to the acquisition-time citation-keying** (`search/citation_keys.py` keeps
  owning the canonical convention; P3 only *validates* the manuscript against it).

---

## [HARD] Constraints

- **Domain-neutral.** The SPEC, its requirements, and the resulting code MUST be
  domain-general. The real manuscript is evidence of the failure mode only — no general
  surface may name or assume a domain, venue, or study. (A prior domain-generality audit
  removed such leaks; do not reintroduce any.)
- **Honor FROZEN invariants.** Record vs belief (audit compares against RECORDED values, never
  fabricates or accepts "seems-right"); no self-certification (the gate is the verdict, not a
  manual check); do not weaken the existing claim-reproduction / record-green gate.
- **Backward-compat honesty.** P1 changes the "absent contract = vacuously clean" posture;
  specify it as a loud refusal/warning + a required freeze in the workflow, never a silent
  behavior change. Record the decision and migration notes (REQ-PG-108, OD-8).
- **Minimal, no over-engineering.** Smallest gates that close the holes; acceptance criteria
  concrete and testable.
- **Suite stays green.** The existing suite (~1281 tests) MUST stay green; each new gate needs
  tests; Docker-dependent tests marked `integration`.

---

## Design Rationale Pointer

A design rationale record for this SPEC MUST live at
`design/paper-writing-enforcement.md` (sci-adk's design docs live in `design/`, not under
`.moai/`). It records: the three leaks with file:line evidence, the chosen OD resolutions
(especially OD-2's record-backing strategy), the migration posture (OD-8), and the
record/prose boundary (OD-7). It cross-references `design/near-submission-package.md`,
`design/paper-publishing-requirements.md`, `design/render-architecture-reframe.md`, and
`design/research-session-enforcement.md`.

---

## Affected Surfaces (evidence map, for the Run phase — not implementation guidance)

- `src/sci_adk/loop/verify.py` — `_check_pubreqs` (L831), `_check_package_requirements`
  (L1008, L1082 guard), `verify_package` (L431), Stop-hook integration target.
- `src/sci_adk/core/pubreqs.py` — `DEFAULT_REQUIRED_SECTIONS` (L36, add Conclusion).
- `src/sci_adk/core/pkgreqs.py` — `PackageReqs` (add `figure_font_policy`, `image_min_dpi`).
- `src/sci_adk/render/pubreqs_checks.py` — `required_sections_problems` (L69, add order).
- `src/sci_adk/render/pkgreqs_checks.py` — `cite_resolution_problems` (L109).
- `src/sci_adk/render/factref.py` — number-audit companion (L204 `find_unresolved_factrefs`).
- `src/sci_adk/search/citation_keys.py` — canonical key convention (validation reuse).
- `src/sci_adk/render/package.py` — verbatim author copy (L415), merge-render target (P5).
- `templates/research-workspace/.claude/hooks/sci-adk/stop-verify-gate.sh` — add
  `verify <workspace>` (REQ-PG-104).
- `.claude/skills/.../science-workflow-publish/SKILL.md` — freeze-required wording
  (REQ-PG-102/103).
