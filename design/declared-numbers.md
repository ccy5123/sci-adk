# Declared numbers: binding every number in a paper to its source

> Status: **v0.1 DRAFT (2026-10-09)** — design only; nothing here is built.
> Replaces, when adopted, the pattern-based number audit of
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

## 7. Open decisions

1. Opt-in now and required later, or required at once for papers rendered after this
   ships (OD-8 chose immediate refusal for P2 itself).
2. Identifier entries: unconstrained but listed (proposed), or limited to shapes such as
   hyphen-joined groups (reintroduces a pattern).
3. The `draft` helper in the first phase (proposed) or later.
4. Whether the blind conclusions reviewer (§11.4 of reader-facing-prose) also receives
   the identifier list.

---

Version: 0.1
