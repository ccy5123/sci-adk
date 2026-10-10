# Paper Publishing Requirements, Figure Font/DPI Policy, and Reproduction Bundle

> Status: **AGREED (2026-06-25)** — reviewed with the user; the open decision-forks (§6)
> are RESOLVED to their proposed defaults (see §6). Build may begin, F2 first (§5). The
> project's AGREED→BUILT discipline, as with abstractions.md / science-guards.md /
> render-architecture-reframe.md.
>
> Defines three publishing-stage features that extend the render contract of
> render-architecture-reframe.md WITHOUT touching the rigor kernel's record/belief core:
>
> - **F1 — Publishing requirements**: elicit, at `/sci publish` time, the conditions the
>   paper must meet, freeze them as a contract, and gate the rendered paper against the
>   deterministically-checkable ones via `sci-adk verify`.
> - **F2 — Figure font + DPI policy**: equations in a Times-compatible serif, all other
>   figure text in an Arial-compatible sans; raster (image) figures held to a minimum
>   effective DPI. Enforced at render time and re-checked by `verify`.
> - **F3 — Reproduction bundle**: the generating code is retained with the paper (an SI
>   code listing, and the source files under `paper/code/`), and `paper/reproduce.py`
>   lists those files and checks their SHA-256 hashes. It ships the files it names and
>   checks their hashes; it does not re-run them (§3, amendment of 2026-10-10: the record
>   holds no arguments or input files to re-run them with).

---

## 0. Where this sits (and what it must not break)

These are PUBLISHING-stage features. They obey the same constraints the render reframe
fixed:

- [HARD] **No LLM in the verdict path.** Every requirement that gates the paper is a
  DETERMINISTIC checker folded into `sci-adk verify` (the sole verdict). Subjective
  conditions are surfaced as ADVISORY, never as a pass/fail the engine fakes.
- [HARD] **Tool-agnostic paper.** A requirement is metadata + a gate; it NEVER injects a
  sci-adk-internal noun into `draft.tex` (the §10 / `paper_tool_clean` rule stands). The
  record dump, deposited as `runs/<id>/record.tex` outside the submission, is exempt, so
  F3's code listing lives there, not in the paper or in the authored `si.tex`.
- [HARD] **Record/belief separation.** The requirements artifact is a FROZEN contract (a
  record), like the Spec; the rendered paper is checked AGAINST it. Amending it is
  explicit, mirroring `sci-adk amend-spec`.
- **Render reframe inheritance.** F2/F3 attach to the deterministic spine (figures pull
  `y` from Evidence; the full record dump is `runs/<id>/record.tex`, while `paper/si.tex`
  is authored and written only when `sci-adk render` is given `--si si.json`). They add a
  font/DPI gate and a code artifact to that spine — they do not move the line back toward
  LLM-authored facts.

---

## 1. F1 — Publishing requirements

### 1.1 The artifact

A new FROZEN publishing contract at `runs/<id>/pubreqs.json` (run root, beside
`spec.json` — NOT inside the regenerated `paper/` dir, so `render` never clobbers it).

