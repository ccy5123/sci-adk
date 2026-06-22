# Render Architecture Reframe — "Move the Line"

> Status: AGREED + BUILT (2026-06-22). User-approved architecture decision: the render
> layer's deterministic-spine boundary is moved so the paper is an agent-authored belief
> narrative, while a record-fidelity spine + a markup fidelity gate preserve rigor.

## 1. Problem

The render layer produced a paper (`draft.tex`) full of mechanical defects: the
hypothesis statement dumped into `\title`, the same hypothesis text repeated 4–5×,
"confidence 0 (credence)" next to SUPPORTED verdicts, truncated mid-token JSON in the
Evidence list, six identical literature lines, stage-named sections (Goal / Background /
Evidence / Figures) instead of IMRaD, a demo run plotted into the headline figure, and a
compile-breaking `\citep` with no `natbib`.

**Root diagnosis:** these are SYMPTOMS of the deterministic render spine OVER-REACHING into
belief-narrative territory. `render_paper_latex` was trying to assemble a finished *paper*
deterministically — title, section structure, per-hypothesis verdict prose — which a
record-projector cannot do well, so it produced mechanical artifacts.

The architecture already said this work was misplaced: rigor-shell-architecture.md §2.4
puts **"Writing paper prose" OUT of the kernel** (the in-session Claude's job) and keeps
only **"LaTeX/citation emission (deterministic spine)" IN**. The spine had simply crept
past its boundary.

## 2. Decision — move the line (not abolish determinism)

Two different "determinisms" were conflated:

| Determinism | Status | Why |
|---|---|---|
| verdict / measured value / evidence / figure y-value / replay | **settled, non-negotiable** | `sci-adk verify` re-derives belief from the record with NO LLM (adoption-roadmap.md §"no LLM in the verdict path"; "no LLM-as-verdict"). If an LLM produced these, the rigor gate — the whole point of sci-adk — collapses. |
| paper narrative / title / section structure | **moved to the agent** | Already OUT of the kernel per rigor-shell §2.4. The spine was over-reaching. |

So the render contract is reframed:

> **render = a deterministic record-fidelity SPINE + an agent-authored belief NARRATIVE +
> a deterministic markup FIDELITY GATE.**

| | deterministic spine (engine) | belief narrative (agent) |
|---|---|---|
| **draft.tex** | figures (y from the record), bibliography wiring, `\evval`/`\status` substitution | title · abstract · intro · methods · results · discussion · structure |
| **si.tex** | the full record dump (Evidence · numeric table · verdicts · rules · digest) — never moves | (optional) SIProse overview/notes only |
| **verify** | `\ref`↔`\label` gate + `\evval`/`\status` residual scan + verdict re-derivation | — |

The narrative is the agent's; every measured number / verdict it states is still the
record's — see §3.

## 3. Fidelity gate — `\evval` / `\status` markup

The one thing that must NOT move with the narrative is the paper's record-derived FACTS.
An author does not write those as free literals; they write two macros the engine
substitutes FROM THE RECORD at render time (`src/sci_adk/render/factref.py`):

- `\evval{<evidence-id>}{<field>}` → the recorded value. Resolves a Result scalar
  (`point`, `effect_size`, …) first, then a scalar field of the Evidence `finding` JSON
  (so `n_distinct_nonisomorphic_pairs` is citable, not only the typed scalars).
- `\status{<hypothesis-id>}` → the experiment Claim's status (novelty claims excluded).

Substitution is PURE, deterministic, and **FAIL-LOUD**: an unknown id / field / hypothesis,
a non-scalar or non-finite value → `ValueError` (the same record-fidelity spirit as
`figures._y_value`). So **a paper cannot state a measured number or verdict the record does
not hold** — the agent decides WHERE a fact goes; the engine fills WHAT it is.

This is the same design language sci-adk already uses — a deterministic checker over
explicit markup, NOT NLP (the figure `\ref`↔`\label` gate, the `\novelty` markup).

**Honest limit (documented, like consistency.py's comment rule):** the gate guarantees
every fact written VIA a macro is record-faithful; it cannot force an author to use the
macro for every number. A bare literal typed in prose is outside the gate (the same bound
as `\novelty`). Authors write record-derived facts via the macros; `sci-adk verify` flags a
macro that somehow survives into the rendered `.tex` (`paper_factref_clean`).

## 4. What changed (implementation)

- `render/factref.py` (new): `substitute_factrefs` + `find_unresolved_factrefs`.
- `render/prose.py`: `PaperProse` gains `title` / `methods` / `results` slots.
- `render/paper.py`: `render_paper_latex` reshaped to IMRaD — Abstract / Introduction /
  Methods / Results (+ figures as floats) / Discussion, each slot
  `_latex_sanitize_prose(substitute_factrefs(...))`; title = `prose.title` else `spec.id`
  (never the goal wall); `natbib` + `plainnat` + single reference source (no `\nocite{*}`,
  no manual DOI list when a `.bib` is wired); NO stage-dump sections. `_result_summary`
  rewritten to a STRUCTURED, word-boundary-truncated finding summary (no raw JSON dump).
  `_confidence_display` suppresses the uninformative credence/posterior = 0 default.
- `render/si.py`: the record dump gains de-duplication (`(kind, finding, point)` →
  `(recorded Nx)`), a captioned + labelled `table` (S-numbered, referenced within the SI),
  `natbib` + `\bibliography`, the evidence-validity honesty label (moved here from the
  paper), and `\evval`/`\status` substitution in SIProse. Main figures are NO LONGER
  re-rendered in the SI; it carries only supplementary `si_figures`.
- `loop/compiler.py`: `stage_render`/`compile` gain `si_figures` (main figures → paper
  only; `si_figures` → SI). The co-located `references.bib` is wired into BOTH documents.
- `loop/verify.py`: a `paper_factref_clean` field + `_check_paper_factrefs` fold the
  residual-macro scan into the HARD exit gate (`passed = all_reproduced and
  paper_consistent and paper_factref_clean`).

## 4a. Tool-agnostic paper (§10 — tool-vocabulary leakage)

A consequence of the moved line: the paper is the *science*, so it must not name the
*machinery* that produced it. A reader who has never heard of sci-adk must see only
legitimate science (the **tool-agnostic reader test**) — no sentence may require knowing a
sci-adk internal object to make sense.

- The engine emits NO tool self-reference into the paper: the old `\author{sci-adk
  (deterministic render)}` is now agent-supplied (`PaperProse.author`, default empty
  `\author{}`), and the old "Draft compiled by sci-adk from Spec … Belief state is
  revisable as Evidence accrues." provenance note is dropped from the paper (it lives in
  the SI, which is exempt).
- The agent prose translates tool jargon to standard science: "pre-registered … in the
  frozen Spec … engine-derived verdicts" → "we specified the two acceptance thresholds in
  advance, before computing any statistic"; "Both verdicts reproduce under the sci-adk
  verify audit." → a data/code-availability statement; "the append-only Evidence record"
  → "the full data". The scientific CLAIMS (what is supported, scoping, limitations,
  prior art) are unchanged — only vocabulary/voice.
- A deterministic checker enforces it: `check_paper_tool_vocabulary(draft.tex)` flags
  forbidden tool nouns (`sci-adk`, `frozen Spec`, `engine-derived`, `verdict`, `Evidence
  record`, `result.point`, `Spec` as a proper noun, …). It is wired into the verify HARD
  gate as `paper_tool_clean` — a leak in `draft.tex` fails `sci-adk verify`. **The SI
  (`si.tex`) is openly the record dump and is EXEMPT** (never scanned). Honest limit: a
  curated phrase/word list, not NLP — like the `\novelty` / `\ref` gates.

## 5. Defect → resolution map

1.1 agent title / 1.2 hypothesis stated once / 2.1 `_confidence_display` + `\status` /
3.1·3.2 structured finding (no JSON in paper; SI structured) / 3.3 SI dedup / 4 IMRaD /
5 Evidence is SI-only, main figures are paper-Results-only / 6 natbib + bib in both,
single reference source / 7 SI table caption + label (S-numbered) / 8 designed-only
headline figure (authoring) / 9 SIProse wording (authoring) / 10 tool-agnostic paper —
empty `\author`, no provenance note, jargon→science prose, `paper_tool_clean` verify gate
(SI exempt) — see §4a.

## 6. Verification

The full suite is green (paper / si golden tests, `factref` tests, the verify factref
gate). The t1-godel run re-renders cleanly and `sci-adk verify` exits 0 (both claims
REPRODUCED, `\ref`↔`\label` integrity OK for draft.tex + si.tex, no residual fact macros).

## 7. References

- rigor-shell-architecture.md §2.4 (the kernel IN/OUT table — "Writing paper prose" is OUT).
- adoption-roadmap.md (no LLM in the verdict path; LLM-as-verdict cut; `sci-adk verify`
  re-derives with no LLM).
- tool-policy.md Addendum (the render-determinism reframe note).
- design/paper-figures-and-si.md (the figure + SI machinery this reframe builds on).
- src/sci_adk/render/{factref,paper,si,prose}.py · loop/{compiler,verify}.py.
