# The manuscript is an argument, not a rendering of the record

> Status: **OD-R1 IMPLEMENTED (2026-08-31, v0.3)** on branch `feat/verdict-markup` —
> see §9. §1-§7 remain the diagnosis; §8 corrects two errors in it that surfaced during
> implementation; §10 lists what is still open.
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

## 9. OD-R1 — RESOLVED (implemented, branch `feat/verdict-markup`)

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

Version: 0.3 (OD-R1 resolved + implemented; §8 corrects the v0.2 audit)
Source: author reading report + framing correction, 2026-08-31; protocol audit and
implementation same date.
