# The manuscript is an argument, not a rendering of the record

> Status: **§11-§13 COMPLETE (v1.0)** on branch `feat/declaration-list` — §11.3 and
> §11.4 built, §11.1 resolved as a protocol change that needed no code (§11.5d).
> §12 defines what tool vocabulary IS and §12.2a corrects it to be AUDIENCE-relative;
> all of its routes are now applied (list, author instruction, reviewer, floor). §13
> records the first outside test: two findings open, one fixed.
> §1-§7 are the
> diagnosis; §8 corrects two errors in it; §9 is a first answer that was implemented and
> then SUPERSEDED — it fails at the submission boundary; **§11 is the architecture**.
>
> The `\finding` markup of §9 is REMOVED on this branch (the declaration list quotes the
> sentence, so an in-document marker adds nothing — §11.5). Its commit is preserved at the
> untouched `feat/verdict-markup` ref.
>
> v0.2 supersedes v0.1's framing. v0.1 diagnosed "the protocol specifies no reader" and
> proposed readability remedies. That was one level too shallow: the missing reader is a
> symptom. The root is a **genre error** (§2), and correcting it re-ranks every direction
> v0.1 listed (§7).
>
> Cross-references: `design/render-architecture-reframe.md` (the moved line — narrative
> to the agent, facts to the engine), `design/paper-writing-enforcement.md` (the five
> hard gates), `design/si-belief-record-split.md` (main·SI both authored belief),
> `design/rigor-shell-architecture.md` §2.4 ("writing paper prose" is OUT of the kernel).

---

## 1. The complaint

Reported by the author after reading a rendered manuscript end to end: the paper-writing
protocol is not reader-friendly, and reading the output was uncomfortable. Localized to
two things:

1. **Vocabulary leak** — the tool's internal words (`gate`, `pre-registered`, `frozen`,
   `recorded`, `cycle`, `Evidence`) appear in the outward-facing manuscript.
2. **Conclusion delivery** — what the paper does and does not claim does not come
   through to a reader.

Both are downstream of one thing.

---

## 2. The root — a genre error

**What we must produce is a paper. Not a specification, and not a reproduction
document.**

These are three genres with three different jobs:

| Genre | Job | Succeeds when |
|---|---|---|
| Specification | fix what will count as an answer, before looking | it cannot be reinterpreted after the fact |
| Reproduction document | let a stranger re-derive what happened | nothing needed is missing |
| **Paper** | **persuade a skeptical peer that a claim about the world holds** | **the argument survives the reader's objections** |

sci-adk already produces the first two, correctly and by construction: the frozen Spec is
the specification; the SI record dump is the reproduction document. That is the system's
whole point, and none of it is in question here.

The error is that **the third has been treated as a prose rendering of the first two.**
The publish protocol's stated split is right — "Main paper = belief narrative; SI = the
full record auto-dumped" (`science-workflow-publish/SKILL.md`) — but only the SI side is
specified. The main-paper side is given IMRaD containers to fill, a fidelity ceiling, and
macros that substitute recorded facts. Nothing in the protocol asks **what the paper
argues.** With the genre unspecified and the record's shape supplied, the manuscript
defaults to the genre the protocol actually describes: a second, prose-shaped copy of the
reproduction document.

That default explains both symptoms at once. Tool vocabulary is *correct* in a
reproduction document and only wrong in a paper (§3). Bookkeeping verdicts are *the point*
in a specification and say nothing to a reader (§4). Neither symptom is a word-choice
accident; each is the right behavior for the wrong genre.

---

## 3. The genre error is rendered by the engine, not adopted by the agent

The one mechanism the protocol provides for stating a verdict in prose is the `\status`
macro (`src/sci_adk/render/factref.py:14`):

```
\status{<hypothesis-id>}  -> the experiment Claim's status (e.g. supported)
```

Resolution is literal (`src/sci_adk/render/factref.py:157`):

```python
return claim.status.value if hasattr(claim.status, "value") else str(claim.status)
```

`claim.status.value` is the enum string from `src/sci_adk/core/claim.py:50-53` —
`proposed` / `supported` / `contested` / `refuted`. These are sci-adk's belief-state
ontology, chosen for the record's non-monotone semantics, and they are substituted
verbatim into the manuscript body. An author who uses the protocol's own fidelity
mechanism for every verdict produces a maximally record-voiced manuscript **by
construction**.

### 3.1 The consequence: argument and rigor are placed in opposition

`factref.py:28-33` documents the honest limit — the gate binds only facts written *via* a
macro; a bare literal typed in prose is outside it. Therefore:

| Author writes | Reads as | Record-bound? |
|---|---|---|
| `\status{h2}` → "supported" | a database field | yes |
| "the model reproduces the observed values" | an argument | **no** |

