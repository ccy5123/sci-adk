# Declared numbers: binding every number in a paper to its source

> Status: **v0.2 (2026-10-09)** — §7 decided; phase 1 (the per-run list) built, see §8.
> The package stage (§5, second paragraph) is phase 2 and not built.
> Replaces, per run that adopts it, the pattern-based number audit of
> `design/paper-writing-enforcement.md` (P2, OD-2/OD-3). Mirrors the conclusion
> declaration list of `design/reader-facing-prose.md` §11.3.

## 1. The question

A manuscript must state only numbers the record holds (P2). Today a checker guesses, for
every digit run in the paper, whether it is a reported quantity or something else (a year,
a page, an identifier), and then looks the quantities up in a pool of recorded values. Can
that guessing be made reliable, or does each new paper need another rule?

## 2. What the first full paper showed (run SPEC-BCFKOW-001, 2026-10-09)

The paper session drafted a 2,500-word manuscript from the record and, before rendering,
ran sci-adk's own tokenizer and pool over it. Of roughly 80 numbers
(`drafts/SPEC-BCFKOW-001/paper/unbacked-numbers.md` in that workspace):

| Outcome | Count | Examples | Cause (`src/sci_adk/render/number_audit.py`) |
|---|---|---|---|
| backed by a recorded value | — | 0.769, 0.618, 0.712 | Result scalars and rule thresholds |
| rejected, though the record states them in prose | about 50 | 341 chemicals, 13 records, 95 (of 95% CI) | a finding enters the pool only when it is JSON (`pool_from_record`) |
| passed only by coincidence | about 20 | 0.678 (R²), 0.60, 0.85 | derived policy: any sum, difference, product or ratio of two pool values (`RecordedValuePool.backs`) |
| never checked: read as a year | 4 | 6973, 2393 records | `_YEAR_RE` drops every 4-digit integer, not only years |
| never checked: read as a page | 1 | 47 (in "P 47") | `_PAGE_RE` is case-insensitive and needs no period |
| rejected identifiers | 4 literals | CAS RN 17109-49-8 → 17109, 49, 8; "criterion-5" → 5 | hyphenated digit groups split into numbers |
| range misread | — | 0.712–0.826 → −0.826 | an en dash between numbers read as a minus sign |

Counts are from that list, which records each number once under the item that computes it.

The rows below the first two are the problem. Five numbers were never checked, and about
twenty passed for a reason unrelated to the record. A checker that passes a number it did
not verify is worse than one that rejects a number it should have accepted.

## 3. Why another rule will not fix it

Whether "47" is a quantity depends on the sentence: a page in "p. 47", a prime in "P 47",
a count in "47 chemicals". Whether "2393" is a year or a count, whether "17109-49-8" is
one identifier or three numbers, whether "0.60" is the paper's result or a value quoted
from another study — each is decided by context, and contexts differ by field (gene names,
registry numbers, model versions, coordinates, formulae). Every rule added for one case
moves errors between the two columns that matter: rejecting real numbers, or silently
passing them. The derived policy has the same shape: widening it backs real derived values
and coincidences alike.

A deterministic checker cannot read context, and no language model may sit on the verdict
path. So the role of each number has to be stated, not inferred.

## 4. Design: a number list beside the paper

The conclusion declarations already work this way: the author states which sentence
carries which verdict; the machine checks the statement against the record and the text,
and reads no meaning. Numbers get the same treatment.

### 4.1 The file

`runs/<id>/numbers.json`, beside `declarations.json` (outside `paper/`, so render never
overwrites it; not frozen; revised with the paper; never submitted).

```json
{
  "spec_id": "SPEC-BCFKOW-001",
  "numbers": [
    {"text": "0.769", "document": "draft.tex",
     "source": {"evidence": "evi-run-20261008-h1-primary-fit", "field": "effect_size"}},
    {"text": "341",
     "source": {"evidence": "evi-obs-…-h1-counts", "field": "finding.n_chemicals"}},
    {"text": "0.5", "source": {"spec": "hypotheses[1].decision_rule.params.value"}},
    {"text": "95",  "source": {"spec_text": "hypotheses[0].decision_rule.expression"}},
    {"text": "2006", "role": "citation", "source": {"bib": "Arnot2006", "field": "year"}},
    {"text": "17109-49-8", "role": "identifier"},
    {"text": "0.157", "role": "derived", "formula": "a - b",
     "operands": {"a": {"evidence": "…", "field": "effect_size"},
                  "b": {"evidence": "…", "field": "finding.slope"}}}
  ]
}
```

Roles:

- **recorded** (default when a `source` is given): equals a recorded value. Sources:
  an Evidence field (`point`, `effect_size`, `ci[0]`, `ci[1]`, `p_value`, `posterior`,
  `finding.<key>`), a numeric field of the frozen Spec (`spec`, a JSON path), or a digit
  literal inside a Spec text field (`spec_text`: the literal must occur as written in that
  field — not anywhere in the Spec, which is how a "3" passes today against an unrelated 3).
