---
name: science-tool-academic-search
description: >
  sci-adk academic-search tool knowledge: how to conduct a prior-art / novelty search per
  (hypothesis × kind) against the exact draft-Spec hypothesis text — arXiv, Semantic
  Scholar, and web sources, with a recorded search date ("as of <date>"), a graceful
  WebFetch fallback when the academic MCP is unavailable, and found_nothing recorded as a
  result. The conduct behind the novelty decision; the record is written by the prereg
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
  tags: "sci-adk, academic-search, prior-art, novelty, arxiv, semantic-scholar, literature, search-date, found-nothing, mcp-fallback, result-kind, method-kind"

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
text for the kind in hand:

- **arXiv** — preprints; closest to the frontier for math / CS / physics claims.
- **Semantic Scholar** — cross-publisher index with citation graph; good for "has this
  result/method appeared anywhere" coverage.
- **WebSearch / WebFetch** — official venues, journal pages, and grey literature the
  academic indexes miss; verify each candidate against its primary source.

Use the academic-search MCP (arXiv / Semantic Scholar) when available. Search the precise
hypothesis statement, not a paraphrase — a vague query manufactures a false `found_nothing`.

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
add-literature` (the manual-ingest verb; the workspace CLAUDE.md
"User-provided literature" rule owns the bibkey), or (b) skip this paper → record the
miss as a null and continue. A missed acquisition is a recorded null, never a
skipped-over gap.

### MCP fallback (do not let a missing MCP block the search)

If the academic-search MCP is unavailable, detect it immediately and fall back to
WebFetch against official sources (arxiv.org, semanticscholar.org, journal/venue pages),
and SAY in the recorded basis that you used the fallback. A missing MCP weakens coverage;
it never excuses skipping the search or recording a hollow `found_nothing`.

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
