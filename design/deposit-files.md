# Deposit files: shipping the protocol history and declared data with the paper

> Status: **v0.5 (2026-10-11) — approved for implementation 2026-10-11.** Phase 1 built
> 2026-10-11: 1a (the per-run protocol bundle) and 1b (`record.tex`, `run_index.csv` and the
> package). Phase 2 (declared data) built 2026-10-11. Phase 3 (instructions and Evidence
> times) built 2026-10-11. The core, render and verify paths and the package hardened
> 2026-10-11. See the change log.
> Revised after a review of v0.1 and a second review of v0.2 (the points of both and where
> each is resolved are listed at the end); v0.4 records the two decisions taken on 2026-10-11
> (§7 Resolved, change log); v0.5 records the third (§7 Q9) and the hardening. Where code
> forces a deviation, the implementer makes the smallest one and records it in the change log.
> Found on the second trial workspace (run SPEC-BCFKOW-001, `~/research/lit-search-trial-2`).
> Builds on `design/si-belief-record-split.md` (the record is the deposit),
> `design/paper-publishing-requirements.md` §3 (the code bundle), `design/near-submission-package.md`
> (package layout) and `design/declared-numbers.md` (an author declaration checked against the
> record).

"Deposit files" here means files shipped with the paper so that a reader holding only the
paper bundle can check what the paper says about its protocol and its data. They are copies;
the record they are checked against stays where it is (`runs/<id>/`, read by `sci-adk verify`).
In a per-run bundle they all sit under one folder, `paper/deposit/` (D13).

All measurements below were taken on 2026-10-10 on the working tree (including its uncommitted
changes) and on a copy of the trial workspace. Code is cited by module and symbol, not by line;
the trial's documents are cited by line as measured.

## 1. Problem

The trial paper states that "both questions, their acceptance criteria and the analysis steps
were written down and time-stamped before any record was selected" (`paper/draft.tex:31`), and
its authored SI is entirely about that claim: it summarises protocol version 1, the amendment
and version 2, each with a creation time and the SHA-256 of its file (`paper/si.tex:18-33`).
The reader cannot open any of those files.

| What | Where it lives | Shipped? |
|---|---|---|
| protocol v1 | `runs/<id>/spec_history/spec.v1.json` (`loop/amend_spec.py`: `HISTORY_DIR`, `history_path`) | no |
| amendment receipt | `runs/<id>/checkpoints/amendment-v2.json`; its `prior_spec_sha256` is the SHA-256 of v1's bytes (`AmendmentReceipt`, written by `amend_spec`) | no |
| protocol v2 | `runs/<id>/spec.json` | no |
| the analysed table (404 chemicals) | `analysis/<id>/out/s3_chemicals_final.csv`, 51,239 bytes; its SHA-256 `5e6f3568…` occurs in 5 Evidence items | no |
| third-party input (journal SI workbook, as received) | `data/raw/…/a06-005.xls`, 4,777,472 bytes, encrypted with Excel's default key; its SHA-256 `d5f642bd…` occurs in 6 Evidence items and in the amendment rationale, which is stored twice (the receipt's `rationale` and `spec.json`'s `amendment_rationale`) | no (and not by default, D7) |
| the decrypted copy of that workbook, which every analysis step read | `data/raw/…/a06-005.decrypted.xls`, 4,777,472 bytes; its SHA-256 `1081e637…` occurs in 25 Evidence items, not in the rationale | no (and not by default, D7) |

What does ship:

- per run, `paper/` (`ResearchCompiler.stage_render` in `loop/compiler.py`): `draft.tex`,
  `si.tex`, `references.bib`, `references_SI.bib`, `figures/`, and, when an Evidence
  `code_ref` resolves, `code/` + `reproduce.py`, which lists the shipped scripts, checks every
  shipped file's SHA-256 and runs nothing. A `--record-only` render (`stage_render_record`)
  writes nothing under `paper/`.
- package (`render/package.py`, layout in its module docstring): `01_manuscript/`;
  `02_data/claims_all.csv` only; `03_figures/<id>/`; `04_scripts/`; `05_inputs/README.md`, a
  fixed sentence (`_write_inputs_readme`); `06_provenance/` with `run_index.csv`, verify logs
  and `record.tex`.

Neither path has a slot for the protocol history or for a data table.

Because the files could not be shipped, the SI could not name them either, and identifies
each one by its checksum ("its file has SHA-256 …"). The vocabulary check bans `spec.json`,
`spec.v<N>.json` and `spec_history` in the paper, in any letter case (`_PAPER_ARTIFACT_RES` in
`render/paper.py`). It does not flag `checkpoints/amendment-v2.json`, the other checkpoint
files or `deposit.json` (D6), so an author can still name internal paths a reader cannot open.

The paper also reports results over that table (404 chemicals passed the filters; 341 of them
had log Kow between 1 and 6). The record binds the table by checksum; nothing gives it to the
reader.

Last, the SI's account rests on less than it reads: the earlier protocol versions and the
receipts are outside the record digest (D11), and every time in them comes from a local
clock (D12).

## 2. Scope

In: the frozen protocol history of a run, and the run-level switch that withholds it; data
files the author declares, and which of them ship; the manifests; the `verify` checks on them;
a protocol digest; a times advisory; the vocabulary check; the terms each shipped file is
distributed under; the SI and availability wording that follow.
Domain-neutral throughout: nothing below knows what the files contain.

Out: what `verify` computes on the record; `record_digest`, which stays as it is (D11); the
Spec model, which gets no new field (its `model_dump` feeds both digests); the code bundle
(`code/`, `reproduce.py`), which keeps its own gate; `numbers.json`; an external time anchor
(§7 Q1).

## 3. Decisions

### D1 — The protocol history ships by default, as exact bytes, under reader-facing names

| Record file | In the per-run bundle | In the package |
|---|---|---|
| `spec_history/spec.v<N>.json`, each N < V | `paper/deposit/protocol/protocol-v<N>.json` | `06_provenance/protocol/<id>/protocol-v<N>.json` |
| `spec.json` (version V, current) | `paper/deposit/protocol/protocol-v<V>.json` | `06_provenance/protocol/<id>/protocol-v<V>.json` |
| `checkpoints/amendment-v<N>.json` | `paper/deposit/protocol/amendment-v<N>.json` | `06_provenance/protocol/<id>/amendment-v<N>.json` |

- **By default.** Written on every full render with no declaration needed: every run has a
  frozen protocol, and every paper's methods rest on it. An unamended run ships
  `protocol-v1.json` alone. The package builds these copies from `runs/<id>/` directly (D8),
  so a run rendered before this feature is still covered. The one exception is a run whose
  persisted declaration withholds its protocol (below).
- **Byte copy, never re-serialized.** `prior_spec_sha256` is the SHA-256 of the exact bytes of
  the replaced version (`amend_spec` hashes the bytes it writes to `spec_history/`).
  Pretty-printing or canonicalizing the copy would break the one check a reader can do by hand.
- **Raw JSON keeps the record's field names.** The vocabulary check reads `paper/draft.tex` and
  `paper/si.tex` by name only (`_PAPER_DOCS`, read by `_check_paper_tool_vocab` in
  `loop/verify.py`), so nothing under `paper/deposit/` is scanned; D4 says why this keeps the
  record/belief boundary. The SI remains the readable account of the protocol.
- Other files under `checkpoints/` (`prior_work.json`, `science.json`) are working markers,
  not the protocol, and do not ship.
- A receipt written before history was kept (`prior_spec_sha256` null, no history file) ships;
  the missing version appears in the manifest with no file (D4).
- Every version carries the raw proposal (`raw_proposal`) verbatim, and it ships with it. A
  partial copy is not offered: a redacted file would no longer match its checksum, and the
  receipt and the chain check rely on that checksum. The only opt-out is withholding the whole
  history (§7 Resolved, Q6).

**Withholding.** A run withholds its protocol history with two top-level keys in its persisted
declaration (D2, D3): `"protocol": "withheld"` and `"protocol_reason"`, one line saying why.
The switch needs no declared data. With it:

- render writes nothing under `paper/deposit/protocol/` and removes the protocol files an
  earlier render wrote there, under the D13 rules; the package leaves
  `06_provenance/protocol/<id>/` absent (D8);
- the manifest keeps one row for every version and every amendment, each with an empty
  `file`, the SHA-256 and size of the record's file, and the reason (D4);
- `record.tex` keeps its Protocol history section (times, checksums, protocol digest, D11), the
  protocol digest is still printed, and `verify` still compares the record's own history
  files, receipts and `spec.json` with one another (D5); a copy released later can be checked
  against the manifest checksums and the digest;
- `verify` reports an advisory, not a failure: readers cannot check the protocol or what the
  paper says about it (D5);
- a sentence in the paper or SI that names a protocol file fails the names check (D5, D9).

Withholding covers every version and every amendment of the run, never a subset. It stops the
files only: `record.tex` still prints each claim with its hypothesis's decision rule and never
the raw proposal (`render_si_latex` in `render/si.py`), and the paper still describes the
method.

### D2 — Declared data: a render flag, kept in the run directory

The author declares data files in a JSON file passed at render time with `--deposit <json>`,
by convention `drafts/<id>/paper/deposit.json` beside `prose.json` and `figures.json`. Reasons
against a `deposit` list in `pubreqs.json`:

1. **Timing.** `pubreqs.json` is frozen when `/sci publish` starts, before the paper is written
   (trial: frozen 2026-10-09T04:58Z; prose and SI revised through 2026-10-10). Which tables a
   paper points to is decided while writing it.
2. **Kind.** `pubreqs.json` holds venue requirements, and its digest changes when a requirement
   changes; `pubreqs_digest` excludes `frozen_at` for exactly that reason. Adding a table is not
   a requirement change, yet it would force a re-freeze and a new digest.
3. **Reach.** The package has no `pubreqs.json`; a list there would need a twin in
   `pkgreqs.json`.

**Persisted in the run directory, not in `paper/`.** A render given `--deposit` validates the
file (D3) and copies its bytes to `runs/<id>/deposit.json`, beside `numbers.json`,
`declarations.json` and `novelty_sentences.json`, which live there so that a render never
clobbers them (module docstring of `core/numbers.py`; `ResearchCompiler._write_novelty_sentences`).
A declaration that fails validation changes nothing: the previous one stays and the render
stops. Editing `runs/<id>/deposit.json` directly is equivalent to passing it with the flag; a
bare render validates it the same way.

**How it reaches each render path.**

| Path | Code | Declaration used |
|---|---|---|
| `sci-adk render` | `_cmd_render` → `stage_render` | `--deposit` if given, else `runs/<id>/deposit.json` |
| `sci-adk run` | `_cmd_run` → `ResearchCompiler.compile` → `stage_render` | `--deposit` if given (threaded through `compile()` as `figures` is), else the persisted one |
| `sci-adk resolve` | `_cmd_resolve` → `run_checkpoint_loop` → `compile()` | the persisted one (the verb passes no prose or figures either) |
| `sci-adk render --record-only` | `_cmd_render` → `stage_render_record` | none; writes nothing under `paper/`; `--deposit` together with `--record-only` is rejected |

A bare re-render therefore ships the same data as the last render that was given a
declaration. To stop shipping data, pass a declaration whose `files` is empty or absent.
Render prints which declaration it used, how many files it shipped, each declared entry it did
not ship and why (D7), and whether the protocol shipped or was withheld. `verify` and
`package` read the persisted declaration (D4, D8).

**The protocol switch lives in the same file.** `protocol` and `protocol_reason` (D1, D3) are
top-level keys of the declaration, so they reach every render path, `verify` and `package` the
way the data entries do, and a declaration may carry the switch with no data:

```json
{"spec_id": "SPEC-BCFKOW-001", "protocol": "withheld",
 "protocol_reason": "The proposal includes a collaborator's unpublished results."}
```

A bare re-render keeps the protocol withheld while the persisted declaration says so; a
declaration without the two keys ships it again. The switch is not part of the Spec,
`runs/<id>/deposit.json` is outside `record_digest`, and the protocol digest is computed from
the protocol files alone (D11), so setting or clearing the switch changes neither digest.

### D3 — The declaration schema

```json
{
  "spec_id": "SPEC-BCFKOW-001",
  "license": "CC-BY-4.0",
  "files": [
    {"source": "analysis/SPEC-BCFKOW-001/out/s3_chemicals_final.csv",
     "name": "chemicals.csv", "origin": "recorded",
     "evidence": "evi-obs-20261008-h2-sample",
     "cite": ["Arnot2006"],
     "description": "The 404 chemicals that passed the filters: CAS RN, structure, measured log Kow, mean log BCF."},
    {"source": "data/raw/arnot-gobas-2006/a06-005.xls",
     "origin": "external",
     "evidence": "evi-obs-20261008-datasource-arnotgobas2006",
     "cite": ["Arnot2006"],
     "description": "BCF database, supplementary file of the cited article, as received (encrypted with Excel's default key)."},
    {"source": "data/raw/arnot-gobas-2006/a06-005.decrypted.xls",
     "origin": "external",
     "evidence": "evi-obs-20261008-datasource-arnotgobas2006",
     "cite": ["Arnot2006"],
     "description": "The same file decrypted with msoffcrypto-tool 6.0.0; every analysis step read this copy."}
  ]
}
```

As declared, no data file here ships. The chemical table holds values from the cited workbook
and states neither `license` nor `redistribution`, so it is cited, not shipped (D7); with
`"license": "CC-BY-4.0", "redistribution": "author-asserted"` added it ships as
`deposit/data/chemicals.csv`. The two workbook entries are external, state neither, and are
not copied; each would ship to `deposit/inputs/` only with both fields, as the table does. The
protocol ships (D1).

Top-level keys are exactly `spec_id`, `license`, `protocol`, `protocol_reason`, `files`; entry
keys exactly `source`, `name`, `origin`, `evidence`, `cite`, `license`, `redistribution`,
`description`. Anything else is rejected, and a load error names the entry index (as
`core/numbers.py` does). `spec_id` is required and must equal the run's Spec id; the other
top-level keys are optional, and an absent `files` is read as `[]`, so a declaration that only
withholds the protocol (D2) loads.

**Entry keys.**

- `source`: a relative path, looked up in the run dir first, then the workspace (as `code_ref`
  lookup). No absolute path, no `..`, and the path with every symlink resolved must lie inside
  the workspace. This is stricter than `code_ref`, which takes an absolute path as given
  (`_existing_file` in `loop/code_ref.py`), because these bytes are copied into a bundle meant
  for distribution. Missing at render → render fails. A protocol file (D1 ships it) and
  anything under `runs/<id>/paper/` (the bundle itself) are rejected as sources.