**There is no third option in the current design.** Writing a paper rather than a record
dump is purchasable only by leaving the fidelity gate. This is the defect: two properties
the system needs together are made to trade against each other.

### 3.2 The observed consequence

In the field case the correction ran the expected course. A find-and-replace pass was
attempted first and rejected by the author as not a fix; the manuscript was then rewritten
paragraph by paragraph by hand. Two costs were incurred, both predicted by §3.1:

- Verdict statements moved from macro-bound to prose literals — **fidelity coverage went
  down as the paper became a paper.**
- The number-audit baseline was edited so a deliberately-removed threshold value would not
  fail the gate — justified, but a **gate criterion changed to let its own output pass**,
  with no second party.

A protocol in which writing a proper paper mechanically reduces rigor is mis-specified.

---

## 4. Why the conclusion does not land

**The status vocabulary is not a conclusion vocabulary.** "H2 is supported" is a statement
about the record's bookkeeping. It does not tell a reader what was found, how large it
was, under what conditions, or how much to believe it. The four values exist so belief can
move non-monotonically as evidence arrives — a record-side requirement with no reader-side
meaning. Rendering them into the manuscript answers a question no reader asked.

**The only prose instruction is a ceiling, not a target.**
`science-workflow-publish/SKILL.md:60` instructs: never restate a Claim more strongly than
its status. Correct and necessary — but it is the *only* rule about what prose says, so it
is optimized against in isolation. The safest sentence under a ceiling-only rule asserts as
little as possible. Repeated across a manuscript, maximal hedging is what makes "so what
was found?" unanswerable. The missing counterweight is a floor: **state the strongest
conclusion the record does support, plainly, and stand behind it.** Rigor is symmetric —
overclaiming and underclaiming are both failures. The protocol implements only the upper
half, because underclaiming costs a reproduction document nothing.

**Supporting evidence — the protocol contains no reader.** A search across every workspace
skill for `readab|reader|audience|prose quality|jargon|plain english|style` returns only
`reference_style` (bibliography format) and `output style` (the persona). Every stated
requirement is a refusal condition (numbers record-pulled, no dangling `\ref`, sections
present, word count ≤ limit, font/DPI); there are zero conditions on whether the paper
argues anything. A specification made only of refusal conditions selects for the cheapest
artifact that is not refused — which, given §2, is the record in prose clothing. An agent
under this specification correctly reports "seven gates PASS, 7993/8000 words" as
completion, and correctly responds to an over-length rewrite by compressing further: the
limit is specified, the argument is not.

---

## 5. What is NOT wrong

Stated explicitly so a fix does not damage it.

- The frozen Spec, the append-only Evidence record, the derived Claim statuses, and the SI
  record dump are correct as they are. The reproduction document is a required deliverable
  and sci-adk produces it well.
- Record fidelity for cited facts is correct. A paper being an argument does not license
  unbound numbers — an argument that cites the record is *stronger*, not weaker, than one
  that cites nothing.
- The moved line (`rigor-shell-architecture.md` §2.4 — narrative belongs to the agent, not
  the kernel) is correct and this diagnosis reinforces it (§7, D1).

The genre error is confined to how the main manuscript surface is specified and rendered.

---

## 6. Constraints on any fix

- **[C0] The deliverable is a paper.** Any change is judged by whether the manuscript
  argues better to a skeptical peer — not by whether it is more traceable. Traceability
  has its own artifact.
- **[C1] Not a lint, not a banned-word list.** A find-replace pass over tool vocabulary was
  tried and rejected: substituting a synonym leaves a sentence built in the record's shape.
  Detection may be mechanical; correction is rewriting.
- **[C2] Must not buy the paper with fidelity.** Any fix that makes verdicts readable by
  moving them off the macro path makes §3.1 worse. The target is a verdict expression that
  is both record-bound and argument-voiced.
- **[C3] Add a floor, keep the ceiling.** `SKILL.md:60` stays. What is missing is its dual.
- **[C4] Domain-neutral.** No general surface may assume a domain, venue, or study.
- **[C5] Argument quality is not machine-adjudicable.** It must not become a HARD gate. The
  engine's verdict authority covers record fidelity; whether a paper persuades is a human
  judgement — at most an advisory signal, preferably an authoring instruction.
- **[C6] The record's vocabulary stays unchanged.** `proposed/supported/contested/refuted`
  are correct inside the record and inside the SI dump. Only the manuscript surface is at
  issue.

---

## 7. Directions, re-ranked under §2

v0.1 listed these as readability remedies. Under the genre framing their order changes.

- **D4 — Specify the manuscript's genre in the authoring protocol. (now first.)** The
  publish skill gains what it currently lacks entirely: what a paper is for, what the
  argument must do, the floor as well as the ceiling, and the vocabulary boundary between
  the manuscript and the record. This addresses the root; everything else addresses
  symptoms. Objection: instructions without a signal are followed unevenly (§4).
