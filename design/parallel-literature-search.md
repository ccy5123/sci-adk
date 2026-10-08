# Parallel literature search

> Status: **v0.1 DRAFT (2026-10-08)** — design only; nothing here is built.
> Cross-references: `design/literature-acquisition.md` (discovery is the agent's job,
> acquisition is `paperforge`; the trigger model and `found_nothing` as a recorded null),
> the workspace skill `science-tool-academic-search` (how one search is conducted).

## 1. The question

The prior-art and novelty search at `/sci plan` is run by one `expert-literature` agent,
one (hypothesis × kind) unit after another. Can it run in parallel, and what does that
change besides speed?

## 2. What the code allows today

Measured on master `c1323c9`:

| Write | Shape | Safe to run concurrently? |
|---|---|---|
| decision and evidence items | one file each, id = timestamp + uuid (`loop/decision_record.py:88`) | yes |
| literature acquisition | rewrites the shared `references.bib` and `manifest.csv`, assigns `a/b` citation-key suffixes in arrival order (`loop/literature_acquirer.py:293`) | **no** — no file lock anywhere in `src/` |

So the searches can run in parallel; the recording verbs (`prior-work`, `novelty`,
`contested`, `add-literature`, `inquiry`) must not.

A second finding, independent of parallelism: **the record does not say how a search was
done.** `novelty --searched` stores the DOIs and the outcome; it has no field for which
indexes were queried, with which query strings, or which of them failed. A
`found_nothing` from one phrasing on one index and one from five phrasings on three
indexes are recorded identically. The search skill now asks the agent to return this in
its `Sources:` list, but that list is prose in a conversation, not record.

## 3. The pattern borrowed

Claude's `deep-research` skill already solves the same shape: several researchers run at
once, each writes only its own notes file, and one writer reads all notes and produces
the single output. No two agents write the same file, so no lock is needed.

What it does not carry over: its output is a prose report keyed by URL, it splits a
question into free-form subtopics, and "found nothing" becomes a sentence in a Gaps
section. sci-adk needs DOIs, the exact hypothesis text per kind, and a recorded null.

## 4. Proposed design

### 4.1 Units and searchers

- One searcher per (hypothesis × kind). A Spec with three hypotheses has six units.
- Each searcher must query at least two indexes and at least two phrasings of the
  hypothesis (the conduct in `science-tool-academic-search`).
- Optional redundancy: when there are few units (≤ 2), run two independent searchers on
  the same unit with different phrasings. Parallelism then buys fewer false nulls rather
  than speed.
- Cap concurrent searchers at 4. The public indexes rate-limit: Semantic Scholar
  refused every keyless request in testing (HTTP 429), and OpenAlex reports a per-request
  cost against a free allowance.
- Below 2 units, do not fan out: the token cost scales with the number of searchers and
  the time saved is nil.

### 4.2 The notes file

Each searcher writes one JSON file and nothing else:

`runs/<id>/literature/search-notes/<hypothesis>-<kind>[-<n>].json`

```json
{
  "hypothesis_id": "H1",
  "kind": "method",
  "searched_at": "2026-10-08T05:12:44Z",
  "queries": [
    {"index": "openalex", "query": "...", "status": "ok", "n_results": 138},
    {"index": "semantic_scholar", "query": "...", "status": "failed", "detail": "HTTP 429"}
  ],
  "candidates": [
    {"doi": "10.xxxx/...", "title": "...", "relevance": "same | related | unrelated",
     "basis": "one line: what in the paper matches or differs"}
  ],
  "proposed_outcome": "found-nothing | found-prior-art"
}
```

The searcher does not run any sci-adk verb.

### 4.3 The recorder

The orchestrator, alone and in sequence, after all searchers return:

1. Reads every notes file for a unit.
2. Records `found-prior-art` if any searcher marked a candidate `same`; otherwise
   `found-nothing` only if at least two indexes answered (`status: ok`) across the
   unit's searchers. If fewer answered, it does not record a null — it re-runs the search
   or records a skip with the reason.
3. Calls `sci-adk novelty --hypothesis <h> --kind <k> --searched <dois> --outcome ...
   --search-log <notes files>` (see 4.4), then moves to the next unit.

### 4.4 Engine change needed

Add `--search-log <file...>` to `prior-work`, `novelty`, `contested` and `inquiry`. The
verb validates each file against the 4.2 schema and stores the `queries` list and
`searched_at` on the decision item (a new optional field on `LiteratureDecision`, or on
`Provenance`). `verify` can then check that every `found_nothing` was produced by at
least two indexes that answered. That check is the main gain of this design and closes
the gap in §2 whether or not searches run in parallel.

The flag stays optional so existing runs and single-agent use keep working.

### 4.5 Timing rule

The rule is that the search is recorded at the moment it happens, before the Spec is
frozen, so its result cannot be fitted to experimental outcomes. Parallel search moves
the recording a few minutes after the search; it does not move it past the freeze, and
`searched_at` in the notes (stored by 4.4) keeps the actual search time on record. The
freeze must not start until every unit is recorded — the orchestrator already waits for
all searchers before step 4.3.

## 5. Not proposed

- **A file lock on literature acquisition.** One recorder makes it unnecessary. Revisit
  only if a second concurrent writer appears.
- **A search module in sci-adk.** Discovery stays the agent's job
  (`literature-acquisition.md`); the indexes are reached through WebFetch.
- **Parallel acquisition.** `paperforge` downloads one DOI after another
  (`paperforge/orchestrator.py:77`). Whether that is a bottleneck has not been measured;
  it is a separate change in a separate repository.

## 6. Open decisions

1. Where `queries`/`searched_at` live: on `LiteratureDecision` (hypothesis-bound
   decisions only) or on `Provenance` (also covers the Spec-bound prior-art decision).
2. Whether `verify` enforces the two-index rule for `found_nothing` (a gate) or reports it
   (an advisory). A gate would fail existing runs that recorded nulls without a log.
3. Whether the redundancy in 4.1 is default or opt-in.

---

Version: 0.1
