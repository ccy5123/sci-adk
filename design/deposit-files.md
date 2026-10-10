# Deposit files: shipping the protocol history and declared data with the paper

> Status: **v0.3 DRAFT (2026-10-10)** — design only, nothing built. Revised after a review of
> v0.1 and a second review of v0.2; the points of both and where each is resolved are listed
> at the end. Decisions below are proposals awaiting confirmation.
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

In: the frozen protocol history of a run; data files the author declares; the manifests; the
`verify` checks on them; a protocol digest; a times advisory; the vocabulary check; the terms
each shipped file is distributed under; the SI and availability wording that follow.
Domain-neutral throughout: nothing below knows what the files contain.

Out: what `verify` computes on the record; `record_digest`, which stays as it is (D11); the
Spec model, which gets no new field (its `model_dump` feeds both digests); the code bundle
(`code/`, `reproduce.py`), which keeps its own gate; `numbers.json`; an external time anchor
(§7 Q1).

## 3. Decisions

### D1 — The protocol history always ships, as exact bytes, under reader-facing names

| Record file | In the per-run bundle | In the package |
|---|---|---|
| `spec_history/spec.v<N>.json`, each N < V | `paper/deposit/protocol/protocol-v<N>.json` | `06_provenance/protocol/<id>/protocol-v<N>.json` |
| `spec.json` (version V, current) | `paper/deposit/protocol/protocol-v<V>.json` | `06_provenance/protocol/<id>/protocol-v<V>.json` |
| `checkpoints/amendment-v<N>.json` | `paper/deposit/protocol/amendment-v<N>.json` | `06_provenance/protocol/<id>/amendment-v<N>.json` |

- **Always.** Written on every full render with no declaration needed: every run has a
  frozen protocol, and every paper's methods rest on it. An unamended run ships
  `protocol-v1.json` alone. The package builds these copies from `runs/<id>/` directly (D8),
  so a run rendered before this feature is still covered.
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
  partial copy is not offered: a redacted file would no longer match its checksum (§7 Q6).

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
declaration. To stop shipping data, pass a declaration whose `files` is empty. Render prints
which declaration it used and how many files it shipped. `verify` and `package` read the
persisted declaration (D4, D8).

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
     "redistribution": "author-asserted",
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

Top-level keys are exactly `spec_id`, `license`, `files`; entry keys exactly `source`, `name`,
`origin`, `evidence`, `cite`, `license`, `redistribution`, `description`. Anything else is
rejected, and a load error names the entry index (as `core/numbers.py` does). `spec_id` must
equal the run's Spec id.

- `source`: a relative path, looked up in the run dir first, then the workspace (as `code_ref`
  lookup). No absolute path, no `..`, and the path with every symlink resolved must lie inside
  the workspace. This is stricter than `code_ref`, which takes an absolute path as given
  (`_existing_file` in `loop/code_ref.py`), because these bytes are copied into a bundle meant
  for distribution. Missing at render → render fails. A protocol file (D1 ships it) and
  anything under `runs/<id>/paper/` (the bundle itself) are rejected as sources.
- `name`: a plain file name (`[A-Za-z0-9._-]+`, no leading dot), required for every file that
  ships, and unique within its folder **compared case-insensitively**: two names that differ
  only in case are one file on the file systems most readers unpack to. Rejected: a name the
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
    as two entries (above); no field links them (§7 Q8). Not copied unless `license` or
    `redistribution` is given (D7).
- `evidence`: the Evidence id that holds the checksum; required for `recorded` and `external`,
  optional for `derived`.
- `cite`: bib keys of the sources the file's values come from. Required and non-empty for
  `external`; for `recorded` and `derived`, non-empty whenever the file holds values taken from
  a third-party source.
- `license`: the terms under which **the deposited file itself** is distributed (for example
  `CC-BY-4.0`), not the terms of the study's code or of the file's sources.
  `redistribution`: the single value `"author-asserted"`, the authors' statement that
  redistribution is permitted, without naming terms. Every file that ships with a non-empty
  `cite` needs one of the two, or the declaration fails to load (D7). An entry with an empty
  `cite` and no `license` takes the top-level `license`.