- **derived**: computed from named recorded values by a stated formula (`+ − × ÷`, a
  constant factor such as `100 * a` for a percentage). Replaces the derived policy: one
  declared computation instead of every pairwise combination.
- **citation**: a year or other field of a cited reference, checked against
  `references.bib`.
- **identifier**: not a quantity (a registry number, a version, a label written in prose).
  Not checked against anything; listed by `verify` so a reader sees every exemption.

`context` (optional): a quoted fragment, needed only when the same `text` has two roles
in one document; it locates the occurrences it covers, as declaration quotes do.

### 4.2 What the checker still does on its own

Tokenizing stays, but only to find numbers, never to judge them. It keeps the exemptions
LaTeX itself defines — arguments of `\ref`, `\cite`, `\label`, `\input`,
`\includegraphics`, comments, and the verbatim spans `\texttt`, `\url`, `\href`, `\path`
(the author's own markup for code and identifiers) — and two lexical rules that do not
depend on the field: digits joined by hyphens without spaces form one literal
(`17109-49-8`, `2026-10-08`), and an en dash or `--` between two numbers separates a range
rather than negating the second. Digits in a superscript or subscript (`R$^2$`,
`H$_2$O`, produced from Unicode by the renderer) are not literals.

Removed: the year, page, date and version rules; the derived policy; the ±0.005 / 1 %
tolerance window; Claim confidence values in the pool.

### 4.3 Checks (`sci-adk verify`)

1. **Coverage** (fail): every literal in `draft.tex` and `si.tex` is in the list.
2. **Resolution** (fail): every source exists, and the recorded value rounded to the
   printed precision of the literal equals it (0.769 matches 0.768932; 0.77 matches it;
   0.768 does not). Integers match exactly. A derived entry is recomputed from its
   operands and compared the same way. A citation year must equal the bib field.
3. **Stale entries** (advisory): a listed literal no longer in the document.
4. **Identifiers** (advisory): every identifier entry is printed, so exemptions are seen.

Nothing in the list is trusted on its own: a source must resolve to the record, and only
identifier entries skip the record, visibly.

### 4.4 Who writes what

- The **experiment stage** records every count, constant and quoted literature value the
  paper may state as structured values in the Evidence `finding` JSON (the pool already
  reads it). The workspace instructions do not say this today; that is why the first paper
  found its counts only in prose. Values quoted from other studies belong in the
  contested-literature record's finding, where they were first read.
- The **paper session** writes `numbers.json` with the manuscript. It may not add record
  values; a number with no recorded home goes back to the experiment stage.
- A helper, `sci-adk numbers draft <run>`, proposes a source for each literal by exact
  printed-precision match and marks the rest unresolved; ambiguous matches are listed, not
  chosen. Deterministic, no model. It saves effort; the author's choices are what is checked.

## 5. Migration

Opt-in per run, like the declaration list: a run with `numbers.json` is checked by §4.3
instead of the pattern audit; a run without one keeps today's audit unchanged and gets an
advisory recommending the list. No existing run changes verdict. Making the list required
is a later decision (§7).

The package stage (merged `main.tex`, `02_data/*.csv`, exact-only audit) follows in a
second phase: the same schema with run-qualified sources and data-cell sources.

## 6. Not proposed

- More patterns or exemptions in the tokenizer (§3).
- Classifying numbers with a language model (verdict path).
- Binding numbers with macros in the submitted source (rejected by OD-7: reviewers read
  the `.tex`).

## 7. Decisions (taken 2026-10-09)

1. **Opt-in per run.** A run with `runs/<id>/numbers.json` is checked by §4.3 instead of
   the pattern audit; a run without one keeps the audit byte for byte and gets one
   advisory line recommending the list. No existing run changes verdict. Making the list
   required stays a later decision.
2. **Identifier entries are unconstrained** and every one is listed by `verify`
   (advisory). No shape rule.
3. **The `draft` helper is in phase 1.**
4. **The blind conclusions reviewer receives the identifier list** and may note any
   identifier that reads, in its sentence, as a reported quantity. Advisory only.
   (Its cold reading of the opening goes to a separate `opening_notes` list in the same
   `review.json`, which `verify` prints beside these `notes`, also advisory.)

## 8. Phase 1 as built

Code: `src/sci_adk/core/numbers.py` (schema, loader, JSON paths, safe formula
evaluator), `src/sci_adk/render/number_literals.py` (tokenizer),
`src/sci_adk/render/number_checks.py` (§4.3 checks), `src/sci_adk/render/number_draft.py`
(helper), wired in `src/sci_adk/loop/verify.py` (`number_problems` / `numbers_clean`,
advisories in `paper_advisory`) and `src/sci_adk/cli.py` (`sci-adk numbers draft`, verify
output). The pattern audit (`render/number_audit.py`) is unchanged.

**Schema.** Entry keys are exactly `text`, `document` (`draft.tex` | `si.tex`), `role`,
`source`, `formula`, `operands`, `context`; anything else is rejected, and a load error
names the entry index and its text. The role, when omitted, follows from the entry: a bib
source makes a citation, any other source a recorded value, a formula a derived value.
Choices beyond §4.1:

- `finding.<key>` accepts a path (`finding.counts.total`), the same syntax as `spec`.
- A bib source reads `year` only.
- A derived entry's operands are evidence or spec values (a text occurrence or a year has
  no single numeric value); every operand must appear in the formula and vice versa.
