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