- `description`: one line. Rejected when the vocabulary check flags it, so the manifest built
  from it passes the same check (D4).
- top-level `license`: the terms for the files this study produced — the protocol files and
  every entry with an empty `cite` — unless an entry states its own. Optional; when it is
  absent, `verify` says so once (D5).

### D4 — Two manifests: Evidence ids only beside the record that resolves them

Per run, render writes `paper/deposit/manifest.csv`, which carries **no record identifiers**.
The package writes `06_provenance/deposit.csv`, the same columns plus `run` and `evidence`. One
row per file, sorted by path, third-party files that are not shipped last; re-rendering the
same record and declaration writes the same bytes. The per-run manifest's first line is a
fixed marker (D13); the package's `deposit.csv` has none, because the package rebuilds its
folders whole (D8).

The column values are written for a reader of the bundle, not in the declaration's terms:

| Column | Content |
|---|---|
| `file` | per run, the path relative to `paper/deposit/` (`protocol/protocol-v1.json`, `data/chemicals.csv`); in the package, relative to the package root; empty for a third-party file that is cited, not shipped, and for a protocol version whose file was not kept |
| `sha256`, `bytes` | of the file's bytes; empty for a version not kept |
| `kind` | `protocol` (a protocol version), `amendment`, `study data` (declared `recorded` or `derived`), `third-party data` (declared `external`) |
| `sha256_also_in` | the other files that state this SHA-256, separated by `;`: for a replaced protocol version, its amendment file (`protocol/amendment-v<N+1>.json`); and `record.tex`, the deposited record, wherever it prints the value — every protocol and amendment file (its Protocol history section, D11) and every `recorded` or `external` file whose Evidence item it prints. Empty when no other file states it: a `derived` file, a version not kept |
| `cite` | bib keys, resolved in the shipped `references.bib` |
| `license` | the file's terms: its own `license`, "redistribution asserted by the authors", the top-level `license` it takes, or empty |
| `description` | one line, from the declaration; for protocol rows fixed text: "protocol, version N (current)", "protocol, version N, replaced by version N+1", "amendment that produced version N", "protocol, version N; file not kept" |
| `run`, `evidence` | package only: the run id, and the Evidence id that holds the checksum |

`sha256_also_in` replaces v0.2's `record` column, whose values ("checksum held by the record",
"not in the record") pointed at something the per-run bundle does not hold and used the
record/belief vocabulary of this design. The new column names files a reader can open and
search, and it carries the same distinction: a `recorded` table shows `record.tex`, a `derived`
one shows nothing. Render computes it by searching the protocol files and the `record.tex` it
writes for the 64-hex token; `verify` recomputes it (D5, plan). The per-run manifest passes
`check_paper_tool_vocabulary` whole, marker line included, and a test locks that (§6.11); so
does the package `deposit.csv` without its `run` and `evidence` columns.

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
column, and rebuilds the expected rows from `runs/<id>/` and `runs/<id>/deposit.json`.

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
| plan | the manifest rows are the rows `runs/<id>/`, the persisted declaration and `runs/<id>/record.tex` call for (`sha256_also_in` recomputed from the protocol files and `record.tex`) | fail | the render is not stale: no amendment and no new declaration since |
| current protocol | `protocol-v<V>.json` bytes equal `runs/<id>/spec.json`; V equals the Spec's version | fail | the protocol shipped is the one the results were judged against; its content is covered by the record digest |
| earlier protocols | the SHA-256 of `protocol-v<N>.json` equals `prior_spec_sha256` in `amendment-v<N+1>.json` and the SHA-256 of `spec_history/spec.v<N>.json`; version N's `created_at`, as `str(created_at.timestamp())`, equals version N+1's `prior_version_id`; versions 1…V present | fail; a version not kept (D1) is advisory | the history files, the receipts and the copies agree with one another — nothing more. They are outside the record digest (D11): a rewrite of an earlier version that keeps its `created_at`, made together with its receipt's `prior_spec_sha256`, passes. The one link inside the digest is the current `spec.json`'s `prior_version_id` (set by `Spec.amend`), and it fixes a time, not content |
| amendments | `amendment-v<N>.json` bytes equal the checkpoint file; its `rationale` equals version N's `amendment_rationale` | fail | copy fidelity; for the latest amendment, its rationale matches the digest-covered `spec.json` |
| protocol digest | computed and printed for every run (D11) | printed | — |
| recorded | the file's SHA-256 occurs as a 64-hex token in the named Evidence item (its serialized JSON, any case) | fail; the message names any other items that hold it | the record, which the record digest covers, names these exact bytes |
| derived | listed as unchecked; a named `evidence` item exists; if the file's hash does occur in the record, advise declaring it `recorded` | listing advisory; fail only for a missing item | nothing about the bytes |
| external | the SHA-256 occurs in the named item; every `cite` key resolves in `references.bib`; the file is copied only with `license` or `redistribution` | fail | the record names these bytes and the paper cites their source |
| terms | every shipped file with a non-empty `cite`, listed with its `license` or "redistribution asserted by the authors"; with no top-level `license`, one line saying the bundle's own files state no terms | advisory | every redistribution is a visible declaration |
| names | every path in `draft.tex` / `si.tex` outside `\url` and `\href` (bare, in `\texttt` or in `\path`) that, after normalisation, starts with `deposit/` (not preceded by a word character, `/` or `.`) and ends in a file name with an extension is `deposit/` + a manifest `file` | fail | the paper points only at files the bundle holds |
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

