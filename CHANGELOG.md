# Changelog

All notable changes to sci-adk are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The public surface (CLI + curated Python API) is frozen as the 1.0 contract
(`design/surface-freeze-analysis.md`); `1.0.0` will be tagged near the methods-paper
(JOSS) submission. `0.2.0` is the first tagged release.

## [Unreleased]

### Added

- The research-workspace kit has a new PreToolUse hook (`.claude/hooks/sci-adk/ascii-script-gate.sh`,
  timeout 30 s) on Write, Edit, MultiEdit and NotebookEdit that blocks a call putting a character
  outside ASCII into a script. It runs `sci-adk check-ascii`, an internal verb outside the public
  CLI (not listed by `sci-adk --help`): it reads the hook input on stdin and exits 3 to block, 0
  otherwise. The hook blocks on exit 3 only; when sci-adk is missing or fails, it lets the call
  through with a warning. Lean files are exempt, and a line written back unchanged is not judged
  (a line ending CR LF and the same line ending LF are one line). `sci-adk init-session` installs
  the hook and its settings entry.
- `sci-adk append-evidence` refuses an Evidence item (exit 2, nothing recorded) whose
  `code_ref` names a script holding non-ASCII bytes. `sci-adk verify` adds one advisory per
  such script recorded before this change.

### Changed

- The bibliographies sci-adk ships (`paper/references.bib`, `paper/references_SI.bib`, the
  `paper/deposit/` copy, the package's SI cut) are a canonical copy of the literature store:
  every entry BibTeX reads, written as `@type{key, field = {value}, ...}`, macros expanded, no
  `@string`, `@preamble` or `@comment`. A value keeps only allow-listed commands (accents,
  letters, text symbols, simple markup, math defined without amsmath); any other command is
  printed as text. The fields no style prints (`abstract`, `keywords`, `copyright` and the
  others `bib_latex.UNPRINTED_FIELDS` names), the ISSN and a url that is the doi.org link of
  the entry's doi are left out of every shipped copy without a warning (the literature store
  keeps them). An entry whose key no citation can name or that repeats a key, a url or doi that
  is not plain and a crossref to an absent entry are left out too, and each of these, like a
  BibTeX syntax error in the store, is a render warning naming the entry.
- In that copy a `(` or `)` at brace level 0 of an author, editor or key field is braced
  (natbib read the label up to the first `(` and stopped on `Doe ({\"O}nal)`); an entry plainnat
  would label by the first three characters of its organization (an authorless `@manual` or
  `@proceedings`) or of its citation key, where those cut an escape, math or a letter in two or
  hold `_`, gets a `key` field of plain letters (natbib then cites it by that key, without a
  year, as plainnat cites any entry with a key); a key field is at most 100 characters; `\not`
  is kept only before one character or one plain math symbol (newtxmath's `\not` looped on
  anything else); a script after a math font declaration on a scripted base gets an empty base
  (`x^2\rm^3`); an accent over an empty or doubly braced group is written with its braces
  dropped (`\~{{}}` -> `\~{}`) or printed as text. Each stopped pdflatex in the draft, the SI
  and the record while render and verify said nothing. A run rendered before this change fails
  `verify` until it is rendered again (see below).
- A package bibliography the author supplies also fails on what natbib or BibTeX stop on though
  every command in it is allowed: a `(` followed by a command, group or letter outside ASCII in
  the names or key a label holds, a bracket there, a label too long for BibTeX, an unsafe
  three-character label, a year that is not plain text (`bib label:`); a command with a capital
  letter or a capital in math at brace level 0 of a title, edition or type, which BibTeX's case
  change lowercases (`bib case:`, fix: braces); a key a citation cannot name, a type named like a
  style's function (`bib entry:`); a value longer than BibTeX holds.
- In that copy a link command (`\href`, `\url`) inside another link is printed as text (hyperref
  keeps at most 10 open: 11 nested `\href` stopped pdflatex); math commands with arguments nest
  at most 4 deep, with no arrow accent inside another and no `\sqrt` with an index inside another
  `\sqrt`, text markup nests at most 8 deep, and a value holds at most 32 math commands with
  arguments (`\sqrt[3]` 12 deep, `\overrightarrow` 11 deep or 4700 of them in one reference kept
  pdflatex busy for minutes; `\textsuperscript` 37 deep stopped it). The rest are printed as
  text, each a render warning. An entry whose key starts with a character outside ASCII (a
  `\cite` naming it first stopped pdflatex: "Missing \endcsname inserted") or is longer than 200
  characters is left out, the warning suggesting an ASCII key; a letter outside ASCII later in a
  key is kept. A name ending in a comma followed only by `-`, `--` or `~` is written without it
  (BibTeX: "has a comma at the end"). A superscript right after a prime keeps its base (`x'^2`;
  TeX joins them), and a prime after a space gets an empty base (`x' '` was a double
  superscript).
