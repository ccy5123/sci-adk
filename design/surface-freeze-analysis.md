# sci-adk 1.0 Surface Freeze Analysis (G-D D1)

> Status: ANALYSIS + DECISION RECORD (the surface contract for semver 1.0)
> Created: 2026-06-26 (sci-adk session 9)
> Classification: PLANNING RECORD — measures the public surface and records the
> freeze decisions. It does **not** itself bump the version or apply `__all__`;
> those are the G-D D1/D2 execution steps, listed in §7.
> Resolves the basis of `design/release-readiness.md` §6 D1 (`[OPEN]` "surface still growing").

## 0. What this is

semver 1.0 is a **stability promise**: the public surface will not break within
the major version. Before promising it, the surface has to be (a) enumerated
exactly, (b) shown to have stopped growing, and (c) scoped — what counts as
"public" and therefore covered by the promise. This record does all three,
grounded in measurement of `src/sci_adk/cli.py` and `src/sci_adk/core/`.

Decisions taken (user, 2026-06-26):
- **Stability scope = CLI + a curated Python API** (§4).
- **The publishing layer (`package` / `pkgreqs` / `pubreqs`) is part of the 1.0
  stable surface** (§2), not experimental.

## 1. The CLI is the primary public contract

Entry point: `pyproject.toml:51` `sci-adk = "sci_adk.cli:main"` → `src/sci_adk/cli.py`
(1845 LOC). Measured surface: **17 top-level verbs, 83 `add_argument` flags.**
This is how sci-adk is actually consumed — IEAM-P8 (the 2nd-domain validation,
`design/g-a-a3-decision.md`) used the installed **binary**, not Python imports.

## 2. CLI surface inventory (the frozen contract)

Grouped by lifecycle role. Positional args in `<…>`; `?` = optional positional.
"freeze" rows are the single subcommand under `pubreqs` / `pkgreqs`.

### 2.1 Compiler — one-shot

| Verb | Positional | Flags |
|------|-----------|-------|
| `run` | `<proposal?>` | `-o/--output`, `--spec-id`, `--capability`, `--t1-demo`, `--prose`, `--si-prose`, `--figures`, `--no-strict-science` |

### 2.2 Compiler — the 6 decomposed stage verbs (`cli.py:298` `_add_verb_parsers`; commit `69558a5`)

| Verb | Positional | Flags |
|------|-----------|-------|
| `init-spec` | `<proposal?>` | `-o/--output`, `--spec-id`, `--capability`, `--t1-demo` |
| `amend-spec` | `<run_dir>` | `--rationale` (required) |
| `execute` | `<run_dir>` | `--capability`, `--t1-demo`, `--force` |
| `append-evidence` | `<run_dir>` | `--evidence` (required), `--spec-digest` |
| `derive-claim` | `<run_dir>` | `--no-strict-science`, `--spec-digest` |
| `render` | `<run_dir>` | `--prose`, `--si-prose`, `--figures` |

### 2.3 Judgment / verification path (the verdict surface)

| Verb | Positional | Flags |
|------|-----------|-------|
| `verify` | `<run_dir>` | `--strict-science` |
| `resolve` | `<run_dir>` | (none) |
| `prior-work` | `<run_dir>` | `--searched DOI… \| --skip` (required, exclusive), `--reason`, `--target-id`, `--allow-no-email` |
| `novelty` | `<run_dir>` | `--hypothesis` (req), `--kind result\|method` (req), `--searched \| --skip` (req, exclusive), `--outcome`, `--reason`, `--allow-no-email` |
| `contested` | `<run_dir>` | `--hypothesis` (req), `--searched \| --note` (exclusive), `--allow-no-email` |
| `status` | `<run_dir>` | `--json` |

### 2.4 Bootstrap

| Verb | Positional | Flags |
|------|-----------|-------|
| `init-session` | `<dir>` | `--dry-run` |

