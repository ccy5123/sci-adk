---
name: science-workflow-publish
description: >
  sci-adk Stage 4 (publish) workflow knowledge: author the PaperProse / SIProse /
  FigureSpec hooks and render the self-contained paper/ folder via sci-adk render,
  with figures pulling y FROM Evidence by evidence_id (record fidelity), the
  within-doc paper-consistency gate, plain-text cross-doc SI references, body-order
  figure numbering, and Overleaf folder upload. Loaded by the sci hub for /sci publish
  and by expert-writer. Builds on science-foundation-rigor.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob
user-invocable: false
metadata:
  version: "1.0.0"
  category: "workflow"
  status: "active"
  updated: "2026-06-22"
  modularized: "false"
  tags: "sci-adk, publish, render, paper, figures, evidence-id, paper-consistency, si, overleaf"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["render", "paper", "figure", "evidence_id", "paper consistency", "ref label", "supporting information", "overleaf", "record fidelity"]
  agents: ["expert-writer"]
  phases: ["publish"]
---

# science-workflow-publish — Render the Paper (Stage 4)

The publish-stage procedure: render a self-contained `paper/` folder by authoring the
prose/figure hooks and letting the engine render deterministically from the recorded
Spec, Evidence, and Claims. For the discipline (record vs belief, verbs, the verify
gate) load `Skill("science-foundation-rigor")`; this skill is the HOW.

## Quick Reference (30 seconds)

- **Author WHAT, not the bytes.** Author the `PaperProse` / `SIProse` / `FigureSpec`
  hooks; the ENGINE renders the LaTeX deterministically FROM the record. This mirrors
  how the prose hook works — content + intent from the agent, faithful rendering from
  the engine.
- **Figures pull `y` FROM Evidence by `evidence_id`** — you reference the Evidence,
  you do NOT retype numbers into the figure. An unknown `evidence_id` or a
  `None`/`NaN`/`inf` value is a HARD error — that is the record-fidelity guarantee.
- **Main paper = belief narrative; SI = the full record auto-dumped.** Record/belief
  maps onto SI/paper: the SI is the deterministic dump of the record; the main paper
  is the narrative, and every quantitative statement must trace to the record.

## Implementation Guide (5 minutes)

### Author the hooks

- **`PaperProse`** — the main-paper narrative (what the paper claims and why). It must
  match the DERIVED Claim statuses: never restate a Claim more strongly than its
  status, never introduce a finding the record does not contain.

  That rule is a CEILING. It has a FLOOR, and both are enforced: **state the strongest
  conclusion the record does support, plainly, and stand behind it.** A ceiling alone is
  satisfied by asserting as little as possible, which is how a paper ends up saying
  nothing. Underclaiming and overclaiming are both failures.
- **`SIProse`** — optional prose around the auto-dumped Supporting Information record.
- **`FigureSpec`** — figure specifications. For a data plot, the `y` values are pulled
  FROM Evidence by `evidence_id` (record fidelity). For a diagram (not a data plot),
  an image figure is supplied externally via the general figure mechanism — the
  kernel carries no domain plotting code, so any domain-specific figure tool produces
  the image file outside the kernel and you reference it.

### The paper is written in a SEPARATE session, from the record

Two documents, two jobs, and they are not written together:

| | `runs/<id>/record.tex` | the paper (`paper/draft.tex`) |
|---|---|---|
| What | the deterministic record dump | the argument |
| Written by | the engine, no authoring judgement | you, in a session of your own |
| Submitted | no | yes |
| Vocabulary | the record's own, freely | tool-agnostic science |

If you are the session that ran the experiments, your publish job ends at the record:
`sci-adk render <run> --record-only` deposits `record.tex` and writes nothing under
`paper/`. Then stop and hand off. Do not use a plain render without `--prose` for this:
it also writes a skeleton `paper/draft.tex`, `verify` judges any `draft.tex` as the
manuscript and fails it against the frozen `pubreqs.json`, and the session cannot end.

If you are the paper session, **`record.tex` is your input** — the complete Evidence,
the numeric tables, the figures, the verdicts with their frozen decision rules. Read
it and work out what was found and what it means. A verdict decided by a threshold or
interval rule carries no degree of belief: report the recorded estimate and its interval
against the pre-registered threshold or band, never a confidence value and never a margin
you computed (the margin is the rule's bookkeeping, not a finding; only a Bayesian rule's
posterior is a probability).
Then:

1. author the manuscript into a `prose.json` (a `PaperProse`: title / abstract /
   introduction / methods / results / discussion);
2. `sci-adk numbers draft <run> --prose prose.json` and complete `runs/<id>/numbers.json`
   from the proposals it writes (below) — every number the paper states;
3. `sci-adk render <run> --prose prose.json` — this also re-deposits the identical
   `record.tex`, since the record inputs have not changed;
4. record the conclusions in `runs/<id>/declarations.json` (below);
5. `sci-adk verify <run>`.

**No gate can tell whether you actually did this in a separate session.** The
separation is a discipline, not a check. What the engine can see is whether the
paper's numbers trace to the record, whether its declared conclusions still match, and
whether any conclusion is missing — which is why those three are gates and this is not.

### State conclusions as an ARGUMENT, and declare them beside the paper

You are writing a PAPER — an argument addressed to a skeptical peer. It is not a prose
rendering of the record. The reproduction document already exists; do not write a second
one.

So a conclusion is never stated as a bookkeeping value. `H2 is supported` tells a reader
nothing: not what was found, how large it was, under what conditions, or how much to
believe it. Write the sentence you would defend at a seminar.

```
NO   H2 is \status{h2}. H1 is \status{h1}.
YES  The model reproduces the observed values across all nine sites, with no parameter
     refitted. The elasticity relation, by contrast, was mis-stated and does not hold at
     these concentrations.
```

**What is submitted is the `.tex` SOURCE**, not just the PDF — reviewers, editors,
co-authors on Overleaf, and publisher typesetting all read it. So the manuscript carries
NO markup a reviewer would not recognize. The binding to the record lives in a side file
that is never submitted, `runs/<id>/declarations.json`:

```json
{"spec_id": "<id>", "declarations": [
  {"hypothesis_id": "h2", "status": "supported",
   "sentence": "The model reproduces the observed values across all nine sites, with no parameter refitted."},
  {"hypothesis_id": "h1", "status": "refuted",
   "sentence": "The elasticity relation, by contrast, was mis-stated and does not hold at these concentrations."}
]}
```

Copy each sentence VERBATIM from the manuscript. Line wrapping is fine (whitespace is
normalized); anything else must match exactly.

Three HARD checks in `verify`, none of which reads meaning:

- **The declared status must still match the record.** Belief is revisable. When new
  evidence moves a status, the sentence and the argument built around it were written for
  the old verdict, so `verify` FAILS and you rewrite the passage. A revision costs a
  rewrite, never a silent word swap.
- **The declared sentence must still be in the manuscript.** If you rewrite it, the
  declaration has detached from what it described — re-declare it as it now reads.
- **Every decided hypothesis must be declared.** Once the list exists, a hypothesis with a
  derived Claim and no declaration is a result the paper silently omits. This is the floor,
  made structural: a rule against overstating, alone, is satisfied by saying nothing.

What these do NOT check is whether your sentence overstates the status it declares. That
is a judgement, and no gate makes it — an independent reviewer does, and its finding goes
to a human.

### Declare the numbers beside the paper

Numbers need no markup either. Their binding lives in a second side file that is never
submitted, `runs/<id>/numbers.json`: every number literal the paper states, its role, and
where it comes from. No checker can tell from the text whether "47" is a page, a prime or
a count, so the role is stated, not guessed:

```json
{"spec_id": "<id>", "numbers": [
  {"text": "0.62", "source": {"evidence": "<evidence id>", "field": "point"}},
  {"text": "31", "source": {"evidence": "<evidence id>", "field": "finding.n_sites"}},
  {"text": "0.5", "source": {"spec": "hypotheses[0].decision_rule.params.value"}},
  {"text": "95", "source": {"spec_text": "hypotheses[0].decision_rule.expression"}},
  {"text": "2006", "source": {"bib": "<key>", "field": "year"}},
  {"text": "71.4", "formula": "100 * a",
   "operands": {"a": {"evidence": "<evidence id>", "field": "finding.fraction"}}},
  {"text": "4.2.1", "role": "identifier"},
  {"text": "13", "context": "13 of the records", "source": {"evidence": "<evidence id>",
   "field": "finding.n_rescored"}}
]}
```

