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
  copied it verbatim to `paper/references.bib` (stem `references`) for the main paper. Since
  2026-10-10 it writes a LaTeX-safe copy instead and reads the pool from `literature/` first
  (see §7). There is exactly ONE literature pool per run; `references_SI.bib` is a SUBSET of
  it, not a separate acquisition.
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

## 6. Hardening (2026-07-01)

Two robustness fixes to the M6 bib path, TDD (reproduction-first). Neither re-opens the four
decisions; both harden their mechanism.

- **Brace-depth-aware `bib_subset`.** The subset builder (`render/pkgreqs_checks.py`) used a
  naive "next `@header` = entry end" slice, so a pool entry whose field value embeds a
  `@word{...}`-shaped token (e.g. `note = {... @inbook{X, y} ...}`) was TRUNCATED at that fake
  header — emitting a brace-unbalanced, field-losing entry (a lost `year = {...}`, an
  unbalanced brace) while the cite gate falsely read clean (`bib_keys` reads only the first
  line). Fixed by scanning `{`/`}` nesting depth from the entry-open brace to the TRUE matching
  close (`_entry_close_index`), still regex/line-based, no `bibtexparser` (house style). Contract
  preserved: `bib_keys(bib_subset(bib, keep)) == sorted(set(keep) & set(bib_keys(bib)))`, empty
  → `""`. Real-world trigger is LOW (paperforge/doi.org minimal bib), but the gate blind-spot
  was real.
- **Dual-bib integrity gate.** `sci-adk verify` now validates the brace-balance of BOTH
  `references.bib` (main) AND `references_SI.bib` (SI) — per-run (`paper/`) and package
  (`01_manuscript/`) — reusing the existing `_braces_balanced` helper (the .tex compile-integrity
  balancer). A PRESENT-but-brace-unbalanced bib FAILS, naming the file; a MISSING bib is not a
  failure (thin/absent SI, no-pool run stay clean per REQ-SA-606/615). The user's requirement:
  "references는 _SI도 따로 있기에 둘 다 검정해야함" — both bibs are validated, not just cite-resolution.

## 7. LaTeX-safe copy (2026-10-10)

The trial run's manuscript did not compile: entry `oki2005` in the run's pool has U+2212 MINUS
SIGN in its title, and the verbatim copy carried it into `paper/references.bib`.