### 2.5 Publishing (part of the 1.0 stable surface — user decision)

| Verb | Positional | Flags |
|------|-----------|-------|
| `pubreqs freeze` | `<run_dir>` | `--defaults`, `--venue`, `--required-section`, `--no-font-policy`, `--image-min-dpi`, `--no-image-dpi`, `--reference-style`, `--max-pages`, `--max-words`, `--no-repro-bundle`, `--advisory` |
| `pkgreqs freeze` | `<workspace>` | `--defaults`, `--venue`, `--required-section`, `--no-font-policy`, `--image-min-dpi`, `--no-image-dpi`, `--reference-style`, `--abstract-max-words`, `--body-word-min`, `--body-word-max`, `--run`, `--advisory` |
| `package` | `<workspace>` | `--no-assemble` |

## 3. Growth timeline (measured — the surface has stopped growing)

`git log` over `src/sci_adk/cli.py`, newest → oldest:

| Commit | CLI surface change |
|--------|--------------------|
| `6e96103` (R1, advisory channel) | **none** — `paper_advisory` is an internal output channel; zero new flags |
| `c3ca867` (SPEC-PAPER-GATE M1) | added `pkgreqs freeze` flags |
| `cb61542` | added `package` verb |
| `0ff48bc` | added `pubreqs` |
| `69558a5` | decomposed `run` into the 6 stage verbs |

The surface grew steadily through M1; the **most recent commit (R1) is the first
in recent history with no surface change.** So `release-readiness.md` D1's
`[OPEN]` "still growing" was accurate as of M1 and is now satisfied — the surface
stabilized one commit before HEAD. The full test suite (1362 passed) covers it,
and the publishing layer is additionally gated by the SPEC-PAPER-GATE-001
`verify` gates (`paper_requirements_clean` / `package_requirements_clean`).

## 4. Python API surface — gap + the curated 1.0 export

**Measured gap (RESOLVED 2026-06-26):** `src/sci_adk/__init__.py` was **empty** — no
`__all__`, no curated exports. Consumers reached into submodules directly. A
semver-1.0 promise that includes a Python API needs an explicit, curated export
surface declared *before* 1.0. This is now implemented (§7 step 1): the root
re-exports the 29 symbols below, guarded by `tests/test_public_api.py`.

The curated surface is the record/belief core + the sole verdict path — the
symbols a Python embedder legitimately needs, and exactly the ones the public
identity already names. Measured locations:

| Symbol | Source | Role in the 1.0 API |
|--------|--------|---------------------|
| `Spec`, `Hypothesis`, `RawProposal`, `MethodPlan`, `DecisionRule`, `TargetClaim`, `DiscriminatingCase` | `core/spec.py:414/210/66/357/93/392/177` | frozen compiler input (record) |
| `HypothesisMode`, `DecisionRuleKind` | `core/spec.py:31/44` | Spec enums |
| `EvidenceItem`, `Provenance`, `Result`, `Bearing`, `Cost` | `core/evidence.py:534/128/185/249/107` | append-only record |
| `EvidenceKind`, `BearingDirection` | `core/evidence.py:30/87` | Evidence enums |
| `Claim`, `Confidence`, `EvidenceLink`, `StatusChange` | `core/claim.py:220/110/171/192` | revisable belief |
| `ClaimStatus`, `ConfidenceType`, `ConfidenceLevel`, `EvidenceLinkRole` | `core/claim.py:34/57/75/94` | Claim enums |
| `DecisionEngine` | `loop/decision_engine.py:126` | the verdict engine |
| `verify_run`, `verify_package`, `VerifyReport`, `PackageVerifyReport` | `loop/verify.py:281/460` | the sole verdict path |