- `name`: a plain file name (`[A-Za-z0-9._-]+`, no leading dot), required for every entry
  that ships (which entries ship: below), optional for the others, and unique within its
  folder **compared case-insensitively**: two names that differ only in case are one file on
  the file systems most readers unpack to. Rejected: a name the
  vocabulary check flags (`spec.json`, `deposit.json`, `evi-…`), so the exemption in D4 cannot
  carry an internal name; and, compared case-insensitively, the names the package generates or
  may generate in a per-run data folder (`README.md`, `claims.csv`, `claims_all.csv`,
  `deposit.csv`, `manifest.csv`). The reserved names are rejected in every mode, so a
  declaration valid for the per-run render is valid for the package (D8). D8 gives the naming
  guidance that keeps a name out of the number checks.
- `origin`:
  - `recorded` — the study produced the file and the record holds its checksum. The binding
    `verify` checks.
  - `derived` — the study produced the file, but no Evidence item holds its checksum (for
    example a table exported while writing). **A derived file carries no integrity claim:**
    nothing in the record fixes its bytes, `verify` lists it as unchecked, and its manifest
    row names no other file that states its checksum. It may name, in `evidence`, the Evidence
    item that describes the step that produced it; `verify` checks only that the item exists.
  - `external` — third-party data, and any byte-level copy the study made in order to read it
    (decrypted, decompressed, converted): its values are the source's, so its terms are too.
    Each copy is its own entry with its own checksum, and the step that made it is stated in
    `description` and in the methods. The trial declares the workbook and its decrypted copy
    as two entries (above); no field links them (§7 Q8). Not copied unless it states both
    `license` and `redistribution` (D7, §7 Q9).
- `evidence`: the Evidence id that holds the checksum; required for `recorded` and `external`,
  optional for `derived`.
- `cite`: bib keys of the sources the file's values come from. Required and non-empty for
  `external`; for `recorded` and `derived`, non-empty whenever the file holds values taken from
  a third-party source.
- `license`: the terms under which **the deposited file itself** is distributed (for example
  `CC-BY-4.0`), not the terms of the study's code or of the file's sources.
- `redistribution`: the single value `"author-asserted"`, the authors' statement that
  redistribution is permitted; any other value is rejected. `license` gives the reader terms;
  `redistribution` states that the authors may grant them.
- **Which entries ship.**
  - `recorded` or `derived` with an empty `cite`: ships. Without its own `license` it takes the
    top-level `license`.
  - `recorded` or `derived` with a non-empty `cite`: **cited, not shipped, by default.** It
    ships only when it states both `license` and `redistribution`. With neither, or with one,
    the declaration still loads; the manifest lists the file with its checksum and citation
    (D4), render prints that it was not shipped and which field it lacks, and `verify` lists it
    in an advisory (D5).
  - `external`: the same rule (§7 Q9, decided 2026-10-11): ships only when it states both
    `license` and `redistribution`. With neither, or with one, the manifest lists the file
    with its checksum and citation and render prints that it was not shipped and which field
    it lacks; `verify` adds an advisory only when it states exactly one (D5), since one
    stating neither is the default for third-party data.

  Shipping is decided by these fields alone; no flag overrides them.
- `description`: one line. Rejected when the vocabulary check flags it, so the manifest built
  from it passes the same check (D4).

**Top-level keys** besides `spec_id` and `files`.

- `license`: the terms for the files this study produced — the protocol files and every entry
  with an empty `cite` — unless an entry states its own. Optional; when it is absent, `verify`
  says so once (D5).
- `protocol`: absent, and the protocol ships (D1), or exactly `"withheld"`. Any other value is
  rejected.
- `protocol_reason`: one line (no line break, not empty once stripped), printed in the
  manifest's protocol rows (D4). Required when `protocol` is `"withheld"`, rejected otherwise,
  and rejected when the vocabulary check flags it, as `description` is.

### D4 — Two manifests: Evidence ids only beside the record that resolves them

Per run, render writes `paper/deposit/manifest.csv`, which carries **no record identifiers**.
The package writes `06_provenance/deposit.csv`, the same columns plus `run` and `evidence`. One
row per file, sorted by path in byte order, a withheld or not-kept protocol row keyed by the
path its file would have (D1); the data files that are not shipped come last, study data
before third-party data, each group sorted by `sha256`, then `description`. Re-rendering the
same record and declaration writes the same bytes. The per-run manifest's first line is a
fixed marker (D13); the package's `deposit.csv` has none, because the package rebuilds its
folders whole (D8).

The column values are written for a reader of the bundle, not in the declaration's terms:

| Column | Content |
|---|---|
| `file` | per run, the path relative to `paper/deposit/` (`protocol/protocol-v1.json`, `data/chemicals.csv`); in the package, relative to the package root; empty for a data file that is cited, not shipped (D7: third-party data, and study data with a non-empty `cite`, that lacks `license`, `redistribution` or both), for a protocol file that is withheld (D1), and for a protocol version whose file was not kept |
| `sha256`, `bytes` | of the file's bytes — for a file not shipped or withheld, of the source or record file; empty for a version not kept |
| `kind` | `protocol` (a protocol version), `amendment`, `study data` (declared `recorded` or `derived`), `third-party data` (declared `external`) |
| `sha256_also_in` | the other files that state this SHA-256, separated by `;`: for a replaced protocol version, its amendment file (`protocol/amendment-v<N+1>.json`) when that file ships; and `record.tex`, the deposited record, wherever it prints the value — every protocol and amendment file, withheld or not (its Protocol history section, D11), and every `recorded` or `external` file whose Evidence item it prints. Empty when no other file states it: a `derived` file, a version not kept |
| `cite` | bib keys, resolved in the shipped `references.bib` |
| `license` | the file's terms: its own `license`; "redistribution asserted by the authors"; both, joined by `; `; the top-level `license` it takes; "not redistributed" for a data file that is cited, not shipped; or empty (a withheld or not-kept protocol row, or no terms stated) |
| `description` | one line, from the declaration; for protocol rows fixed text: "protocol, version N (current)", "protocol, version N, replaced by version N+1", "amendment that produced version N", "protocol, version N; file not kept"; on a withheld row the fixed text is followed by `; withheld: ` and the declaration's `protocol_reason` |
| `run`, `evidence` | package only: the run id, and the Evidence id that holds the checksum |

`sha256_also_in` replaces v0.2's `record` column, whose values ("checksum held by the record",
"not in the record") pointed at something the per-run bundle does not hold and used the
record/belief vocabulary of this design. The new column names files a reader can open and
search, and it carries the same distinction: a `recorded` table shows `record.tex`, a `derived`
one shows nothing. Render computes it by searching the protocol files and the `record.tex` it
writes for the 64-hex token; `verify` recomputes it (D5, plan). The per-run manifest passes
`check_paper_tool_vocabulary` whole, marker line included (the author's `description` and
`protocol_reason` are checked at load, D3), and a test locks that (§6.11); so does the package
`deposit.csv` without its `run` and `evidence` columns.

Why the split. `record.tex`, the document that resolves Evidence ids, sits outside `paper/`
per run (`deposit_record_path` in `loop/compiler.py`) and inside `06_provenance/` in the
package. An Evidence id in the per-run bundle would point at nothing that bundle holds, and
would put record identifiers in the folder the author uploads as the submission. The id-bearing
per-run information is the declaration itself, `runs/<id>/deposit.json` (D2), which `verify`
reads. A reader of the per-run bundle keys a row to the record by its checksum, which
`record.tex` prints wherever the record holds it (the trial's `record.tex` carries the full
`5e6f3568…` six times, `1081e637…` 26 times, `d5f642bd…` six times). In the package the ids sit
beside `06_provenance/record.tex`, which carries them already.

The protocol copies under `paper/deposit/protocol/` do carry record field names and the Spec
id. They are copies checked against the record and never read as the record: `verify` reads
`runs/<id>/`. The exemption of record-side text from the vocabulary check holds by
construction because the check reads two fixed names at the top of `paper/` (`_PAPER_DOCS`);
a file under `paper/deposit/` cannot become one of them. The scripts under `paper/code/` have
the same standing today.

### D5 — `verify` checks

One pure checker, used by render (problems printed as warnings, like `code_ref_warnings`) and
by `verify` (per run whenever `paper/draft.tex` exists; in the package gate for the package
paths of D8). `verify` recomputes every hash from bytes, never trusts a manifest's `sha256`
column, and rebuilds the expected rows from `runs/<id>/` and `runs/<id>/deposit.json`; for a
declared file that is not shipped it hashes the `source`, for a withheld protocol file the
record's file.

**Render reads the Evidence it is given.** Render runs the checker inside `stage_render`,
which `compile()` also calls (the `run` and `resolve` paths). The checks that read Evidence
(recorded, derived, external) take the Evidence list `stage_render` receives — the list the
paper and `record.tex` are rendered from — and never read `runs/<id>/evidence/` themselves.
The times advisory needs the whole log and runs in `verify` only. `verify` reads everything
from disk. Measured on the current tree: inside `compile()`, `stage_execute` writes the
Evidence before it returns, so the two lists agree there; `_write_record`'s docstring still
says the loop persists after compile. The rule above holds under either order.

| Check | Rule | Severity | What a pass shows |
|---|---|---|---|
| inventory | the manifest's first line is the marker (D13); every manifest file exists under `paper/deposit/` with that hash and size; every file under `paper/deposit/` is in the manifest (an unlisted file is named: render did not write it) | fail | the bundle holds exactly the listed bytes |
| plan | the manifest rows are the rows `runs/<id>/`, the persisted declaration (its data entries and its protocol switch) and `runs/<id>/record.tex` call for (`sha256_also_in` recomputed from the protocol files and `record.tex`) | fail | the render is not stale: no amendment and no new declaration since |
| current protocol | `protocol-v<V>.json` bytes equal `runs/<id>/spec.json`; V equals the Spec's version. With the protocol withheld (D1) there is no copy; the row's `sha256` is checked by `plan` | fail | the protocol shipped is the one the results were judged against; its content is covered by the record digest |
| earlier protocols | the SHA-256 of `protocol-v<N>.json` equals `prior_spec_sha256` in `amendment-v<N+1>.json` and the SHA-256 of `spec_history/spec.v<N>.json`; version N's `created_at`, as `str(created_at.timestamp())`, equals version N+1's `prior_version_id`; versions 1…V present. With the protocol withheld, the comparisons among the record's own files (history file, receipt, `created_at` link) still run and those against copies are skipped | fail; a version not kept (D1) is advisory | the history files, the receipts and the copies agree with one another — nothing more. They are outside the record digest (D11): a rewrite of an earlier version that keeps its `created_at`, made together with its receipt's `prior_spec_sha256`, passes. The one link inside the digest is the current `spec.json`'s `prior_version_id` (set by `Spec.amend`), and it fixes a time, not content |
| amendments | `amendment-v<N>.json` bytes equal the checkpoint file; its `rationale` equals version N's `amendment_rationale`. With the protocol withheld, only the `rationale` comparison runs | fail | copy fidelity; for the latest amendment, its rationale matches the digest-covered `spec.json` |
| withheld | the persisted declaration withholds the protocol (D1); prints `protocol withheld (<reason>): readers cannot check the protocol or what the paper says about it, such as when it was written; the manifest lists the SHA-256 of each withheld file` | advisory, never a failure | — |
| protocol digest | computed and printed for every run (D11), withheld or not | printed | — |
| recorded | the file's SHA-256 occurs as a 64-hex token in the named Evidence item (its serialized JSON, any case); shipped or not | fail; the message names any other items that hold it | the record, which the record digest covers, names these exact bytes |
| derived | listed as unchecked; a named `evidence` item exists; if the file's hash does occur in the record, advise declaring it `recorded` | listing advisory; fail only for a missing item | nothing about the bytes |
| external | the SHA-256 occurs in the named item; every `cite` key resolves in `references.bib`; the file is copied only with both `license` and `redistribution` | fail | the record names these bytes and the paper cites their source |
| cited, not shipped | every `recorded` or `derived` entry with a non-empty `cite` that lacks `license`, `redistribution` or both, and every `external` entry that states exactly one of the two (one stating neither is the default and is not listed): listed as cited, not shipped, with its checksum and citation, naming the field(s) it lacks | advisory | the bundle leaves the file out on purpose; the manifest names its bytes and its source |
| citations | every `cite` key of a `recorded` or `derived` entry resolves in `references.bib`, as for `external`, shipped or not | fail | the manifest's `cite` column (D4) points at entries the bundle holds |
| terms | every shipped file with a non-empty `cite`, listed with its terms (each states both `license` and `redistribution`, D3); with no top-level `license`, one line saying the bundle's own files state no terms | advisory | every redistribution is a visible declaration, and no third-party file or table of third-party values ships without both statements |
| names | every path in `draft.tex` / `si.tex` outside `\url` and `\href` (bare, in `\texttt` or in `\path`) that, after normalisation, starts with `deposit/` (not preceded by a word character, `/` or `.`) and ends in a file name with an extension is `deposit/` + a manifest `file`; and every bare protocol file name (below) is the name of a file under `paper/deposit/protocol/`. When the name is a withheld protocol file, or the declared `name` of an entry that is not shipped, the message says so | fail | the paper points only at files the bundle holds |
| pointed to | the paper and SI name none of the deposited paths | advisory | — |
| times | D12 | advisory | — |
| no deposit | `paper/draft.tex` exists, `paper/deposit/` does not (a paper rendered before this feature) | advisory, recommending a re-render; no verdict changes | — |

The pass line of `earlier protocols` reads "consistent", not "verified", and says that the
history is outside the record digest.

**Names: normalisation.** LaTeX source spells an underscore `\_` outside `\path`, and a path at
the end of a clause carries the clause's punctuation. Before matching, the checker reads `\_`
as `_`, takes the path as the longest run of `[A-Za-z0-9._/-]` from `deposit/`, and drops
trailing `.`, `,`, `;`, `:` and `)` from it. So `deposit/data/my\_table.csv` in prose or in
`\texttt`, `\path{deposit/data/my_table.csv}`, and "… in `deposit/data/my_table.csv`." all
name the row `data/my_table.csv`. Matching against the manifest is exact: on a case-sensitive
file system `Chemicals.csv` is not `chemicals.csv`.

Keying the names check on the `deposit/` root keeps it off ordinary prose: "the script reads
data/raw/x.xls" and "zenodo.org/deposit/1.json" match nothing. A sentence that names some
other `deposit/…` path with an extension fails, and is fixed with `\url` or by rewording.

**Names: bare protocol file names.** The protocol files have names render generates (D1), so
the check also reads them without the `deposit/` root: a token `protocol-v<N>.json` or
`amendment-v<N>.json`, found in any letter case, with no word character, `/`, `.` or `-`
immediately before it and no word character immediately after, must equal exactly the name
of a file under `paper/deposit/protocol/`. With the protocol withheld no such file exists, so
every sentence that names one fails, whether it writes "`deposit/protocol/protocol-v1.json`"
or "protocol-v1.json"; with the protocol shipped, a version that does not exist
(`protocol-v3.json` on a two-version run) fails. `checkpoints/amendment-v2.json` is preceded
by `/` and stays with the vocabulary check (D6).

