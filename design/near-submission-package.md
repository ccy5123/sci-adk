# Near-Submission Package — making the package spec mandatory for any sci-adk paper

> Status: **BUILT (2026-06-25)** — AGREED with the user (PF-1..7 resolved; PF-7 →
> route-to-package + warn), then built in two checkpointed waves, suite green (1280 passed,
> +53 new tests, 0 regressions) and verified end-to-end on real records.
>   - Wave 1 (engine): `core/pkgreqs.py` (`PackageReqs`), `render/package.py` (assembler),
>     `render/pkgreqs_checks.py`, the `package_requirements_clean` HARD gate in
>     `loop/verify.py`, the `package` + `pkgreqs freeze` verbs + `verify <ws>` auto-detect in
>     `cli.py`, and the field-agnostic builders under `templates/research-workspace/package/`.
>   - Wave 2 (orchestration): the `science-workflow-package` skill + `/sci package` command,
>     the `/sci` hub `package` subcommand + PF-7 routing/warn, and the `expert-writer`
>     merged-manuscript instruction (author drop-point `<ws>/package_src/main.tex`).
> Follows the project's AGREED→BUILT discipline (abstractions.md / science-guards.md /
> render-architecture-reframe.md / paper-publishing-requirements.md).
>
> Directive (user, 2026-06-25): *"any research — if it renders a paper through sci-adk —
> MUST follow the package spec."* This promotes the field-agnostic near-submission-package
> procedure (previously an ad-hoc pasted prompt) into a first-class, enforced sci-adk
> capability: a workspace-level **`sci-adk package`** verb + **`/sci package`** skill +
> a **`package_requirements_clean`** HARD gate in `sci-adk verify`.

---

## 0. Where this sits (and what it must not break)

This is a WORKSPACE-level publishing layer that sits ABOVE the per-run render contract
(render-architecture-reframe.md) and the per-run publishing requirements (F1/F2/F3 in
paper-publishing-requirements.md). It composes with them; it does not replace them.

- **Per-run render / `pubreqs.json` = tenants.** Each `runs/<id>/paper/` and its
  `pubreqs.json` remain the detailed internal record (per-run paper + per-run format
  gate). UNCHANGED.
- **Package = the submission.** A new workspace-level unit: ONE merged manuscript
  (`main.tex` + `si.tex` + figures) plus the standard 6-folder reproduction package built
  from ALL runs. This is "the paper" a venue receives.

It obeys the same HARD constraints the render reframe and F1/F2/F3 fixed:

- [HARD] **No LLM in the verdict path.** Every requirement that GATES the package is a
  deterministic checker folded into `sci-adk verify`. Authorial qualities that cannot be
  checked deterministically (narrative, contribution framing, honest-negative discussion)
  are SURFACED as advisory, never a pass/fail the engine fakes.
- [HARD] **Tool-agnostic paper.** The merged `main.tex` names the science, not the
  toolchain (the §10 / `paper_tool_clean` rule extends to the merged manuscript).
- [HARD] **Record/belief separation.** No new empirical belief: every number in the
  package is a recorded Claim that reproduces under `sci-adk verify`. The package
  INTERPRETS/FRAMES/DISCUSSES those results; it asserts no un-reproduced value.
- [HARD] **Frozen contract.** The package's venue/format conditions are a frozen
  contract (`pkgreqs.json`), like the Spec and `pubreqs.json`; relaxing a gate-bearing
  field needs an explicit amendment receipt (anti-moving-the-goalposts).

---

## 1. The canonical package spec (what "follow the spec" means)

The package procedure is the field-agnostic [0]–[5] contract (formerly the pasted
PACKAGE_BUILD_PROMPT). Canonized here so every workspace inherits it via `init-session`.

- **[0] Derive from the record (hardcode nothing).** Verify every run green; read each
  spec/claims/evidence/novelty/exploratory; derive field, question, contribution,
  prior-work position, narrative, honest negatives, and confirmatory-vs-exploratory — from
  the record alone. Choose a venue (state the assumption if unforced); mirror an existing
  package/seed if present (extend, do not rewrite).
