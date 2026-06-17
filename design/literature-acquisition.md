# sci-adk Literature Acquisition

> Status: v0.4 (2026-06-17). How sci-adk surveys and acquires prior work.
> Discovery = Claude's web_search (allowed tool); acquisition = paperforge.
> v0.2 added the discovery **trigger model** (graded triggers + a recorded
> search/skip decision + an F7 link). v0.3 IMPLEMENTS the novelty (High) and
> contested (Medium) triggers (the Spec-creation anchor was already implemented).
> **v0.4 reshapes the novelty trigger (A->B-replace):** novelty is no longer a
> run-HALT coupled to the experiment verdict -- it is a 1st-class revisable Claim
> derived by rule. The paper-render (Low) trigger remains deferred.

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
| Before **paper render** | at output | related-work *completeness*, not claim validity -- weakest and latest | Low | deferred |

**Minimal, highest-value first bite (shipped):** the **Spec-time prior-art check + a
skip record (with reason)** was the first cut. v0.3 added the next two
**incremental** triggers -- novelty (High) and contested (Medium) -- never pegged at
the same priority as the Spec anchor. **v0.4** reshaped the novelty trigger from a
run-HALT into a revisable rule-derived claim + a non-HALT compile-time checkpoint
(A->B-replace). The paper-render (Low) trigger stays deferred (weakest and latest;
related-work completeness, not claim validity).

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

**Implementation (v0.3).** The novelty (High) and contested (Medium) triggers are
now built, on top of the Spec-creation anchor. Each recording-type checkpoint
**reuses the judge rail's `Checkpoint` surface** (the typed `checkpoints/*.json`
discriminated union in `loop/verdict.py`): a recording-only checkpoint is that same
surface with no verdict trail, so the marginal cost is low. Concretely:

- **Novelty (High) -- v0.4 B-replace (a revisable claim, not a HALT).** `Hypothesis.novelty`
  remains a frozen anti-HARKing flag, but novelty is now **decoupled from the experiment
  claim** and is a **1st-class revisable Claim** `claim-novelty-<hyp>`, separate from the
  experiment claim `claim-<hyp>`. The status is derived by a PURE RULE
  `derive_novelty_status(hypothesis, novelty_decisions)` (in `core/validity.py`, no
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
  --outcome {found-nothing|found-prior-art} | --skip --reason "...")` and `sci-adk
  contested <run> --hypothesis <id> (--searched <dois...> | --note "...")`. For novelty,
  `--searched` and `--outcome` are required together (a recorded search records what it
  found; `found-nothing` -> `found_nothing`, `found-prior-art` -> `found_something`). The
  searched paths honor the same contact-email policy as `prior-work` (`ConfigHalt` by
  default, `--allow-no-email` to proceed degraded).

The paper-render (Low) trigger remains deferred.

**Novelty claim framing (convention).** Novelty claims are framed in the direction
they assert. A novel refutation (e.g. "first to show X does NOT cause Y") is set up as
a **negative hypothesis** ("X does not cause Y") and handled as SUPPORTED, so it passes
through the SUPPORTS-only novelty gate. **Explicit limitation:** if a novel refutation
is mis-framed as a REFUTED novelty claim it escapes the gate -- this residual is left
to the (future) substance-judge backstop, the same process-vs-substance limit as
elsewhere; no extra code/gate is built for it now.

## Code map

- `src/sci_adk/search/paperforge_adapter.py` -- `PaperforgeAdapter` (subprocess
  driver over the `paperforge` CLI; pinned SHA; provenance capture).
- `src/sci_adk/loop/literature_acquirer.py` -- `LiteratureAcquirer` /
  `acquire_literature` (the loop stage: DOIs -> PDFs + `LITERATURE` Evidence).
- `src/sci_adk/loop/prior_work.py` -- the Spec-creation prior-art trigger
  (`prior_work_open` / `record_prior_work_searched` / `record_prior_work_skip`).
- `src/sci_adk/loop/literature_triggers.py` -- the novelty (High) + contested (Medium)
  triggers (`record_novelty_searched` / `record_novelty_skip` / `record_contested` /
  `contested_open` / `contested_checkpoint`).
- `src/sci_adk/loop/decision_record.py` -- the single shared decision-writer reused by
  all three triggers (`write_decision_evidence`).
- `src/sci_adk/core/validity.py` -- `check_novelty_adequacy` (the novelty hard gate).
- `design/tool-policy.md` -- paperforge tool record + web_search discovery pairing.

---

Version: 0.3.0
Source: paperforge tool integration (2026-06-16); discovery trigger model decision (2026-06-16, design-only); novelty (High) + contested (Medium) triggers implemented (2026-06-17, render trigger still deferred)
Last Updated: 2026-06-17