Token matching, not a parser, for data: the trial's `data_ref` texts spell checksums at least
three ways (`… .csv sha256 <hex>`, `… sha256=<hex>`, `(original sha256 <hex>)`). The code
bundle's rule — path token, then `sha256=<hex>` (module docstring of `loop/code_ref.py`,
`parse_code_ref`) — exists to find *which* file to ship from a `code_ref`; here the file is
already declared and the only question is whether the record names its content, which an
exact 64-hex token answers.

### D6 — Vocabulary check: reader-facing deposit names pass, internal names fail

The check leaves deposited names alone on purpose (the comment above `_PAPER_ARTIFACT_RES`:
deposited artifacts are deliberately absent). Every row below was measured by running
`check_paper_tool_vocabulary` on the current tree; the "Proposed" column ran the same texts with
the two patterns below added. The current filename patterns match in any letter case
(`re.IGNORECASE`) and already include `\bspec\.v\d+\.json\b` and `\bspec(?:\\_|_)history\b`.

| Text | Flagged now | Proposed |
|---|---|---|
| `deposit/protocol/protocol-v1.json`, `deposit/protocol/amendment-v2.json`, `deposit/data/chemicals.csv`, `deposit/manifest.csv`; package `06\_provenance/protocol/SPEC-BCFKOW-001/protocol-v1.json`, `02\_data/SPEC-BCFKOW-001/chemicals.csv`, `06\_provenance/deposit.csv` | no | no (locked by a test) |
| `spec.json`, `SPEC.JSON`, `numbers.json`, `declarations.json`, `evi-…` ids | yes | yes |
| `spec.v1.json`, `SPEC.V1.JSON`, `spec_history/spec.v1.json`, `spec\_history/spec.v1.json` | yes | yes |
| `spec_history/`, "the spec\_history folder", `Spec_History/` | yes | yes |
| `checkpoints/amendment-v2.json`, `checkpoints/prior_work.json`, `checkpoints/prior\_work.json`, `checkpoints/science.json`, `Checkpoints/Science.json` | no | yes |
| `checkpoints/config.json`, `checkpoints/` | no | no |
| `deposit.json`, `Deposit.json` (the declaration) | no | yes |
| `zenodo.org/deposit/1.json` | no | no |

Two patterns are missing, both added to `_PAPER_ARTIFACT_RES` with `re.IGNORECASE` like their
neighbours:

- `\bcheckpoints/(?:amendment-v\d+|prior(?:\\_|_)work|science)\.json\b`;
- `deposit` in the internal JSON-name alternation:
  `\b(?:spec|pubreqs|pkgreqs|declarations|review|deposit|numbers(?:\.draft)?)\.json\b`.

`checkpoints/` alone is not banned: a machine-learning paper may deposit its own
`checkpoints/` folder. The same name (`amendment-v2.json`) is internal under `checkpoints/` and
reader-facing under `deposit/protocol/`; the folder decides, and no exemption code is needed.

### D7 — Third-party values are cited with their checksum, not redistributed by default; every shipped file states its terms

- **External data.** An `external` entry is copied only when it states both `license` and
  `redistribution: "author-asserted"`, the rule for a table built from third-party values
  below (§7 Q9, decided 2026-10-11). With neither, or with one, its manifest row has an empty
  `file`, the checksum, the citation and "not redistributed" (and, in the package, the
  Evidence id); `verify` advises on an entry that states exactly one. With both, the file is
  copied to `paper/deposit/inputs/` (package: `05_inputs/<id>/`) and `verify` lists it with
  its terms. sci-adk does not judge licenses; it makes each redistribution a visible
  declaration. The literature PDFs a run acquired are external by this rule and never ship by
  default; neither does a copy the study made of a third-party file (D3: the trial's
  decrypted workbook).
- **Tables built from third-party values are cited, not shipped, by default.** A `recorded` or
  `derived` table can hold values taken from a cited source; the trial table holds BCF values
  from the cited workbook. Any `recorded` or `derived` entry with a non-empty `cite` is, by
  default, handled as an external entry that states neither field: not copied, its manifest
  row with an empty `file`, its checksum, its citation and "not redistributed" (in the
  package, also the Evidence id); render prints
  that it was not shipped, and `verify` lists it with the field(s) it lacks (D5). It ships, to
  `paper/deposit/data/` (package: `02_data/<id>/`), only when the entry states both `license`
  and `redistribution: "author-asserted"` (D3); `verify` then lists it with both. Both are the
  authors' statements; sci-adk records them and checks neither. An empty `cite` is the
  authors' statement that the file holds no third-party values; nothing checks that either.
- **The bundle's own files.** The top-level `license` gives the terms for the protocol files
  and for every entry with an empty `cite`. The availability statement names it (D9).
- **The one way around these terms: `runs/<id>/artifacts/` in the package.** The package
  copies that folder whole to `04_scripts/runs/<id>/` (D8) whatever the declaration says, so a
  file there ships even when its entry is cited, not shipped, and a third-party file there
  ships with no entry at all (acquired literature PDFs in the older `artifacts/literature/`
  layout among them, despite the first bullet). This is reported as an advisory, never a failure, and only for
  a declared file whose bytes the package finds there (D8). Keeping third-party files out of
  `artifacts/` is the author's job; nothing checks it.
- **The package README.** `05_inputs/README.md` is generated from the rows: each third-party
  file with its citation, its checksum and "not redistributed" or its terms; then each study
  file with a non-empty `cite`, with its citation, its checksum and "not redistributed" or its
  terms. The sentence "Nothing copyrighted is redistributed here" (`_write_inputs_readme`) is
  written only when no shipped file has a non-empty `cite`. With no deposit rows the README
  keeps today's text.

### D8 — Package placement

Per-run folders follow the package's existing convention (`03_figures/<id>/`,
`04_scripts/runs/<id>/`, `_colocate_run_artifacts` in `render/package.py`).

| Content | Package path | Built from |
|---|---|---|
| protocol | `06_provenance/protocol/<id>/protocol-v<N>.json`, `…/amendment-v<N>.json`; nothing for a run whose persisted declaration withholds it (D1), whose rows `deposit.csv` still lists | `runs/<id>/` directly, never the per-run copies |
| `recorded`, `derived` that ship (D3, D7) | `02_data/<id>/<name>` | `runs/<id>/paper/deposit/data/<name>`, the copy the per-run `verify` checked |
| redistributed `external` | `05_inputs/<id>/<name>` | `runs/<id>/paper/deposit/inputs/<name>` |
| manifest | `06_provenance/deposit.csv` (with `run`, `evidence`), listed in `MANIFEST.md` | the rows above and `runs/<id>/deposit.json` |

- **The package owns three per-run namespaces**: `02_data/<id>/`, `05_inputs/<id>/` and
  `06_provenance/protocol/<id>/`, for every `<id>` that has `runs/<id>/spec.json`. Each
  assembly clears every one of them and copies in what that run ships now, as
  `_copytree_idempotent` does for `03_figures/<id>/`, and also when the run ships nothing
  there, in which case the namespace stays absent. (`_copytree_idempotent` clears only when a
  source exists, so a run that stops having figures keeps a stale `03_figures/<id>/` today;
  that gap is outside this design.) A workspace run that is not packaged has its namespaces
  cleared. A run whose declaration shrank, or that left the package, therefore leaves no stale
  file behind. A file an author puts in an owned namespace is removed by the next assembly; the
  `MANIFEST.md` row for `02_data/` says the `<id>/` folders are rebuilt on every assembly.
- **The package inventory** is the files under the owned namespaces of the packaged runs plus
  `06_provenance/deposit.csv`: every file there is a `deposit.csv` row with that hash and size,
  and every row's file exists (fail otherwise). A subfolder of `06_provenance/protocol/` that is
  not a packaged run fails, since that folder is the package's whole; a subfolder of `02_data/`
  or `05_inputs/` named after no workspace run is not the package's, is left alone, and gets an
  advisory that it ships unchecked.
- **Protocol rows are current at package time by construction.** The package reads
  `runs/<id>/`, not the per-run bundle, so a stale per-run copy cannot reach it; the package
  gate re-runs the D5 protocol checks against `runs/<id>/`, so an amendment after packaging
  fails the gate. It reads the protocol switch from `runs/<id>/deposit.json`, so a run
  withheld after its last per-run render is still withheld in the package; the gate reports
  the withheld advisory (D5) per run.
- **Declared files** follow each run's persisted declaration; a declared file that ships and is
  missing from that run's `paper/deposit/` stops assembly with "re-render run <id>". The
  package processes no second declaration. Two runs may declare the same `name`; the per-run
  folders keep them apart.
- **Never at the top of `02_data/`.** The package number audit takes every numeric cell of
  `02_data/*.csv`, non-recursively, as a recorded value (`RecordedValuePool.from_data_csvs`,
  used by `from_package` in `render/number_audit.py`). A deposited table is recorded by its
  checksum, not cell by cell; at the top level, the cells of the 404-row table would let almost
  any number in the manuscript pass the exact-only audit. The per-run subfolder keeps them out,
  and a test locks it.
- **Reserved names** (D3) keep declared files from colliding with generated per-run files in
  `02_data/<id>/`: the package already promises per-run claim CSVs in `02_data/` without fixing
  their names (layout in the module docstring of `render/package.py`).
- **`runs/<id>/artifacts/`** is copied whole to `04_scripts/runs/<id>/`
  (`_colocate_run_artifacts`) and is not changed by this design. A declared file whose bytes
  also appear there ships twice; `verify` advises, naming both paths and saying that the
  `02_data` copy is the checked one. For a declared entry that is cited, not shipped (D7), the
  same advisory says instead that the copy under `04_scripts/runs/<id>/` ships the file
  although the declaration does not. (The trial run has no `artifacts/`.) Both are advisories,
  never failures: the wholesale copy bypasses the D7 terms, and the package states it instead
  of refusing it. A file under `artifacts/` that no entry declares ships with no row and no
  advisory; that includes acquired literature PDFs in the older `artifacts/literature/`
  layout, which `ResearchCompiler._LITERATURE_DIRS` still reads.
- **The package names check.** `01_manuscript/main.tex` and `si.tex` are written for the
  package and name package paths (`02_data/<id>/chemicals.csv`,
  `06_provenance/protocol/<id>/protocol-v1.json`, `06_provenance/deposit.csv`). With the D5
  normalisation (every package path contains `_`, so LaTeX spells it `02\_data` outside
  `\path`), every path in them that starts with `02_data/`, `05_inputs/` or `06_provenance/`
  must exist in the package; a per-run `deposit/…` path fails, and the message gives the
  package path its manifest row maps to. A path into `06_provenance/protocol/<id>/` of a run
  that withholds its protocol fails with a message saying so, and a bare protocol file name
  (D5) must be the name of a file under some `06_provenance/protocol/<id>/`.

**How paths, checksums and times meet the number checks.** Two tokenizers read a manuscript,
and which one applies depends on the mode:

| Mode | Tokenizer | `\texttt` | Outside verbatim spans |
|---|---|---|---|
| per run, `runs/<id>/numbers.json` present | `find_literals` (`render/number_literals.py`), the declared-number checks | prose: numbers inside it are literals; `\path`, `\url`, `\verb`, `\nolinkurl` are masked | a run of 7 or more hex characters in one letter case, holding a digit and a letter, and not digits-e-digits, is a word, not a number |
| per run, no `numbers.json` | `tokenize_quantitative` (`render/number_audit.py`), the pattern audit | stripped whole, as are `\path`, `\url`, `\verb`, `\href`, `\nolinkurl` (`_STRIP_PATTERNS`) | a digit group after a non-word character is a number |
| package (always) | `tokenize_quantitative`, exact-only (`number_audit_problems(…, allow_derived=False)`) | as the line above | as the line above |

Measured on the current tree:

| Text | `find_literals` | pattern audit |
|---|---|---|
| `deposit/protocol/protocol-v1.json`, `deposit/data/chemicals.csv`, bare or in `\texttt` | none | none |
| `02\_data/SPEC-BCFKOW-001/chemicals.csv` bare / in `\texttt` / in `\path` | `02`, `001` / `02`, `001` / none | 2, 1 / none / none |
| `deposit/data/table-2.csv`, `bcf-2006.csv`, `2023\_bcf.csv` (bare) | `2`, `2006`, `2023` | 2, 2006, none (a bare year is stripped) |
| `table\_2.csv`, `table2.csv`, `my\_table.csv` | none | none |
| a full SHA-256 split into 16-character `\texttt` pieces joined by `\allowbreak` (the trial SI's form) | none | none |
| elided `4fa76e47…a767fa66`: bare / in `\texttt` | none / none | 4 / none |
| elided prefixes `9dc5d638…`, `45e12abc…` (bare) | none | 9, 4.5e13 |
| `\texttt{1081e637}\ldots` (a prefix that reads as digits-e-digits) | the literal `1081e637` (no value) | none |
| `2026-10-08T10:03:39Z` bare / in `\texttt` | one date-time literal / the same | −10, 8, 3, 39 / none |

Guidance that follows, for both modes (Phase 3 puts it in the publish and package skills):

- In the package manuscript, every path, checksum and date-time goes inside `\texttt` or
  `\path`: bare, they read as the numbers above and fail the exact-only audit.
- A declared name has no digit group after a hyphen or at its start (`table_2.csv`, not
  `table-2.csv` or `2023_bcf.csv`); otherwise the per-run declared-number checks read a literal
  in every sentence that names it, to be declared as an identifier in `numbers.json`.
- A checksum is written in full — 64 hex digits, split into `\texttt` pieces of at least four
  characters joined by `\allowbreak`, as the trial SI does — not elided: an elided prefix such
  as `1081e637` reads as a number in the declared-number checks, and a reader cannot check an
  elided value anyway.
- `\path{…}` keeps a path out of both tokenizers and needs no `\_`.

### D9 — What the SI and the availability statement say

The SI names the files instead of describing them. From the trial SI (`si.tex:21,24,33`),
rewritten (the checksum is elided here; the paper writes it in full, D8):

> Version 1 of the protocol (`deposit/protocol/protocol-v1.json`) was created at
> 2026-10-08T10:03:39Z. The amendment (`deposit/protocol/amendment-v2.json`, recorded at
> 2026-10-08T14:05:17Z) stores the SHA-256 of the version it replaced, `4fa76e47…a767fa66`,
> which is the checksum of `deposit/protocol/protocol-v1.json`. Version 2
> (`deposit/protocol/protocol-v2.json`) is the protocol the results were judged against.

What stands behind each clause:

- the two times are copied from the files; no check covers the clock (D12);
- "stores the SHA-256 … which is the checksum of `protocol-v1.json`" is the D5
  earlier-protocols check, which shows that the deposited files agree with one another, not
  that version 1 was never rewritten together with its receipt (D10, D11);
- "the protocol the results were judged against" is the D5 current-protocol check.

No check covers "the analysis was done after version 2 was written". The trial's sentence
"written down and time-stamped before any record was selected" (`draft.tex:31`) rests, with
the deposit, on times recorded by local clocks; the times advisory (D12) prints them beside
the paper.

The availability statement (authored, in the paper) names the bundle's folders, the manifest
and the terms, and cites with its checksum every data file the bundle does not ship. Example
for the declaration in D3, with an illustrative license (checksums elided here, written in
full in the paper):

> The protocol in both versions and its amendment (`deposit/protocol/`) and the analysis
> scripts (`code/`; `reproduce.py` lists them and checks each against its SHA-256) are
> distributed with this paper; `deposit/manifest.csv` lists every file with its SHA-256 and the
> terms it is distributed under, and gives the SHA-256 of each data file that is not
> distributed. Files produced in this study are distributed under CC BY 4.0. The table of the
> 404 chemicals that passed the filters contains BCF values from Arnot and Gobas (2006) and is
> not distributed; its SHA-256 is `5e6f3568fd1c7f1b…c888b871`. The BCF database is not
> redistributed either: it is the supplementary file of Arnot and Gobas (2006), SHA-256
> `d5f642bdaf3c69fa…7dc7f8f0`, encrypted with Excel's default key, and every analysis step read
> a decrypted copy, SHA-256 `1081e637f6bd39f9…fd95c461`, which is not redistributed.

**A table of third-party values that ships.** When the table's entry states both `license`
and `redistribution` (D3, D7), the statement names the file and both statements instead:

> The table of the 404 chemicals that passed the filters (`deposit/data/chemicals.csv`) is
> distributed under CC BY 4.0; it contains BCF values from Arnot and Gobas (2006), and the
> authors state that its redistribution is permitted.

A table that is cited, not shipped, is never named by its bundle path: the names check fails
`deposit/data/chemicals.csv` when the manifest row has an empty `file` (D5).

**A withheld protocol.** With the protocol withheld (D1), the SI and the availability
statement cannot name a protocol file: the names check fails every sentence that does,
bundle path or bare name (D5). They say that the protocol is withheld, give the reason and
point to the checksums:

> The protocol (versions 1 and 2) and its amendment are not distributed with this paper: the
> proposal includes a collaborator's unpublished results. `deposit/manifest.csv` lists the
> SHA-256 of each of the three files, so a copy released later can be checked against them.

The SI may still describe the protocol in prose, but nothing in the bundle stands behind that
description or behind a statement of when the protocol was written; `verify` says so in its
withheld advisory (D5). Statements like the clauses above — which checksum the amendment
stores, which version the results were judged against — then rest on checks only the authors
can run (D5 earlier protocols and current protocol, on `runs/<id>/`).

v0.2's example said the analysis read the copy with SHA-256 `d5f642bd…`; the trial's draft says
the decrypted copy (`1081e637…`) is the one every step read, and 25 Evidence items hold that
checksum against 6 for the original. Both appear in the manifest as third-party rows with an
empty `file`, each checked against the record (D5 external). That the second is the first
decrypted with a named tool is the authors' statement, in the methods and the row's
description; no check covers it (D3, §7 Q8).

The package's generated "Data & code availability" section in `record.tex` (the section the
deposit-completeness check looks for, `_DATA_AVAILABILITY_RE` and
`deposit_completeness_problems` in `render/pkgreqs_checks.py`) lists the `deposit.csv` rows
with their terms.