- `text` is the number as written, without unit or `%` (`95\%` is `95`); `document` is
  `draft.tex` unless it says `si.tex`. Write a range with an en dash (`0.71–0.83`): two
  hyphen-joined numbers read as one label.
- A source is an Evidence field (`point`, `effect_size`, `ci[0]`, `ci[1]`, `p_value`,
  ..., `finding.<key>` of a JSON finding), a numeric field of the frozen Spec, a number
  written in one Spec text field (`spec_text`), or a reference's year.
- `role: "identifier"` is for what is not a quantity — a registry number, a version, a
  date, a label. It is checked against nothing and LISTED by `verify`, so every exemption
  is seen.
- `context` quotes the words around an occurrence; it is needed only when one text has two
  roles in the same document.

`sci-adk numbers draft <run> --prose prose.json` proposes the list: a source where exactly
one recorded field prints as the number, `candidates` where several do, `unresolved` where
none does. A single match is a proposal, not a decision — check it is the quantity the
sentence states. **You never add a value to the record**: a number with no recorded home
goes back to the experiment stage, to be recorded there as a named value.

Two HARD checks in `verify`, neither of which reads meaning: every number in the paper is
covered by an entry, and every entry's source exists and, rounded to the printed
precision, equals the number (`0.769` matches a recorded 0.768932; `0.768` does not).
An entry that no longer matches anything, and every identifier, is reported as advisory.
A run without `numbers.json` is still checked by the older pattern audit.

### Write for readers who were not in the room

A document leaving this session must not use a word whose meaning exists only inside it.
That is not a ban on technical language — a field's own vocabulary belongs in a paper
written for that field. What is banned is WORKING vocabulary reaching a deliverable.

**The test, applied against the actual venue** (`venue` is recorded in the frozen
`pubreqs.json` — read it before you write):

> Would a competent reader of THIS venue know this term without being told by me?

- Yes → use it. Expand an abbreviation once at first use, then freely.
- No, but it is standard elsewhere and this venue is cross-disciplinary → define it in
  the sentence where it first appears, never in a glossary.
- No, because it was invented during this work → remove it and rewrite the passage.

The venue decides, and the same word can fall on either side of it: "pre-registration" is
standard in a clinical journal and opaque in an engineering report; "commit" is ordinary
to software readers and jargon to chemists. Judge against the real audience, not a general
one. This is why `verify`'s vocabulary scan carries only compounds that name the machinery
in EVERY venue — the venue-relative half is your judgement, and no gate makes it for you.

**What leaks most often:**

- Variant labels and numbers: Arm A, Case 3, run type 2, cycle 15, hypothesis 2.
- Words for the machinery: gate, harness, probe, manifest, the pipeline, stage 2.
- Coined shorthand for a finding: the substitution, the hump, the drift.
- Status vocabulary: in force, superseded, frozen, carried through.
- **Vocabulary borrowed from the record document** — the worst kind, because you did not
  define it either. You are reading `record.tex` to write this paper, so you are in
  exactly the position where this happens. A word being in your input is not a reason to
  use it in your output.
- **Script and file names used as concepts**: "the analysis says", "per the probe". Name
  files as files: "the table `analysis.py` produces shows ...".

**Two things that are not the fix.** A glossary is not: defining invented vocabulary and
then using it asks the reader to learn a private language first, and leaves the prose
unreadable to anyone who skips the table. Find-and-replace is not: swapping a word leaves
the sentence built around a concept the new word does not carry, and reads worse than the
original. Read the passage, work out what it is doing, write it again.

**Then check two things the rewrite can break.** Re-verify that every number and claim
survived it — `verify` does this for you (the number list and the declaration checks) and
will refuse if it did not. And **read the opening cold**: the abstract and the first
paragraphs are where an unexplained term does the most damage and where it is most often
left in place.

### Claim no more than the record shows

The second way a paper fails its reader is a claim stated more strongly than the evidence
carries, or buried under more apparatus than the evidence earns. This is not a ban on
caveats: a caveat that changes how a specific result should be read stays, next to that
result.