- **D2 — Worked before/after pairs alongside D4.** The one thing that demonstrably
  transfers: the same recorded verdict written as a database field and as an argument.
  Objection: examples risk becoming templates; they must show the move, not a phrasing to
  copy.
- **D3 — Advisory signal in `verify`.** Reuse the existing non-gating `paper_advisory`
  channel to surface record-vocabulary occurrences on the manuscript surface as a prompt to
  rewrite. Objection: it detects symptom (1) only, never (2); an advisory routinely ignored
  trains the wrong habit; and C1 means it must not propose replacements.
- **D1 — Reader-voiced `\status` rendering in the kernel. (now last; likely reject.)** v0.1
  ranked this first for satisfying C2 mechanically. Under §2 it is wrong in principle: if
  the manuscript is an argument, no kernel-side phrasing table can write it, and installing
  one puts narrative choice back inside the engine against the moved line. What survives is
  the narrower question in OD-R1.

---

## 8. Two corrections to §4's audit (found while implementing)

**A tool-vocabulary gate already exists.** `check_paper_tool_vocabulary`
(`src/sci_adk/render/paper.py:917-960`) matches 12 machinery phrases (`sci-adk`,
`frozen spec`, `the engine`, `evidence record`, `append-only`, `decision rule`, …), the
bare word `verdict`, and the proper noun `Spec`; `verify` gates it HARD over both
submission documents. D3 is therefore **not a new mechanism — it is a list extension.**
The terms the field manuscript actually leaked (`pre-registered`, `gate`, `recorded`,
`cycle`, `registered`) are absent from the list: it catches the machinery's proper nouns
but not the epistemic-process vocabulary. Filing that gap is deferred, deliberately —
extending a banned-word list is C1-adjacent and must not become the fix.