### D10 — What the protocol files establish

- **Content.** A reader can read every version and recompute each checksum.
- **Unamended run.** The single file equals `spec.json`, whose content the record digest
  covers (`record_digest` in `provenance/__init__.py`). Against a copy of the record digest
  published earlier, a later change to the protocol shows.
- **Amended run.** The earlier versions and the receipts are outside the record digest. The
  chain version 1 → amendment → version 2 shows that three files the authors hold agree; a
  consistent rewrite of an earlier version and its receipt passes every D5 check. The current
  `spec.json` fixes only the replaced version's creation time (`prior_version_id`), not its
  content. The protocol digest (D11) makes the history tamper-evident from the moment someone
  other than the authors holds a copy of it (or of a record digest computed after an Evidence
  item recorded it, D11 option D); before that, nothing in the bundle tells the original
  history from a consistent rewrite.
- **Withheld protocol** (D1). The bundle holds no protocol file, so it establishes none of the
  above for a reader; the manifest's checksums and the protocol digest fix which bytes a later
  release must match.
- **Times.** Written by local clocks, or carried by the Evidence JSON (D12); no file can show
  that the clock was right. The SI's comparison also needs the time of the first record
  selection, which only an Evidence item's `created_at` holds, and `record.tex` prints no
  Evidence time today (measured on the trial's `record.tex`); Phase 3 adds it. An external
  anchor is §7 Q1.

### D11 — The record digest stays as it is; a protocol digest covers the history

(Was v0.1 §7 Q1.) `record_digest` covers `spec.json`, `evidence/*.json` and `verdicts/*.json`,
canonicalized through their models. It does not cover `spec_history/` or
`checkpoints/amendment-v<N>.json`. `Spec.prior_version_id` is the replaced version's
`created_at` as a timestamp string (set by `Spec.amend`; trial: `1791453819.934251`, which is
2026-10-08T10:03:39.934251Z), not a hash. So for an amended run the D5 chain check compares
files the authors can edit.

| Option | What it does | Cost |
|---|---|---|
| A. Fold the history and the receipts into `record_digest` | the record digest covers the chain | the digest of every amended run changes, including the 12-hex prefixes already printed in built packages' `run_index.csv`; re-verifying such a package shows a mismatch that reads as tampering. The record digest also moves with every Evidence append, so a value deposited at amendment time cannot be compared with it later |
| B. Leave `record_digest`; add a protocol digest over the history | a second, separate value | one more value to print and explain; like any digest, it shows nothing until someone other than the authors holds a copy |
| C. For new amendments, store the replaced version's SHA-256 in `prior_version_id` | the current `spec.json` binds the chain, so the record digest covers it without a code change or a new field | one field holds two formats (a timestamp on every run amended so far, a hash afterwards); `Spec.amend` sets the field itself and never sees file bytes, so `amend_spec` would overwrite what the model wrote; runs amended before are unchanged |
| D. Record B's value in an Evidence item: an observation, appended at freeze and at each amendment, whose result states the protocol digest (and, once deposited, an archive identifier, §7 Q1) | the observation sits in `evidence/`, inside the record digest, with no change to any model or to `record_digest`; `verify` recomputes the protocol digest of versions 1…N and amendments 2…N and compares it with the recorded value, so a later rewrite of the history no longer matches a digest-covered value | the item bears on no hypothesis and adds one item per amendment; its `created_at` is again a local clock (D12); who appends it — the amend verb or the agent — is open (§7 Q1); like B, it shows nothing until someone else holds a record digest computed after it |
| A new field on `Spec` | — | rejected: `Spec.model_dump` feeds `record_digest` and `spec_digest`, so a new field, even one defaulting to null, changes the digest of every existing run |

**Decision: B**, with D as the way to carry B's value, and an anchor identifier, inside the
record when §7 Q1 is settled. The protocol digest is the SHA-256 of the text `sha256sum`
prints for the protocol files under their bundle names (lines `<64 lowercase hex><two
spaces><name>`), names in byte order. It includes the current version, so at freeze time it
covers version 1:

```
cd deposit/protocol && LC_ALL=C sha256sum $(LC_ALL=C ls) | sha256sum
```

- It is computed from exact bytes, so a reader recomputes it with standard tools from the
  bundle, and `verify` computes the same value from `runs/<id>/` by mapping record names to
  bundle names (D1). Unlike the record digest, a whitespace-only edit changes it.
- It changes at an amendment and not when Evidence is appended, so it is the value to deposit
  with a third party at freeze and at each amendment (§7 Q1). The value after amendment N is
  recomputable later from the files of versions 1…N and amendments 2…N, so every earlier
  deposited value stays checkable.
- It is printed in the `verify` output (`protocol digest (sha256): …`), in a full-width
  `protocol_digest_sha256` column of `06_provenance/run_index.csv` (a 12-hex prefix, like the
  record-digest column's, is too short to deposit), and in a "Protocol history" section of
  `record.tex` (per run and package) that lists each version and each amendment file, its time,
  the SHA-256 of its file, and the protocol digest. The history is on disk before any render,
  so `record.tex` can carry the value; the record digest is left out of `record.tex` because
  `ResearchCompiler._write_record` passes `digest=None`, its docstring saying that the Evidence
  may not yet be persisted at compile time. All three places carry it for a run that withholds
  its protocol too (D1).
- For runs amended before this feature, it covers the history from the moment its value is
  first published, and says nothing about the time before.
- It does not show that the history was not rewritten before anyone else held the value. Under
  B the D5 chain check stays a consistency check, labelled as one.

C stays possible later, alongside B.

### D12 — Times: an advisory line, not a check of the clock

Where the times come from:

- the Spec's `created_at`: set by the freeze or amend verb from the local clock; a value in the
  input JSON is ignored (`_load_spec_json` in `cli.py`; `Spec.amend`);
- the receipt's `recorded_at`: the amend verb's clock (`amend_spec`);
- an Evidence item's `created_at`: whatever the Evidence JSON carries, and the verb's clock
  only when it carries none (`_cmd_append_evidence` validates the file as given with
  `EvidenceItem.model_validate`; `stage_append_evidence` persists it). In the trial, 6 items
  share `2026-10-09T18:14:57.126969Z` and 4 share `2026-10-10T02:01:26.744069Z`: the program
  that wrote the JSON chose those times.

No clock is witnessed. `verify` adds to `paper_advisory`, for every run with a paper:

```
times (local clocks, not witnessed): protocol v1 2026-10-08T10:03:39Z; amendment v2 2026-10-08T14:05:17Z
  earliest Evidence 2026-10-08T10:04:41Z (literature); earliest bearing on a hypothesis 2026-10-08T16:53:36Z
  7 item(s) recorded between v1 and v2 bear on no hypothesis (literature 3, novelty_decision 2, prior_work_decision 1, contested_record 1)
```

and one flag line per Evidence item that bears on a hypothesis h and was created before the
version h depends on. That version is the earliest k such that `hypotheses[h]` and `method` are
unchanged from version k through the current one (`content_changes` in `loop/amend_spec.py`).
An item created before version 1 is flagged whatever it bears on. When a version was not kept,
its content is unknown, every hypothesis counts as changed at the next version, and the line
says so.

On the trial, version 2 changed only `method.approaches[1]`, so H1 and H2 depend on version 2;
the two items bearing on them (16:53:36Z, 16:54:04Z) postdate it (14:05:17Z), and nothing is
flagged. The line compares recorded times only. The amendment rationale names the workbook by
its checksum, and the authored SI says the workbook's layout and record counts had been
inspected before the amendment, yet the Evidence item that records the workbook is
timestamped 14:48:59Z, 43 minutes after version 2. An event recorded later than it happened
does not show in this line.

### D13 — One root, and render touches only the files it wrote

- **One root.** Per run, everything this design writes in the bundle is under
  `paper/deposit/`: `protocol/` (unless withheld, D1), `data/` (`recorded`, `derived` that
  ship, D7), `inputs/` (redistributed `external`) and `manifest.csv`. No generic folder
  (`paper/data/`, `paper/inputs/`) is created: authors keep pgfplots tables or Overleaf data
  there, which a render-owned folder would overwrite and an inventory rule would fail.
- **Marker.** The first line of `paper/deposit/manifest.csv` is the fixed line
  `# Written with this paper; do not edit. Paths are relative to this folder.`, which render
  compares byte for byte. It names no tool, so the manifest passes the vocabulary check whole
  (D4); `reproduce.py`'s marker (`MACHINE_SECTION_MARKER`) names the tool, the manifest's need
  not. CSV readers skip it as a comment (`comment="#"` in pandas, `skip = 1` in R).
- **Writing.** Render writes a file under `paper/deposit/` only where (a) nothing exists, (b) a
  trusted previous manifest lists the path, or (c) the existing file already holds exactly the
  bytes render would write; in case (c) the file counts as written and nothing changes. Any
  other existing file stops the render, naming it; render never overwrites it. Render also
  stops when `paper/deposit/`, one of its three folders or a target path is a symlink: it never
  writes through a link. The manifest itself is replaced only when the existing one carries the
  marker or none exists; a `manifest.csv` without the marker stops the render.
- **Which previous manifest is trusted.** One whose first line is the marker and whose every
  non-empty `file` cell is `protocol/<name>`, `data/<name>` or `inputs/<name>`, with `<name>` a
  plain file name (D3's pattern): relative, no `..`, no leading `/`, no backslash, and resolving
  inside `paper/deposit/` with no symlink on the way. One cell that fails and the whole
  manifest is untrusted: nothing is removed, and render prints the cell. This is the rule the
  code bundle already follows for `paper/code/`: `ResearchCompiler._emit_reproduction_bundle`
  trusts a previous `reproduce.py` only when it carries its marker (`written_by_sci_adk`) and
  only for plain file names inside `paper/code/`.
- **Removing.** From a trusted manifest, render removes the listed files this render does not
  write, and of those only the ones whose bytes still have the listed SHA-256. A listed file
  whose bytes changed is left in place and named; the inventory check then fails on it.
  Withholding the protocol, or an entry that stops shipping (D7), is such a shrink: the
  protocol or data files an earlier render wrote are removed by this rule.
- **Lost manifest.** With no manifest, an unreadable one or an untrusted one, render removes
  nothing and still renders: files whose bytes equal what it writes count as written (c), so a
  lost manifest does not block the next render. Files an earlier render wrote and this one does
  not are left; the inventory check fails on each, naming it, for the author to delete.
- A file someone else puts under `paper/deposit/` is never touched by render; the inventory
  check fails on it, naming it.
- `--record-only` writes nothing under `paper/` and leaves `runs/<id>/deposit.json` alone; the
  `record.tex` it writes carries the Protocol history section (D11), withheld or not.

The package needs none of this: it owns its namespaces whole and rebuilds them (D8).

## 4. Alternatives rejected

- **Relax the vocabulary check so the SI may name `spec.json` and `spec_history/…`.** The names
  mean nothing to a reader of the bundle, and the files still would not ship.
- **Ship a rendered (LaTeX/PDF) protocol instead of the JSON.** A rendering cannot be checked
  against `prior_spec_sha256`; the SI already is the readable account.
- **`deposit` list in `pubreqs.json`.** D2.
- **Generic folders `paper/data/` and `paper/inputs/` owned by render** (v0.1). D13.
- **A render without `--deposit` drops the declared data** (v0.1). D2.
- **An id-bearing manifest in `paper/`** (v0.1). D4.
- **Manifest values in the design's own terms** ("checksum held by the record", `recorded`,
  `derived`; v0.2). D4.
- **Remove whatever the previous manifest lists** (v0.2). A hand-edited or foreign manifest
  could then make render delete `paper/draft.tex`. D13.
- **Fold the history into `record_digest`; a new Spec field; reuse `prior_version_id`.** D11.
- **Require a derived file's inputs and producing script.** Even with both bound, `verify`
  runs no code (`reproduce.py` runs nothing), so the derived bytes would stay unchecked: more
  declaration, no checked property. D3 says plainly that derived files carry no integrity
  claim. The same reason keeps a structured transformation field off external entries for now
  (§7 Q8).
- **Copy every file under the analysis output folder.** Ships working files and third-party
  values unchecked; the author must decide what the paper offers.
- **A structured checksum field on `Provenance`.** A schema change to a record type, and
  existing records (the trial's included) would still carry checksums only in free text. Token
  matching works on them now.
- **Reuse the `code_ref` parser for data.** D5: it reads one spelling at one position.
- **Redistribute external data by default, with a citation.** Licensing.
- **Ship a table of third-party values on `license` or `redistribution` alone, and fail the
  declaration when it states neither** (v0.3). Decided 2026-10-11: such a table is cited, not
  shipped, by default, and ships only with both (D3, D7).
- **Ship a third-party file on `license` or `redistribution` alone** (v0.3, kept in v0.4).
  Decided 2026-10-11 (§7 Q9): the two-field rule of the decision above applies to third-party
  data too, so a third-party file needs the same two statements as a table built from it
  (D3, D7).
- **Withhold the raw proposal alone, or ship a redacted protocol.** A changed file no longer
  matches the checksums the receipt and the chain check rely on (D1). Withholding is per run
  and whole.
- **Fail `verify` when the protocol is withheld.** Decided 2026-10-11: withholding is the
  authors' choice; `verify` reports what it costs the reader as an advisory (D5).

## 5. Phases

**Phase 1 — protocol history, protocol digest, times.** New pure module `render/deposit.py`
(protocol plan, manifest text with its marker and `sha256_also_in`, protocol digest, checks,
times advisory); `loop/compiler.py` `stage_render` writes `paper/deposit/protocol/` and
`paper/deposit/manifest.csv` under the D13 rules (marker, trust, removal by hash, symlinks);
`record.tex` gains the Protocol history section (this changes `record.tex` bytes for every run,
and the tests that lock them are updated); `run_index.csv` gains `protocol_digest_sha256` (the
shipped `build_record_index.py` and its in-process copy in `package.py`); `render/package.py`
clears and rebuilds `06_provenance/protocol/<id>/` (D8) and writes `06_provenance/deposit.csv`;
`loop/verify.py` gains `deposit_file_problems` (fail) and adds the advisories to
`paper_advisory`; `render/pkgreqs_checks.py` runs the same checks and the package inventory in
the package gate; `render/paper.py` gets the two D6 patterns; `cli.py` prints the protocol
digest. This alone lets the trial SI name its files.

**Phase 2 — declared data.** `core/deposit.py` (schema, loader, the D3 rules on sources,
symlinks, names — case-insensitive uniqueness and reserved names — descriptions and terms);
`--deposit` on `render` and `run`, threaded through `compile()`; the persisted
`runs/<id>/deposit.json`, which `resolve` also uses; copies to `paper/deposit/data/` and
`paper/deposit/inputs/`; the cited-not-shipped default for `recorded` and `derived` entries
with a non-empty `cite` (D3, D7); the recorded, derived, external, cited-not-shipped,
citations, terms and names checks (with the bare protocol-name rule), the render side reading
the Evidence `stage_render` receives; package `02_data/<id>/`, `05_inputs/<id>/` rebuilt as
owned namespaces, the generated `05_inputs/README.md` and the package names check. The loader
also reads the protocol switch (`protocol`, `protocol_reason`), and Phase 2 adds its branch to
the Phase 1 protocol plan, manifest rows, protocol checks and package assembly, plus the
withheld advisory.

**Phase 3 — instructions and Evidence times.** Workspace skills: the experiment stage records
`<path> sha256=<hex>` in `data_ref` for every output table a paper may ship (as
`declared-numbers.md` §4.4 does for counts); the publish stage writes `deposit.json` with its
terms, declares a copy made of a third-party file as its own external entry, names deposited
files in the SI and availability statement by their bundle paths, writes the D9 wording for a
table that is cited, not shipped, and for a withheld protocol, follows the D8 guidance on
names, checksums and times, and states times as recorded times; the package skill follows the
same guidance for package paths. `record.tex` prints each Evidence item's `created_at`.

## 6. Test plan

Unit tests build runs through `init-spec` and `amend-spec`, so the history and the receipt are
written by the real verbs. Entries named below come from the trial run; end-to-end checks
render, package and verify a copy of the trial workspace in a temporary directory, never the
workspace itself.

1. **Protocol render.** Ships `protocol-v1.json`, `protocol-v2.json` and `amendment-v2.json`
   under `paper/deposit/protocol/`, byte-identical to their sources; the SHA-256 of
   `protocol-v1.json` is `4fa76e47…`, equal to the receipt's `prior_spec_sha256`. An unamended
   run ships `protocol-v1.json` only. The manifest's first line is the marker. Re-render is
   byte-identical.
2. **Protocol checks.** `verify` passes on that render; fails after one byte of
   `protocol-v1.json` changes; fails after an amendment made post-render (plan, current
   protocol); is advisory for a receipt with `prior_spec_sha256` null and no history file.
   Rewriting `spec_history/spec.v1.json` (same `created_at`) together with the receipt's
   `prior_spec_sha256` passes every D5 check and leaves the record digest unchanged, while the
   protocol digest changes: the test records what the chain does not show. Changing version 1's
   `created_at` fails the `prior_version_id` link; changing the receipt's `rationale` fails the
   amendments check.
3. **Protocol digest.** `verify`'s value equals the D11 `sha256sum` recipe run on the bundle and
   the value computed from `runs/<id>/`; appending Evidence leaves it unchanged; an amendment
   changes it; after a third version, the value printed after version 2 is recomputed from the
   version 1, version 2 and amendment 2 files.
4. **Times.** On the trial copy, the D12 lines print and nothing is flagged; an Evidence item
   bearing on H1 with a `created_at` before version 2 is flagged; a version not kept makes every
   hypothesis count as changed.
5. **Recorded.** The chemical table (`5e6f3568…`) declared against `evi-obs-20261008-h2-sample`
   passes both as declared in D3 (cited, not shipped: `verify` hashes the `source`) and with
   `license` and `redistribution` added (shipped: the copy is hashed too); against an item that
   does not hold the hash it fails and names the five that do; a modified copy fails. Render's
   check reads the Evidence list it is given: `stage_render` called with a list whose item
   holds the hash warns about nothing even when `evidence/` on disk lacks that item, and
   `verify`, reading the disk, fails.
6. **Derived.** Listed as unchecked; a named Evidence id that does not exist fails; a derived
   file whose hash the record holds gets the "declare it recorded" advisory.
7. **External.** The workbook (`d5f642bd…`) and its decrypted copy (`1081e637…`), declared as
   two entries against `evi-obs-20261008-datasource-arnotgobas2006`, both pass and neither is
   copied; each row has an empty `file`, its checksum and `Arnot2006`. With the decrypted copy
   declared against an item that does not hold it, the message names the 25 items that do.
   With `license` alone, or `redistribution` alone, a file is still not copied and `verify`
   advises, naming the missing field; with both it lands in `deposit/inputs/` and its terms
   are listed. A `cite` key absent from `references.bib` fails; a checksum absent from the
   record fails.
8. **Cited, not shipped, and terms.** The chemical table as declared in D3 (`recorded`,
   `cite` `Arnot2006`, neither `license` nor `redistribution`) loads and is not copied: no
   `deposit/data/` file, a manifest row with an empty `file`, `5e6f3568…`, `Arnot2006` and
   "not redistributed"; render prints that it was not shipped and lacks both fields; `verify`
   passes with an advisory naming both. With `license` alone, and with `redistribution` alone,
   the same, the advisory naming the missing one. With both it ships to
   `deposit/data/chemicals.csv`, and its row's `license` reads
   `CC-BY-4.0; redistribution asserted by the authors`. A `derived` entry with a `cite`
   behaves the same. Re-rendering after removing one of the two fields removes the copy an
   earlier render wrote (D13). A `cite` key of a `recorded` entry absent from
   `references.bib` fails, shipped or not. No top-level `license` gives one advisory; the
   top-level `license` appears in the protocol rows and the rows with an empty `cite`, never
   in a cited row.
9. **Persisted declaration.** A render with `--deposit` writes `runs/<id>/deposit.json`; a bare
   `render`, `run` and `resolve` then ship the same data; `files: []` stops shipping and removes
   the data files the previous render wrote; a declaration with `files` absent loads as `[]`;
   an invalid declaration leaves the persisted one untouched; `--record-only` with `--deposit`
   is rejected and nothing under `paper/` changes.
10. **Ownership and removal guards.** An author file at `paper/data/table.dat` is neither
    touched nor inventoried; an author file dropped into `paper/deposit/data/` fails the
    inventory and survives a re-render; a declared name that collides with an existing unlisted
    file of different bytes stops the render; removing one declared entry removes only that
    entry's file. Guards:
    - *tampered manifest*: marker kept, one row's `file` changed to `../draft.tex`, then to
      `data/../../draft.tex`, then to `/tmp/x`, then to a symlink under `deposit/data/` that
      points at `paper/draft.tex`: each time nothing is removed, `paper/draft.tex` is intact,
      and render prints the cell;
    - *manifest without the marker*: render stops, naming it, and removes nothing;
    - *listed file edited by hand*: not removed, named; the inventory fails on it;
    - *lost manifest*: delete `manifest.csv` and re-render with the same declaration: the
      render succeeds, the files whose bytes are unchanged count as written, the new manifest
      is byte-identical to the lost one; after the declaration shrinks with the manifest lost,
      the dropped file stays and the inventory fails naming it;
    - *symlinked folder*: `paper/deposit/data` a symlink → render stops without writing.
11. **Manifests.** An edited `sha256` cell fails. The per-run manifest contains no `evi-` token
    and `check_paper_tool_vocabulary` on its whole text, marker included, returns nothing; so
    does the package `deposit.csv` without its `run` and `evidence` columns. A `description`
    the vocabulary check flags fails to load. `sha256_also_in` reads
    `protocol/amendment-v2.json;record.tex` for `protocol-v1.json`, `record.tex` for
    `protocol-v2.json`, `amendment-v2.json` and the chemical table (shipped or not), and is
    empty for a derived file. The package `deposit.csv` has the `run` and `evidence` columns.
    Row order (D4): with the protocol shipped, the cited chemical table not shipped and the two
    workbook entries, the rows are the three protocol files by path, then the chemical table,
    then the two workbook rows by `sha256` (`1081e637…` before `d5f642bd…`); with the protocol
    withheld the protocol rows keep their places.
12. **Names.** An SI naming `deposit/data/missing.csv` fails; "the script reads data/raw/x.xls",
    "zenodo.org/deposit/1.json" and paths inside `\url` pass. With a row `data/my_table.csv`,
    `deposit/data/my\_table.csv` in prose and in `\texttt`, `\path{deposit/data/my_table.csv}`,
    and the path followed by `.`, `,` or `)` all pass; `deposit/data/My_table.csv` fails. With
    the chemical table cited, not shipped, `deposit/data/chemicals.csv` fails with a message
    that the entry is not shipped. Bare protocol names: on a two-version run with the protocol
    shipped, "protocol-v1.json" and `\texttt{amendment-v2.json}` pass, "protocol-v3.json" and
    "Protocol-V1.json" fail, and "my-protocol-v1.json" and `checkpoints/amendment-v2.json` are
    not read by this rule. The trial SI rewritten as in D9, and the D9 availability examples,
    pass the vocabulary and names checks. Tokenizer pins on the
    per-run declared-number checks (`find_literals`): the `deposit/` paths, bare or in
    `\texttt`, and a full split checksum yield no literal; `deposit/data/table-2.csv` yields
    `2`; `\texttt{1081e637}\ldots` yields the literal `1081e637`; the D9 sentence's literals are
    the version numbers 1 and 2, the two times and the 256 of "SHA-256", which need
    `numbers.json` entries as in the trial SI today.
13. **Vocabulary.** The D6 table row by row, including `checkpoints/config.json`,
    `checkpoints/` and `zenodo.org/deposit/1.json` not flagged and the mixed-case rows flagged.
14. **Schema.** Unknown key, duplicate name, two names differing only in case
    (`Chemicals.csv`, `chemicals.csv`), name with `/`, name `spec.json`, reserved name
    `claims.csv` and `README.MD`, absolute or `..` source, a symlink that resolves outside the
    workspace, a protocol file as source, a source under `runs/<id>/paper/`, a `spec_id` that
    differs from the run's, a flagged `description`, a `redistribution` other than
    `"author-asserted"`, an entry that ships without a `name` — each rejected with the entry
    index. A cited `recorded` entry that does not ship loads without a `name`. Protocol switch:
    `protocol` other than `"withheld"`, `"withheld"` without `protocol_reason`,
    `protocol_reason` without `protocol`, a reason with a line break, an empty or blank reason,
    and a reason the vocabulary check flags — each rejected.
15. **Package.** Files at the D8 paths; protocol rows built from `runs/<id>/` even when the
    per-run copy is stale; package `verify` fails after an amendment made post-package; the
    package number-audit pool is unchanged by `02_data/<id>/chemicals.csv` (the table declared
    with `license` and `redistribution`, so that it ships); as declared in D3 the table is a
    `deposit.csv` row with an empty `file` and nothing lands in `02_data/<id>/`; a per-run
    `deposit/…` path in `main.tex` fails with the package path in the message;
    `\texttt{02\_data/SPEC-BCFKOW-001/chemicals.csv}` resolves in the package names check;
    `05_inputs/README.md` lists the third-party and the cite-bearing study rows, each with
    "not redistributed" or its terms, and drops "Nothing copyrighted is redistributed here"
    when a shipped file has a `cite`; `MANIFEST.md` lists
    everything; rebuild is byte-identical.
    *Shrink then rebuild*: package a run declaring two data files; re-render it with one, and
    rebuild: `02_data/<id>/` holds one file, `deposit.csv` one row fewer, the inventory passes;
    re-render with `files: []` and rebuild: `02_data/<id>/` is absent; deselect the run in
    `pkgreqs.json` and rebuild: its three namespaces are absent; an author file in
    `02_data/<id>/` is gone after a rebuild; an unknown subfolder of `02_data/` gets the
    advisory, one of `06_provenance/protocol/` fails.
    *Tokenizer pins on the pattern audit*: a package path bare yields 2 (or 6) and 1, inside
    `\texttt` or `\path` nothing; a bare elided checksum `4fa76e47…` yields 4 and `9dc5d638…`
    yields 9, inside `\texttt` nothing; a bare `2026-10-08T10:03:39Z` yields −10, 8, 3, 39,
    inside `\texttt` nothing.
16. **Backward compatibility.** Existing render, package and verify tests pass, except those
    that lock `record.tex` or `run_index.csv` bytes, which are updated for the Protocol history
    section and the new column; a paper without `paper/deposit/` gets one advisory and the same
    verdicts.
17. **Withheld protocol.** On the amended trial copy, a declaration holding only `spec_id`,
    `"protocol": "withheld"` and a `protocol_reason` (no `files`) loads and is persisted.
    Render writes no `paper/deposit/protocol/`; `paper/deposit/` holds `manifest.csv` alone,
    with three rows — protocol versions 1 and 2 and amendment 2 — each with an empty `file`,
    the SHA-256 and size of the record's file (`4fa76e47…` for version 1), `record.tex` in
    `sha256_also_in`, an empty `license`, and a `description` ending in `; withheld: ` and the
    reason; the manifest passes `check_paper_tool_vocabulary` whole. An unamended run has one
    row. `record.tex`, the protocol digest and the record digest are byte-identical to the
    shipped case.
    - `verify` passes with one withheld advisory naming the reason, and no failure from
      `current protocol`, `earlier protocols` or `amendments`; the record-side comparisons
      still run: changing the receipt's `rationale`, or version 1's `created_at`, fails.
    - Shipped → withheld: with the switch written into `runs/<id>/deposit.json` by hand,
      `verify` on the old bundle fails `plan`; a bare re-render then removes the three protocol
      files the earlier render wrote (D13) and `verify` passes; a protocol file copied back by
      hand fails the inventory. Withheld → shipped (a declaration without the two keys passed
      with `--deposit`): the files return byte-identical to the first render.
    - Names: the D9 withheld example passes; a sentence naming
      `deposit/protocol/protocol-v1.json`, bare "protocol-v1.json", or
      `\texttt{amendment-v2.json}` fails, the message saying the protocol is withheld.
    - `--record-only` with the switch persisted writes the same `record.tex` as without it.
    - Package: the withheld run has no `06_provenance/protocol/<id>/`; its `deposit.csv` rows
      match the per-run rows plus `run` and `evidence`; its `run_index.csv` row carries the
      protocol digest; the package gate reports the withheld advisory and does not fail;
      `\path{06_provenance/protocol/<id>/protocol-v1.json}` in `main.tex` fails, naming the
      withheld run; a second packaged run that ships its protocol is unaffected. Withholding
      after the last per-run render and rebuilding the package leaves the run withheld in the
      package.

## 7. Open questions

1. **External time anchor** (tied to D11, D12). Whether `/sci plan` should offer, at freeze and
   at each amendment, to deposit the protocol digest with a third party (an archive record, a
   public commit, a timestamping service) and record the identifier, so the protocol side of an
   order claim has a witness. The identifier needs no model change: an Evidence observation
   recording the protocol digest and the archive identifier sits inside the record digest
   (D11 option D). Open within that: whether the amend verb appends the observation itself or
   the agent does. An anchored protocol digest shows only that the protocol existed by that
   time; witnessing "before any record was selected" also needs a witness on the Evidence
   side, for example the record digest deposited after the selection step.
2. **Run ids as folder names in the package** (`<id>` in D8): the same unsettled question as
   hypothesis ids in the package SI (the `hyp-<id>` note above `_PAPER_ARTIFACT_RES`). The
   digits of an id such as `SPEC-BCFKOW-001` also count as a number when a package path is
   written outside `\texttt` (D8).
3. **One inventory.** Whether `code/` files join the deposit manifest, each bound by the
   checksum in its `code_ref`, or stay under the code bundle's own gate; and whether the
   wholesale copy of `runs/<id>/artifacts/` (D8) should be listed there too. Listing it would
   close the way around the D7 terms that the package now only reports as an advisory (D7,
   D8).
4. **File size.** The trial table is 51,239 bytes, each workbook copy 4,777,472 bytes, and the
   run's acquired literature 29 MB. The per-run `paper/` is uploaded to Overleaf as a folder,
   and journals limit supplementary files. Whether render warns above a size, and whether large
   declared files ship only in the package.

Questions 5, 6 and 9 are resolved (§7 Resolved, below); the remaining questions keep their
numbers so that references to them stay valid.

7. **Shared data outside the workspace.** D3 requires a source to resolve inside the
   workspace, so data kept on a symlinked shared drive cannot be declared. Whether to allow a
   list of extra roots, or to require a copy inside the workspace.
8. **Transformed third-party files.** The trial's decrypted workbook is declared as a second
   external entry, and "the cited file decrypted with msoffcrypto-tool 6.0.0" lives only in its
   description and the methods (D3, D9). Whether an entry should name its source entry and the
   tool in structured fields, and the manifest show the pair as linked. `verify` could then
   check that both checksums sit in one Evidence item and that the tool is named there; it
   still could not check the transformation without running it (§4).

### Resolved

5. **Tables that hold third-party values** — decided 2026-10-11. A `recorded` or `derived`
   entry with a non-empty `cite` is cited, not shipped, by default: the manifest lists it with
   its checksum and its citation, and render and `verify` say it was not shipped. It ships only
   when the entry states both `license` (the terms the file is distributed under) and
   `redistribution: "author-asserted"`. In: D3 (Which entries ship), D4 (`file`, `license`
   columns), D5 (cited not shipped, citations, terms), D7, D8, D9, §6.5, §6.8, §6.11, §6.12,
   §6.14, §6.15.
6. **The raw proposal** — decided 2026-10-11. The protocol history ships by default; a run may
   withhold it entirely with `"protocol": "withheld"` and a one-line `protocol_reason` in its
   persisted declaration, which needs no declared data. Render then ships no protocol file; the
   manifest rows say "withheld" with the reason and keep the checksums of the record's files;
   `verify` reports an advisory, not a failure, that readers cannot check the protocol or what
   the paper says about it; and the names check fails a sentence that names a withheld
   protocol file. In: D1 (Withholding), D2, D3, D4, D5 (withheld, names, bare protocol names),
   D8, D9, D10, D11, D13, §6.9, §6.12, §6.14, §6.17.
9. **External entries and the two-field rule** (raised by the Q5 decision) — decided
   2026-10-11, by applying the Q5 decision uniformly. An `external` entry ships only when it
   states both `license` and `redistribution: "author-asserted"`, as a `recorded` or `derived`
   entry with a non-empty `cite` does; with neither or one it is cited, not shipped. Under v0.3
   and v0.4 it shipped with either, so a table built from third-party values needed more than
   the third-party file it was built from. `verify` advises on an external entry that states
   exactly one of the two, the case that shipped before; one stating neither is the default
   and gets no advisory. In: D3 (`origin`, Which entries ship), D4 (`file` column), D5
   (external, cited not shipped, terms), D7, §4, §6.7.

## Change log

- **v0.1, v0.2, v0.3** (2026-10-10). First draft and two revisions after review; the review
  points and where each is resolved are in the two tables below. v0.3 was committed with
  `3937185`.
- **v0.4** (2026-10-11). Status: approved for implementation 2026-10-11.
  - Decisions taken 2026-10-11: §7 Q5 — a `recorded` or `derived` entry with a non-empty
    `cite` is cited, not shipped, by default and ships only with both `license` and
    `redistribution: "author-asserted"` (D3, D7); §7 Q6 — the protocol history ships by
    default, and a run withholds it entirely with `"protocol": "withheld"` and
    `"protocol_reason"` in its persisted declaration (D1, D2, D3). All other decisions are
    kept.
  - Edits these decisions require: `files` is optional (absent = `[]`) so the switch works
    with no data (D3); the manifest's `license` column reads "not redistributed" for every data
    file that is cited, not shipped, and the withheld protocol rows carry the reason in
    `description` (D4); a total order for rows with an empty `file` (D4); a `cite` key of a
    `recorded` or `derived` entry must resolve in `references.bib`, as v0.3 required for
    `external` and as the D4 `cite` column already stated (D5 citations); the names check also
    reads bare `protocol-v<N>.json` and `amendment-v<N>.json`, so a sentence naming a withheld
    file fails without the `deposit/` root (D5); D8 package placement, D9 wording, D10, D11,
    D13, §4, §5 and §6 follow.
  - Raised: §7 Q9 (whether `external` entries take the same two-field rule).
  - Deviations made during implementation are recorded here.
- **Phase 1a built** (2026-10-11): the per-run protocol bundle (`render/deposit.py`;
  `stage_render` writes `paper/deposit/protocol/` and `manifest.csv` under D13; `verify`'s
  protocol checks, times and withheld advisories; the D6 patterns; the protocol digest
  printed). Deviations and settled gaps, each the smallest found:
  - *Phase placement.* The protocol switch is built now, not in Phase 2: `core/deposit.py`
    holds the top-level half of the loader (`spec_id`, `license`, `protocol`,
    `protocol_reason`; `files` must be a list of objects and is not read until Phase 2).
    There is no `--deposit` flag yet; the switch is read from `runs/<id>/deposit.json`,
    which the author edits. The top-level `license` is applied to shipped protocol rows (D7).
  - *`sha256_also_in` before Phase 1b.* It is computed by searching, as D4 says; until
    `record.tex` gains its Protocol history section (Phase 1b), the protocol rows name only
    the amendment file (`protocol/amendment-v2.json` for version 1). A Phase 1a bundle then
    fails the plan check until re-rendered.
  - *Unspecified cases, settled.* A version N > 1 with no receipt: no manifest row, advisory.
    A receipt whose `prior_spec_sha256` is null while the history file exists: advisory. A
    history file missing while its receipt records a checksum: failure. `verify` also fails
    a history file whose `version` is not its N, and a receipt whose version numbers or Spec
    id do not match its file name.
  - *A paper without `paper/deposit/`.* Only the advisory and the times advisory; neither the
    bundle checks nor the record-side comparisons run, so the verdict is unchanged (§6.16).
  - *D13 edges.* A `manifest.csv` that is itself a symbolic link stops the render, like the
    folders. "Unreadable" is read as: the marker line is readable but the rest is not; such
    a manifest is untrusted, render proceeds and replaces it. A manifest whose first line is
    not the marker stops the render. Owned folders a render empties are removed, so a
    withheld render leaves `manifest.csv` alone (§6.17). An invalid persisted declaration
    stops the render before anything under `paper/` is written and is a `verify` failure.
  - *Times advisory.* One `paper_advisory` entry whose continuation lines are indented four
    spaces (the CLI prefixes each advisory with two). The time of a version not kept comes
    from the next version's `prior_version_id`; an amendment's time is its receipt's
    `recorded_at`, else the version's `created_at`. Flag lines read `flagged: <id> (<kind>,
    bears on <h>) created <t>, before protocol v<k> (<t>), the version <h> depends on`.
  - *Where the digest is printed.* Also by `render` and `status`, on the line `verify` prints
    (`protocol digest (sha256): …`); `record.tex` and `run_index.csv` follow in Phase 1b.
  - *Names.* The verify function is `check_deposit_files`; its failures are the report field
    `deposit_file_problems`, which joins the exit gate. The shipped
    `04_scripts/check_package.py` carries the two D6 patterns (its test pins it to the gate).
- **Phase 1b built** (2026-10-11): the Protocol history section of `record.tex` (per run and
  package), `protocol_digest_sha256` in `run_index.csv`, the package's
  `06_provenance/protocol/<id>/` and `06_provenance/deposit.csv`, and the package gate's
  protocol checks and inventory. Every per-run `record.tex` changes bytes, as §5 says; so do
  the package's `record.tex` and `run_index.csv`. A per-run bundle rendered with Phase 1a
  fails the plan check until re-rendered (its manifest lacks `record.tex` in
  `sha256_also_in`). Deviations and settled gaps, each the smallest found:
  - *Section text and order.* The per-run section lists the files in the order they were
    written (version 1, amendment 2, version 2, …), not in manifest path order, under their
    bundle names, each with `created <time>` (a version) or `recorded <time>` (a receipt) and
    its SHA-256 whole on a line of its own (in `\small\texttt`, unbroken, so a reader and
    `sha256_also_in` find it by searching); a version not kept shows the time the next
    version records for it and "no SHA-256". It sits before "Record integrity". A Spec
    rendered with no `runs/<id>/spec.json` on disk gets no section. `--record-only` writes
    it without reading the declaration, so it stays byte-identical withheld or not.
  - *The package's `record.tex`.* `make_si.py` prints the same section, one block per run,
    computed with the standard library only (the script runs on a machine without sci-adk),
    as is the protocol digest in the shipped `build_record_index.py`; the in-process copy in
    `render/package.py` calls the builder's own function, and a test pins both scripts to
    `render/deposit.py` (kept, version not kept, receipt missing, unamended). A run whose
    protocol files cannot be read gets `n/a` in `run_index.csv`. The new column is the last.
  - *`sha256_also_in` in the package.* It names package paths
    (`06_provenance/protocol/<id>/amendment-v2.json`, `06_provenance/record.tex`), searched
    in the package's protocol copies and its `record.tex`, because D4 makes the package's
    `file` column relative to the package root. §6.17's "rows match the per-run rows plus
    `run` and `evidence`" therefore holds for every column except `file` and
    `sha256_also_in`, which carry the package's paths.
  - *Clearing.* The assembler removes `06_provenance/protocol/` whole before rebuilding it
    (D8: the folder is the package's whole), so a run that left the workspace also leaves no
    folder; D8 named only workspace runs. Each run's plan, with its persisted declaration, is
    read before the assembler writes anything: an invalid `deposit.json` stops `sci-adk
    package` (exit 2) with `package/` untouched, and in the gate it is a failure for that
    run. A withheld run adds a note to the assembly output.
  - *Which runs the gate checks.* The assembler's own selection (`resolve_runs` over
    `pkgreqs.json`), not `run_index.csv`, which lists every workspace run.
  - *A package assembled before this feature* (neither `deposit.csv` nor
    `06_provenance/protocol/`): one advisory, no failure, mirroring the per-run "no deposit"
    row; with either present every check runs.
  - *Not yet.* `02_data/<id>/` and `05_inputs/<id>/` as owned namespaces, the generated
    `05_inputs/README.md` and the package names check stay in Phase 2, where data first
    ships. The shipped `check_package.py` does not read `deposit.csv`.
  - *Guidance.* The D8 guidance on package paths, checksums and times (and the layout and
    gate) is in the package skill now, because Phase 1b ships the protocol paths a package
    manuscript names; the publish-skill half stays in Phase 3. The tokenizer pins of §6.12
    and §6.15 are tests; every measurement in the D8 table held.
  - *Tests updated.* `tests/test_cli_verb_decomposition.py` compared `record.tex` across two
    workspaces frozen at different clock times; the section prints the checksum of each
    frozen `spec.json`, whose bytes carry `created_at`. Its in-process byte-identity tests now
    freeze both Specs at one fixed instant (full bytes still compared); its Docker-only CLI
    test (`run --t1-demo` against the verb chain) compares `record.tex` without the Protocol
    history section, the one place two separate freezes may differ.
- **Phase 2 built** (2026-10-11): declared data. `core/deposit.py` validates the data entries
  (`DepositEntry`; `parse_deposit_declaration`, and `load_deposit_declaration` /
  `read_deposit_declaration`, which also resolve every source); `--deposit` on `render` and
  `run`, threaded through `compile()`; `render/deposit.py` gains the data plan, the data rows,
  `deposit_data_problems`, `deposit_name_problems` and `package_name_problems`; the package
  rebuilds `02_data/<id>/` and `05_inputs/<id>/`, generates `05_inputs/README.md` and its gate
  checks the data. Deviations and settled gaps, each the smallest found:
  - *Required `description`.* D3 does not say whether it is required; it is, because the row
    of a file that is not shipped gives the reader only its description, checksum and source.
  - *More text checked at load.* Besides `description` and `protocol_reason`, the vocabulary
    check also reads an entry's `name`, `license` and `cite` keys and the top-level `license`:
    each is printed in the manifest, which D4 says passes the check whole. A `cite` key is a
    string with no space, comma or semicolon (the manifest joins keys with `;`).
  - *Where sources are resolved.* `parse_deposit_declaration` reads no file;
    `load_deposit_declaration` and `read_deposit_declaration` (the `--deposit` path) look up
    every source and apply the D3 rules on it. A missing source is a load error, so render
    stops before writing (D3 "missing at render"), `verify` reports the persisted declaration
    as invalid, and `package` stops.
  - *When `--deposit` is persisted.* Its bytes are written to `runs/<id>/deposit.json` in the
    step that writes `paper/deposit/`, after the paper is rendered: a render that fails for
    any reason (validation, a D13 refusal, a renderer error) leaves the persisted declaration
    as it was. D2 required this only for a declaration that fails validation.
  - *Name uniqueness.* Compared case-insensitively within each folder (`data/`, `inputs/`)
    among every entry that states a name, shipped or not, so the names check can say which
    entry a path meant.
  - *`sha256_also_in` of a data row.* Computed as D4 says: the shipped protocol files and
    `record.tex` that hold the 64-hex token; never for a `derived` row. On the trial the
    workbook row reads `protocol/amendment-v2.json;protocol/protocol-v2.json;record.tex`,
    because the amendment rationale names its checksum. `record.tex` prints one Evidence item
    for a run of items with identical findings ("recorded 6x"), so a checksum held only by a
    collapsed item does not appear there, and the column does not name `record.tex` for it.
  - *Serialized Evidence.* The recorded and external checks search
    `EvidenceItem.model_dump_json()`, which is the same for the list render holds and the
    files `verify` reads.
  - *Advisories settled.* A third-party entry that is not shipped gets no `verify` advisory
    (D5 lists none; render prints it). The no-top-level-license advisory is given only when
    something ships that would take that license (a protocol file, or a study file with no
    cited source and no license of its own). "Pointed to" (unphased in §5) is built with the
    names check: an advisory when neither `draft.tex` nor `si.tex` names a file the bundle
    holds (`deposit/manifest.csv` counts).
  - *Names check text.* `\url{}`, `\nolinkurl{}` and the URL argument of `\href` are masked;
    the link text of `\href` is read as prose; LaTeX comments are read, as the vocabulary
    check reads them.
  - *What render prints.* Which declaration it used, how many data files it shipped and how
    many are cited only, and each file not shipped with the reason (stdout). Failures of the
    data and names checks are render warnings (stderr); the advisories are `verify`'s only.
  - *Package copies.* Before writing anything the assembler checks that every declared file a
    packaged run ships is in its `paper/deposit/` with its source's bytes; a missing or stale
    copy stops assembly with "re-render run <id>" (D8 named only a missing one).
  - *Package gate data checks.* The gate runs the D5 data checks per packaged run against the
    run's Evidence and `01_manuscript/references.bib`, the package's bibliography: a `cite`
    key missing there fails the gate, so a package with cited data needs the author's
    `package_src/references.bib` (the placeholder bib the assembler writes holds no entry).
  - *Package names check.* A `02_data/`, `05_inputs/` or `06_provenance/` path passes when it
    exists in the package as a file or a folder; a path with `..` never passes.
  - *Package namespaces.* A `02_data/` or `05_inputs/` subfolder named after a workspace run
    that is not packaged fails (the assembler clears it); files directly in those folders
    (`claims_all.csv`, `README.md`) are not namespaces. Unshipped rows of different runs that
    tie on `sha256` and `description` are ordered by run id. The `evidence` column is empty
    on a `derived` row (the design defines it as the id that holds the checksum).
  - *`MANIFEST.md`.* One line under the `02_data/` and `05_inputs/` headings, always: the
    `<id>/` folders hold each run's declared files and are rebuilt on every assembly.
  - *`05_inputs/README.md`.* With declared data: the intro (the "Nothing copyrighted" sentence
    only when no shipped file has a cited source), then "Third-party files", then "Study files
    holding values from cited sources", one line each with the package path or "not
    included", the run, the description, the citation, the SHA-256 and "not redistributed" or
    the terms. With no declared data, the fixed text of Phase 1.
  - *Tests.* The unit tests use small synthetic files and Evidence items in the trial
    fixture's workspace, in the trial's shape (a table whose checksum three items hold; a
    third-party file and its decrypted copy recorded in one item, the copy in two more). The
    trial table and workbooks are not added to the repository: they hold third-party values,
    and each workbook is 4,777,472 bytes. The counts §6.5 and §6.7 name (5 items for the
    table, 25 for the decrypted copy) were measured on a copy of the trial workspace.
  - *Not yet.* The package `record.tex` "Data & code availability" section listing the
    `deposit.csv` rows (D9, last paragraph; no phase names it). The shipped `check_package.py`
    still does not read `deposit.csv`. The publish and package skills learn the data paths in
    Phase 3.
- **Phase 3 built** (2026-10-11): the workspace instructions and the Evidence times in
  `record.tex`. Deviations and settled gaps, each the smallest found:
  - *Evidence times in `record.tex`.* Each entry of the Evidence record gets a line
    `\textit{created:} <time>` between its head and its provenance, in UTC to the second
    (`2026-10-08T16:53:36Z`, the format of the Protocol history section and the times
    advisory; a time without a zone is read as UTC; `time_label` in `render/deposit.py`). An
    entry that collapses repeated items ("recorded Nx") prints the earliest and the latest of
    its items' times (`<t1> to <t2>`), or one time when they print the same: D10 asks for
    each item's time, and printing every one would undo the collapse. One sentence before the
    list says where the times come from and that nothing witnesses them; an empty record gets
    no sentence. Only the per-run `record.tex` changes: the package's `record.tex`
    (`make_si.py`) prints no Evidence record. Every per-run `record.tex` changes bytes; no
    manifest changes (`sha256_also_in` searches 64-hex tokens), so a bundle rendered before
    this phase still passes `plan`. No locked test needed updating: the tests that compare
    `record.tex` across two renders already give their Evidence one fixed `created_at`, or
    copy the same Evidence files into both workspaces.
  - *Where the instructions live.* The experiment-stage rule (`<path> sha256=<hex>` in
    `data_ref` for every output table a paper may ship, a third-party file and each copy made
    to read it with its own checksum) is in both the experiment skill and the
    `expert-experimentalist` agent, which already carry the `code_ref` rule side by side.
    The publish skill gains a "Deposit files" section: the declaration at
    `drafts/<spec-id>/paper/deposit.json` and `--deposit`, the entry keys, the terms (D3, D7),
    the copy of a third-party file as its own `external` entry, the protocol switch, names by
    bundle path, the D9 sentences as examples, recorded times and the D8 guidance. The
    `expert-writer` agent and the hub point to that section instead of restating it.
  - *One render command.* The paper render the hub, the publish skill and the writer show is
    `sci-adk render <run> --prose prose.json [--si si.json] [--deposit deposit.json]`; a test
    pins the three to the same flags. The `/sci publish` command's description names
    `paper/deposit/` and `--deposit`.
  - *The switch explained once.* `"protocol": "withheld"`, `"protocol_reason"` and the
    consequence for readers appear only in the publish skill. The package skill's gate
    paragraph, which restated the two keys since Phase 1b, now refers to the publish skill;
    a test pins both.
  - *D8 guidance, per run.* With `numbers.json`, a date-time inside `\texttt` is one literal
    declared as an `identifier`; the publish skill says so beside the rule to put paths,
    checksums and times inside `\path` or `\texttt`. The publish skill's example sentences
    put times in `\texttt` and paths in `\path`; tests run them through the vocabulary check,
    and the protocol examples through the names check (shipped on the amended trial fixture,
    and withheld).
  - *Package skill.* Its layout shows `02_data/<id>/`, `05_inputs/<id>/` and the generated
    `05_inputs/README.md`; its gate paragraph covers the declared data and says that a
    package with cited data needs `package_src/references.bib` (the gate resolves cite keys in
    `01_manuscript/references.bib`); its naming section adds the data package paths, the rule
    that a file cited, not shipped, has no package path, and recorded times.
  - *README.* One "Deposit files" bullet in the feature list; the test counts re-measured.
- **Hardening of the core, render and verify paths** (2026-10-11), after review of the built
  phases. Deviations from the review's wording are marked.
  - *Version bound.* `plan_protocol` looped over every version `spec.json` states, so
    `"version": 10000000` hung `verify` and `status`. It now counts the versions 1..V that no
    file of the run accounts for (`spec_history/spec.v<N>.json` accounts for N,
    `checkpoints/amendment-v<N>.json` for N-1 and N, `spec.json` for V) and refuses when more
    than `VERSION_MARGIN` (10) lack one, naming `spec.json`, the count and the highest version
    the files reach. The error is `ProtocolUnreadable`, a `DepositRefused`, so render stops
    before writing and `run` prints it like a refused deposit. Deviation: the review asked
    for "the highest N on disk plus a margin"; counting the versions without a file gives the
    same bound for every run the verbs wrote and is not lifted by one stray high-numbered
    file. The margin keeps a run amended before history files and receipts existed (the real
    t1-godel run is at version 4) planning, its earlier versions "not kept".
  - *No symbolic link in the record's protocol files.* `spec.json`, each
    `spec_history/spec.v<N>.json` and each `checkpoints/amendment-v<N>.json` is read after
    `lstat`; a link, or anything but a plain file, is refused with the file named. Addition:
    so is a `spec_history/` or `checkpoints/` folder that is a link (a file under a linked
    folder is read through the link). `verify` and `status` report it; `render --record-only`
    now prints the error and exits 2 instead of raising a traceback (one `try` in `cli.py`).
  - *The history line says what it compared.* "consistent -- versions 1 to N and R amendment
    receipt(s) agree" is printed only when every step was compared in full: both versions
    kept and the receipt present with a `prior_spec_sha256`. Otherwise the line reads
    "partly compared -- of versions 1 to N, the step from version 1 to 2 agrees with its
    receipt; not compared in full: version 2 was not kept; amendment-v3.json does not exist;
    ..." (or "no step ... could be compared in full").
  - *Unreadable source.* An `OSError` while reading a declared source that exists is a
    `DepositDeclarationError` naming the entry ("'source' ... is not readable (...)"): render
    prints `error:`, `verify` lists it as a failure. Both raised a traceback before.
  - *Case-only renames.* A trusted manifest's path that differs from a target in letter case
    only and is the same file (`os.path.samefile`) is never removed, and a target that is such
    a file is written, not refused. On a case-sensitive file system the two spellings are two
    files and the old one is removed as before. Tested by simulation: a hard link stands for
    the second spelling. Not done: on a case-insensitive file system the file keeps its old
    spelling on disk, so the inventory fails it under that spelling until it is renamed by
    hand.
  - *Names.* A declared `name` that is a Windows device name (CON, PRN, AUX, NUL, COM0-9,
    LPT0-9, with or without an extension, in any letter case) or ends in `.` or a space is
    rejected. COM0 and LPT0 are added to the review's list: Windows reserves them too.
  - *Hashing.* A source that does not ship is hashed in 1 MiB chunks and never held whole;
    only a source that ships is read into memory, since render writes those bytes. `DataFile`
    carries `sha256`, `size` and `data` (`None` unless the entry ships). On the trial's three
    declared files (two workbooks of 4,777,472 bytes) render took 0.55 s.
  - *Sources inside the record.* A declared source that resolves, links followed, into
    `evidence/`, `claims/`, `verdicts/` or `checkpoints/` of a run, or to a top-level `*.json`
    of a run, is rejected: those files carry record identifiers (D4). Deviation: every run
    under `runs/`, not only the declaring run; another run's record carries identifiers just
    the same. The rule runs after the protocol-file and `paper/` rules, whose messages stay.
  - *One line.* A one-line field rejects every character `str.splitlines()` breaks at: U+2028,
    U+2029, U+0085, vertical tab, form feed and U+001C-U+001E as well as line feed and
    carriage return. Applied to every one-line field of the declaration (`description`,
    `license`, `evidence`, `source`), not only `protocol_reason`: they share one validator.
  - *Stray files.* The inventory now says "is not in the manifest (left from an earlier render,
    or added by hand)" instead of "render did not write it". Render warns once per file when a
    file under `paper/deposit/` stays that the new manifest does not list (a lost or
    untrusted manifest, a hand-added file); a listed file left in place because its bytes
    changed keeps its existing warning only. Every file under `paper/deposit/`, not only
    `protocol/` and `data/`: the inventory fails any of them.
  - *Times in `record.tex`.* Each time in the Protocol history section and each `created:`
    time in the Evidence record is set in `\mbox{...}`, so a line never breaks at one of its
    hyphens. `HistoryEntry.time_label` is unchanged: the shipped `make_si.py` copy is pinned
    to it.
  - *§7 Q9 decided (2026-10-11): third-party data takes the two-field rule.* An `external`
    entry ships only when it states both `license` and `redistribution: "author-asserted"`;
    with one or neither it is cited only (a manifest row with an empty `file` and "not
    redistributed"). `not_shipped_reason` names the field(s) it lacks. `verify` adds an
    advisory for an external entry that states exactly one of the two, the case that shipped
    before this decision; one stating neither is the default and gets none. The design text
    (D3, D4 `file` column, D5 table, D7, §7) is updated separately.
  - *Left to the package scripts.* The stdlib copies in `package/04_scripts/` still read the
    protocol files with `os.path.isfile` (links followed) and loop over the stated version
    unbounded: `build_record_index.py` (`protocol_files`) and `make_si.py`
    (`protocol_history`) need the same `lstat` refusal and the same bound (more than 10
    versions without a file), and `make_si.py`'s `protocol_section` the `\mbox{}` around
    each time it prints. (Done in the package hardening below, *The shipped builders*.)
  - *Tests.* `tests/test_deposit_hardening.py` (71 cases) pins each change;
    `tests/test_cli_verb_decomposition.py`'s `_without_protocol_history` now cuts a
    Protocol history section that is last to the end of the text (one case). Updated for Q9:
    `test_deposit_data.py` (which entries ship, the external-needs-a-name case, one folder
    name per data and inputs, the inputs test, the row-order test) and
    `test_deposit_data_package.py` (`_ship_all`); for `\mbox`: `test_deposit_phase1b.py`,
    `test_deposit_phase3.py`. Suite: 3033 passed, 2 skipped, 14 failed (Docker not
    running; the same 14 as before).
  - *Real trial.* Copies of `~/research/lit-search-trial-2` under
    `/tmp/sciadk-wf/core/trial-135144/`, with three declarations (the table cited, the
    workbook with `license` only, the workbook with both terms): each behaves as D3 now says
    and reports no deposit problem; `record.tex` shows the `\mbox{...}` times; a copy whose
    `spec.json` is a symbolic link is refused by `render --record-only` (exit 2) and reported
    by `verify`. `verify` does not pass on the trial for reasons outside this work: its
    numbers check fails, on an untouched copy as well. Measured again for v0.5 on an
    untouched copy (`/tmp/sciadk-wf/docs/trial-144504/`): every claim reproduces; the
    numbers check fails on the SI's undeclared times and seeds, and the publishing
    requirements on a paper rendered before the font policy and the current reproduction
    bundle; the deposit advisory says `paper/deposit/` is missing (rendered before the
    feature).
  - *Not run.* The Docker-only CLI test that uses `_without_protocol_history` (`run
    --t1-demo` against the verb chain) did not run, since Docker was not running; the
    helper's own unit test passes.
  - *Found, not fixed (older than this work).* `sci-adk render . --record-only` run from
    inside a run directory raises: `_cmd_render` takes `run_dir.parent.parent` without
    resolving the path.
- **Hardening of the package** (2026-10-11), after review of the built phases (the package
  assembler and gate, and the three scripts shipped in `package/04_scripts/`). Deviations
  from the review's wording are marked.
  - *No delete or write through a link.* With `package/06_provenance` or `package/02_data` a
    symbolic link, `_write_deposit` removed files in the link's target (`rmtree` through the
    linked parent). Before its first write `assemble_package` now raises `ValueError` (the
    CLI prints `error:` and exits 2; `package/` is untouched) when `package/` is a link, when
    a folder it writes into is one, or when any folder between `package/` and a path it
    clears is one. Addition: the folders it writes into are the six canonical folders plus
    `04_scripts/runs` and `06_provenance/verify_logs`, not only `02_data`, `05_inputs` and
    `06_provenance`; the others receive writes, and `03_figures/<id>` and
    `04_scripts/runs/<id>` are removed whole, just the same. `_clear(package_dir, rel)`
    repeats the check for its own path and still removes a link AT the path without
    following it; `_copytree_idempotent` now clears through `_clear`, so a link at
    `03_figures/<id>` is removed instead of making `rmtree` raise. Not done: a FILE the
    assembly writes (`MANIFEST.md`, `06_provenance/deposit.csv`, `01_manuscript/main.tex`)
    that is itself a link is still written through.
  - *`\path` compiles in the skeletons.* Both skeleton preambles (`main.tex`, `si.tex`) load
    `url`, after `graphicx`; a test compiles each skeleton with a
    `\path{02_data/<id>/table.csv}` added. No test locked the skeleton bytes, so none changed.
  - *Evidence ids in the package record (D4).* The package `deposit.csv` carried Evidence ids
    nothing in the package resolved, and `sha256_also_in` was empty for a recorded table, as
    for a derived one. `make_si.py` now writes a "Declared data files" section after the
    Protocol history: per run, each entry of `runs/<id>/deposit.json` declared `recorded` or
    `external`, as `\item[\texttt{<Evidence id>}] <description> SHA-256: <64 hex>`, the
    checksum computed with the standard library from the declared source (looked up in the
    run's folder, then the workspace, as `entry_source_path` does). `sha256_also_in` now names
    `06_provenance/record.tex` for those rows, and the `evidence` column resolves in the
    package. The section is left out when no packaged run declares such a file, so the record
    of a package without declared data keeps its bytes. The assembler runs the package's copy
    of `make_si.py` in process (`build()`); there is no second copy to change. On the real
    trial (the declaration with both terms on the workbook) the table row and the decrypted
    copy's row, both cited only, now name `06_provenance/record.tex`. Still not done: the D9
    "Data & code availability" listing of every `deposit.csv` row with its terms.
  - *Protocol digests in the package gate (D11).* `package_deposit_problems` recomputes each
    packaged run's protocol digest from `runs/<id>/` and fails when `run_index.csv` has no
    `protocol_digest_sha256` column, no row for the run or another value there, or when the
    run's block in the Protocol history section of `06_provenance/record.tex` prints no digest
    or another one.
  - *Assembled before the feature.* Only a package with none of `deposit.csv`,
    `06_provenance/protocol/`, a Protocol history section in `record.tex` and a
    `protocol_digest_sha256` column in `run_index.csv` gets the one advisory. With any of them
    a missing `deposit.csv` fails, and a missing protocol folder fails through the copies it
    should hold. `test_a_package_assembled_before_deposit_files_gets_one_advisory` now removes
    both markers too.
  - *The citation message names the package bibliography.* The package gate's citation
    failures read "cite key 'K' is not in 01_manuscript/references.bib, supplied via
    package_src/references.bib" (`deposit_data_problems(..., bib_name=...)`; the per-run text
    is unchanged). Not done, by choice: seeding the placeholder bibliography with the entries
    the declared data cite from the runs' `paper/references.bib`. The assembler writes the
    placeholder once and keeps it across assemblies, so a seeded copy would go stale when a
    declaration changes or would have to overwrite a bibliography edited in place;
    `package_src/references.bib` stays the one source.
  - *Removal notes.* Each file the assembly removes from `06_provenance/protocol/`,
    `02_data/<id>/` or `05_inputs/<id>/` that no row lists gets a note, "removed <path>: no row
    of 06_provenance/deposit.csv listed it; the package rebuilds <folder>/ on every assembly";
    a link there gets "removed <path>, a symbolic link (its target was not touched)". `sci-adk
    package` prints them as `note:`. Deviation: a row is one of the earlier `deposit.csv` or of
    the rows written now, since a file at a path the new rows list is replaced, not lost.
  - *`check_package.py` reads `deposit.csv`.* A fourth check, with the standard library only:
    every row's file exists, with no link on the way, and has the row's SHA-256 and size;
    every file under `06_provenance/protocol/<run>/` and the packaged runs' `02_data/<run>/`
    and `05_inputs/<run>/` is a row; a protocol subfolder that is no packaged run fails, and so
    does a `02_data/` or `05_inputs/` folder named after a run of the workspace around the
    package that is not packaged; the names rule of `package_name_problems`, with the
    withheld runs and the per-run-to-package path map read from `deposit.csv` (the packaged
    runs are its `run` column). It prints that it does not compare the rows with the record.
    A package with no trace of the feature prints "deposit files not checked" and passes, as
    the gate's advisory does. Tests pin its patterns and its names messages to the gate's.
    Not done: it does not recompute the protocol digests and compare them with
    `run_index.csv`, as the gate now does (above).
  - *The shipped builders.* `build_record_index.py` (`protocol_files`) and `make_si.py`
    (`protocol_history`) read every protocol file after `lstat`, refuse a linked `spec.json`,
    history file, receipt, `spec_history/` or `checkpoints/`, and refuse a version with more
    than 10 of versions 1..V unaccounted for, as `plan_protocol` does. Both raise
    `ValueError`: the run's `run_index.csv` cell reads `n/a` and the record says its protocol
    files could not be read (the assembler, which plans first, stops before writing).
    `make_si.py` sets each Protocol history time in `\mbox{...}`, as the per-run record does.
  - *Real trial.* Copies of `~/research/lit-search-trial-2` under `/tmp/sciadk-wf/pkg/`: the
    trial as it is (no declared data) and with the core review's declaration `both.json`.
    `check_package.py` passes on both packages and fails a tampered shipped workbook (its
    SHA-256 and size); a hand-added `05_inputs/<id>/mine.csv` is removed with a note; with
    `06_provenance` a link, `sci-adk package` exits 2 and the link's target keeps its file.
    The package gate fails on the trial for reasons outside this work (no frozen
    `pkgreqs.json`; number audit of the skeleton) and, with the declaration, for its cite key
    missing from the placeholder bibliography, now named as above.
  - *Tests.* `tests/test_deposit_package_hardening.py` (65 cases); updated in
    `test_deposit_phase1b.py`: the pre-feature test (above) and the package Protocol history
    assertion, which now reads `recorded \mbox{...}`.
- **v0.5** (2026-10-11): the design text, the workspace instructions and the README brought in
  line with the two hardening entries above.
  - *§7 Q9 recorded as resolved.* The user's decision of 2026-10-11 (Q5: a table of
    third-party values ships only with both terms) is applied uniformly: an `external` entry
    also needs both `license` and `redistribution` to ship. The code changed in the core
    hardening (above); the text changes here: D3 (`origin`, Which entries ship, the note under
    the example), D4 (`file` column), D5 (external, cited not shipped, terms), D7, §4 (a new
    rejected alternative), §6.7, and §7 (Q9 moved to Resolved). The Phase 2 note "a
    third-party entry that is not shipped gets no `verify` advisory" now holds only for one
    that states neither term.
  - *The `artifacts/` bypass, stated.* D7 gains a bullet and D8's `artifacts/` bullet a
    closing paragraph: the package copies `runs/<id>/artifacts/` whole, so a file there ships
    whatever the declaration says; the package reports it as an advisory, never a failure,
    and only for a declared file whose bytes it finds there. An undeclared file there ships
    with no row and no advisory, including literature PDFs in the older
    `artifacts/literature/` layout. §7 Q3 notes that listing that copy in the manifest would
    close the bypass. No code changed.
  - *What render writes, everywhere it is listed.* The foundation skill's verb table and the
    output style's Stage 4 now name `paper/deposit/` and `--deposit`. Deviation: to put both
    under the render-flags test, both now show the paper render command itself
    (`sci-adk render <run> --prose prose.json [--si si.json] [--deposit deposit.json]`; in
    the verb table it replaces the bare `sci-adk render` in the verb column). Tests: every
    paragraph, list item or table row of the hub, the writer, the foundation skill and the
    output style that names `sci-adk render`, `draft.tex` and `si.tex` names `paper/deposit/`
    and `--deposit`; the paper render the foundation skill and the output style show uses the
    publish skill's flags.
  - *The terms in the instructions.* The publish skill's "An `external` file ships when it
    states either" now says an `external` file takes the same rule and ships only with both;
    the `expert-writer` agent's summary of the terms names a third-party file beside a study
    file of third-party values. Tests pin both and reject "either" there.
  - *Package skill.* Its naming section says `\path{…}` comes from the `url` package, which
    both skeleton preambles now load, and that a venue's preamble must keep
    `\usepackage{url}`. A test pins it.
  - *README.* The "Deposit files" bullet is two sentences: what `paper/deposit/` holds, and
    that a third-party file or a table of third-party values is cited by its checksum and not
    shipped unless its entry states both terms. A test pins the two sentences. Cut from it:
    the persisted `runs/<id>/deposit.json`, `verify`'s re-hashing and the package copy.
  - *Counts.* Ten new cases in `tests/test_deposit_phase3.py`. Suite: 3,124 tests, 3,108
    passed, 2 skipped (no `mcp`; no `pgfplots`), 14 failed (Docker not running; the same 14
    as before), in 140 test files; the README's counts were re-measured to these. No source
    module changed in this entry.

## Review of v0.1: where each point is resolved

| Point | Resolved in |
|---|---|
| 1. History outside `record_digest`; `prior_version_id` is a timestamp; the chain check compares editable files | D11 (v0.1 §7 Q1 argued; option B chosen, record digest unchanged, no Spec field), D5 "what a pass shows", D9, D10; external anchor tied in §7 Q1 |
| 2. Generic `paper/data/`, `paper/inputs/`; names regex on prose; bare re-render drops data | D13 (one root, render touches only what it wrote), D2 (persisted declaration, every render path), D5 names check keyed on `deposit/` |
| 3. Licensing of default-shipped files | D3 (`license` defined, `redistribution`, top-level `license`), D5 terms, D7, D9 |
| 4. Vocabulary table re-measured | D6 (re-measured again for v0.3) |
| 5. Ids inside `paper/` | D4 (id-free per-run manifest; ids beside `record.tex`; `--record-only` in D2, D13) |
| 6. `derived` | D3 (no integrity claim), §4 |
| 7. Package mode | D8 |
| 8. Temporal claim | D12 (advisory line, clock sources), D9 (clauses reworded), D10 |
| 9. Facts and open questions | §1 table (workbook checksum in 6 Evidence items and the rationale), D3 (symlinks), §7 Q4–Q7 |

## Review of v0.2: where each point is resolved

| Point | Resolved in |
|---|---|
| 1. Vocabulary table stale: `spec_history` and `spec.v<N>.json` already flagged, all filename patterns case-insensitive | D6 re-measured row by row on the current tree; the `spec_history` addition and the case paragraph deleted; two patterns proposed (`checkpoints/…` names, `deposit` in the JSON-name alternation); §1 sentence corrected; code cited by symbol throughout |
| 2. Deletion guards for previously deposited files | D13 (marker, trusted manifest: relative `protocol/` `data/` `inputs/` + plain name inside `paper/deposit/`, no `..`, absolute path or symlink; one bad cell removes nothing; removal only of unchanged bytes; byte-identical files count as written, so a lost manifest does not block); §4; §6.10 |
| 3. Stale files in the package | D8 (three owned per-run namespaces cleared and rebuilt, also when empty; deselected runs cleared; package inventory = those namespaces + `deposit.csv`); §6.15 shrink then rebuild |
| 4. Names check in LaTeX; case | D5 normalisation (`\_`, trailing punctuation, `\path`), D8 package names check; D3 case-insensitive uniqueness and reserved names; §6.12, §6.14 |
| 5. Render-time checks before Evidence is persisted | D5 (render's checks read the Evidence `stage_render` receives; times advisory in `verify` only; measured order noted); §6.5 |
| 6. Availability example named the wrong checksum | §1 table (decrypted copy, 25 Evidence items), D3 (copies of third-party files are `external` entries of their own; example), D9 (example corrected), D7; §7 Q8 |
| 7. Package naming guidance and tokenizers | D8 (tokenizer per mode, measured table, guidance on paths, names, checksums, times); §6.12, §6.15 pins |
| 8. Evidence-item option for the anchor | D11 option D; §7 Q1; D10 |
| 9. Manifest values in working vocabulary; `reproduce.py` description | D4 (`kind`, `sha256_also_in`, fixed protocol descriptions, vocabulary test over the manifest), D3 (`description` checked); §1 and D9 describe `reproduce.py` as listing the scripts, checking every shipped file's SHA-256 and running nothing |

---

Version: 0.5 (approved for implementation 2026-10-11; Phases 1, 2 and 3 built and hardened
2026-10-11)
Source: 2026-10-10 — trial run SPEC-BCFKOW-001: the paper's pre-registration claim and its SI
rest on files that neither the per-run bundle nor the package ships; v0.2 and v0.3 after
review; v0.4 records the decisions of 2026-10-11 on §7 Q5 and Q6; v0.5 records §7 Q9 and the
hardening.
Related: design/si-belief-record-split.md, design/paper-figures-and-si.md,
design/declared-numbers.md, design/near-submission-package.md,
design/paper-publishing-requirements.md, design/reader-facing-prose.md §12.3