- More than 26 entries sharing one citation label (plainnat tells them apart by a letter after
  the year, a to z, and natbib stops on the 27th cited) are a render warning, and in `verify` a
  `bib label:` failure when the manuscript cites more than 26 of them, an advisory when it cites
  fewer. The copy is not rewritten.
- A package bibliography the author supplies also fails on those nesting and count limits, on a
  key that starts outside ASCII or is longer than 200 characters, and on a superscript or
  subscript the copy rewrites so that it compiles (`bib script:`: `x^2^3`, `x_1_2`, `x^2'`, `x^$`,
  `x^\rm 2`, `x^\hat{y}`, `x^\cdots`, a letter outside ASCII after `^`).
- The bibliography checks read a file once and at most its first 5000 commands (entries,
  `@string`, `@preamble`); a file with more fails with a `bib size:` line. 100000 `@string`
  macros, 50000 repeated keys or a 3 MB copy took from 30 s to minutes in `verify`; each now
  takes a few seconds.
- `render --record-only` no longer says the scripts its record shows by name only are shipped
  under `paper/code/` (that mode writes nothing under `paper/`); it says a full render ships them.
- `verify` prints a bibliography's re-render remedy once per file, not on every entry line.
- `sci-adk verify` fails a shipped bibliography that is not that canonical copy, or that holds
  a command off the allow-list or a character pdflatex cannot typeset, whether or not
  `pubreqs.json` is frozen. **A run rendered before this change fails until it is rendered
  again with the inputs of its last render** (`sci-adk render <run_dir> --prose ... --si ...
  --si-prose ... --figures ...`, each that the run used; the deposit declaration is kept from
  the last render, and a bare `sci-adk render` writes a skeleton draft). A package bibliography the author supplies is checked against the
  allow-list in every field and fails on a BibTeX syntax error, a repeated key or a macro no
  `@string` defines. The package SI bibliography is held to the canonical form only when the
  assembler cut it.
- The bibliography deny-list is gone. A lint names the commands that read or write files or run
  code in author-written LaTeX (an authored SI body, a package `main.tex` or `si.tex`), as a
  render warning and a verify advisory; it never fails a run. It also names `\VerbatimInput`,
  `\makeatletter`, `\newread` and `\newwrite`.
- The English-only scripts hook lets a Write, Edit or MultiEdit of a document (`.md`, `.csv`,
  `.json`, `.tex`, `.lean` ...) through without starting sci-adk, and warns when its input is not
  a JSON object. The verify advisory for a recorded non-ASCII script is printed as `advisory:`
  with or without a publishing contract.
- `.pyw` joined `code_ref.SOURCE_EXTENSIONS` (Python source): a `.pyw` script a `code_ref`
  names is now shipped under `paper/code/` in the reproduction bundle, and the English-only
  scripts rule covers it. Before, the bundle did not copy it (written with a hash, it was
  listed as a data reference).

- `sci-adk render` writes a LaTeX-safe copy of the run's literature bib into
  `paper/references.bib` and `paper/references_SI.bib` instead of a verbatim one: HTML
  entities and tags (`<i>`, `<sub>`, `<span>`, `<jats:p>` ...) become LaTeX, any other `<` or
  `>` prints as itself, a bare `&`, `%`, `#` (and `_` or `^` outside math) is escaped, and
  characters pdflatex cannot typeset go through render's character map (inside `$...$`
  without a second pair of `$`) or become accent commands. A bare month name BibTeX does not
  define (`month = June`, `sept`) becomes its macro (`jun`, `sep`). The literature store is
  never rewritten. (Since the canonical copy, above, the copy also leaves out fields no style
  prints and a url or doi that is not plain.)
- `sci-adk verify` fails a run whose `paper/references.bib` or `paper/references_SI.bib`
  still holds, in a field a style prints, a character pdflatex cannot typeset, an HTML entity
  or tag, a bare special, or a `$` nested inside math or left open. Each line names the file,
  the entry key and the character, and either the LaTeX form to use or, where there is none,
  that the character must be replaced in the literature store. A run rendered before this
  change fails until it is rendered again with the inputs of its last render. The package gate
  runs the same check, names the `package_src/` file to fix, and advises on month names
  BibTeX does not define.