### D7 — Third-party data is cited with its checksum, not redistributed; every shipped file states its terms

- **External data.** An `external` entry with neither `license` nor `redistribution` is not
  copied. Its manifest row has an empty `file`, the checksum and the citation (and, in the
  package, the Evidence id). With either, the file is copied to `paper/deposit/inputs/`
  (package: `05_inputs/<id>/`) and `verify` lists it with its terms. sci-adk does not judge
  licenses; it makes each redistribution a visible declaration. The literature PDFs a run
  acquired are external by this rule and never ship by default; so does a copy the study made
  of a third-party file (D3: the trial's decrypted workbook).
- **Tables built from third-party values are derivatives.** A `recorded` or `derived` table can
  hold values taken from a cited source; the trial table holds BCF values from the cited
  workbook. Such a file ships by default, so without a rule the default would redistribute
  third-party values unannounced. D3 requires `license` or `redistribution: "author-asserted"`
  on every shipped entry with a non-empty `cite`, and `verify` lists all of them. Both are the
  authors' statements; sci-adk records them and checks neither.
- **The bundle's own files.** The top-level `license` gives the terms for the protocol files
  and for every entry with an empty `cite`. The availability statement names it (D9).
- **The package README.** `05_inputs/README.md` is generated from the rows: each third-party
  file with its citation, its checksum and "not redistributed" or its terms; then each shipped
  file with a non-empty `cite`, with its terms. The sentence "Nothing copyrighted is
  redistributed here" (`_write_inputs_readme`) is written only when no shipped file has a
  non-empty `cite`. With no deposit rows the README keeps today's text.

### D8 — Package placement

Per-run folders follow the package's existing convention (`03_figures/<id>/`,
`04_scripts/runs/<id>/`, `_colocate_run_artifacts` in `render/package.py`).

| Content | Package path | Built from |
|---|---|---|
| protocol | `06_provenance/protocol/<id>/protocol-v<N>.json`, `…/amendment-v<N>.json` | `runs/<id>/` directly, never the per-run copies |
| `recorded`, `derived` | `02_data/<id>/<name>` | `runs/<id>/paper/deposit/data/<name>`, the copy the per-run `verify` checked |
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
  fails the gate.
- **Declared files** follow each run's persisted declaration; a declared file missing from
  that run's `paper/deposit/` stops assembly with "re-render run <id>". The package processes no
  second declaration. Two runs may declare the same `name`; the per-run folders keep them apart.
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
  `02_data` copy is the checked one. (The trial run has no `artifacts/`.)