- **[1] Quality.** Standalone Abstract + Introduction (motivation→gap→contribution vs
  prior work) + Methods (fully reproducible; what it proves and what it does not) + Results
  (per logical block; effect size + uncertainty + robustness/domain) + Discussion
  (interpretation, limits, honest negatives, future) + References. Every quantitative
  statement traces to a Claim; confirmatory and exploratory are separated; figures have
  self-contained captions with a data table behind each; null/negative/refuted are
  first-class; citations come from the record's prior-work/novelty decisions (real refs
  only; flag unverified).
- **[2] Layout.** `01_manuscript/` (paper + SI) · `02_data/` (result CSVs) ·
  `03_figures/` (figures + scripts) · `04_scripts/` (deterministic analyses + builders) ·
  `05_inputs/` (inputs or copyright-respecting pointers) · `06_provenance/` (run index:
  spec-id · digest · verdict + verify logs) · `MANIFEST.md` · `README.md`.
- **[3] Discipline.** = the §0 HARD constraints.
- **[4] Done.** Layout met; paper + SI compile-clean (ref/label, figures, braces, cite
  keys resolve); citations wired; every number ↔ Claim; all runs verify-green; MANIFEST
  complete; a "submission-readiness" self-assessment paragraph naming the record-external
  gaps.
- **[5] If stuck.** Do not fabricate; report which Claim is missing. If the result is
  thin, down-scope the venue honestly (brief report / negative-result note), do not inflate.

## 2. The artifact — `pkgreqs.json` (workspace-level, frozen)

A FROZEN package contract at the workspace root `<ws>/pkgreqs.json` (beside `runs/`, NOT
inside the regenerated `package/`, so re-running `package` never clobbers it). A Pydantic
model in `core/`, mirroring `Spec`/`PubReqs` freeze + digest:

```
PackageReqs {
  frozen_at: ISO-8601
  digest: str                       # tamper-evidence
  venue: str | None                 # free-text label (reuses PubReqs.venue semantics)
  required_sections: list[str]      # in main.tex (default IMRaD: Abstract..Discussion)
  reference_style: str | None       # checked wired in main.tex
  abstract_max_words: int | None    # venue abstract limit (e.g. IEAM 300)
  body_word_range: [int,int] | None # advisory range (e.g. 4000–7000); surfaced, not gated
  runs: list[str] | "all"           # which runs the package synthesizes (default all)
  advisory: list[str]               # free-form, surfaced, NOT gated
}
```

`venue`/format reuse the F1 elicitation: `/sci package` asks (AskUserQuestion) for venue +
the format fields, offering a defaults fast-path, then freezes `pkgreqs.json`. Absent
contract → the gate runs the layout/traceability checks but the venue-format checks are
vacuously clean (backward compatible).

## 3. The gate — `package_requirements_clean` (HARD, deterministic)

`sci-adk verify` (run at workspace scope, or a new `sci-adk package verify`) gains a HARD
gate field alongside the per-run paper gates. Deterministic, read-only, no recompile, no
LLM:

| Check | Deterministic test |
|---|---|
| layout | `01_manuscript … 06_provenance` + `MANIFEST.md` + `README.md` present |
| compile integrity | `main.tex` + `si.tex`: `\ref`↔`\label`, figure files present, braces balanced |
| citations wired | every `\cite*` key in `main.tex` resolves in `references.bib` |
| tool-agnostic | `main.tex` + `si.tex` carry no toolchain noun (reuse `paper_tool_clean`) |
| required_sections | each declared section is a real `\section{...}` in `main.tex` |
| abstract_max_words | word count over the abstract ≤ `abstract_max_words` |
| reference_style | declared style wired in `main.tex` (`\bibliographystyle`) |
| traceability | `02_data/claims_all.csv` present; every run's claims represented |
| record green | `06_provenance/run_index.csv` present; every listed run reproduces (the record audit) |
| value fidelity | `\evval`/`\status`-marked numbers re-derive from the record (reuse the reframe gate) |
| self-assessment | `README.md` contains a submission-readiness section |

Surfaced as ADVISORY (never gated): `body_word_range`, free-prose numbers not behind
`\evval`, and the §4 evaluator qualities.

## 4. The procedure — `/sci package` skill + `sci-adk package` verb

`sci-adk package <ws>` (new verb) drives the deterministic spine; `/sci package` (new
skill/command) is the orchestrator that supplies the authorial parts and the elicitation:

1. **Verify** every run green ([0] gate) — stop + report if not.
2. **Elicit + freeze** `pkgreqs.json` (venue + format; orchestrator-only AskUserQuestion;
   defaults fast-path).