**Verbs follow the design.** Every verb and noun that asserts cause, mechanism or
generality must be licensed by something the paper itself shows — and the design is
recorded: the method plan (`method`) and each hypothesis's decision rule in the frozen
`spec.json`.

- Descriptive or observational design: "increased", "was higher in", "was associated
  with", "was observed", "co-occurred with". Stop there.
- Causal language — "caused", "drove", "led to", "reduced" (transitive), "due to",
  "because of", and the nouns "effect", "impact", "driver", "role" — only where the
  design supports it: a controlled experiment, randomization, or a causal identification
  strategy stated in the methods.
- "Demonstrates" and "shows" only for what the data directly display. A mechanism the
  data are consistent with is "consistent with", once — not "suggests", "indicates" and
  "points to" in turn.
- Scope words follow the sample. Twelve cases measured under two conditions support a
  statement about those twelve cases under those two conditions, not about the class
  they were drawn from.

**One claim, one position.** Do not state a claim and walk it back in the next sentence.

- Uncertainty goes inside the claim, as numbers: range, interval, n, detection limit.
  "The difference was 0.42 (95% CI 0.18–0.66, n = 31)" replaces "The difference was
  positive, although considerable variability was observed."
- Stacked hedges ("may potentially suggest a possible role") mean the sentence has
  nothing left to say. Find the one defensible statement or delete it.
- What the work does not show and the reader does not need: leave it out.
- Stock softeners are deleted on sight: "It should be noted that", "These results should
  be interpreted with caution", "Further research is needed", "Importantly", "Notably";
  in Korean, "~일 가능성을 배제할 수 없다", "해석에 주의가 필요하다", "향후 추가 연구가
  필요하다".

A null or refuted result is stated as plainly as a supported one — understating is a
defect too, and the conclusion reviewer reads in both directions.

**Proportion.** Each part earns its length from the results.

- Limitations: only those that would change how a reader interprets a specific result,
  or that a competent reviewer at this venue would raise. Name the result each one
  limits; usually one to three. Limitations true of every study of this kind are cut
  unless they bite on a stated conclusion. The limitations text is shorter than the
  results it qualifies.
- Implications: only those that follow directly from a result and that this venue's
  reader would act on.
- Future work: at most one sentence, naming the measurement or analysis that would
  settle a specific open question these results raise. Otherwise none.
- Methods: enough to reproduce, nothing more. Cite standard procedures instead of
  narrating them; report software as name, version and non-default settings. The full
  record is already in `record.tex` — the paper does not repeat it.

Where the venue mandates a section (a required "Limitations" heading in `pubreqs.json`),
write it and hold its contents to the same test.

**Deletion is the method.** When a sentence needs a hedge to be true, write the hedged
version and ask whether it still tells the reader anything; if not, delete it. The same
goes for sentences that exist to look careful: a result restated in softer words, an
objection nobody raised answered anyway, a closing summary at the end of each section.

**A hedge is not the fix** — the third of the non-fixes above. Keeping the strong verb
and adding "may", or appending a caution sentence, leaves the overclaim in place and adds
a retraction on top. Downgrade the claim to what the design supports, or delete it.

**Order of work before render:**

1. List the terms this venue's reader would not know; sort them into field vocabulary
   (keep, expand once), cross-disciplinary (define in place), invented here (remove).
2. Rewrite the passages holding invented terms — passage by passage, not word by word.
3. Mark every verb and noun in the abstract, results and conclusions that asserts cause,
   mechanism or generality; check each against the recorded design. Downgrade or delete.
4. Merge every claim-plus-softener pair into one claim with its uncertainty as numbers.
5. Tie every limitation, implication and future-work sentence to a specific result;
   delete the rest.
6. Strip narrated standard procedures and default settings from the methods.
7. Run `verify` — it re-checks every number and every declared conclusion against the
   record.
8. Read the opening and the closing cold. In both, every sentence is either the question
   or a finding; delete the rest.

### Render

`sci-adk render` is the ONLY way to produce the paper artifacts — do not hand-write
the final `.tex`. It emits a self-contained folder:

```
paper/
├── draft.tex        # the main paper (belief narrative)
├── si.tex           # Supporting Information (the full record, auto-dumped)
├── figures/         # body-order numbered figure files
└── references.bib   # bibliography
```

