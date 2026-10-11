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
  characters are dropped. Commands are still copied as acquired, but verify names every
  control word outside `bib_latex.SAFE_COMMANDS` (accents, letters, markup, symbols, common
  math) and `^^` in math (TeX's character-code notation), which the copy writes as two
  printed carets.
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
- **Bib commands: a deny-list.** Verify failed every command outside a closed list of known
  ones, which refused harmless publisher commands (`\texttimes`, `\MakeUppercase`,
  `\hspace`). It now fails only a command that can read or write a file, define a macro,
  change how TeX reads its input, run code later, stop the run or reach the engine
  (`bib_latex.DANGEROUS_COMMANDS`), and `^^` notation in text or math; any other unknown
  command is advisory. The check runs on every bibliography render writes (`paper/`,
  `references_SI.bib`, `paper/deposit/`) with or without `pubreqs.json`, and render names a
  dangerous command in the bibliography it writes. Measured: 0 failures and 0 advisories over
  the 131 bibliographies under `~/research`, raw and copied.
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
  `run:`/`file:` link: hyperref reads a URL as TeX. `\bibitem` is on the deny-list; `\hbox`
  and `\upmu` are unknown commands (advisory); a math command in running text is advisory; an
  accented letter in bib math is written as boxed accent commands. Measured: 0 failures and 0
  advisories over the 131 bibliographies under `~/research`, raw and copied.
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