- **The package names check.** `01_manuscript/main.tex` and `si.tex` are written for the
  package and name package paths (`02_data/<id>/chemicals.csv`,
  `06_provenance/protocol/<id>/protocol-v1.json`, `06_provenance/deposit.csv`). With the D5
  normalisation (every package path contains `_`, so LaTeX spells it `02\_data` outside
  `\path`), every path in them that starts with `02_data/`, `05_inputs/` or `06_provenance/`
  must exist in the package; a per-run `deposit/…` path fails, and the message gives the
  package path its manifest row maps to.

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
and the terms, and cites external data with its checksum. Example, with an illustrative
license (checksums elided here, written in full in the paper):

> The protocol in both versions and its amendment (`deposit/protocol/`), the table of the 404
> chemicals that passed the filters (`deposit/data/chemicals.csv`) and the analysis scripts
> (`code/`; `reproduce.py` lists them and checks each against its SHA-256) are distributed with
> this paper; `deposit/manifest.csv` lists every file with its SHA-256 and the terms it is
> distributed under. Files produced in this study are distributed under CC BY 4.0. The chemical
> table contains BCF values from Arnot and Gobas (2006); the authors state that its
> redistribution is permitted. The BCF database is not redistributed: it is the supplementary
> file of Arnot and Gobas (2006), SHA-256 `d5f642bdaf3c69fa…7dc7f8f0`, encrypted with Excel's
> default key, and every analysis step read a decrypted copy, SHA-256
> `1081e637f6bd39f9…fd95c461`, which is not redistributed either.

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
  may not yet be persisted at compile time.
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
  `paper/deposit/`: `protocol/`, `data/` (`recorded`, `derived`), `inputs/` (redistributed
  `external`) and `manifest.csv`. No generic folder (`paper/data/`, `paper/inputs/`) is
  created: authors keep pgfplots tables or Overleaf data there, which a render-owned folder
  would overwrite and an inventory rule would fail.
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
- **Lost manifest.** With no manifest, an unreadable one or an untrusted one, render removes
  nothing and still renders: files whose bytes equal what it writes count as written (c), so a
  lost manifest does not block the next render. Files an earlier render wrote and this one does
  not are left; the inventory check fails on each, naming it, for the author to delete.
- A file someone else puts under `paper/deposit/` is never touched by render; the inventory
  check fails on it, naming it.
- `--record-only` writes nothing under `paper/` and leaves `runs/<id>/deposit.json` alone; the
  `record.tex` it writes carries the Protocol history section (D11).

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
`paper/deposit/inputs/`; the recorded, derived, external, terms and names checks, the render
side reading the Evidence `stage_render` receives; package `02_data/<id>/`, `05_inputs/<id>/`
rebuilt as owned namespaces, the generated `05_inputs/README.md` and the package names check.

**Phase 3 — instructions and Evidence times.** Workspace skills: the experiment stage records
`<path> sha256=<hex>` in `data_ref` for every output table a paper may ship (as
`declared-numbers.md` §4.4 does for counts); the publish stage writes `deposit.json` with its
terms, declares a copy made of a third-party file as its own external entry, names deposited
files in the SI and availability statement by their bundle paths, follows the D8 guidance on
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
   passes; against an item that does not hold the hash it fails and names the five that do; a
   modified copy fails. Render's check reads the Evidence list it is given: `stage_render`
   called with a list whose item holds the hash warns about nothing even when `evidence/` on
   disk lacks that item, and `verify`, reading the disk, fails.
6. **Derived.** Listed as unchecked; a named Evidence id that does not exist fails; a derived
   file whose hash the record holds gets the "declare it recorded" advisory.
7. **External.** The workbook (`d5f642bd…`) and its decrypted copy (`1081e637…`), declared as
   two entries against `evi-obs-20261008-datasource-arnotgobas2006`, both pass and neither is
   copied; each row has an empty `file`, its checksum and `Arnot2006`. With the decrypted copy
   declared against an item that does not hold it, the message names the 25 items that do.
   With `license` a file lands in `deposit/inputs/` and its terms are listed. A `cite` key
   absent from `references.bib` fails; a checksum absent from the record fails.
