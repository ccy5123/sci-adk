# Field-report triage — external run of sci-adk on a real research program

Source: an in-session agent used sci-adk (v0.2.0) as a *user* to run a full research
program (chemical-space smoothness, "hard problem A-1") across the empirical/threshold,
formal/proof, mixed, and prior-work paths (~9 runs). The report is external field
validation — the first independent use surfacing structured defects.

Severity is ranked by **whether the defect violates sci-adk's own philosophy** (the system
punishing the honesty/record it demands) over pure ergonomics. Every claim below was
verified against source at the cited `path:line`.

## Triage table

| ID | Sev | One line | Kind | Status |
|----|-----|----------|------|--------|
| P3 | HIGH | Recording prior work post-hoc breaks `verify` for every run | Philosophy violation (honesty penalty) | **Fixed this session** |
| P2 | HIGH | Resolved run renders a stale "Pending" section that trips its own gates | Philosophy violation (self-inflicted) | **Fixed this session** |
| P1 | HIGH | `DecisionRule(kind=PROOF)` can never reach SUPPORTED; QUALITATIVE can | Design inconsistency | Open — needs a decision |
| P4 | MED | Number-audit rejects ordinal/label numerals (`Theorem 5`, `A-1`) | Gate over-fires on theory papers | Open |
| P5 | MED | `pubreqs freeze --defaults` requires a `Conclusion` slot `PaperProse` lacks | Config/slot mismatch | Open |
| P6 | MED | No out-of-tree capability registration; library-driven pattern undocumented | Extensibility + docs | Open |
| P7 | LOW | Shipped executor pins `sci-adk-python-base` (no RDKit); chem needs a custom image | Packaging + docs | Open |

Papercuts worth an issue: opaque `verify` failure diagnosis (which `passed` sub-gate
failed), no `verdicts=` convenience on `compile()`, `compile()` re-runs the experiment on
the resolve pass.

## Fixed this session

### P3 — reproduction-bundle gate no longer requires process-decision refs
`prior-work --searched` appends a `PRIOR_WORK_DECISION` item whose
`code_ref="prior_work:searched"` (`loop/prior_work.py:221`) — a process **decision
pointer**, not generating code, with `bears_on=[]`. The F3 gate
(`loop/verify.py::_reproduction_bundle_problems`) required every recorded `code_ref` to
appear in the already-rendered `reproduce.py`, so honestly recording prior art flipped
every previously-passing run to `verify` exit 1.

Fix: exclude the process/decision meta-record kinds
(`PRIOR_WORK_DECISION`, `NOVELTY_DECISION`, `CONTESTED_RECORD`) from the reproduction-bundle
requirement. Reproduction is about the generating code only.
Test: `tests/test_verify.py::test_verify_reproduction_bundle_ignores_prior_work_decision_ref`.

### P2 — resolved hypotheses no longer render a "Pending agent judgments" section
`loop/compiler.py::_collect_checkpoints` flags every proof/qualitative hypothesis
unconditionally, and `stage_render` fed all of them to the renderer's `pending` list
regardless of Claim status. A fully-resolved run kept a "Pending agent judgments" section
whose boilerplate ("verdict") tripped the §10 tool-vocabulary gate and whose dumped finding
digits tripped the number-audit — the run failing `verify` on its own auto-generated
scaffolding.

Fix: in `stage_render`, drop from `pending` any hypothesis whose Claim `is_supported()` or
`is_refuted()` (matched by `Claim.answers == Checkpoint.hypothesis_id`). The judge-checkpoint
files on disk are untouched; only the rendered belief paper changes.
Test: `tests/test_compiler.py::test_stage_render_pending_section_gated_on_claim_resolution`.

Full suite after both fixes: 1521 passed, 1 skipped.

---

## Open issues — copy-paste drafts

### Issue: PROOF rules are refute-only for automation, but QUALITATIVE is not — pick one, loudly (P1)