Proposed schema (a Pydantic model in `core/`, mirroring `Spec`'s freeze + digest):

```
PubReqs {
  spec_id: str
  frozen_at: ISO-8601
  digest: str                       # tamper-evidence, like the spec digest
  venue: str | None                 # free-text label ("arXiv", "JOSS", "<journal>")
  required_sections: list[str]      # e.g. ["Abstract","Introduction","Methods",
                                    #       "Results","Discussion"] — checked present
  figure_font_policy: bool          # F2 on/off (default true)
  image_min_dpi: int | None         # F2 raster gate threshold (default 300; null=off)
  reference_style: str | None       # "natbib"/"numeric"/... — checked in draft.tex
  max_pages: int | None             # advisory unless a deterministic page count exists
  max_words: int | None             # deterministic word count over prose slots
  reproduction_bundle: bool         # F3 on/off (default true)
  advisory: list[str]               # free-form conditions surfaced, NOT gated
}
```

All gate-bearing fields are frozen (anti-moving-the-goalposts): you cannot relax
`image_min_dpi` after seeing a figure fail, except by an explicit amendment receipt.

### 1.2 Elicitation (orchestrator-only)

[HARD] AskUserQuestion is the orchestrator's; a subagent cannot prompt. So the `/sci
publish` HUB collects the requirements BEFORE spawning `expert-writer`:

1. `/sci publish` starts → the hub asks (AskUserQuestion) for venue, required sections,
   font policy on/off, image min DPI, reference style, length limits, and any free-form
   advisory conditions. A "use defaults" fast-path offers the proposed defaults above.
2. The hub freezes `pubreqs.json` (a new thin verb, e.g. `sci-adk pubreqs freeze`, or
   folded into the existing flow — see Open fork OF-1).
3. The hub passes the frozen requirements to `expert-writer` in its spawn prompt (so the
   writer authors TO the contract) and to `sci-adk render` / `verify`.

### 1.3 The gate

`sci-adk verify` gains `paper_requirements_clean` (a HARD gate field alongside
`paper_consistent` / `paper_factref_clean` / `paper_tool_clean` / `paper_novelty_clean`
/ `paper_cross_doc_clean`). It runs the deterministic checks the frozen `pubreqs.json`
declares:

| Requirement | Deterministic check (read-only, no recompile, no LLM) |
|---|---|
| required_sections | each named section present as a `\section{...}` in `draft.tex` |
| figure_font_policy | the font preamble + per-figure font setup present (F2 §2) |
| image_min_dpi | every `\includegraphics` raster ≥ threshold effective DPI (F2 §2.3) |
| reference_style | the declared bib style wired in `draft.tex` (e.g. `\bibliographystyle`) |
| max_words | word count over the rendered prose ≤ limit |
| reproduction_bundle | `paper/reproduce.py` + `paper/code/` present and non-empty (F3) |

`advisory` items and `max_pages` (no deterministic page count without a compile) are
surfaced in the verify report but do NOT fail the gate. The CLI prints failures the same
way it prints the other paper gates.

When `pubreqs.json` is ABSENT, the gate is vacuously clean (a run with no declared
requirements behaves exactly as today — backward compatible).

---

## 2. F2 — Figure font + DPI policy

### 2.1 The font rule

- Equations / math: a Times-compatible serif.
- All other figure text (axis labels, ticks, legends, annotations): an Arial-compatible
  sans.

### 2.2 Engine choice (decided: pdflatex metric-compatible)

The current pipeline is pdflatex + Overleaf, default Computer Modern, NO font package
([paper.py:706-717](src/sci_adk/render/paper.py), [si.py:266-275](src/sci_adk/render/si.py)).
"Arial" and "Times New Roman" are proprietary; under pdflatex the standard is to use
their METRIC-COMPATIBLE free equivalents — no font files, no engine change, identical
metrics:

- math (Times-compatible): `mathptmx` (or `newtxmath`) in the preamble.
- text sans (Arial/Helvetica-compatible): `helvet`, applied to figure text only.

Preamble additions (guarded so the no-figure path is unchanged):

```
\usepackage{mathptmx}      % Times-compatible math + serif text
\usepackage[scaled]{helvet} % Helvetica/Arial-compatible sans
```

Per-figure: pgfplots labels/ticks set to `\sffamily` (sans = Arial-metric) while math in
labels stays serif (Times-metric). The figure environment scopes the sans default so
body text is unaffected. Native (pgfplots) figures are VECTOR — infinite resolution, so
"high DPI" is automatically satisfied; the DPI gate (§2.3) is RASTER-only.

(If a venue ever requires the literal Arial/Times New Roman font files, that is a
separate xelatex/lualatex + fontspec track — Open fork OF-2, NOT this proposal.)

Amendment (2026-10-10). The F2 build emitted `newtxmath` (math only) after
`[T1]{fontenc}` + `lmodern`, so a figure-bearing paper set its body in Latin Modern and its
equations in Times. Where the policy applies, render now emits `[T1]{fontenc}` +
`newtxtext` in place of `lmodern`, then `amsmath` + `newtxmath` + `[scaled]{helvet}`: body
and equations in one Times-compatible face (TeX Gyre Termes X), as the `mathptmx` line
above intended. Documents the policy does not apply to keep `lmodern`. The verify gate
requires all three packages (`newtxtext`, `newtxmath`, `helvet`), so a preamble with Latin
Modern text beside Times math fails it.

### 2.3 Raster (image) DPI gate

`ImageFigureSpec` ([figures.py:164](src/sci_adk/render/figures.py)) carries the source
`image` path and a LaTeX `width`; it does NOT record pixel dimensions. The compiler
co-locates the source to `paper/figures/fig<N><ext>`. So the DPI gate, at VERIFY time:

1. read the co-located image's pixel width (PNG/JPEG header via stdlib; Pillow if added);
2. resolve the display width in inches from the figure's `width` spec against a nominal
   `\textwidth` (≈6.5in for `article`);
3. effective DPI = pixel_width / display_width_in; fail if < `image_min_dpi`.

Honest limits (documented in the gate, like consistency.py's comment rule):
- Vector PDFs/EPS have no fixed DPI → skipped (vector is already resolution-independent).
- The display width is approximate (depends on the true `\textwidth`); the gate computes
  a CONSERVATIVE effective DPI and documents the assumption.
- The font INSIDE a raster image cannot be checked deterministically — fonts baked into a
  bitmap are out of scope (the gate covers resolution, not the raster's internal fonts).
  The font rule (§2.1) is enforced for engine-rendered NATIVE figures only.

### 2.4 Render-time + verify (both)

The font policy is emitted at render time (so the produced `paper/` is already correct)
AND re-checked by `verify` (so a hand-edited `.tex` that strips the policy fails the
gate) — the same render-time + verify-gate pairing the reframe uses for `\evval` / `\ref`.

---

## 3. F3 — Reproduction bundle (code retained + hash-checked)

The reproducibility core already exists: `provenance.code_ref` / `environment` / `seed`
([evidence.py:128-170](src/sci_adk/core/evidence.py)), the docker executor
([docker_executor.py:39](src/sci_adk/runner/docker_executor.py)), and `sci-adk verify`
re-deriving belief. F3 ADDS two artifacts to the render output:

### 3.1 SI code listing (retained)

`render/si.py` gains a "Reproduction code" section: for each Evidence item whose
`provenance.code_ref` resolves to a co-located script, the code is included as a LaTeX
listing (read-only, for the reader). The record dump is exempt from the tool-vocabulary
rule, so a code listing belongs there, not in the tool-agnostic paper. (Since
SPEC-SI-AUTHORING-001 that dump is deposited as `runs/<id>/record.tex`; `paper/si.tex` is
authored and carries no listing.) When `code_ref` is a bare commit/ref (no co-located
script), the record lists the reference (a pointer), honestly — it cannot inline a body it
does not hold.

### 3.2 Runnable bundle (executable on the spot)

The compiler's `stage_render` ([compiler.py:478-576](src/sci_adk/loop/compiler.py)) — the
same place it co-locates `figures/` and `references.bib` — additionally emits:

- `paper/code/` — the recorded generating code (co-located from each resolvable
  `code_ref`, mirroring the image co-location pattern);
- `paper/reproduce.py` — SUPERSEDED (see the amendment below): originally a thin DRIVER
  meant to re-run the recorded code through `sci-adk execute` / the docker executor. As
  built it is a manifest and a hash check: it lists the shipped files and checks their
  hashes, and runs nothing.

### 3.3 Gate

`reproduction_bundle` (F1 §1.3): `verify` checks `paper/reproduce.py` + `paper/code/`
exist, are non-empty, and reference real recorded `code_ref`s. It does NOT execute any
code — running arbitrary recorded code inside the read-only verify gate is out of scope and
unsafe (and `reproduce.py`, after the amendment below, runs nothing either).

Amendment (2026-10-10). The driver of §3.2 cannot be built from the record: a `code_ref`
records a script and its sha256, never the command-line arguments or the input files the
script was run with. On a real run the emitted driver called the executor with neither, so
every script stopped at once while its docstring promised to regenerate the results.
`paper/reproduce.py` is now a manifest and a hash check that runs nothing, and says so: it
lists each script shipped under `paper/code/`, the recorded results it backs (the first
sentence of each finding, with record ids removed -- see the second pass below) and the data those results name, checks
each shipped copy's sha256, and exits 0 only when every copy matches. Record ids and the
verbatim `code_ref`s sit only in its marked machine section. `paper/code/` holds one copy
per distinct script content under the script's own file name (a name shared by different
contents gets a `_<sha256 prefix>` suffix), byte for byte; every script a `code_ref` names
with its own `sha256=` is shipped, not only the leading one; decision meta-records
(`prior_work:`, `novelty:`, `contested:`, `inquiry:`) are not reproduction entries. A
re-render removes the `paper/code/` files the previous `reproduce.py` listed and the new one
does not, and nothing else. The §3.3 gate additionally requires, for every named script
with a recorded hash that resolves in the workspace, a copy in `paper/code/` with that hash.

Amendment (2026-10-10, second pass). Reviewing the first amendment on the same run found:

- *Only source files ship.* Any word followed by `sha256=<hex>` was read as a script, so a
  `code_ref` naming the data its script read (`analysis/data.csv sha256=...`) shipped the
  data into `paper/code/`, listed it as a script and inlined a CSV in the record. A named
  path is now a script only when its extension is in a fixed set of program-file
  extensions, compared case-insensitively (`SOURCE_EXTENSIONS` in `loop/code_ref.py`:
  `.py .ipynb .r .rmd .qmd .jl .m .do .ado .sas .sps .sh .bash .zsh .ps1 .bat .cmd .pl .pm
  .rb .lua .tcl .awk .sed .js .mjs .cjs .ts .c .h .cc .cpp .cxx .hpp .hh .f .for .f77 .f90
  .f95 .f03 .f08 .rs .go .java .scala .kt .cs .swift .hs .sage .wl .wls .nb .mpl .lean
  .thy .sql .mk .smk .nf .wdl .cwl`), or its file name is `Makefile`, `makefile`,
  `GNUmakefile`, `Snakefile` or `Dockerfile`. Any other path written with a hash, that has a directory
  part or an extension, is a data reference: `reproduce.py` lists it with its recorded hash
  under the script its `code_ref` names, and it is never copied (data can be large,
  licensed or private) and not gated.
- *The gate checks the script list.* `verify` compared the shipped copies with the record
  but not `reproduce.py`'s `SCRIPTS` list, which is what a reader's `python reproduce.py`
  checks against. It now reads that list (with `ast`, never executing it) and fails on an
  entry missing, an entry no `code_ref` names, or an entry whose hash differs from the
  recorded one; names are re-derived as the compiler derives them. A script named without
  a hash is compared by name only.
- *The report survives any console.* `reproduce.py` crashed when the console encoding could
  not show a character of a summary (e.g. `PYTHONIOENCODING=ascii`); it now prints such a
  character as `?`.
- *No placeholders for references.* Summaries had record ids replaced by "another recorded
  result" and kept the MethodPlan's internal approach numbers ("approach [13]"). A record
  id is now removed with the clause around it: cut where a preposition introduces it
  ("Named values for <id>" → "Named values"), removed with its part inside brackets, or
  removed as a whole clause; a first sentence left empty falls back to the output's file
  name. An approach number is dropped, never turned into the approach's title: the record
  does not fix whether the numbering starts at 0 or 1, so a title could name the wrong
  approach. The first sentence no longer ends at an abbreviation ("Environ.", "et al.",
  "Fig.", an initial).
- *Pruning also without listings.* A render with nothing to list returned before removing
  the `paper/code/` files the previous render had written. It now removes them, and removes
  the previous `reproduce.py` when a sci-adk render wrote it; a hand-written one stays.

---

## 4. File touch-list (rough, for the build that follows AGREED)

- `core/` — new `PubReqs` model + freeze/digest (mirror `Spec`); a thin `sci-adk pubreqs`
  verb (OF-1).
- `render/paper.py`, `render/si.py`, `render/figures.py` — font preamble + per-figure
  sans/serif scoping; SI code-listing section.
- `render/` (new small module) — the image-DPI checker + the font-policy checker (pure,
  like `consistency.py`).
- `loop/compiler.py` — emit `paper/code/` + `paper/reproduce.py`.
- `loop/verify.py` — `paper_requirements_clean` field + the requirement checks + DPI/font
  gates folded into the HARD exit gate.
- `cli.py` — `pubreqs` verb + verify-report printing for the new gate.
- templates: `science-workflow-publish` SKILL + `/sci publish` hub flow (elicitation) +
  `expert-writer` agent (author to the contract).
- `design/render-architecture-reframe.md` — note the extended render contract.
- tests across the above.

## 5. Build sequence (proposed)

F2 (font + DPI, self-contained) → F3 (code listing + bundle) → F1 (requirements artifact
+ elicitation + umbrella gate that absorbs F2/F3 as declared requirements). Each a
checkpointed unit with its own tests + commit. (Open to F1-first if the umbrella should
exist before its first tenants — OF-3.)

---

## 6. Decision-forks — RESOLVED (2026-06-25 AGREED)

- **OF-1 — `pubreqs` CLI surface**: RESOLVED → a dedicated `sci-adk pubreqs freeze` verb,
  so requirements can be frozen independently of a render (mirrors `init-spec`).
- **OF-2 — exact fonts**: RESOLVED → stay pdflatex metric-compatible (mathptmx/newtx +
  helvet). The xelatex/fontspec literal-font track is OUT of scope (revisit only if a venue
  demands the exact font files).
- **OF-3 — default `image_min_dpi`**: RESOLVED → 300 (print). Build sequence RESOLVED →
  F2-first.
- **OF-4 — `reproduce.py` granularity**: RESOLVED → a whole-run entry point (with per-figure
  helper functions). Superseded 2026-10-10: `reproduce.py` now lists the shipped scripts and
  the data files each recorded result names, checks every shipped file's SHA-256, and runs
  nothing (the record holds no arguments or input mapping to run them with). A bare-commit `code_ref` with no co-located script is recorded as a
  POINTER and does NOT block the bundle gate (fail-open, honest about what is held).
- **OF-5 — required-sections source**: RESOLVED → interactive elicitation with a fixed
  IMRaD default (Abstract / Introduction / Methods / Results / Discussion); venue profiles
  remain out of scope.

Build note (F2-first): F2 ships the render-time font policy (always emitted for
figure-bearing papers) + the pure font/DPI checker functions with tests. The verify HARD
gate that CONSUMES those checkers is wired in F1 (the `paper_requirements_clean` umbrella
driven by `pubreqs.json`); until F1, an absent `pubreqs.json` keeps the gate vacuous
(backward compatible), while the produced `paper/` is already font-correct.

---

Version: 0.1.0
Status: PROPOSAL — awaiting AGREED
Source: user feature request (2026-06-25) — paper conditions + figure fonts + runnable code
References: design/render-architecture-reframe.md, design/paper-figures-and-si.md,
design/abstractions.md, design/evidence-validity.md, design/sci-adk-as-moai.md (§4 publish).
