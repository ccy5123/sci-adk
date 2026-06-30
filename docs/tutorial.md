# Tutorial: Your First 15 Minutes with sci-adk

sci-adk is a command-line **research compiler** and a domain-general rigor/verification kernel — a *referee*, not a player. It keeps an append-only **record** (Evidence: what happened) separate from revisable **belief** (Claims: what the evidence supports). Agents propose; the engine judges by frozen criteria. No self-certification.

This tutorial has five parts. Parts 1–2 need nothing beyond a Python install. Part 3 needs nothing for the proposal-compilation step; the live demo run in Part 3 (marked OPTIONAL) needs Docker.

---

## Setup

```bash
git clone https://github.com/ccy5123/sci-adk
cd sci-adk
pip install -e .
# Alternative without installing: PYTHONPATH=src python3 -m sci_adk.cli <verb> …
```

The console script `sci-adk` becomes available after `pip install -e .`.

---

## Part 1 — Re-verify the bundled run (60-second core)

The repository ships with a pre-recorded run `runs/t1-godel/`. Verify it:

```
$ sci-adk verify runs/t1-godel
verified run 't1-godel' -> runs/t1-godel
  record digest (sha256): d07591e443a8500338d1223e65099f0308813788f91a024273cd88a2d74672ad
    - hyp-t1: REPRODUCED  (recorded=supported, re-derived=supported)
  all recorded claims reproduced from the record
# exit code 0
```

Check the run's current state:

```
$ sci-adk status runs/t1-godel
sci-adk status [t1-godel]: 0 unresolved claims, prior-work open, 1 checkpoint awaiting verdict
  spec: t1-godel  (1 hypothesis, run 't1-godel')
  claims: supported=1
  prior-work decision: OPEN (not yet recorded)
  checkpoints awaiting verdict: science
# exit code 0
```

**What just happened.**

`sci-adk verify` re-applied the *frozen* decision rule to the recorded evidence and re-derived the same verdict (`REPRODUCED`). It also printed a SHA-256 digest of the entire evidence record — tamper-evidence. Exit code 0 means every recorded claim reproduces from the record alone. No language model, no API call, no internet connection required.

This is sci-adk's core property: **a third party can run `verify` on the record, offline, and reach the same verdict.** The digest gives them confidence the record has not been altered after the fact.

`sci-adk status` is a read-only snapshot of recorded state and always exits 0. It is cheap to call between steps.

---

## Part 2 — Open the run directory (record vs belief, concretely)

The run directory `runs/t1-godel/` contains:

```
runs/t1-godel/
├── spec.json          ← frozen input contract
├── evidence/          ← append-only log of what happened
├── claims/            ← derived belief (revisable)
├── checkpoints/       ← open decisions awaiting resolution
├── artifacts/         ← capability outputs
├── paper/             ← compiled paper draft
└── science.md         ← spec-gate rigor findings (see Part 3)
```

Each directory maps to a concept.

### (a) The frozen spec — `runs/t1-godel/spec.json`

Key fields (abbreviated):

```json
{
  "id": "t1-godel",
  "hypotheses": [
    {
      "id": "hyp-t1",
      "statement": "Molecule graphs admit an injective Gödel-style encoding on the tested set",
      "mode": "exploratory",
      "decision_rule": {
        "kind": "threshold",
        "expression": "collision_count == 0 over the test set => support; collision_count > 0 => refute",
        "params": { "statistic": "collision_count", "op": "==", "value": 0.0 }
      },
      "referent": "formal",
      "novelty_result": false,
      "novelty_method": false,
      "epistemic_kind": "finding"
    }
  ]
}
```

The hypothesis `hyp-t1` carries its own pre-registered `decision_rule`: `collision_count == 0` over the test set means support; `> 0` means refute. There are no hard-coded global metrics — **each spec declares its own rule, and the verdict is judged against that rule and no other.** The spec is frozen as the first stage, before any evidence is collected.

### (b) The append-only evidence — `runs/t1-godel/evidence/evi-t1-20260616-111516-ddcad848.json`

Key fields (abbreviated):

```json
{
  "id": "evi-t1-20260616-111516-ddcad848",
  "kind": "experiment_run",
  "provenance": {
    "code_ref": "6800c510f53eb912fcc1a459059d9ac633db2d11",
    "environment": "capability:t1-molecular-godel, docker:sci-adk-python-base, image_id:f4b2801533cb"
  },
  "result": {
    "type": "quantitative",
    "point": 0.0,
    "finding": "{\"statistic\": \"collision_count\", \"collision_count\": 0, \"round_trip_ok\": true, \"n_molecules\": 6, \"capability\": \"t1-molecular-godel\"}"
  },
  "bears_on": [
    { "target_id": "hyp-t1", "direction": "supports" }
  ]
}
```

Evidence records **what happened**: the result (`collision_count: 0`, `n_molecules: 6`, `round_trip_ok: true`), the code commit it ran against, and the Docker image that executed it. The `bears_on` field states which hypothesis this item bears on and in which direction (`supports` here, but `refutes` and `inconclusive` are equally valid outcomes). Evidence items are **immutable and append-only** — they are never overwritten.

### (c) The revisable claim — `runs/t1-godel/claims/claim-hyp-t1.json`

Key fields (abbreviated):

```json
{
  "id": "claim-hyp-t1",
  "status": "supported",
  "confidence": {
    "basis": "threshold rule: statistic 'point'=0 == 0 is met (combine='latest', margin=0)"
  },
  "evidence_set": [
    { "evidence_id": "evi-t1-20260616-111516-ddcad848", "role": "supporting" }
  ],
  "history": [
    {
      "at": "2026-06-16T11:15:16.825232Z",
      "from_status": "proposed",
      "to_status": "supported",
      "triggered_by": "evi-t1-20260616-111516-ddcad848",
      "note": "Initial evaluation via DecisionEngine"
    }
  ]
}
```

