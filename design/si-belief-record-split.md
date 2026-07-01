# Authoring-Flow SI — "main and SI are both authored; the record is the deposit"

> Status: BUILT (2026-07-01) as SPEC-SI-AUTHORING-001 — per-run path (M1-M4) + package path
> (M5), on branch `feat/authoring-flow-si` (not yet merged to master). Design AGREED, all open
> points closed. See `.moai/specs/SPEC-SI-AUTHORING-001/`.
>
> The Supporting Information is AUTHORED (agent-written, fidelity-gated) as the natural
> overflow of the main paper — not machine-generated as a record dump. The auditable
> RECORD is the data/code deposit (`runs/` + `sci-adk verify`), which already exists; one
> deterministic record artifact is retained inside the deposit. `main.tex` ↔ `si.tex`
> linkage stays plain-text S-refs guarded by the existing cross-doc gate (zref-xr was
> considered and dropped — §6).
>
> Lineage: extends and REVISES render-architecture-reframe.md. Supersedes this file's
> v0.1 (deterministic-dump-SI as a paper sibling) and v0.2 (which proposed zref-xr).

## 1. Problem

After the render-reframe ([render-architecture-reframe.md]), `main.tex` is an agent-authored
belief narrative, but `si.tex` was left as a deterministic record DUMP organized by record
TYPE, with plain-text cross-references ([src/sci_adk/render/si.py:151](../src/sci_adk/render/si.py)).
Two failures, commonly conflated:

- **(a) Comprehensibility.** A type-sorted dump (all Evidence → table → all Claims → all
  Figures) is machine-natural but reader-hostile; a reader must reassemble a claim's support
  from four sections.
- **(b) Connective tissue.** After the reframe `main.tex` emits no evidence bullets, and the
  SI is a separate type-sorted dump with no authorial through-line between the `\evval`
  numbers in the paper and their backing.

## 2. The decisive lens — how a real researcher makes main + SI

The answer is in actual scientific authoring practice, not in our architecture:

1. **One author, one voice, writes main AND SI together.** Writing the body, the author hits
   "too much detail," pushes it to the SI, and writes `(see Fig. S3, Section S2)` inline as
   they go. **The SI is the overflow of the main narrative** — same hand, cross-references
   authored at the moment of writing.
2. **The SI is authored BELIEF, not a record log.** Real SIs carry captioned figures and
   tables, derivations, extended discussion. Not append-only logs.
3. **The raw RECORD is a separate artifact TYPE — the data/code deposit.** Zenodo/Dryad/
   GitHub: the actual files + a "Data availability" statement + a DOI. *That* is the
   monotone, archival, machine-facing record.

Real science is already three layers, distinguished **by artifact type, not prose density**:
main paper (authored belief) · SI PDF (authored belief, overflow) · data deposit (record).

## 3. The correction — we mislocated the record/belief boundary

v0.1–v0.2 made **SI = the record** (a deterministic dump) and reasoned about keeping prose
out of it. That placed the auditable record INSIDE the SI slot. Real practice keeps the line
by artifact TYPE — a PDF supplement (belief) vs a data repository (record) — so an authored
SI does NOT blur the boundary, because the auditable record was never the SI. In sci-adk the
record is already the deposit: **`runs/` + `sci-adk verify`.**

Consequences: (1) the SI returns to being authored belief, the natural extension of
`main.tex`; (2) the deterministic dump was never an SI — it is retained, relocated into the
deposit as the record artifact (§5); (3) nothing auditable is lost — a reviewer RUNS
`sci-adk verify` over `runs/` (re-derivable), they do not read an 80-page dump.

## 4. sci-adk's edge, in its right place

Ordinary SIs can drift from the data (hand-copied tables, stale values). sci-adk's authored
SI keeps the human-natural form **while binding every measured value to the deposit** via the
fidelity gate (`\evval`/`\status` substitution, FAIL-LOUD,
[src/sci_adk/render/factref.py](../src/sci_adk/render/factref.py)):

> **A human-natural SI with machine-grade numerical fidelity** — the narrative is the
> agent's; every number it states is the record's.

The gate spans BOTH belief documents (①, ②). It guarantees the cited NUMBERS, not the
interpretation and not completeness (an author can still omit a row or mis-frame) — the same,
unchanged exposure the main paper already carries.

