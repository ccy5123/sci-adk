# Acceptance Criteria — SPEC-PAPER-GATE-001

All scenarios are deterministic and third-party re-runnable from the shipped record alone. No
scenario relies on a language model or a human judgment as the verdict. "PASS"/"FAIL" below
mean the deterministic gate's verdict, not a manual review.

---

## Must-Pass Scenarios (derived from the real failure)

These five are the mandated acceptance gates. Each maps to a requirement group and must be
encoded as a test.

### MP-1 — A number absent from the record FAILS verify (P2)

- **Given** a conclusion-bearing merged manuscript whose `main.tex` contains a quantitative
  token (e.g. a ratio or a baseline value) that does NOT map to any value in the
  recorded-value pool,
- **When** `sci-adk verify <workspace>` runs,
- **Then** the number-audit FAILS, exits non-zero, and names the unbacked token and its
  location (REQ-PG-201/202/204).
- **And** the same audit PASSES for an otherwise-identical manuscript in which every
  quantitative token maps to a recorded value (no false positive on backed numbers).

### MP-2 — Sections out of declared/IMRaD order FAIL (or warn per declared venue) (P4)

- **Given** a conclusion-bearing manuscript whose sections appear out of the declared order
  (e.g. Methods placed after Discussion) and/or omit Conclusion,
- **When** `sci-adk verify` runs,
- **Then** the section checker FAILS against the declared/default IMRaD order
  (Introduction→Methods→Results→Discussion→Conclusion), names the out-of-order/missing
  sections (REQ-PG-401/402/403),
- **And** WHERE a venue declares a non-IMRaD order, the checker enforces THAT order (FAIL on
  deviation from the declared order; WARN only when no order is declared) per OD-6.

### MP-3 — A non-conforming cite key FAILS (P3)

- **Given** a manuscript that cites a key not matching `<Surname><Year>(+a/b)` (e.g. a
  lower-cased `<surname><digits>` or a bare initials token),
- **When** `sci-adk verify` runs (per-run AND package),
- **Then** the citation-key checker FAILS and names the offending key (REQ-PG-301/302).
- **And** a mis-disambiguated duplicate group (a bare base key plus a `…b` with no `…a`) also
  FAILS and names the group (REQ-PG-303).
- **And** an unpublished/DOI-less load-bearing citation produces a WARNING naming the entry
  (REQ-PG-304, per OD-5).

### MP-4 — A conclusion-bearing paper/package with no frozen contract triggers a loud refusal/warning (P1)

- **Given** a conclusion-bearing paper draft (≥1 figure or ≥1 `\cite` or ≥1 non-Abstract
  section) OR an assembled `package/`, with NO frozen `pubreqs.json`/`pkgreqs.json`,
- **When** `sci-adk verify` runs,
- **Then** verify emits a loud REFUSAL/WARNING naming the missing contract and does NOT return
  a silent clean pass for that artifact (REQ-PG-101),
- **And** the message is actionable (states what to freeze and how) rather than a silent
  behavior flip (REQ-PG-108, per OD-8).

### MP-5 — The package gate runs at session close (P1)

- **Given** a workspace containing a `package/` that fails the package gate (e.g. an unbacked
  number per MP-1, an unresolved cite, or a missing frozen contract),
- **When** the session reaches the Stop hook,
- **Then** the Stop hook runs `sci-adk verify <workspace>` in addition to the per-run
  claim-reproduction audit and BLOCKS Stop (exit 2) with the failing reasons (REQ-PG-104),
- **And** a clean workspace package allows Stop to proceed (no false block),
- **And** the existing per-run claim-reproduction block is unchanged (REQ-PG-107).

---

## Additional Acceptance Criteria

### AC-1 — F2 wiring gap closed (P1)

- **Given** a frozen `pkgreqs.json` declaring `figure_font_policy` on and an `image_min_dpi`
  floor, and a figure-bearing package,
- **When** `sci-adk verify <workspace>` runs,
- **Then** the package gate applies the font-policy and raster-DPI checks (the same checks the
  per-run gate applies), FAILING when the font preamble is absent or a raster figure is below
  the DPI floor (REQ-PG-106).

### AC-2 — Conclusion in defaults (P1/P4)

- **Given** an author choosing "use defaults" for required sections,
- **When** the default contract is constructed,
- **Then** the required-section set is Abstract/Introduction/Methods/Results/Discussion/
  Conclusion (REQ-PG-105/403).

### AC-3 — Word limits actually gate (P4)