- **The copy.** `paper/references.bib` is `latex_safe_bib(pool)` (`render/bib_latex.py`), and
  `paper/references_SI.bib` is the cited-only subset of that copy, so an SI entry stays byte-for-byte
  equal to its main-bib entry. Only field values change, plus one token: a bare month name
  BibTeX does not define (`month = June`, `sept`; BibTeX warns and drops the month) becomes its
  macro (`jun`, `sep`). In a value, running text, math (`$...$`) and verbatim arguments
  (`\url{...}`) are told apart. In text, HTML entities and the known tags (HTML face markup,
  Crossref's `scp`/`tt`/`ovl`/`font`, namespaced `mml:*`/`jats:*`) become LaTeX, any other `<` or
  `>` becomes `\textless{}`/`\textgreater{}`, a bare `&`, `%`, `#`, `_` is escaped and a bare `^`
  becomes `\textasciicircum{}` (measured: it prints U+005E; `\^{}` prints a raised accent). In
  math, `&`, `%`, `#` are escaped and `<`, `>` stay comparisons. A character pdflatex cannot
  typeset goes through render's prose map -- in math its form without the `$`, so no `$` is
  nested -- or becomes accent commands on the fully decomposed letter (`ǚ` → `{\v{\"{u}}}`,
  `ȩ́` → `{\'{\c{e}}}`, `Ș` → `{\textcommabelow{S}}`; boxed in `\mbox` inside math). `url` and
  `doi` values are left as they are apart from XML's own escapes: plainnat typesets them
  verbatim, so an escape there prints its backslash. Fields no style prints (`abstract`,
  `keywords`, `file`, `annote`, `timestamp`, ...: `bib_latex.UNPRINTED_FIELDS`, an exclusion list so
  an unknown field is still treated as printed) are copied as acquired. A character with no
  LaTeX form (a letter with a horn or hook above, CJK) is kept whole, never dropped or stripped
  of a mark. Keys are never touched, and the pool keeps the bytes it was acquired with.
- **The preamble.** The preambles sci-adk writes (paper draft, record, authored SI, package
  `record.tex`, and the package `main.tex`/`si.tex` skeletons) load `\usepackage[T1]{fontenc}`
  and `\usepackage{lmodern}` after inputenc. With inputenc alone pdflatex runs in OT1, where 22
  characters the copy keeps (« » ‹ › ‚ „ Ð Þ ð þ Ą ą Đ đ Ę ę Į į Ŋ ŋ Ų ų,
  `bib_latex.T1_ONLY_CHARS`) and the ogonek command `\k` stop the compile. One test compiles
  every character the copy keeps with the preamble a render emits; another compiles them in
  OT1 and pins the T1-only set.
- **The gate.** `sci-adk verify` fails a run whose `paper/references.bib` or
  `paper/references_SI.bib` still holds, in a printed field, an entity, a tag, a bare special,
  a `$` nested inside math or left open, or a character pdflatex cannot typeset, naming file,
  key and character with the LaTeX form to use, or -- where there is none -- saying to replace
  the character in the literature store with an ASCII approximation or a LaTeX form. A run
  rendered before this change passes again once re-rendered. The package gate runs the same
  check on `01_manuscript/` and names the `package_src/` file to fix, since the package copies
  its bibliographies from there. An author-supplied package `main.tex` or `si.tex` that loads
  no T1 (and no fontspec) fails only when a bibliography it loads holds a T1-only character;
  the line names the characters and entries and the `\usepackage[T1]{fontenc}` line to add.
  A month name BibTeX does not define in a package bib is an advisory line.
- **`record.tex`.** The deposit record emits `\bibliography{references}`, which resolves to a
  `references.bib` beside `record.tex` at the run root. No render writes one there, so the
  record's bibliography never reaches the pool's raw bib; a record that cites (only through
  `--si-prose`) shows its citations unresolved where it lies. Left as is.

---

Version: 1.3.0
Status: DECIDED (2026-07-01)
History:
- v1.0.0 (2026-07-01): the four confirmed decisions (cited-only subset, both paths, SI cite gate,
  design-first).
- v1.1.0 (2026-07-01): added §2a implementation clarifications from an independent plan-auditor
  pass on SPEC M6 (D1 author-supplied-verbatim vs generated-skeleton bibliography ownership; D2
  cited keys read from the SI SOURCE before the final render, no circularity; D6 no-cite/no-pool →
  NO `references_SI.bib` file). The four decisions are UNCHANGED; §2a only pins their mechanism.
- v1.2.0 (2026-07-01): §6 hardening — brace-depth-aware `bib_subset` (fixes truncation on an
  embedded `@word{...}` token in a field value) + dual-bib brace-integrity verify gate over BOTH
  `references.bib` and `references_SI.bib` (per-run + package). Mechanism hardening only; the four
  decisions are UNCHANGED.
- v1.3.0 (2026-10-10): §7 — the paper bibliographies are a LaTeX-safe copy of the pool (no longer
  verbatim), every emitted preamble loads T1 + Latin Modern, and verify's bib check covers what the
  copy cannot fix. Same day, after a second review: math-aware copy (no nested `$`), printed fields
  only, known tags only, `^` and month names, fully decomposed accents, and the package T1 check.
  The four decisions are UNCHANGED.
Decomposed by: SPEC-SI-AUTHORING-001 M6 (REQ-SA-6xx), revised in SPEC v0.3.1.
Extends: design/si-belief-record-split.md (v0.4, FROZEN — single source for the SI split)
Related: design/paper-figures-and-si.md, design/paper-publishing-requirements.md,
design/paper-writing-enforcement.md
