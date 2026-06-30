# Authoring-Flow SI — "main and SI are both authored; the record is the deposit"

> Status: AGREED (2026-07-01), design — NOT yet built.
>
> The Supporting Information is AUTHORED (agent-written, fidelity-gated) as the natural
> overflow of the main paper — not machine-generated as a record dump. The auditable
> RECORD is the data/code deposit (`runs/` + `sci-adk verify`), which already exists; one
> deterministic record artifact is retained inside the deposit. `main.tex` and `si.tex`
> are linked by real bidirectional `\ref` via `zref-xr`.
>
> Lineage: extends and REVISES render-architecture-reframe.md. Supersedes this file's own
> v0.1 (the "deterministic-dump SI as a paper sibling" model) — see §3 for the correction.

## 1. Problem

After the render-reframe ([render-architecture-reframe.md]), `main.tex` is an agent-authored
belief narrative, but `si.tex` was left as a deterministic record DUMP organized by record
TYPE, with plain-text cross-references ([src/sci_adk/render/si.py:151](../src/sci_adk/render/si.py)).
Two failures, commonly conflated:

- **(a) Comprehensibility.** A type-sorted dump (all Evidence → table → all Claims → all
  Figures) is machine-natural but reader-hostile; a reader must reassemble a claim's support
  from four sections.
- **(b) Connective tissue.** Main↔SI references are plain text, not real `\ref`, and after the
  reframe `main.tex` emits no evidence bullets — so a reader sees `\evval` numbers with their
  backing in a separate, type-sorted document and no authorial through-line between them.

## 2. The decisive lens — how a real researcher makes main + SI

The answer is in actual scientific authoring practice, not in our architecture:

1. **One author, one voice, writes main AND SI together.** Writing the main text, the author
   hits "too much detail for the body," pushes it to the SI, and writes `(see Fig. S3,
   Section S2)` inline as they go. **The SI is the overflow of the main narrative** — same
   author, same voice, cross-references authored at the moment of writing.
2. **The SI is authored BELIEF, not a record log.** Real SIs carry captioned figures and
   tables, derivations, "we chose X because Y," extended discussion. They are not append-only
   logs.
3. **The raw RECORD is a separate artifact TYPE — the data/code deposit.** Zenodo/Dryad/
   figshare/GitHub: the actual CSVs, code, raw measurements, plus a "Data availability"
   statement and a DOI. *That* is the monotone, archival, machine-facing record.

So real science is already three layers, and the layers are distinguished **by artifact
type, not by prose density**:

| real science | nature |
|---|---|
| main paper | authored belief (headline) |
| **SI (PDF)** | **authored belief (extended)** — overflow of the main paper, same hand |
| data/code deposit | the record (the actual deposit, machine/archival) |

## 3. The correction — we mislocated the record/belief boundary

v0.1 of this file (and the prior turn's reasoning) made **SI = the record** (a deterministic
dump) and argued *against* putting prose in it "to keep record/belief clean." That was wrong:
it placed the auditable record INSIDE the SI slot. Real practice keeps the line by artifact
TYPE — a PDF supplement (belief) vs a data repository (record) — so an authored SI does NOT
blur the boundary, because the auditable record was never the SI. In sci-adk the record is
already the deposit: **`runs/` + `sci-adk verify`.**

Consequences:

1. **The SI returns to being authored belief** — the natural extension of `main.tex`,
   written in one voice with cross-references emitted as written. This is what an SI *is*.
2. **The deterministic dump was never an SI.** It was the record rendered as a PDF in the
   wrong slot. It is retained — relocated into the deposit as the record artifact (§5) — not
   shown to a reader as "the SI."
3. **Nothing auditable is lost.** A reviewer does not read an 80-page dump; they RUN
   `sci-adk verify` over `runs/`, which is stronger than a printable dump (re-derivable, not
   merely inspectable).

## 4. sci-adk's edge, finally in its right place

Ordinary SIs can drift from the data (hand-copied tables, stale values). sci-adk's authored
SI keeps the human-natural form **while binding every measured value to the deposit** via the
fidelity gate (`\evval`/`\status` substitution, FAIL-LOUD,
[src/sci_adk/render/factref.py](../src/sci_adk/render/factref.py)):

> **A human-natural SI with machine-grade numerical fidelity** — the narrative is the
> agent's; every number it states is the record's. The dump-as-SI hid this; authoring the SI
> reveals it.

The gate now spans BOTH belief documents (①, ②). It guarantees the NUMBERS, not the
interpretation — the same, unchanged exposure the main paper already carries.

## 5. Decision — the three artifacts, correctly typed

```
BELIEF FLOOR  (authored · fidelity-gated · real bidirectional \ref via zref-xr)
  (1) main.tex      headline belief narrative        render_paper_latex (unchanged)
  (2) si.tex        extended belief: authored overflow of main, claim/topic-organized,
                    figures + tables + extended discussion, every value \evval-gated,
                    zref-xr to (1).                  ★ NEW authoring path (closer to
                                                       paper.py than to today's si.py)
RECORD FLOOR  (machine/archival · already exists · bears sci-adk verify)
  (3) deposit       runs/ + sci-adk verify + a "Data & code availability" statement
                    + ONE retained deterministic record artifact (record.tex/.pdf =
                    today's render_si_latex output, RELOCATED into the deposit and
                    re-named from "SI" to "record", code reused verbatim).
```

