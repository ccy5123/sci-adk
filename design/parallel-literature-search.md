# Parallel literature search

> Status: **v0.3 (2026-10-08)** — all of §4 is applied: the search log (§4.4) in the
> engine, the parallel searchers and the single recorder (§4.1–4.3) in the workspace
> instructions. §6 decisions all taken. Not yet exercised on a real research run.
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
- Redundancy is automatic when there are 1 or 2 units: two independent searchers per
  unit, told to use different phrasings and a different first index. With so few units
  parallelism saves no time, so it is spent on fewer false nulls instead. With 3 or more
  units, one searcher each.
- Cap concurrent searchers at 4. The public indexes rate-limit: Semantic Scholar
  refused every keyless request in testing (HTTP 429), and OpenAlex reports a per-request
  cost against a free allowance. Two units with two searchers each fill the cap exactly.
- No units (the draft proposes no novelty): one `expert-literature` in its normal mode
  runs the Spec-level prior-art search and records it.

Searchers are `expert-literature` in a second mode, not a new agent: the prompt names one
unit and a log path, and the agent then searches only and runs no verb.

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
2. Records `found-prior-art`, passing the `same` DOIs, if any searcher marked a
   candidate `same`. Otherwise `found-nothing` only if at least two distinct indexes
   answered (`status: ok`) across the unit's logs, passing the `related` DOIs (the
   nearest work examined) to `--searched`, which requires at least one DOI. If fewer
   answered, it re-spawns one searcher for the unit, once; if that still falls short, it
   records a skip whose reason names the failed indexes.
3. Calls `sci-adk novelty --hypothesis <h> --kind <k> --searched <dois> --outcome ...
   --search-log <notes files>` (see 4.4), then moves to the next unit.
4. After every unit: one Spec-level `sci-adk prior-work --searched <all same and
   related DOIs> --search-log <all log files>`. Only then does `manager-prereg` freeze.

Applied to the workspace templates: `/sci plan` step 2 (`skills/sci/SKILL.md`),
`expert-literature` (its searcher mode), `science-orchestrator` Stage 2, and the log path
in `science-tool-academic-search`.

### 4.4 Engine change (implemented)

`prior-work`, `novelty`, `contested` and `inquiry` accept `--search-log <file...>` on the
searched path only (refused with `--skip`, and on `contested` without `--searched`). Each
file is validated against the 4.2 schema (`src/sci_adk/core/search_log.py`: unknown
fields, an empty `queries` list, a status other than `ok`/`failed`, or a `searched_at`
that is not ISO-8601 UTC are refused) before anything is acquired or written. For
`novelty` and `contested`, a file's `hypothesis_id`/`kind`, when present, must match
`--hypothesis`/`--kind`. A refused log records nothing.

The decision item stores the log on `Provenance.search_log`: one `searched_at` per file,
and the `queries` and `candidates` of all files concatenated in file order. The field is
optional; evidence written before it existed loads unchanged.

`verify` applies a two-index rule to every novelty decision with outcome `found_nothing`:

- a log in which fewer than two distinct indexes (case-insensitive) answered a query
  (`status: ok`) fails the run (`VerifyReport.search_log_problems`, part of `passed`);
- no log at all produces one advisory line naming the hypothesis and kind
  (`VerifyReport.paper_advisory`); it never affects `passed`, so runs recorded before the
  flag existed keep passing.

The rule is judged per {hypothesis, kind}, the unit a novelty claim derives from
(`derive_novelty_status`: SUPPORTED if ANY `found_nothing` of that unit exists). One
decision whose log shows two answering indexes clears the unit, whatever else it holds.
Without this, a weak null recorded early could never be cured: the record is
append-only, so re-searching soundly and re-recording must be enough.

Prior-work, contested and inquiry decisions have no `found_nothing` outcome; their logs
are stored and not checked.

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

## 6. Decisions

1. **Decided: on `Provenance`.** This also covers the Spec-bound prior-work decision,
   which carries no `LiteratureDecision`. Implemented as `Provenance.search_log` (§4.4).
2. **Decided: a gate when a log exists, an advisory when none does.** A `found_nothing`
   whose log shows fewer than two answering indexes fails `verify`; a `found_nothing`
   with no log gets an advisory line, so existing runs are not failed retroactively.
   Implemented (§4.4).
3. **Decided: automatic for 1–2 units.** Two searchers per unit when there are one or
   two units; one per unit from three. Applied (§4.1).

---

Version: 0.3