Proposed **internal / unstable** (NOT in the 1.0 promise — free to change):
- `adapter/*` — the T-1 capability + registry (A1b is scoped out, `design/g-a-a3-decision.md`).
- `render/*` internals — the PURE render functions (output format may evolve).
- `search/*`, `provenance/*`, `core/parser.py` (`ProposalParser`), `loop/*` other than the verify entry + `DecisionEngine`.
- The literature/digitization/science-finding types (`LiteratureDecision`, `NegativeControl`, `DigitizedData`/`DigitizedVerification`, `ScienceFinding`, `PubReqs`, `PackageReqs`) — used through the CLI; not promised as a stable Python import.

## 5. Decisions (recorded)

1. **Stability scope = CLI + curated Python API.** The CLI (§2, all 17 verbs incl.
   publishing) is the primary contract. The Python API is the curated core in §4;
   everything else is explicitly internal/unstable.
2. **Publishing layer is in the 1.0 stable surface** — `package`, `pkgreqs`,
   `pubreqs` are complete, suite-covered, and verify-gated; not flagged experimental.
3. **Surface is freezable.** It stopped growing at HEAD-1; the verb set is
   lifecycle-complete (input → execute → evidence → claim → render → verify →
   publish) with no identified missing verb.

## 6. Freeze recommendation

**The surface is ready to freeze for 1.0**, conditional only on the execution
steps in §7 (the curated `__all__` must be made real, since the Python API is in
scope). No CLI change is required to freeze — the contract in §2 stands as-is.

Devil's-advocate (CC meta-rule #3): the publishing layer is the youngest surface
(landed `0ff48bc`→`c3ca867`) and has the least field use. Mitigation: it is fully
covered by the 1362-test suite and the SPEC-PAPER-GATE verify gates, and the user
has explicitly accepted it into the 1.0 surface. If real publishing use later
forces a flag change, semver allows additive 1.x growth; only *breaking* a §2 flag
would require 2.0.

## 7. Remaining execution steps (NOT done here — these are G-D D1/D2/D3)

1. **D1 close — DONE (2026-06-26):** the curated Python API is real —
   `src/sci_adk/__init__.py` re-exports the 29-symbol §4 surface, guarded by
   `tests/test_public_api.py` (pins `__all__`, asserts the adapter is not exposed,
   asserts `import sci_adk` does not pull in the adapter). Suite 1369 passed.
2. **D2** — `pyproject.toml` `version = "0.1.0"` → `"1.0.0"`.
3. **D3** — `v1.0.0` git tag + GitHub release notes.
4. **D4** — PyPI publish decision (`[TBD]`, `release-readiness.md` §6).

Each is its own approved step (checkpoint mode); this record only fixes the
contract they freeze.

## 8. ruff finding (cross-reference, not a freeze blocker)

Measured at HEAD: `ruff check .` (no config → all default rules) reports 202
errors, **all in `tests/`** — `src/` passes clean (zero errors), so the verdict
path is unaffected. Breakdown: F811 ×128, F401 ×64, E402 ×6, F841 ×4. The F811+F401
bulk (192/202) are pytest **fixture-import false positives** — test modules do
`from tests.fixtures import (valid_claim, …)` (`tests/test_claim.py:44`) to bring
fixtures into scope; ruff misreads the imports as unused/redefined because pytest
injects fixtures by parameter name.

- ruff is **not a gate**: CI runs only `pytest -q -m "not integration"`
  (`.github/workflows/ci.yml:32`); there is no ruff config anywhere.
- `ruff --fix` would **delete the fixture imports and break the suite** — do not
  bulk-fix. If a lint gate is ever wanted, the correct fix is config
  (`[tool.ruff.lint.per-file-ignores]` `tests/** = F401,F811`, or move fixtures to
  `conftest.py`), not `--fix`.

Not a 1.0 blocker; recorded so the decision can be made deliberately later.

---

Version: 1.0
Created: 2026-06-26 (sci-adk session 9)
Related: `design/release-readiness.md` §6 (G-D), `design/g-a-a3-decision.md`
(scope of what is validated), `design/sci-adk-as-moai.md` §4.6 (the stage verbs).
