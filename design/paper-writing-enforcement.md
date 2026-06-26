# Paper-Writing / Packaging Hard-Gate Discipline — closing the three leaks

> Status: **M1 KEYSTONE BUILT (2026-06-26)** — P1 (non-vacuous refusal) + P2 (number-audit)
> implemented test-first (RED→GREEN→REFACTOR), suite green. M2 (P3 citation-key shape +
> P4 section order/word-limits) and M3 (P5 cross-run merge render) remain open; their open
> decisions (OD-4/5/6/7) are confirmed when those milestones begin.
>
> SPEC: `.moai/specs/SPEC-PAPER-GATE-001/` (spec.md / plan.md / acceptance.md).
> Cross-references: `design/near-submission-package.md` (the workspace package layer),
> `design/paper-publishing-requirements.md` (per-run F1/F2/F3 `pubreqs.json`),
> `design/render-architecture-reframe.md` (the moved line + the `\evval`/`\status` fidelity
> gate this generalizes), `design/research-session-enforcement.md` (the Stop-hook gate).

This record captures WHY the paper-writing/packaging stage needed the same hard-gate discipline
as the rest of the engine, the three structural leaks a code audit found (with file:line
evidence), the open-decision resolutions that scoped M1, and the migration posture.

---

## 0. The thesis it restores

sci-adk's thesis: **agents propose; the engine judges by frozen criteria; no
self-certification; record (Evidence) vs belief (Claim).** Every stage honored this EXCEPT
paper writing/packaging, which was opt-in and markup-gated — so a hand-assembled,
manually-verified merged manuscript bypassed the engine's verdict. A real failed manuscript
exhibited every leak below; it is **evidence of the failure mode only** — no general surface
here names or assumes a domain, venue, or study (the domain-neutrality constraint).

---

## 1. The three leaks (file:line evidence, at audit time)

### L1 — Vacuous-by-default publishing/package gate

- `loop/verify.py` `_check_paper_requirements`: when `runs/<id>/pubreqs.json` was absent the
  per-run publishing gate returned `[]` (vacuously clean, "backward compatible").
- `loop/verify.py` `_check_package_requirements`: the package venue-FORMAT checks ran only
  `if pkgreqs is not None`; `verify_package` returned clean when there was no `package/`.
- Freezing a contract was OPTIONAL — no hook required it; the Stop hook only ran
  `sci-adk verify <run>` per-run, never `sci-adk verify <workspace>` (the package gate).

### L2 — Fidelity was opt-in per number

- Only values authored through the `\evval`/`\status` macros (`render/factref.py`) or
  native-plot y-values pulled by `evidence_id` (`render/figures.py`) were record-bound.
- A number typed as a literal in prose, a hand-typed table cell, or a number inside an image
  figure was COMPLETELY outside the gate. `find_unresolved_factrefs` only caught a *residual
  macro* in the rendered `.tex`; nothing scanned for bare numeric literals. The package README
  even ASSERTED "every number maps to a row of `claims_all.csv`" while nothing enforced it.

### L3 — Merged manuscript prose was author-owned by construction

