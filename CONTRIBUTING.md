# Contributing to sci-adk

Thanks for your interest in sci-adk — an Agentic Discovery Kit (ADK): a
domain-general rigor / verification system that keeps **record** (what happened)
separate from **belief** (a revisable claim). Before contributing, please read
this guide; sci-adk is not a typical software project and a few of its rules are
load-bearing.

## The one idea to internalize

**Agents propose; the engine judges by frozen criteria.** The verdict path is
deterministic and rule-based. A contribution must never let an LLM (or a human)
self-certify a result. If a change touches how a Claim is decided, it must go
through the `DecisionEngine` / recorded-judge path — not around it.

See [`README.md`](README.md) and [`design/abstractions.md`](design/abstractions.md)
for the Spec / Evidence / Claim model and its invariants.

## Development setup

```bash
git clone https://github.com/ccy5123/sci-adk
cd sci-adk
pip install -e ".[dev]"        # runtime deps + pytest
# PYTHONPATH=src also works without installing.
```

Optional acquisition tooling (`paperforge`, private repo) lives behind the
`tools` extra: `pip install -e ".[tools]"`.

## Running tests

```bash
python -m pytest -q                  # unit tests (the full suite)
python -m pytest -q -m integration   # integration tests (require Docker)
```

CI runs the unit suite on Python 3.11 and 3.12 (Docker integration tests are not
run in CI). A pull request must keep the unit suite green.

## The invariants you must not break

- **Kernel ⊄ adapter (F4).** The rigor kernel (`src/sci_adk/core`, `loop`,
  `provenance`, `render`, `runner`, `search`) must never import from
  `src/sci_adk/adapter/`. This is enforced by
  [`tests/test_kernel_adapter_seam.py`](tests/test_kernel_adapter_seam.py); a PR
  that violates it fails CI.
- **Evidence is append-only.** Never mutate or delete recorded Evidence. Null and
  negative results are valid, complete outcomes — keep them.
- **Specs are frozen.** A Spec amendment is a human-gated, logged operation that
  preserves the prior version (it never edits in place).
- **No metric is hardcoded.** Each Spec declares its own `DecisionRule`; do not
  add global pass/fail constants (e.g. coverage thresholds).

## Adding a capability (new domain)

A capability is **how** an experiment runs at runtime — it never enters the
frozen Spec. To add one:

1. Implement an `ExperimentFn` provider that returns `EvidenceItem`s.
2. Register it in [`src/sci_adk/adapter/registry.py`](src/sci_adk/adapter/registry.py).
3. Keep all Claude-Code-specific logic inside `adapter/` — the kernel sees only
   the three interfaces (Verifier / Experiment / Judge).

A second domain plugging in **without a kernel edit** is the project's
generalization gate — contributions that demonstrate it are especially welcome
(see [`design/release-readiness.md`](design/release-readiness.md), gate G-A).

## Tool policy

sci-adk's *research runtime* deliberately **excludes** some tools common to
software projects — LSP "type-correct = done" gates, ast-grep, Conventional-Commit
automation, and coverage thresholds — because "build state equals truth" is the
assumption sci-adk rejects. These exclusions apply to the research workflow, not
to the engineering layer: the `tests/` suite is ordinary pytest and is expected
to pass. Full policy: [`design/tool-policy.md`](design/tool-policy.md).

## Code conventions

- Type hints on public function signatures; English comments and identifiers.
- No bare `except:`; no mutable default arguments; no `import *`.
- Pydantic v2 for data models (`model_validate`, not `parse_obj`).
- Touch only what the change requires — no drive-by refactors.

## Pull requests

1. Branch from `master`, keep the change focused.
2. `python -m pytest -q` must pass; add tests for new behavior.
3. Describe the change and, if it affects the record/belief path, what Evidence
   or Claim behavior changes and why it stays honest.
4. Open the PR against `master`.

## Reporting bugs / security

Functional bugs: open a GitHub issue. Security-sensitive reports: see
[`SECURITY.md`](SECURITY.md) — please do not file them as public issues.
