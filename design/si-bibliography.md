# SI Bibliography Decision Record — the authored `si.tex` gets its own `references_SI.bib`

> Status: DECIDED (2026-07-01)
> Classification: DECISION RECORD (single source for the `references_SI.bib` decision)
> Decomposed by: SPEC-SI-AUTHORING-001 M6 (v0.3.0), requirements `REQ-SA-6xx`.
> Relationship to the FROZEN design: this record EXTENDS `design/si-belief-record-split.md`
> (v0.4, the FROZEN design for the SI belief/record split). That file remains the SINGLE
> SOURCE for the record/belief split itself; this file adds ONLY the bibliography-wiring
> decision the split left implicit. No re-decision of v0.4.

## 0. What this resolves

`design/si-belief-record-split.md` v0.4 made `si.tex` an AUTHORED belief artifact (②) — the
overflow of `main.tex` — reusing the `paper.py` prose machinery, with `\cite`/`\citep`
surviving verbatim through the sanitizer (`authored_si.py:_slot`). But the authored-SI
renderer was shipped WITHOUT any bibliography wiring: it adds `\usepackage{natbib}` in the
preamble but never emits a `\bibliography{}` line and takes no `bib_path` parameter. So any
`\cite`/`\citep` the author writes in `si.tex` renders as `[?]`. This record fixes that gap
by giving the authored SI its OWN bibliography file, `references_SI.bib`, symmetric to how
`main.tex`/`draft.tex` uses `references.bib`.

## 1. The measured gap (file:line — the SPEC must encode these, not re-decide them)

- **The authored-SI renderer has NO bib wiring (the gap).**
  `src/sci_adk/render/authored_si.py:113` — `render_authored_si_latex(si, spec, claims,
  evidence)` has NO `bib_path` parameter. The preamble adds `\usepackage{natbib}` at
  `authored_si.py:192`, but the render ends at `\end{document}` (`authored_si.py:244`) with
  NO `\bibliography{}` line. A `\citep`/`\cite` the author writes therefore has no `.bib` to
  resolve against and prints `[?]`.
- **The compiler calls it with no bib passed.**
  `src/sci_adk/loop/compiler.py:625` — `render_authored_si_latex(si, spec, claims_list,
  evidence_list)`. No bib is co-located for the SI and none is passed.