3. **Author** the merged manuscript: `Agent(expert-writer)` authors `main.tex` (derive
   narrative/contribution/discussion from the record) TO the §1 spec contract — naming the
   science, separating confirmatory/exploratory, foregrounding negatives. (Authorial =
   contract-driven, not gated.)
4. **Assemble** the 6 folders via record-driven builders shipped in `04_scripts/`
   (`build_record_index.py`, `make_si.py`, `check_package.py` — field-agnostic, derive
   everything from `runs/`).
5. **Advisory review**: `Agent(evaluator-rigor)` advisory pass — contribution stated?
   negatives first-class? confirmatory/exploratory separated? Surfaced, NOT a gate.
6. **Gate**: `sci-adk verify` runs `package_requirements_clean`; the CLI prints failures
   like the other paper gates. Write the submission-readiness self-assessment.

"Render a paper through sci-adk" is realized through `/sci package`; the HARD gate makes
the mechanically-checkable spec items non-bypassable, and the writer/evaluator contracts
carry the authorial ones.

## 5. File touch-list (for the build that follows AGREED)

- `core/` — new `PackageReqs` model + freeze/digest (mirror `PubReqs`).
- `render/package.py` (new) — the assembler: 6-folder layout + MANIFEST/README scaffold
  from the record (reuses the per-run render outputs + the builders).
- `loop/verify.py` — `package_requirements_clean` field + the checks (reuse `consistency`,
  `paper_tool_clean`, the record audit, the value-fidelity gate).
- `cli.py` — `package` verb (assemble + verify) + report printing.
- `04_scripts` builders promoted into `templates/research-workspace/` (the field-agnostic
  `build_record_index.py` / `make_si.py` / `check_package.py`).
- templates: new `science-workflow-package` SKILL + `/sci package` command + `/sci` hub
  routing; `expert-writer` gains the merged-manuscript-to-§1-contract instruction.
- `design/render-architecture-reframe.md` + `design/sci-adk-as-moai.md` — note the
  workspace-level package layer.
- tests across the above (a smoke fixture workspace → `package` → `verify` green).

## 6. Decision-forks

RESOLVED (2026-06-25, user):
- **PF-1 enforcement surface** → a workspace-level `sci-adk package` verb + `/sci package`
  skill + a `package_requirements_clean` HARD gate (NOT extending per-run render; NOT
  gate-only).
- **PF-2 unit** → the submission = the workspace: ONE merged `main.tex` + `si.tex` +
  figures + the 6-folder package. Per-run `paper/` stays as the detailed record.
- **PF-3 authorial enforcement** → HARD-gate the mechanically-checkable; drive the
  authorial parts via the §1 writer/skill contract + an evaluator ADVISORY pass (no LLM in
  the verdict path).

RESOLVED (2026-06-25, defaults accepted):
- **PF-4 contract location/name** → `<ws>/pkgreqs.json` (workspace root, beside `runs/`),
  reusing `PubReqs.venue` semantics.
- **PF-5 gate entry point** → `sci-adk verify <ws>` auto-detects a `package/` +
  `pkgreqs.json` and runs the umbrella gate.
- **PF-6 build sequence** → builders-as-templates → `PackageReqs` + assembler verb →
  `package_requirements_clean` gate → `/sci package` skill + writer/evaluator wiring →
  tests. Each a checkpointed unit + commit.
- **PF-7 mandatory scope** → `/sci publish` (per-run) stays for single-run papers; `/sci
  package` is the mandated route for a workspace submission; `/sci` routes a "render the
  paper" intent to `package` when >1 run exists. Per-run `render` continues to work but
  WARNS ("this is the internal record, not the submission — use `/sci package`") when used
  as a stand-in for a multi-run workspace submission (route-to-package + warn; no HARD
  refuse, so single-run and mid-work flows are unbroken).

---

Version: 0.1.0
Status: PROPOSAL — awaiting AGREED
Source: user directive (2026-06-25) — make the near-submission-package spec mandatory for
any sci-adk paper render. First manual execution: ~/research/ieam-followup-p8/package/.
References: design/paper-publishing-requirements.md, design/render-architecture-reframe.md,
design/paper-figures-and-si.md, design/sci-adk-as-moai.md, design/abstractions.md.