## 5. Decision — the three artifacts, correctly typed

```
BELIEF FLOOR  (authored · fidelity-gated · plain-text S-ref linkage + existing cross-doc gate)
  (1) main.tex      headline belief narrative        render_paper_latex (unchanged)
  (2) si.tex        extended belief: authored overflow of main, FREE structure (§8.1),
                    figures + hand-authored tables + extended discussion, every value
                    \evval-gated, plain-text "Figure S<n>" refs to/from (1).
                                                      ★ NEW authoring path (reuses paper.py
                                                        machinery, NOT the si.py dump)
RECORD FLOOR  (machine/archival · already exists · bears sci-adk verify)
  (3) deposit       runs/ + sci-adk verify + a "Data & code availability" statement
                    + ONE retained deterministic record artifact (record.tex/.pdf =
                    today's render_si_latex output, RELOCATED into the deposit and
                    re-named from "SI" to "record", code reused verbatim).
```

What dies: the ROLE "si.tex = deterministic dump / paper sibling." What lives: the dump
RENDERER (`render_si_latex`) — demoted to producing the deposit's retained record artifact (3),
determinism and `sci-adk verify` unchanged.

### Artifact contracts

| | spine (engine) | authored (agent) | audited by |
|---|---|---|---|
| **(1) main.tex** | figures (y from record), bib, `\evval`/`\status` subst | title · IMRaD prose · plain-text S-refs to (2) | fidelity gate + cross-doc S-ref gate |
| **(2) si.tex** | figures (y from record), bib, `\evval`/`\status` subst | free-structured prose · hand-authored tables · plain-text S-refs to (1) | fidelity gate + cross-doc S-ref gate |
| **(3) deposit** | `runs/` JSON, `sci-adk verify`, retained deterministic record artifact | "Data & code availability" statement | `sci-adk verify` |

## 6. Confirmed decisions (2026-07-01)

- **SI is authored, not generated** (reverses v0.1). ② is written by the in-session agent as
  the overflow of ①, gated by `\evval`/`\status`.
- **The record is the deposit.** ③ = `runs/` + `sci-adk verify` + availability statement.
- **Keep ONE deterministic record artifact inside the deposit.** Reuse today's
  `render_si_latex` output as `record.tex`/`.pdf` in the deposit (not a paper sibling); no new
  renderer.
- **Linkage = plain-text S-refs + the existing cross-doc gate; `zref-xr` DROPPED.** Measured
  rationale: authoring ② already supplies the through-line, and
  `check_cross_doc_s_refs` already prevents dangling "Figure S<n>" with NO compile coupling
  ([src/sci_adk/render/consistency.py:22-31](../src/sci_adk/render/consistency.py)). `zref-xr`
  would only add clickable navigation, at the cost of reintroducing the cross-document compile
  coupling the current design deliberately avoids for Overleaf folder-upload UX. Not worth it.
- **8.1 ② organization = FREE authored structure, no fixed axis.** The renderer may offer a
  conventional default skeleton (Supplementary Methods / Notes / Figures / Tables); the agent
  reorganizes freely per the overflow. Linkage is carried by cross-refs, not by a forced
  claim axis. ("Claim-anchored restructure" framing is retired.)
- **8.2 ② tables = hand-authored by the agent** (`\evval` per cell). The dump's table logic is
  NOT reused for ② (it lives only in ③). Fidelity of cited cells is gated; row completeness is
  the author's responsibility (per §4).
- **8.3 figure ownership.** Each figure lives in exactly one of ① / ② (Figure N XOR S*); ③'s
  record artifact carries all exhaustively (R*). One shared `figures/` file set; labels differ.
