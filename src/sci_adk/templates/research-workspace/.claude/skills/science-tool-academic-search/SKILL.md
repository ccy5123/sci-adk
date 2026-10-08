---
name: science-tool-academic-search
description: >
  sci-adk academic-search tool knowledge: how to conduct a prior-art / novelty search per
  (hypothesis × kind) against the exact draft-Spec hypothesis text — the public academic
  indexes (OpenAlex, arXiv, Crossref; Semantic Scholar when it answers) queried through
  WebFetch, plus the open web, with a recorded search date ("as of <date>") and
  found_nothing recorded as a result. The conduct behind the novelty decision; the record is written by the prereg
  verbs. Loaded by the sci hub at /sci plan and by expert-literature. Builds on
  science-foundation-rigor; the freeze procedure is science-workflow-prereg.
license: Apache-2.0
compatibility: Designed for Claude Code
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch
user-invocable: false
metadata:
  version: "1.0.0"
  category: "tool"
  status: "active"
  updated: "2026-06-25"
  modularized: "false"
  tags: "sci-adk, academic-search, prior-art, novelty, arxiv, semantic-scholar, literature, search-date, found-nothing, openalex, crossref, result-kind, method-kind"

# MoAI Extension: Progressive Disclosure
progressive_disclosure:
  enabled: true
  level1_tokens: 100
  level2_tokens: 5000

# MoAI Extension: Triggers
triggers:
  keywords: ["prior art", "prior-work", "novelty search", "literature search", "arxiv", "semantic scholar", "academic search", "found nothing", "search date", "result novelty", "method novelty"]
  agents: ["expert-literature"]
  phases: ["plan"]
---

# science-tool-academic-search — Prior-art / Novelty Search Conduct

How to CONDUCT the prior-art and novelty search that backs a sci-adk novelty decision.
This is the search craft only; the freeze workflow (two-pass plan, setting the novelty
flags) is `science-workflow-prereg`, and the record is written by the verbs
(`sci-adk prior-work`, `sci-adk novelty --kind {result|method}`) — never by hand.

## Quick Reference (30 seconds)

- **Search the exact hypothesis text, per kind.** Two ORTHOGONAL kinds — `result`
  (the conclusion) and `method` (the approach) — are searched and recorded
  INDEPENDENTLY. A `found_nothing` for one kind never satisfies the other.
- **Search at the trigger moment.** The search runs at pre-registration, against the
  DRAFT Spec, BEFORE the freeze — never retrofitted after results are in (anti-HARKing).
- **Record the search date.** Every novelty decision is "as of <search date>"; the engine
  later renders an honest "to our knowledge, as of <date>" scope from it.