- `spec_text` compares the literal's text with the numbers written in the named field
  (`95` matches "95% interval"; `0.50` does not match "0.5").

**Tokenizer.** As in §4.2, plus these lexical rules, none field-specific:

- Masked as non-prose: comments; the arguments of `\ref`-like, `\cite`-like (with up to
  two `[...]` options), `\label`, `\input`, `\include`, `\includegraphics`,
  `\bibliography(style)`, `\usepackage`, `\documentclass`, `\pgfplotsset`; `\texttt`,
  `\path`, `\url`, `\nolinkurl`, `\verb`, the URL argument of `\href`; macro definitions
  and `#N` (an escaped `\#3` stays prose); the two identifier arguments of `\novelty`;
  the `coordinates {...}` of `\addplot` (plotted values come from the record by Evidence
  id); superscripts and subscripts in math, `\textsuperscript`, `\textsubscript`.
- Section titles and captions are prose (the pattern audit stripped section arguments).
- A minus negates only when unary: not after a digit, letter, underscore or closing
  bracket. So `criterion-5` is the literal 5, and `n - 2` is 2. `-`, U+2212 and `$-$`
  count; a run of hyphens (`--`, `---`) never does.
- A digit run continuing a word (`log10`, `CO2`) is part of the word, as in the pattern
  audit. Digit groups joined by two or more dots are one literal (`2025.09.4`).
- A hyphen-joined range (`1-6`) is one literal with no value; a range needs an en dash.

**Precision.** The slack in `|v - literal| <= 0.5·10^-d` is relative to that tolerance
(`× (1 + 1e-9)`), not an absolute 1e-9, so a literal such as `1.2e-12` is not matched by
every value within 1e-9.

**Helper.** `sci-adk numbers draft <run> [--prose P] [--si S] [--figures F]` reads
`paper/draft.tex` / `si.tex`, or, given the JSON, renders it in memory through
`ResearchCompiler.render_texts` (the same render path, byte-identical to what `render`
writes). All recorded fields are searched together, with no preference between them: one
match fills `source`, several are listed as `candidates`, none is `unresolved`.
Undecided proposals also carry `where` snippets and do not load as entries until decided.
Spec bookkeeping (`id`, `version`, `created_at`) is not searched. The summary names
resolved literals stated more than once, because one entry covers every occurrence of its
text and a second role can hide behind a single match.

**Reviewer.** `review.json` gained an optional `notes` list (`text`, `document`,
`note`); a file without it loads unchanged. Notes reach `paper_advisory` as written.

**Experiment stage.** The experimentalist instructions now require every count, constant
and quoted value a paper may state as a named number in a finding JSON
(`{"summary": ..., "<name>": <value>}`), and `record.tex` renders such a finding as the
summary followed by `key = value`. Values quoted from another study go in an
`observation` naming the study, not the contested-literature record of §4.4: that verb
records a prose note and cannot hold named values.

**Also.** `numbers.json` / `numbers.draft.json` join the internal file names a paper may
not mention (tool-vocabulary check). Nothing reads the run root's JSON files by glob, and
the record digest covers only `spec.json`, `evidence/` and `verdicts/`, so neither file
changes a digest or is mistaken for a record.

**On the first paper (run SPEC-BCFKOW-001, a copy).** From the session's `prose.json`
the helper found 87 distinct literals: 26 resolved, 12 ambiguous, 49 unresolved. Every
unresolved literal is either in section A of that session's list of numbers without a
structured home (42: the filter counts, the fit's intercept, standard error and R², the
residual subsets, the literature values) or an identifier (the three registry numbers and
four software versions). The section-A numbers not marked unresolved are small integers
and literature values that also occur in Spec text or print like a recorded value; three
single matches were coincidences the author must reject: 0.77 (a published slope) matched
the run's own slope 0.768932, and 7 and 8 matched "pH 7" and a SMARTS substructure query
(`[#7,#8,#16]`) in Spec text. 13 matched the prime list although one of its three uses is
a record count. After one observation recorded four counts as named values, 341 and 404
resolved, 13 became ambiguous between its two roles, and 50 gained the recorded count
beside nine Spec text candidates. Rendered with a list of the 27 then-resolved proposals and seven identifiers,
`verify` reported no resolution failure, no stale entry, and 53 coverage failures — the
13 ambiguous and 40 unresolved literals still to decide.

---

Version: 0.2