- **8.4 gate surface (MEASURED — the existing gate already audits `si.tex` as a manuscript).**
  `verify.py` already scans BOTH documents: `_PAPER_DOCS = (draft.tex, si.tex)`
  ([verify.py:114](../src/sci_adk/loop/verify.py)); **P2 number-audit runs over draft.tex + si.tex**
  ([verify.py:908,1145](../src/sci_adk/loop/verify.py)), as do tool-vocabulary
  ([verify.py:1196](../src/sci_adk/loop/verify.py)), value-fidelity, ref-consistency, novelty,
  and cross-doc S-ref. So:
  - **②'s gate is UNCHANGED — authoring ② opens NO verification hole.** When `si.tex` was a
    dump, P2 passed trivially (dump = record); now ② is authored, P2 does REAL work auditing the
    authored numbers against the record pool, and that wiring already exists
    ([number_audit.py:7-10](../src/sci_adk/render/number_audit.py) closes "fidelity is opt-in per
    number"). Hand-authored ② tables (8.2) are likewise number-audited cell by cell; row
    completeness stays the author's responsibility.
  - **③ `record.tex` = tool-vocabulary EXEMPT.** The dump relocates to ③; as the record /
    provenance it legitimately names `capability:…`, `docker:…`, `environment:…` (cf. T-1
    evidence provenance). The tool-agnostic gate stays on ① and ② (the submission); the
    "the dump is exempt" intent moves to the correct artifact now that ② is genuine belief.
    ③ is by-construction clean on number-audit (it IS the record).
  - **Deposit-completeness check = IN this SPEC**: ③ record artifact present + a "Data & code
    availability" statement present (precedent: `readme_submission_readiness_problems`);
    `sci-adk verify` green already exists. So the new gate work is small and all on the record
    side, not the belief side.

## 7. Authoring flow (`/sci publish`, the new shape)

1. The agent writes ① and, on body-overflow detail, pushes it to ② and writes the inline
   `(Figure S<n>)` — one voice, co-authored, refs as written.
2. ② receives the overflow as freely-structured sections (captioned figures, hand-authored
   tables, extended discussion); every measured value is `\evval`-bound to the deposit.
3. The fidelity gate + the cross-doc S-ref gate run over ① and ②. ③ is `runs/` + `verify` +
   the availability statement + the retained record artifact.
4. The through-line is authorial (one agent writing both) — the missing through-line is
   exactly why the old dump-SI read as disconnected; no `zref-xr` needed to fix it.

## 8. Resolved questions

All §8 points are now closed (see §6 for 8.1–8.4). Recap of the two that needed measurement:

- **8.4 gate surface** — RESOLVED (§6): the existing gate already audits `si.tex` as a
  manuscript, so ②'s gate is unchanged and no hole is opened; ③ `record.tex` is tool-vocab
  exempt; deposit-completeness is in this SPEC. The new work is small and record-side only.
- **8.5 thin records** — self-resolves: a 1-hypothesis run gets a short authored SI (or none),
  as a small real study has a short supplement. No special degenerate case needed.

## 9. Scope and non-goals

- **In scope:** the domain-journal / `package` submission path (e.g. the IEAM-P8-style
  near-submission package).
- **Out of scope:** the JOSS *tool paper* (`paper/paper.md`) — short, SI not central; untouched.
- **Non-goals:** changing what `sci-adk verify` computes (it audits `runs/` + the retained
  record artifact); any LLM in the verdict or record path; the gate guaranteeing interpretation
  or completeness (it guarantees cited numbers only).

---

Version: 0.4.0 (design, SPEC-ready) — supersedes v0.1, v0.2, v0.3
History:
- v0.1 (2026-07-01): split SI into readable narrative + deterministic record PDF, both as
  paper siblings. Superseded same day.
- v0.2 (2026-07-01): "real researcher" lens corrected the record/belief boundary — SI is
  authored belief, record is the deposit; proposed `zref-xr` linkage.
- v0.3 (2026-07-01): confirmed open points 8.1/8.2/8.3 + dropped `zref-xr` (measured: the
  existing cross-doc S-ref gate already prevents dangling without compile coupling; authoring
  supplies the through-line). 8.4 (gate-surface extent) left open.
- v0.4 (2026-07-01): 8.4 resolved by measurement — the existing gate already audits `si.tex`
  as a manuscript (P2 number-audit over draft.tex+si.tex), so ②'s gate is unchanged and opens
  no hole; ③ record.tex is tool-vocab exempt; deposit-completeness is in this SPEC. All open
  points closed; SPEC-ready.
Source: 2026-07-01 session — SI readability + main↔SI linkage pivot
Extends / revises: design/render-architecture-reframe.md
Related: design/paper-figures-and-si.md, design/paper-publishing-requirements.md,
design/paper-writing-enforcement.md