- `render/package.py` copied a hand-written `package_src/main.tex` VERBATIM ("author owns the
  prose"); there was no programmatic cross-run merge render — the narrative and all its numbers
  were hand-authored. (M3/P5 territory; the M1 number-audit is the per-slot fallback gate.)

---

## 2. Open-decision resolutions (M1 keystone, confirmed 2026-06-26)

| OD | Resolution (M1) |
|----|-----------------|
| **OD-1** | **STRICT.** Conclusion-bearing = ANY `paper/draft.tex` (per-run) OR ANY `package/` (workspace). No null-result exemption. A run with neither is NOT conclusion-bearing (the vacuous-clean path survives there). |
| **OD-2** | **STAGED → stage (iii) first.** Audit every quantitative token against a BROAD recorded-value pool: Claim point statistics + Evidence Result scalars (incl. `finding` JSON + the pre-registered DecisionRule thresholds) + the per-figure CSV values (`02_data/*.csv` for a package). Derived-number policy: a value recomputable from TWO recorded operands by ratio/difference/sum/product within tolerance is accepted. Stage (ii) (require record-pulled macros; refuse bare literals) is a follow-on within P2. |
| **OD-3** | **prose numbers + table cells, in M1.** Audited = prose decimals/percentages/ratios AND table data cells. Ignore-list = section/figure/table/equation/reference numbers (the args of `\ref`/`\cite`/`\label`/`\section`/`\eqref`…), dates, page numbers, version strings, macro-definition arity/`#N` args, verbatim/code/path/URL spans (`\texttt`/`\verb`/`\path`/`\url`), and math-mode structural literals (`$…$`, `\[…\]`, equation environments). |
| **OD-8** | **IMMEDIATE REFUSAL for all.** No grace period: `sci-adk verify` exits non-zero for ANY conclusion-bearing artifact (existing or new) lacking a frozen contract or failing the number-audit. |

**M2 open decisions (confirmed 2026-06-26):** OD-4 (P3 fail-vs-rekey) = **FAIL and name the key**
(never re-key — author files are not mutated; the acquisition path `search/citation_keys.py`
owns deterministic re-keying). OD-5 (P3 unpublished/DOI-less) = **WARN** (surfaced via the report
advisory, never gated). OD-6 (P4 order) = **FAIL against a DECLARED order** (the contract's
`required_sections` list order), **WARN against the default IMRaD order when undeclared**.

OD-7 (P5 record/prose boundary) remains open — confirmed when M3 begins.

---

## 3. What M1 built (P1 + P2)

### P1 — non-vacuous refusal (REQ-PG-101/107/108)

- `loop/verify.py::_check_paper_requirements` — a per-run run WITH a `paper/draft.tex` but NO
  frozen `pubreqs.json` now returns a LOUD, actionable refusal naming what to freeze
  (`sci-adk pubreqs freeze <run>`), replacing the silent `return []`. A run with NO `draft.tex`
  stays vacuously clean (the pre-paper path is unchanged).
- `loop/verify.py::_check_package_requirements` — a workspace WITH a `package/` but NO frozen
  `pkgreqs.json` now appends the analogous refusal (`sci-adk pkgreqs freeze <workspace>`); the
  layout/traceability/fidelity/record-green checks still run alongside it.
- **Additive (REQ-PG-107):** the existing claim-reproduction / record-green gate (`verify_run`)
  is untouched — a non-reproducing claim still FAILS exactly as before.

### P2 — reproducible number-audit (REQ-PG-201..204), the central fix

- New PURE checker `src/sci_adk/render/number_audit.py` (kernel; imports `sci_adk.core` only —
  the F4 seam). It tokenizes every quantitative literal in `main.tex` + `si.tex` (prose +
  table cells, OD-3 scope) and FAILS on any token absent from the recorded-value pool, naming
  the unbacked token and its source document. Deterministic, no LLM, third-party re-runnable.
- **Record vs belief (REQ-PG-203, FROZEN):** the audit compares ONLY against RECORDED values
  — it never fabricates, infers, or accepts a "seems-right" value; a human/agent spot-check
  does not substitute for the gate. The pool is the engine's own record (Claims + Evidence +
  the figure CSVs), exactly the values `\evval`/`\status` already pull.
- Wired into both `verify <run>` (per-run, pool from the recorded Claims/Evidence/Spec) AND
  `verify <workspace>` (package, pool from `02_data/*.csv`).

Tests: `tests/test_number_audit.py` (the pure checker — tokenizer scope, pool sources, derived
policy, tolerance) and `tests/test_paper_gate_enforcement.py` (the verify-side wiring — P1
refusal both paths, P2 fail-and-name + no-false-positive both paths, the additive guard).
MP-1 ⇒ `test_*_number_audit_fails_on_unbacked_token` + `test_*_passes_on_backed_manuscript`.
MP-4 ⇒ `test_per_run_draft_without_frozen_pubreqs_refuses` +
`test_package_without_frozen_pkgreqs_refuses`.

