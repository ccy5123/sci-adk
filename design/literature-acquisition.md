# sci-adk Literature Acquisition

> Status: v0.6 (2026-06-18). How sci-adk surveys and acquires prior work.
> Discovery = Claude's web_search (allowed tool); acquisition = paperforge.
> v0.2 added the discovery **trigger model** (graded triggers + a recorded
> search/skip decision + an F7 link). v0.3 IMPLEMENTS the novelty (High) and
> contested (Medium) triggers (the Spec-creation anchor was already implemented).
> **v0.4 reshapes the novelty trigger (A->B-replace):** novelty is no longer a
> run-HALT coupled to the experiment verdict -- it is a 1st-class revisable Claim
> derived by rule. **v0.5 lays down the 2-kind Novelty definition** (result-novelty +
> method-novelty, independent; see "Novelty -- definition") as the agreed refinement of
> the single-flag implementation. **v0.6 IMPLEMENTS the 2-kind core (N1):** the single
> `Hypothesis.novelty` flag is replaced by independent `novelty_result` / `novelty_method`
> (hard migration, no back-compat); per-{hyp, kind} claims, decisions, derivation, and the
> CLI `--kind` flag are now live. The render-time `\novelty{}` markup + scoped-render (N2)
> and the render/verify novelty GATE (N3) remain deferred. The paper-render (Low) novelty
> gate remains deferred.

sci-adk acquires the literature the way a researcher does: when starting, when
unsure, or when checking whether something has already been done, you *search*
for the key papers, then *pull* the ones you need. sci-adk splits this into two
honestly separated halves.

## Two halves: discovery vs acquisition

| Half | Who does it | Tool | Output |
|------|-------------|------|--------|
| **Discovery** | Claude (the agent), on-demand | native `web_search` (+ `web_fetch`) | a DOI list of key papers |
| **Acquisition** | the loop stage | paperforge via `search/paperforge_adapter.py` | OA PDFs + a `LITERATURE` EvidenceItem |

**Discovery is not a code module.** It is Claude using `web_search` at
orchestration time -- an allowed tool (design/tool-policy.md). Claude reliably
turns a topic into a list of key papers and reasonably trustworthy DOIs; that is
the front-end. Building an arXiv/S2 discovery subsystem is deliberately *not*
done here (tool-policy conservatism: add surface only when needed).

**Acquisition is code.** Given a DOI list, paperforge resolves each DOI through
an OA fallback chain (arXiv -> Unpaywall -> OpenAlex -> Europe PMC -> Semantic
Scholar), verifies each PDF by its `%PDF-` magic bytes, and writes a resumable
manifest. See design/tool-policy.md (addendum 2026-06-16).

## The flow

```
topic / question
   │  Claude web_search  (discovery -- agent action, on-demand)
   ▼
DOI list  (e.g. ["10.48550/arXiv.1706.03762", ...])
   │  LiteratureAcquirer.acquire(dois)   (acquisition -- loop stage)
   ▼
runs/<spec.id>/literature/      OA PDFs + manifest.csv + .json sidecars
runs/<spec.id>/evidence/        a LITERATURE EvidenceItem (the record)
```

## Two entry points

- **Ad-hoc survey (pre-Spec).** Before a Spec exists -- "has this been done?" --
  call `PaperforgeAdapter.fetch(dois, out_dir)` directly with any output dir. No
  Spec, no Evidence; just the PDFs + manifest for a quick look.
- **In-run acquisition (with a Spec).** Inside a research run, use
  `LiteratureAcquirer(spec, workspace_dir).acquire(dois)` (or the
  `acquire_literature(...)` convenience). This deposits PDFs under
  `runs/<spec.id>/literature/` and records a `LITERATURE` EvidenceItem in the
  append-only log -- so the prior-work survey is part of the scientific record.

## Acquisition records what was acquired, not belief

A `LITERATURE` EvidenceItem records *which papers were obtained* (DOIs, OA
source, license, filename) and the paperforge provenance (pinned SHA, version,
exit code, manifest path). It asserts no support/refute direction: `bears_on` is
empty unless the caller passes a `target_id`, in which case a single **NEUTRAL**
bearing links the survey to a hypothesis as context. Judging whether a paper
supports or refutes a hypothesis is a separate, later step (its own Evidence) --
acquisition is record, not belief (design/abstractions.md).

A failed DOI (no downloadable OA PDF) is a valid outcome recorded in the
finding, not an error (Invariant E2: null results are results).