**`verdict` is itself banned manuscript vocabulary** (`paper.py:933`: "a paper states a
'result', not a 'verdict'"). The surviving markup is scanned by that gate, so the macro
below is named `\finding`, not `\verdict`.

---

## 9. OD-R1 — first answer, SUPERSEDED by §11 (implemented, branch `feat/verdict-markup`)

> **SUPERSEDED (same day).** The mechanism below is sound about *what* must be bound and
> *why* declaration beats substitution — §11 keeps both. It is WRONG about *where* the
> declaration lives. `\finding` is opaque shorthand inside the reviewer-facing source, and
> `design/paper-writing-enforcement.md` §6a already resolved OD-7 with a standing user
> constraint that forbids exactly that. The reader was scoped to "someone reading the PDF";
> the submitted artifact is the `.tex`. The branch is left intact pending a decision; §11
> is the architecture that replaces it.

**The reframe.** `\status` has the engine WRITING text into the manuscript, so the
engine's vocabulary arrives by construction. The fix is to have the engine CHECK instead.

**Not an invention.** `render/novelty.py` already locks exactly this architecture:
*"SURVIVE + preamble newcommand (NOT substitute-away)"* — `\novelty{kind}{hyp}{text}`
carries the author's text, LaTeX renders only that text via
`\newcommand{\novelty}[3]{#3}`, and the metadata survives for `verify` to re-scan.
`novelty.py` names `factref.py` its sibling; `\status` is the family's one deviant member.
OD-R1 applies the family's own locked architecture to it.

    \finding{<hypothesis-id>}{<status>}{<the author's argued sentence>}

**Why declaration beats substitution — the record is non-monotone.** A status can move
from `supported` to `contested`. Under substitution the next render silently swaps that
one word while the motivation, the discussion, and the implications stay written for the
old verdict: the paper quietly self-contradicts and every gate stays green. Under
declaration the stale declaration no longer matches, `verify` fails loud, and a human
rewrites the passage. **A belief revision should cost a rewrite, not a string replacement.**
This is the decisive argument, and it follows directly from record-vs-belief.

**The floor is gateable even though the ceiling is not.** Judging whether a sentence
overstates its status is semantic (C5 — no LLM on the verdict path). But "every decided
hypothesis is argued somewhere" is structural, and is the same shape as the existing
orphan-figure check. So the ceiling stays an instruction and the floor becomes a HARD
gate — the inverse of the previous state, where prose had no gate and only a ceiling
instruction.

**Honest limits (documented in the module).** The gate binds the DECLARATION, not the
sentence: declaring the true status and still overstating passes. That ceiling was never
mechanically enforced anyway — `\status` only guaranteed the printed WORD was the recorded
one, never that the surrounding sentence did not overstate — so what is given up is an
appearance, not a guarantee. A verdict written as bare prose with no macro remains
ungoverned (the `factref.py:28-33` bound), but the INCENTIVE inverts: under substitution,
using the macro cost readability, so bypassing bought something; here the author writes
their own sentence either way, so bypassing buys nothing. This is how §3.1's opposition is
actually dissolved.

**Scope of the two gates (partial OD-R3 resolution).** MISMATCH runs over `draft.tex` and
`si.tex` (no gap for a stale declaration to hide in). FLOOR runs over `draft.tex` only —
the SI is authored overflow, not the argument, so demanding full coverage there would be
wrong. Both are opt-in per document: a manuscript with no markup is not retro-broken.

**Delivered.** `src/sci_adk/render/finding.py` (pure, F4 seam, fail-loud);
`render/paper.py` `_markup_prose` + conditional preamble; `loop/verify.py`
`_check_paper_findings` → `paper_finding_clean` in the combined HARD gate; `cli.py`
surfacing; the floor + the argument instruction + worked before/after pairs in
`science-workflow-publish/SKILL.md` (D4+D2, so the mechanism is not an un-wired kernel);
`tests/test_finding_markup.py` (28 tests, incl. the end-to-end belief-revision catch).

---

## 10. Still open

- **OD-R2** — If an advisory signal is added, what is its unit? Record vocabulary on the
  manuscript surface is detectable (and §8 shows the existing list is the place for it).
  Symptom (2) — hedging with no stated conclusion — is not, without NLP the project has
  consistently refused. The floor gate now covers the *structural* half of (2) (a decided
  hypothesis argued nowhere); the *rhetorical* half remains unaddressed.
- **OD-R3** — Partially resolved (§9 scope). What remains: whether the authored SI should
  carry the record's vocabulary at all, given it sits beside the record dump.
- **The vocabulary-list gap** (§8) — file the missing epistemic-process terms, without
  letting the list become the fix (C1).
- **`\status` deprecation posture** — it is left intact (the 1.0 surface freeze, D1 in
  `design/surface-freeze-analysis.md`). Whether it should be narrowed to non-conclusion
  values is not decided.

---

## 11. The architecture (supersedes §9)

Two corrections drove this: the submitted artifact is the `.tex` source, not the PDF; and
one document cannot be both the complete record of what happened and the argument to a
peer. The answer stops trying to make one artifact serve both.

### 11.1 Two documents, honestly named

| | Procedure/record document | Paper |
|---|---|---|
| Audience | the team, and the reviewer agent (§11.4) | the venue's reviewers |
| Submitted | no | yes |
| Vocabulary | the record's own, freely | tool-agnostic science |
| Markup | macros fine (`\evval`, `\status`, `\novelty`) | **none a reviewer would not recognize** |
| Job | complete and traceable | persuasive and correct |

The paper is authored FROM the first document — read it, understand what was found and
what was meant, then write the argument. Two passes, not one: be faithful first, be
persuasive second. This is D4 from §7 done properly, and it dissolves the vocabulary
problem at the source rather than policing it with a banned-word list (which §8 shows was
never going to be the fix, and C1 forbids anyway).

Note this gives the first document a consumer it did not previously have. Before, it was
"the paper, written badly"; now it is the input to two distinct readers — the human team
and the reviewer agent.

**Implementation posture.** `draft.tex` is referenced in 78 places across 10 modules, and
the path is inside the frozen 1.0 surface. So the move is a REASSIGNMENT of role, not a
rename: `draft.tex` stops being the submission (existing gates keep applying to it
unchanged), and the paper becomes a separate artifact carrying the new gates.

### 11.2 Where each kind of statement is bound

The single idea: **turn every semantic question into a comparison of two values.** What
cannot be reduced that way is escalated to a person, never auto-decided.

| Layer | What it compares | Verdict? |
|---|---|---|
| Number audit (exists) | every number in the paper ↔ the recorded value pool | mechanical, HARD |
| Declaration list (§11.3) | declared status ↔ recorded status; quoted sentence ↔ paper text | mechanical, HARD |
| Reviewer agent (§11.4) | the status a sentence actually asserts ↔ the declared status | model, **ADVISORY** |

The bottom two decide; the top one summons a human.

### 11.3 The declaration list

A small file beside the paper — never submitted — holding one row per conclusion:

    hypothesis | declared status | the exact sentence in the paper that states it

The paper itself is untouched: plain LaTeX, nothing a reviewer would find odd. This
satisfies OD-7 while keeping the binding, on the same reasoning OD-7 itself gave — *"the
macro was only ever ONE way to bind a number to the record."* The same is true of a
verdict.

`verify` runs two mechanical checks, neither of which reads meaning:

1. **Is the declared status still what the record derives?** Belief is non-monotone; when
   it moves, the declaration is now false → refuse, and name the passage to rewrite. This
   is §9's revision catch, preserved intact.
2. **Does the quoted sentence still appear in the paper?** If the author edited it, the
   quote no longer matches → refuse, and require re-declaration.

Check 2 is strictly stronger than what `\finding` could do: a macro's text argument can be
rewritten freely with nothing noticing. The machine still cannot judge the new sentence —
but it can refuse to let a declaration silently detach from the sentence it was made about.

Completeness rule (carried over from §9's floor, and still necessary): once the paper
declares one conclusion, it must declare every hypothesis the record actually decided.
Without it, an author declares the favourable results and omits the rest.

Known costs: one more file to keep in sync; quote matching is brittle against whitespace,
line wrapping, and LaTeX escaping, so it needs normalization and will still not be perfect.

### 11.4 The reviewer agent — as a label comparison, not a hunt

A fresh-context agent is the only layer that can read meaning. It belongs in the existing
guard tier (`evaluator-rigor` / `evaluator-active`), which is advisory by construction.

**Do not ask it to find overstatement.** A model asked to find problems finds them whether
or not they exist; a few false alarms and the signal is ignored, which is how a gate dies.

Ask instead: give it the hypothesis, the pre-registered decision rule, the recorded result,
and the conclusion sentence — **withholding the declared status** — and have it answer one
bounded question: *which status does this sentence, as written, assert?* Four values plus
"unclear". Then compare its answer to the declaration mechanically.

The properties this buys:

- The model **reads** rather than hunts. A clean paper produces silence.
- The disagreement is **computed, not asserted** by the model.
- **Both directions come free.** Declared `supported`, read as `contested` = overstatement.
  Declared `supported`, read as something weaker = UNDERSTATEMENT — which matters, because
  a reviewer hunting only overclaims rewards hedging and re-creates the §4 defect.
- The declaration list earns its keep twice: the reviewer is told which sentence to
  classify instead of having to locate the conclusions itself.

Constraints: the result is a signal for a person, never a gate — an LLM must not sit on the
verdict path. Model answers vary between runs, so run it more than once and escalate only
stable disagreements (precedent: the design constitution's independent re-evaluation
mechanism).

Blind spot, to be stated rather than hidden: this checks declared sentences only. Spin in
the abstract, selective emphasis, and a discussion that travels further than the results
support are all invisible to a per-sentence label comparison. A person has to read the
paper.

### 11.5 What §9 contributes to §11

Not discarded: the reason declaration beats substitution (a revision must cost a rewrite,
not a silent word swap), the floor as a structural rule, and the finding that no gate ever
needed the sentence as a macro argument — which is precisely why moving it out of the
document costs nothing. What changes is the location: outside the manuscript, not inside.
If the branch is reworked rather than dropped, the marker form (§6 F3, no text argument) is
the shape that survives; the flat-argument problem and its `\begin{finding}` fix (F2) both
disappear, since there is no span.

### 11.5b What shipped for §11.3

`src/sci_adk/core/declarations.py` — the type + loader, at `runs/<id>/declarations.json`
(beside `spec.json`/`pubreqs.json`, outside the regenerated `paper/` so `render` never
clobbers it). NOT frozen, unlike `PubReqs`: a declaration list is revised whenever the
paper is, which is exactly what check 2 enforces.

`src/sci_adk/render/declaration_checks.py` — the three pure checks. Quote matching
normalizes whitespace only (LaTeX re-wraps freely) and strips unescaped-`%` comments first,
so a sentence surviving only inside a commented-out block does not count as present.

`loop/verify.py` `_check_declarations` → `declarations_clean` in the combined HARD gate;
`cli.py` surfacing; `science-workflow-publish/SKILL.md` rewritten to author the list
instead of the markup. `tests/test_declarations.py`, 25 tests including the belief-revision
catch, the silently-edited-conclusion catch, and a test asserting the manuscript itself
carries no markup.

Opt-in at the RUN level: no `declarations.json` → vacuously clean, so no existing run is
retro-broken. A malformed file is a loud failure, never a silent skip.

### 11.5c What shipped for §11.4

`core/declarations.py` gains `ReadConclusion` / `ConclusionReview` / `load_review`
(`runs/<id>/review.json`); `render/declaration_checks.py` gains
`declaration_disagreements`, which COMPUTES the disagreement rather than letting the model
assert one; `verify._conclusion_review_advisory` routes the result through the existing
non-gating `paper_advisory` channel — so the layer that involves a model is structurally
incapable of failing a run, and a malformed review becomes an advisory line rather than an
error (a broken advisory input must not stop a run either).

`.claude/agents/evaluator-conclusions.md` is the guard. Its hard rules: answer only *which
status does this sentence assert*; **never open `declarations.json`** (seeing the declared
status destroys the independence that makes the check worth running); treat understatement
as a real defect, not a safe default; "cannot tell" is a legitimate answer and gets its own
advisory line rather than being dropped.

Tests: 8 added to `tests/test_declarations.py` — agreement is silent, overstatement and
understatement both surface, cannot-tell surfaces, and two tests assert the verdict is
byte-identical with and without a disagreeing (or malformed) review.

### 11.5d §11.1 RESOLVED — and it needed no code

Both §11.6 questions were answered by the author: **the internal document is the record
dump**, and **the paper is written in a separate session**.

That resolution collapses the implementation almost entirely, because both halves already
exist:

- The internal document is `runs/<id>/record.tex` — written by the compiler via
  `render_si_latex`: the complete Evidence, the numeric tables, every figure, the verdicts
  with their frozen decision rules, and the record-integrity line, with no authoring
  judgement and no LLM. Nothing to build. The earlier plan to REASSIGN `draft.tex` is moot:
  `draft.tex` is the paper, `record.tex` is the internal document, and there is no third
  artifact.
- The separate session already has a file-based way in: `sci-adk render <run> --prose
  prose.json`. A session that never saw the research conversation can read `record.tex`,
  author a `PaperProse` JSON, render, declare, and verify. No new verb, no surface change.

So §11.1 is a PROTOCOL change, not a code change, and the honest thing was to ship it as
one rather than manufacture kernel work to look busy. What shipped is the two-session split
in `sci/SKILL.md` (Session A deposits the record and stops; Session B writes the paper from
`record.tex`) and the paper session's input contract in `science-workflow-publish/SKILL.md`.

**Stated limit, in the skill itself: no gate can tell whether the paper was really written
in a separate session.** The separation is a discipline. What the engine can see is whether
the paper's numbers trace to the record, whether its declared conclusions still match it,
and whether any decided conclusion is missing — which is why those three are gates and this
is not. The instruction that matters most is therefore the negative one: the research
session must NOT continue into the manuscript merely because the record is at hand.

Note the pleasing consequence: rendering with no `--prose` deposits the record and leaves
the manuscript an empty skeleton. The default behaviour of the research session is now
exactly the correct one.

### 11.6 Open

Both of v0.6's open questions were answered by the author (§11.5d). What remains is not a
decision but a bet:

- **RESIDUAL RISK, accepted rather than solved.** Session separation is unenforceable, so
  the architecture rests on a discipline the engine cannot see. The three gates bound what
  a paper may SAY; none bounds how it came to be written. A violation will show up as
  papers that read like the record again — qualitative evidence, not a failing gate. The
  strongest countermeasure available is the default: rendering with no `--prose` deposits
  the record and leaves the manuscript empty, so the research session's easiest path is now
  the correct one.
- **The record dump carries facts but not INTENT**, and intent is part of what a paper
  needs. The paper session reconstructs it from the Spec's frozen hypotheses and decision
  rules, which the dump carries — that is why they were pre-registered. Whether it is
  enough is an empirical question, and the first real paper written this way is the test.

---

## 12. What tool vocabulary IS — a definition, not a list

§8 left "extend the banned-word list" as an open item. Attempting it produced the reason it
should not be done that way, and the reason is not caution: **a list cannot express the
thing being banned.**

### 12.1 Why the list cannot work in principle

The words the field manuscript actually leaked are ordinary scientific English:

| word | legitimate use | leaked use |
|---|---|---|
| recorded | "we recorded the temperature" | "recorded as refuted" |
| cycle | the catalytic cycle | "four pre-registered cycles" |
| gate | a gated ion channel; gate voltage | "the gate" |
| frozen | samples frozen at -80 C | "the frozen criterion" |
| pre-registered | "the analysis plan was pre-registered" | "the pre-registered acceptance of 0.15" |

The same word appears on both sides of every row. **The word is not the unit of the
offence; its referent is.** Any list is therefore either too narrow (only the compounds
nobody would write anyway) or fires on correct papers — and a gate that fires on correct
papers is a gate people learn to ignore, which is worse than no gate. sci-adk is
domain-general, so this is not a corner case: almost any English word is a legitimate term
of art in some field.

### 12.2 The definition

> **A term is tool vocabulary when its referent is an artifact or state of the authoring
> system rather than of the science.**

The science includes the object of study, the methods used to interrogate it, and the
reasoning from evidence to conclusion. It does not include the bookkeeping by which this
document's claims were tracked.

**The operational test — the stranger test.** *Could a researcher who has never used this
tool, working from the same experiments, write this sentence?* If the sentence becomes
unwritable or meaningless without the tool, the term refers to the machinery.

Worked: "we recorded the temperature" — any researcher writes it. "recorded as refuted" —
only someone with our Claim log does. Same word, opposite verdicts, and the test separates
them without knowing the word in advance. That is what a list can never do.

### 12.2a The test needs a second parameter: the AUDIENCE

The stranger test above is correct for the class it names, and incomplete. It asks whether
ANY researcher could write the sentence — so it silently assumes one audience. The real
test carries a venue:

> **Would a competent reader of the venue this document is written for know this term
> without being told by me?**

with three outcomes rather than two: *field vocabulary* (keep; expand an abbreviation once
at first use), *standard elsewhere but this venue is cross-disciplinary* (define it in the
sentence where it first appears, never in a glossary), and *invented here* (remove it and
rewrite the passage).

**This corrects §12.4 below.** That section argued `pre-registered` can never be banned
because it is a scientific virtue term. Venue-blind. Pre-registration is standard in a
clinical journal and opaque in an engineering report — the same word, decided by the
reader. The right conclusion was never "never ban" but **"the judgement is parameterised by
venue"**, and the parameter already exists on the record: `pubreqs.json` carries `venue`,
frozen with the rest of the publishing contract.

That gives a clean split of labour, and it is why the mechanical gate stays
venue-independent:

- A term naming the machinery leaks in EVERY venue (`spec digest`, `result.point`,
  `sci-adk`). Venue-independent → the list, mechanically.
- A term ordinary somewhere and opaque here depends on the reader. Venue-relative → the
  author's judgement and the reviewer's, both of which must be TOLD the venue.

A boundary case worth stating: in a paper ABOUT this tool, the machinery vocabulary IS the
field vocabulary. The same word is correct in `paper/paper.md` and a leak in a chemistry
manuscript the tool produced — so the vocabulary gate would be wrong to run against this
project's own tool paper.

### 12.3 The taxonomy, and what each class is enforceable by

| Class | What it is | Signature | Enforceable? |
|---|---|---|---|
| **A. System proper nouns** | the tool's name and its types promoted from common nouns (`Spec`, `Evidence`, `Claim`) | capitalised mid-sentence; the product name | partly — the `Spec` rule already does this |
| **B. Structural literals** | field paths, ids, artifact names, commands (`result.point`, `hyp-001`, `pubreqs.json`, `sci-adk verify`) | dotted paths, slug ids, file extensions, verb names | **yes, high precision** — never ordinary prose |
| **C. Bookkeeping referents** | ordinary words pointing at our record/gate state | none — identical to legitimate use | **no, in principle** (§12.1) |
| **C2. Borrowed vocabulary** | words imported from the record document, undefined by the author either | none | no — but it has a known SOURCE (§12.3a) |
| **C3. Files as concepts** | "the analysis says", "per the probe" | none — no filename token appears | no — class B's scan cannot see it |
| **D. Criterion recital** | stating the internal threshold instead of the finding | none | no — and it is not vocabulary at all |

The existing list covers A and B. **C is why the field manuscript leaked, and C is exactly
what no list can catch.**

### 12.3a Borrowed vocabulary — a risk §11.1 created

C2 deserves separate mention because the two-document architecture PUT the paper session in
the position where it happens. Session B's input is `record.tex`, the machinery's own
document, which uses the machinery's own words freely and correctly. The author is
therefore importing vocabulary from a document whose terms they did not define — the
hardest kind to catch, because it arrives pre-legitimised by its source.

§12.5 previously said the split "removes the pressure" on the vocabulary problem. Half
right: the pressure MOVED, from the document to the person reading it. The countermeasures
are stated where they act — the publish skill warns Session B that a word appearing in its
input is not a reason to use it in its output, and the reviewer is told to look for exactly
this.

C3 is a second thing class B cannot see. Class B catches a filename as a TOKEN
(`pubreqs.json` appearing in prose); it cannot catch a file used as an agent, because no
token appears at all. "The analysis says X" is ordinary English whose referent is a script.

### 12.4 D was conflated with the rest, and is a different defect

"The pre-registered acceptance of R² ≥ 0.15" was read as a vocabulary leak. It is not. A
researcher with a real pre-registration could write that sentence, so the stranger test
passes it. What is wrong with it is that it **reports the bookkeeping instead of the
result** — the reader is told what we required, not what we found. The repair is the one
that was actually applied by hand: state the finding and let it speak (`R^2 = -29` — worse
than predicting the mean). No vocabulary rule would have produced that repair, and adding
`pre-registered` to a list would have banned a word science wants.

Separating D out also resolves the tension flagged early in this work: pre-registration is
a *virtue* to advertise, not a term to hide.

### 12.5 Where each class belongs

- **A + B → the gate.** Mechanically detectable, near-zero false positives, and
  venue-independent — which is what makes them listable at all. APPLIED: the list now
  carries the machinery compounds (`claim status`, `evidence item`, `record digest`,
  `spec digest`, `record fidelity`, `frozen contract`, `frozen decision rule`,
  `pre-registered decision rule`, `research compiler`, `verify gate`), with a test that
  locks the restraint — eight sentences of correct scientific English using the words the
  field manuscript leaked must produce no findings.
- **C, C2, C3 → the authoring instruction, carrying the venue.** Only the author knows what
  a word refers to, and only the venue says who has to understand it. APPLIED: the publish
  skill states the venue test, its three outcomes, the leak classes (including the borrowed
  and files-as-concepts kinds), both non-fixes, and the two post-rewrite checks — re-verify
  the numbers survived, and read the opening cold.
- **The opening, cold → the reviewer.** APPLIED: `evaluator-conclusions` reads the title,
  abstract and first paragraphs as a reader of the frozen `venue`, BEFORE any declared
  conclusion, and reports terms that venue's reader would not know. It proposes no
  replacement words — a synonym leaves the sentence built around the old concept, so the
  repair is the author's rewrite.
- **D → the floor + the reviewer.** "State the strongest conclusion the record supports,
  plainly" already forbids reciting the criterion in place of the finding, and the blind
  reviewer (§11.4) reads for exactly this: a sentence that recites a threshold asserts
  nothing, and will be read as `proposed` against a declared `supported`.

The two-document split (§11.1) gives the definition one artifact with a clean boundary
instead of a document trying to be both — but see §12.3a: it moved the pressure onto the
paper session rather than removing it.

### 12.6 Status — APPLIED

All routes of §12.5 are wired. The A+B list extension shipped WITH the load-bearing half
rather than in place of it, which was the condition for shipping it at all.

What the engine can enforce: the venue-independent compounds, plus the two post-rewrite
checks the guideline can only ask a human to perform — that every number and claim survived
the rewrite (the number audit and the declaration checks REFUSE if they did not). What it
cannot: the venue-relative judgement, which is stated for the author, read for by an
advisory reviewer, and decided by neither alone.

Sources: the author's writing guideline (2026-09-08), and this document's §12.1-12.2
analysis, which that guideline completed.

---

## 13. First outside test (2026-09-09)

The same recorded result was written twice -- once under the pre-§11 protocol (A), once
under this one (B) -- and an external reviewer, given both and told nothing else, was asked
which was submittable.

| | A (old) | B (new) |
|---|---|---|
| belief-state enum visible to a reader | `supported`, `refuted` | none |
| tool-vocabulary gate | 4 findings | clean |
| body words | 301 | 1003 |
| record revises `refuted` -> `contested` | text changes silently, no gate fires | `verify` exits 1, names the passage to rewrite |

The reviewer chose B, on grounds the design did not anticipate and that are worth keeping:
A is unreproducible (no sizes, no distribution, no reference method), its criterion is
unauditable ("qualitative ... expert judgment"), it records a refutation without explaining
it, and its Discussion is a tautology. Its verdict -- *A is an audit log, B is a paper* --
is the §2 genre distinction reached independently from outside.

### 13.1 What it found that the machinery cannot

**An inferential overclaim.** B says the measured exponent is "below even the square-root
growth that independent rounding errors would produce". With one seed and five points that
claim is not supported. Every gate passed it: the numbers all trace to the record, so the
number audit was silent; the blind reviewer agreed with the declaration. **This is §11.4's
stated blind spot -- a discussion travelling further than the results support -- occurring
live on the first real paper.** It is the strongest evidence in this document that the
advisory human layer is load-bearing rather than decorative.

**No home for a deviation.** The pre-registered criterion for the first hypothesis was a
ratio, and the ratio proved uncomputable (its denominator measured exactly zero). B says so
honestly in prose, but sci-adk has nowhere to RECORD that a frozen criterion was departed
from. The record shows a supported claim and gives no sign that its stated test could not
be run. OPEN.

**Artifact ids in the manuscript.** FIXED (`986d180`) -- §12.5 had claimed class B was
gated and it was not. Provenance worth stating: that leak was the author's own sentence,
not something the old protocol forced; the record macros substitute their ids away. The gap
was real regardless, and nothing stopped it.

### 13.2 One claim of the review that does not hold

The review read A ("the decision rules are qualitative") against B ("two criteria were
fixed in advance") as a contradiction, and warned that submitting B with A attached would
destroy the credibility of the pre-registration. Checked against the record: both are true.
`decision_rule.kind` is `qualitative` with `params: None`, AND the thresholds sit inside the
frozen hypothesis STATEMENTS, written before any value was computed.

But the concern underneath it is right, and it is this document's own open item: **the
binding rule carries no threshold; the threshold lives only in prose.** An auditor holding
both documents would be right to ask which one binds. That is the four-pane path's
inability to express a numeric decision rule -- found from the inside during this test, and
rediscovered from the outside by a reader who had only the two manuscripts.

---

Version: 1.0 (§13 records the first outside test: two findings open, one fixed)
Source: author reading report + framing correction + the submission-boundary objection +
the definition-over-enumeration correction, 2026-08-31.