- The preambles sci-adk writes (paper draft, record, authored SI, the package `record.tex`,
  and the package `main.tex` and `si.tex` skeletons written when the author supplies none)
  load `\usepackage[T1]{fontenc}` and `\usepackage{lmodern}` after inputenc. In the default
  OT1 encoding letters such as Ð, þ, Ę, Ų and the guillemets stopped pdflatex. An
  author-supplied package `main.tex` or `si.tex` is not changed: the package gate fails it
  only when it loads no T1 and the bibliography it loads holds such a character, naming the
  characters and the line to add.

## [0.3.0] - 2026-06-30

### Added

- bib LaTeX-safety gate in `sci-adk verify`: a blocking check
  (`bib_latex_safety_problems`) that fails on a `references.bib` containing HTML
  entities (`&amp;`), HTML tags (`<i>`), a bare `&`, or non-standard Unicode
  spaces — the failure modes that break `bibtex`/`pdflatex`. Runs per-run and at
  the package level; names the offending entry, never rewrites it.
- `--version` flag (reads the installed package metadata).
- 15-minute try-it tutorial for external users (`docs/tutorial.md`), the landing
  page for a clean-clone first run (`git clone` -> `pip install -e .` ->
  `sci-adk verify runs/t1-godel`, verified reproducible offline).
- pyOpenSci / JOSS readiness: coverage report in CI and GitHub issue templates
  (bug report / feature request).

## [0.2.0] - 2026-06-30

### Added — public API

- Curated public Python API: `sci_adk` re-exports the 29-symbol record/belief
  surface (Spec / Evidence / Claim + `DecisionEngine` + `verify_run` /
  `verify_package`), guarded by a contract test; everything else is
  internal/unstable.

### Added — kernel spine

- Core types with invariant enforcement: Spec (S1–S5), Evidence (E1–E4),
  Claim (C1–C6) — record (append-only) vs belief (revisable) separation.
- Four-pane proposal parser (Background / Goal / Method / Expected Output;
  English and Korean section headers).
- `DecisionEngine`: threshold + Bayesian + interval numeric rules, plus a
  proof/qualitative judge rail with a mandatory verdict-trail gate.
- `sci-adk verify`: headless re-derivation of every recorded Claim plus a record
  digest (tamper-evidence); exit 0 iff all claims reproduce — no LLM required.
- Checkpoint loop (`sci-adk resolve`) re-entering a run with recorded verdicts.
- Capability-adapter seam with an enforced "kernel must not import adapter"
  invariant (F4 lint).
- T-1 capability: an injective Gödel-style molecular-graph encoding with an
  autonomous numeric injectivity verdict.
- Docker-isolated Python execution with provenance capture.

### Added — rigor and publishing layers

- Referent-typed evidence-validity enforcement (synthetic data cannot make a
  SUPPORTED *empirical* claim).
- Figure-digitization as a gated `digitized` Evidence kind (extractor ≠
  verifier).
- Science guards G1–G5 (analyticity / test-power / falsifiability / mode /
  cost) — pure, no-LLM spec-layer rigor gates surfacing findings in
  `runs/<id>/science.md`.
- Literature triggers: prior-work recording, contested status, and novelty as a
  first-class revisable Claim (2-kind: result vs method).
- Render record-fidelity spine: a deterministic spine + agent-authored belief
  narrative + a markup fidelity gate, producing a tool-agnostic paper; native
  figures and an SI record dump.
- Publishing requirements F1/F2/F3 (`pubreqs` contract + figure font/DPI policy
  + reproduction bundle), gated inside `sci-adk verify`.
- Workspace-level near-submission package (`sci-adk package`, `pkgreqs`, and a
  `package_requirements_clean` gate).
- Operational layer (`sci-adk init-session`): the `science-orchestrator`
  persona, worker and guard agents, `/sci` commands, and enforcement hooks.

### Project / release hygiene

- MIT license; `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `CITATION.cff`; CI running the unit suite on Python 3.11 and 3.12.
- CLI/API surface-freeze analysis fixing the 1.0 contract
  (`design/surface-freeze-analysis.md`); methods-paper (JOSS) draft under `paper/`.

[Unreleased]: https://github.com/ccy5123/sci-adk/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ccy5123/sci-adk/releases/tag/v0.2.0