### P2 stage ii — exact-only audit for the broad package pool (OD-2 follow-on)

OD-2 staged stage (iii) first (the derived-number policy) and named stage (ii) — "require
record-pulled macros; refuse bare literals" — as a follow-on within P2. Stage (ii) is now built
for the package audit, closing the residual leniency that the broad pool made dangerous:

- **The leniency.** `RecordedValuePool.backs` accepts a token that is a ratio / difference / sum /
  product of TWO recorded operands within ~1% tolerance. Over the SMALL, curated per-run pool
  (Claim stats + Evidence scalars + Spec thresholds) the operand combinations are sparse and the
  policy is safe. Over the BROAD package pool (every numeric cell of the record CSVs — often
  hundreds) the `O(N^2)` operand space is dense enough that a coincidentally-matching WRONG number
  can pass. (Concretely: `1` and `0` were UNIVERSALLY "derivable" from any non-empty pool via the
  self-operations `a / a = 1` and `a - a = 0`.)
- **The resolution.** `number_audit_problems` takes `allow_derived` (default `True`). The per-run
  audit keeps it `True` (stage iii — small pool, derived policy on). The package audit passes
  `allow_derived=False` (stage ii — exact-only: a token is backed iff it EQUALS a recorded value,
  `pool.contains`). A genuinely derived quantity must then have a recorded home (an Evidence
  `finding` scalar or a data cell) pulled via `\evval`, not a hand-typed literal blind-matched by
  the operand search; the exact-only failure message says exactly this (REQ-PG-108 spirit).
- **Pool-coverage companion (necessary to avoid false positives).** Exact-only exposed a
  pre-existing gap the `a / a = 1` loophole had masked: the package pool was built from
  `02_data/*.csv` only, but the SI record dump (`make_si.py`) also reports the run-index counts
  from `06_provenance/run_index.csv` (e.g. `n_hypotheses = 1`). `RecordedValuePool.from_package`
  now unions BOTH record CSVs the manuscript dumps from, so a record-dumped count is backed by the
  record that holds it (a hex digest cell does not parse as a number, so it never enters the pool).
- **Honest bound (the maximal stage ii is deferred).** This does NOT yet require EVERY number to
  be a macro at the SOURCE prose. The package `main.tex` is copied verbatim (L3), so there is no
  agent-prose-slot structure on which to enforce macro-only authoring; the structural elimination
  of the hand-typing surface for the merged manuscript is P5 / M3 (the cross-run merge render).
  Stage ii here closes the specific documented derived-policy leniency on the broad pool — the leak
  that let a coincidentally-matching wrong number pass.

Tests: `tests/test_number_audit.py` (exact-mode rejects a derived-only value / accepts exact
recorded values / actionable message; `from_package` unions data + run-index and tolerates a
missing run-index) + `tests/test_paper_gate_enforcement.py::test_package_number_audit_refuses_a_derived_only_value`
(the verify-side wiring). The full suite stays green.

---

## 3b. What M2 built (P3 + P4)

### P3 — citation gates (REQ-PG-301..305)

New PURE checkers in `render/pkgreqs_checks.py` (beside `cited_keys` / `bib_keys` /
`cite_resolution_problems` — one cite-logic home), wired into BOTH the per-run paper gate and the
package gate:

- **Shape (REQ-PG-301/302, OD-4).** `citation_key_shape_problems` validates every `\cite` key AND
  every `.bib` entry key against the canonical `<Surname><Year>(+a/b)` shape (`_CITEKEY_SHAPE_RE`).
  FAIL and name the offenders — never re-key (the gate validates; `search/citation_keys.py` owns
  deterministic re-keying). Casing is NOT forced to a leading capital: the convention
  `normalize_surname` PRESERVES author casing (`vanderBerg2020a` is legitimate), so a
  capital-required rule would reject real keys.
- **Disambiguation (REQ-PG-303).** `citation_disambiguation_problems` groups conforming keys by
  base; a bare base coexisting with a suffixed sibling, or a non-contiguous `a/b/c…` run (a `…b`
  with no `…a`, or a gap), FAILS and names the group.