- **`found_nothing` IS a result.** An affirmative recorded null ("a real search of the
  right {hypothesis, kind} found no prior art") — not "nothing found, move on".

## Implementation Guide (5 minutes)

### Sources and order

Search the academic record, then the open web, against the DRAFT Spec's exact hypothesis
text for the kind in hand. Discovery is your job, not a sci-adk module: no academic-search
server ships with this workspace. Query the indexes' public APIs directly with WebFetch —
they need no key, and they are the same services `paperforge` already uses to acquire
the DOIs you find, so nothing new is added to the toolchain.

| Index | Query (URL-encode the terms) | Use it for | Watch for |
|---|---|---|---|
| **OpenAlex** | `https://api.openalex.org/works?filter=title_and_abstract.search:<terms>&per-page=25&select=doi,title,publication_year` | the main cross-publisher sweep; returns DOIs | `search=` matches full text and is far too broad — use the title-and-abstract filter |
| **arXiv** | `https://export.arxiv.org/api/query?search_query=abs:"<phrase>"+AND+abs:<term>&max_results=25` | preprints, closest to the frontier | bare words are OR-ed together — quote phrases and join with `AND` |
| **Crossref** | `https://api.crossref.org/works?query.bibliographic=<terms>&rows=25&select=DOI,title,issued` | DOI coverage OpenAlex misses | loose relevance ranking — a candidate source, never a null; supplementary files carry their own DOIs (e.g. a `.s003` suffix) — pass the article's DOI, not the file's |
| **Semantic Scholar** | `https://api.semanticscholar.org/graph/v1/paper/search?query=<terms>&limit=25&fields=title,year,externalIds` | citation-graph follow-up | often refuses keyless requests (HTTP 429); if it does, say so — it was not searched |
| **WebSearch** | — | official venues, journal pages, grey literature the indexes miss | verify each candidate against its primary source |

If a contact email is configured for acquisition (`UNPAYWALL_EMAIL`), add
`&mailto=<that address>` to the OpenAlex and Crossref queries; both then serve you from
their faster, more reliable pool.

Search the precise hypothesis statement, not a paraphrase — a vague query manufactures a
false `found_nothing`. Then run at least one rephrasing (synonyms, the field's other name
for the method) on a second index: one phrasing on one index is not a search.

### Per (hypothesis × kind)

For EACH hypothesis, search EACH kind on its own:
- `result` — has this statement / conclusion been established before?
- `method` — has this approach been used before (even toward a different conclusion)?

Adjudicate only what you can: whether a `found_nothing` search of the right
{hypothesis, kind} exists, plus your RECORDED judgment of relevance / same-ness. You do
NOT adjudicate significance. The engine only checks that a `found_nothing` search of the
right shape is on record — the relevance call is your recorded judgment.

### Record the decision through the verbs

The search output is the TYPED record, not a prose summary:
- `sci-adk prior-work` — records the search and the prior art found (or none).
- `sci-adk novelty --kind {result|method}` — records the per-kind decision
  (`found_nothing` or prior-art). The `--kind` flag is REQUIRED; there is no
  kind-agnostic novelty decision.
- `sci-adk contested` — records a contested-literature finding when sources conflict.

Record the search date with the decision. When a search surfaces URLs, return a
`Sources:` list so the orchestrator can cite them — but the canonical record is the verb
output, not the prose. Never record `found_nothing` for a search you did not actually run.

### Acquisition halt (a searched DOI had no OA PDF)

`prior-work --searched` and `novelty --searched` acquire the given DOIs. When a DOI
has no downloadable Open-Access PDF, the acquirer HALTS: the verb prints
`halt (human input needed):` + the missed DOI(s) to STDERR. The halt is SOFT — the
exit code is still `0` and the decision is already recorded — so watch STDERR, not the
exit code. Do NOT proceed silently: the orchestrator surfaces the missed-paper list to
the user via `AskUserQuestion`, offering (a) provide the PDF now → `sci-adk
add-literature <run_dir> --pdf <path> --doi <missed DOI>` (the manual-ingest verb;
`--doi` saves the PDF under the key that DOI already has in `references.bib`; the
workspace CLAUDE.md "User-provided literature" rule owns the bibkey), or (b) skip this paper → record the
miss as a null and continue. A missed acquisition is a recorded null, never a
skipped-over gap.

### When an index does not answer

An index that refuses (HTTP 429), times out or errors was NOT searched. Do not count it
toward a `found_nothing`. Retry it once later in the session; if it still fails, carry on
with the others. An unavailable index weakens coverage; it never excuses skipping the
search or recording a hollow `found_nothing`.

Record how the search was done. Write a search log to
`drafts/<spec-id>/search-notes/<hypothesis>-<kind>.json` at the plan stage (the run
directory does not exist before the freeze), or `runs/<id>/literature/search-notes/`
after it, with a `-<n>` suffix when several searchers cover one unit, and pass it to
the recording
verb with `--search-log <file>` (accepted by `prior-work`, `novelty`, `contested` and
`inquiry`, searched path only). The file is one JSON object:

- `hypothesis_id`, `kind` (`result` | `method`) — must match `--hypothesis` / `--kind`
  when given; leave them out for a prior-work search.
- `searched_at` — ISO-8601 UTC, e.g. `2026-10-08T05:12:44Z`.
- `queries` — every query sent, failed ones included:
  `{"index": "openalex", "query": "<exact string>", "status": "ok" | "failed",
  "n_results": 12, "detail": "HTTP 429"}` (`n_results`, `detail` optional).
- `candidates` — `{"doi", "title", "relevance": "same" | "related" | "unrelated",
  "basis": "<what matches or differs>"}`; may be empty.
- `proposed_outcome` — optional, `found-nothing` | `found-prior-art`.

The verb refuses a malformed log and records nothing. `sci-adk verify` FAILS a novelty
`found_nothing` whose log shows fewer than two distinct indexes that answered
(`status: ok`); with one index answering, query another or do not record a null. Still list
the indexes and queries in the `Sources:` list you return.

### Re-search only on amendment

At `/sci plan` you search against the DRAFT Spec so the literature can inform the freeze.
After the Spec is frozen, the recorded search results are immutable. Re-search ONLY when
`manager-prereg` amends the Spec (the amendment carries a new `[FROZEN SPEC REFERENCE]`);
otherwise the recorded decisions stand.

## Advanced (10+ minutes)

A novelty decision is a revisable LITERATURE-referent Claim: "no prior published work
establishes a specified aspect of this hypothesis, as of <date>". Like any Claim it can be
demoted later if new prior art surfaces — recording the search date is what makes that
revision honest rather than retroactive. The `found_nothing` Evidence stays out of the
DecisionEngine (it is a record ABOUT novelty, not about the hypothesis's truth), exactly as
a `negative_control` does — see `science-foundation-rigor` for the kind taxonomy.

## Works Well With

- `science-foundation-rigor` — the record/belief discipline and Evidence-kind taxonomy.
- `science-workflow-prereg` — the two-pass freeze that consumes this search to set the
  novelty flags.
- `expert-literature` — the worker that runs the search and records the decision via the verbs.
