# Paper Figures and Supporting Information — Design

> Status: v0.2 — decisions D1-D5 resolved; Phases 1-4 IMPLEMENTED (4c deferred). 2026-06-18.
> Purpose: generate the paper's important **figures** (with captions/labels consistent with the body) and its **Supporting Information (SI)**, deterministically and as a self-contained Overleaf folder-upload

## Implementation status

- **Phase 1** (4be6ea7): figure-spec hook + native pgfplots data-plot renderer + stable labels + folder co-location + prose↔figure `\ref` consistency report.
- **Phase 2** (aa9e850): SI auto record-dump renderer (`si.tex`).
- **Phase 3** (249df7b): within-document `\ref`↔`\label` consistency as a `sci-adk verify` HARD gate.
- **Phase 4-1** (69c0133): image-path figure RENDER mechanism — `ImageFigureSpec` (kind-discriminated union; native stays byte-identical) + `render_image_figure` + compiler co-location into `paper/figures/`.
- **Phase 4-2** (5fdf79b): the deterministic image SOURCE (O-A) — an RDKit-in-docker molecule-structure plotter (`adapter/t1_figures.py`, F4-seam capability); byte-identical PNG VERIFIED against the rebuilt `sci-adk-python-base` image.
- **Phase 4-3** (1dadf33): the optional agent `SIProse` hook (mirrors `PaperProse`) around the SI record dump.
- **4c DEFERRED** (cross-document main↔SI `\ref` via `xr`): not built — the Overleaf folder-upload compile-order wrinkle (si.tex must compile first to emit si.aux) outweighs the value. The authoring convention stays: refer to SI figures as plain text ("Figure S1"), not `\ref{fig:SI-...}`.

---

## 1. Problem

The render produces a deterministic `.tex` (`render/paper.py`) + an agent-authored prose hook
(`render/prose.py`). Measured (2026-06-18) it does NOT:

- **generate the paper's figures.** There is no `\includegraphics` / pgfplots / `\caption` /
  plotting anywhere in `src/`. (Note the two *inverse/adjacent* things that already exist and
  are NOT this: `design/figure-digitization.md` reads data *from published figures* — the
  inverse; the "Supporting Information" in `loop/literature_acquirer.py` fetches a *cited
  paper's* SI as reading INPUT — input-side, not our output.)
- **generate the paper's own Supporting Information.** No SI/appendix render exists.

A real paper needs key figures whose numbering/captions are consistent with the body, and an SI
(the complete record behind the headline). Both are missing.

---

## 2. Core principle: record / belief ↔ SI / paper

sci-adk's record-vs-belief split maps directly onto paper structure:

- **Main paper = the BELIEF narrative**: the Claims + the *key* figures that carry the headline.
- **Supporting Information = the RECORD**: the full append-only Evidence, all data tables, all
  figures, the verdicts + decision rules, the provenance digest.

A rigorous SI *is* "the complete record behind the belief" — and sci-adk already stores exactly
that. So the SI is the most natural **deterministic** render of what sci-adk holds; only the main
paper needs authoring judgment.

**Agent / engine split (same as the prose hook).** The AGENT authors WHAT (which Evidence to
plot, captions, which Claims to feature); the ENGINE renders deterministically FROM THE RECORD
(no LLM at render time). Figures and the SI both follow this — a figure SPEC is agent-authored
input, exactly like prose; the plotting/dumping is deterministic.

---

## 3. Decisions (D1-D5, resolved 2026-06-18)

### D1 — Figures: **hybrid**, agent-spec → deterministic render
A figure has an **agent-authored spec** (mirrors `render/prose.py`): which Evidence series, plot
kind, caption, a stable label. The engine renders it deterministically by kind:
- **data plots → LaTeX-native (pgfplots/TikZ)**: emitted as *text* inside the `.tex`. No Python
  plotting dependency, no docker, no image files; Overleaf compiles it; the `paper/` folder stays
  trivially self-contained; determinism is automatic (it is text).
- **diagrams / arbitrary figures → image** (co-located `figures/*.pdf`), used only when a figure
  cannot be expressed natively.

The render assigns a **stable `\label{fig:<spec-id>}`** so the body's `\ref` resolves and
numbering is automatic — this is the "figure title/number unified with the paper body" the user
requires.

### D2 — Plot determinism
Native (pgfplots) is auto-deterministic (text). The **image** path MUST be reproducible (fixed
style/fonts/backend, no embedded timestamps) so a figure is part of the deterministic record
(re-render = byte-identical). This is why D1 prefers native wherever possible.

### D3 — SI = **auto record-dump + optional agent prose**
The SI is a deterministic render of the full record: every Evidence item, data tables from the
findings, ALL figures, verdicts + the frozen decision rules, and the record digest
(tamper-evidence). No authoring is needed — it IS the record. An OPTIONAL agent SI-prose hook
(mirrors `prose.py`) may add narrative around it. The strict, no-authoring record dump is the
spine.

### D4 — Consistency = **verify-style deterministic gate**
A deterministic check: every `\ref` resolves to a real `\label`; no orphan figure (defined but
never referenced); every main↔SI cross-ref (`Fig. S2`, `Table S1`) resolves. Surfaced as a
report and available as a hard gate — sci-adk's "the engine checks, not the author" spirit, a
natural extension of `sci-adk verify`.

### D5 — **One folder**
The deliverable is one `paper/` folder: `draft.tex` + `si.tex` (two compilable documents) +
`figures/` (image-path figures only) + `references.bib`. One Overleaf folder-upload yields both
the paper and the SI. Self-contained (extends the existing `references.bib` co-location).

---

## 4. Architecture

- **Figure-spec hook** (mirrors `render/prose.py`): agent-authored input — a list of specs
  `{id, kind: native|image, evidence_refs, plot:{type,x,y,...} | image_ref, caption}`. Absent →
  no figures (byte-identical skeleton, regression-locked, like the prose hook).
- **Figure renderer** (`render/figures.py`, PURE): spec + Evidence → a LaTeX `figure` env with
  `\caption`+`\label` — a pgfplots/TikZ body for native, an `\includegraphics` for image. Stable
  label from the spec id. No fs/LLM/network.
- **SI renderer** (`render_si_latex`, PURE): record → `si.tex` (Evidence dump, data tables, all
  figures, verdicts, digest). Deterministic.
- **Consistency checker** (PURE): scans the rendered `.tex`(s) for label/ref/cross-ref integrity
  → a report; reused by the render-time gate and by `verify`.
- **Compiler** (composition root, the ONLY filesystem toucher — consistent with the existing
  render-purity invariant): gathers Evidence + figure specs + prose + bib, calls the pure
  renderers, co-locates figure images + bib into `paper/`, runs the consistency check.

All renderers stay PURE (data in, string out) — the compiler composes. This preserves the
render-purity invariant already locked by the evidence-validity/render tests.

---

## 5. Open sub-decisions (resolve during implementation)

- **O-A — image-path source. RESOLVED (Phase 4-2).** The IMAGE source is a per-domain
  deterministic plotter living in the capability adapter (F4 seam), NOT the kernel: the first is
  an RDKit-in-docker molecule-structure plotter (`adapter/t1_figures.py`) that draws a `Molecule`
  to a fixed-canvas PNG inside `sci-adk-python-base`. The reproducibility story (D2) is satisfied
  and VERIFIED: the same molecule renders byte-identical across runs (pinned `rdkit==2024.9.6`,
  no timestamp in cairo PNG). The kernel render path (Phase 4-1) is domain-free — it only emits
  `\includegraphics{figures/<id><ext>}` from an `ImageFigureSpec`; the compiler co-locates the
  file. An agent-provided file is also accepted by that same render path (the spec just points at
  a file). digitized images remain a later option.
- **O-B — where the consistency gate lives.** Extend `sci-adk verify` (so a third party
  re-checks consistency headless) vs a render-time check vs both. Recommendation: a PURE checker
  used at render time AND surfaced in `verify`.
- **O-C — SI contents granularity.** The exact tables/sections of the record dump; how much
  provenance; how digitized vs measured Evidence is labelled in the SI.
- **O-D — pgfplots compile reality.** pgfplots is a LaTeX package (Overleaf ships it) → NO Python
  dep; but the generated pgfplots has the same "never run through a real LaTeX engine" caveat as
  the rest of the render — the first folder-upload is the real test.

---

## 6. Phasing (proposal)

- **Phase 1**: figure-spec hook + native pgfplots data-plot renderer + stable labels + folder
  co-location + prose↔figure `\ref` consistency (the user's headline need).
- **Phase 2**: SI auto record-dump renderer (`si.tex`) + main↔SI cross-ref consistency.
- **Phase 3**: consistency as a verify-style gate (extend `verify`).
- **Phase 4** (DONE, except 4c): 4-1 the image render path (`ImageFigureSpec` + co-location);
  4-2 the deterministic image source (RDKit-in-docker molecule plotter, O-A resolved); 4-3 the
  optional agent SI-prose hook. **4c** (cross-document main↔SI `\ref` via `xr`) is DEFERRED — the
  Overleaf compile-order wrinkle outweighs the value; plain-text "Figure S1" stays the convention.

---

## 7. Non-goals / honest caveats

- The render generates figures FROM the record (Evidence) — it does NOT invent data. A figure is
  only as honest as the Evidence behind it; the caption cites the Evidence id (traceable).
- No LLM at render time. The figure SPEC is agent-authored INPUT (like prose); the rendering is
  deterministic.
- Same never-real-compiled caveat as the rest of the render: pgfplots output is *designed* to
  compile but hasn't been run through a real LaTeX engine — the first Overleaf folder-upload is
  the test.
- The deferred render-time novelty 'first' gate is a sibling render-layer item; this design does
  not block it and shares the same self-containment + determinism constraints.

---

## 8. Constraints [HARD]

- Renderers PURE (data in, string out; no fs/LLM/network); the compiler is the composition root.
- The `paper/` folder stays self-contained for an Overleaf folder-upload.
- Deterministic: re-rendering the same record yields byte-identical output (figures included).
- No LLM/network in the render path.

---

Version: 0.2.0
Status: IMPLEMENTED (Phases 1-4; 4c cross-document `\ref` deferred)
Relates to: `design/research-session-enforcement.md` (sibling render-layer design pattern),
`design/literature-acquisition.md` (SI here is OUTPUT-side, vs the INPUT-side SI-acquisition
there), `design/figure-digitization.md` (the INVERSE — reading data from figures).