The claim is **belief** — derived from the record. Its `history` shows the status move (`proposed → supported`) triggered by the evidence item. A future contradicting evidence item (say, a collision found in a larger test set) could move the claim to `contested` or `refuted`. This non-monotone, revisable nature of claims — contrasted with the monotone, append-only evidence — is the record/belief separation made concrete.

---

## Part 3 — Compile your own proposal (see the rigor gates fire)

sci-adk accepts a four-pane Markdown proposal with `# Background` / `# Goal` / `# Method` / `# Expected Output` headings (Korean equivalents also accepted).

Save the following as `proposal.md`:

```markdown
# Background
Molecular graphs have no canonical integer key, so structurally distinct
molecules can collide under naive encodings.

# Goal
Define an injective Gödel-style numbering for small molecular graphs.

# Method
Encode atoms and bonds by prime factorization + Cantor pairing; test
injectivity (zero collisions) over a fixed molecule set.

# Expected Output
A collision-free encoding over the tested set, reported as an injectivity verdict.
```

Then compile it:

```bash
sci-adk run proposal.md
```

A bare `run` compiles the Spec and a proposal draft, then **surfaces checkpoints** — it does not invent an experiment. Proof and qualitative hypotheses become checkpoints for the in-session Claude agent to resolve; numeric threshold rules run autonomously via the DecisionEngine once evidence is recorded.

### The science guards are a feature

Under the default strict science guards, compiling an under-justified hypothesis surfaces findings in `runs/<id>/science.md`. The bundled run illustrates all four:

```
## G1 -- hyp-t1
- formal + deterministic (threshold) hypothesis asserting no novelty, still
  epistemic_kind='finding': a constructively-true / already-known result would
  be framed as an empirical discovery. Reclassify (epistemic_kind -> 'unit_test'
  if it is true by construction, 'capability_check' for a capability assertion)
  or assert novelty (novelty_result/novelty_method with a recorded
  found_nothing prior-art search). (G1)

## G2 -- hyp-t1
- formal + deterministic (threshold) hypothesis declares no
  discriminating_cases: a pass over an easy/undeclared test set is
  non-discriminating. Declare the hard cases that make a pass informative,
  each with the reason it separates a correct method from a broken one. (G2)

## G3 -- hyp-t1
- formal + deterministic (threshold) hypothesis: a strict SUPPORTED will
  REQUIRE a NEGATIVE_CONTROL Evidence item -- a deliberately mutated method
  that was actually run and returned NOT-SUPPORTED. Plan to record one
  (e.g. remove a tie-breaking invariant from the canonicalizer and confirm
  collisions appear). (G3)

## G4 -- hyp-t1
- mode-coherence: a frozen pre-registered threshold decision rule is treated
  as binding pass/fail, but mode=='exploratory'. Set mode='confirmatory' to
  honestly pre-register the hard threshold, or use a non-threshold rule for
  exploratory work. (G4)
```

The engine refusing to silently bless an under-justified claim **is the point**. These are spec-layer rigor gates — pure rule-based, no LLM — surfaced at compile time. They are never an automatic halt. You resolve each by amending the Spec (supply the missing artifact or a justification), then re-running. See [`design/science-guards.md`](../design/science-guards.md) for the full specification.

### OPTIONAL — live demo run (requires Docker)

```bash
# Quick smoke run: disables strict science guards
sci-adk run --t1-demo --no-strict-science

# Default: surfaces G1–G4 findings (intended behavior, not a bug)
sci-adk run --t1-demo
```

`--t1-demo` runs the T-1 molecular Gödel-encoding capability over its designed molecule test set inside a Docker container and yields an autonomous injectivity verdict via the DecisionEngine. Without `--no-strict-science` it deliberately surfaces the G1–G4 findings above — the demo carries no negative control by design (G3 is real, not a mistake).

---

## Part 4 — What `verify` does and does not guarantee

`sci-adk verify` audits **internal consistency**: does the recorded evidence satisfy the pre-registered decision rules? It also produces a SHA-256 record digest as tamper-evidence.

It does **not** audit scientific validity. A hypothesis can be internally consistent — every rule satisfied, every claim reproduced — and still be wrong, poorly designed, or trivially true. Internal consistency is necessary, not sufficient, for a result to be true. The science guards (Part 3) catch some structural weaknesses at spec-compile time, but they are not a substitute for scientific judgment.

On the freeze discipline: the spec is frozen as the first stage (before evidence is collected), and the record digest provides tamper-evidence. Neither mechanism provides a trusted wall-clock timestamp in the way a preregistration server does. Like pre-registration on OSF, it assumes the spec was committed in good faith before the experiment ran. The digest lets a third party detect if the record was altered afterward; it cannot detect if the spec was written post-hoc. Keep that boundary honest.

---

## Part 5 — Leave a trace

If you ran sci-adk — even just Part 1 — please open a GitHub issue at  
**https://github.com/ccy5123/sci-adk/issues**

Describe what you ran and what you expected or saw. Questions, bug reports, feature suggestions, and "I tried X on domain Y" reports are all welcome. External use reports are the most load-bearing evidence that the verification kernel generalizes beyond the bundled example domain.

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for development setup and contribution guidelines.

To cite sci-adk in a paper, see [`CITATION.cff`](../CITATION.cff).