- **Given** a frozen contract declaring an abstract word limit and a body word range, and a
  manuscript over the abstract limit and/or outside the body range,
- **When** `sci-adk verify` runs,
- **Then** the word-limit checks FAIL and name the violated limit (REQ-PG-404),
- **And** a within-limits manuscript PASSES (no false positive).

### AC-4 — Per-run cite resolution (P3)

- **Given** a per-run paper draft that `\cite`s a key with no defined `.bib` entry,
- **When** `sci-adk verify <run>` runs,
- **Then** the per-run cite-resolution check FAILS naming the dangling key (REQ-PG-305).

### AC-5 — Record-vs-belief invariant preserved (P2)

- **Given** the number-audit running over any manuscript,
- **When** a token is compared,
- **Then** it is compared ONLY against RECORDED values; the gate never accepts a value because
  it "seems right" and a manual spot-check by an author/agent does not substitute for the gate
  (REQ-PG-203).

### AC-6 — Existing gate not weakened (P1)

- **Given** a run whose recorded Claim does NOT reproduce from the record,
- **When** `sci-adk verify <run>` runs,
- **Then** it still FAILS exactly as before this SPEC (the claim-reproduction gate is
  untouched; new gates are additive) (REQ-PG-107).

### AC-7 — Cross-run merge render gates record content, frees prose (P5, M3)

- **Given** a cross-run merge render over multiple runs,
- **When** the merged manuscript is produced,
- **Then** numbers/tables/figures are record-extracted (record-faithful by construction) and
  only prose is agent-authored, with the boundary as resolved in OD-7 (REQ-PG-501/502),
- **And** a record-typed quantity cannot be hand-typed into a record-extracted region without
  the merge path refusing it or the P2 audit FAILING (REQ-PG-503).

---

## Edge Cases

- **EC-1 — Pure null-result note.** A run note that asserts no finding (no figure, no cite, no
  non-Abstract section) is NOT conclusion-bearing and is exempt from the contract requirement
  (per OD-1). Verify must not refuse it.
- **EC-2 — Derived numbers.** A reported ratio/percentage that is a transform of recorded
  values: behavior governed by OD-2's derived-number policy. The test encodes whichever policy
  is confirmed (FAIL-and-require-record-home, or accept-if-both-operands-recorded).
- **EC-3 — Ignored numeric tokens.** Section/figure/table/equation/reference numbers, dates,
  page numbers, and math-mode structural literals are NOT audited (OD-3 ignore-list); a test
  confirms they do not produce false failures.
- **EC-4 — Pre-existing run migration.** A run created before this SPEC with no frozen contract
  produces a WARNING (not a hard block) during the grace period, while a new artifact produces
  a REFUSAL (OD-8). A test confirms both posture branches.
- **EC-5 — Uncited defined .bib entry.** A defined-but-uncited entry remains benign for
  cite-resolution (existing behavior) but its key shape is still validated by P3.
- **EC-6 — Abstract as environment vs section.** The section/order checker accepts
  `\begin{abstract}` OR `\section{Abstract}` (existing special-case) and orders the abstract
  first.

---

## Quality Gate Criteria

- All deterministic checkers are PURE (no network, no LLM); IO confined to reading the shipped
  record + manuscript.
- New checkers ship with unit tests; Docker-dependent end-to-end `verify <workspace>` tests
  marked `integration`.
- The existing ~1281-test suite stays green.
- No general surface (requirement, checker, default, message, test fixture name) names or
  assumes a domain, venue, or study.
- `ruff` / `black` clean; type hints on all new function signatures.

---

## Definition of Done

- [ ] All resolved Open Decisions (OD-1..OD-8) recorded in
      `design/paper-writing-enforcement.md` with the three leaks' file:line evidence and
      migration notes.
- [ ] M1 (P1+P2): MP-1, MP-4, MP-5, AC-1, AC-2, AC-5, AC-6 pass.
- [ ] M2 (P3+P4): MP-2, MP-3, AC-3, AC-4 pass.
- [ ] M3 (P5): AC-7 passes.
- [ ] All edge-case tests (EC-1..EC-6) pass.
- [ ] Existing claim-reproduction / record-green gate verified unchanged (AC-6).
- [ ] Existing ~1281-test suite green; new gates covered; Docker tests marked `integration`.
- [ ] Domain-neutrality audit: no domain/venue/study leak in any general surface.
- [ ] `/sci publish` and `/sci package` require a frozen contract as a completion step;
      the Stop hook runs `verify <workspace>`.
