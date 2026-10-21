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

## 4b. LaTeX a prose slot may carry (2026-10-11)

A prose slot (`PaperProse` and `SIProse` fields) is escaped as text except for a closed list
(`paper._latex_sanitize_prose`): `\ref` `\autoref` `\cite` `\citep` `\citet` with a
key of label characters (§4e), passed verbatim (`\eqref` was on the list until §4d), and —
added after the
second trial paper — one structural command, the run-in heading `\paragraph{<text>}`.
Before, a writer who gave Methods/Results lead-in labels as `\paragraph{Data.}` got the
literal text `\textbackslash{}paragraph\{Data.\}`,
so the trial paper fell back to sentence fragments ("Data. BCF values were …", "Slope. 341
chemicals …").

- The heading text is reader-facing prose, so it is escaped like the rest (`95%` → `95\%`,
  unicode folded); only the command and its braces pass. `\evval`/`\status` inside it are
  substituted first, like anywhere else in the slot.
- Brace-free text only: a heading holding another command (`\paragraph{A \textbf{b}}`) is not
  matched and stays literal, so the heading cannot carry LaTeX the list does not allow.
  `\paragraph*`, `\subparagraph` and `\paragraphs` stay escaped.
- No paragraph break in the text: a newline passes only when the next line is not blank (a line
  of spaces or tabs is blank to TeX). `\paragraph{a<blank line>b} c` stopped pdflatex with
  "Paragraph ended before \@sect was complete" while render and `verify` exited 0; it now stays
  literal.
- Only inside a section. `\begin{abstract}\paragraph{…}` stopped pdflatex with "Something's
  wrong--perhaps a missing \item" (the abstract is a list environment): render now refuses a
  heading in the abstract, checked after `\evval`/`\status` substitution, with an error naming
  the slot (exit 2, `draft.tex` not written). The title is escaped whole, so a heading there
  would print as literal text: refused the same way. A novelty sentence cannot hold one (its
  text is brace-free), and the SIProse slots each sit in a section.
- Any other `\paragraph` form in a prose slot (braces or commands in the text, a blank line,
  `\paragraph*`, a space before the brace, no closing brace) prints as literal text: render
  names the command in a warning (stderr, non-blocking; since §4d one rule for every command
  printed as literal text, `paper.literal_command_warnings`). Pinned in
  `tests/test_prose_heading_slots.py`, with pdflatex builds of the allowed forms and of the two
  constructs render no longer writes.
- The authored `si.tex` body is verbatim LaTeX and already carried `\paragraph` (the trial SI
  uses it for its protocol summary), so the same lead-in now renders the same in both documents.
- The checks over the rendered documents read the heading text: the tool-vocabulary scan is a
  substring scan, and the declared-number tokenizer (`render/number_literals.py`) counts section
  titles and captions as literals. The pattern audit used by runs without `numbers.json`
  (`render/number_audit.py`) strips `\paragraph{…}` as it strips `\section{…}` (OD-3); that
  module is kept byte-stable, so a number in a lead-in label is checked only by the declared
  list. Pinned in `tests/test_prose_paragraph_and_date.py`.

Measured on a copy of the trial run (SPEC-BCFKOW-001): ten lead-ins rewritten as
`\paragraph{…}`, re-rendered, `sci-adk verify` exit 0 with `numbers.json` unchanged, draft and SI
compile under pdflatex with no errors, labels typeset as run-in headings.

## 4c. No date on the rendered documents (2026-10-11)

`draft.tex`, the authored `si.tex` and the deposit's `record.tex` wrote `\date{\today}`, so every
compile of the same source printed that day's date: the same record compiled on two days gave
two different title pages. All three now write `\date{}` (no date line), as the package skeleton
(`render/package.py`, `make_si.py`) already did. The submission date belongs to the venue; the
record's own times are in the record (Evidence timestamps, the protocol-history advisory).

## 4d. What the sanitizer lets through (2026-10-11)

A pass over the render path with hostile input found prose that rendered and verified (exit
0) but stopped pdflatex or changed what it read. Closed in `render/paper.py`, pinned in
`tests/test_latex_sanitize_hardening.py` (pdflatex builds included):

- **Compatibility forms of the specials.** The sanitizer escaped the ASCII specials, then
  folded each other character (NFKD) and kept the ASCII result unescaped, so a fullwidth or
  small-form `\ { } & % # _ $ ^ ~` became a live special: a fullwidth `\input{/etc/hostname}`
  was read into the PDF, a fullwidth `\end{document}` cut the paper short. The fold result is
  now escaped like any text; the fullwidth backslash prints as `\textbackslash{}`. The
  curated map (subscripts, relations, Greek, the micro sign) still runs first, unchanged.
- **Control characters.** C0 controls other than tab and line feed, and DEL, are removed
  and line ends normalized (`_clean_text`) before any match, so a key, a heading text, the
  title or the author cannot carry one and the abstract refusal sees what the sanitizer
  sees. C1 controls become `?` through the fold.
- **One paragraph per key.** A `\ref`/`\cite` key, like a heading text, may hold a line break
  but no blank line; `\citep{a,<blank line>b}` stays literal text.
- **`\eqref` removed** from the list: prose holds no equation, and a figure-less draft loads
  no amsmath, so it could never resolve.
- **One warning rule.** Every backslash the sanitizer printed as `\textbackslash{}` before a
  command name gives one warning per slot and command, naming what passes; fact macros and
  novelty markup are substituted first and never warn.
- **Title and author on one line** (whitespace runs collapsed; also the authored SI's titles):
  a blank line in `\author{}` stopped pdflatex. `sci-adk run` now exits 2 with the message on
  a refused prose slot, as `render` did.

## 4e. Keys, glyph-less letters, the bib copy, macro arguments (2026-10-12)

A second hostile pass found the same class in four more places (pinned in
`tests/test_latex_keys_and_bib_escapes.py`, pdflatex and bibtex builds included):

- **Keys are whitelisted.** A `\ref`/`\cite` key passed whatever it held except braces and
  a blank line, and TeX reads a key inside `\csname`: `\ref{\input <file> }` ran the
  `\input`, and `%`, `#`, a backslash or a non-ASCII letter in a key stopped pdflatex. A
  key now holds only ASCII letters, digits, spaces, `: _ . , ; + / = @ -` and single line
  breaks; any other key stays literal text and is warned about.
- **Eight letters without a glyph.** Ħ ħ ĸ Ŀ ŀ ŉ Ŧ ŧ lie in the passthrough window but
  stopped pdflatex under both preambles; they now take the fold/placeholder path. The prose
  sanitizer and the bib copy share the set (`paper._UNDEFINED_LATIN_A`).
- **The bib copy.** It kept a compatibility fold's ASCII raw, so a fullwidth
  `\input{<file>}` in a bib title was read from the `.bbl`. The fold is now written as text
  (braces as `\textbraceleft{}`/`\textbraceright{}`, boxed in math) and ASCII control
  characters are dropped. [Superseded by §4h: the copy no longer keeps commands as acquired,
  and verify judges it against the allow-list there. As written on 2026-10-12: commands were
  copied as acquired, and verify named every control word outside a closed list of known
  ones and `^^` in math, which the copy writes as two printed carets.]
- **Macro arguments on one line.** A blank line in a claim statement stopped the record's
  `\subsection{}`; every free text or id the renderers put in a macro argument (record
  `\item[...]`, `\texttt{}`, table cells, figure captions and axis labels) is now one line.

## 4f. Headings, figure files, DOIs, bib commands (2026-10-12)

A third hostile pass (pinned in `tests/test_latex_sanitize_round3.py`, pdflatex and bibtex
builds included):

- **Heading text on one line.** A `\paragraph{...}` heading was judged on the text as
  written and folded afterwards, so a line holding only U+00A0, U+3000, U+2003 or a lone
  combining mark passed the blank-line rule and folded to a blank line ("Paragraph ended
  before \@sect was complete", in all seven section and record slots). A heading that passes
  is now written on one line.
- **Image figure width and extension.** Both went into `\includegraphics[width=...]{figures/
  fig<N><ext>}` as written; either could close the command and `\input` a file. A width is
  now a TeX length (`8cm`, `100pt`) or a factor of `\linewidth`, `\textwidth` or
  `\columnwidth`; an extension is a dot and 1 to 8 ASCII letters or digits. Anything else is
  refused when the figure spec is read (render exits 2). A plot point's x must be finite.
- **DOIs without a bibliography.** The no-`.bib` References list wrote each recorded DOI
  into `\url{https://doi.org/<doi>}` as written; `10.1/x}\input{<file>}%` read the file. Only
  a value of the DOI form (`10.`, 4 to 9 registrant digits, `/`, a suffix of printable ASCII
  without spaces, braces, backslash, `%`, `#` or `^`) is cited now; any other is left out and
  named in a render warning with where it was recorded. Leaving it out, rather than printing
  it as text, keeps a value that cannot resolve at doi.org out of the reference list.
- **Bib commands: a deny-list.** [Superseded by §4h: the deny-list could not be closed and
  is gone from the bibliography gate.] As written on 2026-10-12: verify failed only a command
  that can read or write a file, define a macro, change how TeX reads its input, run code
  later, stop the run or reach the engine, and `^^` notation; any other unknown command was
  advisory. What still holds: the check runs on every bibliography render writes
  (`paper/`, `references_SI.bib`, `paper/deposit/`) with or without `pubreqs.json`.
- **Entities in bib math.** An HTML entity decoded inside `$...$` became a text command
  (`&#92;` gave `\textbackslash{}`), which stops pdflatex in math; the decoded character is
  now boxed (`\mbox{\textbackslash{}}`), except `<` and `>`, which stay relations.
- **Warnings.** A literal-command warning is one short line per slot and command; what a
  prose slot passes is stated once per render. A character the sanitizer prints as `?`
  (CJK, emoji, Ħ ħ ĸ Ŀ ŀ ŉ Ŧ ŧ) is named by codepoint, one line per slot, title and author
  included. The writer guidance (`PaperProse`/`SIProse` docstrings, the CLI help, the
  expert-writer agent, the publish skill) now says to write a symbol as its Unicode character
  or in plain ASCII, not as LaTeX.
- **Authored SI body.** The body of an authored `si.tex` section stays verbatim LaTeX, cleaned
  only of control characters and normalized line ends before its fact macros are substituted.
- **Record bibliography.** Whether the record names `references.bib` is read from its closing
  lines (`\bibliographystyle{plainnat}`, `\bibliography{references}`, `\end{document}`), so a
  reproduction listing holding `\bibliography{references}` no longer counts.
- **Reproduction listing and package record.** The listing caption and the pointer line's
  `\texttt{}` id and code reference are one line. The package's `make_si.py` escaped only five
  specials and kept the narrative title raw; it now carries a copy of the renderer's one-line
  sanitizer (it runs where sci-adk may not be installed), applied to every field it prints,
  the title included, and the test suite compares the copy with the renderer.

## 4g. What BibTeX prints, listings, the package skeleton (2026-10-12)

A fourth hostile pass (pinned in `tests/test_latex_sanitize_round4.py`, pdflatex and bibtex
builds included):

- **Recorded strings in the authored SI.** A recorded string cited with `\evval` went into
  the authored `si.tex` body as written, and nothing sanitizes that body afterwards:
  `sample_A` stopped pdflatex and `x}\input{<file>}%` read the file. A recorded string is now
  sanitized as it is substituted there; numbers and verdicts are written as before.
- **The bib checks read the file as BibTeX does.** They read only `@type{key,` bodies, while
  BibTeX also prints `@preamble` text, `@string` values (also a macro named like an unprinted
  field, `title = abstract`), parenthesised entries, `@ article{...}` and values holding
  `@word{`; each read a file through the reference list. `bib_latex.bib_commands` now reads a
  `.bib` with BibTeX's rules (no `%` comments, `@comment` is a word, after a syntax error the
  next `@`), and the checks scan every entry, `@string` and `@preamble` it returns. A
  `@preamble` fails, and render's copy leaves every one out. A `url` or `doi` value, a macro
  one names and the URL argument of `\url`/`\href` fail on a backslash, `^^`, a brace or a
  `run:`/`file:` link: hyperref reads a URL as TeX. An accented letter in bib math is written
  as boxed accent commands. [Superseded by §4h: `\bibitem` on a deny-list, `\hbox` and
  `\upmu` as advisory unknown commands, and a math command in running text as an advisory;
  the reading of a `.bib` as BibTeX reads it still holds, and the copy is now built from it.]
- **Reproduction listings.** A script is typeset only when its body is printable ASCII, tabs
  and line feeds with no line over 2000 columns (a UTF-8 comment, a control character or a
  3000-column line stopped the record); any other is shipped and named.
- **Package skeleton.** `main.tex` escaped record text with five specials only; it now uses
  render's one-line sanitizer, and `reference_style` must be a BibTeX style name.
- **Figures.** An image is one of `.pdf .png .jpg .jpeg .eps` (any case, written in lower
  case); a width is at most 1000pt or 10 times a text width; an axis label at most 200
  characters (pgfplots cannot break one).
- **Bibliography not UTF-8.** Render exited 2 after writing the paper; the store is copied as
  before and render says it is not UTF-8. The authored SI body names in a render warning each
  character pdflatex cannot typeset there.

## 4h. The bibliography is a canonical copy holding allow-listed commands (2026-10-20)

This section replaces the bibliography parts of §4e, §4f and §4g. Pinned in
`tests/test_bib_allowlist.py` and `tests/test_render_round5.py` (pdflatex and bibtex builds
included).

Independent checkers showed that a list of forbidden commands over the bibliography copy could
not be closed: a command split across BibTeX `#` parts or `@string` macros was never seen by a
scan of the parts but BibTeX joins it; BibTeX's `change.case$` lowercases a title at brace level
0, so `\INPUT{...}` reached the reference list as `\input`; expl3, `\expandableinput`, pdfTeX
link actions, hyperref form fields and `\typein` were not on the list; `\(`, `\[` and commands
the figure-less preamble does not define (`\mathbb`, `\text`, `\operatorname` ...) stopped
pdflatex while verify was silent; a name holding `[` broke natbib's author-year label.

The design: render and verify judge the same text.

- **Render writes a canonical copy.** `bib_latex.paper_bib` reads the store as BibTeX reads it
  (`bib_commands`: braces or parentheses, `@string` macros with the predefined `jan`..`dec`,
  `#` parts joined, macros expanded in file order, `@preamble` and `@comment` dropped, after a
  syntax error the next `@` BibTeX would read) and writes every entry as
  `@type{key, field = {value}, ...}`: one braced value per field, no `@string`, `@preamble`
  or `@comment`, nothing between entries. Fields no style prints, the ISSN, and a url that is
  the entry's own doi.org link are left out; a bare month macro stays a macro. So `abstract`,
  `keywords`, `copyright` and the other `UNPRINTED_FIELDS` are left out of every shipped copy
  (the literature store keeps them; the bibliographies under `~/research` hold 25 `keywords`
  and 24 `copyright` fields, which the verbatim copies of earlier renders carried).
- **A value holds only allow-listed commands.** Each value is read as TeX tokens. The
  commands kept (`bib_latex.TEXT_COMMANDS`, `MATH_COMMANDS`) are accents and letters, the
  escaped specials, the text symbols publisher metadata carries, simple markup and font
  declarations, `\url`/`\href` with a plain URL, and a math set defined without amsmath. A
  test compiles each of them under the four preambles render emits (draft and record, Latin
  Modern without figures and Times with them). Every other control word or symbol is printed
  as text (`{\textbackslash}name`, boxed in math); balanced `\( ... \)` and `\[ ... \]` become
  `$ ... $`, unbalanced ones are printed; `^^` never survives. Each kept command and its
  arguments sit in one brace group, which BibTeX treats as one special character, so its case
  change cannot alter the command; math is written `{$...$}`. A math command in running text
  is put in math; a text command in math in an `\mbox`. `[` and `]` at brace level 0 are
  braced. Titles keep their case and names are tidied as before.
- **url, doi, keys.** A url is kept only when it is http, https or ftp with printable ASCII and
  no white space, backslash, brace, `%`, `#` or `^`; a doi only in the DOI form (a doi.org
  prefix is dropped). Any other is left out and named in a render warning with the entry key,
  and so is an entry whose key a citation cannot name and a repeated key (BibTeX keeps the
  first). The SI subset and the package's SI cut are taken from the canonical copy.
- **Verify.** Every bibliography sci-adk ships (`paper/references.bib`, `references_SI.bib`,
  the `paper/deposit/` copy, the package SI cut) fails unless it is the canonical copy itself
  (`paper_bib(text) == text`) and holds only allow-listed commands; each line names the entry
  key and what differs. A package bibliography the author supplied gets the allow-list check
  (judged on its values as BibTeX prints them, macros expanded), and there a math command in
  running text or a text command in math fails too (the copy moves them; the author's file
  would stop pdflatex). There are no bib advisories for unknown commands any more: what is not
  on the list fails. A superscript or subscript the copy rewrites so that it compiles fails it
  too (`bib script:`, §4k), so the author's bibliography gets the same compile rules as the copy
  for what the writer judges, not only the command allow-list.
- **Measured** (2026-10-21, after §4i and §4j) over the 136 bibliographies under `~/research`
  (985 entries): the copy keeps every key, is idempotent and passes the form and command
  checks. Render gives 12 warnings: 10 names in one entry that end with a comma (BibTeX stops on
  them; the copy writes them without it, §4i), one entry holding U+FFFD (kept, and named by
  verify) and one entry with a BibTeX syntax error (none of its fields kept). No url, doi or
  entry is left out and no command is printed as text. Two copies differ from the ones the
  §4i code wrote, each by a braced parenthesis in a name (`European Food Safety Authority
  {(}EFSA{)}`, `Li, Ang {(}Leo{)}`, §4j).

**Author-written LaTeX is outside the guarantee.** The guarantee above covers the text sci-adk
writes from the record and from external metadata. The body of an authored SI section and a
package `main.tex` / `si.tex` the author supplies are written as the author wrote them; sci-adk
does not judge what that LaTeX does. A lint (`render/latex_lint.py`) names the commands in it
that read or write files or run code (`\input`, `\include`, `\InputIfFileExists`,
`\expandableinput`, `\scantokens`, `\write`, `\immediate`, `\openout`, `\openin`, `\read`,
`\ExplSyntaxOn` and expl3-shaped names, `\directlua`, pdfTeX primitives, hyperref form and
action commands, `\typein`, `\special`) in a render warning and a verify advisory. It never
fails a run.

Other defects closed in the same pass: `sci-adk verify` prints why a run without `pubreqs.json`
fails; a CSV cell is written raw as a number only in ASCII; a claims-table row starts with `{}`
so `\\` cannot read a `[` as its option; a record label cuts an id over 200 characters (shown
whole, breakable, in the item, and named in a warning); an image must be the format its
extension names; a .tex line over 10000 characters is broken at white space; a script the
record cannot typeset is one line naming why, its `paper/code/` path and its SHA-256, and render
says once which scripts it showed by name only.

## 4i. What BibTeX and pdflatex do with the remaining edge cases (2026-10-21)

Pinned in `tests/test_bib_round6.py` (bibtex and pdflatex builds included). Independent checkers
found places where the copy or its checks still parted from BibTeX or pdflatex. Each is closed
as follows; every change is a render warning naming the entry key.

- **The reader after an error.** BibTeX stores a `@string` macro's name as its text before it
  reads the value, so a definition that fails defines the macro as its own name, in lower case.
  It reads nothing after the key of an entry that repeats an earlier key (ASCII case ignored)
  and looks for the next `@` from there. `bib_commands` reads both the same way. A test runs
  BibTeX, with a style that writes every field of every entry, over 260 mutated bibliographies
  and checks that every value BibTeX prints is one the reader reads. An author's package
  bibliography with a syntax error, a repeated key or a macro no `@string` defines fails verify
  (`bib syntax:` lines): what BibTeX prints after an error depends on how it recovers.
- **Limits.** Braces nested more than 50 deep give an empty value (TeX has 255 grouping levels;
  254 stopped pdflatex). Text accents nest at most 3 deep and deeper ones are printed as text
  (each level doubled pdflatex's time; 22 levels took 17 s). A run of more than 10000 characters
  without a space gets one (TeX reads lines of at most 200000 characters, and BibTeX breaks a
  line only at a space). A value written longer than 100000 characters is cut (BibTeX's string
  pool holds 200000). A url longer than 4000 characters is not kept.
- **Math.** Every script argument is braced, and a second script of one kind on one base gets an
  empty base (`x^2^3`, `x^\hat{y}` and `x^\int` stopped pdflatex). Empty math is left out (`$$`
  opens display math). A character outside ASCII in math is written in its math form, as boxed
  accent commands, or boxed. ~~`\not` always gets an argument (newtxmath defines it with
  one).~~ (Superseded by §4j: `\not` is kept only before one plain symbol.) A test compiles every
  allow-listed command as `x^NAME`, `x_NAME` and `x^NAME^2` under both typefaces.
- **natbib's label.** A year is written as plain text, at most 40 characters (a command, math or
  a group there stopped natbib with "Improper alphabetic constant"). A name with more than two
  commas, or ending in a comma, is braced as one name (BibTeX: "Too many commas in name"). A last
  name longer than 100 characters is shortened (the label is one BibTeX entry string, 250
  characters by BibTeX's default; past it the label lost its year and natbib stopped).
- **Types, cross references, keys.** An entry type other than the 14 BibTeX ones is written
  `misc`, as a style prints it (`@output` and `@and` are function names in plainnat, and BibTeX
  stopped). A crossref to an entry the copy lacks is left out; an SI subset keeps the entries
  its entries cross-reference. A key may hold the Latin letters pdflatex typesets
  (`Müller2019`; `\citep` reads it under both preambles), after its first character (§4k).
- **Fixed point.** The copy writes each value again until that changes nothing, so a file render
  wrote is one verify accepts (the checkers had found one random value in ten that changed when
  copied again). A test copies 2500 values built from TeX fragments twice.
- **Characters with no LaTeX form** are kept, so a reference never silently loses a letter;
  render names each and verify fails it, with or without a publishing contract. A line or
  paragraph separator becomes a space.
- **Package SI bibliography.** verify holds `01_manuscript/references_SI.bib` to the canonical
  form only when the assembler cut it (its MANIFEST.md line says so); one written in place, or
  supplied in `package_src/`, gets the allow-list check. Its form line says to re-assemble the
  package or to supply the file in `package_src/`. A per-run copy's form line names the full
  re-render, with the `--prose`, `--si`, `--si-prose` and `--figures` inputs of the last render
  (the deposit declaration is kept; a bare `sci-adk render` writes a skeleton draft).
- **An author's bibliography** is checked for commands in every field, not only in those plainnat
  prints (the author's style may print `annote`).
- **Lost fields.** An entry a syntax error cut short is named, with how many fields were kept.

## 4j. Labels, `\not`, scripts, accents and an author's case change (2026-10-21)

Pinned in `tests/test_bib_round7.py` (bibtex and pdflatex builds, every key cited by `\citep`
and `\citet`, under the four preambles of §4h). Independent checkers found six more inputs on
which the copy, its own fixed point, stopped pdflatex in the draft, the SI and the record while
render and verify said nothing. Each is closed as follows.

- **natbib's label.** plainnat writes `\bibitem[<label>(<year>)]` and natbib reads it back up to
  the first `(` at brace level 0 as the names. A `(` there followed by a command, a group or a
  letter outside ASCII stopped it ("Improper alphabetic constant"), so the copy braces `(` and
  `)` at brace level 0 of an author, editor or key field, as it braces `[` and `]`.
- **Three-character labels.** An authorless `@manual` or `@proceedings` is labelled by the first
  three characters of its organization (`"The "` dropped), and an entry with no author, editor,
  key or organization by the first three bytes of its citation key. Those cut `AT\&T` to `AT\`,
  `$\alpha$` to `$\a`, a letter outside ASCII in two, or hold a `_`, and pdflatex stopped. Where
  they would, the copy writes a `key` field: the first three letters, digits and spaces of the
  organization, or the key's first three characters as text (`a\_b`). natbib then cites the
  entry by that key without a year, as plainnat cites any entry that has a key; an entry whose
  three characters are plain keeps plainnat's label and year. An entry with a crossref is judged
  with what it inherits. A key field is at most 100 characters (BibTeX cut a longer label,
  braces and all).
- **`\not`.** newtxmath's `\not` reads one plain symbol; before anything else (a box, a command
  with arguments, an empty group, nothing) it looped ("TeX capacity exceeded"). The copy keeps
  `\not` only before one ASCII letter, digit or `=<>|+-:/()[]!`, or one `zero` math command, and
  writes it `\not{X}`; any other is printed as text. A test compiles `\not` before every `zero`
  command under both typefaces.
- **Scripts.** A math font declaration (`\rm \it \bf \sf \tt`) is an assignment, not an atom, and
  so is a token the copy drops: a script after one still belongs to the atom before it, and the
  copy gives a second script of one kind an empty base there too (`x^2\rm{}^3`).
- **Accents.** LaTeX's T1 accents read their argument's first item inside `\csname`: an empty
  group there stopped pdflatex ("Missing \endcsname inserted"), and so did a group holding a
  command after its first token. The copy drops the braces around the whole argument when that
  gives one that compiles (`\~{{}}` -> `\~{}`, `\"{{\foo}}` -> `\"{{\textbackslash}foo}`) and
  otherwise prints the accent as text. Both count as a fix an author's bibliography fails on.
- **An author's bibliography.** It is not rewritten, so verify fails what BibTeX or natbib stop
  on though every command in it is allowed (`pkgreqs_checks.bib_label_problems`): the label
  shapes above, a bracket in the names or key a label holds, a year that is not plain text
  (`bib label:`); a command with a capital letter, or a capital in math, at brace level 0 of a
  title, edition or type, the fields the TeX Live styles change the case of (BibTeX writes
  `\LaTeX` as the undefined `\latex`, `$\Delta$` as `$\delta$`: `bib case:`, fixed by braces); a
  key a citation cannot name and a type named like a function of the standard styles
  (`@output`: `bib entry:`). A value longer than BibTeX holds fails too.
- **Time.** A chain of `@string` macros each doubling the last is joined to at most 200000
  characters (27 doublings would be 2^29 characters; an entry field cut there is noted), and
  markup tags are paired in one pass (200000 unclosed `<i>` took minutes).
- **verify's form line** names the re-render once per file, not on every entry line.
- **The reader.** On the file's last line BibTeX reads only the first command (a `@string` and
  an entry there gave no entry) and drops what follows a syntax error; the reader reads all of
  it, so it reads more than BibTeX there, never less. A test diffs the two both ways for files
  with no syntax error and a last line without a command.

Left open: more than 26 cited entries sharing one label make plainnat's year letters run past
`z` (`{`, `|`, `}`) and natbib stops; in the bibliographies under `~/research` at most 3
entries of one file share a label. (Closed in §4k: a warning and a verify line, no rewrite.)

## 4k. Links, nesting, keys, script errors and file size (2026-10-21)

Pinned in `tests/test_bib_round8.py` (pdflatex and bibtex builds under both typefaces, every key
cited, build times bounded). Independent checkers found inputs that stop pdflatex or BibTeX, or
keep pdflatex busy for minutes, while render exits 0 and verify says nothing. Measured with TeX
Live 2026 under both preambles render emits.

- **Links.** hyperref keeps at most 10 links open: 11 nested `\href`, or 10 and a `\url` inside,
  in a title, note or howpublished stopped pdflatex ("TeX capacity exceeded, sorry [pdf link
  stack size=10]"). The copy never keeps a link command (`\href`, `\url`) inside another; the
  inner one is printed as text, with a render warning. An author's bibliography fails on it.
- **Nesting and count.** A `\sqrt` with an index and the arrow accents (`\overrightarrow`,
  `\overleftarrow`) typeset their argument four times (`\mathpalette`), so pdflatex's time grows
  fourfold with each level: `\sqrt[3]` 12 deep took over 120 s a pass, `\overrightarrow` 10 deep
  39 s, 49 deep ran out of grouping levels; 4700 arrow accents in one reference took 24 s a pass
  (1000 took 0.6 s); `\textsuperscript` about 37 deep made the type so small that pdflatex
  stopped ("Improper `at' size"). Other math commands with arguments, 2000 in a paragraph, took
  under 0.4 s. The copy keeps math commands with arguments at most 4 deep in all, never an arrow
  accent inside an arrow accent and never a `\sqrt` with an index inside a `\sqrt`; text markup
  at most 8 deep; and at most 32 math commands with arguments in one value (counted in reading
  order before the walk, so the count does not depend on what is written first). Past a limit
  the command is printed as text and what follows it is written as it stands; each is a render
  warning, and an author's bibliography fails. The values under `~/research` hold no math
  command with arguments.
- **Keys.** A `\cite` whose first key starts with a character outside ASCII stopped pdflatex
  under both preambles ("Missing \endcsname inserted"; the cedilla and ogonek letters "Illegal
  parameter number"); the same key after a comma, and a letter outside ASCII later in a key,
  compiled. A key of 100000 characters overflowed TeX's buffer; 1000 compiled. The copy leaves
  out an entry whose key starts with a character outside ASCII (the warning suggests an ASCII
  key, `Önal2019` -> `Onal2019`) or is longer than 200 characters. Every first character the
  copy keeps is cited by `\citep`, `\citet`, `\cite` and `\citeauthor` in a test.
- **Names.** BibTeX reads `-` and `~` as separators inside a name, so `Doe, -`, `Doe,--` and
  `Doe, J, ~` end in an empty part ("has a comma at the end", exit 2). The copy writes the name
  without that tail.
- **Labels.** plainnat tells entries with one label (the first author's last name, or two, or
  "et al.", and the year) apart by a letter after the year; the 27th gets `{` and natbib stops
  ("Paragraph ended before \@lbibitem was complete"); 26 compile. More than 26 entries with one
  label are a render warning; verify fails when the manuscript that loads the bibliography cites
  more than 26 of them and gives an advisory when it cites fewer. The copy is not rewritten:
  which of the entries a paper needs is the author's call.
- **Scripts.** The copy braces every script argument and gives a second script of one kind on a
  base an empty base. Now that is a signal too (`bib_latex.script_issues`): an author's
  bibliography fails with a `bib script:` line on each place the copy rewrites -- a second script
  (`x^2^3`, `x_1_2`, `x^{2}^{3}`, `x^2'`, `x' '`), a script with nothing to take (`x^$`), and an
  argument pdflatex takes only in braces: a math command measured to stop pdflatex unbraced
  after `^` or `_` in either preamble (`bib_latex._SCRIPT_UNSAFE`: `\hat`, `\sqrt`, `\cdots`,
  `\log`, `\rm` ...; a test compiles every other math command unbraced), `\, \; \: \!`, `~`,
  `'` and a letter outside ASCII. `x'^2`, `x''` and `x^\alpha` compile and pass; the copy no
  longer gives `x'^2` an empty base (TeX joins a prime and the superscript after it), and gives
  one to a prime after a space (`x' '` and `x' ^2` were double superscripts).
- **File size.** The checks read a file once (the reading of the last few files is remembered)
  and count lines as they go; before, each check read it again and counted lines from the start
  for each entry, so 100000 `@string` macros did not finish in 120 s, 50000 repeated keys took
  51 s and a 3 MB copy 31 s. They read at most 5000 commands of a file (entries, `@string`,
  `@preamble`); a file with more fails with a `bib size:` line and its first 5000 are checked
  (the form check is left out then). A paper's bibliography holds far fewer.

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