**What happens.** `loop/decision_engine.py::_eval_proof` returns `inconclusive` even for a
STRONG, trailed judge "verified" ("a human spot-check is required before 'supported'
(override D8)", `decision_engine.py:515-519`); only a counterexample is decisive
(`:470-476`). So a `kind=PROOF` hypothesis can never be SUPPORTED, and `verify` then
re-derives `inconclusive` → UNRESOLVED → the gate fails, with no way to pass.

**The real defect is the asymmetry.** `_eval_qualitative` (`decision_engine.py:552-556`)
*does* bind SUPPORTS/REFUTES from a confident trailed judge, with **no** §0 human-spot-check
override. So the two non-numeric paths use different trust models, and the path whose name
is most correct (PROOF) is the punished one. Users route around it by modeling proofs as
QUALITATIVE — exploiting exactly this gap.

**Design question (needs a decision).** Either PROOF's human-in-loop strictness is right and
QUALITATIVE is too loose, or QUALITATIVE's recorded-attestation trust is right and PROOF is
over-strict. The record/belief framing supports the strict view (a counterexample is a
monotone *record* fact; "this proof is valid" is a revisable *belief* needing judgment) —
but then QUALITATIVE undercuts it.

**Whichever way it resolves, it must be loud.** Today the CLI `run`/`--help` and docs say
nothing; a proof author only discovers PROOF is refute-only by reading the engine source.

---

### Issue: number-audit over-fires on theory papers (ordinals, labels, identifiers) (P4)

The publishing number-audit rejects any standalone numeral in `draft.tex` not in the
recorded-value pool, flagging non-claim numerals: `Theorem 5`, `Section 3`, `Figure 2`,
`A-1`. A theory paper cannot name its own theorems by number. (Digits inside a token —
`ECFP4`, `mol2vec` — are correctly ignored, but that is under-documented.)

The gate conflates "number as claim" (anti-fabrication target) with "number as label"
(structural). Proposed: an author-declared numeric allowlist in `pubreqs`, and/or skip
numerals inside recognized label patterns (`Theorem N`, `Section N`, `Figure N`, and
identifiers like `A-1`). Relates to SPEC-PAPER-GATE-001 P2.

---

### Issue: `pubreqs freeze --defaults` requires a `Conclusion` section `PaperProse` cannot emit (P5)

`--defaults` sets required sections to Abstract/Introduction/Methods/Results/Discussion/
**Conclusion**, but `render/prose.py::PaperProse` has slots only through `discussion` — no
`conclusion`. A `--defaults` + PaperProse-authored paper always fails
`missing required section: Conclusion`.

Fix: add a `conclusion` slot to `PaperProse`, or align the default required-section set with
the PaperProse slots. (Workaround: `freeze` with an explicit `--required-section` list.)

---

### Issue: no out-of-tree capability registration; document the library-driven pattern (P6)

`adapter/registry.py` exposes a clean `register`/`resolve`/`available` + `CapabilityProvider`
seam, but the registry is populated only by import-time `register(...)` calls (T-1 hardcoded,
`registry.py:108-145`). There is no entry-point / plugin discovery / `--capability-module`,
so a new capability requires either editing the kernel repo or driving the kernel as a
library (`ResearchCompiler(ws).compile("", spec=..., experiment=...)`) — which works well
and keeps upstream pristine, but is undocumented.

Ask: (a) support a plugin entry-point or `run --capability-module path.py`; (b) document the
library-driven authoring pattern as a first-class way to add a capability without touching
the kernel.

---

### Issue: ship a chem environment recipe / document custom-image capabilities (P7)

The shipped T-1 executor pins `sci-adk-python-base`, whose image comments RDKit out, so any
real chemistry capability must build its own image and thread it through a custom executor.
Ask: document "point a capability at a custom image", and consider shipping an optional
`sci-adk-chem` image or an `environments/` recipe with RDKit enabled.

---

### Issue: `verify` should always print which `passed` sub-gate failed (papercut)

`VerifyReport.passed` is an AND of several gates, but the CLI prints a gate's detail only
when that gate's section fires. A run hit `passed=False` with no obviously-failing line (the
cause was `paper_requirements_clean` = conclusion-bearing paper but no `pubreqs.json`) and
had to be diagnosed by introspecting the `VerifyReport` booleans in Python. Print the failing
sub-gate name unconditionally.