## Halt gates (hand back to the human)

Acquisition can stop the loop and ask the human, returning a structured
`AcquisitionHalt` (the orchestrator surfaces it via AskUserQuestion and halts --
sci-adk runtime code never prompts the user directly). Two conditions:

1. **Unacquired papers (mechanical).** The whole DOI batch is still attempted
   and recorded, then if *any* DOI had no downloadable OA PDF,
   `acquire(...)` returns an `AcquisitionOutcome` whose `halt`
   (`reason=UNACQUIRED_PAPERS`) lists the misses with their reasons. The
   orchestrator feeds that list back to the user and stops -- it does not
   silently proceed on a partial corpus.
2. **Supporting Information needed (agent-judged).** After Claude reads a main
   text and judges the paper's **SI** (Supporting Information) is required, it
   builds `AcquisitionHalt.for_supporting_info([...])` and halts. This is a
   judgment, not a mechanical check -- paperforge fetches the main OA PDF, not
   the SI -- so the agent raises it; this module only provides the halt type.

```
outcome = acquire_literature(spec, dois, ...)
if outcome.should_halt:          # condition 1: some DOIs unacquired
    feed back outcome.halt.feedback() to the user; STOP the loop
# ... Claude reads main texts ...
if SI is required (agent judgment):   # condition 2
    halt = AcquisitionHalt.for_supporting_info([...]); feed back; STOP
```

Both halts are first-class "ask the human" gates, consistent with sci-adk's
human-checkpoint discipline: when the autonomous flow hits a wall (a paper it
cannot get, or data that lives only in the SI), it surfaces rather than guesses.

## Discovery trigger model -- graded triggers + a decision record

Discovery stays **agent on-demand** (the "Two halves" model): Claude calls
`web_search` when its judgment says prior work matters. We deliberately do **not**
add a periodic "check literature?" flag on every loop iteration -- that would
reverse the tool-policy conservatism above and is mostly noise (discovery is not
loop-bound; it matters at a few research-meaningful moments, not every compile).

What we **do** add closes a real gap: today the *decision* to check prior work is
invisible. Acquisition is fully recorded (a `LITERATURE` EvidenceItem, provenance,
halts), but the front-half decision leaves no trace -- if the agent never searches,
nothing in the record shows whether prior work was even considered. In a system
whose spine is record!=belief and "null results are results" (Invariant E2),
**not searching is itself a recorded null**: the discovery decision must be in the
record, or rigor breaks exactly at the trigger.

So at the trigger moments below, the agent surfaces a **recording-type checkpoint**
capturing the decision -- *searched* (which flows into the existing acquisition +
`LITERATURE` Evidence) or *skipped, with a reason* (a recorded null). This records
a decision, not a belief; it asserts no support/refute direction.

### The triggers are NOT equal weight

| Trigger | Fires | Why it matters | Weight | Status |
|---------|-------|----------------|--------|--------|
| **Spec creation** (prior-art) | before any result exists | pre-registration canonical; zero post-hoc risk -- the cleanest, most important check ("has this been done?") | **Primary anchor** | implemented |
| Before a **novelty / priority** claim | when asserting "new / first" | underwrites the *validity* of the claim | High | implemented (v0.4: B-replace -- a revisable claim, not a HALT) |
| Claim -> **contested** | after evidence conflicts | here the rigor is **recording, not searching**: a timestamp so literature that arrived *after* the conflict stays visible (anti post-hoc-rationalization -- no hunting for favorable papers once the result is known) | Medium | implemented |
| **Emergent question** (mid-research) | when a NEW question arises DURING the run | researcher-like on-demand discovery -- the ad-hoc "wait, has anyone done this?" moment; keeps the record honest about what was considered mid-stream | On-demand (agent-raised) | implemented (v0.5, `INQUIRY_DECISION` + `sci-adk inquiry`) |
| Before **paper render** | at output | related-work *completeness*, not claim validity -- weakest and latest | Low | deferred |

**Minimal, highest-value first bite (shipped):** the **Spec-time prior-art check + a
skip record (with reason)** was the first cut. v0.3 added the next two
**incremental** triggers -- novelty (High) and contested (Medium) -- never pegged at
the same priority as the Spec anchor. **v0.4** reshaped the novelty trigger from a
run-HALT into a revisable rule-derived claim + a non-HALT compile-time checkpoint
(A->B-replace). The paper-render (Low) trigger stays deferred (weakest and latest;
related-work completeness, not claim validity).