The SI is the deterministic record dump (Evidence record + quantitative table +
Claims with their C3 bases + decision rules + figures + record-integrity). The whole
`paper/` folder is self-contained for a single Overleaf folder upload.

### The paper-consistency gate

`sci-adk verify` runs a within-document consistency gate over the rendered `.tex` as a
HARD gate — a dangling `\ref`, an orphan figure, or an unsupported `\novelty` marker
makes verify exit non-zero EVEN IF the Claims reproduce. Run `sci-adk verify` as a
read-only self-check before returning.

### Publishing requirements (the frozen contract)

`/sci publish` may FREEZE a publishing contract at `runs/<id>/pubreqs.json` (via
`sci-adk pubreqs freeze`, beside `spec.json` so `render` never clobbers it) — venue,
required sections, figure font policy, raster `image_min_dpi`, reference style, length
limits, and free-form advisory conditions. It is a RECORD (frozen + digest, like the
Spec): authored TO, then checked AGAINST. The orchestrator elicits it (`AskUserQuestion`);
a worker authors to it but never freezes or relaxes it.

`sci-adk verify` enforces it as the `paper_requirements_clean` HARD gate: each declared,
deterministically-checkable requirement — sections present (`\section{...}` in
`draft.tex`), the F2 figure font policy + raster DPI, the reference style wired, word
count ≤ limit, the F3 reproduction bundle present (`paper/reproduce.py` referencing the
recorded `code_ref`s, and each file a `code_ref` names still matching the `sha256=`
recorded with it) — must pass; `advisory` items and `max_pages` (no page count
without a compile) are surfaced but NEVER gate. ABSENT `pubreqs.json` → the gate is
vacuously clean (backward compatible). A gate-bearing field cannot be relaxed after a
failure except by an explicit re-freeze (anti-moving-the-goalposts).

### Authoring constraints

- **Body-order figure numbering.** A prose `\ref{fig:<id>}` drives the numbering —
  referenced figures are numbered in the order they are first referenced in the body.
  Use a stable `\label{fig:<id>}` and reference by it; never hardcode a figure number.
- **Cross-doc SI references are PLAIN TEXT.** A main-paper → SI-figure reference must
  be plain text (e.g. "Figure S1"), NOT `\ref{fig:SI-...}` — the within-document gate
  flags a cross-doc `\ref` as dangling (cross-doc `\ref` resolution is deferred).
- **Novelty markup is HARD-gated.** A `\novelty{result|method}{hyp}{text}` marker may
  only be emitted for a kind whose novelty flag is supported on the record (a
  `found_nothing` search exists). Do not assert novelty the record does not back.

### Frozen-Spec boundary

The artifacts bind to the frozen `spec_id` + `spec_digest`; the verbs check the digest
against the on-disk Spec. Render against the Spec, Evidence, and Claims AS RECORDED.
`paper/` is ready for Overleaf folder upload only once the consistency gate passes.

## Advanced (10+ minutes)

The figure/SI design (hybrid LaTeX-native pgfplots data plots + image fallback for
diagrams; SI = auto record-dump; the verify consistency gate) is detailed in the
paper-figures-and-si design. The novelty render-time `\novelty{}` markup gate
(detection via explicit markup, HARD-fail on unsupported, scoped "to our knowledge,
as of <search date>" auto-attach on supported) is a separate track in the literature
acquisition design — render-time emission of `\novelty` should survive into the
`.tex` so verify can re-scan it.

## Works Well With

- `science-foundation-rigor` — the record-fidelity discipline this builds on.
- `science-workflow-experiment` — produced the Evidence + derived Claims being narrated.
- `expert-writer` — the worker that authors the hooks and renders the paper.
- The `evaluator-rigor` guard — advisory paper-consistency pre-check before close.
- The `evaluator-conclusions` guard — reads each declared conclusion BLIND (it is not
  told what you declared) and answers only "which status does this sentence assert?".
  `verify` computes the disagreement and surfaces it as a non-gating advisory, so a
  faithful paper produces silence. It catches both overstatement and understatement,
  and it can never fail a run. Run it before close; do not show it the declaration list.
  Give it the identifier entries of `numbers.json`: it notes any that reads, in its
  sentence, as a reported quantity (advisory, like its readings).