- **Unpublished WARN (REQ-PG-304, OD-5).** `unpublished_citation_warnings` flags a CITED key whose
  `.bib` entry has no `doi` field as a NON-BLOCKING warning (preprint/in-prep is legitimate),
  routed to the report advisory — never the gating problems.
- **Per-run cite resolution (REQ-PG-305).** The existing `cite_resolution_problems` (package-only)
  is now ALSO wired into the per-run paper gate, closing the per-run cite-gate gap.

### P4 — section ORDER + word-limit gating (REQ-PG-401..404)

- **Section order (REQ-PG-401/402, OD-6).** New `section_order_problems` (`render/pubreqs_checks.py`)
  compares the relative order of the sections present in BOTH the manuscript and the reference
  order (`ordered_section_sequence` records the abstract env + `\section`s in source order, EC-6).
  Severity routing lives in `loop/verify`: a DECLARED order (`required_sections` non-empty) → FAIL;
  an UNDECLARED order (empty) → WARN against the default IMRaD order (package advisory).
- **Word limits gate (REQ-PG-404 / AC-3).** The package `body_word_range` now GATES (it was
  advisory): `body_word_range_problems` FAILS when the body word count (the prose outside the
  abstract env, `body_word_count`) is outside the declared `(min, max)`. The per-run `max_words`
  and package `abstract_max_words` ceilings already gated. `core/pkgreqs.py`'s `body_word_range`
  doc + `_package_advisory` were updated (no longer an advisory note); the one in-repo test
  asserting the OLD advisory posture was rewritten to the gating discipline (the M1 pattern).

### WARN routing (scoping decision)

`PackageVerifyReport` has a non-gating `advisory` channel; the per-run `VerifyReport` does NOT. So
the WARN-type findings (unpublished citation, undeclared-order) route to the package advisory, and
the per-run path runs only the FAIL-type gates (shape, disambiguation, cite-resolution,
declared-order). REQ-PG-304 is "Optional/warning" and the motivating unpublished placeholder lived
in the merged manuscript, so package-scoped WARNs satisfy the SPEC. Adding a per-run advisory
channel (model + CLI surface) is a clean follow-on if per-run WARNs are wanted.

Tests: `tests/test_pkgreqs.py` (cite shape/disambiguation/unpublished + body-word units),
`tests/test_pubreqs.py` (section-order units), `tests/test_paper_gate_enforcement.py` (MP-2 order,
MP-3 cite-key, AC-3 word limits, AC-4 per-run resolution wiring), `tests/test_package_gate.py`
(body-range now-gates). Full suite green.

---

## 4. Migration posture (OD-8 consequence)

The flip from "absent contract = vacuously clean" to "loud refusal" is a verdict-path change,
surfaced as an actionable message (what to freeze, how), never a silent behavior flip.

**Existing in-repo tests that encoded the OLD posture were updated** to the discipline (they
freeze a minimal compliant contract, or assert the new refusal). The exact set changed:

- `tests/test_verify.py` — the seeded-paper consistency / cross-doc / tool-vocab tests freeze a
  minimal `pubreqs.json`; `test_verify_no_pubreqs_is_vacuously_clean` was SPLIT into
  `test_verify_no_pubreqs_with_draft_refuses` (new posture) + `test_verify_no_draft_is_vacuously_clean`
  (the surviving pre-paper path). The `0`-literal in the SI-exempt test was replaced with the
  recorded point estimate.
- `tests/test_cli_verify.py` — the three exit-0 paper tests freeze a minimal contract; the
  "no paper" exit-0 test removes the rendered `paper/` to exercise the genuine non-conclusion-
  bearing path.
- `tests/test_novelty_render.py` — the supported-novelty draft freezes a minimal contract.
- `tests/test_package_gate.py` — `test_package_gate_no_pkgreqs_still_runs_layout_and_traceability`
  → renamed/rewritten to assert the refusal AND that traceability still runs.