**v0.5 (enforcement, field-report follow-up):** the Spec-anchor decision was recorded but
never *enforced* -- a run could reach a passing `verify` (and an autonomous flow could run
experiments) with the prior-work decision still open, so an external run "started research"
with no literature check and nothing caught it. v0.5 makes the anchor un-skippable WITHOUT
reversing the "record the decision, do not force a search" principle (a skip-with-reason
still clears it):
- **verify gate (always on):** a conclusion-bearing run (a rendered `paper/draft.tex`) whose
  prior-work decision is still open FAILS `paper_requirements_clean` -- you cannot publish
  without the decision in the record. Pre-paper exploratory runs are unaffected (reuses the
  conclusion-bearing scoping).
- **experiment-start halt (opt-in):** `compile(enforce_prior_work=True)` (the orchestrated
  "start research" path -- `sci-adk run --enforce-prior-work`) raises `PriorWorkHalt` BEFORE
  running experiments while the decision is open. The run dir + Spec are already laid down, so
  the human records the decision (`sci-adk prior-work <run> --searched … | --skip --reason …`)
  and re-runs -- search FIRST, like a researcher. The raw `compile()` default is unchanged
  (`enforce_prior_work=False`) so library/primitive callers are not forced.
This still forces a DECISION, never a search (E2: a skip is a recorded null). Source:
`docs/field-report-triage.md` (concern 1).

**v0.5 (emergent-question trigger, field-report concern 2):** the triggers above all fire
at *fixed* moments (Spec creation, a novelty claim, a contested claim). A real researcher
also stops MID-stream -- "wait, has anyone measured X?" -- and that emergent moment had no
recording rail. v0.5 adds the **emergent-question trigger**: `EvidenceKind.INQUIRY_DECISION`
+ `sci-adk inquiry <run> --question "<q>" (--searched <dois> | --skip --reason …)`. It is a
*recording-type* decision (searched -> LITERATURE + INQUIRY_DECISION; skipped -> a recorded
null), the same family as the others (`bears_on=[]`, excluded from the reproduction-bundle
requirement). This does NOT contradict the "no periodic prompt" rule above: the inquiry is
**agent-raised on judgment**, not a per-loop flag. The autonomous behavioral wiring lives in
the workspace `CLAUDE.md` + the experiment SKILL (search the question, then record). Source:
`docs/field-report-triage.md` (concern 2).

### When found literature touches a frozen element -> Spec amendment (F7)

Recording the *decision* is not enough. If newly found prior work means a
**frozen** element must change -- a baseline, a `DecisionRule` criterion, or a
novelty claim -- it must **not** be edited silently. It goes through the
human-only Spec amendment path (F7, `checkpoints/<spec>.amend.json`: logged with a
rationale, prior Spec + its Evidence preserved; see
`design/rigor-shell-architecture.md` Sec.7.2 / Sec.8 F7). The **contested** trigger
frequently meets this case (you find work that undercuts a frozen baseline).
Rule: **a search result that touches frozen ==> F7, never a silent edit.**

### Relationship to the halt gates, and to implementation

This decision checkpoint is **proactive** (recorded at a trigger, before/around
discovery); the "Halt gates" above are **reactive** (raised after an acquisition
attempt -- an OA miss, or SI needed). They are complementary surfaces, not the
same mechanism.

## Novelty — definition (2-kind; agreed 2026-06-18)

> This is the AGREED conceptual definition. It is now IMPLEMENTED in the 2-kind core
> (N1, v0.6): the single `Hypothesis.novelty` flag is replaced by independent
> `novelty_result` / `novelty_method`, each backed by a per-{hyp, kind}
> `claim-novelty-result-<hyp>` / `claim-novelty-method-<hyp>`, a `NOVELTY_DECISION.kind`,
> and `derive_novelty_status(hyp, kind, ...)`. The render-time markup + scoped-render (N2)
> and the render/verify novelty gate (N3) remain pending.

**Novelty** in sci-adk is a revisable, **literature-referent** Claim that, as of a
recorded prior-art search, **no prior published work establishes a specified aspect of a
hypothesis**. It is a claim ABOUT the state of published knowledge (referent = the
literature) — distinct from the experiment claim (referent = nature) and from formal
claims — and independent of the experiment verdict (B-replace).

Two **independent** kinds, each separately pre-registered, searched, derived, and revised:

- **result-novelty(hyp)** — no prior published work has established hyp's RESULT (its
  `statement`/conclusion).
- **method-novelty(hyp)** — no prior published work has used hyp's METHOD (its approach).

The axes are orthogonal — all four quadrants are meaningful: known-result/new-method
(e.g. a simpler proof of a known theorem), new-result/known-method (e.g. a known technique
applied to a new target), both-new, neither.

Defining properties (per kind):
1. **Referent = the literature** (state of published knowledge), not nature — so a "novel
   refutation" is naturally experiment-REFUTED + novelty-SUPPORTED.
2. **Absence claim → searched, never proven.** Intrinsically scoped "to our knowledge, as
   of the recorded search"; never absolute priority.
3. **SUPPORTED iff** a `NOVELTY_DECISION` bound to {hyp, kind} recorded outcome
   `found_nothing` (safety floor — `found_something`/skip/absent → PROPOSED).
4. **Pre-registered (anti-HARKing):** the {hyp, kind} flag is frozen in the Spec before
   results; dropping it is a human-only F7 amendment, never a silent edit.
5. **Revisable / non-monotone:** new prior art demotes it; `sci-adk verify` re-derives the
   status from the record (deleted/tampered decision → DIVERGED).

**Boundary — what the gate does NOT adjudicate.** sci-adk does not decide whether a found
paper is *really* "the same" result/method — that semantic judgment lives in the recorded
search (the searched DOIs + the searcher's recorded outcome). The (future) gate is purely
deterministic: it checks that a `found_nothing` search of the right {hyp, kind} is on
record. Likewise sci-adk does not adjudicate **significance/importance** (a value
judgment) — only novelty (a recordable literature-absence claim).

**Structural changes from the single-flag model (IMPLEMENTED in N1, v0.6 — the "current (single)" column is now historical/removed):**

| element | current (single) | 2-kind |
|---------|------------------|--------|
| Spec `Hypothesis` | `novelty: bool` | `novelty_result: bool` + `novelty_method: bool` (frozen) |
| Claim | `claim-novelty-<hyp>` | `claim-novelty-result-<hyp>` / `claim-novelty-method-<hyp>` (flagged kinds only) |
| `NOVELTY_DECISION` | hyp-bound | + `kind: result \| method` |
| `derive_novelty_status` | per hyp | per {hyp, kind} |
| CLI | `sci-adk novelty <run> --hypothesis <id> ...` | `... --kind {result\|method}` |
| (future) render markup — STILL PENDING (N2) | `\novelty{hyp}{text}` | `\novelty{result\|method}{hyp}{text}` |

### Render-time novelty gate (design agreed 2026-06-18; implementation pending)

The gate enforces that the paper (belief) never asserts a novelty/priority claim the record
does not back. Same family as the evidence-validity gate (synthetic data cannot make a
SUPPORTED empirical claim) and the paper-consistency gate (a dangling `\ref` fails verify).

**Detection — explicit markup only (deterministic).** A novelty/priority claim is asserted
in the paper ONLY via `\novelty{result|method}{hyp-id}{text}` (never inferred from free
prose — no keyword scan, no NLP). This mirrors the `\ref`↔`\label` gate: the engine checks
markup against the record deterministically. The honest limit (as with `\ref`): a "first"
written as plain prose is not governed — the discipline is "assert novelty via the command".

**Action — HARD fail on unsupported + scoped-render on supported.** For each
`\novelty{kind}{hyp}{text}` the engine looks up `claim-novelty-{kind}-{hyp}`:
- **SUPPORTED** → render `text` **plus an honest scope auto-derived FROM the record** — "to
  our knowledge, as of <search date from the backing `NOVELTY_DECISION`>". This is the
  engine rendering FROM the record (the good kind of "hedge"), not editing belief: the
  intrinsic "to our knowledge, as of the search" bound (definition property 2) is attached
  deterministically from the recorded search, never invented.
- **NOT SUPPORTED** → HARD fail: a render error / non-zero `sci-adk verify`, naming
  {hyp, kind} and the remedy (record a `found_nothing` search via
  `sci-adk novelty <run> --hypothesis <hyp> --kind <kind> --searched ... --outcome found-nothing`,
  or remove the assertion). The engine never softens or rewrites the author's claim — it
  refuses to emit an unbacked one. (Auto-"hedging" an unsearched claim with "to our
  knowledge" would be dishonest — it implies a search that never happened — so it is NOT a
  fallback; hedging belongs only to the SUPPORTED render above.)

**Placement (O-B-style):** a PURE checker used at render time (compiler) AND re-run by
`sci-adk verify` headless. Recommended so verify can re-scan: emit `\novelty{}` as a
preamble `\newcommand` macro that survives into the persisted `.tex` (LaTeX expands it; the
record-derived scope string is baked in at render), so `verify` re-derives the novelty claim
statuses from the persisted `NOVELTY_DECISION`s and re-checks every `\novelty{}` in the
`.tex` against them — symmetry with the `\ref`↔`\label` re-scan. (Stage note: "the run never
HALTs on novelty" is the experiment LOOP; this render/verify gate is the OUTPUT stage — no
contradiction.)

**Boundary unchanged:** the gate checks only that a `found_nothing` search of the right
{hyp, kind} is on record — never semantic "same-ness" (the searcher's recorded judgment) or
significance.

The 2-kind migration this gate depends on is now implemented (N1, v0.6), so the markup +
gate (N2/N3) remain to be built on top of the now-live `claim-novelty-{kind}-{hyp}`
primitives (markup carries `kind`; the gate keys on `claim-novelty-{kind}-{hyp}`).

**Implementation (v0.6, N1 — 2-kind core).** The conceptual 2-kind definition above is
now the implemented core (the v0.3/v0.4 single-flag narrative that follows is preserved as
the evolution record). Concretely: the single `Hypothesis.novelty` flag → independent
`novelty_result` / `novelty_method`; `claim-novelty-<hyp>` → `claim-novelty-{kind}-<hyp>`
(only for set kinds); every `NOVELTY_DECISION` carries `kind`; `derive_novelty_status` is
per-{hyp, kind} (SUPPORTED iff a matching {hyp, kind} `found_nothing` decision is on record,
the `kind==` match load-bearing); the CLI gained a **required** `--kind {result|method}`;
and `sci-adk verify` re-derives per kind (DIVERGED when only the OTHER kind's `found_nothing`
exists). This was a **hard migration (no back-compat alias)** — the old single flag is not
auto-mapped onto either kind — and is independently verified (997 tests). N2 (the render-time
`\novelty{}` markup + scoped-render) and N3 (the render/verify novelty gate) remain deferred.

**Implementation (v0.3).** The novelty (High) and contested (Medium) triggers are
now built, on top of the Spec-creation anchor. Each recording-type checkpoint
**reuses the judge rail's `Checkpoint` surface** (the typed `checkpoints/*.json`
discriminated union in `loop/verdict.py`): a recording-only checkpoint is that same
surface with no verdict trail, so the marginal cost is low. Concretely:

- **Novelty (High) -- v0.4 B-replace (a revisable claim, not a HALT).** `Hypothesis.novelty`
  (v0.6: now per-{hyp, kind} `novelty_result` / `novelty_method`) remains a frozen
  anti-HARKing flag, but novelty is now **decoupled from the experiment
  claim** and is a **1st-class revisable Claim** `claim-novelty-<hyp>` (v0.6: now
  `claim-novelty-{kind}-<hyp>`), separate from the
  experiment claim `claim-<hyp>`. The status is derived by a PURE RULE
  `derive_novelty_status(hypothesis, novelty_decisions)` (v0.6: now per-{hyp, kind}
  `derive_novelty_status(hyp, kind, novelty_decisions)`) (in `core/validity.py`, no
  raise): **SUPPORTED iff** a recorded `NOVELTY_DECISION` bound to the hypothesis has
  outcome `found_nothing` (a prior-art search that returned nothing); otherwise
  **PROPOSED** (no decision, a `skipped` one, or a `found_something` one). The searched
  outcome is split into `found_nothing` / `found_something`; **SUPPORTED-iff-found_nothing**
  is the safety floor -- a `found_something` decision **never** yields SUPPORTED (active
  `refuted` promotion is deferred with render). **The run never HALTs on novelty.**
  Instead, while the novelty claim is PROPOSED the compiler surfaces a **NON-HALT**
  `NoveltyCheckpoint` (the compile proceeds normally), with a **reason-tailored** prompt:
  `not_searched` (no decision / a skip) tells the agent to search prior art and record
  the outcome or drop the flag via an F7 amendment; `found_something` tells the agent the
  search is done and the escape is the F7 amendment (it does **not** say "go search").
  Dropping the flag is a human-only Spec amendment (F7) -- never a silent edit. `sci-adk
  verify` RE-DERIVES the novelty status from the record: a SUPPORTED `claim-novelty-<hyp>`
  (v0.6: now per-{hyp, kind} `claim-novelty-{kind}-<hyp>`)
  whose `found_nothing` decision was deleted (or a `found_something` tampered to
  `found_nothing`) is reported DIVERGED. The render `first`-gate + hedge reporting remain
  **DEFERRED** (this milestone is render-free).
- **Contested (Medium)** is a hypothesis-bound *recording* trigger -- **no gate, no
  halt**. When a Claim is/becomes CONTESTED the run path surfaces an open
  `ContestedCheckpoint`; `record_contested` writes a `CONTESTED_RECORD` (the
  anti-post-hoc timestamp is the append-only `created_at`), optionally acquiring DOIs.
- Both write through a single shared decision-writer (`loop/decision_record.py`) and
  use separate `EvidenceKind`s (`NOVELTY_DECISION` / `CONTESTED_RECORD`), so the
  Spec-creation `prior_work_open` closing-kind anchor (which keys only on
  `PRIOR_WORK_DECISION`) is unchanged.
- The CLI verbs are `sci-adk novelty <run> --hypothesis <id> (--searched <dois...>
  --outcome {found-nothing|found-prior-art} | --skip --reason "...")` (v0.6: now also takes
  a **required** `--kind {result|method}`) and `sci-adk
  contested <run> --hypothesis <id> (--searched <dois...> | --note "...")`. For novelty,
  `--searched` and `--outcome` are required together (a recorded search records what it
  found; `found-nothing` -> `found_nothing`, `found-prior-art` -> `found_something`). The
  searched paths honor the same contact-email policy as `prior-work` (`ConfigHalt` by
  default, `--allow-no-email` to proceed degraded).

The paper-render (Low) trigger remains deferred.

**Novelty claim framing (B-replace).** Because the novelty claim `claim-novelty-<hyp>`
is **decoupled from the experiment claim**, positive-framing tricks are no longer
needed. The experiment claim may be SUPPORTED or REFUTED on its own merits; the novelty
claim is independently derived from whether a `found_nothing` prior-art search was
recorded — regardless of the experiment direction. A "novel refutation" (e.g. "first
to show X does NOT cause Y") is handled naturally: the experiment claim is REFUTED (the
experiment worked as intended) while the novelty claim is SUPPORTED if a
`found_nothing` search is on record. No positive-hypothesis re-framing required; the
old SUPPORTS-only gate was an artifact of the A-design and is removed in B-replace.

## Code map

- `src/sci_adk/search/paperforge_adapter.py` -- `PaperforgeAdapter` (subprocess
  driver over the `paperforge` CLI; pinned SHA; provenance capture).
- `src/sci_adk/loop/literature_acquirer.py` -- `LiteratureAcquirer` /
  `acquire_literature` (the loop stage: DOIs -> PDFs + `LITERATURE` Evidence).
- `src/sci_adk/loop/prior_work.py` -- the Spec-creation prior-art trigger
  (`prior_work_open` / `record_prior_work_searched` / `record_prior_work_skip`).
- `src/sci_adk/loop/literature_triggers.py` -- the novelty (High) + contested (Medium)
  triggers (`record_novelty_searched` / `record_novelty_skip` / `record_contested` /
  `contested_open` / `contested_checkpoint`); v0.6: the novelty recorders/predicates
  (`record_novelty_searched` / `record_novelty_skip` / `novelty_open` / `novelty_checkpoint`
  / `novelty_reason_from_decisions`) now take `kind`.
- `src/sci_adk/loop/decision_record.py` -- the single shared decision-writer reused by
  all three triggers (`write_decision_evidence`).
- `src/sci_adk/core/validity.py` -- `derive_novelty_status(hyp, kind, novelty_decisions)` (the pure novelty-status rule, now per-{hyp, kind}; the old `check_novelty_adequacy` HALT was removed in B-replace).
- `design/tool-policy.md` -- paperforge tool record + web_search discovery pairing.

---

Version: 0.6.0
Source: paperforge tool integration (2026-06-16); discovery trigger model decision (2026-06-16, design-only); novelty (High) + contested (Medium) triggers implemented (2026-06-17); novelty B-replace (decoupled claim, non-HALT) + code map corrections (2026-06-18); 2-kind Novelty core (N1) implemented — hard migration, no back-compat (2026-06-18)
Last Updated: 2026-06-18