8. **Terms.** A `recorded` entry with a non-empty `cite` and neither `license` nor
   `redistribution` fails to load; with `redistribution: "author-asserted"` it ships and is
   listed; no top-level `license` gives one advisory; the top-level `license` appears in the
   protocol rows and the rows with an empty `cite`.
9. **Persisted declaration.** A render with `--deposit` writes `runs/<id>/deposit.json`; a bare
   `render`, `run` and `resolve` then ship the same data; `files: []` stops shipping and removes
   the data files the previous render wrote; an invalid declaration leaves the persisted one
   untouched; `--record-only` with `--deposit` is rejected and nothing under `paper/` changes.
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
    `protocol-v2.json`, `amendment-v2.json` and the chemical table, and is empty for a derived
    file. The package `deposit.csv` has the `run` and `evidence` columns.
12. **Names.** An SI naming `deposit/data/missing.csv` fails; "the script reads data/raw/x.xls",
    "zenodo.org/deposit/1.json" and paths inside `\url` pass. With a row `data/my_table.csv`,
    `deposit/data/my\_table.csv` in prose and in `\texttt`, `\path{deposit/data/my_table.csv}`,
    and the path followed by `.`, `,` or `)` all pass; `deposit/data/My_table.csv` fails. The
    trial SI rewritten as in D9 passes the vocabulary and names checks. Tokenizer pins on the
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
    differs from the run's, a flagged `description` — each rejected with the entry index.
15. **Package.** Files at the D8 paths; protocol rows built from `runs/<id>/` even when the
    per-run copy is stale; package `verify` fails after an amendment made post-package; the
    package number-audit pool is unchanged by `02_data/<id>/chemicals.csv`; a per-run
    `deposit/…` path in `main.tex` fails with the package path in the message;
    `\texttt{02\_data/SPEC-BCFKOW-001/chemicals.csv}` resolves in the package names check;
    `05_inputs/README.md` lists the third-party and the cite-bearing rows and drops "Nothing
    copyrighted is redistributed here" when a shipped file has a `cite`; `MANIFEST.md` lists
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
   wholesale copy of `runs/<id>/artifacts/` (D8) should be listed there too.
4. **File size.** The trial table is 51,239 bytes, each workbook copy 4,777,472 bytes, and the
   run's acquired literature 29 MB. The per-run `paper/` is uploaded to Overleaf as a folder,
   and journals limit supplementary files. Whether render warns above a size, and whether large
   declared files ship only in the package.
5. **Tables that hold third-party values.** D7 lets them ship on the authors' statement.
   Whether that is enough, or whether a `recorded` or `derived` entry with a non-empty `cite`
   should default, like external data, to cited and not shipped, with shipping opt-in.
6. **The raw proposal always ships.** Every protocol version carries `raw_proposal` verbatim,
   working notes and names included. A redacted copy would not match the checksums the receipt
   and the chain rely on, so the only consistent opt-out is withholding a run's protocol
   entirely: rows marked "withheld", no files, and an SI that cannot name them. Whether to
   offer it.
7. **Shared data outside the workspace.** D3 requires a source to resolve inside the
   workspace, so data kept on a symlinked shared drive cannot be declared. Whether to allow a
   list of extra roots, or to require a copy inside the workspace.
8. **Transformed third-party files.** The trial's decrypted workbook is declared as a second
   external entry, and "the cited file decrypted with msoffcrypto-tool 6.0.0" lives only in its
   description and the methods (D3, D9). Whether an entry should name its source entry and the
   tool in structured fields, and the manifest show the pair as linked. `verify` could then
   check that both checksums sit in one Evidence item and that the tool is named there; it
   still could not check the transformation without running it (§4).

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

Version: 0.3 (draft)
Source: 2026-10-10 — trial run SPEC-BCFKOW-001: the paper's pre-registration claim and its SI
rest on files that neither the per-run bundle nor the package ships; v0.2 and v0.3 after
review.
Related: design/si-belief-record-split.md, design/paper-figures-and-si.md,
design/declared-numbers.md, design/near-submission-package.md,
design/paper-publishing-requirements.md, design/reader-facing-prose.md §12.3