- `tests/test_package_smoke.py` — `test_cli_package_without_pkgreqs_still_gates_green` →
  rewritten to assert the refusal (exit non-zero + actionable message).
- `tests/test_operational_layer_smoke.py` — the end-to-end chain freezes a `pubreqs.json` after
  render (the new completion step) before the verify gate.

### Demo-run note (OD-8, demo migration)

The SPEC anticipated that the in-repo demos (`runs/t1-godel`, `runs/t1-demo`) would FAIL once
the gate ships and would need a frozen contract + a number-clean manuscript. **In fact neither
demo is conclusion-bearing under OD-1 strict:** they ship only Markdown (`paper/paper.md`,
`paper/draft.md`) — no `paper/draft.tex` and no `package/`. The OD-1 trigger keys on a rendered
`.tex` manuscript / assembled package, so the gate correctly does NOT fire on them, and they
still `verify` green (exit 0, `t1-godel` reproduces, `t1-demo`'s claim is its pre-existing
PROPOSED/UNRESOLVED state). **No demo migration was required.** Making a demo EXEMPLIFY the
discipline (render a real `draft.tex` + freeze a `pubreqs.json` whose numbers audit clean) is a
worthwhile follow-on but is scope-expansion beyond closing the leak — left for a follow-up so
M1 stays minimal.

---

## 5. Exclusions honored

- No NLP / semantic prose understanding; no LLM in the verdict path — the audit is a
  deterministic markup/token checker (the same design language as the ref/label, `\novelty`,
  and factref gates).
- No weakening of the claim-reproduction / record-green gate — all new checks are additive.
- No domain/venue/study specialization in any general surface (requirement, checker, default,
  message, test fixture).
- No automatic prose rewriting — the gate refuses or names; it never authors or "fixes" prose.

---

## 6. Clean seams for the next increment (deferred, NOT built)

> Status update: the P1/F2/IMRaD seams below were built in M1, and P3 + P4 in M2 (see §3 / §3b).
> The only genuinely-deferred pillar now is **P5 — cross-run merge render (M3)**; OD-7 (the
> record/prose boundary) is the one remaining open decision. The seam notes below are retained as
> the original design rationale.

- **P1 Stop-hook wiring (MP-5).** `templates/research-workspace/.claude/hooks/sci-adk/stop-verify-gate.sh`
  runs `sci-adk verify <run>` per-run today; it must ALSO run `sci-adk verify <workspace>` so
  the package gate fires at session close (REQ-PG-104). `verify_package` already returns the
  block reason; the hook just needs the extra invocation + exit-2 on failure.
- **F2 package-gate gap.** `core/pkgreqs.py::PackageReqs` lacks `figure_font_policy` +
  `image_min_dpi` (the per-run `PubReqs` has them). Add those fields and call
  `figure_font_policy_problems` / `image_dpi_problems` in `_check_package_requirements`
  (REQ-PG-106). The per-run checkers in `render/pubreqs_checks.py` are already pure and reusable.
- **IMRaD defaults incl. Conclusion (REQ-PG-105/403).** Add "Conclusion" to
  `core/pubreqs.py::DEFAULT_REQUIRED_SECTIONS` (and mirror in `core/pkgreqs.py`). M2/P4 also
  adds section-ORDER enforcement (`render/pubreqs_checks.py::required_sections_problems` is
  presence-only today) and turns word-limit checks into real gates via P1's non-vacuous posture.
- **P3 citation-key shape + per-run cite resolution (M2).** Validate `\cite`/`.bib` keys against
  `<Surname><Year>(+a/b)` (reuse `search/citation_keys.py`'s convention, validate-only), detect
  mis-disambiguated duplicate groups, WARN on unpublished/DOI-less load-bearing cites, and add
  the missing per-run cite-resolution check.
- **P5 cross-run merge render (M3).** A programmatic merge that extracts numbers/tables/figures
  from all listed runs' records, leaving only prose for the agent — making a hand-typed
  record-typed quantity structurally impossible (P2 remains the gate for author-supplied slots).
