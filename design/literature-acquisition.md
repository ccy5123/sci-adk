# sci-adk Literature Acquisition

> Status: v0.1 (2026-06-16). How sci-adk surveys and acquires prior work.
> Discovery = Claude's web_search (allowed tool); acquisition = paperforge.

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

## Code map

- `src/sci_adk/search/paperforge_adapter.py` -- `PaperforgeAdapter` (subprocess
  driver over the `paperforge` CLI; pinned SHA; provenance capture).
- `src/sci_adk/loop/literature_acquirer.py` -- `LiteratureAcquirer` /
  `acquire_literature` (the loop stage: DOIs -> PDFs + `LITERATURE` Evidence).
- `design/tool-policy.md` -- paperforge tool record + web_search discovery pairing.

---

Version: 0.1.0
Source: paperforge tool integration (2026-06-16)
Last Updated: 2026-06-16