- **The stale comment.** `compiler.py:544` ("The co-located `references.bib` is wired into
  BOTH documents (the SI's `\citep` resolved too).") is STALE: it describes the OLD
  record-dump path (`render_si_latex`, which DID take `bib_path`, `si.py:540-543`), not the
  new authored `si.tex`. It must be corrected when M6 lands.
- **Both siblings DO wire bib correctly (the symmetry anchors).**
  - main paper `src/sci_adk/render/paper.py:831-834` — `\bibliographystyle{plainnat}` +
    `\bibliography{<stem>}` when a `bib_path` is supplied.
  - the deposit record dump `src/sci_adk/render/si.py:540-543` — same wiring; takes
    `bib_path`. (That dump now lands in `record.tex` in the deposit, M1, NOT in `si.tex`.)
- **The per-run literature pool (the subset source).**
  `src/sci_adk/loop/compiler.py:814` (`_locate_bib_path`) — the run's ONE literature pool is
  `runs/<id>/artifacts/literature/references.bib`. `compiler.py:582,832` (`_colocate_bib`)
  copies it verbatim to `paper/references.bib` (stem `references`) for the main paper. There
  is exactly ONE literature pool per run; `references_SI.bib` is a SUBSET of it, not a
  separate acquisition.
- **The package path ships ONE shared bib.**
  `src/sci_adk/render/package.py` — `01_manuscript/` gets `main.tex + si.tex +
  references.bib`; the single `references.bib` is copied from `package_src/references.bib`
  (`package.py:431-437`, `_ensure_manuscript`); the merged `main.tex` wires
  `\bibliography{references}` (`package.py:543-544`). The authored `package_src/si.tex` is
  preserved verbatim (`package.py:449-451`) but shares that one `references.bib` and (like
  the per-run authored SI) is not currently wired to any SI bib.
- **verify's cite-resolution gate today checks the main manuscript ONLY.**
  - per-run: `src/sci_adk/loop/verify.py:1012-1018` reads `paper/references.bib` and runs
    `cite_resolution_problems(draft_tex, bib)` — over `draft.tex` only. `si.tex` is NOT
    cite-checked.
  - package: `src/sci_adk/loop/verify.py:1242` runs `cite_resolution_problems(main_tex, bib)`
    — over `main.tex` only. `si_tex` is number-audited, compile-checked, tool-vocab-scanned,
    and value-fidelity-scanned (`verify.py:1212,1222,1254,1264`) but is NOT passed to
    `cite_resolution_problems`.
- **The subset selection is already a pure, deterministic pair of helpers (no LLM).**
  `src/sci_adk/render/pkgreqs_checks.py:113` `cited_keys(tex)` (every distinct `\cite*` key in
  a `.tex`, sorted, PURE) + `pkgreqs_checks.py:124` `bib_keys(bib)` (every entry key in a
  `.bib`, PURE). The SI subset = entries of the literature pool whose key is in
  `cited_keys(si_tex)`. `cite_resolution_problems` (`pkgreqs_checks.py:129`) is the existing
  pure gate this record parallels for `si.tex` vs `references_SI.bib`.

## 2. The four confirmed decisions (SETTLED — encode, do not re-open)

1. **Content policy — cited-only subset from the SAME per-run pool.** `references_SI.bib`
   contains ONLY the entries CITED in `si.tex`, selected as a SUBSET of the single per-run
   literature pool (`runs/<id>/artifacts/literature/references.bib` → co-located
   `paper/references.bib`). There is NO separate SI literature-acquisition pool. Uncited
   entries MUST NOT appear (keeps the SI self-contained and consistent with the
   cite-resolution gate: every `\cite` in `si.tex` resolves in `references_SI.bib`, and no
   dead entries pad it).

2. **Scope — both compile paths, symmetric to `main.tex`.**
   - per-run compile path: `paper/si.tex` + a co-located `paper/references_SI.bib`; `si.tex`
     wires `\bibliography{references_SI}`.
   - package submission path: `01_manuscript/si.tex` + `01_manuscript/references_SI.bib`; the
     package `si.tex` wires `\bibliography{references_SI}`.
   In both cases this mirrors the EXISTING `main.tex`/`references.bib` treatment.

3. **verify gate — a cite-resolution gate for `si.tex` vs `references_SI.bib`.** ADD a
   cite-resolution gate for `si.tex` against `references_SI.bib`, exactly parallel to the
   existing `main.tex`-vs-`references.bib` gate (`cite_resolution_problems`), per-run and
   package. Every `\cite*` key in `si.tex` MUST resolve in `references_SI.bib`.

4. **Process — design + SPEC first, implementation later.** This record + SPEC M6 come first;
   no `src/` change is made until the user reviews.

## 2a. Implementation clarifications (audit-driven, v1.1)

An independent plan-auditor pass on SPEC M6 surfaced three mechanism points that the four
decisions above did not fully pin. These clarify HOW the decisions are realized; they do NOT
change WHAT was decided.

- **(D1) Who owns the `\bibliography{references_SI}` line in the package `si.tex`.** Because an
  author-supplied `package_src/si.tex` is copied VERBATIM (`package.py:449-451`), the assembler
  cannot inject wiring into it. So the wiring has TWO owners by case:
  - author-supplied `si.tex` → the AUTHOR owns the `\bibliography{references_SI}` line; the
    assembler ONLY lands `01_manuscript/references_SI.bib` beside the copied file. A missing or
    wrong author bibliography is surfaced by the SI cite-resolution gate (decision 3), not
    silently repaired.
  - assembler-generated skeleton `si.tex` (`_skeleton_si_tex`, `package.py:459-482`) → the
    assembler owns the line and wires `\bibliography{references_SI}` IFF the skeleton cites
    anything.
  The per-run `paper/si.tex` is renderer-emitted, so its `\bibliography` line is emitted by
  `render_authored_si_latex` when a `bib_path` is supplied (no verbatim-copy tension there).
- **(D2) The cited-key set is read from the SI SOURCE, before the final render.** To avoid a
  latent circularity (`cited_keys` needs the SI text, but `bib_path` is a render input), cited
  keys are extracted from the authored SI SOURCE — the `AuthoredSI` section bodies
  (`prose.py:187,219`) — BEFORE the final render (or via a first no-bib render pass), then the
  cited-only subset is built and passed as `bib_path` to the SINGLE final render. This is
  well-defined because `\cite`/`\citep` keys survive the fidelity pipeline VERBATIM (`_slot` runs
  `substitute_factrefs` + the sanitizer, both preserving `\cite`/`\ref`, `authored_si.py:157-177`),
  so the source cited keys equal the rendered cited keys.
- **(D6) No citations / no pool → NO `references_SI.bib` file (ABSENCE, not an empty file).** When
  `si.tex` cites nothing or the run has no literature pool, the compiler writes NO
  `references_SI.bib` and passes no `bib_path`, so `si.tex` emits no `\bibliography` — mirroring
  the main paper's missing-pool handling (`compiler.py:830-831`). A single, unambiguous file
  state.

## 3. Rationale

- **Symmetry with `main.tex`.** The main paper resolves citations from a co-located
  `references.bib` wired as `\bibliography{references}` (`paper.py:831-834`). The authored SI
  is the overflow of the main paper (design §2/§5) and is a submission document in its own
  right; it should resolve citations the same way. A separate `references_SI.bib` makes
  `si.tex` structurally identical to `main.tex` — one authored `.tex` + one co-located `.bib`.
- **Self-contained SI.** A journal supplement is uploaded and reviewed as its own PDF. A
  cited-only SI bib means the SI compiles standalone with no `[?]`, and carries no references
  the SI never cites. This matches the journal-submission norm (the SI has its own reference
  list).
- **Consistency with the cite-resolution gate.** The gate is "every citation has a
  reference." A cited-only subset makes the gate exact for the SI: `cited_keys(si_tex) ⊆
  bib_keys(references_SI.bib)` by construction, and there is no benign-but-confusing surplus.
- **Why a SEPARATE file, not the shared `references.bib`.** The SI is a distinct compiled
  document. Pointing `si.tex` at the main paper's full `references.bib` would (a) print the
  main paper's uncited-in-SI references in the SI's reference list (violating self-
  containment) and (b) couple the two documents' bibliographies. A cited-only subset keeps
  each document's reference list scoped to what that document cites.

## 4. Record / belief framing (constitution alignment)

- **`references_SI.bib` is BELIEF-SIDE, co-located with the authored `si.tex` (②).** It is
  the SI's citation apparatus, part of the authored submission document — NOT a new RECORD
  artifact. The record floor is unchanged: `runs/` + `sci-adk verify` + the deterministic
  `record.tex` + the "Data & code availability" statement (design §5). `references_SI.bib`
  does not enter the deposit-completeness check and asserts no measured value.
- **No LLM at bib-selection time.** The subset is chosen DETERMINISTICALLY: scan the authored
  `si.tex` for `\cite*` keys (`cited_keys`, pkgreqs_checks.py:113), then filter the literature
  pool (`bib_keys`, pkgreqs_checks.py:124) to that key set. The agent authors the `\cite`
  calls (belief); the bib assembly is a pure set operation over the existing pool (no model,
  no network) — consistent with sci-adk's "no LLM in the record/apparatus assembly" and with
  how `_colocate_bib` faithfully copies an existing pool rather than generating one.
- **Reuse, do not re-acquire.** `references_SI.bib` is derived from the ALREADY-ACQUIRED
  per-run pool; M6 adds no literature-acquisition path. The single acquisition pool remains
  `runs/<id>/artifacts/literature/references.bib`.

## 5. Scope and non-goals

- **In scope:** wiring the authored-SI renderer to emit `\bibliography{references_SI}`;
  building + co-locating the cited-only `references_SI.bib` per-run and in the package;
  extending the cite-resolution gate to `si.tex` vs `references_SI.bib` (per-run + package).
- **Out of scope / non-goals:**
  - No separate SI literature acquisition — the SI bib is a subset of the ONE per-run pool.
  - No change to `main.tex`/`references.bib` wiring (`paper.py`, `_colocate_bib`).
  - No change to the deposit `record.tex` (it keeps its own `references.bib` wiring from
    `render_si_latex`, `si.py:540-543` — it is the record artifact, unaffected by ②'s bib).
  - No change to what `sci-adk verify` computes over `runs/` or the record; the new gate is a
    belief-side cite-resolution check, parallel to the existing one.
  - No `zref-xr` / cross-document coupling (already dropped, design §6).
  - No domain/study specialization.

---

Version: 1.1.0
Status: DECIDED (2026-07-01)
History:
- v1.0.0 (2026-07-01): the four confirmed decisions (cited-only subset, both paths, SI cite gate,
  design-first).
- v1.1.0 (2026-07-01): added §2a implementation clarifications from an independent plan-auditor
  pass on SPEC M6 (D1 author-supplied-verbatim vs generated-skeleton bibliography ownership; D2
  cited keys read from the SI SOURCE before the final render, no circularity; D6 no-cite/no-pool →
  NO `references_SI.bib` file). The four decisions are UNCHANGED; §2a only pins their mechanism.
Decomposed by: SPEC-SI-AUTHORING-001 M6 (REQ-SA-6xx), revised in SPEC v0.3.1.
Extends: design/si-belief-record-split.md (v0.4, FROZEN — single source for the SI split)
Related: design/paper-figures-and-si.md, design/paper-publishing-requirements.md,
design/paper-writing-enforcement.md