What dies: the ROLE "si.tex = deterministic dump / paper sibling." What lives: the dump
RENDERER (`render_si_latex`) — demoted to producing the deposit's retained record artifact
(3), determinism and `sci-adk verify` unchanged.

### Artifact contracts

| | spine (engine) | authored (agent) | audited by |
|---|---|---|---|
| **(1) main.tex** | figures (y from record), bib, `\evval`/`\status` subst | title · IMRaD prose · cross-refs to (2) | fidelity gate |
| **(2) si.tex** | figures, bib, `\evval`/`\status` subst, `zref-xr` to (1) | extended prose · tables · per-claim/topic sections · cross-refs to (1) | fidelity gate |
| **(3) deposit** | `runs/` JSON, `sci-adk verify`, retained deterministic record artifact (record.tex/pdf) | "Data & code availability" statement | `sci-adk verify` |

## 6. Confirmed decisions

- **SI is authored, not generated.** ② is written by the in-session agent as the overflow of
  ①, in one voice, gated by `\evval`/`\status`. (Reverses v0.1.)
- **The record is the deposit.** ③ = `runs/` + `sci-adk verify` + availability statement.
- **Keep ONE deterministic record artifact inside the deposit** (user decision, 2026-07-01):
  reuse today's `render_si_latex` output as `record.tex`/`.pdf`, placed in the deposit (not as
  a paper sibling), so the deposit is self-describing and archivally citable. No new renderer.
- **Linkage: two files + `zref-xr`** (matches venue/JOSS conventions and the package
  `make_si.py` split-file model,
  [.../package/04_scripts/make_si.py](../src/sci_adk/templates/research-workspace/package/04_scripts/make_si.py)).
  The cyclic main↔SI references use `zref-xr`'s multi-pass protocol; the package build owns
  the compile rounds.

## 7. Authoring flow (`/sci publish`, the new shape)

Mirrors the human flow:

1. The agent writes ① and, on hitting body-overflow detail, pushes it to ② and emits a
   `\ref{si:...}` inline — one voice, co-authored, cross-refs as written.
2. ② receives the overflow as per-claim/topic sections (captioned figures, full tables,
   extended discussion); every measured value is `\evval`-bound to the deposit.
3. The fidelity gate runs over ① and ②. ③ is `runs/` + `verify` + the availability statement
   + the retained record artifact.
4. `zref-xr` supplies the cross-doc `\ref` MECHANISM; the through-line is authorial (one agent
   writing both) — the missing through-line is exactly why the dump-SI read as disconnected.

## 8. Open questions (smaller now)

- **8.1 Organization axis of ②** — per-claim (mirror main's hypothesis axis) vs per-topic
  (methods-extended / data-extended, as many real SIs do). Recommended: per-claim primary,
  with a methods-extended section permitted; both are authored, so this is an authoring
  convention, not a renderer constraint.
- **8.2 Author vs scaffold** — how much of ② the renderer scaffolds (section skeleton,
  figure floats, gate, zref-xr wiring) vs the agent authors (all prose, table captions,
  ordering). Recommended: renderer scaffolds the same way `paper.py` does for ①; agent
  authors the rest. (Reuse `paper.py` machinery; the old `si.py` is not the basis for ②.)
- **8.3 Figure ownership** — ① headline (`Figure N`), ② extended (`Figure S*`), ③ record
  artifact carries all (exhaustive). One shared `figures/` file set; labels differ.
- **8.4 pkgreqs / verify anchor** — the deterministic-record anchor of
  `package_requirements_clean` moves to ③'s retained record artifact + `runs/`
  ([render/pkgreqs_checks.py](../src/sci_adk/render/pkgreqs_checks.py),
  [core/pkgreqs.py](../src/sci_adk/core/pkgreqs.py)); the fidelity gate extends to ②.
- **8.5 Thin records** — now self-resolving: a 1-hypothesis run simply gets a short authored
  SI (or none), exactly as a small real study has a short supplement. No special degenerate
  case is needed once the SI is authored rather than a fixed dump.

## 9. Scope and non-goals

- **In scope:** the domain-journal / `package` submission path (full manuscripts, e.g. the
  IEAM-P8-style near-submission package).
- **Out of scope:** the JOSS *tool paper* (`paper/paper.md`) — short, SI not central;
  untouched.
- **Non-goals:** changing what `sci-adk verify` computes (it audits `runs/` + the retained
  record artifact, as today); any LLM in the verdict or record path; the gate guaranteeing
  interpretation (it guarantees numbers only — an explicit honesty boundary).

---

Version: 0.2.0 (design, pre-build) — supersedes v0.1 (deterministic-dump-SI model)
History:
- v0.1 (2026-07-01): split SI into readable narrative + deterministic record PDF, both as
  paper siblings. Superseded same day.
- v0.2 (2026-07-01): the "how a real researcher makes main + SI" lens corrected the
  record/belief boundary — the SI is authored belief, the record is the deposit. SI becomes
  authored (not dumped); the dump renderer is retained as the deposit's record artifact.
Source: 2026-07-01 session — SI readability + main↔SI linkage pivot
Extends / revises: design/render-architecture-reframe.md
Related: design/paper-figures-and-si.md, design/paper-publishing-requirements.md,
design/paper-writing-enforcement.md
